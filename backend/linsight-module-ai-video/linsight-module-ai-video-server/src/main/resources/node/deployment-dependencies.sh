#!/usr/bin/env bash
# Probe capabilities, not distribution meta-packages: vendor images can provide a
# working Python/FFmpeg while holding a different distro package version.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C
mode="${1:-check}"
bootstrap="${2:-}"
python_bin="${LINSIGHT_PYTHON:-python3}"
[[ "$mode" = install || "$mode" = check ]] || exit 64

fail() { echo "LINSIGHT_ERROR=$*"; exit 1; }
python_minor=$("$python_bin" -c 'import sys; assert (3,12) <= sys.version_info < (3,14), "Python 3.12/3.13 required"; print(f"{sys.version_info.major}.{sys.version_info.minor}")') \
  || fail '需要可用的 Python 3.12 或 3.13；未修改系统 Python'
probe=$(mktemp -d /tmp/linsight-venv-check.XXXXXX)
trap 'rm -rf -- "$probe"' EXIT

check_capabilities() {
  missing=()
  if ! timeout 45s "$python_bin" -m venv "$probe/venv" >"$probe/venv.log" 2>&1 \
      || ! "$probe/venv/bin/python" -m pip --version >>"$probe/venv.log" 2>&1; then
    echo '[DEPENDENCY] Python venv/pip 不可用：'
    tail -n 12 "$probe/venv.log"
    if [[ -n "$bootstrap" ]]; then
      echo '[DEPENDENCY] 使用随包 pip 实测应用隔离环境，保留系统 Python 与锁定包'
      if ! timeout 120s "$python_bin" -I "$bootstrap" --probe "$probe"; then
        fail '随包 Python 隔离环境实测失败，未安装系统包；请检查上方 bootstrap 错误'
      fi
    else
      missing+=("python${python_minor}-venv")
    fi
  fi
  timeout 10s ffmpeg -version >/dev/null 2>&1 || missing+=(ffmpeg)
  timeout 10s curl --version >/dev/null 2>&1 || missing+=(curl)
  [ -s /etc/ssl/certs/ca-certificates.crt ] || missing+=(ca-certificates)
}

echo 'LINSIGHT_PROGRESS=58 正在实测 Python 环境与系统依赖'
check_capabilities
if [ "${#missing[@]}" = 0 ]; then
  echo '[DEPENDENCY] Python venv/pip、FFmpeg、curl、CA 均可用，跳过 APT'
  exit 0
fi
echo "[DEPENDENCY] 仅补齐缺失项：${missing[*]}"
[ "$mode" = install ] || fail "依赖不可用：${missing[*]}；请启用自动安装依赖后重试"

# Never unhold vendor packages or repair the entire OS as an application upgrade.
apt_options=(-o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o Dpkg::Use-Pty=0)
apt-get "${apt_options[@]}" update --error-on=any \
  || fail 'APT 软件源刷新失败；请检查上方源地址与网络错误，原服务未切换'

contains() { local value="$1"; shift; local item; for item in "$@"; do [[ "$item" = "$value" ]] && return 0; done; return 1; }
installed_version() {
  dpkg-query -W -f='${Status}|${Version}\n' "$1" 2>/dev/null | awk -F '|' '$1 ~ / ok installed$/ {print $2}' || true
}
candidate_version() { apt-cache policy "$1" | awk '$1 == "Candidate:" && $2 != "(none)" {print $2}'; }
available_version() {
  # A version merely present in dpkg status is not necessarily downloadable.
  # Respect non-positive APT pins instead of selecting a forbidden version.
  apt-cache policy "$1" | awk -v v="$2" '
    $1 == v && $2 > 0 {found=1}
    $1 == "***" && $2 == v && $3 > 0 {found=1}
    END {exit !found}' || return 1
  apt-cache madison "$1" | awk -F '|' -v v="$2" '
    {gsub(/^[ \t]+|[ \t]+$/, "", $2); if ($2 == v) found=1}
    END {exit !found}'
}
diagnostics() {
  echo '[DEPENDENCY] 锁定包（完整列表；空列表不代表存在 hold）：'
  cat "$probe/holds"
  echo '[DEPENDENCY] Python/venv 与缺失项的已安装版本、候选版本及源优先级：'
  apt-cache policy "${python_packages[@]}" "${missing[@]}" || true
}

python_package="python${python_minor}"
venv_package="${python_package}-venv"
python_packages=("$python_package" "${python_package}-minimal" "lib${python_package}-minimal" "lib${python_package}-stdlib" "$venv_package")
for optional in "lib${python_package}" "lib${python_package}t64"; do
  [[ -z "$(installed_version "$optional")" ]] || python_packages+=("$optional")
done
apt-mark showhold >"$probe/holds" || fail '无法读取系统包锁定状态，未安装系统依赖'
audit=$(dpkg --audit) || fail '无法检查 dpkg 状态，未安装系统依赖'
if [[ -n "$audit" ]]; then
  echo "$audit"
  fail '系统存在未完成配置的包，请先处理 dpkg 状态；不会自动修复整机依赖'
fi

