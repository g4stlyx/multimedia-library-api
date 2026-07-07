import re
import unicodedata

def normalize_email(value: str) -> str:
    return value.strip().casefold()


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def normalize_title(value: str) -> str:
    # Convert to lowercase
    val = value.lower()
    # Normalize and remove accents (diacritics)
    val = "".join(
        c for c in unicodedata.normalize("NFD", val)
        if unicodedata.category(c) != "Mn"
    )
    # Remove punctuation/special characters, keeping alphanumeric and spaces
    val = re.sub(r"[^a-z0-9\s]", "", val)
    # Collapse consecutive whitespace and strip edges
    val = re.sub(r"\s+", " ", val).strip()
    return val

