#!/usr/bin/env python3
"""Authenticated management API load probe; credentials are read from the environment."""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINTS = (
    "/admin-api/ai-video/algorithm/simple-list",
    "/admin-api/ai-video/camera/page?pageNo=1&pageSize=10",
    "/admin-api/ai-video/model/page?pageNo=1&pageSize=10",
    "/admin-api/ai-video/task/page?pageNo=1&pageSize=10",
    "/admin-api/ai-video/event/page?pageNo=1&pageSize=10",
    "/admin-api/ai-video/node/simple-list",
)


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile_value) - 1)
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Load-test authenticated LInsight admin APIs")
    parser.add_argument("--base-url", default="http://127.0.0.1:48888")
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--tenant-id", default="1")
    parser.add_argument("--token-env", default="LINSIGHT_LOAD_ACCESS_TOKEN")
    parser.add_argument("--endpoint", action="append", dest="endpoints")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/load/admin-api-local.json"
    )
    parser.add_argument("--environment", default="LOCAL_ENGINEERING")
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests and --concurrency must be positive")
    token = os.environ.get(args.token_env)
    if not token:
        print(f"missing access token environment variable: {args.token_env}", file=sys.stderr)
        return 2
    endpoints = tuple(args.endpoints or DEFAULT_ENDPOINTS)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def invoke(sequence: int) -> dict:
        endpoint = endpoints[sequence % len(endpoints)]
        url = urllib.parse.urljoin(args.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "tenant-id": args.tenant_id,
                "Accept": "application/json",
            },
        )
        started = time.perf_counter()
        http_status = 0
        application_code = None
        try:
            with opener.open(request, timeout=10) as response:
                http_status = response.status
                body = json.loads(response.read())
                application_code = body.get("code") if isinstance(body, dict) else None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "endpoint": endpoint,
            "durationMs": duration_ms,
            "httpStatus": http_status,
            "applicationCode": application_code,
            "success": http_status == 200 and application_code == 0,
        }

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(invoke, range(args.requests)))
    wall_seconds = time.perf_counter() - started
    by_endpoint: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_endpoint[result["endpoint"]].append(result)

    def summarize(values: list[dict]) -> dict:
        durations = [value["durationMs"] for value in values]
        statuses = Counter(str(value["httpStatus"]) for value in values)
        return {
            "requests": len(values),
            "success": sum(value["success"] for value in values),
            "httpStatuses": dict(sorted(statuses.items())),
            "p50Ms": round(percentile(durations, 0.50), 2),
            "p95Ms": round(percentile(durations, 0.95), 2),
            "maxMs": round(max(durations), 2),
        }

    overall = summarize(results)
    passed = overall["success"] == args.requests and overall["p95Ms"] < 500
    report = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(UTC).isoformat(),
        "environment": args.environment,
        "baseUrl": args.base_url,
        "concurrency": args.concurrency,
        "wallSeconds": round(wall_seconds, 3),
        "throughputRps": round(args.requests / wall_seconds, 2),
        "status": "PASS" if passed else "FAIL",
        "target": {"successRate": 1.0, "p95MsLessThan": 500},
        "overall": overall,
        "endpoints": {
            endpoint: summarize(values) for endpoint, values in sorted(by_endpoint.items())
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
