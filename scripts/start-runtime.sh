#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${PROJECT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
  set +a
fi

if [[ "${LINSIGHT_RUNTIME_ENABLED:-false}" != "true" ]]; then
  echo "LINSIGHT_RUNTIME_ENABLED must be true in .env" >&2
  exit 1
fi
if [[ -z "${LINSIGHT_RUNTIME_API_KEY:-}" ]]; then
  echo "LINSIGHT_RUNTIME_API_KEY must be configured in .env" >&2
  exit 1
fi

exec "${PROJECT_DIR}/runtime/.venv/bin/python" -m uvicorn \
  ai_runtime.app.main:create_app --factory \
  --app-dir "${PROJECT_DIR}/runtime" --host 127.0.0.1 --port 48900
