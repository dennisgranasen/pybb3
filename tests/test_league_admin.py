from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

from bb3.client import BB3Client
from bb3.enums import AdmissionMode, CompetitionFormat, TimerId
from bb3.models import League


def b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def recorder(client, monkeypatch):
    calls = []

    def fake(request_name, response_name, extra_xml=""):
        calls.append((request_name, response_name, extra_xml))
        values = {
            "ResponseGetCompetitionDaysNumber": "<Value>3</Value>",
            "ResponseGetCompetitionDescription": f"<Value>{b64('description')}</Value>",
            "ResponseGetLeagueDescription": f"<Description>{b64('league description')}</Description>",
            "ResponseGetPassword": f"<Password>{b64('secret')}</Password>",
        }
        return ET.fromstring(f"<{response_name}>{values.get(response_name, '')}</{response_name}>")

    monkeypatch.setattr(client, "request", fake)
    return calls


def test_create_league_contract(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = recorder(client, monkeypatch)
    client.create_league(
        "League", description="Description", logo_id="logo-id",
        password="pwd", language=0, is_cross_play=True,
    )
    request, response, body = calls[-1]
    assert (request, response) == ("RequestCreateLeague", "ResponseCreateLeague")
    assert f"<Name>{b64('League')}</Name>" in body
    assert f"<Description>{b64('Description')}</Description>" in body
    assert f"<LogoId>{b64('logo-id')}</LogoId>" in body
    assert "<HasPassword>true</HasPassword>" in body
    assert f"<Password>{b64('pwd')}</Password>" in body


def test_create_competition_contract(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = recorder(client, monkeypatch)
    client.create_competition(
        "Wissen", "league-id", format=CompetitionFormat.WISSEN,
        participants_number_max=16, timer_id=TimerId.UNLIMITED,
        admission_mode=AdmissionMode.TICKETS, logo_id="logo-id",
    )
    request, response, body = calls[-1]
    assert (request, response) == ("RequestCreateCompetition", "ResponseCreateCompetition")
    assert "<Format>3</Format>" in body
    assert "<ParticipantsNumberMax>16</ParticipantsNumberMax>" in body
    assert "<TimerId>6</TimerId>" in body
    assert "<AdmissionMode>2</AdmissionMode>" in body


def test_league_and_competition_read_contracts(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = recorder(client, monkeypatch)
    assert client.get_league_description("league") == "league description"
    assert calls[-1][2] == f"<LeagueId>{b64('league')}</LeagueId>"
    assert client.get_competition_description("competition") == "description"
    assert client.get_competition_days_number("competition") == 3
    assert client.get_competition_password("setting") == "secret"


def test_setting_mutation_response_names_and_wire_fields(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = recorder(client, monkeypatch)

    client.set_allow_custom_teams("setting", True)
    assert calls[-1][:2] == ("RequestSetAllowCustomTeams", "ResponseSetCompetitionSetting")
    assert "<AllowCustomTeams>true</AllowCustomTeams>" in calls[-1][2]

    client.set_enable_match_consequences("setting", False)
    assert calls[-1][:2] == ("RequestSetEnableMatchConsequences", "ResponseSetCompetitionSetting")

    client.set_competition_description("competition", "Description")
    assert f"<Idcompetition>{b64('competition')}</Idcompetition>" in calls[-1][2]

    client.set_banned_pitches("setting", ["pitch-1", "pitch-2"])
    assert f"<BannedPitchesItem>{b64('pitch-1')}</BannedPitchesItem>" in calls[-1][2]

    client.set_tv_range_max("setting", None)
    assert "<TvRangeMax>0</TvRangeMax><SetNoLimit>true</SetNoLimit>" in calls[-1][2]


def test_participant_by_gamer_keeps_observed_asymmetric_response(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = recorder(client, monkeypatch)
    client.get_competition_participants_by_gamer("competition", "gamer")
    assert calls[-1][:2] == (
        "RequestGetCompetitionParticipantsByGamer", "ResponseGetCompetitionRanking"
    )


def test_league_model():
    root = ET.fromstring(
        f"""<ResponseGetLeague><League><Id>{b64('league-id')}</Id>
        <UgcId>{b64('ugc-id')}</UgcId><BoardId>{b64('board-id')}</BoardId>
        <CompetitionSettingId>{b64('setting-id')}</CompetitionSettingId>
        <LogoId>{b64('logo-id')}</LogoId><Name>{b64('League')}</Name>
        <CreationTime>{b64('2026-09-01 21:10:02')}</CreationTime>
        <NbMember>2</NbMember><NbCompetition>3</NbCompetition>
        <IsOfficial>0</IsOfficial><IsEternal>0</IsEternal><IsCrossPlay>1</IsCrossPlay>
        </League></ResponseGetLeague>"""
    )
    league = League.from_response(root)
    assert league.league_id == "league-id"
    assert league.name == "League"
    assert league.member_count == 2
    assert league.competition_count == 3
    assert league.is_cross_play is True
