"""
Centralized logging configuration. When use_cloud_logging is True, attaches
Google Cloud Logging to the root logger so all standard logging goes to GCP.
"""

import logging
import sys

from backend.config import settings


def _ensure_console_handler() -> None:
    """Ensure the root logger has a StreamHandler so local dev sees logs."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        root.addHandler(handler)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root.setLevel(level)


def _already_has_cloud_handler(root: logging.Logger) -> bool:
    """Return True if root already has a Cloud Logging handler (idempotency)."""
    for h in root.handlers:
        if type(h).__name__ == "CloudLoggingHandler":
            return True
    return False


def configure_logging() -> None:
    """
    Configure logging once at startup. If use_cloud_logging is True, attach
    Google Cloud Logging to the root logger; otherwise ensure a console
    handler. Safe to call multiple times (idempotent).
    """
    root = logging.getLogger()

    if not settings.use_cloud_logging:
        _ensure_console_handler()
        return

    if _already_has_cloud_handler(root):
        return

    try:
        import google.cloud.logging
    except ImportError:
        # Library not installed; fall back to console
        _ensure_console_handler()
        return

    try:
        client = google.cloud.logging.Client()
        client.setup_logging()
        level = getattr(logging, settings.log_level.upper(), logging.INFO)
        root.setLevel(level)
    except Exception as exc:
        # Misconfigured GCP or missing ADC; fall back to console so app keeps running
        _ensure_console_handler()
        root.warning(
            "Cloud Logging setup failed, using console: %s",
            exc,
            exc_info=False,
        )
