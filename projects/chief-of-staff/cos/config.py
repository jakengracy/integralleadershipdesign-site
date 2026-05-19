"""
cos/config.py — Centralised configuration for the Chief of Staff agent.

All sensitive values (API keys) are read from environment variables only —
never hardcoded. Non-sensitive defaults are set here.

Load order for .env:
    run.py and run_voice.py both call load_dotenv() before importing this
    module, so the values are populated by the time any other module reads them.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above this package)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# ── Base paths ─────────────────────────────────────────────────────────────────

WORKSPACE_ROOT = Path(
    os.environ.get("WORKSPACE_ROOT", os.path.expanduser("~/Documents/claude-workspace"))
)

# Project root can be overridden — useful for running from a non-standard location
PROJECT_ROOT = Path(
    os.environ.get("COS_PROJECT_ROOT", str(WORKSPACE_ROOT / "projects" / "chief-of-staff"))
)

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── API keys ───────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    # Non-fatal at import time — the LLM router will error only when Claude is called
    import warnings
    warnings.warn("ANTHROPIC_API_KEY is not set. Claude routing will fail.", stacklevel=1)


# ── External service URLs ──────────────────────────────────────────────────────

# Ollama must be running before CoS starts; default port is standard Ollama default
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# supervisord XML-RPC endpoint — inet_http_server in supervisord.conf
SUPERVISORD_URL: str = os.environ.get("SUPERVISORD_URL", "http://localhost:9001/RPC2")


# ── CoS server ─────────────────────────────────────────────────────────────────

COS_PORT: int = int(os.environ.get("COS_PORT", 5009))
# Bind to 127.0.0.1 only — Tailscale handles remote access; never expose to 0.0.0.0
COS_HOST: str = os.environ.get("COS_HOST", "127.0.0.1")


# ── Scheduler ─────────────────────────────────────────────────────────────────

# Ottawa is America/Toronto. APScheduler uses pytz/zoneinfo names.
SCHEDULER_TIMEZONE: str = os.environ.get("SCHEDULER_TIMEZONE", "America/Toronto")


# ── LLM models ────────────────────────────────────────────────────────────────

# Fast local model used for intent classification. Verify model name with
# `ollama list` on first M1 deployment — swap if llama3.2 isn't present.
OLLAMA_CLASSIFY_MODEL: str = os.environ.get("OLLAMA_CLASSIFY_MODEL", "llama3.2")

# Claude model for synthesis and complex reasoning tasks
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")


# ── Subagent project directories ──────────────────────────────────────────────
# Each agent module sys.path-inserts its source dir to import the original pipeline.
# Verify these match your actual SERVER_REGISTRY.md paths on first M1 deployment.

TASK_AGENTS_DIR = Path(
    os.environ.get("TASK_AGENTS_DIR", str(WORKSPACE_ROOT / "projects" / "task-agents"))
)
REFLIB_AGENT_DIR = Path(
    os.environ.get("REFLIB_AGENT_DIR", str(WORKSPACE_ROOT / "projects" / "reflib-agent"))
)
AGENTIC_INBOX_DIR = Path(
    os.environ.get("AGENTIC_INBOX_DIR", str(WORKSPACE_ROOT / "projects" / "agentic-inbox"))
)
GILLY_JOBS_DIR = Path(
    os.environ.get("GILLY_JOBS_DIR", str(WORKSPACE_ROOT / "projects" / "gilly-jobs"))
)

# supervisord program name for gilly-jobs (must match services.yaml name field)
GILLY_JOBS_SERVICE_NAME: str = os.environ.get("GILLY_JOBS_SERVICE_NAME", "gilly-jobs")
# How long to wait for gilly-jobs to complete before timing out (seconds)
GILLY_JOBS_TIMEOUT: int = int(os.environ.get("GILLY_JOBS_TIMEOUT", 600))  # 10 minutes


# ── Voice layer ────────────────────────────────────────────────────────────────

# faster-whisper model size: tiny/base/small/medium/large-v3
# medium is a good balance on M1 Ultra; upgrade to large-v3 if accuracy is poor
WHISPER_MODEL_SIZE: str = os.environ.get("WHISPER_MODEL_SIZE", "medium")
WHISPER_LANGUAGE: str   = os.environ.get("WHISPER_LANGUAGE", "en")

# Global push-to-talk hotkey in pynput format
# Default: Cmd+Shift+Space  (pynput uses <cmd>, <shift>, <space> notation)
PTT_HOTKEY: str = os.environ.get("PTT_HOTKEY", "<cmd>+<shift>+<space>")

# CoS endpoint the voice app POSTs transcripts to
COS_COMMAND_URL: str = os.environ.get("COS_COMMAND_URL", f"http://localhost:{COS_PORT}/command")


# ── Logging ────────────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
