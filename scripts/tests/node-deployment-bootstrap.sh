#!/usr/bin/env bash
# Real Python offline bootstrap plus mocked APT; only run in a disposable container.
set -euo pipefail
[ -f /.dockerenv ] && [ "${LINSIGHT_ISOLATED_DEPENDENCY_TEST:-}" = 1 ] || exit 64
fixture=$(mktemp -d /tmp/linsight-bootstrap-test.XXXXXX)
trap 'rm -rf -- "$fixture"' EXIT
export FIXTURE="$fixture"
mkdir -p "$fixture/bin"
export PATH="$fixture/bin:$PATH"
# This container's Python is real, but its ensurepip is deliberately unavailable.
mv /usr/local/lib/python3.12/ensurepip "$fixture/disabled-ensurepip"
if python3 -m venv "$fixture/standard" >"$fixture/standard.log" 2>&1; then exit 1; fi
cat >"$fixture/bin/ffmpeg" <<'SH'
#!/bin/bash
[ -f "$FIXTURE/installed" ]
SH
cat >"$fixture/bin/apt-get" <<'SH'
#!/bin/bash
echo "$*" >>"$FIXTURE/apt-calls"
# Deployment 44: ffmpeg needs no Python update. Reject any accidental Python plan.
[[ "$*" != *python* ]] || exit 99
if [[ " $* " = *' --simulate '* ]]; then
  if [ -f "$FIXTURE/held-ffmpeg-dependency" ]; then
    echo 'Inst libavcodec60 [1.0] (2.0 Ubuntu [arm64])'
  fi
  echo 'Inst ffmpeg (7:6.1.1-3ubuntu5 Ubuntu [arm64])'
elif [[ " $* " = *' install '* ]]; then touch "$FIXTURE/installed"; fi
SH
cat >"$fixture/bin/apt-mark" <<'SH'
#!/bin/bash
[ "$*" = showhold ] || exit 99
printf '%s\n' python3.12 python3.12-minimal libpython3.12-minimal libpython3.12-stdlib libpython3.12t64
[ ! -f "$FIXTURE/held-ffmpeg-dependency" ] || echo libavcodec60
SH
cat >"$fixture/bin/curl" <<'SH'
#!/bin/bash
[ "$*" = --version ] || exit 99
SH
chmod +x "$fixture/bin/"*
bootstrap=/runtime/ai_runtime/app/core/environment.py

# Disabled auto-install still rejects genuinely missing OS capability.
if bash /dependencies.sh check "$bootstrap" >"$fixture/output" 2>&1; then exit 1; fi
test ! -e "$fixture/apt-calls"
grep -q '请启用自动安装依赖' "$fixture/output"
echo 'PASS: disabled auto-install rejects missing ffmpeg without APT'

bash /dependencies.sh install "$bootstrap" >"$fixture/output" 2>&1
grep -q '使用随包 pip' "$fixture/output"
grep -q 'install -y ffmpeg=7:6.1.1-3ubuntu5' "$fixture/apt-calls"
! grep -Eq 'python|unhold|allow-change-held' "$fixture/apt-calls"
echo 'PASS: absent ensurepip and held Python use real offline seed; APT installs only ffmpeg'

python3 -I "$bootstrap" "$fixture/application" >"$fixture/bootstrap.log" 2>&1
"$fixture/application/bin/python" -I -m pip check
# Creating a second environment from the first simulates later model deployment.
"$fixture/application/bin/python" -I "$bootstrap" "$fixture/model" >>"$fixture/bootstrap.log" 2>&1
"$fixture/model/bin/python" -I -m pip check
echo 'PASS: application and nested model environments run pip without system ensurepip'

rm "$fixture/apt-calls"
bash /dependencies.sh check "$bootstrap" >"$fixture/output" 2>&1
test ! -e "$fixture/apt-calls"
echo 'PASS: subsequent capability check skips APT with system Python still unchanged'

if bash /dependencies.sh install /missing/environment.py >"$fixture/output" 2>&1; then exit 1; fi
test ! -e "$fixture/apt-calls"
grep -q '随包 Python 隔离环境实测失败' "$fixture/output"
echo 'PASS: missing bootstrap fails before APT'

rm "$fixture/installed"
touch "$fixture/held-ffmpeg-dependency"
if bash /dependencies.sh install "$bootstrap" >"$fixture/output" 2>&1; then exit 1; fi
test ! -e "$fixture/installed"
grep -q '修改锁定包 libavcodec60' "$fixture/output"
echo 'PASS: bootstrap does not bypass non-Python package holds'
