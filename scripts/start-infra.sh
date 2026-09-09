#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker compose --env-file "${PROJECT_DIR}/.env" \
  -f "${PROJECT_DIR}/deploy/docker-compose.dev.yml" up -d --wait
"${PROJECT_DIR}/scripts/apply-ai-video-migrations.sh"
docker compose --env-file "${PROJECT_DIR}/.env" \
  -f "${PROJECT_DIR}/deploy/docker-compose.dev.yml" ps
