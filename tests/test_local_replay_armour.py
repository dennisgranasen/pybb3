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


@pytest.mark.parametrize("bbr_path", BBR_FILES, ids=lambda path: path.name)
def test_local_armour_checks_match_armour_effect_subject(bbr_path):
    timeline = Replay.from_bbr(bbr_path.read_bytes()).timeline()
    narrative = timeline.to_narrative_dict(
        include_moves=True, include_evidence=False
    )
    narrative_by_id = {event["id"]: event for event in narrative["events"]}
    errors = []

    for event in timeline.events:
        armour_effects = [
            effect
            for effect in event.effects
            if effect.type == "armour_roll" and effect.subject is not None
        ]
        if not armour_effects:
            continue

        projected = narrative_by_id.get(event.id)
        if projected is None:
            continue

        armour_checks = [
            check
            for check in projected.get("checks", [])
            if check.get("type") == "armour"
        ]
        if len(armour_checks) != len(armour_effects):
            errors.append(
                f"event={event.id} type={event.type}: "
                f"{len(armour_effects)} armour effects but "
                f"{len(armour_checks)} checks"
            )
            continue

        for effect, check in zip(armour_effects, armour_checks):
            subject = check.get("subject")
            subject_id = subject.get("id") if isinstance(subject, dict) else None
            if subject_id != effect.subject.id:
                errors.append(
                    f"event={event.id} type={event.type}: "
                    f"armour subject={subject_id} expected={effect.subject.id}"
                )

        if any(
            effect.get("type") == "armour_roll"
            for effect in projected.get("effects", [])
        ):
            errors.append(
                f"event={event.id} type={event.type}: "
                "armour_roll duplicated in narrative effects"
            )

    assert not errors, (
        f"{bbr_path.name}: invalid armour narrative projection:\n"
        + "\n".join(errors)
    )
