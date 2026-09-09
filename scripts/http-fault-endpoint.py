#!/usr/bin/env python3
"""Local HTTP fault endpoint for 429/500/timeout offline replay tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FaultHandler(BaseHTTPRequestHandler):
    mode = "500"
    delay_seconds = 30.0
    log_path = Path("fault-http-requests.jsonl")

    def do_GET(self) -> None:
        self._respond()

    def do_POST(self) -> None:
        self._respond()

    def do_PUT(self) -> None:
        self._respond()

    def _respond(self) -> None:
        length = min(int(self.headers.get("Content-Length", "0") or 0), 16 * 1024 * 1024)
        body = self.rfile.read(length) if length else b""
        record = {
            "observedAt": datetime.now(UTC).isoformat(),
            "method": self.command,
            "path": self.path.split("?", 1)[0],
            "bodyBytes": len(body),
            "bodySha256": hashlib.sha256(body).hexdigest(),
            "idempotencyKey": self.headers.get("Idempotency-Key"),
            "mode": self.mode,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        if self.mode == "timeout":
            time.sleep(self.delay_seconds)
            return
        status = 429 if self.mode == "429" else 500
        payload = json.dumps({"code": status, "msg": f"injected HTTP {status}"}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if status == 429:
            self.send_header("Retry-After", "1")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("429", "500", "timeout"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=49800)
    parser.add_argument("--delay-seconds", type=float, default=30)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    FaultHandler.mode = args.mode
    FaultHandler.delay_seconds = args.delay_seconds
    FaultHandler.log_path = args.log
    ThreadingHTTPServer((args.host, args.port), FaultHandler).serve_forever()


if __name__ == "__main__":
    main()
