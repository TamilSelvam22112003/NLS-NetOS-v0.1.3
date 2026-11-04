#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build/frr-src"
STAGE_DIR="${ROOT_DIR}/build/rootfs"
FRR_REPO="${FRR_REPO:-https://github.com/FRRouting/frr.git}"
FRR_REF="${FRR_REF:-master}"
JOBS="${JOBS:-$(nproc)}"

if [[ $EUID -ne 0 ]]; then SUDO=sudo; else SUDO=""; fi
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
 git ca-certificates build-essential autoconf automake libtool pkg-config \
 make gcc g++ bison flex python3 python3-dev python3-pip python3-setuptools \
 libreadline-dev libncurses-dev libjson-c-dev libcap-dev libpam0g-dev \
 libsystemd-dev libsnmp-dev libelf-dev libunwind-dev libyang2-dev \
 libpcre2-dev libxml2-dev libsqlite3-dev libzmq3-dev

mkdir -p "$(dirname "$BUILD_DIR")" "$STAGE_DIR"
if [[ ! -d "$BUILD_DIR/.git" ]]; then git clone --filter=blob:none "$FRR_REPO" "$BUILD_DIR"; fi
git -C "$BUILD_DIR" fetch --tags origin
git -C "$BUILD_DIR" checkout --force "$FRR_REF"
cd "$BUILD_DIR"
if [[ -x ./bootstrap.sh ]]; then ./bootstrap.sh; elif [[ -x ./bootstrap ]]; then ./bootstrap; fi
CONFIGURE_ARGS=(--prefix=/usr --sbindir=/usr/lib/frr --sysconfdir=/etc --localstatedir=/var --runstatedir=/var/run --enable-systemd --enable-multipath=64)
[[ -x ./configure ]] || { echo "ERROR: configure script missing after bootstrap" >&2; exit 1; }
./configure "${CONFIGURE_ARGS[@]}"
make -j"$JOBS"
$SUDO make DESTDIR="$STAGE_DIR" install
mkdir -p "$STAGE_DIR/etc/frr" "$STAGE_DIR/usr/sbin/frr" "$STAGE_DIR/usr/lib/frr" "$STAGE_DIR/usr/share/doc/frr" "$STAGE_DIR/var/log/frr" "$STAGE_DIR/var/run/frr" "$STAGE_DIR/lib/systemd/system"
for f in daemons vtysh.conf zebra.conf; do
  [[ -e "$STAGE_DIR/etc/frr/$f" ]] || install -m 0640 "$ROOT_DIR/etc/frr/$f" "$STAGE_DIR/etc/frr/$f"
done
if [[ -d "$BUILD_DIR/doc" ]]; then cp -a "$BUILD_DIR/doc/." "$STAGE_DIR/usr/share/doc/frr/" 2>/dev/null || true; fi
if [[ -d "$BUILD_DIR/examples" ]]; then mkdir -p "$STAGE_DIR/usr/share/doc/frr/examples"; cp -a "$BUILD_DIR/examples/." "$STAGE_DIR/usr/share/doc/frr/examples/" 2>/dev/null || true; fi
install -m 0644 "$ROOT_DIR/lib/systemd/system/frr.service" "$STAGE_DIR/lib/systemd/system/frr.service"
echo "FRR staged in $STAGE_DIR. Inspect with: find '$STAGE_DIR' -type f"
