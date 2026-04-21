"""Tests for GET /health"""
from unittest.mock import MagicMock, patch


def test_health_terminal_connected(client):
    mock_terminal = MagicMock()
    mock_account = MagicMock()
    mock_account.login = 12345
    with (
        patch("MetaTrader5.terminal_info", return_value=mock_terminal),
        patch("MetaTrader5.account_info", return_value=mock_account),
    ):
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["mt5_terminal_connected"] is True
    assert data["mt5_account_logged_in"] is True
    assert data["mt5_account"] == 12345


def test_health_terminal_not_connected(client):
    with (
        patch("MetaTrader5.terminal_info", return_value=None),
        patch("MetaTrader5.account_info", return_value=None),
    ):
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["mt5_terminal_connected"] is False
    assert data["mt5_account_logged_in"] is False
    assert data["mt5_account"] is None
