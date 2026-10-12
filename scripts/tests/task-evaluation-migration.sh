#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_CONTAINER="linsight-evaluation-test-$$"
trap 'docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true' EXIT
docker run --detach --network none --name "$TEST_CONTAINER" --env MYSQL_ALLOW_EMPTY_PASSWORD=yes mysql:8.4 >/dev/null
for attempt in $(seq 1 60); do
  if docker exec "$TEST_CONTAINER" mysqladmin ping --silent >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$TEST_CONTAINER" mysql -e 'CREATE DATABASE evaluation_test;'
for attempt in 1 2; do
  docker exec -i "$TEST_CONTAINER" mysql evaluation_test < "$PROJECT_DIR/backend/sql/mysql/migrations/ai-video/V202610121000__independent_task_evaluations.sql"
done
TEST_INSERT="INSERT INTO ai_task_evaluation (tenant_id,task_id,task_name,config_version,request_id,request_hash,source,status,dataset_version,dataset_sha256,measured_at_millis,evidence_ref,measurement,configuration_snapshot,failed_checks) VALUES"
TEST_VALUES="(1,'task',3,'request-0000000001',REPEAT('a',64),'MANUAL_VIDEO','FAIL','dataset-v1',REPEAT('b',64),1700000000000,'reports/1.json','{\"metrics\":{\"endToEndP95Ms\":8500}}','{\"schemaVersion\":\"1.0\"}','[\"endToEndP95Ms\"]')"
# The suffix starts with task_id, while tenant_id is supplied independently.
TEST_SUFFIX="${TEST_VALUES#(}"
docker exec "$TEST_CONTAINER" mysql evaluation_test -e "$TEST_INSERT (11,$TEST_SUFFIX, (22,$TEST_SUFFIX;"
if docker exec "$TEST_CONTAINER" mysql evaluation_test -e "$TEST_INSERT (11,$TEST_SUFFIX;" >/dev/null 2>&1; then
  echo 'FAIL: duplicate tenant/task/request accepted' >&2
  exit 1
fi
TEST_RESULT="$(docker exec "$TEST_CONTAINER" mysql --batch --skip-column-names evaluation_test -e "SELECT COUNT(*), SUM(JSON_EXTRACT(measurement, '$.metrics.endToEndP95Ms') = 8500) FROM ai_task_evaluation;")"
[[ "$TEST_RESULT" == $'2\t2' ]]
TEST_INDEXES="$(docker exec "$TEST_CONTAINER" mysql --batch --skip-column-names evaluation_test -e "SELECT COUNT(DISTINCT INDEX_NAME) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='evaluation_test' AND TABLE_NAME='ai_task_evaluation';")"
[[ "$TEST_INDEXES" == '4' ]]
echo 'PASS: MySQL 8.4 fresh/repeated migration, JSON persistence, tenant-scoped idempotency and indexes'