allowed_upgrades=("${missing[@]}")
plan_reason='没有找到可安全安装的依赖组合'
selected=()
validate_plan() {
  local package version installed held base
  if grep -Eq '^(Remv|Purg) ' "$probe/plan"; then
    plan_reason='模拟安装需要删除系统包，已阻止'; return 1
  fi
  selected=()
  while IFS=$'\t' read -r package version; do
    [[ -n "$package" ]] || continue
    if [[ ! "$package" =~ ^[a-z0-9][a-z0-9.+:-]*$ || ! "$version" =~ ^[a-zA-Z0-9.+:~_-]+$ ]]; then
      plan_reason='无法识别 APT 模拟结果，未安装系统依赖'; return 1
    fi
    if ! dpkg --validate-version "$version" >/dev/null 2>&1; then
      plan_reason='APT 模拟结果包含无效版本，未安装系统依赖'; return 1
    fi
    base=${package%%:*}
    while read -r held; do
      if [[ -n "$held" && "${held%%:*}" = "$base" ]]; then
        plan_reason="模拟安装需要修改锁定包 $package，已阻止"; return 1
      fi
    done <"$probe/holds"
    installed=$(installed_version "$package")
    if [[ -n "$installed" ]]; then
      if dpkg --compare-versions "$version" lt "$installed"; then
        plan_reason="模拟安装需要降级 $package（$installed → $version），已阻止"; return 1
      fi
      if ! contains "$base" "${allowed_upgrades[@]}"; then
        plan_reason="模拟安装需要变更无关系统包 $package，已阻止"; return 1
      fi
    fi
    selected+=("$package=$version")
  done < <(awk '/^Inst / {v=$0; sub(/^[^(]*\(/, "", v); sub(/[ )].*$/, "", v); print $2 "\t" v}' "$probe/plan")
  # Fail closed if a missing capability would otherwise produce an empty plan.
  [[ "${#selected[@]}" -gt 0 ]] || { plan_reason='APT 未提供安装动作，但能力检查仍失败'; return 1; }
}
try_plan() {
  local label="$1"; shift
  echo "[DEPENDENCY] 模拟方案：$label"
  if ! apt-get "${apt_options[@]}" --simulate --no-remove --no-install-recommends install "$@" >"$probe/plan" 2>&1; then
    cat "$probe/plan"
    plan_reason="APT 无法满足方案：$label"; return 1
  fi
  cat "$probe/plan"
  if ! validate_plan; then echo "[DEPENDENCY] $plan_reason"; return 1; fi
}

plan_ready=false
if contains "$venv_package" "${missing[@]}"; then
  # Only coordinate distro Python packages when they own the active interpreter.
  interpreter=$(readlink -f "$(command -v "$python_bin")")
  owner=$(dpkg-query -S "$interpreter" 2>/dev/null || true)
  # Debian/Ubuntu normally place the binary in pythonX.Y-minimal, not pythonX.Y.
  contains "${owner%%:*}" "$python_package" "${python_package}-minimal" \
    || fail '当前 Python 不是对应发行版包管理的解释器，不能自动升级系统 Python；请提供带 venv 的受支持 Python'
  current_python=$(installed_version "${owner%%:*}")
  [[ -n "$current_python" ]] || fail '无法确定系统 Python 包的已安装版本，未安装依赖'
  echo "[DEPENDENCY] 当前 Python 包版本：$python_package=$current_python"
  other_missing=()
  for package in "${missing[@]}"; do [[ "$package" = "$venv_package" ]] || other_missing+=("$package"); done
  if available_version "$venv_package" "$current_python"; then
    if try_plan '优先匹配现有 Python，不升级解释器' "$venv_package=$current_python" "${other_missing[@]}"; then plan_ready=true; fi
  else
    echo '[DEPENDENCY] 软件源没有可安装的同版本 venv，检查同一 Python 小版本的配套升级'
  fi
  if [[ "$plan_ready" = false ]]; then
    target_python=$(candidate_version "$python_package")
    cohort=()
    coherent=true
    if [[ -z "$target_python" ]] || dpkg --compare-versions "$target_python" lt "$current_python"; then
      coherent=false
      plan_reason='Python 候选版本缺失或低于已安装版本，不自动降级'
    else
      for package in "${python_packages[@]}"; do
        if [[ "$(candidate_version "$package")" != "$target_python" ]] || ! available_version "$package" "$target_python"; then
          coherent=false
          plan_reason="软件源或 APT pin 导致 Python 配套候选版本不一致：$package 无法使用 $target_python"; break
        fi
        cohort+=("$package=$target_python")
      done
    fi
    if [[ "$coherent" = true ]]; then
      allowed_upgrades+=("${python_packages[@]}")
      if try_plan "Python $python_minor 配套补丁版本 $target_python" "${cohort[@]}" "${other_missing[@]}"; then plan_ready=true; fi
    fi
  fi
else
  if try_plan '只补齐缺失的系统能力' "${missing[@]}"; then plan_ready=true; fi
fi
if [[ "$plan_ready" = false ]]; then
  diagnostics
  fail "APT 依赖冲突：$plan_reason；未安装系统包，未切换原服务"
fi
echo "[DEPENDENCY] 已通过安全检查，按模拟结果固定版本安装：${selected[*]}"
apt-get "${apt_options[@]}" --no-remove --no-install-recommends install -y "${selected[@]}" \
  || fail '系统依赖安装失败；原服务未切换，具体原因见上方 APT 日志'
check_capabilities
[ "${#missing[@]}" = 0 ] || fail "安装后依赖仍不可用：${missing[*]}；原服务未切换"
echo '[DEPENDENCY] 系统依赖实测通过'
