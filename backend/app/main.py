import asyncio
import os
import re
import secrets
from collections import deque
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.language import translate_texts, language_catalog
from app.providers.tradesoft_parts_catalogs import TradesoftPartsCatalogsAdapter, TradesoftError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as version_file:
    APP_VERSION = version_file.read().strip()
if not APP_VERSION:
    raise RuntimeError("backend/VERSION must contain the release version")
TIMEOUT_SECONDS = float(os.getenv("CATALOG_TIMEOUT_SECONDS", "25"))
TRADESOFT_API_TOKEN = os.getenv("TRADESOFT_API_TOKEN", "").strip()
TRADESOFT_ENABLED = os.getenv("TRADESOFT_ENABLED", "false").strip().lower() == "true" and bool(TRADESOFT_API_TOKEN)
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
admin_auth = HTTPBasic(auto_error=False)
TRADESOFT_ADAPTER = TradesoftPartsCatalogsAdapter(TRADESOFT_API_TOKEN, timeout_seconds=TIMEOUT_SECONDS) if TRADESOFT_ENABLED else None
app = FastAPI(
    title="AI Manager Catalog API",
    version=APP_VERSION,
    description="OEM catalogue search through TradeSoft Parts.Catalogs.",
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
    allow_headers=["Content-Type", "X-Request-ID", "X-Admin-Token", "Authorization", "X-Conversation-ID"],
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


class AnalyticsEventRequest(BaseModel):
    event_type: str = Field(min_length=2, max_length=80)
    conversation_id: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranslationRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=30)
    source: str = Field(default="auto", min_length=2, max_length=8)
    target: str = Field(min_length=2, max_length=8)
    domain: Literal["general", "automotive"] = "general"


from app import analytics

@app.middleware("http")
async def analytics_request_middleware(request, call_next):
    started = asyncio.get_running_loop().time()
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/admin/") and path != "/api/analytics/events":
        duration_ms = (asyncio.get_running_loop().time() - started) * 1000
        event_type = "vin_decode" if path.endswith("/vehicles/decode") else ("parts_lookup" if path.endswith("/lookup") else "http_request")
        provider = "tradesoft_parts_catalogs" if path.startswith("/api/catalog/") else "backend"
        try:
            await asyncio.to_thread(
                analytics.record_event, event_type,
                conversation_id=request.headers.get("X-Conversation-ID"),
                route=path, method=request.method, status_code=response.status_code,
                duration_ms=duration_ms, metadata={"provider": provider},
            )
        except Exception:
            # Analytics must never take down the customer chat.
            pass
    return response


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


@app.on_event("startup")
async def verify_analytics_database_on_startup():
    result = await asyncio.to_thread(analytics.database_health)
    # Emit only the status and exception class; never log DATABASE_URL or connection details.
    print(f"AI_MANAGER_ANALYTICS_DATABASE={result.get('status')} ERROR_TYPE={result.get('error_type', 'none')}")


