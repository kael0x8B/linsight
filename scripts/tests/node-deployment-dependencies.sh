#!/usr/bin/env bash
# Isolated fault injection: no real package manager or device is modified.
set -euo pipefail
[ -f /.dockerenv ] && [ "${LINSIGHT_ISOLATED_DEPENDENCY_TEST:-}" = 1 ] || exit 64
fixture=$(mktemp -d /tmp/linsight-dependency-test.XXXXXX)
trap 'rm -rf -- "$fixture"' EXIT
export FIXTURE="$fixture"
mkdir -p "$fixture/bin"
export PATH="$fixture/bin:$PATH"
cat >"$fixture/bin/python3" <<'SH'
#!/bin/bash
if [ "$1" = -c ]; then echo 3.12; exit 0; fi
if [ "$1 $2" = '-m venv' ]; then
  if [ -f "$FIXTURE/missing-venv" ] && { [ ! -f "$FIXTURE/installed" ] || [ -f "$FIXTURE/broken-after-install" ]; }; then echo 'ensurepip unavailable'; exit 1; fi
  mkdir -p "$3/bin"
  printf '#!/bin/bash\nexit 0\n' >"$3/bin/python"
  chmod +x "$3/bin/python"
fi
SH
cat >"$fixture/bin/curl" <<'SH'
#!/bin/bash
if [ -f "$FIXTURE/missing-curl" ] && [ ! -f "$FIXTURE/installed" ]; then exit 127; fi
exit 0
SH
cat >"$fixture/bin/ffmpeg" <<'SH'
#!/bin/bash
if [ -f "$FIXTURE/missing-ffmpeg" ] && [ ! -f "$FIXTURE/installed" ]; then exit 127; fi
exit 0
SH
cat >"$fixture/bin/apt-get" <<'SH'
#!/bin/bash
echo "$*" >>"$FIXTURE/apt-calls"
if [ -f "$FIXTURE/network-error" ] && [[ " $* " = *' update '* ]]; then echo 'Could not resolve repository'; exit 100; fi
if [[ " $* " = *' --simulate '* ]]; then
  if [ -f "$FIXTURE/conflict" ]; then echo 'curl : Depends: libcurl4t64 (= newer) but held is installed'; exit 100; fi
  if [ -f "$FIXTURE/removal" ]; then echo 'Remv vendor-display [1.0]'; fi
  if [ -f "$FIXTURE/malformed" ]; then echo 'Inst python3.12-venv'; fi
  if [ -f "$FIXTURE/unrelated" ]; then echo 'Inst libc6 [2.39] (2.40 Ubuntu [arm64])'; fi
  if [ -f "$FIXTURE/downgrade" ]; then echo 'Inst python3.12 [3.12.3-1ubuntu0.8] (3.12.3-1ubuntu0.1 Ubuntu [arm64])'; fi
  if [ -f "$FIXTURE/held-transitive" ]; then echo 'Inst libpython3.12-minimal:arm64 [3.12.3-1ubuntu0.8] (3.12.3-1ubuntu0.16 Ubuntu [arm64])'; fi
  if [ -f "$FIXTURE/upgrade-python" ]; then
    for package in python3.12 python3.12-minimal libpython3.12-minimal libpython3.12-stdlib; do
      [[ " $* " = *" $package=3.12.3-1ubuntu0.16 "* ]] || { echo "missing coordinated $package"; exit 100; }
      echo "Inst $package [3.12.3-1ubuntu0.8] (3.12.3-1ubuntu0.16 Ubuntu [arm64])"
    done
  fi
  for arg in "$@"; do
    case "$arg" in
      python3.12-venv=*) echo "Inst python3.12-venv (${arg#*=} Ubuntu [arm64])";;
      ffmpeg) echo 'Inst ffmpeg (7:6.1.1-3ubuntu5 Ubuntu [arm64])';;
    esac
  done
elif [[ " $* " = *' install '* ]]; then touch "$FIXTURE/installed"; fi
SH
cat >"$fixture/bin/apt-mark" <<'SH'
#!/bin/bash
[ "$*" = showhold ] || exit 99
if [ -f "$FIXTURE/held-transitive" ]; then echo 'libpython3.12-minimal:arm64'; fi
exit 0
SH
cat >"$fixture/bin/dpkg-query" <<'SH'
#!/bin/bash
if [ "$1" = -S ]; then
  [ ! -f "$FIXTURE/custom-python" ] || exit 1
  echo "python3.12-minimal: $2"; exit 0
fi
package=${!#}
case "${package%%:*}" in
  python3.12|python3.12-minimal|libpython3.12-minimal|libpython3.12-stdlib)
    echo 'install ok installed|3.12.3-1ubuntu0.8';;
  libc6) echo 'install ok installed|2.39';;
  curl) echo 'hold ok installed|8.5.0';;
  *) exit 1;;
