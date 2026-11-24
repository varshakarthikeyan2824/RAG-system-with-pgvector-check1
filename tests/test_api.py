import re
from collections import namedtuple

from fastapi.testclient import TestClient

from src import main

client = TestClient(main.app)
FakeUser = namedtuple("FakeUser", ["tenant_id", "role"])
KEY = {"x-service-key": "test-key"}
TEST_PASSWORD = "MySecureTestPassword123!"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers.get("X-Request-ID")


def test_ask_success(monkeypatch):
    monkeypatch.setattr(
        main, "lookup_user", lambda uid: FakeUser("water_company_A", "engineer")
    )
    monkeypatch.setattr(
        main,
        "generate_answer_with_citations",
        lambda **kw: {"answer": "Two active outages.", "citations": []},
    )

    response = client.post(
        "/ask",
        headers=KEY,
        json={"question": "Which outages are active?", "user_id": "u_eng"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Two active outages."


def test_ask_without_key_is_refused():
    response = client.post(
        "/ask", json={"question": "Which outages are active?", "user_id": "u_eng"}
    )
    assert response.status_code == 401


def test_ask_unknown_user_is_refused(monkeypatch):
    monkeypatch.setattr(main, "lookup_user", lambda uid: None)
    response = client.post(
        "/ask",
        headers=KEY,
        json={"question": "Which outages are active?", "user_id": "nobody"},
    )
    assert response.status_code == 403


def test_client_cannot_choose_its_own_role(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        main, "lookup_user", lambda uid: FakeUser("water_company_A", "customer")
    )

    def fake(**kw):
        seen.update(kw)
        return {"answer": "x", "citations": []}

    monkeypatch.setattr(main, "generate_answer_with_citations", fake)

    client.post(
        "/ask",
        headers=KEY,
        json={
            "question": "Who is on crew duty?",
            "user_id": "u_cust",
            "user_role": "engineer",
        },
    )  # an attacker's extra field

    assert seen["user_role"] == "customer"  # the server's value wins


def test_validation_error():
    response = client.post(
        "/ask", headers=KEY, json={"question": "Which outages are active?"}
    )  # user_id missing
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_unexpected_error(monkeypatch):
    monkeypatch.setattr(
        main, "lookup_user", lambda uid: FakeUser("water_company_A", "engineer")
    )

    def boom(**kw):
        raise RuntimeError("Sensitive internal database details")

    monkeypatch.setattr(main, "generate_answer_with_citations", boom)

    test_client = TestClient(main.app, raise_server_exceptions=False)
    response = test_client.post(
        "/ask", headers=KEY, json={"question": "Test error", "user_id": "u_eng"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "Sensitive internal database details" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_login_success(monkeypatch):
    fake_user = FakeUser("water_company_A", "customer")

    monkeypatch.setattr(
        main,
        "authenticate_user",
        lambda uid, password: (
            namedtuple("User", ["user_id", "tenant_id", "role"])(
                uid, fake_user.tenant_id, fake_user.role
            )
            if uid == "u_cust" and password == TEST_PASSWORD
            else None
        ),
    )
    monkeypatch.setattr(main, "create_session", lambda uid: "test-session-token")
    test_client = TestClient(main.app, base_url="https://testserver")
    page = test_client.get("/knowledge")

    csrf_token = re.search(
        r'id="csrf_token"[^>]*value="([^"]+)"',
        page.text,
    ).group(1)
    response = test_client.post(
        "/login",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "user_id": "u_cust",
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Login successful"
    assert response.cookies.get("auth_session") == "test-session-token"


def test_login_invalid_password(monkeypatch):
    monkeypatch.setattr(main, "authenticate_user", lambda uid, password: None)
    test_client = TestClient(main.app, base_url="https://testserver")
    page = test_client.get("/knowledge")

    csrf_token = re.search(
        r'id="csrf_token"[^>]*value="([^"]+)"',
        page.text,
    ).group(1)
    response = test_client.post(
        "/login",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "user_id": "u_cust",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid user ID or password"
    assert response.json()["error"]["code"] == "HTTP_ERROR"


def test_me_without_session():
    response = client.get("/me")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Not authenticated"
    assert response.json()["error"]["code"] == "HTTP_ERROR"


def test_logout_rejects_missing_csrf():
    test_client = TestClient(main.app)
    test_client.cookies.set("auth_session", "test-session-token")

    response = test_client.post("/logout")

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Invalid CSRF token"


def test_logout_rejects_invalid_csrf():
    test_client = TestClient(main.app)
    test_client.get("/knowledge")
    test_client.cookies.set("auth_session", "test-session-token")

    response = test_client.post(
        "/logout",
        headers={"X-CSRF-Token": "invalid-token"},
    )

    assert response.status_code == 403


def test_logout_success(monkeypatch):
    monkeypatch.setattr(main, "revoke_session", lambda token: True)

    test_client = TestClient(main.app, base_url="https://testserver")
    page = test_client.get("/knowledge")

    csrf_token = re.search(
        r'id="csrf_token"[^>]*value="([^"]+)"',
        page.text,
    ).group(1)

    test_client.cookies.set("auth_session", "test-session-token")

    response = test_client.post(
        "/logout",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Logout successful"
    assert "auth_session" not in response.cookies


def test_knowledge_page_requires_login(monkeypatch):
    monkeypatch.setattr(main, "get_session_user", lambda token: None)

    test_client = TestClient(main.app)
    response = test_client.get("/knowledge")

    assert response.status_code == 401
    assert "Login" in response.text


def test_knowledge_ask_rejects_invalid_csrf():
    test_client = TestClient(main.app)

    response = test_client.post(
        "/knowledge/ask",
        data={
            "question": "Which outages are active?",
            "csrf_token": "invalid-token",
        },
    )

    assert response.status_code == 403
    assert "session has expired" in response.text


def test_knowledge_ask_uses_authenticated_user(monkeypatch):
    user = namedtuple("User", ["user_id", "tenant_id", "role"])(
        "u_eng", "water_company_A", "engineer"
    )

    monkeypatch.setattr(main, "get_session_user", lambda token: user)

    seen = {}

    def fake_answer(**kwargs):
        seen.update(kwargs)
        return {"answer": "Test answer", "citations": []}

    monkeypatch.setattr(main, "generate_answer_with_citations", fake_answer)

    test_client = TestClient(
        main.app,
        base_url="https://testserver",
    )
    test_client.cookies.set("auth_session", "valid-token")

    page = test_client.get("/knowledge")
    assert page.status_code == 200

    import re

    csrf_token = re.search(
        r'name="csrf_token" value="([^"]+)"',
        page.text,
    ).group(1)

    response = test_client.post(
        "/knowledge/ask",
        data={
            "question": "Which outages are active?",
            "csrf_token": csrf_token,
        },
    )

    assert response.status_code == 200
    assert seen["tenant_id"] == "water_company_A"
    assert seen["user_role"] == "engineer"
