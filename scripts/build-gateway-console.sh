#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}/frontend"
corepack pnpm@11.7.0 --filter @linsight/console build
python3 - "${PROJECT_DIR}" <<'PY'
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = root / 'frontend/apps/web-antd/dist'
target = root / 'runtime/edge_agent/app/console'
if not (source / 'gateway.html').is_file():
    raise SystemExit('Gateway entry was not built')
temporary = target.with_name('console.build')
shutil.rmtree(temporary, ignore_errors=True)
shutil.copytree(source, temporary, ignore=shutil.ignore_patterns('*.map', '*.zip'))
shutil.rmtree(target, ignore_errors=True)
temporary.rename(target)
print(f'Gateway console packaged: {target}')
PY
