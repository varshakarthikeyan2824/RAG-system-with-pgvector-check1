import hashlib
import secrets
from urllib.parse import urlsplit

import psycopg

from src.config import get_settings
from src.security import hash_password
from src.session import (
    DATABASE_URL,
    authenticate_user,
    create_session,
    get_session_user,
    revoke_session,
)


def test_create_and_validate_session():
    token = create_session("u_cust")

    try:
        assert token
        user = get_session_user(token)

        assert user is not None
        assert user.user_id == "u_cust"
        assert user.tenant_id == "water_company_A"
        assert user.role == "customer"

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        with psycopg.connect(get_settings().database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT token_hash FROM user_sessions WHERE token_hash = %s",
                    (token_hash,),
                )
                row = cur.fetchone()

        assert row is not None
        assert row[0] != token

    finally:
        revoke_session(token)


def test_unknown_session_returns_none():
    token = secrets.token_urlsafe(32)

    assert get_session_user(token) is None


def test_revoked_session_is_invalid():
    token = create_session("u_cust")

    assert revoke_session(token) is True
    assert get_session_user(token) is None


def test_session_cannot_be_revoked_twice():
    token = create_session("u_cust")

    try:
        assert revoke_session(token) is True
        assert revoke_session(token) is False
    finally:
        revoke_session(token)


def test_authenticate_user_with_correct_password():
    password = "MySecureTestPassword123!"
    hashed = hash_password(password)

    with psycopg.connect(get_settings().database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s
                WHERE user_id = %s
                """,
                (hashed, "u_cust"),
            )

    user = authenticate_user("u_cust", password)

    assert user is not None
    assert user.user_id == "u_cust"
    assert user.role == "customer"


def test_authenticate_user_with_wrong_password():
    user = authenticate_user("u_cust", "WrongPassword123!")

    assert user is None


def test_authenticate_unknown_user():
    user = authenticate_user("unknown_user", "SomePassword123!")

    assert user is None


def test_authenticate_user_without_password_hash():
    with psycopg.connect(get_settings().database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = NULL
                WHERE user_id = %s
                """,
                ("u_eng",),
            )

    user = authenticate_user("u_eng", "SomePassword123!")

    assert user is None


def test_pytest_uses_test_database():
    settings_database = urlsplit(get_settings().database_url)
    session_database = urlsplit(DATABASE_URL)

    assert settings_database.path == "/water_rag_test_db"
    assert session_database.path == "/water_rag_test_db"
