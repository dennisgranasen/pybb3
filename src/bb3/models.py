from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import xml.etree.ElementTree as ET

from .encoding import b64_decode_text


def _int(element: ET.Element | None, path: str, default: int = 0) -> int:
    text = element.findtext(path) if element is not None else None
    try:
        return int(text) if text not in (None, "") else default
    except ValueError:
        return default


def _bool(element: ET.Element | None, path: str, default: bool = False) -> bool:
    text = element.findtext(path) if element is not None else None
    if text is None:
        return default
    return text.strip().lower() in {"1", "true", "yes"}


def _b64(element: ET.Element | None, path: str) -> str | None:
    text = element.findtext(path) if element is not None else None
    if not text:
        return None
    try:
        return b64_decode_text(text)
    except Exception:
        # Keep protocol parsing forward-compatible if a field that normally
        # contains Base64 is temporarily emitted as plain text.
        return text


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


@dataclass(slots=True, frozen=True)
class PlayerCharacteristic:
    characteristic_id: int
    value: int
    bonuses: int = 0
    maluses: int = 0


@dataclass(slots=True, frozen=True)
class PlayerSkillOption:
    skill_id: int
    available: bool
    choosable: bool
    cost: int
    team_value: int


@dataclass(slots=True, frozen=True)
class PlayerSkillCategory:
    category: int
    affinity: int
    cost_random: int
    team_value_random: int
    team_value_chosen: int
    random_available: bool
    random_choosable: bool
    skills: tuple[PlayerSkillOption, ...] = ()


@dataclass(slots=True)
class Player:
    player_id: str | None
    ugc_id: str | None
    name: str | None
    position_id: int
    number: int
    slot_number: int | None
    level: int
    spp: int
    level_up_status: int
    value: int
    dead: bool
    miss_next_game: bool
    retirement_status: int
    can_be_updated: bool
    has_original_name: bool
    skill_ids: tuple[int, ...]
    characteristics: tuple[PlayerCharacteristic, ...]
    casualty_ids: tuple[int, ...]
    raw_xml: str


@dataclass(slots=True)
class RosterPosition:
    position_id: int
    cost: int
    maximum: int
    starting_skill_ids: tuple[int, ...]
    characteristics: tuple[PlayerCharacteristic, ...]
    skill_categories: tuple[PlayerSkillCategory, ...]
    raw_xml: str


@dataclass(slots=True, frozen=True)
class RosterizedInducement:
    inducement_id: int
    number: int
    available: bool
    maximum: int
    cost: int
    original_cost: int


@dataclass(slots=True)
class TeamRoster:
    can_add_starplayer: bool
    can_be_redrafted: bool
    nb_slots: int
    can_be_updated_reason: str | None
    players: tuple[Player, ...]
    positions: tuple[RosterPosition, ...]
    rosterized_inducements: tuple[RosterizedInducement, ...]
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "TeamRoster":
        roster = root.find("Roster")
        if roster is None:
            raise ValueError("ResponseGetTeamRoster contained no Roster")

        positions = tuple(
            _parse_roster_position(line)
            for line in roster.findall(
                "./RaceRoster/Slots/RosterSlot/Lines/RosterSlotLine"
            )
        )

        players = tuple(
            _parse_player(slot.find("Player"), slot_number=_int(slot, "Number"))
            for slot in roster.findall("./TeamRoster/TeamRosterSlot")
            if slot.find("Player") is not None
        )

        inducements: list[RosterizedInducement] = []
        for item in roster.findall(
            "./RosterizedInducements/RosterizedInducement"
        ):
            inducement = item.find("Inducement")
            if inducement is None:
                continue
            inducements.append(
                RosterizedInducement(
                    inducement_id=_int(inducement, "Id"),
                    number=_int(item, "Number"),
                    available=_bool(inducement, "Available"),
                    maximum=_int(inducement, "Max"),
                    cost=_int(inducement, "Cost"),
                    original_cost=_int(inducement, "OriginalCost"),
                )
            )

        return cls(
            can_add_starplayer=_bool(roster, "CanAddStarplayer"),
            can_be_redrafted=_bool(roster, "CanBeRedrafted"),
            nb_slots=_int(roster, "Nb_slots"),
            can_be_updated_reason=roster.findtext("CanBeUpdatedReason") or None,
            players=players,
            positions=positions,
            rosterized_inducements=tuple(inducements),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True)
