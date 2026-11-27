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
            for key in ("data", "items", "results", "cars", "list", "groups"):
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

        # CarInfo supplies the vehicle identity. TradeSoft documents Car2 as the
        # detailed selected-vehicle record (including its parameter collection).
        # Enrich only an unambiguous result; never guess which variant to expand.
        if len(candidates) == 1:
            vehicle = candidates[0]
            catalog_id = vehicle.get("catalogId")
            car_id = vehicle.get("carId")
            if catalog_id is not None and car_id is not None:
                detail_params: dict[str, Any] = {}
                if vehicle.get("criteria") not in (None, ""):
                    detail_params["criteria"] = vehicle["criteria"]
                try:
                    details = await self._get(
                        f"/catalogs/{catalog_id}/cars2/{car_id}",
                        detail_params,
                        lang,
                    )
                    if isinstance(details, dict) and isinstance(details.get("data"), dict):
                        details = details["data"]
                    elif isinstance(details, dict) and isinstance(details.get("data"), list):
                        detail_rows = [row for row in details["data"] if isinstance(row, dict)]
                        details = detail_rows[0] if len(detail_rows) == 1 else details
                    if isinstance(details, dict):
                        for key, detail_value in details.items():
                            if detail_value in (None, ""):
                                continue
                            if key == "parameters" and isinstance(detail_value, list):
                                original = vehicle.get("parameters")
                                if isinstance(original, list):
                                    vehicle["parameters"] = original + detail_value
                                else:
                                    vehicle["parameters"] = detail_value
                            elif key not in {"catalogId", "carId", "criteria"}:
                                if vehicle.get(key) in (None, "", [], {}):
                                    vehicle[key] = detail_value
                                elif key not in vehicle:
                                    vehicle[key] = detail_value
                        vehicle["vehicle_details_status"] = "success"
                    else:
                        vehicle["vehicle_details_status"] = "empty"
                except TradesoftError as exc:
                    # The base VIN identity remains valid; detailed enrichment is
                    # explicitly marked unavailable and does not fabricate fields.
                    vehicle["vehicle_details_status"] = "unavailable"
                    vehicle["vehicle_details_error"] = exc.code

        async with self._lock:
            self._cache[cache_key] = (time.monotonic() + 86400, candidates)
        return candidates

    @staticmethod
    def _truthy(value: Any) -> bool:
        return value is True or value == 1 or str(value).strip().lower() in {"true", "1", "yes"}

    @staticmethod
    def _schema_group_id(row: dict[str, Any]) -> Any:
        for key in ("groupId", "group_id", "groupID", "id", "Id"):
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _image_key(value: Any) -> str:
        image = str(value or "").strip().split("?", 1)[0]
        if image.startswith("https://"):
            image = image[8:]
        elif image.startswith("http://"):
            image = image[7:]
        elif image.startswith("//"):
            image = image[2:]
        return image.rstrip("/")

    @classmethod
    def _parts_payload_complete(cls, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        groups = payload.get("partGroups") or payload.get("part_groups") or []
        if not isinstance(groups, list):
            return False
        parts = payload.get("parts") if isinstance(payload.get("parts"), list) else []
        if not parts:
            parts = [
                part
                for group in groups if isinstance(group, dict)
                for part in (group.get("parts") or [])
                if isinstance(part, dict)
            ]
        positions = payload.get("positions") or []
        return bool(payload.get("img") and parts and isinstance(positions, list) and positions)

    async def _search_schemas(
        self, catalog_id: Any, car_id: Any, query: str, lang: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        # The browser's terminology engine sends alternatives separated by "|".
        # Search every phrase independently; TradeSoft q is not a multi-term expression.
        terms = list(dict.fromkeys(term.strip() for term in query.split("|") if term.strip()))
        if not terms:
            terms = [query.strip()]

        suggestions_by_id: dict[str, dict[str, Any]] = {}
        schemas_by_id: dict[str, dict[str, Any]] = {}
        first_payload: Any = None
        for term in terms:
            suggestions_payload = await self._get(
                f"/catalogs/{catalog_id}/groups-suggest", {"q": term}, lang
            )
            term_ids: list[str] = []
            for suggestion in self._rows(suggestions_payload):
                sid = suggestion.get("sid", suggestion.get("id"))
                if sid is None or not str(sid).strip():
                    continue
                sid_text = str(sid).strip()
                term_ids.append(sid_text)
                suggestions_by_id.setdefault(sid_text, {
                    "sid": sid_text,
                    "name": str(suggestion.get("name") or suggestion.get("title") or term),
                })

            schema_params: dict[str, Any] = {"carId": car_id, "partName": term}
            if term_ids:
                schema_params["partNameIds"] = ",".join(dict.fromkeys(term_ids))
            schema_payload = await self._get(
                f"/catalogs/{catalog_id}/schemas", schema_params, lang
            )
            if first_payload is None:
                first_payload = schema_payload
            for schema in self._rows(schema_payload):
                schema_id = self._schema_group_id(schema)
                dedupe_key = str(schema_id) if schema_id is not None else (
                    self._image_key(schema.get("img")) + "|" + str(schema.get("name") or "")
                )
                schemas_by_id.setdefault(dedupe_key, schema)

        rows = list(schemas_by_id.values())
        if isinstance(first_payload, dict):
            envelope = dict(first_payload)
            list_key = next(
                (key for key in ("list", "data", "items", "results", "schemas")
                 if isinstance(envelope.get(key), list)),
                "list",
            )
            envelope[list_key] = rows
        else:
            envelope = {"list": rows}
        return list(suggestions_by_id.values()), envelope, rows

    async def _groups_matching_schema_image(
        self,
        catalog_id: Any,
        base_params: dict[str, Any],
        schema_image: Any,
        query: str,
        lang: str,
    ) -> list[dict[str, Any]]:
        image_key = self._image_key(schema_image)
        if not image_key:
            return []
        query_text = query.lower()
        if any(term in query_text for term in ("тормоз", "колод", "диск", "brake", "rotor", "pad", "гальм")):
            category_terms = ("тормоз", "brake")
        elif any(term in query_text for term in ("амортиз", "shock", "strut", "подвес", "suspension", "сайлент", "bushing", "рычаг", "control arm")):
            category_terms = ("подвес", "suspension", "chassis")
        else:
            category_terms = ()

        root_payload = await self._get(
            f"/catalogs/{catalog_id}/groups2/", dict(base_params), lang
        )
        roots = self._rows(root_payload)
        selected_roots = [
            root for root in roots
            if not category_terms or any(term in str(root.get("name") or "").lower() for term in category_terms)
        ]
        if not selected_roots:
            selected_roots = roots

        matches: list[dict[str, Any]] = []
        visited: set[str] = set()
        visited_count = 0

        async def walk(group: dict[str, Any], depth: int = 0) -> None:
            nonlocal visited_count
            if depth > 8 or visited_count >= 500:
                return
            group_id_value = self._schema_group_id(group)
            if group_id_value is None:
                return
            key = str(group_id_value)
            if key in visited:
                return
            visited.add(key)
            visited_count += 1

            has_parts = self._truthy(group.get("hasParts", group.get("has_parts")))
            has_subgroups = self._truthy(group.get("hasSubgroups", group.get("has_subgroups")))
            if has_parts and self._image_key(group.get("img")) == image_key:
                matches.append(group)
            if not has_subgroups:
                return
            child_params = dict(base_params)
            child_params["groupId"] = group_id_value
            children = await self._get(
                f"/catalogs/{catalog_id}/groups2/", child_params, lang
            )
            for child in self._rows(children):
                await walk(child, depth + 1)

        for root in selected_roots:
            await walk(root)
        return matches

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
            resolved_group_id = group_id
            selected_schema = None
            if not self._parts_payload_complete(parts) and query and query.strip():
                suggestions, schemas_payload, schema_rows = await self._search_schemas(
                    catalog_id, car_id, query, lang
                )
                selected_schema = next(
                    (row for row in schema_rows if str(self._schema_group_id(row)) == str(group_id)),
                    None,
                )
                if selected_schema and selected_schema.get("img"):
                    matching_groups = await self._groups_matching_schema_image(
                        catalog_id, base_params, selected_schema.get("img"), query, lang
                    )
                    for group in matching_groups:
                        candidate_id = self._schema_group_id(group)
                        if candidate_id is None:
                            continue
                        candidate_params = dict(base_params)
                        candidate_params["groupId"] = candidate_id
                        candidate_parts = await self._get(
                            f"/catalogs/{catalog_id}/parts2", candidate_params, lang
                        )
                        if self._parts_payload_complete(candidate_parts):
                            parts = candidate_parts
                            resolved_group_id = candidate_id
                            break
            if not self._parts_payload_complete(parts):
                raise TradesoftError(
                    "schema_group_mapping_failed",
                    "TradeSoft returned the original schema image but no matching parts2 group with positions and OE parts. The selection was stopped rather than guessing.",
                )
            return {
                "vehicle": car,
                "catalogId": catalog_id,
                "carId": car_id,
                "criteria": criteria,
                "parts": parts,
                "selectedSchema": selected_schema,
                "resolvedGroupId": resolved_group_id,
            }

        if not query or not query.strip():
            raise TradesoftError("missing_query", "A part name is required for OEM catalogue search.")
        part_query = query.strip()
        suggestions, schemas, schema_rows = await self._search_schemas(
            catalog_id, car_id, part_query, lang
        )
        return {
            "vehicle": car,
            "catalogId": catalog_id,
            "carId": car_id,
            "criteria": criteria,
            "query": part_query,
            "suggestions": suggestions,
            "schemas": schemas,
            "note": "Select the matching original TradeSoft diagram. Its schema image is mapped to the VIN-specific groups2 leaf before parts2 is requested.",
        }
