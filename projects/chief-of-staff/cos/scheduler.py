"""
cos/scheduler.py — APScheduler job definitions for the Chief of Staff.

All times are in America/Toronto (Ottawa local time). APScheduler uses
BackgroundScheduler so jobs run in threads within the same process as Flask.

Job inventory:
    morning_briefing    weekdays 07:00 local
    reflib_digest       Sundays  08:00 local
    reflib_nightly      daily    23:00 local
    health_sweep        every 5 minutes (always-on service watchdog)

To add a new job: write the job function below and register it in get_scheduler().
"""

import logging
from datetime import datetime

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from cos.config import SCHEDULER_TIMEZONE, LOG_DIR

logger = logging.getLogger(__name__)

# ── Watchdog configuration ─────────────────────────────────────────────────────
# Load the health-check URLs from services.yaml at scheduler init time so we
# can probe always-on services without hardcoding them here.
# This dict maps supervisord service name → health check URL.
_HEALTH_ENDPOINTS: dict[str, str] = {}


def _load_health_endpoints() -> dict[str, str]:
    """
    Parse services.yaml and return {name: health_check_url} for every always-on
    service that has a non-null health_check field.
    Called once at scheduler startup — not per-job.
    """
    from pathlib import Path
    import yaml

    services_yaml = Path(__file__).parent.parent / "supervisord" / "services.yaml"
    if not services_yaml.exists():
        logger.warning(f"services.yaml not found at {services_yaml} — health sweep disabled")
        return {}

    try:
        with open(services_yaml) as f:
            data = yaml.safe_load(f)
        return {
            s["name"]: s["health_check"]
            for s in data.get("services", [])
            if s.get("always_on") and s.get("health_check")
        }
    except Exception as e:
        logger.error(f"Failed to load health endpoints from services.yaml: {e}")
        return {}


# ── Job functions ──────────────────────────────────────────────────────────────

def job_morning_briefing():
    """
    Weekday 07:00 — run the morning briefing agent.
    Imports the agent module at call time so a syntax error in the agent
    doesn't prevent the scheduler from starting.
    """
    logger.info("Scheduler: firing morning_briefing")
    try:
        from cos.agents.morning_briefing import run_morning_briefing
        context = {"triggered_by": "scheduler", "trigger_time": datetime.now().isoformat()}
        result  = run_morning_briefing(context)
        logger.info(f"morning_briefing result: {result.get('summary', 'no summary')}")
    except Exception as e:
        logger.exception("morning_briefing job failed")


def job_reflib_digest():
    """
    Sunday 08:00 — run the weekly REFLIB digest (compile + send).
    """
    logger.info("Scheduler: firing reflib_digest (weekly)")
    try:
        from cos.agents.reflib_digest import run_weekly_digest
        context = {"triggered_by": "scheduler", "trigger_time": datetime.now().isoformat()}
        result  = run_weekly_digest(context)
        logger.info(f"reflib_digest result: {result.get('summary', 'no summary')}")
    except Exception as e:
        logger.exception("reflib_digest job failed")


def job_reflib_nightly():
    """
    Daily 23:00 — run the nightly REFLIB ingest (index new items).
    """
    logger.info("Scheduler: firing reflib_nightly")
    try:
        from cos.agents.reflib_digest import run_nightly_ingest
        context = {"triggered_by": "scheduler", "trigger_time": datetime.now().isoformat()}
        result  = run_nightly_ingest(context)
        logger.info(f"reflib_nightly result: {result.get('summary', 'no summary')}")
    except Exception as e:
        logger.exception("reflib_nightly job failed")


def job_health_sweep():
    """
    Every 5 minutes — ping the health endpoint of every always-on service.
    If a service is unreachable, ask supervisord to restart it.
    This is a belt-and-suspenders watchdog on top of supervisord's own autorestart.
    """
    from cos.service_manager import manager as svc

    if not _HEALTH_ENDPOINTS:
        return  # No endpoints configured — nothing to do

    for name, url in _HEALTH_ENDPOINTS.items():
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                logger.warning(
                    f"Health sweep: {name} returned HTTP {resp.status_code} — restarting"
                )
                svc.restart(name)
        except requests.exceptions.ConnectionError:
            logger.warning(
                f"Health sweep: {name} unreachable at {url} — checking supervisord state"
            )
            # Check if supervisord knows about it before blindly restarting
            state = svc.status(name).get("state", "UNKNOWN")
            if state in ("STOPPED", "EXITED", "FATAL"):
                logger.warning(f"Health sweep: {name} is {state} — attempting restart")
                svc.restart(name)
        except requests.exceptions.Timeout:
            logger.warning(f"Health sweep: {name} timed out at {url}")
        except Exception as e:
            logger.error(f"Health sweep: unexpected error checking {name}: {e}")


# ── Scheduler factory ──────────────────────────────────────────────────────────

def get_scheduler() -> BackgroundScheduler:
    """
    Build, register all jobs on, and return the APScheduler BackgroundScheduler.
    Caller (run.py) is responsible for calling scheduler.start().
    """
    global _HEALTH_ENDPOINTS
    _HEALTH_ENDPOINTS = _load_health_endpoints()
    logger.info(f"Health sweep will monitor {len(_HEALTH_ENDPOINTS)} services: "
                f"{list(_HEALTH_ENDPOINTS.keys())}")

    scheduler = BackgroundScheduler(timezone=SCHEDULER_TIMEZONE)

    # Morning briefing — weekdays only (day_of_week=mon-fri)
    scheduler.add_job(
        job_morning_briefing,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=7,
            minute=0,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="morning_briefing",
        name="Morning Briefing",
        replace_existing=True,
    )

    # Weekly REFLIB digest — Sunday morning
    scheduler.add_job(
        job_reflib_digest,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=8,
            minute=0,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="reflib_digest",
        name="REFLIB Weekly Digest",
        replace_existing=True,
    )

    # Nightly REFLIB ingest — every night
    scheduler.add_job(
        job_reflib_nightly,
        trigger=CronTrigger(
            hour=23,
            minute=0,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="reflib_nightly",
        name="REFLIB Nightly Ingest",
        replace_existing=True,
    )

    # Health check sweep — every 5 minutes
    scheduler.add_job(
        job_health_sweep,
        trigger=IntervalTrigger(minutes=5),
        id="health_sweep",
        name="Service Health Sweep",
        replace_existing=True,
    )

    # Log all registered jobs at startup for easy verification
    jobs = scheduler.get_jobs()
    logger.info(f"Scheduler: {len(jobs)} jobs registered:")
    for job in jobs:
        logger.info(f"  [{job.id}] {job.name} — next run: {job.next_run_time}")

    return scheduler