@app.get("/health")
async def health():
    database = await asyncio.to_thread(analytics.database_health)
    return {
        "status": "ok",
        "version": APP_VERSION,
        "analytics_database": database,
        "providers": [
            {"id": "tradesoft_parts_catalogs", "type": "oem_parts_catalog", "enabled": TRADESOFT_ENABLED},
        ],
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


def _authorize_admin(credentials: HTTPBasicCredentials | None = None, x_admin_token: str | None = None):
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        valid = bool(credentials and secrets.compare_digest(credentials.username, ADMIN_USERNAME)
                     and secrets.compare_digest(credentials.password, ADMIN_PASSWORD))
    elif ADMIN_API_TOKEN:
        # Backward-compatible fallback: existing token remains valid as X-Admin-Token
        # or as the password for the fixed username "admin".
        valid = bool(
            (x_admin_token and secrets.compare_digest(x_admin_token, ADMIN_API_TOKEN))
            or (credentials and credentials.username == "admin"
                and secrets.compare_digest(credentials.password, ADMIN_API_TOKEN))
        )
    else:
        raise HTTPException(status_code=503, detail="Admin access is not configured.")
    if not valid:
        raise HTTPException(status_code=401, detail="Administrator login required.",
                            headers={"WWW-Authenticate": "Basic"})


@app.get("/api/admin/traces")
async def admin_traces(
    credentials: HTTPBasicCredentials | None = Depends(admin_auth),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _authorize_admin(credentials, x_admin_token)
    return {
        "events": list(TRACE_EVENTS),
        "retained": len(TRACE_EVENTS),
        "retention": "in-memory; cleared on process restart",
    }


@app.post("/api/analytics/events")
async def analytics_event(
    payload: AnalyticsEventRequest,
    x_conversation_id: str | None = Header(default=None, alias="X-Conversation-ID"),
):
    allowed = {"chat_message", "conversation_started", "conversation_ended", "vehicle_confirmed",
               "parts_selection_incomplete", "parts_lookup_failed"}
    if payload.event_type not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported client analytics event type.")
    conversation_id = payload.conversation_id or x_conversation_id
    try:
        await asyncio.to_thread(
            analytics.record_event, payload.event_type,
            conversation_id=conversation_id, metadata=payload.metadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Analytics storage is unavailable.") from exc
    return {"status": "recorded"}


@app.get("/api/admin/analytics")
async def admin_analytics(
    days: int = 30,
    credentials: HTTPBasicCredentials | None = Depends(admin_auth),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _authorize_admin(credentials, x_admin_token)
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="days must be 7, 30 or 90")
    try:
        return await asyncio.to_thread(analytics.dashboard_summary, days)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Analytics database is unavailable or not configured.") from exc


@app.get("/api/admin/conversations")
async def admin_conversations(
    days: int = 30,
    credentials: HTTPBasicCredentials | None = Depends(admin_auth),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _authorize_admin(credentials, x_admin_token)
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="days must be 7, 30 or 90")
    try:
        rows = await asyncio.to_thread(analytics.conversation_summary, days)
        return {"conversations": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Analytics database is unavailable or not configured.") from exc


@app.get("/api/catalog/v1/providers")
async def providers():
    return {
        "limit": 1,
        "configured": int(TRADESOFT_ENABLED),
        "primary_provider": "tradesoft_parts_catalogs" if TRADESOFT_ENABLED else None,
        "providers": [
            {"id": "tradesoft_parts_catalogs", "name": "TradeSoft OEM Parts.Catalogs",
             "kind": "oem_parts_catalog", "enabled": TRADESOFT_ENABLED,
             "capabilities": ["vin_decode", "frame_decode", "vehicle_catalogue", "group_navigation", "schemas", "oem_parts", "diagram_callouts"],
             "authentication": "Server-side API key"},
        ],
    }


def _first_vehicle_text(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def _vehicle_attribute_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = re.sub(r"[^a-z0-9а-я]+", "", value.strip().lower())
    aliases = {
        "brand": "make", "make": "make", "manufacturer": "make", "manufacturername": "make",
        "производитель": "make", "марка": "make", "виробник": "make",
        "model": "model", "modelname": "model", "title": "model", "модель": "model",
        "type": "type", "vehicletype": "type", "modification": "type", "тип": "type",
        "year": "modelYear", "modelyear": "modelYear", "productionyear": "modelYear",
        "manufactured": "modelYear", "годвыпуска": "modelYear", "годпроизводства": "modelYear",
        "ріквиробництва": "modelYear", "ріквипуску": "modelYear",
        "productiondate": "productionDate", "date": "productionDate", "датапроизводства": "productionDate",
        "дата виробництва": "productionDate",
        "engine": "engine", "engineinfo": "engineInfo", "enginedescription": "engineInfo",
        "двигатель": "engineInfo", "двигун": "engineInfo",
        "enginetype": "engineType", "motortype": "engineType", "типдвигателя": "engineType",
        "типдвигуна": "engineType",
        "enginecode": "engineCode", "коддвигателя": "engineCode", "коддвигуна": "engineCode",
        "enginedisplacement": "engineDisplacement", "displacement": "engineDisplacement",
        "capacity": "engineDisplacement", "объемдвигателя": "engineDisplacement",
        "обємдвигуна": "engineDisplacement",
        "power": "power", "enginepower": "power", "horsepower": "power", "мощностьдвигателя": "power",
        "потужністьдвигуна": "power",
        "fuel": "fuelType", "fueltype": "fuelType", "типтоплива": "fuelType", "топливо": "fuelType",
        "типпалива": "fuelType", "паливо": "fuelType",
        "cylindersvalves": "cylindersValves", "cylinders": "cylinders", "valves": "valves",
        "цилиндрыклапаны": "cylindersValves", "цилиндры": "cylinders", "клапаны": "valves",
        "циліндриклапани": "cylindersValves", "циліндри": "cylinders", "клапани": "valves",
        "body": "body", "bodytype": "bodyType", "кузов": "body", "типкузова": "bodyType",
        "fuelSystem": "fuelSystem", "fuelsystem": "fuelSystem", "injectiontype": "fuelSystem",
        "топливнаясистема": "fuelSystem", "паливнасистема": "fuelSystem",
        "drivetype": "driveType", "drivetrain": "driveType", "типпривода": "driveType",
        "типприводу": "driveType",
        "transmission": "transmission", "gearbox": "transmission", "трансмиссия": "transmission",
        "трансмісія": "transmission", "коробка передач": "transmission",
        "region": "region", "регион": "region", "регіон": "region",
        "market": "market", "рынок": "market", "ринок": "market",
        "tecdoc": "tecdocId", "tecdocid": "tecdocId", "идентификаторtecdoc": "tecdocId",
        "идентифікаторtecdoc": "tecdocId",
        "productionrange": "productionRange", "prodrange": "productionRange",
        "периодпроизводства": "productionRange",
    }
    return aliases.get(key)


def _parameter_pairs(value: Any):
    """Yield label/value pairs from TradeSoft parameter arrays and nested objects."""
    if isinstance(value, list):
        for item in value:
            yield from _parameter_pairs(item)
    elif isinstance(value, dict):
        label = next((value.get(k) for k in
                      ("name", "title", "label", "parameterName", "parameter_name", "key")
                      if isinstance(value.get(k), str) and value.get(k).strip()), None)
        field_value = next((value.get(k) for k in
                            ("value", "valueName", "value_name", "displayValue", "display_value",
                             "valueText", "value_text", "text")
                            if value.get(k) not in (None, "")), None)
        if label is not None and field_value is not None and not isinstance(field_value, (dict, list)):
            yield label, str(field_value).strip()
        for key in ("parameters", "items", "values", "attributes", "data"):
            if key in value and isinstance(value[key], (dict, list)):
                yield from _parameter_pairs(value[key])


def _normalize_tradesoft_vehicle(record: dict[str, Any]) -> dict[str, Any]:
    """Preserve TradeSoft identity and expose detailed CarInfo/Car2 parameters."""
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

    attributes: dict[str, str] = {}
    # Normalize direct provider properties, including nested Car2 fields.
    def walk(obj: Any):
        if isinstance(obj, dict):
            for key, value in obj.items():
                canonical = _vehicle_attribute_key(key)
                if canonical and not isinstance(value, (dict, list)) and value not in (None, ""):
                    attributes.setdefault(canonical, str(value).strip())
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(record)
    for label, value in _parameter_pairs(record.get("parameters", [])):
        canonical = _vehicle_attribute_key(label)
        if canonical and value:
            attributes.setdefault(canonical, value)

    if attributes:
        normalized["vehicle_attributes"] = attributes
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


async def _catalog_event(provider: str, route: str, mode: str, status_code: int,
                        duration_ms: float, conversation_id: str | None = None):
    try:
        await asyncio.to_thread(
            analytics.record_event, "catalog_request", conversation_id=conversation_id,
            route=route, method="POST", status_code=status_code, duration_ms=duration_ms,
            metadata={"provider": provider, "mode": mode},
        )
    except Exception:
        pass


@app.post("/api/catalog/v1/vehicles/decode")
async def decode_vehicle(payload: DecodeRequest, request: Request):
    vin = payload.vin.strip().upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        raise HTTPException(status_code=422, detail="VIN must contain 17 valid characters.")

    started = asyncio.get_running_loop().time()
    try:
        adapter = _require_tradesoft()
        rows = await adapter.decode(vin, "vin", payload.lang)
        elapsed = (asyncio.get_running_loop().time() - started) * 1000
        if len(rows) != 1:
            await _catalog_event("tradesoft_parts_catalogs", "/api/catalog/v1/vehicles/decode", "vin_decode", 200, elapsed, request.headers.get("X-Conversation-ID"))
            return {
                "vin": vin, "status": "ambiguous", "vehicle": None,
                "vehicle_data_complete": False, "vehicle_missing_fields": ["vehicle_variant"],
                "providers": [{"provider": "tradesoft_parts_catalogs", "status": "ambiguous", "elapsed_ms": elapsed}],
                "is_oem_catalog_verified": False, "source": "tradesoft_parts_catalogs",
            }
        vehicle = _normalize_tradesoft_vehicle(rows[0])
        if vehicle.get("catalogId") is None or vehicle.get("carId") is None:
            await _catalog_event("tradesoft_parts_catalogs", "/api/catalog/v1/vehicles/decode", "vin_decode", 502, elapsed, request.headers.get("X-Conversation-ID"))
            raise HTTPException(status_code=502, detail="TradeSoft VIN response has no OEM catalogue identity.")
        await _catalog_event("tradesoft_parts_catalogs", "/api/catalog/v1/vehicles/decode", "vin_decode", 200, elapsed, request.headers.get("X-Conversation-ID"))
        completeness = _vehicle_completeness(vehicle)
        trace("VIN decode", "tradesoft_parts_catalogs", "success", "TradeSoft OEM catalogue VIN lookup completed", {
            "catalog_verified": True,
            "vehicle_data_complete": completeness["details_complete"],
        })
        return {
            "vin": vin, "status": "success", "vehicle": vehicle,
            "vehicle_identity_complete": completeness["identity_complete"],
            "vehicle_data_complete": completeness["details_complete"],
            "vehicle_missing_fields": completeness["missing_fields"],
            "providers": [{"provider": "tradesoft_parts_catalogs", "status": "success", "elapsed_ms": elapsed}],
            "is_oem_catalog_verified": True, "source": "tradesoft_parts_catalogs",
        }
    except HTTPException:
        raise
    except Exception as exc:
        elapsed = (asyncio.get_running_loop().time() - started) * 1000
        status = getattr(exc, "status_code", None) or (503 if getattr(exc, "code", "") == "not_configured" else 502)
        await _catalog_event("tradesoft_parts_catalogs", "/api/catalog/v1/vehicles/decode", "vin_decode", status, elapsed, request.headers.get("X-Conversation-ID"))
        trace("VIN decode", "tradesoft_parts_catalogs", "error", str(exc)[:240])
        raise HTTPException(status_code=status, detail={
            "provider": "tradesoft_parts_catalogs",
            "status": getattr(exc, "code", "unavailable"),
            "message": str(exc)[:240],
        }) from exc


@app.post("/api/catalog/v1/lookup")
async def catalogue_lookup(payload: LookupRequest, request: Request):
    if payload.mode != "models" and not payload.vin:
        raise HTTPException(status_code=422, detail="A VIN is required for OEM catalogue lookup.")
    if payload.mode == "parts" and not payload.q and not payload.group_id:
        raise HTTPException(status_code=422, detail="A part name or selected group_id is required.")
    vin = payload.vin.strip().upper() if payload.vin else None
    if vin and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        raise HTTPException(status_code=422, detail="VIN must contain 17 valid characters.")

    started = asyncio.get_running_loop().time()
    try:
        adapter = _require_tradesoft()
        result = await adapter.lookup(vin or "", payload.mode, payload.q, payload.lang, payload.group_id)
        elapsed = (asyncio.get_running_loop().time() - started) * 1000
        status = "ambiguous" if isinstance(result, dict) and result.get("status") == "ambiguous" else "success"
        await _catalog_event("tradesoft_parts_catalogs", "/api/catalog/v1/lookup", payload.mode, 200, elapsed, request.headers.get("X-Conversation-ID"))
        trace("OEM catalogue lookup", "tradesoft_parts_catalogs", status, "TradeSoft OEM catalogue lookup completed", {
            "mode": payload.mode, "catalog_verified": True,
        })
        catalog_result = {
            "provider": "tradesoft_parts_catalogs",
            "status": status,
            "result": result,
            "elapsed_ms": elapsed,
        }
        return {
            "status": status, "mode": payload.mode, "vin": vin,
            "source": "tradesoft_parts_catalogs", "result": result,
            "catalog_results": [catalog_result],
            "providers": [{"provider": "tradesoft_parts_catalogs", "status": status, "elapsed_ms": elapsed}],
            "is_demo_data": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        elapsed = (asyncio.get_running_loop().time() - started) * 1000
        status_code = getattr(exc, "status_code", None) or (503 if getattr(exc, "code", "") == "not_configured" else 502)
        await _catalog_event("tradesoft_parts_catalogs", "/api/catalog/v1/lookup", payload.mode, status_code, elapsed, request.headers.get("X-Conversation-ID"))
        trace("OEM catalogue lookup", "tradesoft_parts_catalogs", "error", str(exc)[:240], {"mode": payload.mode})
        raise HTTPException(status_code=status_code, detail={
            "provider": "tradesoft_parts_catalogs",
            "status": getattr(exc, "code", "unavailable"),
            "message": str(exc)[:240],
        }) from exc
