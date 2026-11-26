import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

from app import main
from app.providers import solocatalog_mcp as solo_provider
from app.providers import nhtsa_vpic as nhtsa_provider


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None, text=None):
        self.status_code = status
        self.headers = headers or {"content-type": "application/json"}
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class FakeMCPClient:
    def __init__(self, **kwargs):
        self.calls = []
        self.responses = [
            FakeResponse({"result": {"protocolVersion": "2025-03-26"}}, headers={"content-type": "application/json", "Mcp-Session-Id": "session-1"}),
            FakeResponse({}, status=202, headers={"content-type": "application/json"}, text=""),
            FakeResponse({"result": {"tools": [{
                "name": "decode_vin",
                "inputSchema": {"type": "object", "properties": {"vin": {}, "lang": {}}, "required": ["vin"]},
            }]}}, headers={"content-type": "application/json"}),
            FakeResponse({"result": {"content": [{"type": "text", "text": '{"brand":"VOLKSWAGEN","model":"Golf","catalogue":"VW"}'}]}}, headers={"content-type": "application/json"}),
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json})
        return self.responses.pop(0)


class FakeNHTSAClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        return FakeResponse({"Results": [{
            "Make": "VOLKSWAGEN", "Model": "Golf", "ModelYear": "2018",
            "EngineModel": "DDYA", "FuelTypePrimary": "Diesel",
        }]})

class SoloAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_decode_uses_documented_tool_and_optional_bearer_key(self):
        client = FakeMCPClient()
        with patch.object(solo_provider.httpx, "AsyncClient", return_value=client):
            adapter = solo_provider.SoloCatalogMCPAdapter(
                "https://solocatalog.com/mcp", api_key="test-key"
            )
            result = await adapter.decode("WVWZZZAUZJP594600", "en")
        self.assertEqual(result["provider"], "solocatalog_mcp")
        self.assertEqual(result["data"]["brand"], "VOLKSWAGEN")
        self.assertEqual(client.calls[0]["headers"]["Authorization"], "Bearer test-key")
        call = client.calls[-1]["json"]
        self.assertEqual(call["params"]["name"], "decode_vin")
        self.assertEqual(call["params"]["arguments"], {"vin": "WVWZZZAUZJP594600", "lang": "en"})

    async def test_mcp_rejects_non_https_endpoint(self):
        with self.assertRaises(ValueError):
            solo_provider.SoloCatalogMCPAdapter("http://example.com/mcp")


class NHTSATests(unittest.IsolatedAsyncioTestCase):
    async def test_vpic_returns_vehicle_fields_without_claiming_oem_fitment(self):
        with patch.object(nhtsa_provider.httpx, "AsyncClient", FakeNHTSAClient):
            result = await nhtsa_provider.NHTSAVPICAdapter().decode("WVWZZZAUZJP594600")
        self.assertEqual(result["Make"], "VOLKSWAGEN")
        self.assertEqual(result["ModelYear"], "2018")


def _request():
    return Request({
        "type": "http", "method": "POST", "scheme": "https", "path": "/",
        "raw_path": b"/", "query_string": b"", "headers": [(b"x-conversation-id", b"test-session")],
        "server": ("localhost", 443), "client": ("127.0.0.1", 1234), "root_path": "",
    })


