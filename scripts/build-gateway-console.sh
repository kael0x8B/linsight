#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${SOURCE_DATE_EPOCH:-}" ]]; then
  SOURCE_DATE_EPOCH="$(git -C "${PROJECT_DIR}" log -1 --format=%ct 2>/dev/null || true)"
fi
if [[ ! "${SOURCE_DATE_EPOCH}" =~ ^[0-9]+$ ]]; then
  echo "SOURCE_DATE_EPOCH must be set when the source is not in a Git checkout" >&2
  exit 1
fi
export SOURCE_DATE_EPOCH
cd "${PROJECT_DIR}/frontend"
corepack pnpm@11.7.0 --filter @vben/vite-config stub
corepack pnpm@11.7.0 --filter @linsight/console build
python3 "${PROJECT_DIR}/runtime/ai_runtime/app/gateway/console_artifact.py" build \
  --dist "${PROJECT_DIR}/frontend/apps/web-antd/dist" \
  --source-root "${PROJECT_DIR}/frontend" \
  --bundle-dir "${PROJECT_DIR}/runtime/gateway-console"
echo "Gateway console artifact: ${PROJECT_DIR}/runtime/gateway-console/manifest.json"
