from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"

# Normalized, case-insensitive names. Keep this list deliberately broader than
# the current wire format so debug tooling remains safe as it evolves.
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "apikey",
        "apipassword",
        "authtoken",
        "authorization",
        "guardcode",
        "guarddata",
        "legacycredential",
        "password",
        "refreshtoken",
        "steamguardcode",
        "steamguardsecret",
        "steampassword",
        "steamauthticket",
        "steamauthsessionticket",
        "steamticket",
    }
)

_FIELD_PATTERN = (
    r"api[_-]?key|api[_-]?password|auth[_-]?token|authorization|"
    r"guard[_-]?(?:code|data)|legacy[_-]?credential|password|"
    r"refresh[_-]?token|steam[_-]?password|steam[_-]?guard[_-]?(?:code|secret)|"
    r"steam[_-]?(?:auth[_-]?session[_-]?)?ticket"
)
_XML_SECRET_RE = re.compile(
    rf"(<(?P<name>{_FIELD_PATTERN})\b[^>]*>).*?(</(?P=name)\s*>)",
    flags=re.IGNORECASE | re.DOTALL,
)
_JSON_SECRET_RE = re.compile(
    rf'("(?:{_FIELD_PATTERN})"\s*:\s*)"(?:\\.|[^"\\])*"',
    flags=re.IGNORECASE,
)
_ASSIGNMENT_SECRET_RE = re.compile(
    rf"^(?P<prefix>\s*(?:{_FIELD_PATTERN})\s*=)[^\r\n]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_BEARER_RE = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")


def is_sensitive_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.casefold())
    return normalized in SENSITIVE_FIELD_NAMES


def redact_text(value: str) -> str:
    """Redact labelled credentials from XML, JSON, dotenv and log text."""

    value = _XML_SECRET_RE.sub(rf"\1{REDACTED}\3", value)
    value = _JSON_SECRET_RE.sub(rf'\1"{REDACTED}"', value)
    value = _ASSIGNMENT_SECRET_RE.sub(rf"\g<prefix>{REDACTED}", value)
    return _BEARER_RE.sub(rf"\1{REDACTED}", value)


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a recursively redacted copy suitable for diagnostic output."""

    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if is_sensitive_field(str(key)):
            redacted[str(key)] = REDACTED
        else:
            redacted[str(key)] = _redact_value(value)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
