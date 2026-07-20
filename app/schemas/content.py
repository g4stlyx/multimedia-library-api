from __future__ import annotations

import re

from pydantic import ValidationInfo

COMMENT_BODY_MAX_LENGTH = 2_000
REVIEW_BODY_MAX_LENGTH = 5_000
LIST_DESCRIPTION_MAX_LENGTH = 5_000
LIST_ITEM_NOTE_MAX_LENGTH = 2_000
PRIVATE_NOTE_MAX_LENGTH = 5_000

_MARKUP_TAG = re.compile(r"<\s*(?:/?[a-zA-Z][^>]*|![^>]*|\?[^>]*?)>")


def _normalize_plain_text(value: str | None) -> str | None:
    """Normalize user-authored text and reject markup/control characters.

    API responses are rendered as text. Rejecting markup at the boundary prevents
    storing a second, unsafe content format before a vetted sanitizer exists.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if _MARKUP_TAG.search(value):
        raise ValueError("Markup is not supported")
    if any(ord(char) < 32 and char not in {"\n", "\r", "\t"} for char in value):
        raise ValueError("Text contains unsupported control characters")
    return value


def validate_optional_plain_text(value: str | None, info: ValidationInfo) -> str | None:
    return _normalize_plain_text(value)


def validate_required_plain_text(value: str, info: ValidationInfo) -> str:
    normalized = _normalize_plain_text(value)
    if normalized is None:
        raise ValueError("Text must not be blank")
    return normalized
