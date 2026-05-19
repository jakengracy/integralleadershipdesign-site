"""
run.py — Entry point for the Chief of Staff Flask app + APScheduler.

Usage:
    # From the project root, with venv activated:
    python3 run.py

    # Or via supervisord (preferred — managed startup):
    supervisorctl -c supervisord/supervisord.conf start chief-of-staff

Startup sequence:
    1. Load .env (must happen before config.py imports are resolved)
    2. Configure logging
    3. Start APScheduler (registers all cron jobs, begins health sweep)
    4. Start Flask (blocking — supervisord handles the process lifecycle)
"""

import logging
import signal
import sys
from pathlib import Path

# ── Load .env before importing anything from cos/ ─────────────────────────────
# python-dotenv reads .env from the current directory.
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# ── Now safe to import cos modules ────────────────────────────────────────────
from cos.config import COS_HOST, COS_PORT, LOG_DIR, LOG_LEVEL
from cos.app import app
from cos.scheduler import get_scheduler

# ── Logging ────────────────────────────────────────────────────────────────────
# Logging is also configured in app.py, but we set it here first so any
# import-time log messages from config.py are captured.
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(name)-20s] %(levelname)-8s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "cos.log"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("─" * 60)
    logger.info("Chief of Staff starting up")
    logger.info(f"  Flask:    http://{COS_HOST}:{COS_PORT}")
    logger.info(f"  Log dir:  {LOG_DIR}")
    logger.info("─" * 60)

    # ── Start scheduler ────────────────────────────────────────────────────────
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("APScheduler started")

    # ── Graceful shutdown on SIGTERM/SIGINT ────────────────────────────────────
    def _shutdown(signum, frame):
        logger.info(f"Received signal {signum} — shutting down scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # ── Start Flask (blocking) ─────────────────────────────────────────────────
    # debug=False is required in production — supervisord manages restarts.
    # use_reloader=False prevents Flask from spawning a child process that
    # supervisord can't track.
    app.run(
        host=COS_HOST,
        port=COS_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
