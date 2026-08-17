"""
Live integration tests against the public Cloudflare-fronted domain,
mtapi.tradewi.se — as opposed to test_live.py, which talks to the server
directly over localhost/LAN. This exercises the whole path a real external
caller uses: Cloudflare edge -> (Flexible SSL) -> nginx :80 -> Waitress
:8000 -> Flask -> the single-worker /sync_account_history login+fetch flow.

Run with:
    pytest tests/test_live_external.py -v

Skipped automatically when the public domain is unreachable.
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

EXTERNAL_BASE_URL = os.environ.get("MT5_EXTERNAL_BASE_URL", "https://mtapi.tradewi.se")

DEMO_ACCOUNT  = 52414311
DEMO_PASSWORD = "77lmYn!!5@YRn$"
DEMO_SERVER   = "ICMarketsEU-Demo"

# From mt5_login_debug/testmt5.ipynb.
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
    # Cloudflare's edge WAF returns a bare 403 for Python's default
    # "Python-urllib/x.y" User-Agent (verified directly against
    # mtapi.tradewi.se) — a real browser/client UA is required to reach
    # the origin at all. curl passes because it sends its own UA.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) mt5api-live-tests"}
    if _API_KEY:
        headers["X-API-Key"] = _API_KEY
    return headers


def _get(path, params=None):
    url = EXTERNAL_BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


def _post(path, params=None):
    url = EXTERNAL_BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        # A route that no longer exists (e.g. removed /login, /logout) 404s
        # with Flask/Werkzeug's default HTML error page, not JSON.
        body = e.read()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body.decode(errors="replace")


def _run_sync_job(account, password, server, days=1, timeout=30):
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
        s, b, _ = _get(f"/sync_account_history/{job_id}")
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
def external_domain_reachable():
    try:
        status, _, _ = _get("/health")
    except Exception as exc:
        pytest.skip(f"{EXTERNAL_BASE_URL} not reachable — skipping external live tests ({exc})")
    if status != 200:
        pytest.skip(f"{EXTERNAL_BASE_URL}/health returned {status} — skipping external live tests")


# ---------------------------------------------------------------------------
# 1. Reachability through Cloudflare
# ---------------------------------------------------------------------------

class TestExternalReachability:
    def test_health_via_https(self):
        status, body, _ = _get("/health")
        assert status == 200
        assert body["status"] == "healthy"

    def test_served_through_cloudflare(self):
        """Sanity check that we're actually going over the public edge and
        not, say, silently resolving to localhost."""
        _, _, headers = _get("/health")
        server_header = headers.get("Server", "")
        assert "cloudflare" in server_header.lower() or "CF-RAY" in headers, (
            f"Response didn't look like it came through Cloudflare: {headers}"
        )

    def test_login_route_gone_externally(self):
        status, _ = _post("/login", {
            "account": DEMO_ACCOUNT, "password": DEMO_PASSWORD, "server": DEMO_SERVER,
        })
        assert status == 404

    def test_logout_route_gone_externally(self):
        status, _ = _post("/logout")
        assert status == 404


# ---------------------------------------------------------------------------
# 2. Login + history-fetch through the public domain
# ---------------------------------------------------------------------------

class TestExternalSyncAccountHistory:
    @pytest.mark.parametrize(
        "account,password,server",
        [
            (DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER),
            (NOTEBOOK_ACCOUNT, NOTEBOOK_PASSWORD, NOTEBOOK_SERVER),
            (NOTEBOOK_ACCOUNT_2, NOTEBOOK_PASSWORD_2, NOTEBOOK_SERVER_2),
        ],
        ids=["icmarkets-demo", "pepperstone-demo", "fxpro-demo"],
    )
    def test_sync_history_end_to_end_externally(self, account, password, server):
        status, final = _run_sync_job(account, password, server, days=7)
        assert status == 202
        assert final["status"] == "done", final.get("error")
        assert isinstance(final["result"], list)
        assert "password" not in final

        _, health, _ = _get("/health")
        assert health["mt5_terminal_connected"] is True
        assert health["mt5_account_logged_in"] is True
        assert health["mt5_account"] == account

    def test_sync_history_unknown_job_404_externally(self):
        status, _, _ = _get("/sync_account_history/does-not-exist")
        assert status == 404

    def test_sync_history_leaves_demo_account_logged_in(self):
        """Run last: restore the demo account session so other external
        smoke checks against this domain see a consistent account."""
        _, final = _run_sync_job(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER, days=1)
        assert final["status"] == "done", final.get("error")
