FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        xdotool \
        ffmpeg \
        xdpyinfo \
        python3 \
        python3-pip \
        python3-venv \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY server/ /opt/sandbox-server/

RUN pip3 install --no-cache-dir -r /opt/sandbox-server/requirements.txt

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /opt/sandbox-server

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
