#!/usr/bin/env bash
# Root-owned, fixed-scope disk pressure remediation for LInsight edge nodes.
set -euo pipefail
umask 077

mode="${1:-}"
if [ -n "$mode" ] && [ "$mode" != "--force" ]; then
  exit 64
fi

trigger="${LINSIGHT_DISK_CLEANUP_TRIGGER_PERCENT:-80}"
critical="${LINSIGHT_DISK_CLEANUP_CRITICAL_PERCENT:-90}"
[[ "$trigger" =~ ^[0-9]+$ ]] && [ "$trigger" -ge 1 ] && [ "$trigger" -le 99 ] || exit 64
[[ "$critical" =~ ^[0-9]+$ ]] && [ "$critical" -ge "$trigger" ] && [ "$critical" -le 99 ] || exit 64

if [ "${LINSIGHT_DEPLOY_LOCK_HELD:-}" != 1 ]; then
  exec 9>/run/linsight-deploy.lock
  flock -n 9 || exit 0
fi

disk_percent() {
  df -Pk / | awk 'NR == 2 { value=$5; sub(/%$/, "", value); print value }'
}

disk_available_kib() {
  df -Pk / | awk 'NR == 2 { print $4 }'
}

before_percent="$(disk_percent)"
before_available_kib="$(disk_available_kib)"
[[ "$before_percent" =~ ^[0-9]+$ ]] || exit 1
[[ "$before_available_kib" =~ ^[0-9]+$ ]] || exit 1

if [ "$mode" != "--force" ] && [ "$before_percent" -lt "$trigger" ]; then
  exit 0
fi

actions=()
record_action() { actions+=("$1"); }

# Installation caches are reproducible and are never runtime/model source-of-truth data.
if [ -d /var/cache/linsight/pip ]; then
  find /var/cache/linsight/pip -xdev -mindepth 1 -delete 2>/dev/null || true
  record_action pip_cache
fi

# Deployment lock excludes a concurrent installer. Only exact, known staging names are accepted.
for stage in /opt/linsight/runtime.new /opt/linsight/venv.new; do
  if [ -e "$stage" ] || [ -L "$stage" ]; then
    rm -rf -- "$stage"
    record_action stale_stage
  fi
done
while IFS= read -r temporary; do
  name="$(basename -- "$temporary")"
  if [[ "$name" =~ ^linsight-deploy-[0-9]+$ ]]; then
    rm -rf -- "$temporary"
    record_action stale_upload
  fi
done < <(find /tmp -xdev -mindepth 1 -maxdepth 1 -type d -name 'linsight-deploy-*' -mmin +60 -print 2>/dev/null)

# Keep the source-previous snapshot plus one additional newest recovery snapshot.
deployment_base=/var/lib/linsight-deployments
if [ -d "$deployment_base" ]; then
  source_previous="$(readlink -f "$deployment_base/source-previous" 2>/dev/null || true)"
  kept_extra=0
  while IFS= read -r snapshot; do
    name="$(basename -- "$snapshot")"
    [[ "$name" =~ ^[0-9]+$ ]] || continue
    [ -f "$snapshot/ready" ] || continue
    if [ -n "$source_previous" ] && [ "$snapshot" = "$source_previous" ]; then
      continue
    fi
    if [ "$kept_extra" -lt 1 ]; then
      kept_extra=$((kept_extra + 1))
      continue
    fi
    if [ -f "$snapshot/committed" ] || [ -f "$snapshot/restored" ]; then
      rm -rf -- "$snapshot"
      record_action old_snapshot
    fi
  done < <(find "$deployment_base" -xdev -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2-)
fi

# Signed in-band Agent releases are immutable; retain exactly the active and rollback targets.
release_base=/var/lib/linsight/edge-agent/releases
if [ -d "$release_base" ]; then
  current_release="$(readlink -f /var/lib/linsight/edge-agent/current 2>/dev/null || true)"
  previous_release="$(readlink -f /var/lib/linsight/edge-agent/previous 2>/dev/null || true)"
  while IFS= read -r release; do
    [ "$release" = "$current_release" ] && continue
    [ "$release" = "$previous_release" ] && continue
    rm -rf -- "$release"
    record_action old_agent_release
  done < <(find "$release_base" -xdev -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null)
fi

# Cap persistent service logs. Application event data and delivery.sqlite3 are never touched.
if command -v journalctl >/dev/null 2>&1; then
  journalctl --rotate >/dev/null 2>&1 || true
  journalctl --vacuum-time=7d --vacuum-size=256M >/dev/null 2>&1 || true
  record_action journal
fi

mid_percent="$(disk_percent)"
if [ "$mid_percent" -ge "$critical" ] && command -v apt-get >/dev/null 2>&1; then
  apt-get clean >/dev/null 2>&1 || true
  record_action apt_cache
fi

after_percent="$(disk_percent)"
after_available_kib="$(disk_available_kib)"
freed_kib=$((after_available_kib - before_available_kib))
[ "$freed_kib" -ge 0 ] || freed_kib=0
freed_bytes=$((freed_kib * 1024))
status=RECLAIMED
[ "$after_percent" -lt "$trigger" ] || status=STILL_HIGH

state_dir=/var/lib/linsight/disk-pressure
install -d -m 0755 "$state_dir"
temporary_state="$state_dir/.last-run.env.tmp"
{
  printf 'STATUS=%s\n' "$status"
  printf 'LAST_RUN_EPOCH_SECONDS=%s\n' "$(date +%s)"
  printf 'BEFORE_PERCENT=%s\n' "$before_percent"
  printf 'AFTER_PERCENT=%s\n' "$after_percent"
  printf 'FREED_BYTES=%s\n' "$freed_bytes"
  if [ "${#actions[@]}" -eq 0 ]; then
    printf 'ACTIONS=none\n'
  else
    (IFS=,; printf 'ACTIONS=%s\n' "${actions[*]}")
  fi
} >"$temporary_state"
chmod 0644 "$temporary_state"
mv -f -- "$temporary_state" "$state_dir/last-run.env"

logger -t linsight-disk-pressure \
  "status=$status before=${before_percent}% after=${after_percent}% freedBytes=$freed_bytes"
exit 0
