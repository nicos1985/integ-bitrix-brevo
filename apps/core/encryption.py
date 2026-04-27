from cryptography.fernet import Fernet
from django.conf import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.FIELD_ENCRYPTION_KEY
        if isinstance(key, str):
            key = key.encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt_value(value: str | None) -> str | None:
    """Encrypt a plaintext string. Returns None if value is None."""
    if value is None:
        return None
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str | None) -> str | None:
    """Decrypt a previously encrypted string. Returns None if value is None."""
    if value is None:
        return None
    return _get_fernet().decrypt(value.encode()).decode()
