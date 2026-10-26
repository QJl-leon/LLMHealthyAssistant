from __future__ import annotations
import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
_NONCE_LEN = 12

def _key() -> bytes:
    raw = os.getenv('KMS_KEY_DEV', 'lha-dev-kms-key-change-me').encode('utf-8')
    return hashlib.sha256(raw).digest()

def encrypt(plaintext: str) -> str:
    aesgcm = AESGCM(_key())
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return (nonce + ciphertext).hex()

def decrypt(ciphertext_hex: str) -> str:
    raw = bytes.fromhex(ciphertext_hex)
    nonce, ct = (raw[:_NONCE_LEN], raw[_NONCE_LEN:])
    aesgcm = AESGCM(_key())
    return aesgcm.decrypt(nonce, ct, None).decode('utf-8')

def content_hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()

def maybe_decrypt(value: str) -> str:
    try:
        return decrypt(value)
    except Exception:
        return value
