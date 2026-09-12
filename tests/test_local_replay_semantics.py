from __future__ import annotations

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

MOVEMENT_CHECKS = {"dodge", "rush"}
ACTOR_CHECKS = {"dodge", "rush", "pick_up"}
KNOWN_UNRESOLVED = {
    "DamageStep",
    "EventBuyMercenary",
    "EventQuickSnap",
    "EventQuickSnapMove",
    "EventSetupSubstitutePlayers",
    "EventSwelteringHeat",
    "ResultBombExplosion",
    "ResultRoll",
}


@pytest.fixture(params=BBR_FILES, ids=lambda path: path.name)
def replay_timeline(request):
    path = request.param
    timeline = Replay.from_bbr(path.read_bytes()).timeline()
    narrative = timeline.to_narrative_dict(
        include_moves=True, include_evidence=False
    )
    return path, timeline, narrative


def _event_context(timeline):
    context = {}
    for turn in timeline.turns:
        for event in turn.events:
            context[event.id] = (
                turn.number,
                turn.team_id,
                turn.half,
                turn.drive,
                turn.team_turn,
            )
    return context


def test_local_rerolls_are_consistent(replay_timeline):
    path, _timeline, narrative = replay_timeline
    errors = []

    for event in narrative["events"]:
        for check in event.get("checks", []):
            attempts = check.get("attempts", [])
            reroll_attempts = [
                attempt for attempt in attempts if attempt.get("reroll")
            ]

            if check.get("reroll_used"):
                if len(attempts) < 2:
                    errors.append(
                        f"event={event['id']} check={check.get('type')}: "
                        "reroll_used but fewer than two attempts"
                    )
                if not reroll_attempts:
                    errors.append(
                        f"event={event['id']} check={check.get('type')}: "
                        "reroll_used but no attempt identifies reroll source"
                    )

            if "team" in check.get("reroll_offered", []) and check.get("reroll_used"):
                if not any(
                    attempt.get("reroll") == "team" for attempt in attempts
                ):
                    errors.append(
                        f"event={event['id']} check={check.get('type')}: "
                        "team reroll used without reroll='team' attempt"
                    )

            if attempts and check.get("outcome") is not None:
                final_outcome = attempts[-1].get("outcome")
                if final_outcome is not None and check["outcome"] != final_outcome:
                    errors.append(
                        f"event={event['id']} check={check.get('type')}: "
                        f"check outcome={check['outcome']} "
                        f"but final attempt={final_outcome}"
                    )

    assert not errors, f"{path.name}: inconsistent rerolls:\n" + "\n".join(errors)


def test_local_actor_checks_belong_to_action_actor(replay_timeline):
    path, _timeline, narrative = replay_timeline
    errors = []

    for event in narrative["events"]:
        actor = event.get("actor")
        if not isinstance(actor, dict) or actor.get("kind") != "player":
            continue
        actor_id = actor.get("id")

        for check in event.get("checks", []):
            if check.get("type") not in ACTOR_CHECKS:
                continue
            subject = check.get("subject")
            subject_id = subject.get("id") if isinstance(subject, dict) else None
            if subject_id != actor_id:
                errors.append(
                    f"event={event['id']} type={event.get('type')} "
                    f"check={check.get('type')} subject={subject_id} "
                    f"actor={actor_id}"
                )

    assert not errors, f"{path.name}: action check subject mismatch:\n" + "\n".join(errors)


def test_local_successful_rerolls_do_not_leave_failed_move(replay_timeline):
    path, _timeline, narrative = replay_timeline
    errors = []

    for event in narrative["events"]:
        if event.get("type") != "move":
            continue

        movement_checks = [
            check for check in event.get("checks", [])
            if check.get("type") in MOVEMENT_CHECKS
        ]
        for check in movement_checks:
            attempts = check.get("attempts", [])
            if (
                check.get("reroll_used")
                and attempts
                and attempts[-1].get("outcome") == "passed"
                and event.get("outcome") == "failed"
            ):
                errors.append(
                    f"event={event['id']} check={check.get('type')}: "
                    "reroll finished passed but move outcome is failed"
                )

    assert not errors, (
        f"{path.name}: successful reroll left failed movement:\n"
        + "\n".join(errors)
    )


