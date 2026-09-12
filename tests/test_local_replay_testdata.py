from __future__ import annotations

import json
from pathlib import Path

import pytest

from bb3.replay import Replay


TESTDATA_DIR = Path(__file__).resolve().parents[1] / "testdata"
BBR_FILES = sorted(TESTDATA_DIR.glob("*.bbr"))

pytestmark = [
    pytest.mark.testdata,
    pytest.mark.skipif(
        not BBR_FILES,
        reason="no local testdata/*.bbr files; testdata is intentionally not committed",
    ),
]

ACTIVE_TURN_ACTIONS = {
    "move",
    "block",
    "pass",
    "handoff",
    "foul",
    "throw_team_mate",
    "stand_up",
    "negatrait_check",
}


@pytest.fixture(params=BBR_FILES, ids=lambda path: path.name)
def local_replay(request):
    path = request.param
    replay = Replay.from_bbr(path.read_bytes())
    return path, replay


@pytest.fixture
def local_timeline(local_replay):
    path, replay = local_replay
    return path, replay.timeline()


def test_local_replay_decodes_and_builds_timeline(local_timeline):
    path, timeline = local_timeline

    assert timeline.events, f"{path.name}: timeline contains no events"
    assert timeline.turns, f"{path.name}: timeline contains no playable turns"

    # Exercise the compact consumer format too. This catches projection/grouping
    # failures without requiring a live BB3 login.
    narrative = json.loads(
        timeline.to_narrative_json(include_moves=True, include_evidence=False)
    )
    assert narrative["format"] == "pybb3-narrative-timeline"
    assert isinstance(narrative["events"], list)


def test_local_timeline_event_ids_and_causal_links_are_consistent(local_timeline):
    path, timeline = local_timeline
    event_ids = [event.id for event in timeline.events]

    assert len(event_ids) == len(set(event_ids)), f"{path.name}: duplicate event IDs"

    known_ids = set(event_ids)
    dangling = [
        (event.id, event.caused_by)
        for event in timeline.events
        if event.caused_by is not None and event.caused_by not in known_ids
    ]
    assert not dangling, f"{path.name}: dangling caused_by references: {dangling}"


def test_local_turn_events_are_canonical_and_not_duplicated(local_timeline):
    path, timeline = local_timeline
    canonical = {event.id: event for event in timeline.events}
    assigned: dict[int, int] = {}
    errors = []

    for turn in timeline.turns:
        for event in turn.events:
            if event.id not in canonical:
                errors.append(
                    f"turn {turn.number}: event {event.id} missing from canonical events"
                )
            previous_turn = assigned.setdefault(event.id, turn.number)
            if previous_turn != turn.number:
                errors.append(
                    f"event {event.id} assigned to turns {previous_turn} and {turn.number}"
                )

    assert not errors, f"{path.name}:\n" + "\n".join(errors)


def test_local_active_actions_belong_to_turn_team(local_timeline):
    path, timeline = local_timeline
    errors = []

    for turn in timeline.turns:
        for event in turn.events:
            if event.type not in ACTIVE_TURN_ACTIONS:
                continue
            actor = event.actor
            if actor is None or actor.kind != "player" or actor.team_id is None:
                continue
            if actor.team_id != turn.team_id:
                errors.append(
                    f"turn={turn.number} half={turn.half} team_turn={turn.team_turn} "
                    f"event={event.id} type={event.type} actor={actor.id} "
                    f"actor_team={actor.team_id} turn_team={turn.team_id}"
                )

    assert not errors, f"{path.name}: active actions assigned to wrong team:\n" + "\n".join(errors)
