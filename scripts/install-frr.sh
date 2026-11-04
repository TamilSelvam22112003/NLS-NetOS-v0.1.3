#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="${ROOT_DIR}/build/rootfs"
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo $0" >&2; exit 1; }
[[ -d "$STAGE_DIR" ]] || { echo "ERROR: build/rootfs missing; run scripts/build-frr.sh first." >&2; exit 1; }
if ! getent group frr >/dev/null; then groupadd --system frr; fi
if ! id frr >/dev/null 2>&1; then useradd --system --gid frr --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin frr; fi
cp -a "$STAGE_DIR/." /
install -d -o frr -g frr -m 0750 /var/run/frr /var/log/frr
if [[ -d /etc/frr ]]; then chown -R frr:frr /etc/frr; fi
if [[ -f /etc/frr/daemons ]]; then chown root:frr /etc/frr/daemons; chmod 0640 /etc/frr/daemons; fi
if command -v systemctl >/dev/null 2>&1; then
 systemctl daemon-reload
 systemctl disable --now frr.service 2>/dev/null || true
 echo "FRR installed. Service remains stopped; inspect /etc/frr/daemons before starting."
else echo "FRR files installed; systemd unavailable."; fi
