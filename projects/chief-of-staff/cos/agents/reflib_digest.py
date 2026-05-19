"""
cos/agents/reflib_digest.py — REFLIB digest and nightly ingest agent wrappers.

SOURCE PROJECT: ~/Documents/claude-workspace/projects/reflib-agent/
TRIGGERS:
    run_nightly_ingest  — daily 23:00 via APScheduler
    run_weekly_digest   — Sundays 08:00 via APScheduler
    Both are also triggerable on-demand via POST /command

INTEGRATION TODO (complete on M1 deployment):
─────────────────────────────────────────────
1. cd ~/Documents/claude-workspace/projects/reflib-agent/
2. Read all source files — identify:
   a. The nightly ingest entry point (indexes/fetches new reference items)
   b. The weekly digest entry point (compiles and sends the digest)
3. For each entry point, follow the same integration pattern as morning_briefing.py:
      sys.path.insert(0, str(REFLIB_AGENT_DIR))
      from <module> import <function>
      result = <function>(...)
4. Map return values to the {"status", "summary"} format
5. Remove this TODO block

The two functions are kept separate because:
   - Nightly ingest is lightweight (fetch + index); runs every night
   - Weekly digest is heavier (compile + send email/notification); runs once a week
   A failure in one should not prevent the other from running.
"""

import logging
import sys
from datetime import datetime

from cos.config import REFLIB_AGENT_DIR

logger = logging.getLogger(__name__)


def run_nightly_ingest(context: dict) -> dict:
    """
    Index new reference library items.

    Called by: cos/scheduler.py::job_reflib_nightly() (daily 23:00)
               cos/app.py::_dispatch_agent() with target "reflib_nightly"

    Returns: {"status": "ok"|"error", "summary": str, "items_indexed": int}
    """
    logger.info(f"reflib_nightly: starting (triggered_by={context.get('triggered_by','unknown')})")
    start_time = datetime.now()

    if not REFLIB_AGENT_DIR.exists():
        msg = (
            f"reflib-agent directory not found at {REFLIB_AGENT_DIR}. "
            f"Update REFLIB_AGENT_DIR in .env."
        )
        logger.error(msg)
        return {"status": "error", "summary": msg}

    # ── TODO: Replace with actual pipeline call ────────────────────────────────
    # if str(REFLIB_AGENT_DIR) not in sys.path:
    #     sys.path.insert(0, str(REFLIB_AGENT_DIR))
    # from ingest import run_nightly   # adjust to actual module/function name
    # result = run_nightly()
    # return {"status": "ok", "summary": f"Indexed {result['count']} items", **result}
    # ─────────────────────────────────────────────────────────────────────────

    logger.warning(
        "reflib_nightly: STUB — pipeline not yet integrated. "
        "See INTEGRATION TODO at top of this file."
    )
    elapsed = (datetime.now() - start_time).total_seconds()
    return {
        "status":        "ok",
        "summary":       "reflib_nightly stub ran — integrate reflib-agent to activate",
        "items_indexed": 0,
        "elapsed":       elapsed,
    }


def run_weekly_digest(context: dict) -> dict:
    """
    Compile and send the weekly REFLIB digest.

    Called by: cos/scheduler.py::job_reflib_digest() (Sundays 08:00)
               cos/app.py::_dispatch_agent() with target "reflib_digest"

    Returns: {"status": "ok"|"error", "summary": str, "items_in_digest": int}
    """
    logger.info(f"reflib_digest: starting (triggered_by={context.get('triggered_by','unknown')})")
    start_time = datetime.now()

    if not REFLIB_AGENT_DIR.exists():
        msg = (
            f"reflib-agent directory not found at {REFLIB_AGENT_DIR}. "
            f"Update REFLIB_AGENT_DIR in .env."
        )
        logger.error(msg)
        return {"status": "error", "summary": msg}

    # ── TODO: Replace with actual pipeline call ────────────────────────────────
    # if str(REFLIB_AGENT_DIR) not in sys.path:
    #     sys.path.insert(0, str(REFLIB_AGENT_DIR))
    # from digest import run_weekly   # adjust to actual module/function name
    # result = run_weekly()
    # return {"status": "ok", "summary": f"Digest sent with {result['count']} items", **result}
    # ─────────────────────────────────────────────────────────────────────────

    logger.warning(
        "reflib_digest: STUB — pipeline not yet integrated. "
        "See INTEGRATION TODO at top of this file."
    )
    elapsed = (datetime.now() - start_time).total_seconds()
    return {
        "status":          "ok",
        "summary":         "reflib_digest stub ran — integrate reflib-agent to activate",
        "items_in_digest": 0,
        "elapsed":         elapsed,
    }
