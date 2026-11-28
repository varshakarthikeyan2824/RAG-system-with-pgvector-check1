"""One test per fixed flaw. Each of these attacks worked against the original app.py."""
import base64
import pickle
import socket
from pathlib import Path

from fastapi.testclient import TestClient

import app as shop
from app import app

client = TestClient(app)


def auth(name, password):
    token = client.post("/login", json={"name": name, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


ADMIN = lambda: auth("alice", "alice123")  # noqa: E731
USER = lambda: auth("bob", "bob123")  # noqa: E731


def test_bad_password_gets_no_token():
    assert client.post("/login", json={"name": "alice", "password": "wrong"}).json() == {"ok": False, "token": None}


def test_token_is_random_not_base64_of_the_name():
    token = client.post("/login", json={"name": "alice", "password": "alice123"}).json()["token"]
    assert token != base64.b64encode(b"alice").decode()
    forged = {"Authorization": "Bearer " + base64.b64encode(b"alice").decode()}
    assert client.get("/admin/users", headers=forged).status_code == 401


# Fix 1: pickle
def test_import_rejects_a_pickle_payload():
    blob = base64.b64encode(pickle.dumps({"a": 1})).decode()
    assert client.post("/import", json=blob, headers=ADMIN()).status_code == 422


def test_import_accepts_typed_json_from_admin_only():
    body = [{"user_id": 1, "item": "lamp", "total": 9.5}]
    assert client.post("/import", json=body, headers=ADMIN()).json() == {"loaded": body}
    assert client.post("/import", json=body, headers=USER()).status_code == 403


# Fix 2: SQL injection
def test_search_is_not_injectable():
    payload = "zzz' UNION SELECT id, password, email FROM users --"
    assert client.get("/search", params={"q": payload}, headers=USER()).json() == {"results": []}


# Fix 3: missing authentication and access control
def test_admin_users_needs_login_and_admin_role():
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/users", headers=USER()).status_code == 403
    rows = client.get("/admin/users", headers=ADMIN()).json()
    assert len(rows) == 2 and all(len(row) == 4 for row in rows)  # id, name, email, role: no password hash


def test_orders_are_private_to_their_owner():
    assert client.get("/orders/1").status_code == 401
    assert client.get("/orders/2", headers=USER()).json()["item"] == "chair"
    assert client.get("/orders/1", headers=USER()).status_code == 404  # alice's order
    assert client.get("/orders/1", headers=ADMIN()).json()["item"] == "desk"


# Fix 4: secrets
def test_no_secret_values_in_the_source():
    source = Path(shop.__file__).read_text()
    assert "sk_live" not in source and "admin-token" not in source


def test_llm_key_is_sent_in_a_header_not_the_body(monkeypatch):
    seen = {}

    class Fake:
        def json(self):
            return {"text": "hi"}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return Fake()

    monkeypatch.setattr(shop.httpx, "post", fake_post)
    assert client.post("/ask", json="hello", headers=USER()).json() == {"answer": "hi"}
    assert "api_key" not in seen["json"]
    assert seen["headers"]["Authorization"] == f"Bearer {shop.LLM_API_KEY}"
    assert seen["timeout"]


# Fix 5: SSRF
def test_fetch_blocks_internal_and_unlisted_targets(monkeypatch):
    monkeypatch.setattr(shop, "ALLOWED_FETCH_HOSTS", {"api.partner.example"})
    for url in ["http://169.254.169.254/latest/meta-data", "https://localhost/", "https://other.example/",
                "http://api.partner.example/"]:
        assert client.get("/fetch", params={"url": url}, headers=USER()).status_code == 400, url


def test_fetch_blocks_an_allowed_name_that_resolves_to_a_private_address(monkeypatch):
    monkeypatch.setattr(shop, "ALLOWED_FETCH_HOSTS", {"api.partner.example"})
    monkeypatch.setattr(shop.socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 0, 0, "", ("10.0.0.5", 443))])
    assert client.get("/fetch", params={"url": "https://api.partner.example/"}, headers=USER()).status_code == 400


def test_fetch_allows_a_listed_public_host(monkeypatch):
    monkeypatch.setattr(shop, "ALLOWED_FETCH_HOSTS", {"api.partner.example"})
    monkeypatch.setattr(shop.socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 0, 0, "", ("93.184.216.34", 443))])

    class Fake:
        text = "ok"

    monkeypatch.setattr(shop.httpx, "get", lambda url, **kw: Fake())
    assert client.get("/fetch", params={"url": "https://api.partner.example/x"}, headers=USER()).json() == {"body": "ok"}
