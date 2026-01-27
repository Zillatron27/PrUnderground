"""
Encryption utilities for sensitive data storage.

Uses Fernet symmetric encryption with a key derived from SECRET_KEY.
"""

import os
import hashlib
import logging
from base64 import urlsafe_b64encode
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet = None


def get_encryption_key() -> bytes:
    """Derive a Fernet-compatible key from SECRET_KEY."""
    secret = os.getenv("SECRET_KEY", "").encode()
    # Fernet requires a 32-byte key, base64-encoded
    key = hashlib.sha256(secret).digest()
    return urlsafe_b64encode(key)


def get_fernet() -> Fernet:
    """Get or create the Fernet instance."""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_encryption_key())
    return _fernet


def encrypt_api_key(plaintext: str) -> str:
    """
    Encrypt an API key for storage.

    Args:
        plaintext: The API key to encrypt

    Returns:
        Encrypted string (base64-encoded)
    """
    if not plaintext:
        return plaintext
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """
    Decrypt an API key from storage.

    Args:
        ciphertext: The encrypted API key

    Returns:
        Decrypted plaintext API key

    Note:
        If decryption fails (e.g., plaintext key from before encryption was added),
        returns the input unchanged. This allows for graceful migration.
    """
    if not ciphertext:
        return ciphertext
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Likely a plaintext key from before encryption was implemented
        logger.debug("Decryption failed - returning as plaintext (migration period)")
        return ciphertext
    except Exception as e:
        logger.warning(f"Unexpected decryption error: {e}")
        return ciphertext
