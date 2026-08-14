"""
WSGI entry point for the MT5 API.

Production (Waitress):
    python wsgi.py

Or directly via waitress-serve CLI:
    waitress-serve --host=127.0.0.1 --port=8000 wsgi:app

Environment variables (override in .env):
    MT5_WSGI_HOST    Host for waitress to bind on  (default: 127.0.0.1)
    MT5_WSGI_PORT    Port for waitress              (default: 8000)
    MT5_WSGI_THREADS Thread count for waitress      (default: 4)
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)


def _init_mt5() -> bool:
    """Connect to the MetaTrader5 terminal.  Safe to call multiple times."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            code, msg = mt5.last_error()
            logger.error("Failed to initialise MT5: [%d] %s", code, msg)
            return False
        logger.info("MT5 initialised successfully.")
        return True
    except Exception as exc:
        logger.error("Exception initialising MT5: %s", exc)
        return False


_init_mt5()

# Import the Flask app object *after* MT5 is initialised so that any
# blueprint-level startup code already has a live terminal connection.
from app import app  # noqa: E402


if __name__ == "__main__":
    from waitress import serve

    import sync_worker

    # Started only here (the real production entrypoint), never at plain
    # import time — see app.py's __main__ block for why.
    sync_worker.start_worker()

    host = os.environ.get("MT5_WSGI_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_WSGI_PORT", "8000"))
    threads = int(os.environ.get("MT5_WSGI_THREADS", "4"))

    logger.info("Starting Waitress on %s:%d  threads=%d", host, port, threads)
    serve(app, host=host, port=port, threads=threads)
