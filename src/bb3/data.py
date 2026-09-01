from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from .config import dotenv_values, environment_value


class BB3DataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BB3Data:
    """Resolved locations of BB3's external static-data archives."""

    rules_engine_zip: Path
    data_zip: Path

    @classmethod
    def from_installation(cls, path: str | os.PathLike[str]) -> "BB3Data":
        root = Path(path).expanduser().resolve()
        offline_server = root / "BB3" / "Content" / "OfflineServer"
        return cls._validated(
            offline_server / "bb3rulesengine.zip",
            offline_server / "bb3.zip",
        )

    @classmethod
    def from_env(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        dotenv_path: str | Path = ".env",
    ) -> "BB3Data | None":
        dotenv = dotenv_values(dotenv_path)
        root_value = environment_value("BB3_PATH", environ=environ, dotenv=dotenv)
        rules_value = environment_value(
            "BB3_RULES_ENGINE_ZIP", environ=environ, dotenv=dotenv
        )
        data_value = environment_value("BB3_DATA_ZIP", environ=environ, dotenv=dotenv)
        if not any((root_value, rules_value, data_value)):
            return None

        offline_server = None
        if root_value:
            offline_server = (
                Path(root_value).expanduser().resolve()
                / "BB3"
                / "Content"
                / "OfflineServer"
            )
        rules_path = (
            Path(rules_value).expanduser().resolve()
            if rules_value
            else offline_server / "bb3rulesengine.zip" if offline_server else None
        )
        data_path = (
            Path(data_value).expanduser().resolve()
            if data_value
            else offline_server / "bb3.zip" if offline_server else None
        )
        return cls._validated(rules_path, data_path)

    @classmethod
    def _validated(
        cls, rules_path: Path | None, data_path: Path | None
    ) -> "BB3Data":
        missing: list[str] = []
        if rules_path is None:
            missing.append(
                "rules archive: BB3_RULES_ENGINE_ZIP and BB3_PATH are unset"
            )
        elif not rules_path.is_file():
            missing.append(f"rules archive: {rules_path}")
        if data_path is None:
            missing.append("data archive: BB3_DATA_ZIP and BB3_PATH are unset")
        elif not data_path.is_file():
            missing.append(f"data archive: {data_path}")
        if missing:
            attempted = "\n  - ".join(missing)
            raise BB3DataError(
                "Could not resolve BB3 static-data archives; attempted:\n"
                f"  - {attempted}"
            )
        return cls(rules_path, data_path)
