import asyncio
import os
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.language import translate_texts, language_catalog
from app.providers.tradesoft_parts_catalogs import TradesoftPartsCatalogsAdapter, TradesoftError

APP_VERSION = "2.4.9"
TIMEOUT_SECONDS = float(os.getenv("CATALOG_TIMEOUT_SECONDS", "25"))
TRADESOFT_API_TOKEN = os.getenv("TRADESOFT_API_TOKEN", "").strip()
TRADESOFT_ENABLED = os.getenv("TRADESOFT_ENABLED", "false").strip().lower() == "true" and bool(TRADESOFT_API_TOKEN)
TRADESOFT_ADAPTER = TradesoftPartsCatalogsAdapter(TRADESOFT_API_TOKEN, timeout_seconds=TIMEOUT_SECONDS) if TRADESOFT_ENABLED else None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = FastAPI(
    title="AI Manager Catalog API",
    version=APP_VERSION,
    description="OEM catalogue integration through TradeSoft Parts.Catalogs. Other provider slots are reserved and disabled.",
)

allowed_origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "*").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


class DecodeRequest(BaseModel):
    vin: str = Field(min_length=5, max_length=40)
    lang: Literal["en", "uk", "az", "ru"] = "ru"


class LookupRequest(BaseModel):
    mode: Literal["parts", "diagrams", "diagram", "models"] = "parts"
    vin: str | None = Field(default=None, min_length=5, max_length=40)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    diagram: str | None = Field(default=None, max_length=200)
    q: str | None = Field(default=None, max_length=120)
    group_id: str | int | None = None
    lang: Literal["en", "uk", "az", "ru"] = "ru"


class TranslationRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=30)
    source: str = Field(default="auto", min_length=2, max_length=8)
    target: str = Field(min_length=2, max_length=8)
    domain: Literal["general", "automotive"] = "general"


TRACE_EVENTS = deque(maxlen=250)


def trace(stage: str, provider: str, status: str, message: str, details: Any = None):
    TRACE_EVENTS.appendleft({
        "time": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "provider": provider,
        "status": status,
        "message": message,
        "details": details,
    })


def _provider_result(provider: str, status: str, data: Any = None, error: str | None = None):
    result = {"provider": provider, "status": status}
    if data is not None:
        result["data"] = data
    if error:
        result["error"] = error
    return result


def _require_tradesoft():
    if not TRADESOFT_ADAPTER:
        raise HTTPException(status_code=503, detail={
            "provider": "tradesoft_parts_catalogs",
            "status": "not_configured",
            "message": "OEM Parts.Catalogs is not enabled. Configure TRADESOFT_API_TOKEN and TRADESOFT_ENABLED=true on the backend.",
        })
    return TRADESOFT_ADAPTER


@app.get("/")
async def home():
    index = os.path.join(ROOT, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"name": "AI Manager Catalog API", "version": APP_VERSION, "docs": "/docs"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "providers": [
            {"id": "tradesoft_parts_catalogs", "type": "primary_oem_catalog", "enabled": TRADESOFT_ENABLED},
        ],
        "reserved_provider_slots": 9,
        "note": "Process health does not prove upstream reachability; a successful OEM request is required.",
    }


@app.get("/api/language/v1/languages")
async def language_languages():
    return await asyncio.to_thread(language_catalog)


