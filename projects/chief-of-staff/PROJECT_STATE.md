# PROJECT_STATE.md — Chief of Staff build progress

Updated at end of each phase. All phase gates must be cleared before the next phase begins.

---

## Build environment note

This project was scaffolded in a **Linux cloud container** (Claude Code on the web,
repository: `jakengracy/integralleadershipdesign-site`, branch: `claude/chief-of-staff-agent-HCKXh`).

All files are written correctly for **macOS (M1 Ultra)** but have not been executed.
Verification checkpoints marked below must be completed on the M1 after deployment.

---

## Phase 1 — supervisord Foundation

**Status: BUILT — awaiting M1 verification**

Files created:
- `supervisord/services.yaml` — service manifest (9 services: 7 always-on, 3 on-demand)
- `supervisord/generate_conf.py` — generates supervisord.conf from services.yaml
- `supervisord/supervisord.conf` — **not yet generated** (run generate_conf.py on M1)

### M1 deployment steps

```bash
cd ~/Documents/claude-workspace/projects/chief-of-staff

# 1. Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Verify services.yaml paths match SERVER_REGISTRY.md
#    Update any directory: entries that differ from your actual workspace
nano supervisord/services.yaml

# 3. Generate supervisord.conf
python3 supervisord/generate_conf.py

# 4. Check for port conflicts
lsof -i :5001 -i :5002 -i :5003 -i :5004 -i :5005 -i :5009

# 5. Start supervisord
supervisord -c supervisord/supervisord.conf

# 6. Check status
supervisorctl -c supervisord/supervisord.conf status
```

### Checkpoint criteria (must pass before Phase 2)
- [ ] `supervisorctl status` shows all always-on services as RUNNING
- [ ] On-demand services show STOPPED
- [ ] `supervisorctl start gilly-jobs` and `supervisorctl stop gilly-jobs` work
- [ ] No unexpected port conflicts

---

## Phase 2 — Chief of Staff Core

**Status: BUILT — awaiting M1 verification**

Files created:
- `cos/config.py`
- `cos/service_manager.py`
- `cos/app.py`
- `cos/scheduler.py`
- `run.py`

### M1 deployment steps

```bash
# With venv activated, from project root:

# 1. Copy and fill in .env
cp .env.example .env
nano .env    # Set ANTHROPIC_API_KEY at minimum

# 2. Start CoS (supervisord manages this, but test directly first)
python3 run.py

# 3. In a second terminal, verify:
curl http://localhost:5009/health
curl -X POST http://localhost:5009/command \
  -H 'Content-Type: application/json' \
  -d '{"text": "status"}'
```

### Checkpoint criteria
- [ ] `curl http://localhost:5009/health` returns `{"status": "ok", "services": {...}}`
- [ ] `/command` with `{"text":"status"}` returns a service status summary
- [ ] APScheduler log shows 4 jobs registered at startup (morning_briefing, reflib_digest, reflib_nightly, health_sweep)

---

## Phase 3 — Subagent Modules

**Status: STUBS BUILT — integration required on M1**

Files created (stubs with correct interfaces):
- `cos/agents/morning_briefing.py` — `run_morning_briefing(context) -> result`
- `cos/agents/reflib_digest.py` — `run_nightly_ingest(context)`, `run_weekly_digest(context)`
- `cos/agents/email_triage.py` — `run_email_triage(context) -> result`
- `cos/agents/gilly_jobs.py` — `run_gilly_jobs(context) -> result` (supervisord-based, not a stub)

### M1 integration steps (per agent)

For each of morning_briefing, reflib_digest, email_triage:
1. `cd ~/Documents/claude-workspace/projects/<source-project>/`
2. Read all source files — find the pipeline entry point
3. Open `cos/agents/<module>.py` — follow the INTEGRATION TODO instructions
4. Test: `python3 -c "from cos.agents.<module> import <fn>; print(<fn>({}))")`

gilly_jobs.py is functional as-is. Verify completion detection (EXITED state polling)
matches the actual gilly-jobs exit behaviour — see the INTEGRATION TODO in that file.

### Checkpoint criteria
- [ ] Each agent module imports cleanly: `python3 -c "import cos.agents.morning_briefing"`
- [ ] Morning briefing pipeline runs end-to-end
- [ ] REFLIB nightly ingest runs end-to-end
- [ ] REFLIB weekly digest runs end-to-end
- [ ] Email triage runs end-to-end
- [ ] gilly-jobs starts, runs, stops cleanly via `run_gilly_jobs({})`

