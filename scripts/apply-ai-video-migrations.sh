#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${LINSIGHT_ENV_FILE:-${PROJECT_DIR}/.env}"
MIGRATION_DIR="${PROJECT_DIR}/backend/sql/mysql/migrations/ai-video"
MYSQL_CONTAINER="${LINSIGHT_MYSQL_CONTAINER:-linsight-mysql}"
MYSQL_DATABASE="${LINSIGHT_MIGRATION_DATABASE:-linsight}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少环境文件：${ENV_FILE}。请先执行 make init。" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-linsight_dev}"

mysql_exec() {
  docker exec -i -e MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${MYSQL_CONTAINER}" \
    mysql --default-character-set=utf8mb4 --batch --skip-column-names \
    -uroot "${MYSQL_DATABASE}" "$@"
}

if ! docker inspect -f '{{.State.Running}}' "${MYSQL_CONTAINER}" 2>/dev/null | grep -qx true; then
  echo "MySQL 容器 ${MYSQL_CONTAINER} 未运行。" >&2
  exit 1
fi

mysql_exec <<'SQL'
CREATE TABLE IF NOT EXISTS `infra_schema_migration` (
  `version` varchar(32) NOT NULL COMMENT '迁移版本',
  `filename` varchar(255) NOT NULL COMMENT '迁移文件名',
  `checksum` char(64) NOT NULL COMMENT '迁移文件 SHA-256',
  `applied_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '执行时间',
  PRIMARY KEY (`version`),
  UNIQUE KEY `uk_infra_schema_migration_filename` (`filename`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='基础设施数据库迁移记录';
SQL

while IFS= read -r migration_file; do
  filename="$(basename "${migration_file}")"
  version="${filename%%__*}"
  version="${version#V}"
  checksum="$(shasum -a 256 "${migration_file}" | awk '{print $1}')"
  recorded_checksum="$(mysql_exec -e "SELECT checksum FROM infra_schema_migration WHERE version = '${version}' LIMIT 1;" < /dev/null)"

  if [[ -n "${recorded_checksum}" ]]; then
    if [[ "${recorded_checksum}" != "${checksum}" ]]; then
      echo "迁移 ${filename} 已执行但校验和发生变化，已停止以避免不一致。" >&2
      exit 1
    fi
    echo "[skip] ${filename}"
    continue
  fi

  echo "[apply] ${filename}"
  mysql_exec --show-warnings < "${migration_file}"
  mysql_exec -e "INSERT INTO infra_schema_migration (version, filename, checksum) VALUES ('${version}', '${filename}', '${checksum}');" < /dev/null
done < <(find "${MIGRATION_DIR}" -maxdepth 1 -type f -name 'V*.sql' -print | LC_ALL=C sort)

echo "AI 视频数据库迁移已完成，连接字符集为 utf8mb4。"
