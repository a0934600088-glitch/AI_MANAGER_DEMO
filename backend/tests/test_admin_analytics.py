import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main


class AdminAnalyticsContractTests(unittest.TestCase):
    def test_admin_analytics_requires_admin_token(self):
        previous = main.ADMIN_API_TOKEN
        try:
            main.ADMIN_API_TOKEN = "test-admin-secret"
            with self.assertRaises(HTTPException) as missing:
                asyncio.run(main.admin_analytics(30, None))
            self.assertEqual(missing.exception.status_code, 401)
        finally:
            main.ADMIN_API_TOKEN = previous

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

    def test_cors_allows_conversation_tracking_header(self):
        cors = next(
            middleware for middleware in main.app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        )
        allowed = [header.lower() for header in cors.kwargs["allow_headers"]]
        self.assertIn("x-conversation-id", allowed)


if __name__ == "__main__":
    unittest.main()
