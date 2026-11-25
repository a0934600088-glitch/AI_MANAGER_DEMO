"""TradeSoft OEM Parts.Catalogs VIN adapter. Credentials stay server-side."""
from __future__ import annotations
import asyncio
import re
from typing import Any, Literal
import httpx

BASE_URL = "https://api.parts-catalogs.com/v1"
class TradesoftError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

class TradesoftPartsCatalogsAdapter:
    def __init__(self, token: str, timeout_seconds: float = 25.0, min_interval_seconds: float = 2.5):
        if not token or not token.strip():
            raise ValueError("TradeSoft API token is required")
        if timeout_seconds <= 0 or min_interval_seconds < 2.0:
            raise ValueError("Invalid TradeSoft timeout or request interval")
        self._token = token.strip()
        self._timeout = timeout_seconds
        self._interval = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def decode(self, identifier: str, kind: Literal["vin", "frame"] = "vin") -> list[dict[str, Any]]:
        value = identifier.strip().upper()
        pattern = r"[A-HJ-NPR-Z0-9]{17}" if kind == "vin" else r"[A-Z0-9]{5,40}"
        if not re.fullmatch(pattern, value):
            raise TradesoftError("invalid_identifier", "TradeSoft rejected the vehicle identifier format.")
        async with self._lock:
            delay = self._interval - (asyncio.get_running_loop().time() - self._last_request)
            if self._last_request and delay > 0:
                await asyncio.sleep(delay)
            self._last_request = asyncio.get_running_loop().time()
        path = "/car/info" if kind == "vin" else "/frame"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    BASE_URL + path, params={"q": value},
                    headers={"Authorization": self._token, "Accept": "application/json"},
                )
        except httpx.TimeoutException:
            raise TradesoftError("timeout", "TradeSoft request timed out.") from None
        except httpx.RequestError:
            raise TradesoftError("unavailable", "TradeSoft is currently unavailable.") from None
        if response.status_code in (401, 403):
            raise TradesoftError("authorization_error", "TradeSoft rejected the configured credentials.")
        if response.status_code == 429:
            raise TradesoftError("rate_limited", "TradeSoft rate limit was reached.")
        if response.status_code >= 500:
            raise TradesoftError("unavailable", "TradeSoft is currently unavailable.")
        if response.status_code >= 400:
            raise TradesoftError("upstream_error", "TradeSoft could not process the request.")
        try:
            payload = response.json()
        except ValueError:
            raise TradesoftError("invalid_response", "TradeSoft returned invalid JSON.") from None
        if not isinstance(payload, list):
            raise TradesoftError("invalid_response", "TradeSoft returned an unsupported response format.")
        candidates = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            item = {"identifier": value, "identifier_type": kind}
            item["vin" if kind == "vin" else "frame"] = value
            for source, target in (("brand", "make"), ("modelName", "model"), ("title", "title"), ("description", "description"), ("criteria", "criteria")):
                field = row.get(source)
                if isinstance(field, (str, int, float)) and str(field).strip():
                    item[target] = str(field).strip()
            if "model" not in item and item.get("title"):
                item["model"] = item["title"]
            params = row.get("parameters")
            item["parameters"] = [
                {"name": str(p.get("name") or p.get("key")), "value": str(p.get("value"))}
                for p in params if isinstance(p, dict) and (p.get("name") or p.get("key")) and p.get("value") is not None
            ] if isinstance(params, list) else []
            if any(item.get(k) for k in ("make", "model", "title", "description")) or item["parameters"]:
                candidates.append(item)
        if payload and not candidates:
            raise TradesoftError("invalid_response", "TradeSoft response contained no recognizable vehicle fields.")
        return candidates
