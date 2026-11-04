#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
FRR_DIR="${ROOT_DIR}/third_party/frr"
BUILD_DIR="${ROOT_DIR}/build/frr-build"
STAGE_DIR="${ROOT_DIR}/build/rootfs"
JOBS="${JOBS:-$(nproc)}"

if [[ $EUID -ne 0 ]]; then SUDO=sudo; else SUDO=""; fi
if [[ ! -d "$FRR_DIR/.git" ]]; then
  echo "FRR submodule missing. Run: git submodule update --init --recursive" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
 git ca-certificates build-essential autoconf automake libtool pkg-config \
 make gcc g++ bison flex python3 python3-dev python3-pip python3-setuptools \
 libreadline-dev libncurses-dev libjson-c-dev libcap-dev libpam0g-dev \
 libsystemd-dev libsnmp-dev libelf-dev libunwind-dev libyang2-dev \
 libpcre2-dev libxml2-dev libsqlite3-dev libzmq3-dev libprotobuf-c-dev \
 protobuf-c-compiler libgrpc-dev libgrpc++-dev libprotobuf-dev

mkdir -p "$BUILD_DIR" "$STAGE_DIR"
cd "$FRR_DIR"
git submodule update --init --recursive
./bootstrap.sh
CONFIGURE_ARGS=(
  --prefix=/usr
  --sysconfdir=/etc
  --localstatedir=/var
  --sbindir=/usr/lib/frr
  --bindir=/usr/bin
  --enable-vtysh
  --enable-watchfrr
  --enable-user=frr
  --enable-group=frr
  --enable-vty-group=frrvty
  --enable-multipath=64
)
./configure "${CONFIGURE_ARGS[@]}"
make -j"$JOBS"
$SUDO make DESTDIR="$STAGE_DIR" install

mkdir -p "$STAGE_DIR/etc/frr" "$STAGE_DIR/usr/sbin/frr" \
  "$STAGE_DIR/usr/lib/frr" "$STAGE_DIR/usr/share/doc/frr" \
  "$STAGE_DIR/var/log/frr" "$STAGE_DIR/var/run/frr" \
  "$STAGE_DIR/lib/systemd/system"
for f in daemons vtysh.conf zebra.conf; do
  [[ -e "$STAGE_DIR/etc/frr/$f" ]] || install -m 0640 "$ROOT_DIR/etc/frr/$f" "$STAGE_DIR/etc/frr/$f"
done
if [[ -d "$FRR_DIR/doc" ]]; then
  cp -a "$FRR_DIR/doc/." "$STAGE_DIR/usr/share/doc/frr/" 2>/dev/null || true
fi
if [[ -d "$FRR_DIR/examples" ]]; then
  mkdir -p "$STAGE_DIR/usr/share/doc/frr/examples"
  cp -a "$FRR_DIR/examples/." "$STAGE_DIR/usr/share/doc/frr/examples/" 2>/dev/null || true
fi
install -m 0644 "$ROOT_DIR/lib/systemd/system/frr.service" "$STAGE_DIR/lib/systemd/system/frr.service"
echo "FRR source: $(git -C "$FRR_DIR" rev-parse HEAD)"
echo "FRR build and staged installation: $STAGE_DIR"
