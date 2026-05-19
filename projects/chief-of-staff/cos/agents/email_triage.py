"""
cos/agents/email_triage.py — Email triage agent wrapper.

SOURCE PROJECT: ~/Documents/claude-workspace/projects/agentic-inbox/
NOTE: Port the backend pipeline only — the React frontend is out of scope.
TRIGGER: On-demand via POST /command: "triage emails", "run email triage"
         (No scheduled trigger by default — add one in scheduler.py if desired)

INTEGRATION TODO (complete on M1 deployment):
─────────────────────────────────────────────
1. cd ~/Documents/claude-workspace/projects/agentic-inbox/
2. Read all source files in the backend — ignore the React frontend directory
3. Identify:
   a. The entry point that kicks off the triage pipeline
   b. What inputs it needs (Gmail credentials? IMAP config?)
   c. What it produces (categorised list? takes actions? sends replies?)
4. Integrate following the same pattern as morning_briefing.py
5. Add any required credentials to .env.example and cos/config.py
6. Remove this TODO block
"""

import logging
import sys
from datetime import datetime

from cos.config import AGENTIC_INBOX_DIR

logger = logging.getLogger(__name__)


def run_email_triage(context: dict) -> dict:
    """
    Run the email triage pipeline.

    Called by: cos/app.py::_dispatch_agent() with target "email_triage"
               Can be added to scheduler.py as a cron job if desired.

    Returns: {"status": "ok"|"error", "summary": str, "emails_processed": int,
              "actions_taken": list}
    """
    logger.info(f"email_triage: starting (triggered_by={context.get('triggered_by','unknown')})")
    start_time = datetime.now()

    if not AGENTIC_INBOX_DIR.exists():
        msg = (
            f"agentic-inbox directory not found at {AGENTIC_INBOX_DIR}. "
            f"Update AGENTIC_INBOX_DIR in .env."
        )
        logger.error(msg)
        return {"status": "error", "summary": msg}

    # ── TODO: Replace with actual pipeline call ────────────────────────────────
    # if str(AGENTIC_INBOX_DIR) not in sys.path:
    #     sys.path.insert(0, str(AGENTIC_INBOX_DIR))
    # from pipeline import run_triage   # adjust to actual module/function name
    # result = run_triage()
    # return {
    #     "status": "ok",
    #     "summary": f"Triaged {result['count']} emails",
    #     "emails_processed": result['count'],
    #     "actions_taken": result.get('actions', []),
    # }
    # ─────────────────────────────────────────────────────────────────────────

    logger.warning(
        "email_triage: STUB — pipeline not yet integrated. "
        "See INTEGRATION TODO at top of this file."
    )
    elapsed = (datetime.now() - start_time).total_seconds()
    return {
        "status":           "ok",
        "summary":          "email_triage stub ran — integrate agentic-inbox to activate",
        "emails_processed": 0,
        "actions_taken":    [],
        "elapsed":          elapsed,
    }
