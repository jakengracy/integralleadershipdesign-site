# Chief of Staff Agent

A persistent local orchestration layer that manages all local AI services via supervisord, runs scheduled tasks (morning briefing, REFLIB digest, email triage), accepts voice commands via push-to-talk, and routes tasks between a local Ollama LLM and the Claude API.

---

## Prerequisites

- macOS (M1 Ultra or later)
- Python 3.11+
- Ollama running on port 11434 (`ollama serve`)
- Anthropic API key
- Accessibility permission granted to the terminal running `run_voice.py`

---

## First-time setup

```bash
cd ~/Documents/claude-workspace/projects/chief-of-staff

# 1. Create and activate the virtualenv
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 4. Verify Ollama model name
ollama list
# If llama3.2 is not listed, set OLLAMA_CLASSIFY_MODEL=<your model> in .env

# 5. Verify service paths in services.yaml match your workspace layout
# Cross-reference against ~/Documents/claude-workspace/SERVER_REGISTRY.md
nano supervisord/services.yaml

# 6. Generate supervisord.conf
python3 supervisord/generate_conf.py

# 7. Start supervisord (manages all services including CoS itself)
supervisord -c supervisord/supervisord.conf

# 8. Check all services started cleanly
supervisorctl -c supervisord/supervisord.conf status
```

---

## Starting and stopping supervisord

```bash
# Start
supervisord -c supervisord/supervisord.conf

# Stop all managed services
supervisorctl -c supervisord/supervisord.conf shutdown

# Reload config after editing services.yaml (re-run generate_conf.py first)
python3 supervisord/generate_conf.py
supervisorctl -c supervisord/supervisord.conf reload

# Check status
supervisorctl -c supervisord/supervisord.conf status

# View live logs for a specific service
tail -f logs/chief-of-staff.stdout.log
tail -f logs/cos-voice.stdout.log
```

---

## Adding a new service

1. Add an entry to `supervisord/services.yaml`:
   ```yaml
   - name: my-new-service
     port: 5014
     directory: ~/Documents/claude-workspace/projects/my-new-service
     command: venv/bin/python3 run.py
     always_on: true
     health_check: http://localhost:5014/health
   ```

2. Regenerate and reload:
   ```bash
   python3 supervisord/generate_conf.py
   supervisorctl -c supervisord/supervisord.conf reread
   supervisorctl -c supervisord/supervisord.conf add my-new-service
   supervisorctl -c supervisord/supervisord.conf start my-new-service
   ```

3. If the new service is a pipeline agent, add a wrapper in `cos/agents/` and register it in `cos/app.py::AGENT_DISPATCH`.

---

## Sending commands

```bash
# Natural language command (routed through Ollama + Claude)
curl -s -X POST http://localhost:5009/command \
  -H 'Content-Type: application/json' \
  -d '{"text": "start prospect scout"}'

# Direct service control (bypasses LLM routing)
curl -s -X POST http://localhost:5009/services/prospect-scout/start
curl -s -X POST http://localhost:5009/services/prospect-scout/stop

# Health check
curl -s http://localhost:5009/health | python3 -m json.tool

# Full service status
curl -s http://localhost:5009/services | python3 -m json.tool
```

---

## Voice app setup

The voice app runs as the `cos-voice` supervisord process. It requires:

1. **Accessibility permission** for the process/terminal:
   System Settings → Privacy & Security → Accessibility → add Terminal (or your IDE)

2. **Microphone permission**: macOS will prompt on first recording attempt.

3. **CoS must be running** before the voice app starts — it will show a notification if unreachable.

### Push-to-talk

- Default hotkey: `Cmd+Shift+Space` (toggle — press once to start, once to stop)
- Or click "Start Listening" in the menu bar icon menu
- The Whisper model (`medium`) loads on first use — expect a 5–10s delay the first time

### Customising the hotkey

```bash
# In .env:
PTT_HOTKEY=<ctrl>+<alt>+<space>   # or any pynput-format combo
```

---

## Scheduler

Jobs run in the `America/Toronto` timezone. To view the next scheduled run times, check the CoS startup log:

```bash
grep "next run" logs/cos.log | tail -10
```

| Job | Schedule |
|---|---|
| Morning briefing | Weekdays 07:00 |
| REFLIB weekly digest | Sundays 08:00 |
| REFLIB nightly ingest | Daily 23:00 |
| Health sweep | Every 5 minutes |

To trigger a job on-demand:

```bash
curl -s -X POST http://localhost:5009/command \
  -H 'Content-Type: application/json' \
  -d '{"text": "run morning briefing"}'
```

---

## LLM routing

| Intent | Route | Examples |
|---|---|---|
| `start_service` | Ollama | "start prospect scout" |
| `stop_service` | Ollama | "shut down gilly jobs" |
| `service_status` | Ollama | "what's running?" |
| `schedule_query` | Ollama | "when does the briefing run?" |
| `run_agent` | Claude | "run morning briefing" |
| `general_query` | Claude | "summarise my emails from this morning" |

If Ollama is unavailable, all routes fall back to Claude.

---

## Integrating agent pipelines (Phase 3)

After deploying to the M1, open each file in `cos/agents/` and follow the `INTEGRATION TODO` instructions at the top. Each stub shows the exact pattern for adding a `sys.path.insert` and calling the source pipeline's entry function.

See `PROJECT_STATE.md` Phase 3 for step-by-step instructions per agent.

---

## Troubleshooting

**supervisord won't start:**
- Check for port conflicts: `lsof -i :5009`
- Check the supervisord log: `cat logs/supervisord.log`
- Verify all `directory:` paths in services.yaml exist

**CoS health returns `_error`:**
- supervisord is not running — `supervisord -c supervisord/supervisord.conf`
- Or supervisord inet_http_server is disabled — check supervisord.conf

**Voice app: hotkey not working:**
- Accessibility permission not granted — System Settings → Privacy & Security → Accessibility
- Restart the process after granting permission

**Whisper model download:**
- On first run, faster-whisper downloads the model (~1.5 GB for `medium`) to `~/.cache/huggingface/hub/`
- Ensure internet access is available on first launch
- Model is cached after first download — subsequent starts are instant

**Ollama model not found:**
- Run `ollama list` to see installed models
- Set `OLLAMA_CLASSIFY_MODEL=<listed model name>` in `.env`
- Or pull the default: `ollama pull llama3.2`
