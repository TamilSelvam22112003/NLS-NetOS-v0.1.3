#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# NLS-NetOS first-boot/local key provisioning.
# Private material is generated on the target router and is never packaged.

readonly BASE_DIR="/var/lib/nls-netos/crypto"
readonly AES_DIR="${BASE_DIR}/aes-256"
readonly RSA_DIR="${BASE_DIR}/RSA-2048"
readonly AES_KEY="${AES_DIR}/aes256.key"
readonly RSA_PRIVATE="${RSA_DIR}/private_key.pem"
readonly RSA_PUBLIC="${RSA_DIR}/public_key.pem"

log() { printf '[nls-keygen] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "must run as root"
command -v openssl >/dev/null 2>&1 || die "OpenSSL is required; install it before enabling this service"

install -d -o root -g root -m 0700 "$BASE_DIR" "$AES_DIR" "$RSA_DIR"

# Never silently replace persistent key material.
if [[ -e "$AES_KEY" ]]; then
    [[ -f "$AES_KEY" && ! -L "$AES_KEY" ]] || die "AES key path is not a regular file"
    [[ $(stat -c '%s' "$AES_KEY") -eq 32 ]] || die "existing AES key is not 32 bytes; manual recovery required"
    log "Existing AES-256 key validated; preserving it"
else
    tmp_aes=$(mktemp "${AES_DIR}/.aes256.XXXXXXXX")
    trap 'rm -f "${tmp_aes:-}" "${tmp_private:-}" "${tmp_public:-}"' EXIT
    openssl rand -out "$tmp_aes" 32
    chmod 0600 "$tmp_aes"
    mv -n "$tmp_aes" "$AES_KEY"
    [[ -f "$AES_KEY" ]] || die "failed to install AES key"
    log "Generated AES-256 key"
fi
chown root:root "$AES_KEY"
chmod 0600 "$AES_KEY"

# Treat either existing RSA component as an existing identity. Never overwrite.
if [[ -e "$RSA_PRIVATE" || -e "$RSA_PUBLIC" ]]; then
    [[ -f "$RSA_PRIVATE" && ! -L "$RSA_PRIVATE" ]] || die "RSA private key missing or unsafe; manual recovery required"
    [[ -f "$RSA_PUBLIC" && ! -L "$RSA_PUBLIC" ]] || die "RSA public key missing or unsafe; manual recovery required"
    openssl pkey -in "$RSA_PRIVATE" -check -noout >/dev/null
    openssl pkey -pubin -in "$RSA_PUBLIC" -pubcheck -noout >/dev/null
    tmp_public=$(mktemp "${RSA_DIR}/.public-check.XXXXXXXX")
    trap 'rm -f "${tmp_aes:-}" "${tmp_private:-}" "${tmp_public:-}"' EXIT
    openssl pkey -in "$RSA_PRIVATE" -pubout -out "$tmp_public"
    cmp -s "$tmp_public" "$RSA_PUBLIC" || die "RSA public/private keys do not match"
    rm -f "$tmp_public"
    log "Existing RSA-2048 key pair validated; preserving it"
else
    tmp_private=$(mktemp "${RSA_DIR}/.private.XXXXXXXX")
    tmp_public=$(mktemp "${RSA_DIR}/.public.XXXXXXXX")
    trap 'rm -f "${tmp_aes:-}" "${tmp_private:-}" "${tmp_public:-}"' EXIT
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$tmp_private"
    openssl pkey -in "$tmp_private" -pubout -out "$tmp_public"
    openssl pkey -in "$tmp_private" -check -noout >/dev/null
    openssl pkey -pubin -in "$tmp_public" -pubcheck -noout >/dev/null
    chmod 0600 "$tmp_private"
    chmod 0644 "$tmp_public"
    mv -n "$tmp_private" "$RSA_PRIVATE"
    mv -n "$tmp_public" "$RSA_PUBLIC"
    [[ -f "$RSA_PRIVATE" && -f "$RSA_PUBLIC" ]] || die "failed to install RSA key pair"
    log "Generated RSA-2048 key pair"
fi

chown root:root "$RSA_PRIVATE" "$RSA_PUBLIC"
chmod 0600 "$RSA_PRIVATE"
chmod 0644 "$RSA_PUBLIC"
log "Key initialization completed"
