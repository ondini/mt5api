"""Tests for history endpoints."""
from unittest.mock import patch


# ── /get_deal_from_ticket ─────────────────────────────────────────────────────

def test_get_deal_from_ticket_success(client, sample_deal):
    with patch("MetaTrader5.history_deals_get", return_value=(sample_deal,)):
        resp = client.get("/get_deal_from_ticket?ticket=12345")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ticket"] == 12345
    assert data["symbol"] == "EURUSD"


def test_get_deal_from_ticket_missing_param(client):
    resp = client.get("/get_deal_from_ticket")
    assert resp.status_code == 400


def test_get_deal_from_ticket_invalid_type(client):
    resp = client.get("/get_deal_from_ticket?ticket=abc")
    assert resp.status_code == 400


def test_get_deal_from_ticket_not_found(client):
    with patch("MetaTrader5.history_deals_get", return_value=None):
        resp = client.get("/get_deal_from_ticket?ticket=99999")
    # lib.get_deal_from_ticket returns None → 404
    assert resp.status_code == 404


# ── /get_order_from_ticket ────────────────────────────────────────────────────

def test_get_order_from_ticket_success(client, sample_history_order):
    with patch("MetaTrader5.history_orders_get", return_value=(sample_history_order,)):
        resp = client.get("/get_order_from_ticket?ticket=12345")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ticket"] == 12345
    assert data["symbol"] == "EURUSD"


def test_get_order_from_ticket_missing_param(client):
    resp = client.get("/get_order_from_ticket")
    assert resp.status_code == 400


def test_get_order_from_ticket_invalid_type(client):
    resp = client.get("/get_order_from_ticket?ticket=abc")
    assert resp.status_code == 400


def test_get_order_from_ticket_not_found(client):
    with patch("MetaTrader5.history_orders_get", return_value=None):
        resp = client.get("/get_order_from_ticket?ticket=99999")
    assert resp.status_code == 404


# ── /history_deals_get ────────────────────────────────────────────────────────

_DEAL_PARAMS = (
    "?from_date=2023-11-14T00:00:00"
    "&to_date=2023-11-14T01:00:00"
    "&position=12345"
)


def test_history_deals_get_success(client, sample_deal):
    with patch("MetaTrader5.history_deals_get", return_value=(sample_deal,)):
        resp = client.get("/history_deals_get" + _DEAL_PARAMS)
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "EURUSD"


def test_history_deals_get_missing_params(client):
    resp = client.get("/history_deals_get?from_date=2023-11-14T00:00:00")
    assert resp.status_code == 400


def test_history_deals_get_invalid_date(client):
    resp = client.get(
        "/history_deals_get"
        "?from_date=not-a-date&to_date=also-not&position=12345"
    )
    assert resp.status_code == 400


def test_history_deals_get_not_found(client):
    with patch("MetaTrader5.history_deals_get", return_value=None):
        resp = client.get("/history_deals_get" + _DEAL_PARAMS)
    assert resp.status_code == 404


# ── /history_orders_get ───────────────────────────────────────────────────────

def test_history_orders_get_success(client, sample_history_order):
    with patch("MetaTrader5.history_orders_get", return_value=(sample_history_order,)):
        resp = client.get("/history_orders_get?ticket=12345")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert data[0]["ticket"] == 12345


def test_history_orders_get_missing_param(client):
    resp = client.get("/history_orders_get")
    assert resp.status_code == 400


def test_history_orders_get_invalid_type(client):
    resp = client.get("/history_orders_get?ticket=abc")
    assert resp.status_code == 400


def test_history_orders_get_not_found(client):
    with patch("MetaTrader5.history_orders_get", return_value=None):
        resp = client.get("/history_orders_get?ticket=99999")
    assert resp.status_code == 404
