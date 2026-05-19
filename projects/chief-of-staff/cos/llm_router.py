"""
cos/llm_router.py — Routes tasks to Ollama (local, fast) or Claude (cloud, capable).

Routing logic:
    Ollama handles: start_service, stop_service, service_status, schedule_query
    Claude handles: run_agent, general_query

The split reflects cost and latency — mechanical tasks (start this, what's running)
don't need Claude's reasoning. Synthesis, summarisation, and complex queries do.

IMPORTANT: Run `ollama list` on first M1 deployment to verify the model name
set in OLLAMA_CLASSIFY_MODEL. The default is 'llama3.2'. Swap it in .env if needed.
"""

import json
import logging

import requests

from cos.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_CLASSIFY_MODEL,
)

logger = logging.getLogger(__name__)


# ── Intent definitions ─────────────────────────────────────────────────────────
# These are the valid intent strings the classifier can return.
# Keep this in sync with the prompt below.
INTENTS = {
    "start_service",
    "stop_service",
    "service_status",
    "run_agent",
    "schedule_query",
    "general_query",
}

# Intents handled mechanically by Ollama (no Claude needed)
OLLAMA_INTENTS = {"start_service", "stop_service", "service_status", "schedule_query"}
# Intents that need Claude's synthesis/reasoning
CLAUDE_INTENTS  = {"run_agent", "general_query"}


# ── Classify ───────────────────────────────────────────────────────────────────

# System prompt for the Ollama classifier.
# Instructs the model to output only valid JSON with the expected fields.
_CLASSIFY_SYSTEM = """\
You are an intent classifier for a local AI orchestration system called Chief of Staff.
Given a natural language command, return ONLY a JSON object with these exact fields:

{
  "intent": "<one of: start_service, stop_service, service_status, run_agent, schedule_query, general_query>",
  "target_service": "<service name or null>",
  "complexity": "<simple or complex>",
  "confidence": <0.0 to 1.0>
}

Known services: prospect-scout, signal-app, reflib-agent, agentic-inbox, task-agents,
               gilly-jobs, corp-accounting, equity-thesis-tracker, chief-of-staff.
Known agents:   morning_briefing, reflib_digest, reflib_nightly, email_triage, gilly_jobs.

Rules:
- intent = start_service if the command asks to start, launch, bring up, or enable a service
- intent = stop_service if the command asks to stop, shut down, kill, or disable a service
- intent = service_status if the command asks what is running, status, or health
- intent = run_agent if the command asks to run morning briefing, digest, triage, or gilly jobs
- intent = schedule_query if the command asks about schedules, next run times, or cron jobs
- intent = general_query for everything else
- target_service = the normalised service/agent name, or null if not applicable
- complexity = simple for mechanical one-step actions; complex for multi-step or analytical
- Output valid JSON only. No prose before or after the JSON object.
"""


def classify(text: str) -> dict:
    """
    Classify the intent of a natural language command using Ollama.

    Falls back to a rule-based classifier if Ollama is unavailable,
    so the CoS remains functional even when Ollama is down.

    Returns a dict with keys: intent, target_service, complexity, confidence, route
    """
    # First try Ollama
    try:
        result = _classify_with_ollama(text)
        result["route"] = "ollama" if result["intent"] in OLLAMA_INTENTS else "claude"
        return result
    except OllamaUnavailableError as e:
        logger.warning(f"Ollama unavailable — using rule-based fallback: {e}")
        return _classify_rule_based(text)
    except ClassificationParseError as e:
        logger.warning(f"Ollama returned unparseable JSON — using rule-based fallback: {e}")
        return _classify_rule_based(text)


