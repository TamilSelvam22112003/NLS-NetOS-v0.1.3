#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="${ROOT_DIR}/build/rootfs"
OUT_DIR="${ROOT_DIR}/build/packages"
PKG_ROOT="${ROOT_DIR}/build/package-root"
VERSION="${VERSION:-0.1.3}"
ARCH="$(dpkg --print-architecture)"

[[ -d "$STAGE_DIR" ]] || { echo "Missing build/rootfs; run scripts/build-frr.sh first." >&2; exit 1; }
rm -rf "$PKG_ROOT"
install -d "$PKG_ROOT/DEBIAN" "$OUT_DIR"
cp -a "$STAGE_DIR/." "$PKG_ROOT/"

# Stage local key provisioning and the activation-gated boot initializer.
# All generated key material and machine-specific CA metadata remain on target.
install -D -m 0700 "$ROOT_DIR/scripts/generate-keys.sh" \
  "$PKG_ROOT/usr/lib/nls-netos/generate-keys.sh"
install -D -m 0700 "$ROOT_DIR/scripts/nls-boot-init.sh" \
  "$PKG_ROOT/usr/lib/nls-netos/nls-boot-init.sh"
install -D -m 0700 "$ROOT_DIR/scripts/home-ca-vip.py" \
  "$PKG_ROOT/usr/lib/nls-netos/home-ca-vip.py"
install -D -m 0644 "$ROOT_DIR/lib/systemd/system/nls-keygen.service" \
  "$PKG_ROOT/lib/systemd/system/nls-keygen.service"

cat > "$PKG_ROOT/DEBIAN/control" <<CONTROL
Package: nls-netos-frr
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Depends: libc6, libpcre2-8-0, libprotobuf-c1, libunwind8, libyang2t64, iproute2, systemd, python3, python3-cryptography, openssl
Maintainer: NLS-NetOS Maintainers
Description: NLS-NetOS FRRouting runtime and cryptographic provisioning
 FRRouting binaries, NLS key provisioning, and systemd service layout.
CONTROL

cat > "$PKG_ROOT/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
getent group frr >/dev/null || addgroup --system frr
getent group frrvty >/dev/null || addgroup --system frrvty
id frr >/dev/null 2>&1 || adduser --system --ingroup frr --home /nonexistent --no-create-home --shell /usr/sbin/nologin frr
adduser frr frrvty >/dev/null 2>&1 || true
install -d -o frr -g frr -m 0750 /var/run/frr /var/log/frr
if [ -d /etc/frr ]; then chown -R frr:frr /etc/frr; fi
if [ -f /etc/frr/daemons ]; then chown root:frr /etc/frr/daemons; chmod 0640 /etc/frr/daemons; fi
if command -v ldconfig >/dev/null 2>&1; then ldconfig; fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
  # The boot unit checks system-status.json. It performs no NLS key/CA setup
  # unless nls_service.service_enabled is explicitly true.
  if systemctl is-system-running --quiet; then
    systemctl enable --now nls-keygen.service
  else
    systemctl enable nls-keygen.service || true
  fi
fi
exit 0
POSTINST

cat > "$PKG_ROOT/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
  systemctl stop frr.service >/dev/null 2>&1 || true
  systemctl disable frr.service >/dev/null 2>&1 || true
fi
if command -v ldconfig >/dev/null 2>&1; then ldconfig; fi
exit 0
PRERM

chmod 0755 "$PKG_ROOT/DEBIAN/postinst" "$PKG_ROOT/DEBIAN/prerm"
dpkg-deb --root-owner-group --build "$PKG_ROOT" "$OUT_DIR/nls-netos-frr_${VERSION}_${ARCH}.deb"
dpkg-deb --info "$OUT_DIR/nls-netos-frr_${VERSION}_${ARCH}.deb"
echo "Package created: $OUT_DIR/nls-netos-frr_${VERSION}_${ARCH}.deb"
