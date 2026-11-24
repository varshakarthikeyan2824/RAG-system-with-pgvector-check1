import hashlib
import secrets
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import psycopg

from src.config import get_settings
from src.security import password_hash, verify_password

DATABASE_URL = get_settings().database_url

SESSION_DURATION_HOURS = 12

SessionUser = namedtuple(
    "SessionUser",
    ["user_id", "tenant_id", "role"],
)
# Used to reduce timing differences for unknown users.
DUMMY_PASSWORD_HASH = password_hash.hash(secrets.token_urlsafe(32))


def _hash_token(token: str) -> str:
    """Return the SHA-256 hash of a session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str) -> str:
    """Create a session and return its raw token."""
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_sessions (token_hash, user_id, expires_at)
                VALUES (%s, %s, %s)
                """,
                (token_hash, user_id, expires_at),
            )

    return token


def get_session_user(token: str):
    """Return the authenticated user for an active session, or None."""
    if not token:
        return None

    token_hash = _hash_token(token)

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id, u.tenant_id, u.role
                FROM user_sessions AS s
                JOIN users AS u ON u.user_id = s.user_id
                WHERE s.token_hash = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > NOW()
                """,
                (token_hash,),
            )
            row = cur.fetchone()

    return SessionUser(*row) if row else None


def revoke_session(token: str) -> bool:
    """Revoke an active session. Return True if a session was revoked."""
    if not token:
        return False

    token_hash = _hash_token(token)

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_sessions
                SET revoked_at = NOW()
                WHERE token_hash = %s
                  AND revoked_at IS NULL
                """,
                (token_hash,),
            )
            return cur.rowcount == 1


def authenticate_user(user_id: str, password: str):
    """Verify credentials and return the user, or None."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, tenant_id, role, password_hash
                FROM users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if row is None or row[3] is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, row[3]):
        return None

    return SessionUser(row[0], row[1], row[2])
