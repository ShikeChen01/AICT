"""
Central logging facade for backend modules.

Provides:
- configure_logging(): one-time startup logging configuration
- get_logger(): module logger factory used across the backend
- ws_backend_log_stream: websocket log stream export for broadcaster startup
"""

from __future__ import annotations

import logging
import sys

from backend.config import settings
from backend.core.ws_backend_log_stream import ws_backend_log_handler, ws_backend_log_stream


def _root_level() -> int:
    return getattr(logging, settings.log_level.upper(), logging.INFO)


def _ensure_console_handler() -> None:
    """Ensure local/dev environments always have a console handler."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(_root_level())


def _attach_ws_handler_once() -> None:
    root = logging.getLogger()
    if not any(handler is ws_backend_log_handler for handler in root.handlers):
        root.addHandler(ws_backend_log_handler)


def configure_logging() -> None:
    """
    Configure process logging.

    Uses Google Cloud Logging when enabled and available; otherwise falls back
    to stderr console logging. In all cases, mirrors root logs to websocket.
    """
    logging.captureWarnings(True)

    if not settings.use_cloud_logging:
        _ensure_console_handler()
    else:
        try:
            import google.cloud.logging

            client = google.cloud.logging.Client()
            client.setup_logging(log_level=_root_level())
        except ImportError:
            print(
                "google-cloud-logging not installed, falling back to console logging",
                file=sys.stderr,
            )
            _ensure_console_handler()
        except Exception as exc:
            print(f"Failed to setup cloud logging: {exc}", file=sys.stderr)
            _ensure_console_handler()

    _attach_ws_handler_once()


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a module logger from the standard logging hierarchy."""
    return logging.getLogger(name)
