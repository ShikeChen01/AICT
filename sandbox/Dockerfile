FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

# ── Base system + Xvfb + tools ────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        xdotool \
        ffmpeg \
        x11-utils \
        x11-xserver-utils \
        x11vnc \
        openbox \
        dbus-x11 \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        git \
        ca-certificates \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# ── Google Chrome (headed browser — chromium-browser is a snap stub on 22.04) ─
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
        https://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        google-chrome-stable \
        fonts-liberation \
        fonts-noto-color-emoji \
        fonts-noto-cjk \
        libnss3 \
        libatk-bridge2.0-0 \
        libxss1 \
    && rm -rf /var/lib/apt/lists/*

COPY server/ /opt/sandbox-server/

RUN pip3 install --no-cache-dir -r /opt/sandbox-server/requirements.txt

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

WORKDIR /opt/sandbox-server

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
