"""
Background job queue for POST /sync_account_history.

MetaTrader5 has exactly one global, process-wide session — one terminal, one
"currently logged in account" at a time, never per-request. This module is
the sole synchronized path for the login+history-fetch flow: a single
dedicated worker thread is the *only* code path allowed to call
mt5.initialize()/mt5.history_deals_get() for this flow, processing jobs
strictly one at a time from an unbounded FIFO queue. Because there is
exactly one consumer and each job runs to completion before the next
starts, two jobs can never interleave — this is what eliminates the
cross-account race, not a lock.

Login uses the single-call form mt5.initialize(login=, password=, server=)
rather than a separate mt5.initialize() + mt5.login() pair: it starts the
terminal (if not already running) and authorizes the given account in one
IPC round trip, and re-authorizes correctly even when a terminal is already
running under a different account — which is exactly the "next job, next
account" case this worker cycles through all day.

Known limitation: pre-existing routes (/history_deals_get, /symbol_info_tick,
/get_positions, etc.) are NOT routed through this worker and remain
unsynchronized against each other and against sync jobs — MT5's session is
process-wide regardless of which code path touches it. Accepted because this
API is now used exclusively via /sync_account_history for the
history-backfill flow.

Beyond login+fetch, this worker also resolves everything a caller would
otherwise need separate, unsynchronized /get_order_from_ticket and
/symbol_info/<symbol> calls for: each deal gets an `order_type` field, and
the job result carries a `symbols: {symbol: contract_size}` map for every
symbol appearing in the batch. Since one job runs start-to-finish on the
single worker thread with no other job interleaved, these lookups are race-free
here in a way they can never be as separate per-trade HTTP calls from a caller.
"""
import itertools
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import MetaTrader5 as mt5

from lib import get_order_from_ticket

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


@dataclass
class Job:
    job_id: str
    account: int
    password: Optional[str]
    server: str
    from_date: str
    to_date: str
    from_timestamp: int
    to_timestamp: int
    sequence: int
    status: str = STATUS_QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[list] = None
    deal_count: Optional[int] = None
    symbols: Optional[dict] = None
    error: Optional[str] = None
    error_code: Optional[int] = None


_queue: "queue.Queue[str]" = queue.Queue()  # maxsize=0 -> unbounded, put() never blocks/raises
_jobs: dict[str, Job] = {}
_store_lock = threading.Lock()
_sequence_counter = itertools.count(1)
_last_dispatched_sequence = 0
_avg_job_seconds = 3.0  # seed matches empirically observed 2-4s login+fetch cost

_worker_thread: Optional[threading.Thread] = None
_worker_start_lock = threading.Lock()


def enqueue_sync_job(account, password, server, from_date, to_date, from_timestamp, to_timestamp) -> str:
    """Build and store a Job, then enqueue it. Never blocks, never raises for capacity reasons."""
    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        account=account,
        password=password,
        server=server,
        from_date=from_date,
        to_date=to_date,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        sequence=next(_sequence_counter),
    )
    with _store_lock:
        _jobs[job_id] = job
    _queue.put(job_id)
    return job_id


def _enrich_deals(deals: list[dict]) -> dict:
    """
    Mutate each deal dict in place with its order_type, and return a
    {symbol: contract_size} map covering every symbol in the batch.
    Resolves each unique order/symbol exactly once. A lookup miss (order or
    symbol no longer resolvable) leaves the field as None rather than
    failing the whole job — one bad ticket/symbol shouldn't sink the batch.
    """
    symbols: dict = {}
    for deal in deals:
        order = get_order_from_ticket(deal["order"])
        deal["order_type"] = order["type"] if order is not None else None

        symbol = deal["symbol"]
        if symbol not in symbols:
            info = mt5.symbol_info(symbol)
            symbols[symbol] = info.trade_contract_size if info is not None else None
    return symbols


def process_sync_job(job: Job) -> Job:
    """
    Pure, directly-testable core: login, fetch history, mutate job in place.
    No locking, no queue, no thread — callable synchronously from tests or
    the real worker loop identically.
    """
    job.started_at = time.time()
    job.status = STATUS_PROCESSING
    try:
        authorized = mt5.initialize(login=job.account, password=job.password, server=job.server)
        if not authorized:
            code, msg = mt5.last_error()
            job.error = f"Login failed: {msg}"
            job.error_code = code
            return job

        deals = mt5.history_deals_get(job.from_timestamp, job.to_timestamp)
        if deals is None:
            job.error = "Failed to get deals history"
            return job

        job.result = [deal._asdict() for deal in deals]
        job.deal_count = len(job.result)
        job.symbols = _enrich_deals(job.result)
    except Exception as e:
        logger.error(f"Error in process_sync_job: {str(e)}")
        job.error = "Internal server error"
    finally:
        # Drop the credential from memory as soon as it's no longer needed,
        # on every path including exceptions.
        job.password = None
        job.finished_at = time.time()
        # Publish-last: result/deal_count/symbols/error/error_code are
        # already set above by the time status flips to its terminal value, so a
        # lock-free reader (get_job_view) never observes a "done"/"failed"
        # status before the fields it depends on are populated.
        job.status = STATUS_FAILED if job.error else STATUS_DONE
    return job


def _cleanup_expired_jobs(now: float) -> None:
    """Delete finished jobs older than SYNC_JOB_TTL_SECONDS. Caller must hold _store_lock."""
    ttl = int(os.environ.get("SYNC_JOB_TTL_SECONDS", 3600))
    expired = [
        job_id for job_id, job in _jobs.items()
        if job.status in (STATUS_DONE, STATUS_FAILED)
        and job.finished_at is not None
        and now - job.finished_at > ttl
    ]
    for job_id in expired:
        del _jobs[job_id]


def _worker_loop() -> None:
    global _last_dispatched_sequence, _avg_job_seconds
    while True:
        job_id = _queue.get()
        job = _jobs.get(job_id)
        if job is None:
            _queue.task_done()
            continue

        with _store_lock:
            _last_dispatched_sequence = job.sequence

        process_sync_job(job)

        duration = (job.finished_at or time.time()) - (job.started_at or time.time())
        with _store_lock:
            _avg_job_seconds = 0.7 * _avg_job_seconds + 0.3 * max(duration, 0.0)
            _cleanup_expired_jobs(time.time())
        _queue.task_done()


def get_job_view(job_id: str) -> Optional[dict]:
    """Build the JSON-serializable view shared by both routes. Never includes password."""
    with _store_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None

        if job.status == STATUS_QUEUED:
            queue_position = max(0, job.sequence - _last_dispatched_sequence - 1)
            estimated_wait_seconds = round(queue_position * _avg_job_seconds, 1)
        else:
            queue_position = 0
            estimated_wait_seconds = 0.0

        return {
            "job_id": job.job_id,
            "status": job.status,
            "account": job.account,
            "server": job.server,
            "from_date": job.from_date,
            "to_date": job.to_date,
            "queue_position": queue_position,
            "estimated_wait_seconds": estimated_wait_seconds,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "deal_count": job.deal_count,
            "result": job.result,
            "symbols": job.symbols,
            "error": job.error,
            "error_code": job.error_code,
        }


def start_worker() -> None:
    """Idempotent: starts the single background worker thread exactly once per process."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    with _worker_start_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="sync-worker", daemon=True)
        _worker_thread.start()
