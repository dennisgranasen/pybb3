from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from bb3.client import BB3Client
from bb3.models import CharacteristicRoll, PlayerImprovements, TeamRoster

FIXTURES = Path(__file__).with_name("fixtures")


def test_get_team_roster_uses_captured_idteam_field(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    seen = {}

    def request(name, response, extra=""):
        seen.update(name=name, response=response, extra=extra)
        return ET.fromstring("<ResponseGetTeamRoster><Roster/></ResponseGetTeamRoster>")

    monkeypatch.setattr(client, "request", request)
    client.get_team_roster("team-uuid")

    assert seen["name"] == "RequestGetTeamRoster"
    assert seen["response"] == "ResponseGetTeamRoster"
    assert "<IdTeam>" in seen["extra"]
    assert "<TeamId>" not in seen["extra"]


def test_delete_team_uses_verified_body(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    seen = {}

    def request(name, response, extra=""):
        seen.update(name=name, response=response, extra=extra)
        return ET.fromstring("<ResponseDeleteTeam><Exceptions/></ResponseDeleteTeam>")

    monkeypatch.setattr(client, "request", request)
    client.delete_team("team-uuid")

    assert seen["name"] == "RequestDeleteTeam"
    assert seen["response"] == "ResponseDeleteTeam"
    assert "<IdTeam>" in seen["extra"]


def test_player_advancement_field_names_match_capture(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = []

    def request(name, response, extra=""):
        calls.append((name, response, extra))
        if name == "RequestGetPlayerImprovements":
            return ET.parse(FIXTURES / "player_improvements.xml").getroot()
        if name == "RequestAddPlayerRandomSkill":
            return ET.fromstring(
                "<ResponseAddPlayerRandomSkill><Exceptions/><HasLeft>0</HasLeft>"
                "<Skill>8</Skill></ResponseAddPlayerRandomSkill>"
            )
        if name == "RequestBeginIncreasePlayerCharacteristic":
            return ET.parse(FIXTURES / "characteristic_roll.xml").getroot()
        return ET.fromstring(f"<{response}><Exceptions/></{response}>")

    monkeypatch.setattr(client, "request", request)

    client.get_player_improvements("player-uuid")
    random_result = client.add_player_random_skill("player-uuid", 1)
    client.add_player_skill("player-uuid", 38)
    roll = client.begin_increase_player_characteristic("player-uuid")
    client.choose_increase_player_characteristic("player-uuid", 2)

    assert random_result.skill_id == 8
    assert roll.roll == 12

    assert "<IdPlayer>" in calls[0][2]
    assert "<IdPlayer>" in calls[1][2] and "<Category>1</Category>" in calls[1][2]
    assert "<IdPlayer>" in calls[2][2] and "<Skill>38</Skill>" in calls[2][2]
    assert "<PlayerId>" in calls[3][2] and "<IdPlayer>" not in calls[3][2]
    assert "<PlayerId>" in calls[4][2]
    assert "<ChosenCharacteristic>2</ChosenCharacteristic>" in calls[4][2]


def test_roster_fixture_parses_runtime_players_separately_from_templates():
    root = ET.parse(FIXTURES / "team_roster.xml").getroot()
    roster = TeamRoster.from_response(root)

    assert roster.nb_slots == 16
    assert roster.positions[0].position_id == 52
    assert roster.positions[0].cost == 40000
    assert roster.players[0].name == "Jitterbug"
    assert roster.players[0].position_id == 55
    assert roster.players[0].spp == 4
    assert roster.players[0].level_up_status == 1
    assert roster.players[0].slot_number == 6
    assert roster.players[0].number == 3
    assert roster.rosterized_inducements[0].inducement_id == 12


def test_player_improvements_fixture_uses_server_costs():
    root = ET.parse(FIXTURES / "player_improvements.xml").getroot()
    improvements = PlayerImprovements.from_response(root)

    assert improvements.spent_spp == 6
    assert improvements.characteristic_cost == 20
    category = improvements.skill_categories[0]
    assert category.cost_random == 4
    assert category.skills[0].skill_id == 8
    assert category.skills[0].cost == 8
    assert category.skills[0].choosable is True


def test_characteristic_roll_fixture_preserves_roll_and_secondary_fallback():
    root = ET.parse(FIXTURES / "characteristic_roll.xml").getroot()
    roll = CharacteristicRoll.from_response(root)

    assert roll.roll == 12
    assert roll.can_take_secondary_skill is True
    assert [x.available for x in roll.characteristics] == [True, False, True]
