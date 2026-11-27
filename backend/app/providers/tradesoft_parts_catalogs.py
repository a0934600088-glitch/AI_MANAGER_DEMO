"""TradeSoft OEM Parts.Catalogs API adapter.

Uses the documented REST API. Authorization is the raw API key (no Bearer prefix).
Credentials are only read from server environment variables.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Literal

import httpx

BASE_URL = "https://api.parts-catalogs.com/v1"


class TradesoftError(Exception):
    def __init__(self, code: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class TradesoftPartsCatalogsAdapter:
    """Client for VIN decode, catalogue schemas and OEM part diagrams."""

    def __init__(self, token: str, timeout_seconds: float = 25.0):
        if not token or not token.strip():
            raise ValueError("TradeSoft API token is required")
        if timeout_seconds <= 0:
            raise ValueError("TradeSoft timeout must be positive")
        self._token = token.strip()
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any] | None = None, lang: str = "en") -> Any:
        headers = {
            "Authorization": self._token,
            "Accept": "application/json",
            "Accept-Language": lang if lang in {"en", "ru", "uk"} else "en",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(BASE_URL + path, params=params or {}, headers=headers)
        except httpx.TimeoutException:
            raise TradesoftError("timeout", "TradeSoft API request timed out.") from None
        except httpx.RequestError:
            raise TradesoftError("unavailable", "TradeSoft API is unreachable.") from None

        if response.status_code == 401:
            raise TradesoftError("authorization_error", "TradeSoft rejected the API key (HTTP 401).", 401)
        if response.status_code == 403:
            raise TradesoftError("access_denied", "TradeSoft denied access to this catalogue (HTTP 403).", 403)
        if response.status_code == 404:
            raise TradesoftError("not_found", "TradeSoft found no matching catalogue data (HTTP 404).", 404)
        if response.status_code == 429:
            raise TradesoftError("rate_limited", "TradeSoft API rate limit reached (HTTP 429).", 429)
        if response.status_code >= 500:
            raise TradesoftError("unavailable", f"TradeSoft API server error (HTTP {response.status_code}).", response.status_code)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            detail_text = str(detail)[:350]
            detail_text = re.sub(r"[A-HJ-NPR-Z0-9]{17}", lambda match: "*" * 13 + match.group(0)[-4:], detail_text, flags=re.IGNORECASE)
            request_id = response.headers.get("x-request-id") or response.headers.get("X-Request-ID")
            suffix = f" Request ID: {request_id}." if request_id else ""
            raise TradesoftError(
                "upstream_error",
                f"TradeSoft API rejected the request (HTTP {response.status_code}): {detail_text}.{suffix}",
                response.status_code,
            )
        try:
            return response.json()
        except ValueError:
            raise TradesoftError("invalid_response", "TradeSoft returned a non-JSON response.", response.status_code) from None

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "results", "cars", "list"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            if any(key in payload for key in ("catalogId", "carId", "title", "brand")):
                return [payload]
        return []

    async def decode(self, identifier: str, kind: Literal["vin", "frame"] = "vin", lang: str = "en") -> list[dict[str, Any]]:
        value = identifier.strip().upper()
        pattern = r"[A-HJ-NPR-Z0-9]{17}" if kind == "vin" else r"[A-Z0-9]{5,40}"
        if not re.fullmatch(pattern, value):
            raise TradesoftError("invalid_identifier", "Vehicle identifier format is invalid.")

        cache_key = f"{kind}:{value}"
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                return cached[1]

        payload = await self._get("/car/info", {"q": value}, lang)
        rows = self._rows(payload)
        if not rows:
            raise TradesoftError("not_found", "TradeSoft returned no vehicle match.")

        candidates: list[dict[str, Any]] = []
        for row in rows:
            # Keep the provider's original fields and identifiers intact: catalogId,
            # carId and criteria are required by every subsequent catalogue call.
            item = dict(row)
            item["provider"] = "tradesoft_parts_catalogs"
            item["identifier"] = value
            item["identifier_type"] = kind
            if kind == "vin":
                item["vin"] = value
            else:
                item["frame"] = value
            candidates.append(item)

        async with self._lock:
            self._cache[cache_key] = (time.monotonic() + 86400, candidates)
        return candidates

    async def lookup(
        self,
        identifier: str,
        mode: Literal["parts", "diagrams", "diagram", "groups", "models"] = "parts",
        query: str | None = None,
        lang: str = "en",
        group_id: str | int | None = None,
    ) -> dict[str, Any]:
        candidates = await self.decode(identifier, "vin", lang)
        if len(candidates) != 1:
            return {"status": "ambiguous", "candidates": candidates}
        car = candidates[0]
        catalog_id = car.get("catalogId")
        car_id = car.get("carId")
        criteria = car.get("criteria")
        if catalog_id is None or car_id is None:
            raise TradesoftError(
                "invalid_vehicle_record",
                "TradeSoft VIN response is missing catalogId or carId; further OEM lookup is unsafe.",
            )

        base_params: dict[str, Any] = {"carId": car_id}
        if criteria not in (None, ""):
            base_params["criteria"] = criteria

        if mode == "models":
            return {"vehicle": car, "catalogue": await self._get("/catalogs/", lang=lang)}

        if mode == "groups":
            params = dict(base_params)
            if group_id is not None:
                params["groupId"] = group_id
            groups = await self._get(f"/catalogs/{catalog_id}/groups2/", params, lang)
            return {"vehicle": car, "catalogId": catalog_id, "carId": car_id, "criteria": criteria, "groups": groups}

        if mode == "diagrams" or mode == "diagram":
            schemas = await self._get(f"/catalogs/{catalog_id}/schemas", base_params, lang)
            return {
                "vehicle": car,
                "catalogId": catalog_id,
                "carId": car_id,
                "criteria": criteria,
                "schemas": schemas,
            }

        if group_id is not None:
            params = dict(base_params)
            params["groupId"] = group_id
            parts = await self._get(f"/catalogs/{catalog_id}/parts2", params, lang)
            return {
                "vehicle": car,
                "catalogId": catalog_id,
                "carId": car_id,
                "criteria": criteria,
                "parts": parts,
            }

        if not query or not query.strip():
            raise TradesoftError("missing_query", "A part name is required for OEM catalogue search.")
        # TradeSoft's documented name-search flow is two requests:
        # groups-suggest(q) -> sid, then schemas(carId, partNameIds, partName).
        # groups-by-sid is deprecated and must not be used.
        part_query = query.strip()
        suggestions_payload = await self._get(
            f"/catalogs/{catalog_id}/groups-suggest",
            {"q": part_query},
            lang,
        )
        suggestions = self._rows(suggestions_payload)

        suggestion_ids: list[str] = []
        normalized_suggestions: list[dict[str, Any]] = []
        for suggestion in suggestions:
            sid = suggestion.get("sid", suggestion.get("id"))
            name = suggestion.get("name") or suggestion.get("title") or part_query
            if sid is None or not str(sid).strip():
                continue
            sid_text = str(sid).strip()
            if sid_text not in suggestion_ids:
                suggestion_ids.append(sid_text)
            normalized_suggestions.append({"sid": sid_text, "name": str(name)})

        schema_params: dict[str, Any] = {"carId": car_id, "partName": part_query}
        if suggestion_ids:
            schema_params["partNameIds"] = ",".join(suggestion_ids)
        schemas = await self._get(f"/catalogs/{catalog_id}/schemas", schema_params, lang)
        return {
            "vehicle": car,
            "catalogId": catalog_id,
            "carId": car_id,
            "criteria": criteria,
            "query": part_query,
            "suggestions": normalized_suggestions,
            "schemas": schemas,
            "note": "Select a returned schema, then call parts2 with its groupId to retrieve OE part numbers and diagram callouts.",
        }
