from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class BB3RulesError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuleRecord:
    table: str
    data: dict[str, Any]

    @property
    def code(self) -> int | None:
        value = self.data.get("code")
        return value if isinstance(value, int) else None

    @property
    def name(self) -> str | None:
        for key in ("data", "name"):
            value = self.data.get(key)
            if isinstance(value, str):
                return value
        return None

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class BB3Rules:
    """Read-only query layer over the game's external BB3Rules.json data file."""

    ENV_VAR = "BB3_RULES_FILE"

    def __init__(self, source_path: Path, payload: dict[str, Any], sha256: str):
        self.source_path = source_path
        self.payload = payload
        self.sha256 = sha256
        self._by_code: dict[str, dict[int, RuleRecord]] = {}
        self._by_name: dict[str, dict[str, RuleRecord]] = {}
        self._build_indexes()

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "BB3Rules":
        source = Path(path).expanduser().resolve()
        raw = source.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BB3RulesError(f"Invalid BB3 rules file: {source}") from exc
        if not isinstance(payload, dict):
            raise BB3RulesError(f"Expected JSON object in BB3 rules file: {source}")
        return cls(source, payload, hashlib.sha256(raw).hexdigest())

    @classmethod
    def from_env(cls) -> "BB3Rules | None":
        path = os.getenv(cls.ENV_VAR)
        return cls.load(path) if path else None

    def tables(self) -> tuple[str, ...]:
        return tuple(sorted(self.payload))

    def records(self, table: str) -> list[RuleRecord]:
        values = self.payload.get(table)
        if values is None:
            raise KeyError(table)
        if not isinstance(values, list):
            raise BB3RulesError(f"Rules table {table!r} is not a list")
        return [RuleRecord(table, item) for item in values if isinstance(item, dict)]

    def by_code(self, table: str, code: int) -> RuleRecord:
        try:
            return self._by_code[table][code]
        except KeyError as exc:
            raise KeyError(f"No {table} record with code={code}") from exc

    def by_name(self, table: str, name: str) -> RuleRecord:
        try:
            return self._by_name[table][name]
        except KeyError as exc:
            raise KeyError(f"No {table} record named {name!r}") from exc

    def position_by_code(self, code: int) -> RuleRecord:
        return self.by_code("bb3_rules_position", code)

    def position(self, name: str) -> RuleRecord:
        return self.by_name("bb3_rules_position", name)

    def race_by_code(self, code: int) -> RuleRecord:
        return self.by_code("bb3_rules_race", code)

    def race(self, name: str) -> RuleRecord:
        return self.by_name("bb3_rules_race", name)

    def skill_by_code(self, code: int) -> RuleRecord:
        return self.by_code("bb3_rules_skill", code)

    def special_rule_by_code(self, code: int) -> RuleRecord:
        return self.by_code("bb3_rules_special_rule", code)

    def team_improvement_by_code(self, code: int) -> RuleRecord:
        return self.by_code("bb3_rules_team_improvement", code)

    def position_characteristics(self, position_name: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.payload.get("bb3_rules_position_characteristics", []):
            if item.get("position") == position_name:
                characteristic = item.get("characteristic")
                value = item.get("value")
                if isinstance(characteristic, str) and isinstance(value, int):
                    result[characteristic] = value
        return result

    def position_skills(self, position_name: str) -> list[str]:
        result: list[str] = []
        for item in self.payload.get("bb3_rules_position_skills", []):
            if item.get("position") == position_name and isinstance(item.get("skill"), str):
                result.append(item["skill"])
        return result

    def _build_indexes(self) -> None:
        for table, values in self.payload.items():
            if not isinstance(values, list):
                continue
            code_index: dict[int, RuleRecord] = {}
            name_index: dict[str, RuleRecord] = {}
            for item in values:
                if not isinstance(item, dict):
                    continue
                record = RuleRecord(table, item)
                if isinstance(item.get("code"), int):
                    code_index[item["code"]] = record
                for key in ("data", "name"):
                    if isinstance(item.get(key), str):
                        name_index[item[key]] = record
            if code_index:
                self._by_code[table] = code_index
            if name_index:
                self._by_name[table] = name_index
