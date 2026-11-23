from collections import namedtuple
from fastapi.testclient import TestClient

from src import main

client = TestClient(main.app)
FakeUser = namedtuple("FakeUser", ["tenant_id", "role"])
KEY = {"x-service-key": "test-key"}


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers.get("X-Request-ID")


def test_ask_success(monkeypatch):
    monkeypatch.setattr(main, "lookup_user",
                        lambda uid: FakeUser("water_company_A", "engineer"))
    monkeypatch.setattr(main, "generate_answer_with_citations",
                        lambda **kw: {"answer": "Two active outages.", "citations": []})

    response = client.post("/ask", headers=KEY,
        json={"question": "Which outages are active?", "user_id": "u_eng"})
    
    assert response.status_code == 200
    assert response.json()["answer"] == "Two active outages."


def test_ask_without_key_is_refused():
    response = client.post("/ask",
        json={"question": "Which outages are active?", "user_id": "u_eng"})
    assert response.status_code == 401


def test_ask_unknown_user_is_refused(monkeypatch):
    monkeypatch.setattr(main, "lookup_user", lambda uid: None)
    response = client.post("/ask", headers=KEY,
        json={"question": "Which outages are active?", "user_id": "nobody"})
    assert response.status_code == 403


def test_client_cannot_choose_its_own_role(monkeypatch):
    seen = {}
    monkeypatch.setattr(main, "lookup_user",
                        lambda uid: FakeUser("water_company_A", "customer"))
    def fake(**kw):
        seen.update(kw)
        return {"answer": "x", "citations": []}
    monkeypatch.setattr(main, "generate_answer_with_citations", fake)

    client.post("/ask", headers=KEY, json={
        "question": "Who is on crew duty?", "user_id": "u_cust",
        "user_role": "engineer"})          # an attacker's extra field

    assert seen["user_role"] == "customer"   # the server's value wins


def test_validation_error():
    response = client.post("/ask", headers=KEY,
        json={"question": "Which outages are active?"})   # user_id missing
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_unexpected_error(monkeypatch):
    monkeypatch.setattr(main, "lookup_user",
                        lambda uid: FakeUser("water_company_A", "engineer"))
    def boom(**kw):
        raise RuntimeError("Sensitive internal database details")
    monkeypatch.setattr(main, "generate_answer_with_citations", boom)

    test_client = TestClient(main.app, raise_server_exceptions=False)
    response = test_client.post("/ask", headers=KEY,
        json={"question": "Test error", "user_id": "u_eng"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "Sensitive internal database details" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]