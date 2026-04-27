import hashlib
import json
import logging

logger = logging.getLogger(__name__)


def normalize_email(email: str | None) -> str | None:
    """Normalize an email address to lowercase, stripped."""
    if not email:
        return None
    return email.strip().lower()


def build_contact_hash(data: dict) -> str:
    """
    Build a deterministic SHA-256 hash of the given contact field dict.
    Used to detect whether fields have actually changed before writing.
    """
    normalized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode()).hexdigest()


def safe_get_list_value(lst: list, index: int, key: str, default=None):
    """Safely retrieve a key from an item in a list, or return default."""
    try:
        return lst[index].get(key, default)
    except (IndexError, AttributeError, TypeError):
        return default
