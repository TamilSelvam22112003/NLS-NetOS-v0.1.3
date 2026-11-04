import pytest
from cryptography.exceptions import InvalidTag
from nls.crypto import generate_x25519_keypair, derive_session_key, encrypt, decrypt

def test_x25519_hkdf_agreement():
    a_priv, a_pub = generate_x25519_keypair(); b_priv, b_pub = generate_x25519_keypair()
    salt, info = b"0123456789abcdef", b"NLS-NetOS-v1/session"
    assert derive_session_key(a_priv, b_pub, salt, info) == derive_session_key(b_priv, a_pub, salt, info)

def test_aes_gcm_round_trip_and_aad():
    key = bytes(range(32)); nonce, ciphertext = encrypt(key, b"packet payload", b"nls header")
    assert decrypt(key, nonce, ciphertext, b"nls header") == b"packet payload"
    with pytest.raises(InvalidTag): decrypt(key, nonce, ciphertext, b"modified header")

def test_reject_bad_key_and_nonce():
    with pytest.raises(ValueError): encrypt(b"short", b"data")
    with pytest.raises(ValueError): encrypt(bytes(32), b"data", nonce=b"short")
