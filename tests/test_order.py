"""Tests for POST /order"""
from unittest.mock import MagicMock, patch

import MetaTrader5 as mt5

from tests.conftest import RETCODE_DONE, RETCODE_ERROR


def _buy_payload(**kwargs):
    base = {
        "symbol": "EURUSD",
        "volume": 0.1,
        "type": mt5.ORDER_TYPE_BUY,
    }
    base.update(kwargs)
    return base


def test_order_buy_success(client, sample_tick, sample_trade_result):
    with (
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=sample_trade_result),
    ):
        resp = client.post("/order", json=_buy_payload())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["message"] == "Order executed successfully"
    assert data["result"]["retcode"] == RETCODE_DONE


def test_order_sell_success(client, sample_tick, sample_trade_result):
    with (
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=sample_trade_result),
    ):
        resp = client.post("/order", json={
            "symbol": "EURUSD",
            "volume": 0.1,
            "type": mt5.ORDER_TYPE_SELL,
        })
    assert resp.status_code == 200


def test_order_missing_required_fields(client):
    resp = client.post("/order", json={"symbol": "EURUSD"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_order_no_body(client):
    resp = client.post("/order")
    assert resp.status_code == 400


def test_order_invalid_type(client, sample_tick):
    with patch("MetaTrader5.symbol_info_tick", return_value=sample_tick):
        resp = client.post("/order", json={
            "symbol": "EURUSD",
            "volume": 0.1,
            "type": 99,  # not BUY or SELL
        })
    assert resp.status_code == 400


def test_order_no_tick(client):
    with patch("MetaTrader5.symbol_info_tick", return_value=None):
        resp = client.post("/order", json=_buy_payload())
    assert resp.status_code == 400
    assert "Failed to get symbol price" in resp.get_json()["error"]


def test_order_mt5_failure(client, sample_tick):
    bad_result = MagicMock()
    bad_result.retcode = RETCODE_ERROR
    bad_result.comment = "Not enough money"
    bad_result._asdict.return_value = {"retcode": RETCODE_ERROR, "comment": "Not enough money"}
    with (
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=bad_result),
        patch("MetaTrader5.last_error", return_value=(RETCODE_ERROR, "Not enough money")),
    ):
        resp = client.post("/order", json=_buy_payload())
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_order_with_sl_tp(client, sample_tick, sample_trade_result):
    with (
        patch("MetaTrader5.symbol_info_tick", return_value=sample_tick),
        patch("MetaTrader5.order_send", return_value=sample_trade_result),
    ):
        resp = client.post("/order", json=_buy_payload(sl=1.0950, tp=1.1100))
    assert resp.status_code == 200