def test_local_turnover_causes_are_valid_and_in_same_turn(replay_timeline):
    path, timeline, _narrative = replay_timeline
    known = {event.id: event for event in timeline.events}
    context = _event_context(timeline)
    errors = []

    for event in timeline.events:
        if event.type != "turn_end" or event.outcome != "turnover":
            continue

        cause_id = event.caused_by
        if cause_id is None:
            errors.append(f"turnover event={event.id}: missing caused_by")
            continue
        if cause_id not in known:
            errors.append(
                f"turnover event={event.id}: caused_by={cause_id} does not exist"
            )
            continue

        turnover_context = context.get(event.id)
        cause_context = context.get(cause_id)
        if (
            turnover_context is not None
            and cause_context is not None
            and turnover_context != cause_context
        ):
            errors.append(
                f"turnover event={event.id}: cause={cause_id} is in another turn "
                f"{cause_context} != {turnover_context}"
            )

        if cause_id >= event.id:
            errors.append(
                f"turnover event={event.id}: cause={cause_id} is not earlier"
            )

    assert not errors, f"{path.name}: invalid turnover causality:\n" + "\n".join(errors)


def test_local_narrative_references_are_not_dangling(replay_timeline):
    path, timeline, narrative = replay_timeline
    raw_ids = {event.id for event in timeline.events}
    errors = []

    for event in narrative["events"]:
        details = event.get("details", {})
        references = []

        for key in ("action_event_id", "turnover_event_id", "turnover_caused_by"):
            value = details.get(key)
            if value is not None:
                references.append((key, value))

        for value in details.get("grouped_event_ids", []):
            references.append(("grouped_event_ids", value))

        caused_by = event.get("caused_by")
        if caused_by is not None:
            references.append(("caused_by", caused_by))

        for key, value in references:
            if value not in raw_ids:
                errors.append(
                    f"event={event['id']} {key}={value} does not reference a raw event"
                )

    assert not errors, f"{path.name}: dangling narrative references:\n" + "\n".join(errors)


def test_local_pass_groups_keep_passer_and_context(replay_timeline):
    path, timeline, narrative = replay_timeline
    raw_by_id = {event.id: event for event in timeline.events}
    context = _event_context(timeline)
    errors = []

    for event in narrative["events"]:
        if event.get("type") != "pass":
            continue

        actor = event.get("actor")
        details = event.get("details", {})
        passer = details.get("passer")
        if actor is not None and passer is not None and actor.get("id") != passer.get("id"):
            errors.append(
                f"event={event['id']}: passer={passer.get('id')} "
                f"does not match actor={actor.get('id')}"
            )

        base_context = context.get(event["id"])
        for grouped_id in details.get("grouped_event_ids", []):
            if grouped_id not in raw_by_id:
                continue
            grouped_context = context.get(grouped_id)
            if (
                base_context is not None
                and grouped_context is not None
                and grouped_context != base_context
            ):
                errors.append(
                    f"event={event['id']}: grouped event={grouped_id} "
                    f"crosses turn context {grouped_context} != {base_context}"
                )

    assert not errors, f"{path.name}: inconsistent pass grouping:\n" + "\n".join(errors)


def test_local_unresolved_types_are_known(replay_timeline):
    path, timeline, _narrative = replay_timeline
    unresolved = timeline.unresolved
    unknown = sorted(set(unresolved) - KNOWN_UNRESOLVED)

    assert not unknown, (
        f"{path.name}: new unresolved protocol types: {unknown}; "
        f"all unresolved={dict(unresolved)}"
    )
