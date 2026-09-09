#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker compose --env-file "${PROJECT_DIR}/.env" \
  -f "${PROJECT_DIR}/deploy/docker-compose.dev.yml" ps

curl --fail --silent --show-error http://127.0.0.1:48888/actuator/health
printf '\n'
curl --fail --silent --show-error --head http://127.0.0.1:5666 | head -n 1
