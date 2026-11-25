"""Public NHTSA vPIC VIN decoder; not an OEM parts catalogue."""
from __future__ import annotations

from typing import Any
import httpx


class NHTSAVPICAdapter:
    BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"

    def __init__(self, timeout_seconds: float = 25.0):
        self.timeout = timeout_seconds

    async def decode(self, vin: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/DecodeVinValuesExtended/{vin}",
                    params={"format": "json"},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            raise RuntimeError("NHTSA vPIC request timed out.") from None
        except (httpx.RequestError, ValueError):
            raise RuntimeError("NHTSA vPIC is unavailable or returned invalid data.") from None
        rows = payload.get("Results", []) if isinstance(payload, dict) else []
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        return {
            key: value for key, value in row.items()
            if value not in (None, "", "0", "Not Applicable")
        }
