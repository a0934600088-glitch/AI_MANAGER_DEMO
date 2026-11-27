"""Real PostgreSQL tests for tenant-bound event storage and public widget keys."""
import unittest
import uuid

from fastapi import HTTPException

from app import analytics, auth


class PostgresTenantIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        analytics._SCHEMA_READY = False
        analytics.ensure_schema()
        auth.ensure_schema()

    def test_analytics_and_conversations_do_not_cross_tenant_boundaries(self):
        suffix = uuid.uuid4().hex
        tenant_a = "tenant-a-" + suffix
        tenant_b = "tenant-b-" + suffix
        conversation_a = "conversation-a-" + suffix
        conversation_b = "conversation-b-" + suffix

        analytics.record_event("conversation_started", tenant_id=tenant_a, conversation_id=conversation_a)
        analytics.record_event("chat_message", tenant_id=tenant_a, conversation_id=conversation_a)
        analytics.record_event("conversation_started", tenant_id=tenant_b, conversation_id=conversation_b)

        rows_a = analytics.conversation_summary(30, tenant_a)
        rows_b = analytics.conversation_summary(30, tenant_b)
        self.assertEqual([row["conversation_id"] for row in rows_a], [conversation_a])
        self.assertEqual([row["conversation_id"] for row in rows_b], [conversation_b])

        summary_a = analytics.dashboard_summary(30, tenant_a)
        summary_b = analytics.dashboard_summary(30, tenant_b)
        self.assertEqual(summary_a["totals"]["events"], 2)
        self.assertEqual(summary_b["totals"]["events"], 1)
        self.assertEqual(summary_a["scope"], "tenant:" + tenant_a)
        self.assertEqual(summary_b["scope"], "tenant:" + tenant_b)

    def test_public_widget_key_is_bound_to_its_tenant_and_domain(self):
        suffix = uuid.uuid4().hex
        domain = "shop-" + suffix + ".example.test"
        tenant = auth.create_tenant("Integration " + suffix[:8], "ci-" + suffix, [domain])

        self.assertEqual(auth.resolve_public_tenant(tenant["public_key"], "https://" + domain), str(tenant["id"]))
        with self.assertRaises(HTTPException) as error:
            auth.resolve_public_tenant(tenant["public_key"], "https://other.example.test")
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
