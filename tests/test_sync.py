"""Tests for the sync-account-history job queue (sync_worker.py + routes/sync.py)."""
import time
from unittest.mock import patch

import pytest

import sync_worker
from sync_worker import Job, STATUS_DONE, STATUS_FAILED, STATUS_QUEUED


def _make_job(job_id="test-job", account=52414311, password="secret", server="ICMarketsEU-Demo"):
    return Job(
        job_id=job_id,
        account=account,
        password=password,
        server=server,
        from_date="2026-07-01T00:00:00",
        to_date="2026-07-31T00:00:00",
        from_timestamp=1782950400,
        to_timestamp=1785542400,
        sequence=1,
    )


# ── process_sync_job (pure, no threads, no Flask) ──────────────────────────────

def test_process_sync_job_success(sample_deal, sample_history_order, sample_symbol_info):
    job = _make_job()
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=True),
        patch("MetaTrader5.history_deals_get", return_value=(sample_deal,)),
        patch("MetaTrader5.history_orders_get", return_value=(sample_history_order,)),
        patch("MetaTrader5.symbol_info", return_value=sample_symbol_info),
    ):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_DONE
    assert result.error is None
    assert result.deal_count == 1
    expected_deal = sample_deal._asdict()
    expected_deal["order_type"] = sample_history_order.type
    assert result.result == [expected_deal]
    assert result.symbols == {"EURUSD": 100000.0}
    assert result.password is None
    assert result.finished_at is not None


# ── order_type / symbols enrichment ─────────────────────────────────────────

def test_process_sync_job_enrichment_dedupes_symbol_lookups(sample_deal, sample_history_order, sample_symbol_info):
    """Two deals sharing a symbol resolve that symbol's contract size once."""
    other_deal = sample_deal._replace(ticket=88888, order=54321)
    job = _make_job()
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=True),
        patch("MetaTrader5.history_deals_get", return_value=(sample_deal, other_deal)),
        patch("MetaTrader5.history_orders_get", return_value=(sample_history_order,)) as mock_orders,
        patch("MetaTrader5.symbol_info", return_value=sample_symbol_info) as mock_symbol_info,
    ):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_DONE
    assert [deal["order_type"] for deal in result.result] == [sample_history_order.type] * 2
    assert result.symbols == {"EURUSD": 100000.0}
    assert mock_symbol_info.call_count == 1
    assert mock_orders.call_count == 2


def test_process_sync_job_enrichment_missing_order_leaves_order_type_none(sample_deal, sample_symbol_info):
    job = _make_job()
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=True),
        patch("MetaTrader5.history_deals_get", return_value=(sample_deal,)),
        patch("MetaTrader5.history_orders_get", return_value=None),
        patch("MetaTrader5.symbol_info", return_value=sample_symbol_info),
    ):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_DONE
    assert result.result[0]["order_type"] is None
    assert result.symbols == {"EURUSD": 100000.0}


def test_process_sync_job_enrichment_missing_symbol_info_leaves_contract_size_none(sample_deal, sample_history_order):
    job = _make_job()
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=True),
        patch("MetaTrader5.history_deals_get", return_value=(sample_deal,)),
        patch("MetaTrader5.history_orders_get", return_value=(sample_history_order,)),
        patch("MetaTrader5.symbol_info", return_value=None),
    ):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_DONE
    assert result.result[0]["order_type"] is not None
    assert result.symbols == {"EURUSD": None}


def test_process_sync_job_login_failure():
    job = _make_job()
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=False),
        patch("MetaTrader5.last_error", return_value=(-6, "Authorization failed")),
    ):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_FAILED
    assert "Login failed" in result.error
    assert result.error_code == -6
    assert result.result is None
    assert result.password is None


def test_process_sync_job_history_fetch_failure():
    job = _make_job()
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=True),
        patch("MetaTrader5.history_deals_get", return_value=None),
    ):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_FAILED
    assert result.error == "Failed to get deals history"
    assert result.password is None


def test_process_sync_job_exception_still_clears_password():
    job = _make_job()
    with patch("MetaTrader5.terminal_info", side_effect=RuntimeError("boom")):
        result = sync_worker.process_sync_job(job)

    assert result.status == STATUS_FAILED
    assert result.error == "Internal server error"
    assert result.password is None


# ── store / queue helpers (no real worker thread needed) ──────────────────────

