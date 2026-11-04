"""Cryptographic primitives for the experimental NLS data plane."""
from __future__ import annotations
import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
NONCE_SIZE = 12
KEY_SIZE = 32

def generate_x25519_keypair() -> tuple[X25519PrivateKey, X25519PublicKey]:
    private_key = X25519PrivateKey.generate()
    return private_key, private_key.public_key()

def derive_session_key(private_key: X25519PrivateKey, peer_public_key: X25519PublicKey, salt: bytes, info: bytes, length: int = KEY_SIZE) -> bytes:
    if len(salt) < 16: raise ValueError("HKDF salt must contain at least 16 bytes")
    if not info: raise ValueError("HKDF context info must not be empty")
    shared_secret = private_key.exchange(peer_public_key)
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(shared_secret)

def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"", nonce: bytes | None = None) -> tuple[bytes, bytes]:
    if len(key) != KEY_SIZE: raise ValueError("AES-256-GCM requires a 32-byte key")
    nonce = os.urandom(NONCE_SIZE) if nonce is None else nonce
    if len(nonce) != NONCE_SIZE: raise ValueError("AES-GCM nonce must be 12 bytes")
    return nonce, AESGCM(key).encrypt(nonce, plaintext, aad)

def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
    if len(key) != KEY_SIZE or len(nonce) != NONCE_SIZE: raise ValueError("invalid AES-256-GCM key or nonce length")
    return AESGCM(key).decrypt(nonce, ciphertext, aad)
