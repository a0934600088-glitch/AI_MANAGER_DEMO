import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app import analytics, main


class AdminAnalyticsContractTests(unittest.TestCase):
    def test_existing_admin_token_auth_is_preserved(self):
        old = main.ADMIN_API_TOKEN
        try:
            main.ADMIN_API_TOKEN = "token-test"
            main.ADMIN_USERNAME = ""
            main.ADMIN_PASSWORD = ""
            main._authorize_admin(None, "token-test")
            with self.assertRaises(HTTPException):
                main._authorize_admin(None, "wrong")
        finally:
            main.ADMIN_API_TOKEN = old

    def test_basic_auth_is_supported_when_configured(self):
        old_user, old_pass = main.ADMIN_USERNAME, main.ADMIN_PASSWORD
        try:
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = "operator", "secret"
            main._authorize_admin(HTTPBasicCredentials(username="operator", password="secret"))
            with self.assertRaises(HTTPException):
                main._authorize_admin(HTTPBasicCredentials(username="operator", password="wrong"))
        finally:
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = old_user, old_pass

    def test_public_event_allowlist_excludes_fake_selection_success(self):
        payload = main.AnalyticsEventRequest(event_type="selection_success")
        with patch("app.main.analytics.record_event") as record:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(main.analytics_event(payload))
        self.assertEqual(error.exception.status_code, 422)
        record.assert_not_called()

    def test_metadata_filter_removes_raw_chat_content_and_identifiers(self):
        metadata = {"length": 22, "message": "private text", "vin": "WVWZZZAUZJP594600",
                    "phone": "+380000000000", "language": "uk"}
        self.assertEqual(analytics._clean_metadata(metadata), {"length": 22, "language": "uk"})

    def test_chat_event_is_persisted_with_session_id(self):
        payload = main.AnalyticsEventRequest(event_type="chat_message", conversation_id="session-test",
                                             metadata={"length": 22, "language": "uk"})
        with patch("app.main.analytics.record_event") as record:
            result = asyncio.run(main.analytics_event(payload))
        self.assertEqual(result, {"status": "recorded"})
        record.assert_called_once()
        args = record.call_args.kwargs
        self.assertEqual(args["conversation_id"], "session-test")
        self.assertEqual(args["metadata"], {"length": 22, "language": "uk"})

    def test_database_url_missing_fails_closed(self):
        old = __import__("os").environ.pop("DATABASE_URL", None)
        try:
            with self.assertRaises(RuntimeError):
                analytics._dsn()
        finally:
            if old is not None:
                __import__("os").environ["DATABASE_URL"] = old


if __name__ == "__main__":
    unittest.main()
