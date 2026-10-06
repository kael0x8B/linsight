FROM python:3.12-slim-bookworm
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    systemd systemd-sysv dbus ffmpeg curl libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
ENV container=docker
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
