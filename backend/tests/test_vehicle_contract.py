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

    def test_trade_soft_parameter_rows_are_normalized_for_customer_card(self):
        vehicle = main._normalize_tradesoft_vehicle({
            "brand": "MERCEDES-BENZ",
            "title": "C-CLASS Kyne (C205)",
            "parameters": [
                {"name": "Production year", "value": "09.2016 - 12.2018"},
                {"name": "Engine type", "value": "083"},
                {"name": "Engine displacement", "value": "1991 cc"},
                {"name": "Engine code", "value": "M 274.920"},
                {"name": "Fuel type", "value": "Petrol"},
                {"name": "Cylinders / valves", "value": "4 / 4"},
                {"name": "Body type", "value": "Coupe"},
                {"name": "Fuel system", "value": "Direct injection"},
                {"name": "Drive type", "value": "AWD"},
                {"name": "TecDoc identifier", "value": "122128"},
            ],
        })
        self.assertEqual(vehicle["vehicle_attributes"]["modelYear"], "09.2016 - 12.2018")
        self.assertEqual(vehicle["vehicle_attributes"]["engineType"], "083")
        self.assertEqual(vehicle["vehicle_attributes"]["engineDisplacement"], "1991 cc")
        self.assertEqual(vehicle["vehicle_attributes"]["engineCode"], "M 274.920")
        self.assertEqual(vehicle["vehicle_attributes"]["fuelType"], "Petrol")
        self.assertEqual(vehicle["vehicle_attributes"]["cylindersValves"], "4 / 4")
        self.assertEqual(vehicle["vehicle_attributes"]["bodyType"], "Coupe")
        self.assertEqual(vehicle["vehicle_attributes"]["fuelSystem"], "Direct injection")
        self.assertEqual(vehicle["vehicle_attributes"]["driveType"], "AWD")
        self.assertEqual(vehicle["vehicle_attributes"]["tecdocId"], "122128")
    def test_mercedes_trade_soft_description_is_split_into_explicit_card_fields(self):
        vehicle = main._normalize_tradesoft_vehicle({
            "brand": "Mercedes", "modelName": "C-class", "title": "205.349 (C 300 4MATIC)",
            "description": "C COUPE. . Regions: Europe, North America, Japan, 7-SPEED AUTOMATIC TRANSMISSION W7X700 (722969 06 680783, 722.969), R4 GASOLINE ENGINE M274 E20 (274920 30 609221, 274.920, M274 E20)",
            "parameters": [{"name":"Year","value":"2016"},{"name":"Production date","value":"05.02.2016"}],
        })
        a = vehicle["vehicle_attributes"]
        self.assertEqual(a["region"], "Europe, North America, Japan")
        self.assertEqual(a["bodyType"], "C COUPE")
        self.assertEqual(a["transmission"], "7-SPEED AUTOMATIC TRANSMISSION")
        self.assertEqual(a["gearboxModel"], "W7X700")
        self.assertEqual(a["gearboxCode"], "722.969")
        self.assertEqual(a["fuelType"], "Petrol")
        self.assertEqual(a["cylinders"], "4")
        self.assertIn("M274 E20", a["engineCode"])
        self.assertEqual(a["productionDate"], "05.02.2016")
        self.assertEqual(a["modelYear"], "2016")

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

    def test_only_tradesoft_is_exposed_as_catalog_provider(self):
        result = asyncio.run(main.providers())
        self.assertEqual(result["configured"], int(main.TRADESOFT_ENABLED))
        self.assertEqual([item["id"] for item in result["providers"]], ["tradesoft_parts_catalogs"])
        self.assertEqual(result["primary_provider"], "tradesoft_parts_catalogs" if main.TRADESOFT_ENABLED else None)

    def test_decode_requires_trade_soft_and_never_uses_external_fallback(self):
        previous = main.TRADESOFT_ADAPTER
        try:
            main.TRADESOFT_ADAPTER = None
            request = Request({
                "type": "http", "method": "POST", "scheme": "https", "path": "/",
                "raw_path": b"/", "query_string": b"", "headers": [],
                "server": ("localhost", 443), "client": ("127.0.0.1", 1234), "root_path": "",
            })
            with self.assertRaises(HTTPException) as failure:
                asyncio.run(main.decode_vehicle(main.DecodeRequest(vin="WVWZZZAUZJP594600"), request))
            self.assertEqual(failure.exception.status_code, 503)
            self.assertEqual(failure.exception.detail["provider"], "tradesoft_parts_catalogs")
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
