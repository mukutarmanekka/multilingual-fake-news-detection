import pytest
from starlette.testclient import TestClient
from src.main import app


def test_api_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pipeline"


def test_api_recent_claims():
    client = TestClient(app)
    response = client.get("/api/claims/recent")
    assert response.status_code == 200
    data = response.json()
    assert "claims" in data
    assert "total" in data
