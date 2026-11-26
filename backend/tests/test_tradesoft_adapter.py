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
            f"{provider.BASE_URL}/catalogs/11/groups2/": {
                "items": [{"groupId": 33, "name": "Front suspension"}]
            },
            f"{provider.BASE_URL}/catalogs/11/schemas": {
                "data": [{"schemaId": 44, "name": "Front axle"}]
            },
            f"{provider.BASE_URL}/catalogs/11/parts2": {
                "data": [{"oeNumber": "5Q0407183", "callout": "7"}]
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
        self.assertEqual(len(self.requests), 1)
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

        self.assertEqual(result["parts"]["data"][0]["oeNumber"], "5Q0407183")
        self.assertEqual(result["parts"]["data"][0]["callout"], "7")
        self.assertEqual(
            self.requests[-1]["params"],
            {"carId": 22, "criteria": "C1", "groupId": 33},
        )

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
