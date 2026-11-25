"""PostgreSQL-backed operational analytics for the AI Manager demo.

Only aggregate-safe metadata is persisted. Raw chat text, VINs, phone numbers,
emails, credentials and catalogue payloads are never accepted by this module.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime
from threading import Lock
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row

_SCHEMA_READY = False
_SCHEMA_LOCK = Lock()
_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_SAFE_METADATA = {
    "provider", "mode", "surface", "language", "length", "reason", "status",
    "duration_ms", "tokens_input", "tokens_output", "cost_usd", "model", "stage",
    "result", "http_status", "request_kind",
}


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


def _clean_metadata(metadata: dict | None) -> dict:
    clean = {}
    for key, value in (metadata or {}).items():
        if key not in _SAFE_METADATA:
            continue
        if isinstance(value, str):
            clean[key] = value[:120]
        elif isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            clean[key] = value
    return clean


def _clean_conversation_id(value: str | None) -> str | None:
    if not value or not isinstance(value, str) or not _CONVERSATION_ID.fullmatch(value):
        return None
    return value


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
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
            conn.execute("CREATE INDEX IF NOT EXISTS ix_ai_analytics_conversation ON ai_manager_analytics_events (tenant_id, conversation_id, occurred_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_ai_analytics_type_time ON ai_manager_analytics_events (tenant_id, event_type, occurred_at)")
        _SCHEMA_READY = True


def record_event(event_type: str, *, conversation_id: str | None = None,
                 route: str | None = None, method: str | None = None,
                 status_code: int | None = None, duration_ms: float | None = None,
                 metadata: dict | None = None) -> None:
    ensure_schema()
    safe_duration = float(duration_ms) if duration_ms is not None and math.isfinite(float(duration_ms)) else None
    safe_meta = _clean_metadata(metadata)
    with _connect() as conn:
        conn.execute("""
            INSERT INTO ai_manager_analytics_events
            (tenant_id, conversation_id, event_type, route, method, status_code,
             duration_ms, metadata)
            VALUES ('default', %s, %s, %s, %s, %s, %s, %s::jsonb)
        """, (_clean_conversation_id(conversation_id), event_type[:80],
              (route or "")[:160] or None, (method or "")[:12] or None,
              status_code, safe_duration, json.dumps(safe_meta, ensure_ascii=False)))


def dashboard_summary(days: int = 30) -> dict:
    ensure_schema()
    with _connect() as conn:
        totals = conn.execute("""
            SELECT COUNT(*) AS events,
              COUNT(*) FILTER (WHERE event_type IN ('http_request','vin_decode','parts_lookup')) AS requests,
              COUNT(DISTINCT conversation_id) FILTER (WHERE conversation_id IS NOT NULL) AS conversations,
              COUNT(DISTINCT conversation_id) FILTER (WHERE event_type IN ('conversation_started','chat_message')) AS clients,
              COUNT(*) FILTER (WHERE event_type='chat_message') AS messages,
              COUNT(*) FILTER (WHERE event_type='vin_decode') AS vin_decodes,
              COUNT(*) FILTER (WHERE event_type='parts_lookup') AS parts_lookups,
              COUNT(*) FILTER (WHERE event_type='selection_success') AS successful_selections,
              COUNT(*) FILTER (WHERE event_type='selection_failed') AS failed_selections,
              COUNT(*) FILTER (WHERE event_type='parts_selection_incomplete') AS incomplete_selections,
              COUNT(*) FILTER (WHERE event_type='vehicle_confirmed') AS vehicle_confirmations,
              COUNT(*) FILTER (WHERE status_code >= 400 OR event_type='parts_lookup_failed') AS errors,
              ROUND(AVG(duration_ms)::numeric, 1) FILTER (WHERE duration_ms IS NOT NULL) AS avg_api_duration_ms,
              ROUND(AVG(duration_ms)::numeric, 1) FILTER (WHERE event_type='ai_response' AND duration_ms IS NOT NULL) AS avg_ai_response_ms,
              ROUND(AVG(duration_ms)::numeric, 1) FILTER (WHERE event_type='selection_completed' AND duration_ms IS NOT NULL) AS avg_selection_ms,
              COALESCE(SUM((metadata->>'tokens_input')::numeric) FILTER (WHERE event_type='ai_usage'),0) AS tokens_input,
              COALESCE(SUM((metadata->>'tokens_output')::numeric) FILTER (WHERE event_type='ai_usage'),0) AS tokens_output,
              COALESCE(SUM((metadata->>'cost_usd')::numeric) FILTER (WHERE event_type='ai_usage'),0) AS ai_cost_usd
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
        """, (days,)).fetchone()
        daily = conn.execute("""
            SELECT DATE(occurred_at) AS day, COUNT(*) AS events,
              COUNT(*) FILTER (WHERE event_type IN ('http_request','vin_decode','parts_lookup')) AS requests,
              COUNT(DISTINCT conversation_id) AS conversations
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY DATE(occurred_at) ORDER BY day
        """, (days,)).fetchall()
        catalogs = conn.execute("""
            SELECT COALESCE(metadata->>'provider','backend') AS provider,
              COALESCE(route,'—') AS route, COUNT(*) AS requests,
              COUNT(*) FILTER (WHERE status_code >= 400) AS errors,
              ROUND(AVG(duration_ms)::numeric,1) AS avg_duration_ms
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
              AND event_type IN ('http_request','vin_decode','parts_lookup')
            GROUP BY 1,2 ORDER BY requests DESC
        """, (days,)).fetchall()
        request_types = conn.execute("""
            SELECT COALESCE(route,'unknown') AS route, COUNT(*) AS requests,
              COUNT(*) FILTER (WHERE status_code >= 400) AS errors
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
              AND event_type IN ('http_request','vin_decode','parts_lookup')
            GROUP BY 1 ORDER BY requests DESC
        """, (days,)).fetchall()
        funnel = conn.execute("""
            SELECT
              COUNT(*) FILTER (WHERE event_type IN ('http_request','vin_decode','parts_lookup')) AS requests,
              COUNT(*) FILTER (WHERE event_type='parts_lookup') AS selections_started,
              COUNT(*) FILTER (WHERE event_type='selection_success') AS selections_success,
              COUNT(*) FILTER (WHERE event_type='offer_created') AS offers,
              COUNT(*) FILTER (WHERE event_type='order_created') AS orders
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
        """, (days,)).fetchone()
        recent = conn.execute("""
            SELECT occurred_at, conversation_id, event_type, route, status_code, duration_ms, metadata
            FROM ai_manager_analytics_events WHERE tenant_id='default'
            ORDER BY occurred_at DESC LIMIT 100
        """).fetchall()
        coverage = conn.execute("""
            SELECT
              COUNT(*) FILTER (WHERE event_type IN ('selection_success','selection_failed','parts_selection_incomplete')) AS selection_events,
              COUNT(*) FILTER (WHERE event_type IN ('offer_created','order_created')) AS sales_events,
              COUNT(*) FILTER (WHERE event_type='ai_usage') AS ai_usage_events,
              COUNT(*) FILTER (WHERE event_type='ai_response') AS ai_response_events,
              COUNT(*) FILTER (WHERE event_type='selection_completed') AS selection_timing_events
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
        """, (days,)).fetchone()

    def clean(rows):
        return [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()} for row in rows]
    return {
        "period_days": days, "totals": dict(totals), "daily": clean(daily),
        "catalogs": clean(catalogs), "request_types": clean(request_types),
        "funnel": dict(funnel), "recent_events": clean(recent),
        "coverage": dict(coverage), "scope": "single demo tenant",
    }


def conversation_summary(days: int = 30) -> list[dict]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute("""
            SELECT conversation_id, MIN(occurred_at) AS started_at,
              MAX(occurred_at) AS last_activity_at,
              ROUND(EXTRACT(EPOCH FROM (MAX(occurred_at)-MIN(occurred_at)))::numeric,1) AS duration_seconds,
              COUNT(*) AS events,
              COUNT(*) FILTER (WHERE event_type='chat_message') AS messages,
              COUNT(*) FILTER (WHERE event_type='vin_decode') AS vin_decodes,
              COUNT(*) FILTER (WHERE event_type='parts_lookup') AS parts_lookups
            FROM ai_manager_analytics_events
            WHERE tenant_id='default' AND conversation_id IS NOT NULL
              AND occurred_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY conversation_id ORDER BY last_activity_at DESC LIMIT 200
        """, (days,)).fetchall()
    return [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()} for row in rows]
