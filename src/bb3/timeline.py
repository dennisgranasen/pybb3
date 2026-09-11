"""Stateful extraction of domain events from Blood Bowl 3 replays."""
from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET

from .enums import (
    BlockOutcome, CasualtyOutcome, InjuryOutcome, PlayerSituation, PlayerStatus,
    RollType, SequenceType, SpecialCard, StepType,
)


def _name(e: ET.Element) -> str:
    return e.tag.rsplit("}", 1)[-1]


def _direct(e: ET.Element | None, name: str) -> ET.Element | None:
    return None if e is None else next((x for x in e if _name(x) == name), None)


def _text(e: ET.Element | None, name: str) -> str | None:
    x = None if e is None else next((x for x in e.iter() if _name(x) == name), None)
    return x.text if x is not None else None


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _element_int(e: ET.Element | None, name: str) -> int | None:
    """Read a BB3 integer where an empty element represents numeric zero."""
    node = _direct(e, name)
    if node is None:
        return None
    return 0 if node.text is None or not node.text.strip() else _int(node.text)


def _snake_case(value: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def _b64(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return value


def _message_xml(value: str | None) -> ET.Element | None:
    if not value:
        return None
    raw = value.encode("ascii")
    for _ in range(2):
        try:
            raw = base64.b64decode(raw, validate=True)
        except ValueError:
            return None
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def _data(e: ET.Element | None) -> Any:
    if e is None:
        return None
    if not list(e):
        return e.text or ""
    grouped: dict[str, list[Any]] = defaultdict(list)
    for child in e:
        grouped[_name(child)].append(_data(child))
    return {k: v[0] if len(v) == 1 else v for k, v in grouped.items()}


@dataclass(frozen=True, slots=True)
class TimelineParticipant:
    kind: str
    id: int | str
    name: str | None = None
    team_id: int | None = None


@dataclass(frozen=True, slots=True)
class TimelineEffect:
    type: str
    subject: TimelineParticipant | None
    outcome: str | int | bool | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    id: int
    type: str
    clock: int | None
    actor: TimelineParticipant | None = None
    target: TimelineParticipant | None = None
    outcome: str | int | bool | None = None
    effects: tuple[TimelineEffect, ...] = ()
    source_sequences: tuple[int, ...] = ()
    caused_by: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimelineTurn:
    number: int
    team_id: int | None
    half: int | None
    drive: int | None
    team_turn: int | None
    events: tuple[TimelineEvent, ...]


@dataclass(frozen=True, slots=True)
class ReplayTimeline:
    before_match: dict[str, Any]
    turns: tuple[TimelineTurn, ...]
    after_match: dict[str, Any]
    events: tuple[TimelineEvent, ...]
    unresolved: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_xml(cls, xml: bytes) -> "ReplayTimeline":
        root = ET.fromstring(xml)
        if _name(root) != "Replay":
            raise ValueError("Expected Replay XML")
        return _Parser(root).parse()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, filename: str | Path) -> Path:
        path = Path(filename)
        if path.suffix.lower() != ".json":
            raise ValueError("Replay timelines can only be saved as .json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _participant_ref(
        participant: TimelineParticipant | dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if participant is None:
            return None
        if isinstance(participant, TimelineParticipant):
            return {"kind": participant.kind, "id": participant.id}
        if "kind" in participant and "id" in participant:
            return {"kind": participant["kind"], "id": participant["id"]}
        return None

    @staticmethod
    def _dice(data: Any) -> list[int]:
        if not isinstance(data, dict):
            return []
        die = data.get("Die", data)
        items = die if isinstance(die, list) else [die]
        values: list[int] = []
        for item in items:
            value = item.get("Value") if isinstance(item, dict) else None
            parsed = _int(str(value)) if value is not None else None
            if parsed is not None:
                values.append(parsed)
        return values

    @classmethod
    def _roll_summary(cls, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        result: dict[str, Any] = {}
        for source, target in (
            ("Requirement", "required"), ("Difficulty", "difficulty"),
            ("RollType", "roll_type"), ("Outcome", "protocol_outcome"),
        ):
            if source in data:
                value = _int(str(data[source]))
                result[target] = value if value is not None else data[source]
        dice = cls._dice(data.get("Dice"))
        if dice:
            result["dice"] = dice
        return result

    @classmethod
    def _narrative_effect(cls, effect: TimelineEffect) -> dict[str, Any]:
        result: dict[str, Any] = {"type": effect.type}
        subject = cls._participant_ref(effect.subject)
        if subject is not None:
            result["subject"] = subject
        if effect.outcome is not None:
            result["outcome"] = effect.outcome
        details: dict[str, Any] = {}
        if effect.details:
            if "status_name" in effect.details:
                details["status_name"] = effect.details["status_name"]
            source = cls._participant_ref(effect.details.get("source"))
            if source is not None:
                details["source"] = source
        if details:
            result["details"] = details
        return result

    @staticmethod
    def _check_type(code: int | None) -> str:
        if code in RollType._value2member_map_:
            name = RollType(code).name.lower()
            return {"gfi": "rush", "armor": "armour"}.get(name, name)
        return f"roll_{code}" if code is not None else "unknown_roll"

    @staticmethod
    def _check_outcome(code: int | None, value: Any) -> str | int | None:
        raw = _int(str(value)) if value is not None else None
        if code == RollType.ARMOR:
            return "armour_broken" if raw else "armour_held"
        if code == RollType.INJURY and raw in InjuryOutcome._value2member_map_:
            return InjuryOutcome(raw).name.lower()
        if code == RollType.CASUALTY and raw in CasualtyOutcome._value2member_map_:
            return CasualtyOutcome(raw).name.lower()
        if code in {RollType.BLOCK, RollType.SCATTER, RollType.THROW_IN,
                    RollType.BOUNCE, RollType.DEVIATE, RollType.KICK_OFF_TABLE}:
            return raw
        if raw is None:
            return None
        return "passed" if raw != 0 else "failed"

    @classmethod
    def _check_attempt(cls, data: Any, *, reroll: str | None = None) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        attempt: dict[str, Any] = {}
        dice = cls._dice(data.get("Dice"))
        if dice:
            attempt["dice"] = dice
        code = _int(str(data.get("RollType"))) if data.get("RollType") is not None else None
        outcome = cls._check_outcome(code, data.get("Outcome"))
        if outcome is not None:
            attempt["outcome"] = outcome
        if reroll is not None:
            attempt["reroll"] = reroll
        return attempt

    @classmethod
    def _narrative_checks(cls, event: TimelineEvent) -> list[dict[str, Any]]:
        details = event.details if isinstance(event.details, dict) else {}
        messages = details.get("messages", [])
        if not isinstance(messages, list):
            return []
        effects_by_type: dict[str, TimelineEffect] = {}
        for effect in event.effects:
            effects_by_type[{"gfi": "rush", "armor_roll": "armour"}.get(
                effect.type, effect.type
            )] = effect
        checks: list[dict[str, Any]] = []
        pending: dict[str, Any] | None = None
        team_reroll_used: bool | None = None

        def new_check(data: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
            code = _int(str(data.get("RollType"))) if data.get("RollType") is not None else None
            kind = cls._check_type(code)
            check: dict[str, Any] = {"type": kind}
            effect = effects_by_type.get(kind)
            subject = cls._participant_ref(effect.subject if effect else event.actor)
            if subject is not None:
                check["subject"] = subject
            required = _int(str(data.get("Requirement"))) if data.get("Requirement") is not None else None
            if required is not None and required > 0:
                check["required"] = required
            check["attempts"] = [attempt]
            if attempt.get("outcome") is not None:
                check["outcome"] = attempt["outcome"]
            return check

        for message in messages:
            if not isinstance(message, dict):
                continue
            name, data = message.get("type"), message.get("data")
            if name == "QuestionTeamRerollUsage" and isinstance(data, dict):
                roll = data.get("RollInfos")
                if isinstance(roll, dict):
                    attempt = cls._check_attempt(roll)
                    check = new_check(roll, attempt)
                    check["reroll_offered"] = ["team"]
                    checks.append(check)
                    pending = {"check": check, "roll": roll, "attempt": attempt}
                    team_reroll_used = None
                continue
            if name == "ResultTeamRerollUsage" and pending is not None:
                used = isinstance(data, dict) and str(data.get("Used")) == "1"
                pending["check"]["reroll_used"] = used
                team_reroll_used = used
                continue
            if name != "ResultRoll" or not isinstance(data, dict):
                continue
            code = _int(str(data.get("RollType"))) if data.get("RollType") is not None else None
            # Positional/displacement rolls already have clearer event-specific
            # representations and are not pass/fail checks.
            if code in {RollType.SCATTER, RollType.THROW_IN, RollType.BOUNCE,
                        RollType.DEVIATE, RollType.KICK_OFF_TABLE}:
                continue
            if pending is not None:
                pending_code = _int(str(pending["roll"].get("RollType")))
                if code == pending_code:
                    attempt = cls._check_attempt(
                        data, reroll="team" if team_reroll_used else None
                    )
                    prior = pending["attempt"]
                    same = ({k: v for k, v in attempt.items() if k != "reroll"} == prior)
                    if team_reroll_used or not same:
                        pending["check"]["attempts"].append(attempt)
                    pending["check"]["outcome"] = attempt.get("outcome")
                    pending = None
                    team_reroll_used = None
                    continue
            attempt = cls._check_attempt(data)
            checks.append(new_check(data, attempt))
        return checks

    @classmethod
    def _narrative_details(cls, details: Any) -> dict[str, Any]:
        if not isinstance(details, dict):
            return {}
        result: dict[str, Any] = {}
        if details.get("declared_action") is not None:
            result["declared_action"] = details["declared_action"]
        action_target = cls._participant_ref(details.get("action_target"))
        if action_target is not None:
            result["action_target"] = action_target
        eligible = [cls._participant_ref(item)
                    for item in details.get("eligible_targets", [])]
        eligible = [item for item in eligible if item is not None]
        if eligible:
            result["eligible_targets"] = eligible
        for key in ("from", "to"):
            if details.get(key) not in (None, "", {}):
                result[key] = details[key]
        for key in ("roll", "check"):
            summary = cls._roll_summary(details.get(key))
            if summary:
                result[key] = summary
        return result

    @staticmethod
    def _match_result(after_match: dict[str, Any]) -> dict[str, Any]:
        finished = after_match.get("RulesEventGameFinished", after_match)
        match = finished.get("MatchResult", finished) if isinstance(finished, dict) else {}
        gamer_results = match.get("GamerResults", {}) if isinstance(match, dict) else {}
        gamers = gamer_results.get("GamerResult", []) if isinstance(gamer_results, dict) else []
        if isinstance(gamers, dict):
            gamers = [gamers]
        teams: list[dict[str, Any]] = []
        for team_id, gamer in enumerate(gamers if isinstance(gamers, list) else []):
            team_result = gamer.get("TeamResult", {}) if isinstance(gamer, dict) else {}
            # BB3 omits both the value and sometimes the complete Score element
            # for zero, while a GamerResult still identifies the team result.
            raw_score = team_result.get("Score")
            score = 0 if raw_score in (None, "") else _int(str(raw_score))
            result: dict[str, Any] = {"team_id": team_id}
            if score is not None:
                result["score"] = score
            teams.append(result)
        summary: dict[str, Any] = {"teams": teams}
        scored = [x.get("score") for x in teams]
        if len(scored) == 2 and all(isinstance(x, int) for x in scored):
            summary["score"] = scored
            summary["winner_team_id"] = (
                None if scored[0] == scored[1] else (0 if scored[0] > scored[1] else 1)
            )
        return summary

    def to_narrative_dict(
        self, *, include_moves: bool = False, include_evidence: bool = False,
    ) -> dict[str, Any]:
        """Return a compact, non-duplicated projection for narrative generation."""
        context: dict[int, dict[str, Any]] = {}
        for turn in self.turns:
            values = {
                "turn": turn.number, "team_id": turn.team_id, "half": turn.half,
                "drive": turn.drive, "team_turn": turn.team_turn,
            }
            for event in turn.events:
                context[event.id] = {k: v for k, v in values.items() if v is not None}

        events: list[dict[str, Any]] = []
        for event in self.events:
            if event.type == "move" and not include_moves:
                if event.outcome != "failed" and not event.effects:
                    continue
            if event.type in {"face_up_stunned_players", "new_game_phase"}:
                continue
            if event.type == "stand_up" and not event.effects:
                continue
            if event.type == "turn_end" and event.outcome != "turnover":
                continue
            if event.type == "roll" and not include_evidence:
                continue
            item: dict[str, Any] = {"id": event.id, "type": event.type}
            item.update(context.get(event.id, {}))
            if event.clock is not None:
                item["clock"] = event.clock
            for key, participant in (("actor", event.actor), ("target", event.target)):
                reference = self._participant_ref(participant)
                if reference is not None:
                    item[key] = reference
            if event.outcome is not None:
                item["outcome"] = event.outcome
            checks = self._narrative_checks(event)
            if checks:
                item["checks"] = checks
            check_types = {check["type"] for check in checks}
            effect_aliases = {"gfi": "rush", "armor_roll": "armour"}
            effects = [
                effect for effect in event.effects
                if effect_aliases.get(effect.type, effect.type) not in check_types
            ]
            if effects:
                item["effects"] = [self._narrative_effect(x) for x in effects]
            if event.caused_by is not None:
                item["caused_by"] = event.caused_by
            details = self._narrative_details(event.details)
            if (include_evidence and isinstance(event.details, dict)
                    and event.details.get("messages")):
                details["messages"] = event.details["messages"]
            if details:
                item["details"] = details
            events.append(item)

        ignored_before = {
            "setup_move_pitch_player", "legal_kickers", "set_up_configuration",
            "inducements_data",
        }
        pre_match = [event for event in self.before_match.get("events", [])
                     if event.get("type") not in ignored_before]
        return {
            "format": "pybb3-narrative-timeline",
            "version": 1,
            "match": {
                "date": self.before_match.get("date"),
                "teams": [
                    {k: value for k, value in {
                        "id": team.get("id"), "name": team.get("name"),
                    }.items() if value is not None}
                    for team in self.before_match.get("teams", [])
                ],
                "players": [
                    {k: value for k, value in {
                        "id": player.get("id"), "name": player.get("name"),
                        "team_id": player.get("team_id"),
                    }.items() if value is not None}
                    for player in self.before_match.get("players", [])
                ],
                "pre_match_events": pre_match,
                "result": self._match_result(self.after_match),
            },
            "events": events,
            "unresolved": self.unresolved,
        }

    def to_narrative_json(
        self, *, indent: int | None = None, include_moves: bool = False,
        include_evidence: bool = False,
    ) -> str:
        return json.dumps(
            self.to_narrative_dict(
                include_moves=include_moves, include_evidence=include_evidence
            ),
            ensure_ascii=False, indent=indent,
        )

    def save_narrative(
        self, filename: str | Path, *, indent: int | None = None,
        include_moves: bool = False, include_evidence: bool = False,
    ) -> Path:
        path = Path(filename)
        if path.suffix.lower() != ".json":
            raise ValueError("Replay narratives can only be saved as .json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_narrative_json(
            indent=indent, include_moves=include_moves,
            include_evidence=include_evidence,
        ) + "\n", encoding="utf-8")
        return path


@dataclass(slots=True)
class _Message:
    name: str
    node: ET.Element
    sequence: int
    clock: int | None


class _Parser:
    def __init__(self, root: ET.Element) -> None:
        self.root = root
        self.players: dict[int, TimelineParticipant] = {}
        self.teams: dict[int, TimelineParticipant] = {}
        self.event_id = 0
        self.active_player_id: int | None = None
        self.active_team_id: int | None = None
        self.ball_carrier_id: int | None = None
        self.cause_event_id: int | None = None
        self.special_card: str | None = None
        self.unresolved: defaultdict[str, int] = defaultdict(int)
        self.before_events: list[dict[str, Any]] = []
        self._participants()

    def _participants(self) -> None:
        rosters = _direct(self.root, "Rosters")
        if rosters is None:
            return
        joined: dict[int, ET.Element] = {}
        info = _direct(self.root, "NotificationGameJoined")
        if info is not None:
            for gamer in (x for x in info.iter() if _name(x) == "GamerInfos"):
                slot, roster = _int(_text(gamer, "Slot")), _direct(gamer, "Roster")
                if slot is not None and roster is not None:
                    joined[slot] = roster
        for fallback, roster in enumerate(rosters):
            team_id = _int(_text(_direct(roster, "Team"), "TeamId"))
            team_id = fallback if team_id is None else team_id
            name_node = _direct(roster, "Name")
            encoded = name_node.text if name_node is not None else None
            if not encoded and team_id in joined:
                name_node = _direct(joined[team_id], "Name")
                encoded = name_node.text if name_node is not None else None
            self.teams[team_id] = TimelineParticipant("team", team_id, _b64(encoded), team_id)
            players = _direct(roster, "Players")
            for player in (() if players is None else players):
                player_id = _int(_text(player, "Id"))
                if player_id is not None:
                    self.players[player_id] = TimelineParticipant(
                        "player", player_id, _b64(_text(player, "Name")), team_id
                    )
        # EndGame also contains journeymen and other players missing from Rosters.
        end = _direct(self.root, "EndGame")
        if end is not None:
            for result in (x for x in end.iter() if _name(x) == "GamerResult"):
                team_result = _direct(result, "TeamResult")
                team_id = _int(_text(_direct(team_result, "TeamData"), "TeamId"))
                if team_id is None:
                    team_id = _int(_text(team_result, "IdTeam"))
                for player in (x for x in result.iter() if _name(x) == "PlayerData"):
                    player_id = _int(_text(player, "Id"))
                    if player_id is not None and player_id not in self.players:
                        self.players[player_id] = TimelineParticipant(
                            "player", player_id, _b64(_text(player, "Name")), team_id
                        )

    def _who(self, identifier: int | None, team: bool = False) -> TimelineParticipant | None:
        if identifier is None or identifier < 0:
            return None
        known = self.teams if team else self.players
        return known.get(identifier, TimelineParticipant("team" if team else "player", identifier))

    def _event(self, kind: str, clock: int | None, **values: Any) -> TimelineEvent:
        self.event_id += 1
        values.setdefault("caused_by", self.cause_event_id)
        return TimelineEvent(self.event_id, kind, clock, **values)

    @staticmethod
    def _find(messages: list[_Message], name: str) -> list[_Message]:
        return [x for x in messages if x.name == name]

    @staticmethod
    def _evidence(messages: list[_Message]) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "messages": [{"type": x.name, "data": _data(x.node)} for x in messages]
        }
        action = next((x for x in messages if x.name == "ResultUseAction"), None)
        if action is not None:
            code = _int(_text(action.node, "Action"))
            evidence["declared_action"] = (
                SequenceType(code).name.lower()
                if code in SequenceType._value2member_map_ else code
            )
        return evidence

    def _damage_effects(
        self, messages: list[_Message], subject: TimelineParticipant | None
    ) -> list[TimelineEffect]:
        effects: list[TimelineEffect] = []
        for injury in self._find(messages, "ResultInjuryRoll"):
            code = _int(_text(injury.node, "Outcome"))
            outcome = InjuryOutcome(code).name.lower() if code in InjuryOutcome._value2member_map_ else code
            effects.append(TimelineEffect("injury", subject, outcome, _data(injury.node)))
        for removal in self._find(messages, "ResultPlayerRemoval"):
            removed = self._who(_int(_text(removal.node, "PlayerId"))) or subject
            situation, status = _int(_text(removal.node, "Situation")), _int(_text(removal.node, "Status"))
            effects.append(TimelineEffect("player_removed", removed,
                PlayerSituation(situation).name.lower() if situation in PlayerSituation._value2member_map_ else situation,
                {**(_data(removal.node) or {}), "status_name": PlayerStatus(status).name.lower() if status in PlayerStatus._value2member_map_ else status}))
        for casualty in self._find(messages, "ResultCasualtyRoll"):
            code = _int(_text(casualty.node, "Outcome"))
            outcome = CasualtyOutcome(code).name.lower() if code in CasualtyOutcome._value2member_map_ else code
            effects.append(TimelineEffect("casualty", subject, outcome, _data(casualty.node)))
        for apothecary in self._find(messages, "ResultApothecary"):
            code = _int(_text(apothecary.node, "Casualty"))
            outcome = CasualtyOutcome(code).name.lower() if code in CasualtyOutcome._value2member_map_ else code
            effects.append(TimelineEffect("apothecary", subject, outcome, _data(apothecary.node)))
        for sent_off in self._find(messages, "ResultPlayerSentOff"):
            expelled = self._who(_int(_text(sent_off.node, "PlayerId"))) or subject
            effects.append(TimelineEffect("sent_off", expelled, "expelled", _data(sent_off.node)))
        for raised in self._find(messages, "ResultRaisedDead"):
            effects.append(TimelineEffect("raised_dead",
                self._who(_int(_text(raised.node, "RaisedPlayerId"))), details=_data(raised.node)))
        return effects

    def _roll_effects(self, messages: list[_Message], subject: TimelineParticipant | None) -> list[TimelineEffect]:
        effects: list[TimelineEffect] = []
        for message in self._find(messages, "ResultRoll"):
            code = _int(_text(message.node, "RollType"))
            if code in {RollType.ARMOR, RollType.INJURY, RollType.CASUALTY}:
                continue
            name = RollType(code).name.lower() if code in RollType._value2member_map_ else f"roll_{code}"
            effects.append(TimelineEffect(name, subject, _text(message.node, "Outcome") != "0", _data(message.node)))
        return effects

    def _roll_details(self, message: _Message) -> dict[str, Any]:
        data = _data(message.node)
        return data if isinstance(data, dict) else {"value": data}

    def _animal_savagery_event(
        self, messages: list[_Message], actor: TimelineParticipant | None,
        action_target: TimelineParticipant | None, clock: int | None,
        sequences: tuple[int, ...], evidence: dict[str, Any],
    ) -> TimelineEvent | None:
        roll = next((x for x in self._find(messages, "ResultRoll")
                     if _int(_text(x.node, "RollType")) == RollType.ANIMAL_SAVAGERY), None)
        if roll is None:
            return None
        result = self._find(messages, "ResultAnimalSavagery")
        question = next(iter(self._find(messages, "QuestionAnimalSavagery")), None)
        victim_id = _int(_text(result[-1].node, "VictimId")) if result else None
        victim = self._who(victim_id)
        passed = _text(roll.node, "Outcome") != "0"
        outcome = "passed" if passed else ("teammate_hit" if victim else "activation_lost")
        effects: list[TimelineEffect] = []
        if victim is not None:
            effects.append(TimelineEffect("knockdown", victim))
            armour = next((x for x in reversed(self._find(messages, "ResultRoll"))
                           if _int(_text(x.node, "RollType")) == RollType.ARMOR), None)
            if armour is not None:
                effects.append(TimelineEffect(
                    "armour_roll", victim, _text(armour.node, "Outcome") == "1",
                    self._roll_details(armour)
                ))
            effects.extend(self._damage_effects(messages, victim))
        eligible: list[TimelineParticipant] = []
        if question is not None:
            victims = next((x for x in question.node.iter()
                            if _name(x) == "VictimsIds"), None)
            if victims is not None:
                eligible = [participant for child in victims
                            if (participant := self._who(_int(child.text))) is not None]
        evidence.update({
            "check": self._roll_details(roll),
            "action_target": asdict(action_target) if action_target else None,
            "eligible_targets": [asdict(x) for x in eligible],
        })
        return self._event(
            "animal_savagery", clock, actor=actor, target=victim,
            outcome=outcome, effects=tuple(effects), source_sequences=sequences,
            details=evidence,
        )

    def _reduce(self, messages: list[_Message]) -> list[TimelineEvent]:
        if not messages:
            return []
        steps = self._find(messages, "PlayerStep")
        ball_steps = self._find(messages, "BallStep")
        actor = self._who(_int(_text(steps[-1].node, "PlayerId"))) if steps else self._who(self.active_player_id)
        target = self._who(_int(_text(steps[-1].node, "TargetId"))) if steps else None
        sequences = tuple(dict.fromkeys(x.sequence for x in messages))
        clock, evidence = messages[-1].clock, self._evidence(messages)
        blocks = self._find(messages, "ResultBlockOutcome")
        if len(blocks) > 1:
            results: list[TimelineEvent] = []
            positions = [messages.index(block) for block in blocks]
            starts: list[int] = []
            previous = 0
            for position in positions:
                player_steps = [i for i in range(previous, position + 1)
                                if messages[i].name == "PlayerStep"]
                starts.append(player_steps[-1] if player_steps else previous)
                previous = position + 1
            for index, position in enumerate(positions):
                start = starts[index]
                end = starts[index + 1] if index + 1 < len(starts) else len(messages)
                # Keep the roll/push before this outcome and damage/removal after
                # it. This also preserves every Multiple Block consequence.
                results.extend(self._reduce(messages[start:end]))
            return results
        if blocks:
            block = blocks[-1].node
            actor = self._who(_int(_text(block, "AttackerId"))) or actor
            target = self._who(_int(_text(block, "DefenderId"))) or target
            code = _int(_text(block, "Outcome"))
            effects: list[TimelineEffect] = []
            pushes = self._find(messages, "ResultPushBack")
            if pushes:
                push = pushes[-1].node
                effects.append(TimelineEffect("push", self._who(_int(_text(push, "PushedPlayerId"))) or target,
                                              details=_data(push)))
            outcome = BlockOutcome(code).name.lower() if code in BlockOutcome._value2member_map_ else str(code)
            if code == BlockOutcome.ATTACKER_DOWN:
                effects.append(TimelineEffect("knockdown", actor))
            elif code == BlockOutcome.BOTH_DOWN:
                effects += [TimelineEffect("knockdown", actor), TimelineEffect("knockdown", target)]
            elif code == BlockOutcome.BOTH_WRESTLE_DOWN:
                effects += [TimelineEffect("wrestle_down", actor), TimelineEffect("wrestle_down", target)]
            elif code in {BlockOutcome.DEFENDER_DOWN, BlockOutcome.DEFENDER_PUSHED_DOWN}:
                effects.append(TimelineEffect("knockdown", target))
            armour = [x for x in self._find(messages, "ResultRoll") if _text(x.node, "RollType") == "10"]
            if armour:
                roll = armour[-1].node
                effects.append(TimelineEffect("armour_roll", target, _text(roll, "Outcome") == "1", _data(roll)))
            effects.extend(self._damage_effects(messages, target))
            return [self._event("block", clock, actor=actor, target=target,
                outcome=outcome, effects=tuple(effects),
                source_sequences=sequences, details=evidence)]
        step_code = _int(_text(steps[-1].node, "StepType")) if steps else None
        action_types = {
            StepType.PASS: "pass", StepType.CATCH: "catch", StepType.HANDOFF: "handoff",
            StepType.FOUL: "foul", StepType.CHAINSAW_FOUL: "foul",
            StepType.INTERCEPTION: "interception", StepType.THROW_TEAM_MATE: "throw_team_mate",
        }
        if step_code in action_types:
            rolls = self._find(messages, "ResultRoll")
            relevant = next((x for x in reversed(rolls) if _int(_text(x.node, "RollType")) in {
                RollType.PASS, RollType.CATCH, RollType.INTERCEPTION}), None)
            success = None if relevant is None else _text(relevant.node, "Outcome") != "0"
            effects = self._roll_effects(messages, actor) + self._damage_effects(messages, target)
            return [self._event(action_types[StepType(step_code)], clock, actor=actor, target=target,
                outcome=success, effects=tuple(effects), source_sequences=sequences, details=evidence)]
        moves = self._find(messages, "ResultMoveOutcome")
        if steps and moves:
            effects = self._roll_effects(messages, actor) + self._damage_effects(messages, actor)
            # An injury following the movement belongs to the moving player
            # (typically a failed dodge/rush). ``Moved`` is not a success flag.
            failed = any(effect.type == "injury" for effect in effects)
            evidence.update({"from": _data(_direct(steps[0].node, "CellFrom")),
                             "to": _data(_direct(steps[-1].node, "CellTo"))})
            if target is not None:
                evidence["action_target"] = asdict(target)
            return [self._event("move", clock, actor=actor,
                outcome="failed" if failed else "completed", effects=tuple(effects),
                source_sequences=sequences, details=evidence)]
        animal_savagery = self._animal_savagery_event(
            messages, actor, target, clock, sequences, evidence
        )
        if animal_savagery is not None:
            # If the declared action also completes in this same reduced
            # sequence (for example standing up), keep that as the primary
            # event and attach Animal Savagery as its check.
            if step_code in StepType._value2member_map_ and step_code != StepType.ACTIVATION:
                check = TimelineEffect(
                    "animal_savagery", actor, animal_savagery.outcome,
                    animal_savagery.details.get("check", {})
                )
                return [self._event(
                    StepType(step_code).name.lower(), clock, actor=actor, target=target,
                    effects=(check, *animal_savagery.effects),
                    source_sequences=sequences, details=evidence,
                )]
            return [animal_savagery]
        foul_appearance = next((x for x in self._find(messages, "ResultRoll")
                                if _int(_text(x.node, "RollType")) == RollType.FOUL_APPEARANCE), None)
        if foul_appearance is not None:
            passed = _text(foul_appearance.node, "Outcome") != "0"
            effect_details = self._roll_details(foul_appearance)
            if target is not None:
                effect_details["source"] = asdict(target)
            effect = TimelineEffect(
                "foul_appearance", actor, "passed" if passed else "failed", effect_details
            )
            action = evidence.get("declared_action") or "action"
            return [self._event(
                action, clock, actor=actor, target=target,
                outcome="allowed" if passed else "prevented", effects=(effect,),
                source_sequences=sequences, details=evidence,
            )]
        deviation = next((x for x in self._find(messages, "ResultRoll")
                          if _int(_text(x.node, "RollType")) == RollType.DEVIATE), None)
        if deviation is not None and step_code == StepType.KICKOFF:
            if steps:
                evidence.update({
                    "from": _data(_direct(steps[0].node, "CellFrom")),
                    "to": _data(_direct(steps[-1].node, "CellTo")),
                    "roll": self._roll_details(deviation),
                })
            return [self._event(
                "kickoff_deviation", clock, actor=self._who(self.active_team_id, True),
                source_sequences=sequences, details=evidence,
            )]
        if ball_steps:
            rolls = self._roll_effects(messages, actor)
            roll_names = [effect.type for effect in rolls]
            kind = next((name for name in ("pick_up", "catch", "pass", "interception",
                                           "bounce", "scatter", "throw_in") if name in roll_names),
                        "ball_action")
            return [self._event(kind, clock, actor=self._who(self.active_player_id),
                effects=tuple(rolls), source_sequences=sequences, details=evidence)]
        if step_code in StepType._value2member_map_ and step_code not in {
            StepType.ACTIVATION, StepType.DAMAGE, StepType.BALL, StepType.BLOCK, StepType.KICKOFF
        }:
            kind = StepType(step_code).name.lower()
            effects = self._roll_effects(messages, actor) + self._damage_effects(messages, target or actor)
            return [self._event(kind, clock, actor=actor, target=target, effects=tuple(effects),
                source_sequences=sequences, details=evidence)]
        damage = self._damage_effects(messages, target)
        if damage:
            subject = next((effect.subject for effect in damage if effect.subject), target)
            return [self._event("damage", clock, actor=self._who(self.active_player_id), target=subject,
                effects=tuple(damage), source_sequences=sequences, details=evidence)]
        unknown: list[_Message] = []
        for message in messages:
            if not message.name.startswith("Question") and message.name not in {
                "PlayerStep", "BallStep", "ResultUseAction", "ResultDoMove",
                "ResultMoveOutcome", "ResultNoRollSuccess", "ResultSkillUsage",
                "ResultTeamRerollUsage", "ResultFollowUp", "ResultPushBack",
            }:
                self.unresolved[message.name] += 1
                unknown.append(message)
        if unknown:
            return [self._event("unclassified", clock, actor=self._who(self.active_player_id),
                source_sequences=sequences, details=self._evidence(messages))]
        return []

    def _outer(self, node: ET.Element, clock: int | None) -> TimelineEvent | None:
        kind = _name(node).removeprefix("Event")
        if kind == "UseSpecialCard":
            code = _int(_text(node, "CardId"))
            card = SpecialCard(code).name.lower() if code in SpecialCard._value2member_map_ else f"card_{code}"
            team_id = _int(_text(node, "GamerId"))
            event = self._event("special_card", clock, actor=self._who(team_id, True), outcome=card,
                                caused_by=None, details=_data(node))
            self.cause_event_id = event.id
            self.special_card = card
            self.active_player_id = None
            return event
        if kind == "Concession":
            return self._event("concession", clock,
                actor=self._who(_int(_text(node, "GamerId")), True), details=_data(node))
        if kind == "EndTurn":
            turnover = _text(node, "Reason") == "2"
            event = self._event("turn_end", clock, actor=self._who(self.active_player_id),
                outcome="turnover" if turnover else "completed", details=_data(node))
            self.cause_event_id = None
            self.special_card = None
            self.active_player_id = None
            return event
        if kind in {"KickOffTable", "WeatherRoll", "BrilliantCoaching"}:
            return self._event(_snake_case(kind), clock, details=_data(node))
        if "Touchdown" in kind:
            return self._event("touchdown", clock,
                actor=self._who(_int(_text(node, "PlayerId"))), details=_data(node))
        contextual = {"MatchStart", "MatchEnd", "NewGamePhase", "Blitz", "CheeringFans",
                      "OfficiousRef", "FaceUpStunnedPlayers", "AddInducement", "Roll"}
        if kind in contextual:
            return self._event(_snake_case(kind), clock, actor=self._who(self.active_player_id),
                               details=_data(node))
        ignored = {"RulesEngineStandBy", "ActiveTimerChanged", "StartActiveTimer",
                   "PauseActiveTimer", "ActiveGamerChanged", "GamersAreReady"}
        before_match = {"EndInducements", "FanFactor", "InducementsData", "JourneyMen",
                        "KickingChoice", "LegalKickers", "NewInducementsTurn",
                        "QuestionKickingChoice", "SetupMovePitchPlayer", "SetUpConfiguration",
                        "AddInducement"}
        if kind in before_match:
            self.before_events.append({"type": _snake_case(kind), "clock": clock,
                                       "details": _data(node)})
            return None
        if kind not in ignored:
            self.unresolved[f"Event{kind}"] += 1
        return None

    def _possession_event(self, board: ET.Element | None, clock: int | None) -> TimelineEvent | None:
        ball = None if board is None else next((x for x in board.iter() if _name(x) == "Ball"), None)
        if ball is None:
            return None
        carrier = _int(_text(ball, "Carrier")) if _text(ball, "IsHeld") == "1" else None
        previous = self.ball_carrier_id
        if carrier == previous:
            return None
        self.ball_carrier_id = carrier
        if carrier is None and previous is not None:
            return self._event("ball_loose", clock, actor=self._who(self.active_player_id),
                               target=self._who(previous))
        if carrier is not None and previous is None:
            return self._event("possession_gained", clock, actor=self._who(carrier))
        if carrier is not None:
            return self._event("possession_changed", clock, actor=self._who(carrier),
                               target=self._who(previous))
        return None

    def parse(self) -> ReplayTimeline:
        before = {"date": _text(self.root, "Date"), "teams": [asdict(x) for x in self.teams.values()],
                  "players": [asdict(x) for x in self.players.values()], "events": self.before_events}
        end = _direct(self.root, "EndGame")
        after = _data(end) if end is not None else {}
        events: list[TimelineEvent] = []
        turns: list[TimelineTurn] = []
        current: list[TimelineEvent] = []
        pending: list[_Message] = []
        signature: tuple[Any, ...] | None = None
        active_team: int | None = None
        game_phase: int | None = None
        drive = 0
        sequence = 0

        def flush() -> None:
            nonlocal pending
            reduced = self._reduce(pending)
            events.extend(reduced)
            current.extend(reduced)
            pending = []

        def team_turn(board: ET.Element | None, team_id: int | None) -> int | None:
            teams = _direct(board, "ListTeams")
            states = [] if teams is None else [x for x in teams if _name(x) == "TeamState"]
            if team_id is None or not 0 <= team_id < len(states):
                return None
            return _element_int(states[team_id], "GameTurn")

        for step in (x for x in self.root if _name(x) == "ReplayStep"):
            clock_node = _direct(step, "Clock")
            clock = _int(clock_node.text) if clock_node is not None else None
            board = _direct(step, "BoardState")
            for outer in step:
                if _name(outer) == "EventExecuteSequence":
                    sequence += 1
                    decoded: list[_Message] = []
                    for container in (x for x in outer.iter() if _name(x) in {"Step", "StringMessage"}):
                        node = _message_xml(_text(container, "MessageData"))
                        if node is not None:
                            decoded.append(_Message(_b64(_text(container, "Name")) or "Unknown", node, sequence, clock))
                    player_step = next((x for x in reversed(decoded) if x.name == "PlayerStep"), None)
                    new_sig = None if player_step is None else (
                        _int(_text(player_step.node, "PlayerId")), _int(_text(player_step.node, "TargetId")),
                        _text(player_step.node, "StepType"))
                    if pending and new_sig is not None and signature is not None and new_sig != signature:
                        flush()
                    pending.extend(decoded)
                    if new_sig is not None:
                        signature = new_sig
                        if new_sig[2] == str(StepType.ACTIVATION.value):
                            self.active_player_id = new_sig[0]
                            self.cause_event_id = None
                            self.special_card = None
                elif _name(outer).startswith("Event"):
                    if _name(outer) == "EventNewGamePhase":
                        game_phase = _element_int(outer, "Phase")
                        if game_phase == 3:
                            drive += 1
                    # NewActiveGamer is the authoritative current playing team.
                    # BB3 omits the text for numeric zero, so the element's
                    # presence must be distinguished from its absence.
                    if _name(outer) == "EventActiveGamerChanged":
                        changed_team = _element_int(outer, "NewActiveGamer")
                        if changed_team is None and game_phase == 5:
                            changed_team = 0
                        if changed_team is not None:
                            active_team = changed_team
                            self.active_team_id = changed_team
                    semantic = self._outer(outer, clock)
                    if semantic:
                        flush()
                        events.append(semantic)
                        current.append(semantic)
                        if semantic.type == "turn_end":
                            finishing_type = _text(outer, "FinishingTurnType")
                            if finishing_type not in {"5", "6"}:
                                turn = team_turn(board, active_team)
                                half = None if turn is None else (turn - 1) // 8 + 1
                                within_half = None if turn is None else (turn - 1) % 8 + 1
                                turns.append(TimelineTurn(
                                    len(turns) + 1, active_team, half, drive,
                                    within_half, tuple(current)
                                ))
                            current, signature = [], None
            possession = self._possession_event(board, clock)
            if possession is not None:
                events.append(possession)
                current.append(possession)
        flush()
        if current and game_phase != 6:
            turn = team_turn(board, active_team)
            half = None if turn is None else (turn - 1) // 8 + 1
            within_half = None if turn is None else (turn - 1) % 8 + 1
            turns.append(TimelineTurn(
                len(turns) + 1, active_team, half, drive, within_half, tuple(current)
            ))
        return ReplayTimeline(before, tuple(turns), after if isinstance(after, dict) else {},
                              tuple(events), dict(sorted(self.unresolved.items())))