def _classify_with_ollama(text: str) -> dict:
    """
    Call Ollama's chat API and parse the returned JSON classification.
    Raises OllamaUnavailableError or ClassificationParseError on failure.
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model":  OLLAMA_CLASSIFY_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system",  "content": _CLASSIFY_SYSTEM},
                    {"role": "user",    "content": text},
                ],
                # Ask Ollama to output JSON — supported in llama3.2+
                "format": "json",
            },
            timeout=10,
        )
        response.raise_for_status()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise OllamaUnavailableError(f"Ollama not reachable at {OLLAMA_BASE_URL}: {e}") from e
    except requests.exceptions.HTTPError as e:
        raise OllamaUnavailableError(f"Ollama HTTP error: {e}") from e

    raw_content = response.json().get("message", {}).get("content", "")
    logger.debug(f"Ollama raw classification: {raw_content!r}")

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as e:
        raise ClassificationParseError(f"Could not parse Ollama JSON: {e} — raw: {raw_content!r}")

    # Validate intent field; default to general_query if unknown
    intent = parsed.get("intent", "general_query")
    if intent not in INTENTS:
        logger.warning(f"Unknown intent {intent!r} from Ollama — defaulting to general_query")
        intent = "general_query"

    return {
        "intent":         intent,
        "target_service": parsed.get("target_service"),
        "complexity":     parsed.get("complexity", "simple"),
        "confidence":     float(parsed.get("confidence", 0.8)),
    }


def _classify_rule_based(text: str) -> dict:
    """
    Minimal rule-based fallback when Ollama is unavailable.
    Covers the most common command patterns so CoS stays functional.
    """
    lower = text.lower()

    # Detect intent by keyword scanning
    if any(w in lower for w in ("start", "launch", "bring up", "enable", "turn on")):
        intent = "start_service"
    elif any(w in lower for w in ("stop", "shut down", "shutdown", "kill", "disable", "turn off")):
        intent = "stop_service"
    elif any(w in lower for w in ("status", "running", "health", "up", "what's", "whats")):
        intent = "service_status"
    elif any(w in lower for w in ("briefing", "digest", "triage", "gilly", "reflib nightly")):
        intent = "run_agent"
    elif any(w in lower for w in ("schedule", "next run", "when", "cron")):
        intent = "schedule_query"
    else:
        intent = "general_query"

    # Try to identify target service
    target = _extract_service_name(lower)

    route = "ollama" if intent in OLLAMA_INTENTS else "claude"
    return {
        "intent":         intent,
        "target_service": target,
        "complexity":     "simple",
        "confidence":     0.5,  # Low confidence — rule-based fallback
        "route":          route,
        "_fallback":      True,  # Flag for logging/debugging
    }


def _extract_service_name(text: str) -> str | None:
    """
    Simple substring scan to extract a known service or agent name from text.
    Normalises common aliases (e.g. 'prospect scout' → 'prospect-scout').
    """
    aliases = {
        "prospect scout":          "prospect-scout",
        "prospect-scout":          "prospect-scout",
        "prospectr":               "prospect-scout",
        "signal app":              "signal-app",
        "signal-app":              "signal-app",
        "reflib":                  "reflib-agent",
        "reflib agent":            "reflib-agent",
        "reflib-agent":            "reflib-agent",
        "agentic inbox":           "agentic-inbox",
        "agentic-inbox":           "agentic-inbox",
        "inbox":                   "agentic-inbox",
        "task agents":             "task-agents",
        "task-agents":             "task-agents",
        "gilly jobs":              "gilly-jobs",
        "gilly-jobs":              "gilly-jobs",
        "gilly":                   "gilly-jobs",
        "corp accounting":         "corp-accounting",
        "corp-accounting":         "corp-accounting",
        "equity thesis":           "equity-thesis-tracker",
        "equity-thesis-tracker":   "equity-thesis-tracker",
        "morning briefing":        "morning_briefing",
        "morning-briefing":        "morning_briefing",
        "reflib digest":           "reflib_digest",
        "reflib nightly":          "reflib_nightly",
        "email triage":            "email_triage",
        "email-triage":            "email_triage",
    }
    for alias, canonical in aliases.items():
        if alias in text:
            return canonical
    return None


# ── Respond ────────────────────────────────────────────────────────────────────

def respond(text: str, classification: dict, context: dict) -> str:
    """
    Generate a natural language response given the original command, its
    classification, and the current system context.

    Routes to Ollama or Claude based on classification["route"].
    Falls back to Claude if Ollama is unavailable.
    """
    route = classification.get("route", "claude")

    if route == "ollama":
        try:
            return _respond_with_ollama(text, classification, context)
        except OllamaUnavailableError as e:
            logger.warning(f"Ollama unavailable for response — falling back to Claude: {e}")
            return _respond_with_claude(text, classification, context)
    else:
        return _respond_with_claude(text, classification, context)


def _respond_with_ollama(text: str, classification: dict, context: dict) -> str:
    """
    Generate a short, factual response for mechanical tasks (service control,
    status queries) using the local Ollama model.
    """
    action   = context.get("action_taken", "none")
    services = context.get("service_states", {})

    prompt = (
        f"You are the Chief of Staff system assistant. "
        f"The user said: '{text}'. "
        f"Action taken: {action}. "
        f"Current service states: {services}. "
        f"Respond in one brief, friendly sentence confirming what happened."
    )

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model":  OLLAMA_CLASSIFY_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise OllamaUnavailableError(str(e)) from e


def _respond_with_claude(text: str, classification: dict, context: dict) -> str:
    """
    Generate a rich response for analytical and agent tasks using the Claude API.
    Used for: run_agent, general_query, and all Ollama fallback cases.
    """
    if not ANTHROPIC_API_KEY:
        return (
            "Claude API key is not configured. "
            f"Action taken: {context.get('action_taken', 'none')}."
        )

    import anthropic  # Imported here — only required if Claude routing is used

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    action   = context.get("action_taken", "none")
    services = context.get("service_states", {})

    system_prompt = (
        "You are the Chief of Staff, an AI orchestration assistant running locally "
        "on a Mac Studio M1 Ultra. You manage local AI services and pipelines. "
        "Be concise, direct, and professional. "
        "If an action was taken, confirm it. If an agent ran, summarise the result. "
        "Keep responses under 3 sentences unless the user explicitly asked for more detail."
    )

    user_message = (
        f"Command: {text}\n"
        f"Intent classification: {classification}\n"
        f"Action taken: {action}\n"
        f"Current service states: {services}"
    )

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.exception("Claude API call failed")
        return f"Claude API error: {e}. Action taken: {action}."


# ── Exceptions ─────────────────────────────────────────────────────────────────

class OllamaUnavailableError(Exception):
    """Raised when the Ollama server cannot be reached."""


class ClassificationParseError(Exception):
    """Raised when Ollama returns a response that cannot be parsed as classification JSON."""
