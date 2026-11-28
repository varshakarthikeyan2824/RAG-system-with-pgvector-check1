import pytest
from fastapi.testclient import TestClient

from src import main
from src.rate_limit import ask_limiter, login_limiter

client = TestClient(main.app)
LOGIN_BODY = {"user_id": "x", "password": "y"}


@pytest.fixture(autouse=True)
def reset_limiters():
    """Rate-limit counts live in memory, so clear them around every test."""
    for limiter in (login_limiter, ask_limiter):
        limiter.hits.clear()
    yield
    for limiter in (login_limiter, ask_limiter):
        limiter.hits.clear()


# --- Security headers -------------------------------------------------------


def test_security_headers_present():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]


def test_hsts_sent_outside_development():
    # conftest sets APP_ENV=test, which is not "development", so HSTS is on.
    response = client.get("/health")
    assert "max-age=" in response.headers["strict-transport-security"]


# --- CORS -------------------------------------------------------------------


def test_cors_refuses_unlisted_origin():
    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_does_not_reflect_origin_on_normal_request():
    response = client.get("/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


# --- Rate limiting ----------------------------------------------------------


def test_login_rate_limit_returns_429_with_retry_after():
    codes = [client.post("/login", json=LOGIN_BODY).status_code for _ in range(5)]
    assert 429 not in codes  # the first five are let through

    response = client.post("/login", json=LOGIN_BODY)

    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert response.json()["error"]["message"] == "Too many requests"


def test_rate_limit_error_still_has_security_headers():
    for _ in range(5):
        client.post("/login", json=LOGIN_BODY)
    response = client.post("/login", json=LOGIN_BODY)

    assert response.status_code == 429
    assert response.headers["x-content-type-options"] == "nosniff"


# --- Request size limit -----------------------------------------------------


def test_oversized_body_is_refused_with_413():
    response = client.post("/login", content=b"a" * 100_000)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_normal_sized_body_is_not_refused_for_size():
    response = client.post("/login", json=LOGIN_BODY)

    assert response.status_code not in (411, 413)


def test_chunked_body_is_refused_with_411():
    # An iterator body makes the client send Transfer-Encoding: chunked.
    response = client.post("/login", content=iter([b'{"user_id":"x"}']))

    assert response.status_code == 411
    assert response.json()["error"]["code"] == "LENGTH_REQUIRED"