class MultiCatalogRouteTests(unittest.TestCase):
    def setUp(self):
        self.trade = main.TRADESOFT_ADAPTER
        self.solo = main.SOLOCATALOG_ADAPTER
        self.nhtsa = main.NHTSA_ADAPTER

    def tearDown(self):
        main.TRADESOFT_ADAPTER = self.trade
        main.SOLOCATALOG_ADAPTER = self.solo
        main.NHTSA_ADAPTER = self.nhtsa

    def test_vin_decode_runs_both_oem_sources_and_marks_trade_catalog_verified(self):
        trade = type("Trade", (), {"decode": AsyncMock(return_value=[{
            "catalogId": 11, "carId": 22, "criteria": "C1", "brand": "VOLKSWAGEN", "title": "Golf",
        }])})()
        solo = type("Solo", (), {"decode": AsyncMock(return_value={
            "data": {"brand": "VOLKSWAGEN", "model": "Golf", "catalogue": "VW"}
        })})()
        nhtsa = type("NHTSA", (), {"decode": AsyncMock(return_value={"Make": "VOLKSWAGEN", "Model": "Golf"})})()
        main.TRADESOFT_ADAPTER, main.SOLOCATALOG_ADAPTER, main.NHTSA_ADAPTER = trade, solo, nhtsa
        with patch("app.main.analytics.record_event"):
            result = asyncio.run(main.decode_vehicle(main.DecodeRequest(vin="WVWZZZAUZJP594600"), _request()))
        self.assertTrue(result["is_oem_catalog_verified"])
        self.assertEqual(result["source"], "tradesoft_parts_catalogs")
        self.assertEqual({x["provider"] for x in result["providers"]}, {
            "tradesoft_parts_catalogs", "solocatalog_mcp", "nhtsa_vpic"
        })
        solo.decode.assert_awaited_once()
        nhtsa.decode.assert_awaited_once()

    def test_solo_catalog_can_be_used_when_tradesoft_is_unavailable(self):
        trade = type("Trade", (), {"decode": AsyncMock(side_effect=RuntimeError("offline"))})()
        solo = type("Solo", (), {"decode": AsyncMock(return_value={
            "data": {"brand": "VOLKSWAGEN", "model": "Golf", "catalogue": "VW"}
        })})()
        nhtsa = type("NHTSA", (), {"decode": AsyncMock(return_value={})})()
        main.TRADESOFT_ADAPTER, main.SOLOCATALOG_ADAPTER, main.NHTSA_ADAPTER = trade, solo, nhtsa
        with patch("app.main.analytics.record_event"):
            result = asyncio.run(main.decode_vehicle(main.DecodeRequest(vin="WVWZZZAUZJP594600"), _request()))
        self.assertEqual(result["source"], "solocatalog_mcp")
        self.assertTrue(result["is_oem_catalog_verified"])

    def test_incomplete_tradesoft_vehicle_falls_back_to_solo_catalog(self):
        trade = type("Trade", (), {"decode": AsyncMock(return_value=[{
            "brand": "VOLKSWAGEN", "title": "Golf",
        }])})()
        solo = type("Solo", (), {"decode": AsyncMock(return_value={
            "data": {"brand": "VOLKSWAGEN", "model": "Golf", "catalogue": "VW"}
        })})()
        nhtsa = type("NHTSA", (), {"decode": AsyncMock(return_value={})})()
        main.TRADESOFT_ADAPTER, main.SOLOCATALOG_ADAPTER, main.NHTSA_ADAPTER = trade, solo, nhtsa
        with patch("app.main.analytics.record_event"):
            result = asyncio.run(main.decode_vehicle(main.DecodeRequest(vin="WVWZZZAUZJP594600"), _request()))
        self.assertEqual(result["source"], "solocatalog_mcp")
        self.assertTrue(result["is_oem_catalog_verified"])

    def test_nhtsa_only_never_authorizes_oem_parts_search(self):
        trade = type("Trade", (), {"decode": AsyncMock(side_effect=RuntimeError("offline"))})()
        solo = type("Solo", (), {"decode": AsyncMock(side_effect=RuntimeError("offline"))})()
        nhtsa = type("NHTSA", (), {"decode": AsyncMock(return_value={
            "Make": "VOLKSWAGEN", "Model": "Golf", "ModelYear": "2018",
        })})()
        main.TRADESOFT_ADAPTER, main.SOLOCATALOG_ADAPTER, main.NHTSA_ADAPTER = trade, solo, nhtsa
        with patch("app.main.analytics.record_event"):
            result = asyncio.run(main.decode_vehicle(main.DecodeRequest(vin="WVWZZZAUZJP594600"), _request()))
        self.assertEqual(result["status"], "vehicle_only")
        self.assertFalse(result["is_oem_catalog_verified"])
        self.assertEqual(result["source"], "nhtsa_vpic")

    def test_parts_lookup_returns_independent_results_from_both_catalogues(self):
        trade = type("Trade", (), {"lookup": AsyncMock(return_value={"parts": [{"oeNumber": "5Q0407183"}]})})()
        solo = type("Solo", (), {"lookup": AsyncMock(return_value={
            "data": {"parts": [{"oeNumber": "5Q0407183A"}]}
        })})()
        main.TRADESOFT_ADAPTER, main.SOLOCATALOG_ADAPTER = trade, solo
        with patch("app.main.analytics.record_event"):
            result = asyncio.run(main.catalogue_lookup(
                main.LookupRequest(mode="parts", vin="WVWZZZAUZJP594600", q="control arm"),
                _request(),
            ))
        self.assertEqual(len(result["catalog_results"]), 2)
        self.assertEqual(result["source"], "tradesoft_parts_catalogs")
        self.assertEqual(result["result"]["parts"][0]["oeNumber"], "5Q0407183")
        solo.lookup.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
