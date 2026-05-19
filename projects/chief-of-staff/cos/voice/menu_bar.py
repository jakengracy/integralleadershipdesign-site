"""
cos/voice/menu_bar.py — macOS menu bar app for push-to-talk voice commands.

Framework notes:
    - rumps: macOS menu bar app framework (macOS only — won't run on Linux)
    - pynput: global keyboard listener (required for Cmd+Shift+Space hotkey)
      rumps does NOT support global hotkeys natively; pynput is the standard
      solution for cross-app key capture on macOS from a Python process.

Push-to-talk behaviour: TOGGLE
    Press Cmd+Shift+Space once → starts recording (mic icon changes)
    Press Cmd+Shift+Space again → stops recording, transcribes, sends to CoS
    Rationale: toggle is more reliable than hold-to-release with global hotkeys.
    Hold-to-release requires detecting key-up events which are less consistent
    across macOS versions and keyboard types. Change PTT_MODE to "hold" and
    implement _on_release() if you prefer hold behaviour in a future iteration.

Accessibility permission:
    pynput requires the app (or the Terminal/process launching it) to be granted
    Accessibility access in System Settings > Privacy & Security > Accessibility.
    On first launch, macOS will prompt for permission. Grant it and restart the process.

Icons: uses emoji as text-based menu bar items (no .icns file needed).
    Idle:       "🎙" (mic icon)
    Recording:  "🔴" (red dot — recording in progress)
    Processing: "⏳" (hourglass — transcribing / waiting for CoS)
    Error:      "⚠️" (warning — CoS unreachable or transcription failed)
"""

import logging
import subprocess
import threading

import requests
import rumps

from cos.config import COS_COMMAND_URL, PTT_HOTKEY
from cos.voice.transcribe import start_recording, stop_recording

logger = logging.getLogger(__name__)

# ── Icon states ────────────────────────────────────────────────────────────────
ICON_IDLE       = "🎙"
ICON_RECORDING  = "🔴"
ICON_PROCESSING = "⏳"
ICON_ERROR      = "⚠️"


