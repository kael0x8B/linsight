#!/usr/bin/env bash
# Sourced by install.sh. Never replace /usr/bin/python3 or change the host's APT packages.
python_mode="${1:-check}"
[[ "$python_mode" = install || "$python_mode" = check ]] || { echo 'LINSIGHT_ERROR=无效的 Python 安装模式'; return 64; }

python_usable() {
  [[ -n "${1:-}" && -x "$1" ]] || return 1
  "$1" -c 'import sys, ssl; assert (3, 12) <= sys.version_info < (3, 14)' >/dev/null 2>&1
}

managed_python_accessible() {
  chmod 0755 /opt/linsight/python && chmod -R a+rX /opt/linsight/python/3.12.14
}

for candidate in /opt/linsight/python/3.12.14/bin/python3 /usr/local/bin/python3.12 /usr/bin/python3.12 "$(command -v python3.12 || true)" "$(command -v python3 || true)"; do
  if python_usable "$candidate"; then
    if [[ "$candidate" = /opt/linsight/python/* ]]; then
      managed_python_accessible || { echo 'LINSIGHT_ERROR=独立 Python 无法供节点服务用户执行'; return 1; }
    fi
    export LINSIGHT_PYTHON="$candidate"
    echo "[PYTHON] 使用独立解释器：$LINSIGHT_PYTHON"
    return 0
  fi
done

[[ "$python_mode" = install ]] || { echo 'LINSIGHT_ERROR=没有可用的 Python 3.12/3.13；请启用自动安装依赖'; return 1; }

case "$(uname -m)" in
  aarch64|arm64)
    python_arch=aarch64
    python_sha256=c0574c9c9fec561eb192ad510e4e79aaad039929b3531b3bb873e2f630fb14a9
    ;;
  x86_64|amd64)
    python_arch=x86_64
    python_sha256=5eae8cf79dd47fc2496a4fccc892936be831ce7a84d984b2299dfb1cdb592682
    ;;
  *) echo 'LINSIGHT_ERROR=当前架构没有已校验的独立 Python 3.12 安装包'; return 1 ;;
esac

python_artifact="cpython-3.12.14+20260924-${python_arch}-unknown-linux-gnu-install_only.tar.gz"
python_url="https://github.com/astral-sh/python-build-standalone/releases/download/20260924/${python_artifact}"
python_offline="/opt/linsight/runtime.new/deployment-python/${python_artifact}"
python_root=/opt/linsight/python
python_target="$python_root/3.12.14"
install -d -m 0755 "$python_root"
chmod 0755 "$python_root"
python_stage=$(mktemp -d "$python_root/.stage.XXXXXX") || return 1
python_download=$(mktemp "$python_root/.download.XXXXXX") || { rmdir "$python_stage"; return 1; }
python_cleanup() { rm -rf -- "$python_stage"; rm -f -- "$python_download"; }

if [[ -f "$python_offline" ]]; then
  cp -- "$python_offline" "$python_download" || { python_cleanup; return 1; }
  echo '[PYTHON] 使用随部署包提供的独立 Python 3.12'
else
  echo '[PYTHON] 下载已固定版本的独立 Python 3.12，不修改系统 Python'
  if ! timeout 600s python3 - "$python_url" "$python_download" <<'PY'
import shutil
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=60) as source, open(sys.argv[2], "wb") as target:
    shutil.copyfileobj(source, target, length=1024 * 1024)
PY
  then
    python_cleanup
    echo 'LINSIGHT_ERROR=独立 Python 下载失败；请检查网络，或将已校验安装包放入 runtime/deployment-python'
    return 1
  fi
fi

if ! printf '%s  %s\n' "$python_sha256" "$python_download" | sha256sum -c -; then
  python_cleanup
  echo 'LINSIGHT_ERROR=独立 Python 安装包 SHA256 不匹配，未安装'
  return 1
fi
if ! tar -xzf "$python_download" -C "$python_stage" \
    || ! [[ -x "$python_stage/python/bin/python3" ]] \
    || ! "$python_stage/python/bin/python3" -c 'import sys, ssl, venv; assert sys.version_info[:3] == (3, 12, 14)'; then
  python_cleanup
  echo 'LINSIGHT_ERROR=独立 Python 解包或运行校验失败，未切换服务'
  return 1
fi
if [[ -e "$python_target" ]]; then
  python_cleanup
  echo 'LINSIGHT_ERROR=已有不可用的独立 Python 目录，请检查 /opt/linsight/python/3.12.14'
  return 1
fi
mv -- "$python_stage/python" "$python_target" || { python_cleanup; return 1; }
python_cleanup
managed_python_accessible || { echo 'LINSIGHT_ERROR=独立 Python 无法供节点服务用户执行'; return 1; }
export LINSIGHT_PYTHON="$python_target/bin/python3"
echo "[PYTHON] 已安装独立 Python：$($LINSIGHT_PYTHON --version)"
