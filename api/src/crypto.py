"""
Encryption utilities for securing sensitive data.
"""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.form_models import Form, FormInputType

import logging

log = logging.getLogger(__name__)

def _get_fernet() -> Fernet:
    """
    Get Fernet instance using encryption key from environment.

    Derives a valid Fernet key from the JWT_SECRET using PBKDF2.
    """
    secret = os.getenv("ENCRYPTION_KEY", os.getenv("JWT_SECRET", "dev-secret"))
    salt = b"innomightlabs_salt"  # Static salt for deterministic key derivation
    log.info(f"SECRET: {secret}")    

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)


def encrypt(value: str) -> str:
    """
    Encrypt a string value.

    Args:
        value: Plain text to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    fernet = _get_fernet()
    encrypted = fernet.encrypt(value.encode())
    return encrypted.decode()


def decrypt(value: str) -> str:
    """
    Decrypt an encrypted string value.

    Args:
        value: Base64-encoded encrypted string

    Returns:
        Decrypted plain text
    """
    fernet = _get_fernet()
    decrypted = fernet.decrypt(value.encode())
    return decrypted.decode()


def encrypt_secret_fields(form: Form, data: dict) -> dict:
    """
    Encrypt all PASSWORD-type fields in the data based on form schema.

    Args:
        form: Form schema defining field types
        data: Dictionary of field values

    Returns:
        New dictionary with PASSWORD fields encrypted
    """
    result = data.copy()

    for field in form.form_inputs:
        if field.input_type == FormInputType.PASSWORD and field.name in result:
            result[field.name] = encrypt(result[field.name])

    return result


def decrypt_secret_fields(form: Form, data: dict) -> dict:
    """
    Decrypt all PASSWORD-type fields in the data based on form schema.

    Args:
        form: Form schema defining field types
        data: Dictionary of field values

    Returns:
        New dictionary with PASSWORD fields decrypted
    """
    result = data.copy()

    for field in form.form_inputs:
        if field.input_type == FormInputType.PASSWORD and field.name in result:
            result[field.name] = decrypt(result[field.name])

    return result
