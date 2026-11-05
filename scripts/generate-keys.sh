#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# NLS-NetOS first-boot/local key provisioning.
# Keys are generated on each target machine; no secret material belongs in Git.

readonly BASE_DIR="/var/lib/nls-netos/crypto"
readonly AES_DIR="${BASE_DIR}/aes-256"
readonly RSA_DIR="${BASE_DIR}/RSA-2048"
readonly AES_KEY="${AES_DIR}/aes256.key"
readonly RSA_PRIVATE="${RSA_DIR}/private_key.pem"
readonly RSA_PUBLIC="${RSA_DIR}/public_key.pem"

log() { printf '[nls-keygen] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

[[ ${EUID} -eq 0 ]] || die "must run as root"
command -v openssl >/dev/null 2>&1 || die "OpenSSL is required; install the openssl package before running"

install -d -o root -g root -m 0700 "$BASE_DIR" "$AES_DIR" "$RSA_DIR"

tmp_aes=""
tmp_private=""
tmp_public=""
cleanup() {
    [[ -z "$tmp_aes" ]] || rm -f -- "$tmp_aes"
    [[ -z "$tmp_private" ]] || rm -f -- "$tmp_private"
    [[ -z "$tmp_public" ]] || rm -f -- "$tmp_public"
}
trap cleanup EXIT

# Existing key files are validated and preserved; never rotate silently.
if [[ -e "$AES_KEY" || -L "$AES_KEY" ]]; then
    [[ -f "$AES_KEY" && ! -L "$AES_KEY" ]] || die "AES key path is not a regular file"
    [[ $(stat -c '%s' "$AES_KEY") -eq 32 ]] || die "existing AES key is not exactly 32 bytes; manual recovery required"
    log "Existing AES-256 key validated; preserving it"
else
    tmp_aes=$(mktemp "${AES_DIR}/.aes256.XXXXXXXX")
    openssl rand -out "$tmp_aes" 32
    chmod 0600 "$tmp_aes"
    mv -n -- "$tmp_aes" "$AES_KEY"
    tmp_aes=""
    [[ -f "$AES_KEY" && $(stat -c '%s' "$AES_KEY") -eq 32 ]] || die "failed to install AES-256 key"
    log "Generated AES-256 key"
fi
chown root:root "$AES_KEY"
chmod 0600 "$AES_KEY"

# If either RSA component exists, require a complete, matching pair.
if [[ -e "$RSA_PRIVATE" || -L "$RSA_PRIVATE" || -e "$RSA_PUBLIC" || -L "$RSA_PUBLIC" ]]; then
    [[ -f "$RSA_PRIVATE" && ! -L "$RSA_PRIVATE" ]] || die "RSA private key missing or unsafe; manual recovery required"
    [[ -f "$RSA_PUBLIC" && ! -L "$RSA_PUBLIC" ]] || die "RSA public key missing or unsafe; manual recovery required"
    openssl pkey -in "$RSA_PRIVATE" -check -noout >/dev/null
    openssl pkey -pubin -in "$RSA_PUBLIC" -pubcheck -noout >/dev/null
    tmp_public=$(mktemp "${RSA_DIR}/.public-check.XXXXXXXX")
    openssl pkey -in "$RSA_PRIVATE" -pubout -out "$tmp_public"
    cmp -s "$tmp_public" "$RSA_PUBLIC" || die "RSA public/private keys do not match"
    rm -f -- "$tmp_public"
    tmp_public=""
    log "Existing RSA-2048 key pair validated; preserving it"
else
    tmp_private=$(mktemp "${RSA_DIR}/.private.XXXXXXXX")
    tmp_public=$(mktemp "${RSA_DIR}/.public.XXXXXXXX")
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$tmp_private"
    openssl pkey -in "$tmp_private" -pubout -out "$tmp_public"
    openssl pkey -in "$tmp_private" -check -noout >/dev/null
    openssl pkey -pubin -in "$tmp_public" -pubcheck -noout >/dev/null
    chmod 0600 "$tmp_private"
    chmod 0644 "$tmp_public"
    mv -n -- "$tmp_private" "$RSA_PRIVATE"
    tmp_private=""
    mv -n -- "$tmp_public" "$RSA_PUBLIC"
    tmp_public=""
    [[ -f "$RSA_PRIVATE" && -f "$RSA_PUBLIC" ]] || die "failed to install RSA key pair"
    log "Generated RSA-2048 key pair"
fi

chown root:root "$RSA_PRIVATE" "$RSA_PUBLIC"
chmod 0600 "$RSA_PRIVATE"
chmod 0644 "$RSA_PUBLIC"

# Final structural and cryptographic verification.
[[ $(stat -c '%s' "$AES_KEY") -eq 32 ]] || die "AES key size verification failed"
openssl pkey -in "$RSA_PRIVATE" -check -noout >/dev/null
openssl pkey -pubin -in "$RSA_PUBLIC" -pubcheck -noout >/dev/null

log "Key initialization completed"
log "AES-256 key: $AES_KEY"
log "RSA private key: $RSA_PRIVATE"
log "RSA public key: $RSA_PUBLIC"
