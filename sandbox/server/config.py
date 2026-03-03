"""Sandbox server configuration — loaded from environment variables."""

import os

AUTH_TOKEN: str = os.environ.get("AUTH_TOKEN", "")
PORT: int = int(os.environ.get("PORT", "8080"))
DISPLAY: str = os.environ.get("DISPLAY", ":99")

# Ring buffer: max bytes retained in memory per shell session
RING_BUFFER_BYTES: int = 1 * 1024 * 1024  # 1 MB

# Screenshot quality (1=best, 31=worst)
SCREENSHOT_QUALITY: int = 5

# Screen resolution for Xvfb
SCREEN_WIDTH: int = 1024
SCREEN_HEIGHT: int = 768
SCREEN_DEPTH: int = 24

# Recording settings
RECORD_FPS: int = 2
RECORD_OUTPUT: str = "/tmp/recording.mp4"

# Screen streaming settings
STREAM_FPS: int = 3
STREAM_QUALITY: int = 8  # JPEG quality for streaming (1=best, 31=worst)
