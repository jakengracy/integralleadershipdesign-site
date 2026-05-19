"""
cos/agents/gilly_jobs.py — On-demand gilly-jobs orchestration via supervisord.

Unlike the other agent modules, this one does NOT inline the pipeline code.
gilly-jobs is an on-demand supervisord service; CoS starts it, waits for it
to finish, stops it, and returns the result summary.

Completion detection:
    The brief says to read the gilly-jobs source before writing this — since the
    source isn't available in this environment, we use two fallback strategies:
    Strategy A: Poll the gilly-jobs /health or /status endpoint for a "done" signal
    Strategy B: Watch for the supervisord process to exit naturally (state → EXITED)

    INTEGRATION TODO on M1 deployment:
    1. Read ~/Documents/claude-workspace/projects/gilly-jobs/ source files
    2. Identify how gilly-jobs signals completion:
       - Does it stop its own process when done? → Use Strategy B (already implemented)
       - Does it expose a status endpoint? → Add Strategy A polling below
       - Does it write a completion file? → Add file-watch logic
    3. Adjust POLL_INTERVAL and timeout below based on typical run time

SOURCE PROJECT: ~/Documents/claude-workspace/projects/gilly-jobs/
TRIGGER: On-demand via POST /command: "run gilly jobs"
TIMEOUT: GILLY_JOBS_TIMEOUT seconds (default 600 / 10 minutes)
"""

import logging
import time
from datetime import datetime

from cos.config import GILLY_JOBS_SERVICE_NAME, GILLY_JOBS_TIMEOUT
from cos.service_manager import manager as svc

logger = logging.getLogger(__name__)

# How often to poll supervisord for gilly-jobs state (seconds)
POLL_INTERVAL = 10


def run_gilly_jobs(context: dict) -> dict:
    """
    Start gilly-jobs via supervisord, wait for it to complete, return a summary.

    The job is considered complete when supervisord reports the process state
    as EXITED (normal exit) or FATAL (error exit). If neither happens within
    GILLY_JOBS_TIMEOUT seconds, the process is stopped and a timeout error
    is returned.

    Called by: cos/app.py::_dispatch_agent() with target "gilly_jobs"

    Returns: {"status": "ok"|"error"|"timeout", "summary": str, "elapsed": float}
    """
    logger.info(
        f"gilly_jobs: starting "
        f"(triggered_by={context.get('triggered_by','unknown')}, "
        f"timeout={GILLY_JOBS_TIMEOUT}s)"
    )
    start_time = datetime.now()

    # ── Verify it's not already running ───────────────────────────────────────
    current_state = svc.status(GILLY_JOBS_SERVICE_NAME).get("state", "UNKNOWN")
    if current_state == "RUNNING":
        msg = f"gilly-jobs is already running (state={current_state}) — not starting a second instance"
        logger.warning(msg)
        return {"status": "error", "summary": msg, "elapsed": 0}

    # ── Start the service ──────────────────────────────────────────────────────
    start_result = svc.start(GILLY_JOBS_SERVICE_NAME)
    if not start_result.get("success"):
        msg = f"Failed to start gilly-jobs: {start_result.get('error')}"
        logger.error(msg)
        return {"status": "error", "summary": msg, "elapsed": 0}

    logger.info(f"gilly-jobs started — polling every {POLL_INTERVAL}s for up to {GILLY_JOBS_TIMEOUT}s")

    # ── Poll until completion or timeout ──────────────────────────────────────
    deadline = time.time() + GILLY_JOBS_TIMEOUT
    final_state = None

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)

        state_info = svc.status(GILLY_JOBS_SERVICE_NAME)
        state      = state_info.get("state", "UNKNOWN")
        elapsed    = (datetime.now() - start_time).total_seconds()

        logger.debug(f"gilly-jobs state: {state} (elapsed: {elapsed:.0f}s)")

        if state == "EXITED":
            # Normal completion — supervisord exit code is in description
            final_state = "ok"
            logger.info(f"gilly-jobs exited normally after {elapsed:.0f}s")
            break
        elif state == "FATAL":
            # gilly-jobs crashed or exited with non-zero code
            final_state = "error"
            logger.error(
                f"gilly-jobs entered FATAL state after {elapsed:.0f}s: "
                f"{state_info.get('description')}"
            )
            break
        elif state == "STOPPED":
            # Stopped unexpectedly (killed externally?)
            final_state = "error"
            logger.warning(f"gilly-jobs is STOPPED unexpectedly after {elapsed:.0f}s")
            break
        # STARTING / RUNNING → keep polling

    else:
        # Fell through the while loop — timeout
        final_state = "timeout"
        elapsed     = (datetime.now() - start_time).total_seconds()
        logger.error(
            f"gilly-jobs timed out after {elapsed:.0f}s "
            f"(limit={GILLY_JOBS_TIMEOUT}s) — forcing stop"
        )
        svc.stop(GILLY_JOBS_SERVICE_NAME)

    # ── Ensure the process is stopped (it may have exited itself already) ─────
    current = svc.status(GILLY_JOBS_SERVICE_NAME).get("state", "UNKNOWN")
    if current == "RUNNING":
        logger.info("gilly-jobs still RUNNING after poll loop — stopping")
        svc.stop(GILLY_JOBS_SERVICE_NAME)

    elapsed = (datetime.now() - start_time).total_seconds()

    # ── Build result ───────────────────────────────────────────────────────────
    if final_state == "ok":
        summary = f"gilly-jobs completed successfully in {elapsed:.0f}s"
    elif final_state == "timeout":
        summary = f"gilly-jobs timed out after {elapsed:.0f}s — increase GILLY_JOBS_TIMEOUT if the job needs more time"
    else:
        summary = f"gilly-jobs encountered an error after {elapsed:.0f}s — check logs/{GILLY_JOBS_SERVICE_NAME}.stderr.log"

    logger.info(f"gilly_jobs result: {final_state} — {summary}")
    return {
        "status":  final_state if final_state != "timeout" else "error",
        "summary": summary,
        "elapsed": elapsed,
    }
