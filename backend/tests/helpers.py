from typing import Any

from fastapi.testclient import TestClient

DEFAULT_PASSWORD = "correct-horse"


def register_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "email": "taro@example.com",
        "password": DEFAULT_PASSWORD,
        "attribute": "working",
        "agreed_to_terms": True,
    }
    body.update(overrides)
    return body


def register(client: TestClient, **overrides: Any):
    return client.post("/api/v1/auth/register", json=register_body(**overrides))


def field_errors(response) -> list[dict[str, Any]]:
    return response.json()["error"]["fields"]