class ChiefOfStaffVoiceApp(rumps.App):
    """
    macOS menu bar app that handles push-to-talk recording and CoS dispatch.

    The app lives in the menu bar and responds to:
      1. Global keyboard shortcut (Cmd+Shift+Space) via pynput listener thread
      2. Menu item clicks (Start/Stop Listening, Service Status, Quit)
    """

    def __init__(self):
        super().__init__(
            name="Chief of Staff Voice",
            title=ICON_IDLE,
            # quit_button is disabled because we manage Quit manually below
            quit_button=None,
        )

        # Build the menu
        self._btn_listen = rumps.MenuItem(
            "Start Listening",
            callback=self._toggle_listening,
        )
        self._btn_status = rumps.MenuItem(
            "Service Status",
            callback=self._fetch_status,
        )

        self.menu = [
            self._btn_listen,
            None,  # Separator
            self._btn_status,
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]

        # Recording state — toggled by PTT shortcut and menu button
        self._is_recording = False

        # Start the global hotkey listener in a background thread
        self._start_hotkey_listener()

    # ── Hotkey listener ────────────────────────────────────────────────────────

    def _start_hotkey_listener(self):
        """
        Spin up a pynput GlobalHotKeys listener in a daemon thread.
        The listener calls _on_hotkey() whenever Cmd+Shift+Space is pressed.
        This runs independently of the rumps main loop.
        """
        try:
            from pynput import keyboard as pynput_keyboard

            # PTT_HOTKEY format: "<cmd>+<shift>+<space>"
            hotkeys = {PTT_HOTKEY: self._on_hotkey}

            listener = pynput_keyboard.GlobalHotKeys(hotkeys)
            listener.daemon = True  # Dies with the main process
            listener.start()
            logger.info(f"Global hotkey listener started: {PTT_HOTKEY}")

        except ImportError:
            logger.error(
                "pynput is not installed — global hotkey will not work. "
                "Use the menu bar button instead. Install: pip install pynput"
            )
        except Exception as e:
            logger.error(f"Failed to start hotkey listener: {e}. "
                         "Check Accessibility permissions in System Settings.")

    def _on_hotkey(self):
        """
        Called by pynput when the PTT hotkey is pressed.
        Runs in the pynput listener thread — dispatch back to the main thread
        via rumps.Timer to avoid cross-thread UI issues.
        """
        # Use a zero-delay timer to safely call toggle on the main thread
        rumps.Timer(self._toggle_listening, 0).start()

    # ── Recording toggle ───────────────────────────────────────────────────────

    def _toggle_listening(self, _sender=None):
        """Toggle recording on/off. Safe to call from any thread via rumps.Timer."""
        if self._is_recording:
            self._stop_and_transcribe()
        else:
            self._start_listening()

    def _start_listening(self):
        """Begin microphone capture and update UI to recording state."""
        if start_recording():
            self._is_recording     = True
            self.title             = ICON_RECORDING
            self._btn_listen.title = "Stop Listening"
            logger.info("Voice: recording started")
        else:
            self.title = ICON_ERROR
            rumps.notification(
                title="Chief of Staff",
                subtitle="Microphone Error",
                message="Could not open audio stream. Check microphone permissions.",
            )

    def _stop_and_transcribe(self):
        """
        Stop recording, then transcribe and dispatch in a background thread
        so the menu bar doesn't freeze during STT processing.
        """
        self._is_recording     = False
        self.title             = ICON_PROCESSING
        self._btn_listen.title = "Start Listening"
        logger.info("Voice: recording stopped, starting transcription")

        # Transcription + dispatch runs off the main thread (can take 1–3s)
        thread = threading.Thread(target=self._transcribe_and_dispatch, daemon=True)
        thread.start()

    def _transcribe_and_dispatch(self):
        """
        Worker thread: get audio from transcribe module, send to CoS, speak reply.
        Updates menu bar title/icon on completion.
        """
        audio_bytes = stop_recording()

        if not audio_bytes:
            logger.warning("No audio captured — nothing to transcribe")
            self._set_title_safe(ICON_IDLE)
            return

        # ── Transcribe ─────────────────────────────────────────────────────────
        from cos.voice.transcribe import transcribe
        try:
            transcript = transcribe(audio_bytes)
        except Exception as e:
            logger.exception("Transcription error")
            self._set_title_safe(ICON_ERROR)
            rumps.notification(
                title="Chief of Staff",
                subtitle="Transcription Error",
                message=str(e),
            )
            return

        if not transcript:
            logger.warning("Empty transcript — nothing to send")
            self._set_title_safe(ICON_IDLE)
            return

        logger.info(f"Transcript: {transcript!r}")

        # ── Dispatch to CoS ────────────────────────────────────────────────────
        try:
            response = requests.post(
                COS_COMMAND_URL,
                json={"text": transcript},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            reply = data.get("response", "Done.")
        except requests.exceptions.ConnectionError:
            logger.error(f"CoS unreachable at {COS_COMMAND_URL}")
            self._set_title_safe(ICON_ERROR)
            rumps.notification(
                title="Chief of Staff",
                subtitle="CoS Unreachable",
                message=f"Could not reach CoS at {COS_COMMAND_URL}. Is it running?",
            )
            return
        except Exception as e:
            logger.exception("Error sending command to CoS")
            self._set_title_safe(ICON_ERROR)
            reply = f"Error: {e}"

        # ── Speak the response ─────────────────────────────────────────────────
        # macOS `say` command for TTS. Replace with Kokoro in a future phase.
        try:
            subprocess.run(["say", reply], check=False, timeout=60)
        except FileNotFoundError:
            logger.error("`say` command not found — TTS unavailable (macOS only)")
        except Exception as e:
            logger.error(f"TTS error: {e}")

        self._set_title_safe(ICON_IDLE)

    # ── Menu item handlers ─────────────────────────────────────────────────────

    @rumps.clicked("Service Status")
    def _fetch_status(self, _sender=None):
        """
        Poll the CoS /health endpoint and display a summary notification.
        Runs in a background thread to avoid blocking the menu bar.
        """
        def _fetch():
            try:
                response = requests.get(
                    COS_COMMAND_URL.replace("/command", "/health"),
                    timeout=5,
                )
                data     = response.json()
                services = data.get("services", {})
                # Build a short summary: "prospect-scout: RUNNING, signal-app: STOPPED, ..."
                summary = "\n".join(
                    f"{name}: {info.get('state', '?')}"
                    for name, info in services.items()
                    if not name.startswith("_")
                )
                rumps.notification(
                    title="Chief of Staff — Service Status",
                    subtitle="",
                    message=summary or "No services found.",
                )
            except Exception as e:
                rumps.notification(
                    title="Chief of Staff",
                    subtitle="Status Error",
                    message=str(e),
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_title_safe(self, title: str):
        """
        Update the menu bar title from any thread.
        rumps.App.title is not thread-safe so we schedule via a timer.
        """
        def _update(_timer):
            self.title = title

        t = rumps.Timer(_update, 0)
        t.start()

    def _quit(self, _sender=None):
        """Clean shutdown: stop any ongoing recording before quitting."""
        if self._is_recording:
            stop_recording()
        rumps.quit_application()
