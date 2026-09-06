from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

from bb3.client import BB3Client


def dec(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


def capture_request(client, monkeypatch, response_xml: str = "<Response/>"):
    calls = []

    def fake_request(request_name, response_name, extra_xml=""):
        calls.append((request_name, response_name, extra_xml))
        return ET.fromstring(response_xml)

    monkeypatch.setattr(client, "request", fake_request)
    return calls


def test_league_news_requests_match_capture(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = capture_request(client, monkeypatch)

    client.create_league_news("league-id", "New header", "This is news.")
    request, response, xml = calls[-1]
    root = ET.fromstring(f"<Root>{xml}</Root>")

    assert (request, response) == ("RequestCreateLeagueNews", "ResponseCreateLeagueNews")
    assert dec(root.findtext("LeagueId")) == "league-id"
    assert dec(root.findtext("Title")) == "New header"
    assert dec(root.findtext("Description")) == "This is news."


def test_get_league_languages_decodes_names(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    response = (
        "<ResponseGetLeagueLangs><Langs>"
        "<LeagueLang><Id>0</Id><Name>QWxsIGxhbmd1YWdlcw==</Name></LeagueLang>"
        "<LeagueLang><Id>2</Id><Name>RW5nbGlzaA==</Name></LeagueLang>"
        "</Langs></ResponseGetLeagueLangs>"
    )
    capture_request(client, monkeypatch, response)

    assert client.get_league_languages() == {0: "All languages", 2: "English"}


def test_league_password_is_decoded(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    capture_request(
        client,
        monkeypatch,
        "<ResponseGetLeaguePassword><Password>MTIz</Password></ResponseGetLeaguePassword>",
    )

    assert client.get_league_password("league-id") == "123"


def test_competition_gamer_number(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = capture_request(
        client,
        monkeypatch,
        "<ResponseGetCompetitionGamerNumber><Value>7</Value><AIs>2</AIs>"
        "</ResponseGetCompetitionGamerNumber>",
    )

    assert client.get_competition_gamer_number("competition-id") == (7, 2)
    request, response, xml = calls[-1]
    assert (request, response) == (
        "RequestGetCompetitionGamerNumber",
        "ResponseGetCompetitionGamerNumber",
    )
    root = ET.fromstring(f"<Root>{xml}</Root>")
    assert dec(root.findtext("IdCompetition")) == "competition-id"


def test_competition_ticket_filter_envelope(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = capture_request(client, monkeypatch)

    client.get_competition_tickets("competition-id")
    request, response, xml = calls[-1]
    root = ET.fromstring(f"<Root>{xml}</Root>")

    assert (request, response) == (
        "RequestGetCompetitionTickets",
        "ResponseGetCompetitionTickets",
    )
    assert root.findtext("Size") == "15"
    assert root.findtext("Start") == "0"
    assert dec(root.findtext("CompetitionId")) == "competition-id"
    assert [e.text for e in root.findall("./Type/TypeItem")] == ["1", "0"]
    assert [e.text for e in root.findall("./Status/StatusItem")] == ["0"]


def test_valid_teams_request_matches_observed_shape(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = capture_request(client, monkeypatch)

    client.get_competition_gamer_valid_teams("competition-id", "gamer-id")
    _, _, xml = calls[-1]
    root = ET.fromstring(f"<Root>{xml}</Root>")

    assert dec(root.findtext("GamerId")) == "gamer-id"
    assert dec(root.findtext("CompetitionId")) == "competition-id"
    assert root.find("Races") is not None
    assert root.find("Name") is not None
    assert root.find("Competing") is not None
    assert root.find("IsCustom") is not None
    assert root.find("IsTemplate") is not None


def test_join_and_quit_competition(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    calls = capture_request(client, monkeypatch)

    client.join_competition("team-id", "competition-id")
    request, response, xml = calls[-1]
    root = ET.fromstring(f"<Root>{xml}</Root>")
    assert (request, response) == ("RequestJoinCompetition", "ResponseJoinCompetition")
    assert dec(root.findtext("IdTeam")) == "team-id"
    assert dec(root.findtext("IdCompetition")) == "competition-id"

    client.quit_competition("participant-id")
    request, response, xml = calls[-1]
    root = ET.fromstring(f"<Root>{xml}</Root>")
    assert (request, response) == ("RequestQuitCompetition", "ResponseQuitCompetition")
    assert dec(root.findtext("ParticipantId")) == "participant-id"
    assert root.find("CompetitionId") is not None


def test_has_competition_password(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    capture_request(
        client,
        monkeypatch,
        "<ResponseHasPassword><Value>1</Value></ResponseHasPassword>",
    )

    assert client.has_competition_password("setting-id") is True
