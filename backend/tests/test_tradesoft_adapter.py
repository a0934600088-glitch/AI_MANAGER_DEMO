import unittest
from unittest.mock import patch

from app.providers import tradesoft_parts_catalogs as provider


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, requests, payloads):
        self.requests = requests
        self.payloads = payloads

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None, headers=None):
        self.requests.append({
            "url": url,
            "params": params or {},
            "headers": headers or {},
        })
        payload = self.payloads.get(url)
        if payload is None:
            raise AssertionError(f"Unexpected TradeSoft URL: {url}")
        if callable(payload):
            payload = payload(params or {})
        return FakeResponse(payload)


class TradesoftAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.payloads = {
            f"{provider.BASE_URL}/car/info": {
                "data": [{
                    "catalogId": 11,
                    "carId": 22,
                    "criteria": "C1",
                    "brand": "VOLKSWAGEN",
                    "title": "Golf",
                }]
            },
            f"{provider.BASE_URL}/catalogs/11/cars2/22": {
                "name": "Golf 1.6 TDI",
                "brand": "VOLKSWAGEN",
                "parameters": [
                    {"name": "Production year", "value": "2018"},
                    {"name": "Engine code", "value": "DDYA"},
                    {"name": "Engine displacement", "value": "1598 cc"},
                    {"name": "Fuel type", "value": "Diesel"},
                ],
            },
            f"{provider.BASE_URL}/catalogs/11/groups2/": {
                "items": [{"groupId": 33, "name": "Front suspension"}]
            },
            f"{provider.BASE_URL}/catalogs/11/groups-suggest": [
                {"sid": "87", "name": "Brake pads"},
                {"sid": "88", "name": "Brake lining"}
            ],
            f"{provider.BASE_URL}/catalogs/11/schemas": {
                "group": {"id": 1, "name": "Brake system"},
                "list": [{"groupId": 44, "name": "Front brake pads"}]
            },
            f"{provider.BASE_URL}/catalogs/11/parts2": {
                "img": "//img.parts-catalogs.com/test/diagram.png",
                "partGroups": [{"parts": [{"oeNumber": "5Q0407183", "callout": "7"}]}],
                "positions": [{"number": "7", "x": 0.5, "y": 0.5}],
            },
        }
        self.adapter = provider.TradesoftPartsCatalogsAdapter("unit-test-api-key")

    def _client_factory(self, **kwargs):
        return FakeAsyncClient(self.requests, self.payloads)

    async def test_decode_preserves_catalog_identity_and_uses_raw_auth_header(self):
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.decode("WVWZZZAUZJP594600", "vin", "ru")
            cached = await self.adapter.decode("WVWZZZAUZJP594600", "vin", "ru")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["catalogId"], 11)
        self.assertEqual(result[0]["carId"], 22)
        self.assertEqual(result[0]["criteria"], "C1")
        self.assertEqual(result[0]["vin"], "WVWZZZAUZJP594600")
        self.assertEqual(cached, result)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[1]["url"], f"{provider.BASE_URL}/catalogs/11/cars2/22")
        self.assertEqual(self.requests[1]["params"], {"criteria": "C1"})
        self.assertEqual(result[0]["vehicle_details_status"], "success")
        self.assertEqual(result[0]["parameters"][0]["value"], "2018")
        self.assertEqual(self.requests[0]["headers"]["Authorization"], "unit-test-api-key")
        self.assertEqual(self.requests[0]["headers"]["Accept-Language"], "ru")

    async def test_groups_lookup_uses_vehicle_catalog_and_criteria(self):
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup("WVWZZZAUZJP594600", mode="groups", lang="ru")

        self.assertIn("groups", result)
        request = self.requests[-1]
        self.assertEqual(request["url"], f"{provider.BASE_URL}/catalogs/11/groups2/")
        self.assertEqual(request["params"], {"carId": 22, "criteria": "C1"})

    async def test_diagrams_lookup_uses_vehicle_catalog(self):
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup("WVWZZZAUZJP594600", mode="diagrams")

        self.assertIn("schemas", result)
        self.assertEqual(self.requests[-1]["url"], f"{provider.BASE_URL}/catalogs/11/schemas")

    async def test_selected_group_parts_lookup_returns_oe_callouts(self):
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                group_id=33,
            )

        self.assertEqual(result["parts"]["partGroups"][0]["parts"][0]["oeNumber"], "5Q0407183")
        self.assertEqual(result["parts"]["partGroups"][0]["parts"][0]["callout"], "7")
        self.assertEqual(result["resolvedGroupId"], 33)
        self.assertEqual(
            self.requests[-1]["params"],
            {"carId": 22, "criteria": "C1", "groupId": 33},
        )


    async def test_part_name_search_uses_suggest_then_schemas_with_sid(self):
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                query="Brake pads",
                lang="en",
            )

        self.assertEqual(result["suggestions"], [
            {"sid": "87", "name": "Brake pads"},
            {"sid": "88", "name": "Brake lining"},
        ])
        self.assertEqual(result["schemas"]["list"][0]["groupId"], 44)
        self.assertEqual(
            [request["url"] for request in self.requests[2:]],
            [
                f"{provider.BASE_URL}/catalogs/11/groups-suggest",
                f"{provider.BASE_URL}/catalogs/11/schemas",
            ],
        )
        self.assertEqual(self.requests[2]["params"], {"q": "Brake pads"})
        self.assertEqual(self.requests[3]["params"], {
            "carId": 22,
            "partName": "Brake pads",
            "partNameIds": "87,88",
        })

    async def test_part_name_search_without_suggestions_falls_back_to_part_name(self):
        self.payloads[f"{provider.BASE_URL}/catalogs/11/groups-suggest"] = []
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                query="Front shock absorbers",
                lang="en",
            )

        self.assertEqual(result["suggestions"], [])
        self.assertEqual(self.requests[-1]["params"], {
            "carId": 22,
            "partName": "Front shock absorbers",
        })

    async def test_pipe_delimited_part_terms_are_searched_independently(self):
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                query="Brake pads | Brake lining",
                lang="en",
            )

        suggest_requests = [
            request for request in self.requests
            if request["url"].endswith("/groups-suggest")
        ]
        schema_requests = [
            request for request in self.requests
            if request["url"].endswith("/schemas")
        ]
        self.assertEqual([r["params"]["q"] for r in suggest_requests], ["Brake pads", "Brake lining"])
        self.assertEqual([r["params"]["partName"] for r in schema_requests], ["Brake pads", "Brake lining"])
        self.assertEqual(len(result["schemas"]["list"]), 1)

    async def test_schema_group_id_is_mapped_to_matching_groups2_leaf_image(self):
        schema_image = "//img.parts-catalogs.com/test/brake.png"
        self.payloads[f"{provider.BASE_URL}/catalogs/11/schemas"] = {
            "group": {"id": 1, "name": "Brake system"},
            "list": [{
                "groupId": "opaque-schema-id",
                "img": schema_image,
                "name": "Front brake diagram",
                "partNames": [{"id": "289", "name": "Brake pads"}],
            }],
        }
        self.payloads[f"{provider.BASE_URL}/catalogs/11/groups2/"] = lambda params: (
            {"items": [{"groupId": "general-root", "name": "General components", "hasParts": False}]}
            if "groupId" not in params else
            {"items": [{"groupId": "brake-leaf", "name": "Front brake pads", "hasParts": False,
                        "hasSubgroups": False, "img": schema_image}]}
        )
        def parts_response(params):
            if params.get("groupId") == "opaque-schema-id":
                return {"img": schema_image, "partGroups": [], "positions": []}
            return {
                "img": schema_image,
                "partGroups": [{"parts": [{"oeNumber": "5Q0698151", "name": "Brake pad"}]}],
                "positions": [{"number": "3", "x": 0.5, "y": 0.5}],
            }
        self.payloads[f"{provider.BASE_URL}/catalogs/11/parts2"] = parts_response

        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                query="тормозные колодки | brake pads",
                lang="ru",
                group_id="opaque-schema-id",
            )

        self.assertEqual(result["resolvedGroupId"], "brake-leaf")
        self.assertEqual(
            result["parts"]["partGroups"][0]["parts"][0]["oeNumber"],
            "5Q0698151",
        )
        self.assertEqual(
            self.requests[-1]["params"],
            {"carId": 22, "criteria": "C1", "groupId": "brake-leaf"},
        )

    async def test_complete_parts2_payload_with_wrong_diagram_is_remapped_to_schema_image(self):
        schema_image = "//img.parts-catalogs.com/test/brake.png"
        wrong_image = "//img.parts-catalogs.com/test/other-brake.png"
        self.payloads[f"{provider.BASE_URL}/catalogs/11/schemas"] = {
            "list": [{
                "groupId": "opaque-schema-id",
                "img": schema_image,
                "name": "Front brake diagram",
                "partNames": [{"id": "289", "name": "Brake pads"}],
            }]
        }
        self.payloads[f"{provider.BASE_URL}/catalogs/11/groups2/"] = lambda params: (
            {"items": [{"groupId": "brake-root", "name": "Brake system", "hasParts": False, "hasSubgroups": True}]}
            if "groupId" not in params else
            {"items": [{"groupId": "brake-leaf", "name": "Front brake pads", "hasParts": True,
                        "hasSubgroups": False, "img": schema_image}]}
        )
        def parts_response(params):
            if params.get("groupId") == "opaque-schema-id":
                return {
                    "img": wrong_image,
                    "partGroups": [{"parts": [{"oeNumber": "WRONG-IMAGE"}]}],
                    "positions": [{"number": "9", "x": 0.4, "y": 0.4}],
                }
            return {
                "img": schema_image,
                "partGroups": [{"parts": [{"oeNumber": "5Q0698151", "name": "Brake pad"}]}],
                "positions": [{"number": "3", "x": 0.5, "y": 0.5}],
            }
        self.payloads[f"{provider.BASE_URL}/catalogs/11/parts2"] = parts_response

        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                query="тормозные колодки",
                lang="ru",
                group_id="opaque-schema-id",
            )

        self.assertEqual(result["resolvedGroupId"], "brake-leaf")
        self.assertEqual(result["selectedSchema"]["img"], schema_image)
        self.assertEqual(result["parts"]["img"], schema_image)
        self.assertEqual(
            result["parts"]["partGroups"][0]["parts"][0]["oeNumber"],
            "5Q0698151",
        )

    async def test_parts2_mapping_skips_unavailable_group_and_uses_other_exact_image_match(self):
        schema_image = "//img.parts-catalogs.com/test/brake.png"
        self.payloads[f"{provider.BASE_URL}/catalogs/11/schemas"] = {
            "list": [{
                "groupId": "opaque-schema-id",
                "img": schema_image,
                "name": "Front brake diagram",
                "partNames": [{"id": "289", "name": "Brake pads"}],
            }]
        }
        self.payloads[f"{provider.BASE_URL}/catalogs/11/groups2/"] = lambda params: (
            {"items": [{"groupId": "brake-root", "name": "Brake system", "hasSubgroups": True}]}
            if "groupId" not in params else
            {"items": [
                {"groupId": "unavailable-leaf", "name": "Front brake pads", "hasSubgroups": False, "img": schema_image},
                {"groupId": "valid-leaf", "name": "Front brake pads alternate", "hasSubgroups": False, "img": schema_image},
            ]}
        )

        def parts_response(params):
            group_id = params.get("groupId")
            if group_id == "opaque-schema-id":
                return {"img": "//img.parts-catalogs.com/test/wrong.png", "partGroups": [], "positions": []}
            if group_id == "unavailable-leaf":
                raise provider.TradesoftError("not_found", "stale group")
            if group_id == "valid-leaf":
                return {
                    "img": schema_image,
                    "partGroups": [{"parts": [{"oeNumber": "5Q0698151", "name": "Brake pad"}]}],
                    "positions": [{"number": "3", "x": 0.5, "y": 0.5}],
                }
            raise AssertionError(f"Unexpected group id: {group_id}")

        self.payloads[f"{provider.BASE_URL}/catalogs/11/parts2"] = parts_response
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600",
                mode="parts",
                query="тормозные колодки",
                lang="ru",
                group_id="opaque-schema-id",
            )

        self.assertEqual(result["resolvedGroupId"], "valid-leaf")
        self.assertEqual(result["parts"]["img"], schema_image)

    async def test_multi_schema_search_classifies_front_and_rear_from_vin_catalogue_path(self):
        front_image = "//img.parts-catalogs.com/test/front-brake.png"
        rear_image = "//img.parts-catalogs.com/test/rear-brake.png"
        self.payloads[f"{provider.BASE_URL}/catalogs/11/groups-suggest"] = []
        self.payloads[f"{provider.BASE_URL}/catalogs/11/schemas"] = {
            "list": [
                {"groupId": "schema-front", "img": front_image, "name": "Disc brake 3",
                 "partNames": [{"name": "Brake pads"}]},
                {"groupId": "schema-rear", "img": rear_image, "name": "Disc brake 2",
                 "partNames": [{"name": "Brake pads"}]},
                {"groupId": "schema-ambiguous", "img": "//img.parts-catalogs.com/test/other.png",
                 "name": "Disc brake 4"},
            ]
        }
        self.payloads[f"{provider.BASE_URL}/catalogs/11/groups2/"] = lambda params: (
            {"items": [
                {"groupId": "front-root", "name": "Front axle", "hasSubgroups": True},
                {"groupId": "rear-root", "name": "Rear axle", "hasSubgroups": True},
            ]}
            if "groupId" not in params else
            {"items": [
                {"groupId": "front-leaf", "name": "Disc brakes", "img": front_image,
                 "hasSubgroups": False}
            ]}
            if params["groupId"] == "front-root" else
            {"items": [
                {"groupId": "rear-leaf", "name": "Disc brakes", "img": rear_image,
                 "hasSubgroups": False}
            ]}
        )
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup(
                "WVWZZZAUZJP594600", mode="parts", query="Brake pads", lang="en"
            )
            rows = result["schemas"]["list"]
            self.assertEqual([row.get("axle") for row in rows], ["front", "rear", None])
            self.assertEqual(rows[0]["catalogPath"], ["Front axle", "Disc brakes"])
            self.assertEqual(rows[1]["catalogPath"], ["Rear axle", "Disc brakes"])

            # A second part search for the same VIN reuses the indexed hierarchy.
            groups2_before = sum("/groups2/" in request["url"] for request in self.requests)
            await self.adapter.lookup(
                "WVWZZZAUZJP594600", mode="parts", query="Brake discs", lang="en"
            )
            groups2_after = sum("/groups2/" in request["url"] for request in self.requests)
            self.assertEqual(groups2_after, groups2_before)

    async def test_ambiguous_vehicle_is_not_used_for_catalogue_lookup(self):
        self.payloads[f"{provider.BASE_URL}/car/info"] = {
            "data": [
                {"catalogId": 11, "carId": 22},
                {"catalogId": 12, "carId": 23},
            ]
        }
        with patch.object(provider.httpx, "AsyncClient", side_effect=self._client_factory):
            result = await self.adapter.lookup("WVWZZZAUZJP594600", mode="groups")

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(self.requests), 1)


if __name__ == "__main__":
    unittest.main()
