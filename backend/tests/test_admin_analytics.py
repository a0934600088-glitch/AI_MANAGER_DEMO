import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app import main


class AdminAnalyticsContractTests(unittest.TestCase):
    def test_admin_analytics_rejects_missing_credentials(self):
        old_username, old_password = main.ADMIN_USERNAME, main.ADMIN_PASSWORD
        try:
            main.ADMIN_USERNAME = "admin"
            main.ADMIN_PASSWORD = "secret"
            with self.assertRaises(HTTPException) as missing:
                asyncio.run(main.admin_analytics(30, None))
            self.assertEqual(missing.exception.status_code, 401)
            self.assertEqual(missing.exception.headers["WWW-Authenticate"], "Basic")
        finally:
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = old_username, old_password

    def test_admin_analytics_rejects_wrong_credentials(self):
        old_username, old_password = main.ADMIN_USERNAME, main.ADMIN_PASSWORD
        try:
            main.ADMIN_USERNAME = "admin"
            main.ADMIN_PASSWORD = "secret"
            wrong = HTTPBasicCredentials(username="admin", password="wrong")
            with self.assertRaises(HTTPException) as denied:
                asyncio.run(main.admin_analytics(30, wrong))
            self.assertEqual(denied.exception.status_code, 401)
        finally:
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = old_username, old_password

    def test_admin_analytics_accepts_valid_basic_credentials(self):
        old_username, old_password = main.ADMIN_USERNAME, main.ADMIN_PASSWORD
        try:
            main.ADMIN_USERNAME = "admin"
            main.ADMIN_PASSWORD = "secret"
            valid = HTTPBasicCredentials(username="admin", password="secret")
            with patch("app.main.analytics.dashboard_summary", return_value={"scope": "test"}):
                result = asyncio.run(main.admin_analytics(30, valid))
            self.assertEqual(result, {"scope": "test"})
        finally:
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = old_username, old_password

    def test_admin_analytics_is_disabled_without_server_credentials(self):
        old_username, old_password = main.ADMIN_USERNAME, main.ADMIN_PASSWORD
        try:
            main.ADMIN_USERNAME = ""
            main.ADMIN_PASSWORD = ""
            with self.assertRaises(HTTPException) as disabled:
                asyncio.run(main.admin_analytics(30, None))
            self.assertEqual(disabled.exception.status_code, 503)
        finally:
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = old_username, old_password

    def test_analytics_event_accepts_only_known_event_types(self):
        payload = main.AnalyticsEventRequest(event_type="not_allowed")
        with self.assertRaises(HTTPException) as invalid:
            asyncio.run(main.analytics_event(payload))
        self.assertEqual(invalid.exception.status_code, 422)

    def test_chat_event_is_persisted_with_conversation_id(self):
        payload = main.AnalyticsEventRequest(
            event_type="chat_message",
            metadata={"length": 18, "language": "ru"},
        )
        with patch("app.main.analytics.record_event") as record:
            result = asyncio.run(main.analytics_event(payload, "conversation-test"))
        self.assertEqual(result["status"], "recorded")
        record.assert_called_once_with(
            "chat_message",
            conversation_id="conversation-test",
            metadata={"length": 18, "language": "ru"},
        )

    def test_cors_allows_basic_authorization_and_conversation_tracking(self):
        cors = next(
            middleware for middleware in main.app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        )
        allowed = [header.lower() for header in cors.kwargs["allow_headers"]]
        self.assertIn("authorization", allowed)
        self.assertIn("x-conversation-id", allowed)
        self.assertNotIn("x-admin-token", allowed)

    def test_backend_version_comes_from_single_version_file(self):
        with open("VERSION", encoding="utf-8") as version_file:
            self.assertEqual(main.APP_VERSION, version_file.read().strip())


if __name__ == "__main__":
    unittest.main()
