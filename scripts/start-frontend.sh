#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}/frontend"

corepack pnpm@11.7.0 install --frozen-lockfile
exec corepack pnpm@11.7.0 dev:antd -- --host 0.0.0.0

