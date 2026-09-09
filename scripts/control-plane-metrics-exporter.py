#!/usr/bin/env python3
"""Expose existing authenticated LInsight admin projections as low-cardinality metrics."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

CORE_ALGORITHMS = {
    72001: "safety-helmet",
    72002: "reflective-vest",
    72003: "smoking-detection",
    72004: "phone-call-detection",
    72005: "person-intrusion",
    72006: "area-intrusion",
    72007: "fall-detection",
    72008: "flame",
    72009: "vehicle-detection",
    72010: "license-plate",
    72011: "person-off-duty",
}


class Collector:
    def __init__(self, base_url: str, token: str, cache_seconds: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._updated = 0.0
        self._cached = "linsight_control_plane_exporter_up 0\n"

    def get(self, path: str, **parameters: Any) -> Any:
        query = urllib.parse.urlencode({"pageNo": 1, "pageSize": 1, **parameters})
        request = urllib.request.Request(
            f"{self.base_url}{path}?{query}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
        if response.status != 200 or payload.get("code") != 0:
            raise ValueError(f"control-plane request failed for {path}")
        return payload.get("data")

    def total(self, path: str, **parameters: Any) -> int:
        value = self.get(path, **parameters)
        if not isinstance(value, dict) or not isinstance(value.get("total"), int):
            raise ValueError(f"control-plane page response is invalid for {path}")
        return value["total"]

    def collect(self) -> str:
        with self._lock:
            if time.monotonic() - self._updated < self.cache_seconds:
                return self._cached
            try:
                lines = ["# TYPE linsight_control_plane_exporter_up gauge", "linsight_control_plane_exporter_up 1"]
                cameras = self.total("/admin-api/ai-video/camera/page")
                online = self.total("/admin-api/ai-video/camera/page", onlineStatus=1)
                lines.extend(
                    [
                        "# TYPE linsight_camera_total gauge",
                        f"linsight_camera_total {cameras}",
                        "# TYPE linsight_camera_online gauge",
                        f"linsight_camera_online {online}",
                        "# TYPE linsight_camera_offline gauge",
                        f"linsight_camera_offline {max(0, cameras - online)}",
                    ]
                )
                for state in ("RUNNING", "FAILED", "OFFLINE"):
                    total = self.total("/admin-api/ai-video/task/page", actualStatus=state)
                    lines.append(f'linsight_task_total{{status="{state.lower()}"}} {total}')
                for algorithm_id, code in CORE_ALGORITHMS.items():
                    total = self.total("/admin-api/ai-video/event/page", algorithmId=algorithm_id)
                    lines.append(f'linsight_algorithm_events{{algorithm="{code}"}} {total}')
                nodes = self.get("/admin-api/ai-video/node/list")
                if not isinstance(nodes, list):
                    raise ValueError("node list response is invalid")
                node_online = sum(str(value.get("onlineStatus", "")).upper() in {"1", "ONLINE"} for value in nodes)
                lines.extend(
                    [
                        f'linsight_edge_nodes{{status="online"}} {node_online}',
                        f'linsight_edge_nodes{{status="offline"}} {len(nodes) - node_online}',
                    ]
                )
                self._cached = "\n".join(lines) + "\n"
            except (OSError, ValueError, json.JSONDecodeError):
                self._cached = "# TYPE linsight_control_plane_exporter_up gauge\nlinsight_control_plane_exporter_up 0\n"
            self._updated = time.monotonic()
            return self._cached


class Handler(BaseHTTPRequestHandler):
    collector: Collector

    def do_GET(self) -> None:
        if self.path != "/metrics":
            self.send_error(404)
            return
        payload = self.collector.collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-plane-url", default="http://127.0.0.1:48888")
    parser.add_argument("--token-env", default="LINSIGHT_METRICS_ACCESS_TOKEN")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=49100)
    parser.add_argument("--cache-seconds", type=float, default=30)
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.control_plane_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        parser.error("control-plane URL must be credential-free HTTP(S)")
    token = os.environ.get(args.token_env)
    if not token:
        parser.error(f"missing token environment variable: {args.token_env}")
    Handler.collector = Collector(args.control_plane_url, token, args.cache_seconds)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