---

## Phase 4 — LLM Routing Layer

**Status: BUILT — requires Ollama model verification on M1**

Files created:
- `cos/llm_router.py` — `classify(text) -> dict`, `respond(text, classification, context) -> str`

### M1 deployment steps

```bash
# 1. Check available Ollama models
ollama list

# 2. If llama3.2 is not listed, update OLLAMA_CLASSIFY_MODEL in .env:
#    OLLAMA_CLASSIFY_MODEL=<whatever model name is listed>

# 3. Test classification
python3 -c "
from cos.llm_router import classify
print(classify('start prospect scout'))
print(classify('summarise my emails from this morning'))
"
```

### Checkpoint criteria
- [ ] `classify("start prospect scout")` returns `{"route": "ollama", "intent": "start_service", ...}`
- [ ] `classify("summarise my emails from this morning")` returns `{"route": "claude", ...}`
- [ ] Ollama fallback to rule-based classifier works when Ollama is stopped

---

## Phase 5 — Voice Layer

**Status: BUILT — macOS execution required on M1**

Files created:
- `cos/voice/transcribe.py`
- `cos/voice/menu_bar.py`
- `run_voice.py`

### M1 deployment steps

```bash
# 1. Grant Accessibility permission to Terminal (or the app running run_voice.py):
#    System Settings > Privacy & Security > Accessibility → add Terminal

# 2. Start the voice app
python3 run_voice.py

# 3. Verify:
#    - Menu bar icon "🎙" appears
#    - Press Cmd+Shift+Space → icon changes to "🔴" (recording)
#    - Press Cmd+Shift+Space again → icon changes to "⏳" (processing)
#    - `say` speaks the CoS response
#    - Icon returns to "🎙"
```

Design choices logged here:
- Push-to-talk: **toggle** (not hold-to-release) — flagged and documented in menu_bar.py
- Hotkey: `pynput` (not rumps native — rumps has no global hotkey support)

### Checkpoint criteria
- [ ] Menu bar icon appears
- [ ] Cmd+Shift+Space triggers recording
- [ ] Speech is transcribed correctly
- [ ] CoS receives command and responds
- [ ] `say` speaks the response
- [ ] CoS-unreachable case shows a notification, does not crash

---

## Phase 6 — Schedule Migration

**Status: DOCUMENTED — action required on M1**

### M1 steps (run manually)

```bash
# 1. List active launchd agents related to CoS pipelines
launchctl list | grep -iE 'claude|python|briefing|reflib|inbox'

# 2. For each pipeline now managed by APScheduler (morning briefing, reflib nightly,
#    reflib digest), find the plist:
launchctl list <service-label>   # shows plist path

# 3. Unload the plist
launchctl unload ~/Library/LaunchAgents/<plist-name>.plist

# 4. Archive it (do not delete — preserve for reference)
mv ~/Library/LaunchAgents/<plist-name>.plist supervisord/retired_launchd/

# 5. Verify APScheduler has the equivalent job:
curl http://localhost:5009/health   # scheduler jobs are logged at startup

# 6. Update SERVER_REGISTRY.md (or note that services.yaml now supersedes it
#    for all CoS-managed services)
```

### Checkpoint criteria
- [ ] No duplicate launchd agents firing for CoS-managed pipelines
- [ ] APScheduler log shows jobs firing at correct times
- [ ] Retired plists are archived in `supervisord/retired_launchd/`

---

## Open items

- [ ] Verify services.yaml directory paths against SERVER_REGISTRY.md (Phase 1)
- [ ] Verify Ollama model name with `ollama list` (Phase 4)
- [ ] Integrate morning_briefing pipeline from task-agents (Phase 3)
- [ ] Integrate reflib_digest pipelines from reflib-agent (Phase 3)
- [ ] Integrate email_triage pipeline from agentic-inbox (Phase 3)
- [ ] Confirm gilly-jobs completion signal (EXITED state vs endpoint vs file) (Phase 3)
- [ ] Retire launchd plists for migrated pipelines (Phase 6)
- [ ] Consider making long-running agent calls async (return job ID, poll /jobs/<id>)
- [ ] Upgrade Whisper to large-v3 if medium accuracy is insufficient (Phase 5)
- [ ] Kokoro TTS deferred — currently using macOS `say` (Phase 5)
