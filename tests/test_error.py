"""Tests for /last_error and /last_error_str"""
from unittest.mock import patch


def test_last_error_success(client):
    with patch("MetaTrader5.last_error", return_value=(10006, "Request rejected")):
        resp = client.get("/last_error")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["error_code"] == 10006
    assert data["error_message"] == "Request rejected"


def test_last_error_no_error(client):
    with patch("MetaTrader5.last_error", return_value=(0, "No error")):
        resp = client.get("/last_error")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["error_code"] == 0


def test_last_error_str_success(client):
    with patch("MetaTrader5.last_error", return_value=(10006, "Request rejected")):
        resp = client.get("/last_error_str")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["error_message"] == "Request rejected"


def test_last_error_str_no_error(client):
    with patch("MetaTrader5.last_error", return_value=(0, "No error")):
        resp = client.get("/last_error_str")
    assert resp.status_code == 200
    assert resp.get_json()["error_message"] == "No error"
