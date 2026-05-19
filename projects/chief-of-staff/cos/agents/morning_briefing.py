"""
cos/agents/morning_briefing.py — Morning briefing agent wrapper.

SOURCE PROJECT: ~/Documents/claude-workspace/projects/task-agents/
TRIGGER: Weekdays 07:00 AM via APScheduler (cos/scheduler.py job_morning_briefing)
         Also triggerable on-demand via POST /command: "run morning briefing"

INTEGRATION TODO (complete on M1 deployment):
─────────────────────────────────────────────
1. cd ~/Documents/claude-workspace/projects/task-agents/
2. Read all source files in full — especially the entry point that kicks off
   the pipeline (look for main(), run(), or a Flask route that triggers the chain)
3. Identify what the pipeline does and what it returns/sends (email? Slack? stdout?)
4. Replace the stub body below with:
      sys.path.insert(0, str(TASK_AGENTS_DIR))
      from <entry_module> import <entry_function>
      result = <entry_function>(<appropriate args>)
5. Map the pipeline's return value to the dict format below
6. Remove this TODO block

The interface contract (do not change the function signature or return format):
    context: dict — passed by scheduler; may contain {"triggered_by", "trigger_time"}
    returns: {"status": "ok"|"error", "summary": str, ...any extra keys}
"""

import logging
import sys
from datetime import datetime

from cos.config import TASK_AGENTS_DIR

logger = logging.getLogger(__name__)


def run_morning_briefing(context: dict) -> dict:
    """
    Run the morning briefing pipeline.

    Called by: cos/scheduler.py::job_morning_briefing() (weekdays 07:00)
               cos/app.py::_dispatch_agent() (on-demand via /command)

    Returns a result dict with at minimum {"status": "ok"|"error", "summary": str}.
    """
    logger.info(f"morning_briefing: starting (triggered_by={context.get('triggered_by','unknown')})")
    start_time = datetime.now()

    # ── Check source project is available ─────────────────────────────────────
    if not TASK_AGENTS_DIR.exists():
        msg = (
            f"task-agents directory not found at {TASK_AGENTS_DIR}. "
            f"Update TASK_AGENTS_DIR in .env or deploy to correct path."
        )
        logger.error(msg)
        return {"status": "error", "summary": msg}

    # ── TODO: Replace this stub with the actual pipeline call ─────────────────
    # Example integration pattern:
    #
    #   if str(TASK_AGENTS_DIR) not in sys.path:
    #       sys.path.insert(0, str(TASK_AGENTS_DIR))
    #   try:
    #       from pipeline import run_briefing   # adjust import to match source
    #       pipeline_result = run_briefing()
    #       summary = f"Briefing delivered: {pipeline_result}"
    #       return {"status": "ok", "summary": summary, "raw": pipeline_result}
    #   except Exception as e:
    #       logger.exception("morning_briefing pipeline raised an exception")
    #       return {"status": "error", "summary": str(e)}
    #
    # ── STUB: log a warning and return a placeholder result ───────────────────
    logger.warning(
        "morning_briefing: STUB — pipeline not yet integrated. "
        "See INTEGRATION TODO comment at top of this file."
    )

    elapsed = (datetime.now() - start_time).total_seconds()
    return {
        "status":  "ok",
        "summary": "morning_briefing stub ran — integrate task-agents pipeline to activate",
        "elapsed": elapsed,
    }
