#!/usr/bin/env bash
# Invoked only by the root-owned installer / recovery timer. No SSH secrets are stored.
set -euo pipefail
umask 077
action="${1:?action}"
deployment="${2:?deployment id}"
[[ "$deployment" =~ ^[0-9]+$ ]] || exit 64
base=/var/lib/linsight-deployments
backup="$base/$deployment"
unit="linsight-deploy-rollback-$deployment"
# The installer's child shares its already-held lock. Timer/manual callers acquire it.
if [ "${LINSIGHT_DEPLOY_LOCK_HELD:-}" != 1 ]; then
  exec 9>/run/linsight-deploy.lock
  flock -w 30 9 || exit 75
fi
paths=(
  /opt/linsight/runtime /opt/linsight/venv
  /etc/linsight/runtime.env /etc/linsight/agent.env /etc/linsight/agent-upgrade.env
  /etc/systemd/system/linsight-ai-runtime.service /etc/systemd/system/linsight-edge-agent.service
  /etc/systemd/system/linsight-local-console.service
  /etc/systemd/system/linsight-node-power.path /etc/systemd/system/linsight-node-power.service
  /usr/local/sbin/linsight-node-power /etc/tmpfiles.d/linsight.conf
  /var/lib/linsight/edge-agent/current /var/lib/linsight/edge-agent/previous
  /var/lib/linsight/edge-agent/pending-activation.json
  /var/lib/linsight/edge-agent/failed-activation-version
)
services=(linsight-ai-runtime.service linsight-edge-agent.service linsight-local-console.service linsight-node-power.path)
case "$action" in
  prepare)
    install -d -m 0700 "$base" "$backup" "$backup/root"
    [ ! -e "$backup/ready" ] || { echo "Snapshot already exists"; exit 65; }
    required=0
    for path in "${paths[@]}"; do
      if [ -e "$path" ] || [ -L "$path" ]; then
        size=$(du -sk -- "$path" | cut -f1)
        required=$((required + size))
      fi
    done
    available=$(df -Pk "$base" | awk 'NR==2 {print $4}')
    [ "$available" -gt "$((required + 524288))" ] || { echo "Insufficient disk for recovery snapshot"; exit 28; }
    for path in "${paths[@]}"; do
      if [ -e "$path" ] || [ -L "$path" ]; then cp -a --parents -- "$path" "$backup/root"; fi
    done
    for service in "${services[@]}"; do
      if systemctl is-active --quiet "$service"; then echo "$service" >> "$backup/active"; fi
      if systemctl is-enabled --quiet "$service"; then echo "$service" >> "$backup/enabled"; fi
    done
    cp -- "$0" "$backup/restore.sh"
    chmod 0700 "$backup/restore.sh"
    touch "$backup/ready"
    # Armed before the first destructive switch; survives SSH or control-plane loss.
    systemd-run --quiet --unit="$unit" --on-active=300s /bin/bash "$backup/restore.sh" restore "$deployment"
    echo "[RECOVERY] Full snapshot ready; rollback watchdog armed"
    ;;
  restore|manual)
    [ -f "$backup/ready" ] || exit 0
    [ ! -f "$backup/restored" ] || exit 0
    if [ "$action" = restore ] && [ -f "$backup/committed" ]; then exit 0; fi
    systemctl stop "${services[@]}" || true
    systemctl disable "${services[@]}" 2>/dev/null || true
    for path in "${paths[@]}"; do
      # Fixed allowlist, never an arbitrary or user-supplied directory.
      rm -rf -- "$path"
      if [ -e "$backup/root$path" ] || [ -L "$backup/root$path" ]; then
        mkdir -p -- "$(dirname "$path")"
        cp -a -- "$backup/root$path" "$path"
      fi
    done
    systemctl daemon-reload
    if [ -f "$backup/enabled" ]; then while read -r service; do systemctl enable "$service"; done < "$backup/enabled"; fi
    if [ -f "$backup/active" ]; then while read -r service; do systemctl start "$service"; done < "$backup/active"; fi
    touch "$backup/restored"
    systemctl stop "$unit.timer" 2>/dev/null || true
    echo "[RECOVERY] Previous Runtime, environment and services restored"
    ;;
  commit)
    [ -f "$backup/ready" ] && [ ! -f "$backup/restored" ]
    touch "$backup/committed"
    systemctl stop "$unit.timer" 2>/dev/null || true
    if [ -d "$backup/root/opt/linsight/runtime" ] && [ -s "$backup/previous-version" ]; then
      ln -sfn "$backup" "$base/source-previous.tmp"
      mv -Tf "$base/source-previous.tmp" "$base/source-previous"
    fi
    echo "[RECOVERY] Fresh target heartbeat confirmed; deployment committed"
    ;;
  *) exit 64 ;;
esac