@app.post("/api/language/v1/translate")
async def language_translate(payload: TranslationRequest):
    try:
        translations = await asyncio.to_thread(
            translate_texts, payload.texts, payload.source.lower(),
            payload.target.lower(), payload.domain
        )
        return {
            "status": "success", "engine": "argos_translate",
            "domain": payload.domain, "source": payload.source.lower(),
            "target": payload.target.lower(), "translations": translations,
            "note": "Open-source general translation with protected automotive terminology and identifiers."
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        trace("Language translation", "argos_translate", "unavailable", str(exc)[:300],
              {"target": payload.target, "domain": payload.domain})
        raise HTTPException(status_code=503, detail={
            "provider": "argos_translate", "status": "unavailable",
            "message": "Translation model is not available yet. Retry after model initialization."
        }) from exc


@app.get("/api/admin/traces")
async def admin_traces():
    return {"events": list(TRACE_EVENTS), "retained": len(TRACE_EVENTS), "retention": "in-memory; cleared on process restart"}


@app.get("/api/catalog/v1/providers")
async def providers():
    return {
        "limit": 10,
        "configured": int(TRADESOFT_ENABLED),
        "primary_provider": "tradesoft_parts_catalogs" if TRADESOFT_ENABLED else None,
        "providers": [
            {
                "id": "tradesoft_parts_catalogs",
                "name": "TradeSoft OEM Parts.Catalogs",
                "kind": "primary_oem_catalog",
                "enabled": TRADESOFT_ENABLED,
                "capabilities": ["vin_decode", "frame_decode", "vehicle_catalogue", "schemas", "oem_parts", "diagram_callouts"],
                "authentication": "Server-side API key",
            }
        ],
        "reserved_slots": [
            {"id": f"catalog_slot_{i:02d}", "name": f"Reserved catalogue slot {i}", "configured": False, "enabled": False}
            for i in range(2, 11)
        ],
        "disabled_legacy_providers": ["solocatalog_mcp", "nhtsa_vpic"],
    }


@app.post("/api/catalog/v1/vehicles/decode")
async def decode_vehicle(payload: DecodeRequest):
    vin = payload.vin.strip().upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        raise HTTPException(status_code=422, detail="VIN must contain 17 valid characters.")
    adapter = _require_tradesoft()
    try:
        candidates = await adapter.decode(vin, "vin", payload.lang)
        if len(candidates) == 1:
            vehicle: Any = candidates[0]
            status = "success"
        else:
            vehicle = {"candidates": candidates}
            status = "ambiguous"
        trace("VIN decode", "tradesoft_parts_catalogs", status, "TradeSoft OEM VIN lookup completed", {
            "vin": vin, "candidate_count": len(candidates),
        })
        return {
            "vin": vin,
            "vehicle": vehicle,
            "providers": [_provider_result("tradesoft_parts_catalogs", status, candidates)],
            "is_oem_catalog_verified": True,
            "source": "tradesoft_parts_catalogs",
        }
    except TradesoftError as exc:
        trace("VIN decode", "tradesoft_parts_catalogs", exc.code, exc.message, {
            "vin": vin, "http_status": exc.status_code,
        })
        raise HTTPException(status_code=502, detail={
            "provider": "tradesoft_parts_catalogs", "status": exc.code, "message": exc.message,
        }) from exc


@app.post("/api/catalog/v1/lookup")
async def catalogue_lookup(payload: LookupRequest):
    if not payload.vin:
        raise HTTPException(status_code=422, detail="A VIN is required for OEM catalogue lookup.")
    if payload.mode == "parts" and not payload.q and not payload.group_id:
        raise HTTPException(status_code=422, detail="A part name or selected group_id is required.")
    adapter = _require_tradesoft()
    vin = payload.vin.strip().upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        raise HTTPException(status_code=422, detail="VIN must contain 17 valid characters.")
    try:
        result = await adapter.lookup(
            vin, payload.mode, payload.q, payload.lang, payload.group_id
        )
        trace("OEM catalogue lookup", "tradesoft_parts_catalogs", "success", "TradeSoft catalogue request completed", {
            "mode": payload.mode, "vin": vin, "has_query": bool(payload.q), "has_group_id": payload.group_id is not None,
        })
        return {
            "status": "success",
            "mode": payload.mode,
            "vin": vin,
            "source": "tradesoft_parts_catalogs",
            "result": result,
            "is_demo_data": False,
        }
    except TradesoftError as exc:
        trace("OEM catalogue lookup", "tradesoft_parts_catalogs", exc.code, exc.message, {
            "mode": payload.mode, "vin": vin, "http_status": exc.status_code,
        })
        raise HTTPException(status_code=502, detail={
            "provider": "tradesoft_parts_catalogs", "status": exc.code, "message": exc.message,
        }) from exc
