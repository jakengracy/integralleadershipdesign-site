# CLAUDE.md — Chief of Staff Agent

This file documents the project for Claude Code sessions. Read it at the start of every session working on this project.

---

## What this project is

The Chief of Staff Agent is a persistent local orchestration layer running on a Mac Studio M1 Ultra. It:

- Manages all local Flask services via **supervisord** (start/stop/restart/status)
- Runs scheduled tasks via **APScheduler** (morning briefing, REFLIB digest, email triage)
- Accepts voice commands via **push-to-talk** (macOS menu bar app + pynput global hotkey)
- Routes tasks between **Ollama** (local, fast — mechanical tasks) and **Claude API** (cloud — synthesis and reasoning)

---

## Project structure

```
projects/chief-of-staff/
├── CLAUDE.md                  # This file
├── PROJECT_STATE.md           # Build progress — update at end of each phase
├── README.md                  # Setup and usage
│
├── supervisord/
│   ├── supervisord.conf       # Generated — do not edit by hand
│   ├── generate_conf.py       # Regenerates supervisord.conf from services.yaml
│   ├── services.yaml          # Source of truth for all managed services
│   └── retired_launchd/       # Archived launchd plists replaced by APScheduler
│
├── cos/
│   ├── config.py              # All config — reads from .env / environment
│   ├── app.py                 # Flask app — HTTP endpoints
│   ├── scheduler.py           # APScheduler jobs
│   ├── service_manager.py     # supervisord XML-RPC wrapper
│   ├── llm_router.py          # classify() and respond() — Ollama/Claude routing
│   │
│   ├── voice/
│   │   ├── menu_bar.py        # rumps + pynput menu bar app
│   │   └── transcribe.py      # faster-whisper STT
│   │
│   └── agents/
│       ├── morning_briefing.py
│       ├── reflib_digest.py
│       ├── email_triage.py
│       └── gilly_jobs.py      # supervisord-based — starts/stops the service
│
├── run.py                     # CoS Flask + scheduler entry point
├── run_voice.py               # Voice app entry point (macOS only)
├── requirements.txt
└── .env.example
```

---

## Rules for working on this project

1. **Verify before recommending.** Read the file. Check if a route/function exists. Never reconstruct from memory when the source is on disk.

2. **Verify before depending (Rule 1A).** Any time one action produces a result a subsequent action depends on, verify the result before proceeding.

3. **Phase gates.** Complete and checkpoint each phase before starting the next. Update `PROJECT_STATE.md` at every checkpoint.

4. **Ample comments.** All Python files must have inline comments explaining what each section does and why. Do not remove existing comments.

5. **Flag new dependencies.** Any new pip package not already in `requirements.txt` must be flagged before adding.

6. **Port conflicts.** If any port in `services.yaml` is in use by an unexpected process, surface it before starting supervisord.

7. **No em-dashes in headings.**

---

## Architecture decisions (locked)

- **Process manager:** supervisord
- **Scheduling:** APScheduler (BackgroundScheduler)
- **Voice input:** push-to-talk toggle via macOS menu bar (rumps) + pynput global hotkey
- **STT:** faster-whisper medium model
- **TTS:** macOS `say` command (Kokoro deferred)
- **LLM routing:** Ollama for mechanical tasks; Claude API for reasoning
- **Voice app port:** no HTTP port — communicates as HTTP client only (POSTs to CoS)
- **CoS port:** 5009

---

## Key endpoints

| Method | Path | Description |
|---|---|---|
| GET | /health | Liveness + all service states |
| GET | /services | Full service status |
| POST | /services/`<name>`/start | Start a named service |
| POST | /services/`<name>`/stop | Stop a named service |
| POST | /services/`<name>`/restart | Restart a named service |
| POST | /command | Natural language command (routed through LLM) |

---

## Phases and status

See `PROJECT_STATE.md` for current status of each phase.

1. supervisord foundation
2. CoS core (Flask + scheduler)
3. Agent modules (morning briefing, reflib, email triage, gilly jobs)
4. LLM routing layer
5. Voice layer
6. Schedule migration (retire launchd plists)
