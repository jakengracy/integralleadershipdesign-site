"""
cos/service_manager.py — Thin wrapper around supervisord's XML-RPC interface.

supervisord exposes an XML-RPC API at localhost:9001/RPC2 (configured in
supervisord.conf's [inet_http_server] section). This module is the only place
in CoS that talks to supervisord directly — all other modules go through here.

supervisord process states (returned by getProcessInfo):
    STOPPED, STARTING, RUNNING, BACKOFF, STOPPING, EXITED, FATAL, UNKNOWN
"""

import logging
import xmlrpc.client
from typing import Optional

from cos.config import SUPERVISORD_URL

logger = logging.getLogger(__name__)


class ServiceManager:
    """
    Client for the supervisord XML-RPC API.

    All public methods return plain dicts so callers don't need to handle
    XML-RPC types. Errors are caught and returned as {"success": False, "error": "..."}
    rather than raised — the CoS HTTP layer will surface them to the caller.
    """

    def __init__(self, url: str = SUPERVISORD_URL):
        self._url = url
        # Proxy is created lazily so we don't fail at import if supervisord is down
        self._proxy: Optional[xmlrpc.client.ServerProxy] = None

    def _get_proxy(self) -> xmlrpc.client.ServerProxy:
        """Return (or create) the XML-RPC proxy. One proxy per manager instance."""
        if self._proxy is None:
            self._proxy = xmlrpc.client.ServerProxy(self._url)
        return self._proxy

    def _call(self, method: str, *args):
        """
        Call a method on proxy.supervisor, returning (result, error_string).
        error_string is None on success; result is None on failure.
        This wrapper means every public method gets uniform error handling.
        """
        try:
            proxy = self._get_proxy()
            fn    = getattr(proxy.supervisor, method)
            return fn(*args), None

        except xmlrpc.client.Fault as e:
            # supervisord-level fault (e.g. process not found, wrong state)
            msg = f"supervisord fault in {method}({args}): [{e.faultCode}] {e.faultString}"
            logger.error(msg)
            return None, msg

        except ConnectionRefusedError:
            # supervisord is not running or inet_http_server is off
            msg = f"Cannot reach supervisord at {self._url} — is supervisord running?"
            logger.error(msg)
            self._proxy = None  # Force reconnect on next call
            return None, msg

        except OSError as e:
            msg = f"Network error calling supervisord.{method}: {e}"
            logger.error(msg)
            self._proxy = None
            return None, msg

        except Exception as e:
            msg = f"Unexpected error calling supervisord.{method}({args}): {e}"
            logger.exception(msg)
            return None, msg

    # ── Process control ────────────────────────────────────────────────────────

    def start(self, name: str) -> dict:
        """
        Start a named supervisord program.
        supervisord returns True on success; raises a fault if already running.
        """
        result, error = self._call("startProcess", name)
        if error:
            return {"success": False, "name": name, "error": error}
        logger.info(f"Started service: {name}")
        return {"success": True, "name": name}

    def stop(self, name: str) -> dict:
        """
        Stop a named supervisord program.
        supervisord returns True on success; raises a fault if already stopped.
        """
        result, error = self._call("stopProcess", name)
        if error:
            return {"success": False, "name": name, "error": error}
        logger.info(f"Stopped service: {name}")
        return {"success": True, "name": name}

    def restart(self, name: str) -> dict:
        """
        Restart a named program: stop it (ignoring 'not running' faults),
        then start it fresh.
        """
        stop_result = self.stop(name)
        if not stop_result["success"]:
            # NOT_RUNNING is acceptable here — we still want to start it
            logger.warning(f"stop({name}) returned an error — attempting start anyway")

        return self.start(name)

    # ── Status queries ─────────────────────────────────────────────────────────

    def status(self, name: str) -> dict:
        """
        Return current state info for a single named process.
        The 'state' field uses supervisord's statenames: RUNNING, STOPPED, etc.
        """
        result, error = self._call("getProcessInfo", name)
        if error:
            return {"name": name, "state": "UNKNOWN", "error": error}

        start_ts = result.get("start", 0)
        now_ts   = result.get("now", 0)

        return {
            "name":        result.get("name"),
            "state":       result.get("statename"),
            "pid":         result.get("pid"),
            "uptime_secs": (now_ts - start_ts) if start_ts else 0,
            "description": result.get("description"),
        }

    def status_all(self) -> dict:
        """
        Return a dict keyed by service name with state info for every supervised
        process. Used by GET /health and GET /services.
        """
        result, error = self._call("getAllProcessInfo")
        if error:
            # Return the error in a way that's still JSON-serialisable
            return {"_error": error, "_supervisord_url": self._url}

        return {
            p["name"]: {
                "state":       p.get("statename"),
                "pid":         p.get("pid"),
                "uptime_secs": (p.get("now", 0) - p.get("start", 0)) if p.get("start") else 0,
            }
            for p in result
        }

    def is_running(self, name: str) -> bool:
        """Convenience helper — returns True only if the process is in RUNNING state."""
        info = self.status(name)
        return info.get("state") == "RUNNING"


# Module-level singleton — other modules import `manager` and call it directly
manager = ServiceManager()
