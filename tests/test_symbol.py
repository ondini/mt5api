"""Tests for /symbol_info_tick/<symbol> and /symbol_info/<symbol>"""
from unittest.mock import patch


# ── symbol_info_tick ─────────────────────────────────────────────────────────

def test_symbol_info_tick_success(client, sample_tick):
    with patch("MetaTrader5.symbol_info_tick", return_value=sample_tick):
        resp = client.get("/symbol_info_tick/EURUSD")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["bid"] == 1.10000
    assert data["ask"] == 1.10020
    assert data["volume"] == 100


def test_symbol_info_tick_not_found(client):
    with patch("MetaTrader5.symbol_info_tick", return_value=None):
        resp = client.get("/symbol_info_tick/INVALID")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


# ── symbol_info ───────────────────────────────────────────────────────────────

def test_symbol_info_success(client, sample_symbol_info):
    with patch("MetaTrader5.symbol_info", return_value=sample_symbol_info):
        resp = client.get("/symbol_info/EURUSD")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "EURUSD"
    assert data["digits"] == 5


def test_symbol_info_not_found(client):
    with patch("MetaTrader5.symbol_info", return_value=None):
        resp = client.get("/symbol_info/INVALID")
    assert resp.status_code == 404
    assert "error" in resp.get_json()
