"""
Shared pytest fixtures for MT5 API tests.

All tests run without a live MetaTrader5 terminal.  MT5 function calls are
mocked at the MetaTrader5 module level; the real package still provides its
integer constants (TIMEFRAME_*, TRADE_RETCODE_*, …) at import time.
"""
from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Named-tuples that mirror MT5 return types (each has ._asdict())
# ---------------------------------------------------------------------------

Tick = namedtuple(
    "Tick",
    ["time", "bid", "ask", "last", "volume", "time_msc", "flags", "volume_real"],
)

# MT5 OrderSendResult
TradeResult = namedtuple(
    "TradeResult",
    [
        "retcode", "deal", "order", "volume", "price",
        "bid", "ask", "comment", "request_id", "retcode_external", "request",
    ],
)

Position = namedtuple(
    "Position",
    [
        "ticket", "time", "time_msc", "time_update", "time_update_msc",
        "type", "magic", "identifier", "reason",
        "volume", "price_open", "sl", "tp", "price_current",
        "swap", "profit", "symbol", "comment", "external_id",
    ],
)

Deal = namedtuple(
    "Deal",
    [
        "ticket", "order", "time", "time_msc", "type", "entry",
        "magic", "reason", "position_id", "volume", "price",
        "commission", "swap", "profit", "fee",
        "symbol", "comment", "external_id",
    ],
)

HistoryOrder = namedtuple(
    "HistoryOrder",
    [
        "ticket", "time_setup", "time_setup_msc", "time_done", "time_done_msc",
        "time_expiration", "type", "type_time", "type_filling", "state",
        "magic", "position_id", "position_by_id", "reason",
        "volume_initial", "volume_current",
        "price_open", "sl", "tp", "price_current", "price_stoplimit",
        "symbol", "comment", "external_id",
    ],
)

# MT5 TRADE_RETCODE_DONE integer value
RETCODE_DONE = 10009
RETCODE_ERROR = 10011


# ---------------------------------------------------------------------------
# Session-scoped Flask app
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    from app import app as flask_app
    flask_app.config.update({"TESTING": True})
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Base MT5 mock – always patched so import-time calls never touch a terminal
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_mt5_base():
    """Patch initialize() and last_error() for every test automatically.
    Also clears API_KEY so existing tests don't need to send the header —
    test_auth.py sets it explicitly per test via patch.dict(os.environ)."""
    import os
    os.environ.pop("API_KEY", None)
    with (
        patch("MetaTrader5.initialize", return_value=True),
        patch("MetaTrader5.last_error", return_value=(0, "No error")),
    ):
        yield


# ---------------------------------------------------------------------------
# Reusable data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_tick():
    return Tick(
        time=1700000000,
        bid=1.10000,
        ask=1.10020,
        last=1.10010,
        volume=100,
        time_msc=1700000000000,
        flags=0,
        volume_real=0.0,
    )


@pytest.fixture()
def sample_symbol_info():
    mock = MagicMock()
    mock._asdict.return_value = {
        "name": "EURUSD",
        "path": "Forex\\EURUSD",
        "description": "Euro vs US Dollar",
        "digits": 5,
        "spread": 1,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_mode": 4,
        "bid": 1.10000,
        "ask": 1.10020,
    }
    return mock


@pytest.fixture()
def sample_rates():
    return [
        {
            "time": 1700000000,
            "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005,
            "tick_volume": 100, "spread": 1, "real_volume": 0,
        },
        {
            "time": 1700003600,
            "open": 1.1005, "high": 1.1015, "low": 1.0995, "close": 1.1010,
            "tick_volume": 150, "spread": 1, "real_volume": 0,
        },
    ]


@pytest.fixture()
def sample_position():
    return Position(
        ticket=12345,
        time=1700000000, time_msc=1700000000000,
        time_update=1700000000, time_update_msc=1700000000000,
        type=0,  # ORDER_TYPE_BUY
        magic=1000, identifier=12345, reason=0,
        volume=0.1, price_open=1.10000, sl=1.09500, tp=1.11000,
        price_current=1.10050, swap=0.0, profit=5.0,
        symbol="EURUSD", comment="", external_id="",
    )


@pytest.fixture()
def sample_trade_result():
    return TradeResult(
        retcode=RETCODE_DONE,
        deal=67890, order=67890,
        volume=0.1, price=1.10020,
        bid=1.10000, ask=1.10020,
        comment="Request executed",
        request_id=1, retcode_external=0, request=None,
    )


@pytest.fixture()
def sample_deal():
    return Deal(
        ticket=99999, order=12345,
        time=1700000000, time_msc=1700000000000,
        type=0, entry=0,
        magic=1000, reason=0, position_id=12345,
        volume=0.1, price=1.10000,
        commission=-0.5, swap=0.0, profit=5.0, fee=0.0,
        symbol="EURUSD", comment="", external_id="",
    )


@pytest.fixture()
def sample_history_order():
    return HistoryOrder(
        ticket=12345,
        time_setup=1700000000, time_setup_msc=1700000000000,
        time_done=1700000010, time_done_msc=1700000010000,
        time_expiration=0,
        type=0, type_time=0, type_filling=1, state=3,
        magic=1000, position_id=12345, position_by_id=0, reason=0,
        volume_initial=0.1, volume_current=0.0,
        price_open=1.10020, sl=1.09500, tp=1.11000,
        price_current=1.10020, price_stoplimit=0.0,
        symbol="EURUSD", comment="", external_id="",
    )
