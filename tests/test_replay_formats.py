import base64
import json
import xml.etree.ElementTree as ET

from bb3.client import BB3Client, ReplayNotFoundError
from bb3.replay import (
    Replay,
    decode_replay,
    encode_replay,
    replay_xml_to_dict,
    save_replay,
)


def replay_response(xml: bytes) -> ET.Element:
    return ET.fromstring(
        "<ResponseDownloadReplay><ReplayData>"
        + encode_replay(xml)
        + "</ReplayData></ResponseDownloadReplay>"
    )


def test_replay_encode_decode_round_trip():
    xml = b"<Replay><ReplayVersion>1-4-0-0</ReplayVersion></Replay>"
    assert decode_replay(encode_replay(xml)) == xml


def test_download_replay_returns_raw_bbr_without_writing(monkeypatch, tmp_path):
    encoded_ip = base64.b64encode(b"203.0.113.99").decode()
    source_xml = f"<Replay><IpAddress>{encoded_ip}</IpAddress></Replay>".encode()
    client = BB3Client(host="example.invalid", port=1)
    monkeypatch.setattr(client, "request", lambda *_args, **_kwargs: replay_response(source_xml))

    replay = client.download_replay("game-1")

    assert replay.bbr_data == encode_replay(source_xml)
    assert replay.xml_data == source_xml
    assert list(tmp_path.iterdir()) == []


def test_download_replay_raises_specific_not_found_error(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: ET.fromstring("<ResponseDownloadReplay/>"),
    )
    try:
        client.download_replay("missing")
    except ReplayNotFoundError:
        pass
    else:
        raise AssertionError("ReplayNotFoundError was not raised")


def test_list_official_competitions_returns_name_and_id(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    competition_id = base64.b64encode(b"competition-1").decode()
    name = base64.b64encode(b"Official Ladder").decode()
    monkeypatch.setattr(
        client,
        "get_competitions",
        lambda **_kwargs: ET.fromstring(
            f"<ResponseGetCompetitions><Competitions><Competition>"
            f"<Id>{competition_id}</Id><Name>{name}</Name>"
            "</Competition></Competitions></ResponseGetCompetitions>"
        ),
    )
    assert client.list_official_competitions() == (
        ("Official Ladder", "competition-1"),
    )


def test_list_matches_defaults_to_latest_ten(monkeypatch):
    client = BB3Client(host="example.invalid", port=1)
    seen = {}

    def fake_get_games_model(**kwargs):
        seen.update(kwargs)
        return type("Games", (), {"games": ("match",)})()

    monkeypatch.setattr(client, "get_games_model", fake_get_games_model)
    assert client.list_matches("competition-1") == ("match",)
    assert seen["size"] == 10
    assert seen["competition_ids"] == ["competition-1"]
    assert seen["descending"] is True


def test_save_replay_converts_xml_to_recognized_formats(tmp_path):
    xml = b"<Replay><ReplayVersion>1</ReplayVersion></Replay>"
    save_replay(xml, tmp_path / "game.bbr")
    save_replay(xml, tmp_path / "game.xml")
    save_replay(xml, tmp_path / "game.json")

    assert decode_replay((tmp_path / "game.bbr").read_bytes()) == xml
    assert (tmp_path / "game.xml").read_bytes() == xml
    assert replay_xml_to_dict(xml) == json.loads((tmp_path / "game.json").read_text())


def test_replay_can_start_from_each_representation_and_redaction_is_lazy(tmp_path):
    encoded_ip = base64.b64encode(b"198.51.100.44").decode()
    xml = f"<Replay><IpAddress>{encoded_ip}</IpAddress></Replay>".encode()
    variants = (
        Replay.from_bbr(encode_replay(xml)),
        Replay.from_xml(xml),
        Replay.from_json(replay_xml_to_dict(xml)),
    )
    for replay in variants:
        anonymous = replay.redact_ip_addresses()
        assert anonymous.xml_data != xml
        assert decode_replay(anonymous.bbr_data) == anonymous.xml_data
        anonymous.save(tmp_path / f"anonymous-{id(replay)}.json")


def test_save_replay_preserves_unknown_format(tmp_path):
    raw = b"opaque replay bytes"
    path = save_replay(raw, tmp_path / "game.dat")
    assert path.read_bytes() == raw
