"""Tests for X-API-Key authentication middleware."""
import os
from unittest.mock import patch

TEST_KEY = "test-secret-key-1234"


def test_no_key_configured_allows_all(client):
    """When API_KEY is not set, all requests pass through."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("API_KEY", None)
        resp = client.get("/health")
    assert resp.status_code == 200


def test_missing_header_returns_401(client):
    with patch.dict(os.environ, {"API_KEY": TEST_KEY}):
        resp = client.get("/last_error")
    assert resp.status_code == 401
    assert "X-API-Key" in resp.get_json()["error"]


def test_wrong_key_returns_403(client):
    with patch.dict(os.environ, {"API_KEY": TEST_KEY}):
        resp = client.get("/last_error", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403
    assert "Invalid" in resp.get_json()["error"]


def test_correct_key_allows_request(client):
    with patch.dict(os.environ, {"API_KEY": TEST_KEY}):
        resp = client.get("/last_error", headers={"X-API-Key": TEST_KEY})
    assert resp.status_code == 200


def test_health_accessible_without_key(client):
    """Health endpoint must be reachable without auth for monitoring tools."""
    with patch.dict(os.environ, {"API_KEY": TEST_KEY}):
        resp = client.get("/health")
    assert resp.status_code == 200


def test_swagger_ui_accessible_without_key(client):
    """Swagger UI must remain reachable without auth."""
    with patch.dict(os.environ, {"API_KEY": TEST_KEY}):
        resp = client.get("/apidocs/")
    assert resp.status_code == 200


def test_key_required_on_api_endpoints(client):
    """Spot-check a non-health endpoint also requires the key."""
    with patch.dict(os.environ, {"API_KEY": TEST_KEY}):
        resp = client.get("/last_error")
    assert resp.status_code == 401
