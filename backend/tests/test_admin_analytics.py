import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app import analytics, main


class AdminAnalyticsContractTests(unittest.TestCase):
    def test_existing_admin_token_auth_is_preserved(self):
        old = main.ADMIN_API_TOKEN
        old_user, old_pass = main.ADMIN_USERNAME, main.ADMIN_PASSWORD
        try:
            main.ADMIN_API_TOKEN = "token-test"
            main.ADMIN_USERNAME = ""
            main.ADMIN_PASSWORD = ""
            main._authorize_admin(None, "token-test")
            with self.assertRaises(HTTPException):
                main._authorize_admin(None, "wrong")
        finally:
            main.ADMIN_API_TOKEN = old
            main.ADMIN_USERNAME, main.ADMIN_PASSWORD = old_user, old_pass

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
                asyncio.run(main.analytics_event(payload, SimpleNamespace(state=SimpleNamespace(tenant_id="default"))))
        self.assertEqual(error.exception.status_code, 422)
        record.assert_not_called()

    def test_ai_usage_numeric_strings_are_validated_before_sql_cast(self):
        safe = analytics._clean_metadata({
            "tokens_input": "120", "tokens_output": "45", "cost_usd": "0.0025",
            "model": "test-model", "cost_usd_bad": "not-a-number",
        })
        self.assertEqual(safe["tokens_input"], 120.0)
        self.assertEqual(safe["tokens_output"], 45.0)
        self.assertEqual(safe["cost_usd"], 0.0025)

    def test_metadata_filter_removes_raw_chat_content_and_identifiers(self):
        metadata = {"length": 22, "message": "private text", "vin": "WVWZZZAUZJP594600",
                    "phone": "+380000000000", "language": "uk"}
        self.assertEqual(analytics._clean_metadata(metadata), {"length": 22, "language": "uk"})

    def test_chat_event_is_persisted_with_session_id(self):
        payload = main.AnalyticsEventRequest(event_type="chat_message", conversation_id="session-test",
                                             metadata={"length": 22, "language": "uk"})
        with patch("app.main.analytics.record_event") as record:
            result = asyncio.run(main.analytics_event(payload, SimpleNamespace(state=SimpleNamespace(tenant_id="tenant-77"))))
        self.assertEqual(result, {"status": "recorded"})
        record.assert_called_once()
        args = record.call_args.kwargs
        self.assertEqual(args["tenant_id"], "tenant-77")
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

    def test_manager_analytics_is_scoped_to_its_tenant(self):
        user = {"role": "manager", "tenant_id": 42}
        with patch("app.main.analytics.dashboard_summary", return_value={"scope": "tenant:42"}) as summary:
            result = asyncio.run(main.admin_analytics(30, user))
        self.assertEqual(result["scope"], "tenant:42")
        summary.assert_called_once_with(30, "42")

    def test_super_admin_analytics_uses_platform_demo_scope(self):
        user = {"role": "super_admin", "tenant_id": None}
        with patch("app.main.analytics.dashboard_summary", return_value={"scope": "tenant:default"}) as summary:
            asyncio.run(main.admin_analytics(7, user))
        summary.assert_called_once_with(7, "default")

    def test_manager_conversations_are_scoped_to_its_tenant(self):
        user = {"role": "manager", "tenant_id": 19}
        with patch("app.main.analytics.conversation_summary", return_value=[]) as summary:
            result = asyncio.run(main.admin_conversations(90, user))
        self.assertEqual(result["scope"], "tenant:19")
        summary.assert_called_once_with(90, "19")

    def test_shop_admin_cannot_create_another_shop_admin(self):
        payload = main.TenantUserCreateRequest(
            username="second-admin", display_name="Second admin",
            password="long-enough-password", role="shop_admin",
        )
        with patch("app.main.auth.create_user") as create_user:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(main.admin_create_tenant_user(
                    12, payload, {"role": "shop_admin", "tenant_id": 12}
                ))
        self.assertEqual(error.exception.status_code, 403)
        create_user.assert_not_called()

    def test_shop_admin_cannot_list_another_tenants_staff(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.admin_list_tenant_users(43, {"role": "shop_admin", "tenant_id": 42}))
        self.assertEqual(error.exception.status_code, 403)

    def test_manager_cannot_list_or_create_staff(self):
        with self.assertRaises(HTTPException) as list_error:
            asyncio.run(main.admin_list_tenant_users(42, {"role": "manager", "tenant_id": 42}))
        self.assertEqual(list_error.exception.status_code, 403)
        payload = main.TenantUserCreateRequest(
            username="new-manager", display_name="New manager",
            password="long-enough-password", role="manager",
        )
        with self.assertRaises(HTTPException) as create_error:
            asyncio.run(main.admin_create_tenant_user(42, payload, {"role": "manager", "tenant_id": 42}))
        self.assertEqual(create_error.exception.status_code, 403)

    def test_shop_admin_cannot_create_platform_tenants(self):
        payload = main.TenantCreateRequest(name="Other shop", slug="other-shop", domains=["other.example.com"])
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.admin_create_tenant(payload, {"role": "shop_admin", "tenant_id": 42}))
        self.assertEqual(error.exception.status_code, 403)

    def test_unknown_role_cannot_open_analytics(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.admin_analytics(30, {"role": "unknown", "tenant_id": 1}))
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
