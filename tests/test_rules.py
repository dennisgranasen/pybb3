import json

from bb3.rules import BB3Rules


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
