import asyncio
import os
import re
import secrets
from collections import deque
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.language import translate_texts, language_catalog
from app.providers.tradesoft_parts_catalogs import TradesoftPartsCatalogsAdapter, TradesoftError

APP_VERSION = "2.4.10"
TIMEOUT_SECONDS = float(os.getenv("CATALOG_TIMEOUT_SECONDS", "25"))
TRADESOFT_API_TOKEN = os.getenv("TRADESOFT_API_TOKEN", "").strip()
TRADESOFT_ENABLED = os.getenv("TRADESOFT_ENABLED", "false").strip().lower() == "true" and bool(TRADESOFT_API_TOKEN)
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
TRADESOFT_ADAPTER = TradesoftPartsCatalogsAdapter(TRADESOFT_API_TOKEN, timeout_seconds=TIMEOUT_SECONDS) if TRADESOFT_ENABLED else None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = FastAPI(
    title="AI Manager Catalog API",
    version=APP_VERSION,
    description="OEM catalogue integration through TradeSoft Parts.Catalogs. Other provider slots are reserved and disabled.",
)

_configured_origins = os.getenv("CORS_ORIGINS", "")
allowed_origins = [
    item.strip().rstrip("/")
    for item in _configured_origins.split(",")
    if item.strip() and item.strip() != "*"
]
if not allowed_origins:
    allowed_origins = [
        "https://a0934600088-glitch.github.io",
        "https://ai-manager-api-production.up.railway.app",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]
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
    mode: Literal["parts", "diagrams", "diagram", "groups", "models"] = "parts"
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
_VIN_PATTERN = re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])", re.IGNORECASE)


def _mask_trace_value(value: Any) -> Any:
    """Remove complete VINs from diagnostics while retaining the final four characters."""
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            if str(key).lower() in {"vin", "identifier"} and isinstance(item, str) and len(item.strip()) == 17:
                normalized = item.strip()
                masked[key] = "*" * 13 + normalized[-4:]
            else:
                masked[key] = _mask_trace_value(item)
        return masked
    if isinstance(value, (list, tuple)):
        return [_mask_trace_value(item) for item in value]
    if isinstance(value, str):
        return _VIN_PATTERN.sub(lambda match: "*" * 13 + match.group(0)[-4:], value)
    return value


def trace(stage: str, provider: str, status: str, message: str, details: Any = None):
    TRACE_EVENTS.appendleft({
        "time": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "provider": provider,
        "status": status,
        "message": _mask_trace_value(message),
        "details": _mask_trace_value(details),
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
async def admin_traces(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not ADMIN_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Admin trace access is disabled until ADMIN_API_TOKEN is configured.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_API_TOKEN):
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    return {
        "events": list(TRACE_EVENTS),
        "retained": len(TRACE_EVENTS),
        "retention": "in-memory; cleared on process restart",
    }


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
                "capabilities": ["vin_decode", "frame_decode", "vehicle_catalogue", "group_navigation", "schemas", "oem_parts", "diagram_callouts"],
                "authentication": "Server-side API key",
            }
        ],
        "reserved_slots": [
            {"id": f"catalog_slot_{i:02d}", "name": f"Reserved catalogue slot {i}", "configured": False, "enabled": False}
            for i in range(2, 11)
        ],
        "disabled_legacy_providers": ["solocatalog_mcp", "nhtsa_vpic"],
    }


def _first_vehicle_text(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def _normalize_tradesoft_vehicle(record: dict[str, Any]) -> dict[str, Any]:
    """Expose documented TradeSoft CarInfo fields in the stable UI contract.

    TradeSoft CarInfo uses 'title' and 'brand'; the chat UI consumes 'model'
    and 'brand'. Keep every original provider field and identifier unchanged.
    """
    normalized = dict(record)
    brand = _first_vehicle_text(record, "brand", "make", "manufacturer", "manufacturerName")
    model = _first_vehicle_text(
        record, "model", "modelName", "model_name", "modelDescription",
        "model_description", "vehicleName", "vehicle_name", "title",
    )
    if brand:
        normalized["brand"] = brand
        normalized["make"] = brand
    if model:
        normalized["model"] = model
        normalized["model_description"] = model
    return normalized


def _has_nested_vehicle_field(record: Any, aliases: set[str]) -> bool:
    pending = [record]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, (dict, list)) or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).replace("_", "").lower() in aliases and isinstance(value, (str, int, float)) and str(value).strip():
                    return True
                if isinstance(value, (dict, list)):
                    pending.append(value)
        else:
            pending.extend(current)
    return False


def _vehicle_completeness(vehicle: dict[str, Any]) -> dict[str, Any]:
    identity_complete = bool(vehicle.get("brand") and vehicle.get("model"))
    has_year = _has_nested_vehicle_field(
        vehicle, {"year", "modelyear", "productionyear", "manufactured", "date", "productiondate"}
    )
    has_engine = _has_nested_vehicle_field(
        vehicle, {"engine", "enginecode", "engineinfo", "motortype", "enginevariant"}
    )
    missing = []
    if not identity_complete:
        missing.append("brand_or_model")
    if not has_year:
        missing.append("production_year")
    if not has_engine:
        missing.append("engine")
    return {
        "identity_complete": identity_complete,
        "details_complete": identity_complete and has_year and has_engine,
        "missing_fields": missing,
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
            vehicle: Any = _normalize_tradesoft_vehicle(candidates[0])
            status = "success"
        else:
            vehicle = {"candidates": [_normalize_tradesoft_vehicle(item) for item in candidates]}
            status = "ambiguous"
        catalog_verified = bool(
            status == "success"
            and isinstance(vehicle, dict)
            and vehicle.get("catalogId") is not None
            and vehicle.get("carId") is not None
        )
        completeness = _vehicle_completeness(vehicle) if isinstance(vehicle, dict) else {
            "identity_complete": False, "details_complete": False,
            "missing_fields": ["brand_or_model", "production_year", "engine"],
        }
        vehicle_data_complete = completeness["details_complete"]
        trace("VIN decode", "tradesoft_parts_catalogs", status, "TradeSoft OEM VIN lookup completed", {
            "vin": vin,
            "candidate_count": len(candidates),
            "candidate_fields": sorted(candidates[0].keys()) if candidates else [],
            "has_catalog_id": bool(candidates and candidates[0].get("catalogId") is not None),
            "has_car_id": bool(candidates and candidates[0].get("carId") is not None),
            "has_title": bool(candidates and _first_vehicle_text(candidates[0], "title")),
            "has_brand": bool(candidates and _first_vehicle_text(candidates[0], "brand")),
            "vehicle_identity_complete": completeness["identity_complete"],
            "vehicle_data_complete": vehicle_data_complete,
            "vehicle_missing_fields": completeness["missing_fields"],
        })
        return {
            "vin": vin,
            "status": status,
            "vehicle": vehicle,
            "vehicle_identity_complete": completeness["identity_complete"],
            "vehicle_data_complete": vehicle_data_complete,
            "vehicle_missing_fields": completeness["missing_fields"],
            "providers": [_provider_result("tradesoft_parts_catalogs", status, candidates)],
            "is_oem_catalog_verified": catalog_verified,
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
