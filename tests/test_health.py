"""Tests for GET /health"""
from unittest.mock import patch


def test_health_mt5_initialized(client):
    with patch("MetaTrader5.initialize", return_value=True):
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["mt5_connected"] is True
    assert data["mt5_initialized"] is True


def test_health_mt5_not_initialized(client):
    with patch("MetaTrader5.initialize", return_value=False):
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["mt5_connected"] is True   # module is importable
    assert data["mt5_initialized"] is False
