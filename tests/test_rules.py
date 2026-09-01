import json

from bb3.rules import BB3Rules, PositionRule, RaceRule, SkillRule, TeamImprovementRule


def test_rules_indexes_and_position_helpers(tmp_path):
    path = tmp_path / "BB3Rules.json"
    path.write_text(json.dumps({
        "bb3_rules_position": [
            {"code": 1102, "data": "woodElf_woodElfWardancer"}
        ],
        "bb3_rules_position_characteristics": [
            {"position": "woodElf_woodElfWardancer", "characteristic": "MA", "value": 8}
        ],
        "bb3_rules_position_skills": [
            {"position": "woodElf_woodElfWardancer", "skill": "block"}
        ],
    }))
    rules = BB3Rules.load(path)
    assert rules.position_by_code(1102).name == "woodElf_woodElfWardancer"
    assert rules.position("woodElf_woodElfWardancer").code == 1102
    assert rules.position_characteristics("woodElf_woodElfWardancer") == {"MA": 8}
    assert rules.position_skills("woodElf_woodElfWardancer") == ["block"]
    assert len(rules.sha256) == 64


def test_typed_rule_views_retain_raw_records_and_relationships(tmp_path):
    path = tmp_path / "BB3Rules.json"
    path.write_text(json.dumps({
        "bb3_rules_position": [{"code": 1102, "data": "wardancer", "cost": 125000}],
        "bb3_rules_position_characteristics": [
            {"position": "wardancer", "characteristic": "MA", "value": 8}
        ],
        "bb3_rules_position_skills": [{"position": "wardancer", "skill": "block"}],
        "bb3_rules_race": [{"code": 7, "data": "wood_elf"}],
        "bb3_rules_skill": [{"code": 1, "data": "block"}],
        "bb3_rules_team_improvement": [{"code": 4, "data": "reroll"}],
    }))
    rules = BB3Rules.load(path)

    position = rules.position_by_code(1102)
    assert isinstance(position, PositionRule)
    assert position.characteristics == {"MA": 8}
    assert position.skills == ("block",)
    assert position["cost"] == 125000
    assert position.record is rules.by_code("bb3_rules_position", 1102)
    assert isinstance(rules.race_by_code(7), RaceRule)
    assert isinstance(rules.skill("block"), SkillRule)
    assert isinstance(rules.team_improvement("reroll"), TeamImprovementRule)
