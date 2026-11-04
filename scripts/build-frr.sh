#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
FRR_DIR="${ROOT_DIR}/third_party/frr"
LIBYANG_SRC="${ROOT_DIR}/build/libyang-src"
LIBYANG_BUILD="${ROOT_DIR}/build/libyang-build"
STAGE_DIR="${ROOT_DIR}/build/rootfs"
JOBS="${JOBS:-$(nproc)}"

if [[ $EUID -ne 0 ]]; then SUDO=sudo; else SUDO=""; fi
if ! git -C "$FRR_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "FRR submodule missing. Run: git submodule update --init --recursive" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends \
 git ca-certificates build-essential autoconf automake libtool pkg-config cmake \
 make gcc g++ bison flex python3 python3-dev python3-pip python3-setuptools \
 libreadline-dev libncurses-dev libjson-c-dev libcap-dev libpam0g-dev \
 libsystemd-dev libsnmp-dev libelf-dev libunwind-dev libyang2-dev \
 libpcre2-dev libxml2-dev libsqlite3-dev libzmq3-dev libprotobuf-c-dev \
 protobuf-c-compiler libgrpc-dev libgrpc++-dev libprotobuf-dev

mkdir -p "$LIBYANG_SRC" "$LIBYANG_BUILD" "$STAGE_DIR"
# Ubuntu 24.04 provides libyang 2.1.30, below the minimum 2.1.128 required
# by current FRR. Build the FRR-documented 2.1.148 release into /usr/local.
if [[ ! -f "$LIBYANG_SRC/CMakeLists.txt" ]]; then
  git clone --depth 1 --branch v2.1.148 https://github.com/CESNET/libyang.git "$LIBYANG_SRC"
fi
cmake -S "$LIBYANG_SRC" -B "$LIBYANG_BUILD" \
  -D CMAKE_INSTALL_PREFIX=/usr/local \
  -D CMAKE_BUILD_TYPE=Release
cmake --build "$LIBYANG_BUILD" --parallel "$JOBS"
$SUDO cmake --install "$LIBYANG_BUILD"
$SUDO ldconfig
export PKG_CONFIG_PATH="/usr/local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
pkg-config --atleast-version=2.1.128 libyang
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
# Bundle the compatible libyang runtime because Ubuntu 24.04's packaged
# 2.1.30 library is too old for this FRR build.
install -d "$STAGE_DIR/usr/lib"
cp -a /usr/local/lib/libyang.so.2* "$STAGE_DIR/usr/lib/"
echo "FRR source: $(git -C "$FRR_DIR" rev-parse HEAD)"
echo "FRR build and staged installation: $STAGE_DIR"
