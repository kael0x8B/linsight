#!/usr/bin/env bash
# Integration fixture. NEVER run directly on a host or an existing application container.
set -euo pipefail
[ -f /.dockerenv ] && [ "${LINSIGHT_ISOLATED_RECOVERY_TEST:-}" = 1 ] || exit 64
mkdir -p /tmp/test-bin /opt/linsight/runtime /opt/linsight/venv /etc/linsight /etc/systemd/system /var/lib/linsight/edge-agent/releases/v1
cat >/tmp/test-bin/systemctl <<'SH'
#!/bin/bash
echo "$*" >> /tmp/systemctl-calls
exit 0
SH
cat >/tmp/test-bin/systemd-run <<'SH'
#!/bin/bash
echo "$*" >> /tmp/timer-calls
exit 0
SH
chmod +x /tmp/test-bin/*
export PATH="/tmp/test-bin:$PATH"
printf old-code > /opt/linsight/runtime/version
printf old-venv > /opt/linsight/venv/version
printf old-agent-env > /etc/linsight/agent.env
printf old-runtime-env > /etc/linsight/runtime.env
printf old-unit > /etc/systemd/system/linsight-edge-agent.service
ln -s /var/lib/linsight/edge-agent/releases/v1 /var/lib/linsight/edge-agent/current
bash /recovery.sh prepare 901
grep -q -- '--on-active=300s' /tmp/timer-calls
printf broken-code > /opt/linsight/runtime/version
printf broken-venv > /opt/linsight/venv/version
printf broken-agent-env > /etc/linsight/agent.env
printf broken-runtime-env > /etc/linsight/runtime.env
printf broken-unit > /etc/systemd/system/linsight-edge-agent.service
rm /var/lib/linsight/edge-agent/current
# This is the exact command executed by the watchdog after control-plane/SSH loss.
bash /var/lib/linsight-deployments/901/restore.sh restore 901
test "$(cat /opt/linsight/runtime/version)" = old-code
test "$(cat /opt/linsight/venv/version)" = old-venv
test "$(cat /etc/linsight/agent.env)" = old-agent-env
test "$(cat /etc/linsight/runtime.env)" = old-runtime-env
test "$(cat /etc/systemd/system/linsight-edge-agent.service)" = old-unit
test "$(readlink /var/lib/linsight/edge-agent/current)" = /var/lib/linsight/edge-agent/releases/v1
bash /var/lib/linsight-deployments/901/restore.sh restore 901
echo 'PASS: failed switch restores code, venv, both env files, systemd and signed pointer; retry is idempotent'

bash /recovery.sh prepare 902
printf v1 > /var/lib/linsight-deployments/902/previous-version
printf new-code > /opt/linsight/runtime/version
bash /var/lib/linsight-deployments/902/restore.sh commit 902
bash /var/lib/linsight-deployments/902/restore.sh restore 902
test "$(cat /opt/linsight/runtime/version)" = new-code
test "$(readlink /var/lib/linsight-deployments/source-previous)" = /var/lib/linsight-deployments/902
bash /var/lib/linsight-deployments/902/restore.sh manual 902
test "$(cat /opt/linsight/runtime/version)" = old-code
echo 'PASS: confirmed deployment resists watchdog; explicit full rollback restores snapshot'

# A held remote lock rejects a second installer/recovery without altering existing files.
exec 9>/run/linsight-deploy.lock
flock 9
if timeout 1 bash /recovery.sh prepare 903; then exit 1; fi
test ! -e /var/lib/linsight-deployments/903/ready
echo 'PASS: remote concurrent deployment is blocked'
