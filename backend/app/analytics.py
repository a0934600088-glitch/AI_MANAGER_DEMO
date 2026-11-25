"""Persistent analytics for the AI Manager demo.

PostgreSQL is the source of truth. If DATABASE_URL is absent, analytics writes
are skipped and admin analytics endpoints return 503; the customer chat remains
available. Tenant identity is deliberately fixed to 'default' until the app has
real tenant authentication (never trust a caller-supplied tenant header).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import psycopg

_SCHEMA_READY = False
from psycopg.rows import dict_row

def _dsn() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    parsed = urlparse(value)
    if parsed.scheme == "postgres":
        parsed = parsed._replace(scheme="postgresql")
    return urlunparse(parsed)

def _connect():
    return psycopg.connect(_dsn(), row_factory=dict_row, connect_timeout=5)

def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_manager_analytics_events (
                id BIGSERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                conversation_id TEXT,
                event_type TEXT NOT NULL,
                route TEXT,
                method TEXT,
                status_code INTEGER,
                duration_ms DOUBLE PRECISION,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_ai_analytics_tenant_time ON ai_manager_analytics_events (tenant_id, occurred_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_ai_analytics_conversation ON ai_manager_analytics_events (conversation_id)")
    _SCHEMA_READY = True

def record_event(event_type: str, *, conversation_id: str | None = None,
                 route: str | None = None, method: str | None = None,
                 status_code: int | None = None, duration_ms: float | None = None,
                 metadata: dict | None = None) -> None:
    ensure_schema()
    with _connect() as conn:
        conn.execute("""
            INSERT INTO ai_manager_analytics_events
            (tenant_id, conversation_id, event_type, route, method, status_code,
             duration_ms, metadata)
            VALUES ('default', %s, %s, %s, %s, %s, %s, %s::jsonb)
        """, (conversation_id, event_type[:80], route, method, status_code,
              duration_ms, json.dumps(metadata or {}, ensure_ascii=False)))

def dashboard_summary(days: int = 30) -> dict:
    ensure_schema()
    with _connect() as conn:
        totals = conn.execute("""
            SELECT COUNT(*) AS events,
                   COUNT(DISTINCT conversation_id) FILTER (WHERE conversation_id IS NOT NULL) AS conversations,
                   COUNT(*) FILTER (WHERE event_type = 'chat_message') AS messages,
                   COUNT(*) FILTER (WHERE event_type = 'vin_decode') AS vin_decodes,
                   COUNT(*) FILTER (WHERE event_type = 'parts_lookup') AS parts_lookups,
                   COUNT(*) FILTER (WHERE event_type = 'selection_success') AS successful_selections,
                   COUNT(*) FILTER (WHERE status_code >= 400) AS errors,
                   COALESCE(AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL), 0) AS avg_duration_ms
            FROM ai_manager_analytics_events
            WHERE tenant_id = 'default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
        """, (days,)).fetchone()
        daily = conn.execute("""
            SELECT DATE(occurred_at) AS day, COUNT(*) AS events,
                   COUNT(DISTINCT conversation_id) AS conversations
            FROM ai_manager_analytics_events
            WHERE tenant_id = 'default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY DATE(occurred_at) ORDER BY day
        """, (days,)).fetchall()
        providers = conn.execute("""
            SELECT COALESCE(metadata->>'provider', 'backend') AS provider,
                   COUNT(*) AS requests,
                   COUNT(*) FILTER (WHERE status_code >= 400) AS errors,
                   ROUND(AVG(duration_ms)::numeric, 1) AS avg_duration_ms
            FROM ai_manager_analytics_events
            WHERE tenant_id = 'default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
              AND (event_type = 'http_request' OR event_type = 'parts_lookup' OR event_type = 'vin_decode')
            GROUP BY 1 ORDER BY requests DESC
        """, (days,)).fetchall()
        recent = conn.execute("""
            SELECT occurred_at, conversation_id, event_type, route, status_code,
                   duration_ms, metadata
            FROM ai_manager_analytics_events
            WHERE tenant_id = 'default'
            ORDER BY occurred_at DESC LIMIT 100
        """).fetchall()
    def clean(rows):
        return [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()} for row in rows]
    return {"period_days": days, "totals": dict(totals), "daily": clean(daily),
            "providers": clean(providers), "recent_events": clean(recent),
            "scope": "default demo tenant"}

def conversation_summary(days: int = 30) -> list[dict]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute("""
            SELECT conversation_id,
                   MIN(occurred_at) AS started_at, MAX(occurred_at) AS last_activity_at,
                   EXTRACT(EPOCH FROM (MAX(occurred_at)-MIN(occurred_at))) AS duration_seconds,
                   COUNT(*) AS events,
                   COUNT(*) FILTER (WHERE event_type='chat_message') AS messages,
                   COUNT(*) FILTER (WHERE event_type='parts_lookup') AS lookups,
                   COUNT(*) FILTER (WHERE event_type='selection_success') AS successful_selections
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND conversation_id IS NOT NULL
              AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY conversation_id ORDER BY last_activity_at DESC LIMIT 200
        """, (days,)).fetchall()
    return [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()} for row in rows]
