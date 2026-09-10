import base64
import zlib

import xml.etree.ElementTree as ET
from bb3.client import BB3Client
from bb3.replay import (
    decode_replay_data,
    extract_ip_addresses_from_data,
    extract_replay_ip_addresses,
    redact_replay_ip_addresses,
    replay_xml_to_dict,
    replay_xml_to_json,
)


def test_replay_decode_chain():
    xml = b"<Replay><ReplayVersion>1-4-0-0</ReplayVersion></Replay>"
    encoded = base64.b64encode(base64.b64encode(zlib.compress(xml))).decode()
    assert decode_replay_data(encoded) == xml


def test_replay_ip_addresses_are_redacted_by_default():
    first = base64.b64encode(b"203.0.113.52").decode()
    second = base64.b64encode(b"198.51.100.83").decode()
    xml = (
        f"<Replay><IpAddress>{first}</IpAddress>"
        f"<Nested><IpAddress>{second}</IpAddress>"
        f"<IpAddress>{first}</IpAddress></Nested></Replay>"
    ).encode()
    encoded = base64.b64encode(base64.b64encode(zlib.compress(xml))).decode()

    result = decode_replay_data(encoded)
    values = [base64.b64decode(item.text).decode() for item in ET.fromstring(result).iter("IpAddress")]

    assert values == ["192.0.2.1", "192.0.2.2", "192.0.2.1"]
    assert b"203.0.113.52" not in result
    assert first.encode() not in result
    assert second.encode() not in result


def test_replay_ip_redaction_can_be_disabled_explicitly():
    encoded_ip = base64.b64encode(b"198.51.100.83").decode()
    xml = f"<Replay><IpAddress>{encoded_ip}</IpAddress></Replay>".encode()
    encoded = base64.b64encode(base64.b64encode(zlib.compress(xml))).decode()

    assert decode_replay_data(encoded, redact_ip_addresses=False) == xml


def test_redaction_handles_namespaced_ip_address_elements():
    encoded_ip = base64.b64encode(b"2001:db8::5").decode()
    xml = f'<Replay xmlns="urn:bb3"><IpAddress>{encoded_ip}</IpAddress></Replay>'.encode()

    result = redact_replay_ip_addresses(xml)

    address = next(
        element for element in ET.fromstring(result).iter()
        if element.tag.rsplit("}", 1)[-1] == "IpAddress"
    )
    assert base64.b64decode(address.text).decode() == "192.0.2.1"


def test_download_replay_forwards_explicit_redaction_choice(monkeypatch):
    replay_data = base64.b64encode(b"wire payload").decode()
    client = BB3Client(host="example.invalid", port=1)
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: ET.fromstring(
            f"<ResponseDownloadReplay><ReplayData>{replay_data}</ReplayData>"
            "</ResponseDownloadReplay>"
        ),
    )
    seen = {}

    def fake_decode(value, *, redact_ip_addresses=True):
        seen["value"] = value
        seen["redact"] = redact_ip_addresses
        return b"<Replay/>"

    monkeypatch.setattr("bb3.client.decode_replay_data", fake_decode)

    assert client.download_replay("game", redact_ip_addresses=False) == b"<Replay/>"
    assert seen == {"value": replay_data, "redact": False}


def test_replay_json_conversion_preserves_repeated_elements_and_ip_values():
    first = base64.b64encode(b"192.0.2.1").decode()
    second = base64.b64encode(b"192.0.2.2").decode()
    xml = (
        f"<Replay><header><EndGame><GamerResult><IpAddress>{first}</IpAddress>"
        f"</GamerResult><GamerResult><IpAddress>{second}</IpAddress>"
        "</GamerResult></EndGame></header></Replay>"
    ).encode()

    data = replay_xml_to_dict(xml)

    assert len(data["header"]["EndGame"]["GamerResult"]) == 2
    assert extract_replay_ip_addresses(xml) == ["192.0.2.1", "192.0.2.2"]
    assert extract_ip_addresses_from_data(data) == ["192.0.2.1", "192.0.2.2"]
