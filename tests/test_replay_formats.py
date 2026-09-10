import base64
import json
import xml.etree.ElementTree as ET

from bb3.client import BB3Client
from bb3.replay import decode_replay_data, encode_replay_data


def replay_response(xml: bytes) -> ET.Element:
    return ET.fromstring(
        "<ResponseDownloadReplay><ReplayData>"
        + encode_replay_data(xml)
        + "</ReplayData></ResponseDownloadReplay>"
    )


def test_replay_encode_decode_round_trip():
    xml = b"<Replay><ReplayVersion>1-4-0-0</ReplayVersion></Replay>"
    assert decode_replay_data(
        encode_replay_data(xml), redact_ip_addresses=False
    ) == xml


def test_download_replay_saves_repacked_bbr_xml_and_json(monkeypatch, tmp_path):
    encoded_ip = base64.b64encode(b"203.0.113.99").decode()
    source_xml = f"<Replay><IpAddress>{encoded_ip}</IpAddress></Replay>".encode()
    client = BB3Client(host="example.invalid", port=1)
    monkeypatch.setattr(client, "request", lambda *_args, **_kwargs: replay_response(source_xml))

    xml = client.download_replay("game-1", output_dir=tmp_path)

    assert (tmp_path / "game-1.xml").read_bytes() == xml
    assert decode_replay_data(
        (tmp_path / "game-1.bbr").read_text(), redact_ip_addresses=False
    ) == xml
    assert json.loads((tmp_path / "game-1.json").read_text())["IpAddress"]


def test_download_replay_saves_only_selected_formats(monkeypatch, tmp_path):
    source_xml = b"<Replay><ReplayVersion>1</ReplayVersion></Replay>"
    client = BB3Client(host="example.invalid", port=1)
    monkeypatch.setattr(client, "request", lambda *_args, **_kwargs: replay_response(source_xml))

    client.download_replay("game-1", output_dir=tmp_path, formats=("bbr", "json"))

    assert (tmp_path / "game-1.bbr").is_file()
    assert (tmp_path / "game-1.json").is_file()
    assert not (tmp_path / "game-1.xml").exists()
