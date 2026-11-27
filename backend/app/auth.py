"""Database-backed identities, tenant membership and opaque bearer sessions."""
from __future__ import annotations
import base64, hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import HTTPException
from . import analytics

ROLES = {"super_admin", "shop_admin", "manager", "observer"}
SESSION_DAYS = 7

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + _b64(salt) + "$" + _b64(digest)

def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_text, digest_text = encoded.split("$", 2)
        if algorithm != "scrypt": return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt_text), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, _unb64(digest_text))
    except (ValueError, TypeError):
        return False

def ensure_schema() -> None:
    with analytics._connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_manager_tenants (
                id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_manager_users (
                id BIGSERIAL PRIMARY KEY, tenant_id BIGINT REFERENCES ai_manager_tenants(id),
                username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('super_admin','shop_admin','manager','observer')),
                is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CHECK ((role = 'super_admin' AND tenant_id IS NULL) OR (role <> 'super_admin' AND tenant_id IS NOT NULL)))
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_manager_sessions (
                id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES ai_manager_users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE, expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_ai_manager_sessions_expiry ON ai_manager_sessions(expires_at)")
        username, password = os.getenv("ADMIN_USERNAME", "").strip(), os.getenv("ADMIN_PASSWORD", "")
        if username and password:
            conn.execute("""
                INSERT INTO ai_manager_users(tenant_id, username, display_name, password_hash, role)
                VALUES (NULL, %s, 'Главный администратор', %s, 'super_admin')
                ON CONFLICT (username) DO NOTHING
            """, (username, _password_hash(password)))

def login(username: str, password: str) -> dict[str, Any]:
    ensure_schema()
    with analytics._connect() as conn:
        user = conn.execute("""SELECT id, tenant_id, username, display_name, password_hash, role
            FROM ai_manager_users WHERE username=%s AND is_active=TRUE""", (username.strip(),)).fetchone()
        if not user or not _password_matches(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
        token = _b64(secrets.token_bytes(32))
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        conn.execute("INSERT INTO ai_manager_sessions(user_id, token_hash, expires_at) VALUES (%s,%s,%s)",
                     (user["id"], digest, expires))
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(),
            "user": {k: user[k] for k in ("id", "tenant_id", "username", "display_name", "role")}}

def authenticate(token: str | None) -> dict[str, Any]:
    if not token: raise HTTPException(status_code=401, detail="Требуется авторизация")
    ensure_schema()
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with analytics._connect() as conn:
        user = conn.execute("""SELECT u.id, u.tenant_id, u.username, u.display_name, u.role
            FROM ai_manager_sessions s JOIN ai_manager_users u ON u.id=s.user_id
            LEFT JOIN ai_manager_tenants t ON t.id=u.tenant_id
            WHERE s.token_hash=%s AND s.expires_at>NOW() AND u.is_active=TRUE
            AND (u.tenant_id IS NULL OR t.status='active')""", (digest,)).fetchone()
    if not user: raise HTTPException(status_code=401, detail="Сессия недействительна или истекла")
    return dict(user)

def revoke(token: str | None) -> None:
    if not token: return
    ensure_schema()
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with analytics._connect() as conn:
        conn.execute("DELETE FROM ai_manager_sessions WHERE token_hash=%s", (digest,))

def require_role(user: dict[str, Any], *roles: str) -> dict[str, Any]:
    if user.get("role") not in roles: raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user

def create_tenant(name: str, slug: str) -> dict[str, Any]:
    ensure_schema()
    with analytics._connect() as conn:
        row = conn.execute("""INSERT INTO ai_manager_tenants(name,slug) VALUES (%s,%s)
            RETURNING id,name,slug,status,created_at""", (name.strip(), slug.strip().lower())).fetchone()
    return dict(row)

def create_user(tenant_id: int, username: str, display_name: str, password: str, role: str) -> dict[str, Any]:
    if role not in {"shop_admin", "manager", "observer"}:
        raise HTTPException(status_code=422, detail="Недопустимая роль сотрудника")
    if len(password) < 12:
        raise HTTPException(status_code=422, detail="Пароль должен содержать не менее 12 символов")
    ensure_schema()
    with analytics._connect() as conn:
        tenant = conn.execute("SELECT id FROM ai_manager_tenants WHERE id=%s AND status='active'", (tenant_id,)).fetchone()
        if not tenant: raise HTTPException(status_code=404, detail="Магазин не найден или отключён")
        row = conn.execute("""INSERT INTO ai_manager_users(tenant_id,username,display_name,password_hash,role)
            VALUES (%s,%s,%s,%s,%s) RETURNING id,tenant_id,username,display_name,role,is_active""",
            (tenant_id, username.strip(), display_name.strip(), _password_hash(password), role)).fetchone()
    return dict(row)


def list_tenants() -> list[dict[str, Any]]:
    ensure_schema()
    with analytics._connect() as conn:
        rows = conn.execute("SELECT id, name, slug, status, created_at FROM ai_manager_tenants ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def list_users(tenant_id: int) -> list[dict[str, Any]]:
    ensure_schema()
    with analytics._connect() as conn:
        rows = conn.execute("""
            SELECT id, tenant_id, username, display_name, role, is_active, created_at
            FROM ai_manager_users WHERE tenant_id=%s ORDER BY display_name, username
        """, (tenant_id,)).fetchall()
    return [dict(row) for row in rows]
