#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Compatibility alias: the original Runtime now owns the local console as well.
exec bash "${PROJECT_DIR}/scripts/start-runtime.sh"
