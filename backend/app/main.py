import asyncio
import json
import os
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.language import translate_texts, language_catalog
from app.providers.tradesoft_parts_catalogs import TradesoftPartsCatalogsAdapter, TradesoftError

APP_VERSION = "2.2.0"
SOLOCATALOG_MCP_URL = os.getenv("SOLOCATALOG_MCP_URL", "https://solocatalog.com/mcp")
NHTSA_BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"
TIMEOUT_SECONDS = float(os.getenv("CATALOG_TIMEOUT_SECONDS", "25"))
TRADESOFT_API_TOKEN = os.getenv("TRADESOFT_API_TOKEN", "").strip()
TRADESOFT_ENABLED = os.getenv("TRADESOFT_ENABLED", "false").strip().lower() == "true" and bool(TRADESOFT_API_TOKEN)
TRADESOFT_ADAPTER = TradesoftPartsCatalogsAdapter(TRADESOFT_API_TOKEN, timeout_seconds=TIMEOUT_SECONDS) if TRADESOFT_ENABLED else None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = FastAPI(
    title="AI Manager Catalog API",
    version=APP_VERSION,
    description="Catalog integrations: SoloCatalog MCP, NHTSA vPIC and optional TradeSoft OEM Parts.Catalogs.",
)

allowed_origins = [
    item.strip()
    for item in os.getenv("CORS_ORIGINS", "*").split(",")
    if item.strip()
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
    mode: Literal["parts", "diagrams", "diagram", "models"] = "parts"
    vin: str | None = Field(default=None, min_length=5, max_length=40)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    diagram: str | None = Field(default=None, max_length=200)
    q: str | None = Field(default=None, max_length=80)
    lang: Literal["en", "uk", "az", "ru"] = "ru"


class TranslationRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=30)
    source: str = Field(default="auto", min_length=2, max_length=8)
    target: str = Field(min_length=2, max_length=8)
    domain: Literal["general", "automotive"] = "general"


class MCPError(RuntimeError):
    pass


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


def _mcp_payload(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        raise MCPError(f"SoloCatalog MCP HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "")
    body = response.text
    if response.status_code == 202 and not body.strip():
        return {}
    if "text/event-stream" in content_type:
        data_lines = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
        if not data_lines:
            raise MCPError("SoloCatalog MCP returned an empty event stream")
        body = data_lines[-1]
    try:
        return json.loads(body)
    except ValueError as exc:
        raise MCPError("SoloCatalog MCP returned an invalid JSON-RPC response") from exc


async def mcp_request(client: httpx.AsyncClient, payload: dict, session_id: str | None = None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
        headers["MCP-Protocol-Version"] = "2025-03-26"
    response = await client.post(SOLOCATALOG_MCP_URL, headers=headers, json=payload)
    return _mcp_payload(response), response.headers.get("Mcp-Session-Id", session_id)


async def solo_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        init, session_id = await mcp_request(client, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "ai-manager-demo", "version": APP_VERSION},
            },
        })
        if init.get("error"):
            raise MCPError(str(init["error"]))
        await mcp_request(client, {
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
        }, session_id)
        listed, session_id = await mcp_request(client, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
        }, session_id)
        if listed.get("error"):
            raise MCPError(str(listed["error"]))
        tools = listed.get("result", {}).get("tools", [])
        tool = next((t for t in tools if t.get("name") == tool_name), None)
        if not tool:
            raise MCPError(f"SoloCatalog MCP tool '{tool_name}' is not available")
        schema = tool.get("inputSchema", {}) or {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        safe_args = {k: v for k, v in arguments.items() if k in properties and v is not None}
        missing = [key for key in required if key not in safe_args]
        if missing:
            raise MCPError(f"Required arguments for {tool_name} are not available: {', '.join(missing)}")
        called, _ = await mcp_request(client, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": tool_name, "arguments": safe_args},
        }, session_id)
        if called.get("error"):
            raise MCPError(str(called["error"]))
        result = called.get("result", {})
        if result.get("isError"):
            raise MCPError(json.dumps(result.get("content", []), ensure_ascii=False))
        return {"tool": tool_name, "data": result, "provider": "solocatalog_mcp"}


async def nhtsa_decode(vin: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.get(f"{NHTSA_BASE_URL}/DecodeVinValuesExtended/{vin}", params={"format": "json"})
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("Results", [])
    row = rows[0] if rows else {}
    useful = {k: v for k, v in row.items() if v not in (None, "", "0", "Not Applicable")}
    return {"provider": "nhtsa_vpic", "data": useful}


def _provider_result(provider: str, status: str, data: Any = None, error: str | None = None):
    result = {"provider": provider, "status": status}
    if data is not None:
        result["data"] = data
    if error:
        result["error"] = error
    return result


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
            {"id": "argos_translate", "type": "translation", "auth": "open-source self-hosted models", "enabled": True},
            {"id": "solocatalog_mcp", "type": "parts_catalog", "auth": "no-key light-use allowance", "enabled": True},
            {"id": "nhtsa_vpic", "type": "vin_decoder", "auth": "public", "enabled": True},
            {"id": "tradesoft_parts_catalogs", "type": "oem_vehicle_catalog", "auth": "server environment token", "enabled": TRADESOFT_ENABLED},
        ],
        "provider_limit_per_tenant": 10,
        "note": "Health confirms this adapter is running; provider reachability is tested on actual requests.",
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
        "configured": 2 + int(TRADESOFT_ENABLED),
        "providers": [
            {"id": "solocatalog_mcp", "name": "SoloCatalog", "kind": "parts_catalog", "capabilities": ["vin_decode", "parts_search", "diagrams", "diagram_parts", "oem_lookup"], "authentication": "No key for small daily MCP allowance"},
            {"id": "nhtsa_vpic", "name": "NHTSA vPIC", "kind": "vin_decoder", "capabilities": ["vin_decode"], "authentication": "Public, no key", "catalog": False},
        ] + ([{"id": "tradesoft_parts_catalogs", "name": "TradeSoft Parts.Catalogs", "kind": "oem_vehicle_catalog", "capabilities": ["vin_decode", "frame_decode"], "authentication": "Server environment token"}] if TRADESOFT_ENABLED else []),
        "not_configured": ["RockAuto unofficial integration"] + ([] if TRADESOFT_ENABLED else ["Parts-Catalogs / Tradesoft"]),
    }


