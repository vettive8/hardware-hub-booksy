from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def member_headers(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "member@booksy.com", "password": "Member123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