def test_enqueue_and_get_job_view_round_trip():
    job_id = sync_worker.enqueue_sync_job(
        52414311, "secret", "ICMarketsEU-Demo",
        "2026-07-01T00:00:00", "2026-07-31T00:00:00",
        1782950400, 1785542400,
    )
    view = sync_worker.get_job_view(job_id)

    assert view is not None
    assert view["status"] == STATUS_QUEUED
    assert view["account"] == 52414311
    assert "password" not in view


def test_enqueue_burst_does_not_block():
    start = time.time()
    job_ids = [
        sync_worker.enqueue_sync_job(
            1, "pw", "SomeServer", "2026-07-01T00:00:00", "2026-07-31T00:00:00",
            1782950400, 1785542400,
        )
        for _ in range(500)
    ]
    elapsed = time.time() - start

    assert len(set(job_ids)) == 500
    assert elapsed < 2.0  # enqueue is O(1) per call; 500 calls should be near-instant


def test_get_job_view_unknown_job_returns_none():
    assert sync_worker.get_job_view("does-not-exist") is None


def test_cleanup_expired_jobs_removes_old_finished_jobs():
    job = _make_job(job_id="expiring-job")
    job.status = STATUS_DONE
    job.finished_at = 1000.0
    with sync_worker._store_lock:
        sync_worker._jobs["expiring-job"] = job

    with patch.dict("os.environ", {"SYNC_JOB_TTL_SECONDS": "60"}):
        with sync_worker._store_lock:
            sync_worker._cleanup_expired_jobs(now=1000.0 + 120)  # well past the 60s TTL

    assert "expiring-job" not in sync_worker._jobs


# ── routes ──────────────────────────────────────────────────────────────────

def test_sync_account_history_missing_params(client):
    resp = client.post("/sync_account_history")
    assert resp.status_code == 400


def test_sync_account_history_invalid_account(client):
    resp = client.post(
        "/sync_account_history",
        query_string={
            "account": "abc", "password": "pw", "server": "S",
            "from_date": "2026-07-01T00:00:00", "to_date": "2026-07-31T00:00:00",
        },
    )
    assert resp.status_code == 400


def test_sync_account_history_invalid_date(client):
    resp = client.post(
        "/sync_account_history",
        query_string={
            "account": "1", "password": "pw", "server": "S",
            "from_date": "not-a-date", "to_date": "2026-07-31T00:00:00",
        },
    )
    assert resp.status_code == 400


def test_sync_account_history_accepted_and_queued(client):
    resp = client.post(
        "/sync_account_history",
        query_string={
            "account": "52414311", "password": "pw", "server": "ICMarketsEU-Demo",
            "from_date": "2026-07-01T00:00:00", "to_date": "2026-07-31T00:00:00",
        },
    )
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["status"] == STATUS_QUEUED
    assert "job_id" in body
    assert "password" not in body


def test_sync_account_history_status_unknown_job(client):
    resp = client.get("/sync_account_history/does-not-exist")
    assert resp.status_code == 404


def test_sync_account_history_status_reflects_processed_job(
    client, sample_deal, sample_history_order, sample_symbol_info
):
    resp = client.post(
        "/sync_account_history",
        query_string={
            "account": "52414311", "password": "pw", "server": "ICMarketsEU-Demo",
            "from_date": "2026-07-01T00:00:00", "to_date": "2026-07-31T00:00:00",
        },
    )
    job_id = resp.get_json()["job_id"]

    # Process the job synchronously in the test thread — same function the
    # real worker calls, no need to wait on the real background thread.
    job = sync_worker._jobs[job_id]
    with (
        patch("MetaTrader5.terminal_info", return_value=object()),
        patch("MetaTrader5.login", return_value=True),
        patch("MetaTrader5.history_deals_get", return_value=(sample_deal,)),
        patch("MetaTrader5.history_orders_get", return_value=(sample_history_order,)),
        patch("MetaTrader5.symbol_info", return_value=sample_symbol_info),
    ):
        sync_worker.process_sync_job(job)

    status_resp = client.get(f"/sync_account_history/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.get_json()
    assert body["status"] == STATUS_DONE
    assert body["deal_count"] == 1
    expected_deal = sample_deal._asdict()
    expected_deal["order_type"] = sample_history_order.type
    assert body["result"] == [expected_deal]
    assert body["symbols"] == {"EURUSD": 100000.0}
