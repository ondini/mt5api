# CLAUDE.md

MT5 API — Flask app (`app.py`) behind Waitress (`wsgi.py`) behind nginx, on a Windows server (EC2, `EC2AMAZ-VPH2GF6`). Public domain: `mtapi.tradewi.se` (moved from `mtapi.trade-wise.net`, which no longer points here).

## Deployment: MT5API backend runs as a Scheduled Task, NOT a service — by design

- Task: `\MT5\MT5API` (Task Scheduler), logon trigger, runs interactively as Administrator: `python wsgi.py`.
- **Do not** convert it to an NSSM/Windows service. `install_service.bat`'s `MT5API` service target is broken and must not be (re)installed: `mt5.initialize()` fails with `IPC initialize failed, MetaTrader 5 x64 not found` under any service (even NSSM, even as the same user) because Windows Session-0 isolation blocks the IPC the MetaTrader5 Python API needs, which only exists in the interactive desktop session where `terminal64.exe` runs. Confirmed by direct testing 2026-08-14.
- nginx (`MT5API-Nginx` NSSM service, port 80 → Waitress 8000) is fine as a real service — only the Python/MT5 backend has this constraint.
- A stopped/manual-start `MT5API` NSSM service may still be present from that failed experiment — ignore/leftover, not in use.
- To redeploy after a `git pull`: kill the running `python .../wsgi.py` process, then `schtasks /run /tn "\MT5\MT5API"` (or just let the logon trigger fire on next login). The task was found disabled once before after an ad hoc restart attempt — check `schtasks /query /tn "\MT5\MT5API"` shows `Enabled` if the app seems stuck on old code.
- Scheduled-task runs don't write to `logs/mt5api.log` (that path is only populated when NSSM redirects stdout/stderr) — use `/health`'s `mt5_terminal_connected`/`mt5_account_logged_in` fields, or Task Scheduler history, to check liveness instead.

## External access

- Origin (`nginx.conf`) has never served TLS — plain HTTP on port 80 only, no cert anywhere on the box. External HTTPS only works if Cloudflare's SSL/TLS mode for the zone is **Flexible**.
- If `mtapi.tradewi.se` (or any future domain) 522s from Cloudflare, check that setting first before touching anything on this server.
- Confirmed working end-to-end externally as of 2026-08-14 after setting the zone to Flexible.

## For other services calling this API: use `/sync_account_history`, not raw `/login` + `/history_deals_get`

- MT5's Python API has exactly one process-wide session (one terminal, one logged-in account, ever). `POST /sync_account_history` (`routes/sync.py` + `sync_worker.py`) is the only race-free way to do a login+history-fetch: it enqueues the job and returns a `job_id` immediately (`202`); poll `GET /sync_account_history/<job_id>` for status/result.
- It does manage a real queue — an unbounded in-memory FIFO. `POST` never blocks and never rejects for capacity: concurrent callers can enqueue freely, and the response includes `queue_position`/`estimated_wait_seconds`.
- **Exactly one background worker thread, always** — jobs are processed strictly one at a time, never in parallel, by design: MT5 can't have two logins active in the same process, so more workers would just reintroduce the race the queue exists to prevent. Throughput is roughly one job per ~2-4s (login + fetch cost) — bursty callers queue up rather than fan out.
- Every other pre-existing route (`/login`, `/history_deals_get`, `/symbol_info_tick`, `/get_positions`, etc.) bypasses this queue entirely and is **not** synchronized against it or against each other. A direct `/login` call racing a queued sync job can still stomp the session mid-fetch. If another API needs login+history data, it should go through `/sync_account_history` exclusively rather than mixing in the raw endpoints.
- The job result is enriched beyond the raw deals so callers don't need separate `/get_order_from_ticket` or `/symbol_info/<symbol>` calls per trade (those would reintroduce the same unsynchronized-route race, just per-deal instead of per-login): each deal dict in `result` carries an `order_type` field, and the top-level job view carries a `symbols: {symbol: contract_size}` map for every symbol in the batch. Both are resolved once per unique order/symbol inside `sync_worker._enrich_deals`, still on the single worker thread, so still race-free.
