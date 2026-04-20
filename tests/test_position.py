"""Tests for position endpoints."""
import json
from unittest.mock import MagicMock, patch

from tests.conftest import RETCODE_DONE, RETCODE_ERROR


# ── /positions_total ──────────────────────────────────────────────────────────

def test_positions_total_success(client):
    with patch("MetaTrader5.positions_total", return_value=3):
        resp = client.get("/positions_total")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 3


def test_positions_total_failure(client):
    with patch("MetaTrader5.positions_total", return_value=None):
        resp = client.get("/positions_total")
    assert resp.status_code == 400


# ── /get_positions ────────────────────────────────────────────────────────────

def test_get_positions_empty(client):
    with (
        patch("MetaTrader5.initialize", return_value=True),
        patch("MetaTrader5.positions_total", return_value=0),
    ):
        resp = client.get("/get_positions")
    assert resp.status_code == 200
    assert resp.get_json()["positions"] == []


def test_get_positions_with_data(client, sample_position):
    with (
        patch("MetaTrader5.initialize", return_value=True),
        patch("MetaTrader5.positions_total", return_value=1),
        patch("MetaTrader5.positions_get", return_value=(sample_position,)),
    ):
        resp = client.get("/get_positions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert data[0]["ticket"] == 12345
    assert data[0]["symbol"] == "EURUSD"


def test_get_positions_with_magic_filter(client, sample_position):
    with (
        patch("MetaTrader5.initialize", return_value=True),
        patch("MetaTrader5.positions_total", return_value=1),
        patch("MetaTrader5.positions_get", return_value=(sample_position,)),
    ):
        resp = client.get("/get_positions?magic=1000")
    assert resp.status_code == 200
    data = resp.get_json()
    assert all(p["magic"] == 1000 for p in data)


# ── /close_position ───────────────────────────────────────────────────────────

def test_close_position_success(client, sample_tick, sample_trade_result):
    with (
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=sample_trade_result),
    ):
        resp = client.post(
            "/close_position",
            json={
                "position": {
                    "type": 0,
                    "ticket": 12345,
                    "symbol": "EURUSD",
                    "volume": 0.1,
                }
            },
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Position closed successfully"
    assert data["result"]["retcode"] == RETCODE_DONE


def test_close_position_missing_body(client):
    resp = client.post("/close_position", json={})
    assert resp.status_code == 400


def test_close_position_mt5_failure(client, sample_tick):
    bad_result = MagicMock()
    bad_result.retcode = RETCODE_ERROR
    bad_result.comment = "Trade error"
    with (
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=bad_result),
    ):
        resp = client.post(
            "/close_position",
            json={
                "position": {
                    "type": 0,
                    "ticket": 12345,
                    "symbol": "EURUSD",
                    "volume": 0.1,
                }
            },
        )
    assert resp.status_code == 400


# ── /close_all_positions ──────────────────────────────────────────────────────

def test_close_all_positions_no_open(client):
    with patch("MetaTrader5.positions_total", return_value=0):
        resp = client.post("/close_all_positions", json={})
    assert resp.status_code == 200


def test_close_all_positions_success(client, sample_position, sample_tick, sample_trade_result):
    with (
        patch("MetaTrader5.positions_total", return_value=1),
        patch("MetaTrader5.positions_get", return_value=(sample_position,)),
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=sample_trade_result),
    ):
        resp = client.post("/close_all_positions", json={"order_type": "all"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "Closed" in data["message"]


# ── /modify_sl_tp ─────────────────────────────────────────────────────────────

def test_modify_sl_tp_success(client, sample_trade_result):
    with patch("MetaTrader5.order_send", return_value=sample_trade_result):
        resp = client.post(
            "/modify_sl_tp",
            json={"position": 12345, "sl": 1.0950, "tp": 1.1100},
        )
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "SL/TP modified successfully"


def test_modify_sl_tp_missing_position(client):
    resp = client.post("/modify_sl_tp", json={"sl": 1.0950})
    assert resp.status_code == 400


def test_modify_sl_tp_mt5_failure(client):
    bad_result = MagicMock()
    bad_result.retcode = RETCODE_ERROR
    bad_result.comment = "Modification failed"
    with patch("MetaTrader5.order_send", return_value=bad_result):
        resp = client.post(
            "/modify_sl_tp",
            json={"position": 12345, "sl": 1.0950, "tp": 1.1100},
        )
    assert resp.status_code == 400
