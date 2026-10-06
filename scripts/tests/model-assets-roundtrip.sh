#!/usr/bin/env bash
# Use a fresh database and isolated MinIO; the configured application's data remains untouched.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_DIR}"
set -a
source "${LINSIGHT_ENV_FILE:-.env}"
set +a
MYSQL_CONTAINER="${LINSIGHT_MYSQL_CONTAINER:-linsight-mysql}"
CHECK_DATABASE="linsight_modelcheck_$$"
CHECK_MINIO="linsight-modelcheck-$$"
CHECK_REDIS="linsight-modelcheck-redis-$$"
CHECK_API_PID=""
CHECK_UI_PID=""
CHECK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/linsight-modelcheck.XXXXXX")"
CHECK_ENV="${CHECK_ROOT}/.env"
cleanup() {
  [[ -z "${CHECK_UI_PID}" ]] || kill "${CHECK_UI_PID}" 2>/dev/null || true
  [[ -z "${CHECK_API_PID}" ]] || kill "${CHECK_API_PID}" 2>/dev/null || true
  docker rm -f "${CHECK_REDIS}" >/dev/null 2>&1 || true
  docker rm -f "${CHECK_MINIO}" >/dev/null 2>&1 || true
  docker exec -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${MYSQL_CONTAINER}" \
    mysql -uroot -e "DROP DATABASE IF EXISTS ${CHECK_DATABASE}" >/dev/null 2>&1 || true
  rm -rf "${CHECK_ROOT}"
}
trap cleanup EXIT
printf 'MYSQL_ROOT_PASSWORD=%s\nMINIO_ROOT_USER=linsight-check\nMINIO_ROOT_PASSWORD=%s\n' \
  "${MYSQL_ROOT_PASSWORD}" "$(openssl rand -hex 24)" > "${CHECK_ENV}"
chmod 600 "${CHECK_ENV}"
docker run --rm -d --name "${CHECK_MINIO}" --env-file "${CHECK_ENV}" \
  minio/minio:RELEASE.2025-09-07T16-13-09Z server /data >/dev/null
for attempt in $(seq 1 30); do
  if docker exec "${CHECK_MINIO}" curl -sf http://127.0.0.1:9000/minio/health/live >/dev/null; then
    break
  fi
  sleep 1
done
docker exec -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${MYSQL_CONTAINER}" mysql -uroot \
  -e "CREATE DATABASE ${CHECK_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
docker exec -i -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${MYSQL_CONTAINER}" \
  mysql --default-character-set=utf8mb4 -uroot "${CHECK_DATABASE}" < backend/sql/mysql/linsight.sql
export LINSIGHT_MIGRATION_DATABASE="${CHECK_DATABASE}"
export LINSIGHT_MINIO_CONTAINER="${CHECK_MINIO}"
./scripts/apply-ai-video-migrations.sh > "${CHECK_ROOT}/migrations.log"
for pass in 1 2; do
  python3 scripts/sync-builtin-model-assets.py --register --env-file "${CHECK_ENV}" \
    --output "${CHECK_ROOT}/files" > "${CHECK_ROOT}/import-${pass}.log"
  summary="$(docker exec -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${MYSQL_CONTAINER}" \
    mysql -uroot -N "${CHECK_DATABASE}" -e \
    "SELECT COUNT(*),SUM(publish_status='PUBLISHED'),SUM(execution_status='READY') FROM ai_model_version WHERE deleted=0;")"
  [[ "${summary}" == $'15\t15\t0' ]] || { cat "${CHECK_ROOT}/import-${pass}.log"; exit 1; }
  echo "[pass ${pass}] versions=15 published=15 ready=0"
done
echo "[ok] Clean SQL import, offline weights, version registration and repeat import passed."

if [[ "${LINSIGHT_MODEL_CHECK_UI:-false}" == "true" ]]; then
  docker run --rm -d --name "${CHECK_REDIS}" -p 127.0.0.1::6379 redis:7.4-alpine >/dev/null
  CHECK_REDIS_PORT="$(docker port "${CHECK_REDIS}" 6379/tcp | sed 's/.*://')"
  DB_URL="jdbc:mysql://127.0.0.1:${MYSQL_PORT:-23306}/${CHECK_DATABASE}?useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&nullCatalogMeansCurrent=true" \
    REDIS_PORT="${CHECK_REDIS_PORT}" REDIS_DATABASE=0 LINSIGHT_RUNTIME_ENABLED=false \
    "${JAVA_HOME}/bin/java" -jar backend/linsight-server/target/linsight-server.jar \
    --spring.profiles.active=local --server.port=48889 > "${CHECK_ROOT}/api.log" 2>&1 &
  CHECK_API_PID=$!
  for attempt in $(seq 1 60); do
    if curl -sf http://127.0.0.1:48889/actuator/health >/dev/null; then break; fi
    sleep 1
  done
  curl -sf http://127.0.0.1:48889/actuator/health >/dev/null || { tail -30 "${CHECK_ROOT}/api.log"; exit 1; }
  (
    cd frontend/apps/web-antd
    export LINSIGHT_DEV_PROXY_TARGET=http://127.0.0.1:48889
    export npm_lifecycle_script='vite --mode development'
    exec node ../../node_modules/vite/bin/vite.js --mode development --host 127.0.0.1 --port 5667 --strictPort
  ) > "${CHECK_ROOT}/ui.log" 2>&1 &
  CHECK_UI_PID=$!
  for attempt in $(seq 1 30); do
    if curl -sf http://127.0.0.1:5667 >/dev/null; then break; fi
    sleep 1
  done
  curl -sf http://127.0.0.1:5667 >/dev/null || { tail -30 "${CHECK_ROOT}/ui.log"; exit 1; }
  LINSIGHT_E2E_URL=http://127.0.0.1:5667 node frontend/tests/e2e/model-initialization.mjs
fi
