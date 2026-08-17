"""
Live integration tests — require a running MT5 terminal and network access.

Run with:
    pytest tests/test_live.py -v

Skipped automatically when the server is unreachable or MT5 terminal is not connected.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from dotenv import dotenv_values

BASE_URL = os.environ.get("MT5_TEST_BASE_URL", "http://127.0.0.1:8000")

DEMO_ACCOUNT  = 52414311
DEMO_PASSWORD = "77lmYn!!5@YRn$"
DEMO_SERVER   = "ICMarketsEU-Demo"

# From mt5_login_debug/testmt5.ipynb — a second (and third) broker/account
# pair used to prove /sync_account_history's mt5.initialize(login=...) call
# can log a fresh account into the shared process-wide MT5 session, not just
# the account this module happens to test everything else against.
NOTEBOOK_ACCOUNT  = 62134628
NOTEBOOK_PASSWORD = "lk3%qRemwx"
NOTEBOOK_SERVER   = "PepperstoneUK-Demo"

NOTEBOOK_ACCOUNT_2  = 591917355
NOTEBOOK_PASSWORD_2 = "!vkOnq7EvR"
NOTEBOOK_SERVER_2   = "FxPro-MT5 Demo"

_env = dotenv_values(Path(__file__).parent.parent / ".env")
_API_KEY = os.environ.get("API_KEY") or _env.get("API_KEY") or ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers():
    return {"X-API-Key": _API_KEY} if _API_KEY else {}


def _get(path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path, params=None):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _health():
    _, body = _get("/health")
    return body


def _run_sync_job(account, password, server, days=1, timeout=30):
    """
    POST /sync_account_history and poll until the job reaches a terminal
    status. This is now the *only* supported way to establish a logged-in
    MT5 session (raw /login is gone) — it drives mt5.initialize(login=...)
    on the single worker thread exactly like the real production path.
    Returns (post_status_code, final_job_view_or_post_body).
    """
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=days)
    status, body = _post("/sync_account_history", {
        "account":   account,
        "password":  password,
        "server":    server,
        "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    if status != 202:
        return status, body

    job_id = body["job_id"]
    deadline = time.time() + timeout
    final = None
    while time.time() < deadline:
        s, b = _get(f"/sync_account_history/{job_id}")
        assert s == 200
        if b["status"] in ("done", "failed"):
            final = b
            break
        time.sleep(0.5)
    assert final is not None, "sync job did not finish within timeout"
    return status, final


# ---------------------------------------------------------------------------
# Module-level skip guard
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def server_reachable():
    try:
        _, health = _get("/health")
    except Exception:
        pytest.skip("MT5 API server not reachable — skipping live tests")
    if not health.get("mt5_terminal_connected"):
        # Terminal may not have a session yet — establish one the only
        # supported way, via a sync job (mt5.initialize(login=...)).
        _, final = _run_sync_job(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER)
        if final.get("status") != "done":
            pytest.skip("MT5 terminal not connected and sync login failed — skipping live tests")


# ---------------------------------------------------------------------------
# Fixture: logged-in session for the whole module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def session():
    """Ensure the demo account is logged in (process-wide MT5 session) via
    /sync_account_history; yield the finished job view."""
    _, final = _run_sync_job(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER)
    assert final["status"] == "done", f"Login via sync job failed: {final.get('error')}"
    yield final


# ---------------------------------------------------------------------------
# 1. Symbol data
# ---------------------------------------------------------------------------

class TestSymbol:
    def test_symbol_info_tick(self, session):
        status, body = _get("/symbol_info_tick/EURUSD")
        assert status == 200
        for field in ("bid", "ask", "time"):
            assert field in body, f"Missing field: {field}"
        assert body["bid"] > 0
        assert body["ask"] > 0

    def test_symbol_info(self, session):
        status, body = _get("/symbol_info/EURUSD")
        assert status == 200
        assert body["name"] == "EURUSD"
        assert body["digits"] > 0

    def test_symbol_info_unknown(self, session):
        status, body = _get("/symbol_info/DOESNOTEXIST")
        assert status == 404


# ---------------------------------------------------------------------------
# 2. OHLC data
# ---------------------------------------------------------------------------

class TestData:
    def test_fetch_data_pos(self, session):
        status, body = _get("/fetch_data_pos", {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "num_bars": 10,
        })
        assert status == 200
        assert isinstance(body, list)
        assert len(body) == 10
        for field in ("time", "open", "high", "low", "close"):
            assert field in body[0], f"Missing field: {field}"

    def test_fetch_data_range(self, session):
        to_dt   = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=3)
        status, body = _get("/fetch_data_range", {
            "symbol":    "EURUSD",
            "timeframe": "H1",
            "start":     from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "end":       to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        assert status == 200
        assert isinstance(body, list)
        assert len(body) > 0


# ---------------------------------------------------------------------------
# 3. History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_history_deals_returns_list(self, session):
        to_dt   = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=30)
        status, body = _get("/history_deals_get", {
            "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        assert status == 200
        assert isinstance(body, list)

    def test_history_deals_fields(self, session):
        to_dt   = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=30)
        status, body = _get("/history_deals_get", {
            "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        assert status == 200
        if body:
            for field in ("ticket", "symbol", "volume", "price", "profit"):
                assert field in body[0], f"Missing field: {field}"

    def test_history_deals_wider_range(self, session):
        to_dt   = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=365)
        status, body = _get("/history_deals_get", {
            "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        assert status == 200
        assert isinstance(body, list)
        assert len(body) > 0, "Expected at least one deal in the past year"

    def test_history_deals_position_filter_is_exact(self, session):
        """position= filter must return ONLY deals for that position (not all deals)."""
        to_dt   = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=365)

        # Get all deals to find a real position_id
        status, body = _get("/history_deals_get", {
            "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        assert status == 200 and body
        trade_deals = [d for d in body if d.get("position_id") and d.get("symbol")]
        assert trade_deals, "No trade deals found in the past year"
        position_id = trade_deals[0]["position_id"]

        status2, filtered = _get("/history_deals_get", {
            "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "position":  position_id,
        })
        assert status2 == 200
        assert isinstance(filtered, list)
        assert len(filtered) > 0
        # Every returned deal must belong to the requested position
        assert all(d["position_id"] == position_id for d in filtered)
        # Must be a strict subset of all deals
        assert len(filtered) < len(body)

    def test_history_orders_get_by_ticket(self, session):
        """history_orders_get returns a list of orders when given a valid ticket."""
        # First get an order ticket that actually exists in history_orders_get
        to_dt   = datetime.now(timezone.utc)
        from_dt = datetime(2000, 1, 1, tzinfo=timezone.utc)
        status, all_orders = _get("/history_orders_get", {"ticket": 0})
        # ticket=0 acts as "no filter" — returns all orders in range
        assert status == 200 and isinstance(all_orders, list) and all_orders, (
            "Expected at least one order in full history"
        )
        order_ticket = all_orders[0]["ticket"]

        status2, orders = _get("/history_orders_get", {"ticket": order_ticket})
        assert status2 == 200
        assert isinstance(orders, list)
        assert len(orders) > 0


# ---------------------------------------------------------------------------
# 4. Positions
# ---------------------------------------------------------------------------

class TestPositions:
    def test_positions_total(self, session):
        status, body = _get("/positions_total")
        assert status == 200
        assert "total" in body
        assert isinstance(body["total"], int)

    def test_get_positions(self, session):
        status, body = _get("/get_positions")
        assert status == 200
        assert isinstance(body, list)


# ---------------------------------------------------------------------------
# 5. Sync account history (background job queue)
# ---------------------------------------------------------------------------

class TestSyncAccountHistory:
    def test_sync_history_end_to_end(self):
        # Real background worker, real terminal — _run_sync_job's poll loop
        # is the one place a bounded wait is appropriate for this feature.
        status, final = _run_sync_job(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER, days=30)
        assert status == 202
        assert final["status"] == "done", final.get("error")
        assert isinstance(final["result"], list)

    def test_sync_history_unknown_job_404(self):
        status, _ = _get("/sync_account_history/does-not-exist")
        assert status == 404

    def test_sync_history_never_rejects_under_burst(self):
        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=1)
        for _ in range(5):
            status, body = _post("/sync_account_history", {
                "account":   DEMO_ACCOUNT,
                "password":  DEMO_PASSWORD,
                "server":    DEMO_SERVER,
                "from_date": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "to_date":   to_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            assert status == 202
            assert body["status"] == "queued"


# ---------------------------------------------------------------------------
# 6. Login via /sync_account_history across every known credential set
# ---------------------------------------------------------------------------

class TestSyncAccountHistoryCredentials:
    """
    Exercise mt5.initialize(login=...) — the single-call login this module
    replaced mt5.initialize() + mt5.login() with — against every credential
    set on hand: the demo account used throughout this file, plus both
    accounts from mt5_login_debug/testmt5.ipynb (a different broker each).
    Confirms the new login path isn't accidentally tied to one broker/server
    and that it can swap the process-wide MT5 session between accounts.
    """

    @pytest.mark.parametrize(
        "account,password,server",
        [
            (DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER),
            (NOTEBOOK_ACCOUNT, NOTEBOOK_PASSWORD, NOTEBOOK_SERVER),
            (NOTEBOOK_ACCOUNT_2, NOTEBOOK_PASSWORD_2, NOTEBOOK_SERVER_2),
        ],
        ids=["icmarkets-demo", "pepperstone-demo", "fxpro-demo"],
    )
    def test_sync_history_logs_in_and_reflects_in_health(self, account, password, server):
        status, final = _run_sync_job(account, password, server, days=7)
        assert status == 202
        assert final["status"] == "done", final.get("error")
        assert isinstance(final["result"], list)

        h = _health()
        assert h["mt5_terminal_connected"] is True
        assert h["mt5_account_logged_in"] is True
        assert h["mt5_account"] == account

    def test_sync_history_switches_account_between_jobs(self):
        """Two back-to-back jobs for different accounts must each end up
        logged into their own account — proving initialize(login=) actually
        re-authorizes rather than silently reusing a stale session."""
        _, first = _run_sync_job(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER, days=7)
        assert first["status"] == "done", first.get("error")
        assert _health()["mt5_account"] == DEMO_ACCOUNT

        _, second = _run_sync_job(NOTEBOOK_ACCOUNT, NOTEBOOK_PASSWORD, NOTEBOOK_SERVER, days=7)
        assert second["status"] == "done", second.get("error")
        assert _health()["mt5_account"] == NOTEBOOK_ACCOUNT

        # Leave the session back on the demo account for any later test run.
        _, restore = _run_sync_job(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER, days=1)
        assert restore["status"] == "done", restore.get("error")