esac
SH
cat >"$fixture/bin/apt-cache" <<'SH'
#!/bin/bash
package=$2
version=3.12.3-1ubuntu0.8
if [ -f "$FIXTURE/upgrade-python" ] || { [ -f "$FIXTURE/split-sources" ] && [ "$package" = python3.12-venv ]; }; then version=3.12.3-1ubuntu0.16; fi
if [ "$1" = madison ]; then
  echo "$package | $version | http://repository.invalid noble/main arm64 Packages"
else
  echo "$package:"
  echo "  Candidate: $version"
  echo '  Version table:'
  if [ -f "$FIXTURE/negative-pin" ] && [ "$package" = python3.12-venv ]; then
    echo "     $version -1"
  else
    echo "     $version 500"
  fi
fi
SH
chmod +x "$fixture/bin/"*

bash /dependencies.sh install >"$fixture/output"
test ! -e "$fixture/apt-calls"
grep -q '跳过 APT' "$fixture/output"
echo 'PASS: usable vendor-held packages never invoke APT'

touch "$fixture/missing-venv"
bash /dependencies.sh install >"$fixture/output"
grep -q -- 'install -y python3.12-venv=3.12.3-1ubuntu0.8$' "$fixture/apt-calls"
! grep -q -- 'python3-venv\|install -y.*curl\|-qq\|--allow-change-held-packages' "$fixture/apt-calls"
echo 'PASS: install only missing minor-version venv, then verify capability'
rm "$fixture/missing-venv" "$fixture/installed" "$fixture/apt-calls"

touch "$fixture/missing-curl" "$fixture/conflict"
if bash /dependencies.sh install >"$fixture/output"; then exit 1; fi
grep -q 'curl : Depends: libcurl4t64' "$fixture/output"
grep -q 'LINSIGHT_ERROR=APT 依赖冲突' "$fixture/output"
! grep -q -- 'install -y' "$fixture/apt-calls"
echo 'PASS: solver conflict preserves detail and prevents any package mutation'
rm "$fixture/apt-calls"

if bash /dependencies.sh check >"$fixture/output"; then exit 1; fi
test ! -e "$fixture/apt-calls"
grep -q '请启用自动安装依赖' "$fixture/output"
echo 'PASS: automatic installation disabled fails before mutation'

touch "$fixture/network-error"
if bash /dependencies.sh install >"$fixture/output"; then exit 1; fi
grep -q 'APT 软件源刷新失败' "$fixture/output"
! grep -q -- 'install' "$fixture/apt-calls"
echo 'PASS: repository failure is bounded and does not start installation'

reset_case() {
  rm -f "$fixture/missing-venv" "$fixture/missing-curl" "$fixture/missing-ffmpeg" \
    "$fixture/installed" "$fixture/apt-calls" "$fixture/conflict" "$fixture/network-error" \
    "$fixture/upgrade-python" "$fixture/split-sources" "$fixture/negative-pin" \
    "$fixture/removal" "$fixture/malformed" "$fixture/unrelated" "$fixture/downgrade" \
    "$fixture/held-transitive" "$fixture/custom-python" "$fixture/broken-after-install"
}
reset_case
touch "$fixture/missing-venv" "$fixture/missing-ffmpeg" "$fixture/upgrade-python"
bash /dependencies.sh install >"$fixture/output"
grep -q '配套补丁版本' "$fixture/output"
grep -- 'install -y' "$fixture/apt-calls" | grep -q 'python3.12=3.12.3-1ubuntu0.16'
grep -- 'install -y' "$fixture/apt-calls" | grep -q 'ffmpeg=7:6.1.1-3ubuntu5'
echo 'PASS: unavailable old venv coordinates the existing Python minor family and missing ffmpeg'

for scenario in split-sources negative-pin removal malformed unrelated downgrade held-transitive custom-python; do
  reset_case
  touch "$fixture/missing-venv" "$fixture/$scenario"
  if bash /dependencies.sh install >"$fixture/output"; then echo "Unexpected success: $scenario"; exit 1; fi
  if [ -f "$fixture/apt-calls" ]; then ! grep -q -- 'install -y' "$fixture/apt-calls"; fi
  grep -q 'LINSIGHT_ERROR=' "$fixture/output"
  case "$scenario" in
    split-sources|negative-pin) grep -q '软件源或 APT pin' "$fixture/output";;
    removal) grep -q '删除系统包' "$fixture/output";;
    malformed) grep -q '无效版本' "$fixture/output";;
    unrelated) grep -q '无关系统包 libc6' "$fixture/output";;
    downgrade) grep -q '降级 python3.12' "$fixture/output";;
    held-transitive) grep -q '修改锁定包 libpython3.12-minimal:arm64' "$fixture/output";;
    custom-python) grep -q '不是对应发行版包管理' "$fixture/output";;
  esac
  echo "PASS: $scenario refuses package mutation and provides a specific reason"
done

reset_case
touch "$fixture/missing-venv" "$fixture/broken-after-install"
if bash /dependencies.sh install >"$fixture/output"; then exit 1; fi
grep -q '安装后依赖仍不可用' "$fixture/output"
echo 'PASS: successful APT exit is not mistaken for usable venv/pip'
