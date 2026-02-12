"""Security utilities for token encryption and JWT handling.

This module provides cryptographic functions for securing OAuth tokens
at rest and managing application JWT sessions.
"""

import base64
import logging
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Get or create the Fernet encryption instance.

    Returns
    -------
    Fernet
        Fernet instance initialized with the encryption key.

    Raises
    ------
    ValueError
        If TOKEN_ENCRYPTION_KEY is not properly configured.
    """
    global _fernet
    if _fernet is None:
        settings = get_settings()
        try:
            key = settings.token_encryption_key.encode()
            if len(base64.urlsafe_b64decode(key)) != 32:
                raise ValueError("Encryption key must be 32 bytes when decoded")
            _fernet = Fernet(key)
        except Exception as exc:
            logger.exception("Failed to initialize Fernet encryption")
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY must be a valid base64-encoded 32-byte key"
            ) from exc
    return _fernet


def encrypt_token(token: str) -> str:
    """Encrypt a token for secure storage.

    Parameters
    ----------
    token : str
        The plaintext token to encrypt.

    Returns
    -------
    str
        Base64-encoded encrypted token.
    """
    fernet = _get_fernet()
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str | None:
    """Decrypt an encrypted token.

    Parameters
    ----------
    encrypted_token : str
        The encrypted token string.

    Returns
    -------
    str or None
        The decrypted token, or None if decryption fails.
    """
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.warning("Failed to decrypt token - invalid or corrupted")
        return None


def create_jwt_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT token for user session.

    Parameters
    ----------
    user_id : str
        The user ID to encode in the token.
    expires_delta : timedelta, optional
        Token expiration time. Defaults to 24 hours.

    Returns
    -------
    str
        Encoded JWT token.
    """
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(hours=24)

    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def decode_jwt_token(token: str) -> dict | None:
    """Decode and validate a JWT token.

    Parameters
    ----------
    token : str
        The JWT token to decode.

    Returns
    -------
    dict or None
        The decoded payload, or None if invalid.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid JWT token: %s", exc)
        return None
