"""
run_voice.py — Entry point for the Chief of Staff menu bar voice app.

This runs as a SEPARATE supervisord process (cos-voice) from the main CoS Flask
app. It must run on the main thread (rumps requirement) and must be the only
process owning the macOS menu bar slot.

Usage:
    # Directly (for testing):
    python3 run_voice.py

    # Via supervisord (preferred):
    supervisorctl -c supervisord/supervisord.conf start cos-voice

Prerequisites:
    1. macOS only — rumps and the `say` command do not exist on Linux
    2. The Terminal or app running this process must have Accessibility permission
       (System Settings > Privacy & Security > Accessibility)
       pynput requires this to capture global keyboard events
    3. CoS Flask app (run.py) should be running before this starts — the voice
       app will show an error notification (not crash) if CoS is unreachable

macOS note on running from supervisord:
    The menu bar app requires a GUI session to render the menu bar icon.
    supervisord running as a launchd agent (GUI session) handles this correctly.
    If launched from a non-GUI launchd daemon, the icon won't appear.
"""

import logging
import sys
from pathlib import Path

# ── Load .env before importing anything from cos/ ─────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from cos.config import LOG_DIR, LOG_LEVEL

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(name)-20s] %(levelname)-8s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "cos-voice.log"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    # ── Guard: macOS only ──────────────────────────────────────────────────────
    import platform
    if platform.system() != "Darwin":
        logger.error(
            "run_voice.py is macOS only. "
            "rumps and the `say` command are not available on this platform."
        )
        sys.exit(1)

    logger.info("Chief of Staff voice app starting up (macOS menu bar)")

    # ── Import here to fail fast if rumps/pynput are missing ──────────────────
    try:
        import rumps
    except ImportError:
        logger.error("rumps not installed. Run: pip install rumps")
        sys.exit(1)

    try:
        from pynput import keyboard  # noqa: F401 — just checking it's importable
    except ImportError:
        logger.error(
            "pynput not installed. Global hotkey will not work. "
            "Run: pip install pynput"
        )
        # Non-fatal — the app still works via menu clicks without pynput

    from cos.voice.menu_bar import ChiefOfStaffVoiceApp

    # rumps.App.run() is blocking and must be called from the main thread.
    # This is why run_voice.py is a separate entry point.
    app = ChiefOfStaffVoiceApp()
    logger.info("Menu bar app initialised — starting rumps main loop")
    app.run()


if __name__ == "__main__":
    main()
