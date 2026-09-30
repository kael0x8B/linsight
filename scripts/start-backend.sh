#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${PROJECT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
  set +a
fi
if [[ -z "${JAVA_HOME:-}" && -x /usr/libexec/java_home ]]; then
  export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
fi
if [[ -n "${JAVA_HOME:-}" ]]; then
  export PATH="${JAVA_HOME}/bin:${PATH}"
fi
export LINSIGHT_NODE_DEPLOYMENT_RUNTIME_SOURCE="${LINSIGHT_NODE_DEPLOYMENT_RUNTIME_SOURCE:-${PROJECT_DIR}/runtime}"

cd "${PROJECT_DIR}/backend"
mvn install -DskipTests -T 1C
exec mvn -f linsight-server/pom.xml spring-boot:run \
  -Dspring-boot.run.profiles=local
