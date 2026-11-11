from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers.get("X-Request-ID")


def test_ask_success(monkeypatch):
    def fake_generate_answer(**kwargs):
        return "There are two active outages."

    monkeypatch.setattr(main, "generate_answer", fake_generate_answer)

    response = client.post(
        "/ask",
        json={
            "question": "Which outages are active?",
            "tenant_id": "water_company_A",
            "user_role": "engineer",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "There are two active outages."


def test_validation_error():
    response = client.post(
        "/ask",
        json={"question": "Which outages are active?"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_unexpected_error(monkeypatch):
    def fake_generate_answer(**kwargs):
        raise RuntimeError("Sensitive internal database details")

    monkeypatch.setattr(main, "generate_answer", fake_generate_answer)

    test_client = TestClient(
        main.app,
        raise_server_exceptions=False,
    )

    response = test_client.post(
        "/ask",
        json={
            "question": "Test error",
            "tenant_id": "water_company_A",
            "user_role": "engineer",
        },
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "Sensitive internal database details" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
