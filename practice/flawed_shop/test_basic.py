from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def _token(name="alice", password="alice123") -> str:
    return client.post("/login", json={"name": name, "password": password}).json()["token"]


def test_login_works():
    assert client.post("/login", json={"name": "alice", "password": "alice123"}).json()["ok"] is True


def test_search_works():
    headers = {"Authorization": f"Bearer {_token()}"}
    assert client.get("/search", params={"q": "ali"}, headers=headers).json()["results"]