@app.post("/api/catalog/v1/vehicles/decode")
async def decode_vehicle(payload: DecodeRequest):
    vin = payload.vin.strip().upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{5,40}", vin):
        raise HTTPException(status_code=422, detail="VIN/frame contains unsupported characters.")
    tasks = await asyncio.gather(
        solo_call("decode_vin", {"vin": vin, "lang": payload.lang}),
        nhtsa_decode(vin),
        return_exceptions=True,
    )
    results = []
    for provider, item in zip(("solocatalog_mcp", "nhtsa_vpic"), tasks):
        if isinstance(item, Exception):
            results.append(_provider_result(provider, "unavailable", error=str(item)[:300]))
        else:
            results.append(_provider_result(provider, "success", item.get("data")))
    for provider_result in results:
        trace(
            "VIN decode",
            provider_result["provider"],
            provider_result["status"],
            "VIN provider request completed" if provider_result["status"] == "success" else "VIN provider request failed",
            {"vin": vin, "error": provider_result.get("error")},
        )
    primary = next((r.get("data") for r in results if r["provider"] == "solocatalog_mcp" and r["status"] == "success"), None)
    if not primary:
        primary = next((r.get("data") for r in results if r["provider"] == "nhtsa_vpic" and r["status"] == "success"), None)
    if not primary:
        raise HTTPException(status_code=502, detail={"message": "All VIN providers failed", "providers": results})
    if TRADESOFT_ADAPTER:
        try:
            candidates = await TRADESOFT_ADAPTER.decode(vin, "vin")
            results.append(_provider_result("tradesoft_parts_catalogs", "success", candidates))
            trace("VIN decode", "tradesoft_parts_catalogs", "success", "TradeSoft OEM VIN request completed", {"vin": vin, "candidate_count": len(candidates)})
        except TradesoftError as exc:
            results.append(_provider_result("tradesoft_parts_catalogs", exc.code, error=exc.message))
            trace("VIN decode", "tradesoft_parts_catalogs", exc.code, "TradeSoft OEM VIN request failed", {"vin": vin, "http_status": exc.status_code})
    tradesoft_data = next((r.get("data") for r in results if r["provider"] == "tradesoft_parts_catalogs" and r["status"] == "success" and r.get("data")), None)
    if tradesoft_data:
        primary = tradesoft_data[0] if len(tradesoft_data) == 1 else {"candidates": tradesoft_data, "status": "ambiguous"}
    return {"vin": vin, "vehicle": primary, "providers": results, "is_oem_catalog_verified": bool(tradesoft_data)}


@app.post("/api/catalog/v1/lookup")
async def catalogue_lookup(payload: LookupRequest):
    if payload.mode != "models" and not payload.vin:
        raise HTTPException(status_code=422, detail="A VIN is required for vehicle-specific catalogue lookup.")
    if payload.mode == "parts" and not payload.q:
        raise HTTPException(status_code=422, detail="A part name or number is required.")
    if payload.mode == "models":
        tool, args = "find_models", {"brand": payload.brand, "q": payload.q, "lang": payload.lang}
    elif payload.mode == "diagrams":
        tool, args = "list_diagrams", {"vin": payload.vin, "lang": payload.lang}
    elif payload.mode == "diagram":
        tool, args = "get_diagram_parts", {"vin": payload.vin, "model": payload.model, "diagram": payload.diagram, "lang": payload.lang}
    else:
        tool, args = "search_parts", {"vin": payload.vin, "q": payload.q, "query": payload.q, "part_name": payload.q, "lang": payload.lang}
    try:
        trace("Catalog lookup", "solocatalog_mcp", "started", f"Calling {tool}", {"mode": payload.mode, "vin": payload.vin, "arguments": args})
        result = await solo_call(tool, args)
        trace("Catalog lookup", "solocatalog_mcp", "success", f"{tool} returned data", {"mode": payload.mode, "vin": payload.vin, "tool": tool, "result": result["data"]})
        return {"status": "success", "mode": payload.mode, "vin": payload.vin, "source": "solocatalog_mcp", "result": result["data"], "is_demo_data": False}
    except Exception as exc:
        trace("Catalog lookup", "solocatalog_mcp", "error", str(exc)[:300], {"mode": payload.mode, "vin": payload.vin, "tool": tool})
        raise HTTPException(status_code=502, detail={"provider": "solocatalog_mcp", "status": "unavailable", "message": str(exc)[:300]}) from exc