class PlayerImprovements:
    skill_categories: tuple[PlayerSkillCategory, ...]
    characteristic_available: bool
    characteristic_choosable: bool
    characteristic_cost: int
    spent_spp: int
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "PlayerImprovements":
        return cls(
            skill_categories=tuple(
                _parse_skill_category(category)
                for category in root.findall("./SkillCategories/PlayerSkillCategory")
            ),
            characteristic_available=_bool(root, "IsCharacteristicAvailable"),
            characteristic_choosable=_bool(root, "IsCharacteristicChoosable"),
            characteristic_cost=_int(root, "CharacteristicCost"),
            spent_spp=_int(root, "SpentSpp"),
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


@dataclass(slots=True, frozen=True)
class RandomSkillResult:
    skill_id: int
    has_left: bool


@dataclass(slots=True, frozen=True)
class CharacteristicUpgrade:
    characteristic_id: int
    available: bool
    team_value: int
    message: str | None = None


@dataclass(slots=True)
class CharacteristicRoll:
    roll: int
    can_take_secondary_skill: bool
    characteristics: tuple[CharacteristicUpgrade, ...]
    raw_xml: str

    @classmethod
    def from_response(cls, root: ET.Element) -> "CharacteristicRoll":
        upgrades = tuple(
            CharacteristicUpgrade(
                characteristic_id=_int(item, "Id"),
                available=_bool(item, "Available"),
                team_value=_int(item, "TeamValue"),
                message=item.findtext("Message") or None,
            )
            for item in root.findall("./Characteristics/CharacteristicUpgrade")
        )
        return cls(
            roll=_int(root, "Roll"),
            can_take_secondary_skill=_bool(root, "CanTakeSecondarySkill"),
            characteristics=upgrades,
            raw_xml=ET.tostring(root, encoding="unicode"),
        )


def _parse_characteristics(parent: ET.Element | None) -> tuple[PlayerCharacteristic, ...]:
    if parent is None:
        return ()
    return tuple(
        PlayerCharacteristic(
            characteristic_id=_int(item, "Characteristic"),
            value=_int(item, "Value"),
            bonuses=_int(item, "NbBonuses"),
            maluses=_int(item, "NbMaluses"),
        )
        for item in parent.findall("./PlayerCharacteristicsEntry")
    )


def _parse_skill_category(category: ET.Element) -> PlayerSkillCategory:
    skills = tuple(
        PlayerSkillOption(
            skill_id=_int(skill, "SkillId"),
            available=_bool(skill, "IsAvailable"),
            choosable=_bool(skill, "IsChoosable"),
            cost=_int(skill, "Cost"),
            team_value=_int(skill, "TeamValue"),
        )
        for skill in category.findall("./Skills/PlayerSkill")
    )
    return PlayerSkillCategory(
        category=_int(category, "Category"),
        affinity=_int(category, "Affinity"),
        cost_random=_int(category, "CostRandom"),
        team_value_random=_int(category, "TeamValueRandom"),
        team_value_chosen=_int(category, "TeamValueChosen"),
        random_available=_bool(category, "IsRandomAvailable"),
        random_choosable=_bool(category, "IsRandomChoosable"),
        skills=skills,
    )


def _parse_player(player: ET.Element | None, *, slot_number: int | None) -> Player:
    if player is None:
        raise ValueError("TeamRosterSlot contained no Player")
    casualties: list[int] = []
    for item in player.findall("./Casualties/*"):
        try:
            casualties.append(int(item.text or ""))
        except ValueError:
            continue

    return Player(
        player_id=_b64(player, "Id"),
        ugc_id=_b64(player, "UgcId"),
        name=_b64(player, "Name"),
        position_id=_int(player, "Position"),
        number=_int(player, "Number"),
        slot_number=slot_number,
        level=_int(player, "Level"),
        spp=_int(player, "Spp"),
        level_up_status=_int(player, "LevelUpStatus"),
        value=_int(player, "Value"),
        dead=_bool(player, "Dead"),
        miss_next_game=_bool(player, "MissNextGame"),
        retirement_status=_int(player, "RetirementStatus"),
        can_be_updated=_bool(player, "CanBeUpdated"),
        has_original_name=_bool(player, "HasOriginalName"),
        skill_ids=tuple(
            int(item.text)
            for item in player.findall("./Skills/SkillsItem")
            if item.text and item.text.isdigit()
        ),
        characteristics=_parse_characteristics(player.find("Characteristics")),
        casualty_ids=tuple(casualties),
        raw_xml=ET.tostring(player, encoding="unicode"),
    )


def _parse_roster_position(line: ET.Element) -> RosterPosition:
    template = line.find("Player")
    return RosterPosition(
        position_id=_int(line, "Position"),
        cost=_int(line, "Cost"),
        maximum=_int(line, "Max"),
        starting_skill_ids=tuple(
            int(item.text)
            for item in line.findall("./Player/Skills/SkillsItem")
            if item.text and item.text.isdigit()
        ),
        characteristics=_parse_characteristics(
            template.find("Characteristics") if template is not None else None
        ),
        skill_categories=tuple(
            _parse_skill_category(category)
            for category in line.findall("./SkillsCategories/PlayerSkillCategory")
        ),
        raw_xml=ET.tostring(line, encoding="unicode"),
    )
