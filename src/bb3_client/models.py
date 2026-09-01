from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Formation:
    team_id: str
    name: str
    formation_type: int
    pitch_map: dict[str, dict[str, int]]
    formation_id: str | None = None

    def data_dict(self) -> dict[str, Any]:
        return {"pitchMap": self.pitch_map}


@dataclass(slots=True)
class CollectionItem:
    item_id: str
    label: str | None = None
    behaviour: str | None = None
    instance_ids: list[str] = field(default_factory=list)
