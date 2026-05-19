"""
cos/app.py — Flask HTTP interface for the Chief of Staff agent.

This is the single inbound gateway for all CoS interactions:
  - Voice layer POSTs transcripts here (/command)
  - Scheduled jobs trigger agent modules here (via internal calls, not HTTP)
  - Tailscale remote access hits these endpoints
  - Direct curl commands during development

Flask is intentionally thin here — business logic lives in the router and agents.
"""

import importlib
import logging

from flask import Flask, jsonify, request

from cos.config import COS_HOST, COS_PORT, LOG_LEVEL, LOG_DIR
from cos.service_manager import manager as svc
from cos.llm_router import classify, respond

# ── Logging setup ──────────────────────────────────────────────────────────────
# Configure root logger once here; all other modules inherit this config.
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(name)-20s] %(levelname)-8s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "cos.log"),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ── Internal agent dispatch map ────────────────────────────────────────────────
# Maps the classifier's target_service strings to (module_path, function_name).
# Add entries here when new agent modules are added to cos/agents/.
AGENT_DISPATCH: dict[str, tuple[str, str]] = {
    "morning_briefing": ("cos.agents.morning_briefing", "run_morning_briefing"),
    "reflib_digest":    ("cos.agents.reflib_digest",    "run_weekly_digest"),
    "reflib_nightly":   ("cos.agents.reflib_digest",    "run_nightly_ingest"),
    "email_triage":     ("cos.agents.email_triage",     "run_email_triage"),
    "gilly_jobs":       ("cos.agents.gilly_jobs",       "run_gilly_jobs"),
}


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """
    Liveness + service state in one call.
    A single curl to this endpoint shows whether CoS is up and what supervisord
    thinks of every managed process.
    """
    return jsonify({
        "status": "ok",
        "services": svc.status_all(),
    })


@app.route("/services", methods=["GET"])
def list_services():
    """Full service status dict — same data as /health.services, separate route."""
    return jsonify(svc.status_all())


@app.route("/services/<name>/start", methods=["POST"])
def start_service(name: str):
    """Start a named supervisord process directly (no LLM routing)."""
    result = svc.start(name)
    return jsonify(result), (200 if result["success"] else 500)


@app.route("/services/<name>/stop", methods=["POST"])
def stop_service(name: str):
    """Stop a named supervisord process directly."""
    result = svc.stop(name)
    return jsonify(result), (200 if result["success"] else 500)


@app.route("/services/<name>/restart", methods=["POST"])
def restart_service(name: str):
    """Restart a named supervisord process."""
    result = svc.restart(name)
    return jsonify(result), (200 if result["success"] else 500)


@app.route("/command", methods=["POST"])
def command():
    """
    Primary natural language command endpoint.

    The voice app, Tailscale remote clients, and test curls all come here.
    Flow:
        1. Parse text from request body
        2. classify() — Ollama determines intent and routing
        3. Execute mechanical actions (start/stop service) directly
        4. Dispatch agent modules if intent is run_agent
        5. respond() — LLM generates a natural language reply
        6. Return structured JSON (response text + classification + action taken)

    Body:    {"text": "start prospect scout"}
    Returns: {"response": "...", "action_taken": "...", "classification": {...}}
    """
    body = request.get_json(silent=True)
    if not body or "text" not in body:
        return jsonify({"error": "Request body must contain a 'text' field"}), 400

    text = body["text"].strip()
    if not text:
        return jsonify({"error": "'text' cannot be empty"}), 400

    logger.info(f"Command received: {text!r}")

    # ── Step 1: classify intent ────────────────────────────────────────────────
    try:
        classification = classify(text)
    except Exception as e:
        logger.exception("Classification failed")
        return jsonify({"error": f"Classification error: {e}"}), 500

    logger.info(f"Classification: {classification}")
    intent         = classification.get("intent", "general_query")
    target_service = classification.get("target_service")
    action_taken   = None

    # ── Step 2: execute mechanical actions ────────────────────────────────────
    # These don't need an LLM response — just do the thing and record what happened.
    if intent == "start_service" and target_service:
        result = svc.start(target_service)
        action_taken = f"start:{target_service}:{result}"

    elif intent == "stop_service" and target_service:
        result = svc.stop(target_service)
        action_taken = f"stop:{target_service}:{result}"

    elif intent == "run_agent" and target_service:
        # Agent dispatch is synchronous for now — long-running agents should
        # be made async (return a job ID) in a future iteration if needed
        action_taken = _dispatch_agent(target_service)

    # ── Step 3: generate natural language response ────────────────────────────
    context = {
        "classification": classification,
        "action_taken":   action_taken,
        "service_states": svc.status_all(),
    }

    try:
        response_text = respond(text, classification, context)
    except Exception as e:
        logger.exception("LLM response generation failed")
        # Degrade gracefully — return factual action summary without LLM prose
        response_text = (
            f"Action: {action_taken or 'none'}. "
            f"LLM unavailable: {e}. "
            f"Service states: {context['service_states']}"
        )

    return jsonify({
        "response":       response_text,
        "action_taken":   action_taken,
        "classification": classification,
    })


# ── Internal helpers ───────────────────────────────────────────────────────────

def _dispatch_agent(agent_name: str) -> str:
    """
    Dynamically import and call the named agent module function.
    Returns a summary string for inclusion in the LLM context.
    Agent functions receive an empty context dict by default;
    the scheduler passes richer context when it triggers agents.
    """
    if agent_name not in AGENT_DISPATCH:
        logger.warning(f"Unknown agent requested: {agent_name!r}")
        return f"unknown agent: {agent_name}"

    module_path, func_name = AGENT_DISPATCH[agent_name]
    logger.info(f"Dispatching agent: {agent_name} ({module_path}.{func_name})")

    try:
        module = importlib.import_module(module_path)
        func   = getattr(module, func_name)
        result = func(context={})
        summary = result.get("summary", "completed") if isinstance(result, dict) else str(result)
        logger.info(f"Agent {agent_name} result: {summary}")
        return f"{agent_name}:{result.get('status','ok')}:{summary}"
    except Exception as e:
        logger.exception(f"Agent {agent_name} raised an exception")
        return f"{agent_name}:error:{e}"
