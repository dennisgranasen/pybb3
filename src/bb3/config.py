from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def dotenv_values(path: str | Path = ".env") -> dict[str, str]:
    """Read the small dotenv subset used by pybb3."""
    source = Path(path)
    if not source.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def environment_value(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    dotenv: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve one setting, with the real environment taking precedence."""
    env = os.environ if environ is None else environ
    value = env[name] if name in env else (dotenv or {}).get(name)
    return value.strip() if value and value.strip() else None
