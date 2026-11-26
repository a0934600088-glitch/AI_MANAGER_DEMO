import asyncio
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from app import main


class VehicleContractTests(unittest.TestCase):
    def test_tradesoft_title_and_brand_are_normalized(self):
        vehicle = main._normalize_tradesoft_vehicle({
            "brand": "VOLKSWAGEN",
            "title": "Golf/Variant/4Motion",
            "catalogId": 12,
            "carId": 34,
        })
        self.assertEqual(vehicle["brand"], "VOLKSWAGEN")
        self.assertEqual(vehicle["model"], "Golf/Variant/4Motion")
        self.assertEqual(vehicle["catalogId"], 12)
        self.assertEqual(vehicle["carId"], 34)

    def test_identity_alone_is_not_marked_as_complete_vehicle_data(self):
        result = main._vehicle_completeness({
            "brand": "VOLKSWAGEN",
            "model": "Golf",
        })
        self.assertTrue(result["identity_complete"])
        self.assertFalse(result["details_complete"])
        self.assertEqual(result["missing_fields"], ["production_year", "engine"])

    def test_nested_year_and_engine_fields_complete_vehicle_data(self):
        result = main._vehicle_completeness({
            "brand": "VOLKSWAGEN",
            "model": "Golf",
            "parameters": {
                "productionYear": 2018,
                "engineInfo": "1600CC / 115hp / 85kW TDI CR",
            },
        })
        self.assertTrue(result["identity_complete"])
        self.assertTrue(result["details_complete"])
        self.assertEqual(result["missing_fields"], [])

    def test_trace_masks_vin_in_keys_and_free_text(self):
        vin = "WF0UXXGAJUAP34719"
        main.TRACE_EVENTS.clear()
        main.trace(
            "VIN decode",
            "tradesoft_parts_catalogs",
            "success",
            f"Lookup completed for {vin}",
            {"vin": vin, "note": f"VIN was {vin}"},
        )
        event = main.TRACE_EVENTS[0]
        serialized = repr(event)
        self.assertNotIn(vin, serialized)
        self.assertIn("*************4719", serialized)

    def test_cors_configuration_never_uses_wildcard(self):
        cors = next(
            middleware for middleware in main.app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        )
        self.assertNotIn("*", cors.kwargs["allow_origins"])

    def test_cors_allows_admin_trace_header(self):
        cors = next(
            middleware for middleware in main.app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        )
        allowed_headers = [header.lower() for header in cors.kwargs["allow_headers"]]
        self.assertIn("x-admin-token", allowed_headers)

    def test_catalogue_lookup_preserves_ambiguous_provider_status(self):
        class AmbiguousAdapter:
            async def lookup(self, *args, **kwargs):
                return {"status": "ambiguous", "candidates": [{"catalogId": 1}, {"catalogId": 2}]}

        previous = main.TRADESOFT_ADAPTER
        try:
            main.TRADESOFT_ADAPTER = AmbiguousAdapter()
            request = Request({
                "type": "http", "method": "POST", "scheme": "https", "path": "/",
                "raw_path": b"/", "query_string": b"", "headers": [],
                "server": ("localhost", 443), "client": ("127.0.0.1", 1234), "root_path": "",
            })
            result = asyncio.run(main.catalogue_lookup(
                main.LookupRequest(vin="WF0UXXGAJUAP34719", mode="groups"), request
            ))
            self.assertEqual(result["status"], "ambiguous")
            self.assertEqual(result["result"]["status"], "ambiguous")
        finally:
            main.TRADESOFT_ADAPTER = previous

    def test_admin_trace_endpoint_requires_configured_token(self):
        previous = main.ADMIN_API_TOKEN
        try:
            main.ADMIN_API_TOKEN = "unit-test-value"
            with self.assertRaises(HTTPException) as missing:
                asyncio.run(main.admin_traces(None, None))
            self.assertEqual(missing.exception.status_code, 401)

            result = asyncio.run(main.admin_traces(None, "unit-test-value"))
            self.assertIn("events", result)
        finally:
            main.ADMIN_API_TOKEN = previous


if __name__ == "__main__":
    unittest.main()
