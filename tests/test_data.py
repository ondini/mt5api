"""Tests for /fetch_data_pos and /fetch_data_range"""
from unittest.mock import patch


# ── fetch_data_pos ────────────────────────────────────────────────────────────

def test_fetch_data_pos_success(client, sample_rates):
    with patch("MetaTrader5.copy_rates_from_pos", return_value=sample_rates):
        resp = client.get("/fetch_data_pos?symbol=EURUSD&timeframe=M1&num_bars=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert "open" in data[0]
    assert "close" in data[0]


def test_fetch_data_pos_missing_symbol(client):
    resp = client.get("/fetch_data_pos?timeframe=M1&num_bars=10")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_fetch_data_pos_invalid_timeframe(client):
    resp = client.get("/fetch_data_pos?symbol=EURUSD&timeframe=INVALID")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_fetch_data_pos_no_data(client):
    with patch("MetaTrader5.copy_rates_from_pos", return_value=None):
        resp = client.get("/fetch_data_pos?symbol=EURUSD&timeframe=M1")
    assert resp.status_code == 404


def test_fetch_data_pos_defaults(client, sample_rates):
    """num_bars and timeframe have defaults — symbol alone is enough."""
    with patch("MetaTrader5.copy_rates_from_pos", return_value=sample_rates):
        resp = client.get("/fetch_data_pos?symbol=EURUSD")
    assert resp.status_code == 200


# ── fetch_data_range ──────────────────────────────────────────────────────────

def test_fetch_data_range_success(client, sample_rates):
    with patch("MetaTrader5.copy_rates_range", return_value=sample_rates):
        resp = client.get(
            "/fetch_data_range"
            "?symbol=EURUSD&timeframe=H1"
            "&start=2023-11-14T00:00:00"
            "&end=2023-11-14T01:00:00"
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_fetch_data_range_missing_params(client):
    resp = client.get("/fetch_data_range?symbol=EURUSD")
    assert resp.status_code == 400


def test_fetch_data_range_no_data(client):
    with patch("MetaTrader5.copy_rates_range", return_value=None):
        resp = client.get(
            "/fetch_data_range"
            "?symbol=EURUSD&timeframe=M1"
            "&start=2023-11-14T00:00:00"
            "&end=2023-11-14T01:00:00"
        )
    assert resp.status_code == 404
