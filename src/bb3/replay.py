from __future__ import annotations

import base64
import ipaddress
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zlib


_DOCUMENTATION_IPV4_NETWORKS = ("192.0.2", "198.51.100", "203.0.113")


def documentation_ipv4_addresses():
    """Yield RFC 5737 addresses that cannot identify real replay participants."""
    for network, host in itertools.product(_DOCUMENTATION_IPV4_NETWORKS, range(1, 255)):
        yield f"{network}.{host}"


def redact_replay_ip_addresses(xml: bytes) -> bytes:
    """Replace Base64-encoded ``IpAddress`` fields with documentation addresses.

    Equal source values receive the same replacement within one replay, while
    distinct source values remain distinct. The mapping exists in memory only.
    """
    root = ET.fromstring(xml)
    replacements: dict[str, str] = {}
    addresses = documentation_ipv4_addresses()

    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "IpAddress":
            continue
        source = element.text or ""
        replacement = replacements.get(source)
        if replacement is None:
            try:
                replacement = next(addresses)
            except StopIteration as exc:
                raise ValueError("Replay contains too many distinct IP addresses") from exc
            replacements[source] = replacement
        element.text = base64.b64encode(replacement.encode("ascii")).decode("ascii")

    return ET.tostring(root, encoding="utf-8")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_to_data(element: ET.Element) -> Any:
    children = list(element)
    if not children and not element.attrib:
        return element.text or ""

    result: dict[str, Any] = {
        f"@{_local_name(name)}": value for name, value in element.attrib.items()
    }
    grouped: dict[str, list[Any]] = defaultdict(list)
    for child in children:
        grouped[_local_name(child.tag)].append(_element_to_data(child))
    for name, values in grouped.items():
        result[name] = values[0] if len(values) == 1 else values
    if element.text and element.text.strip():
        result["#text"] = element.text
    return result


def replay_xml_to_dict(xml: bytes) -> dict[str, Any]:
    """Convert replay XML to JSON-compatible data without the outer Replay key."""
    root = ET.fromstring(xml)
    if _local_name(root.tag) != "Replay":
        raise ValueError("Expected Replay XML")
    value = _element_to_data(root)
    if not isinstance(value, dict):
        raise ValueError("Replay XML has no structured content")
    return value


def replay_xml_to_json(xml: bytes, *, indent: int | None = 2) -> str:
    """Convert replay XML to readable JSON."""
    return json.dumps(replay_xml_to_dict(xml), ensure_ascii=False, indent=indent)


def _decode_ip_address(value: str) -> str:
    try:
        decoded = base64.b64decode(value, validate=True).decode("ascii")
        return str(ipaddress.ip_address(decoded))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("IpAddress is not a Base64-encoded IP address") from exc


def extract_ip_addresses_from_data(value: Any) -> list[str]:
    """Find and decode every IpAddress scalar in JSON-compatible replay data."""
    addresses: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "IpAddress":
                candidates: Iterable[Any] = child if isinstance(child, list) else (child,)
                for candidate in candidates:
                    if not isinstance(candidate, str):
                        raise ValueError("IpAddress must be a string")
                    addresses.append(_decode_ip_address(candidate))
            else:
                addresses.extend(extract_ip_addresses_from_data(child))
    elif isinstance(value, list):
        for child in value:
            addresses.extend(extract_ip_addresses_from_data(child))
    return addresses


def extract_replay_ip_addresses(xml: bytes) -> list[str]:
    """Extract decoded IpAddress values directly from replay XML."""
    return extract_ip_addresses_from_data(replay_xml_to_dict(xml))


def decode_replay(replay_data: str | bytes) -> bytes:
    """Decode the double-Base64/zlib BBR representation to replay XML."""
    if isinstance(replay_data, bytes):
        replay_data = replay_data.decode("ascii")
    layer1 = base64.b64decode(replay_data)
    layer2 = base64.b64decode(layer1)
    xml = zlib.decompress(layer2)
    if not xml.lstrip().startswith(b"<Replay"):
        raise ValueError("Decoded ReplayData is not Replay XML")
    return xml


def encode_replay(xml: bytes) -> str:
    """Encode replay XML using the ReplayData/.bbr wire representation."""
    compressed = zlib.compress(xml)
    inner = base64.b64encode(compressed)
    return base64.b64encode(inner).decode("ascii")


def decode_replay_data(
    replay_data: str | bytes, *, redact_ip_addresses: bool = True
) -> bytes:
    """Compatibility wrapper for the former decode-and-redact operation."""
    xml = decode_replay(replay_data)
    return redact_replay_ip_addresses(xml) if redact_ip_addresses else xml


def encode_replay_data(xml: bytes) -> str:
    """Compatibility alias for :func:`encode_replay`."""
    return encode_replay(xml)


def _data_to_element(name: str, value: Any) -> ET.Element:
    element = ET.Element(name)
    if isinstance(value, dict):
        for key, child in value.items():
            if key.startswith("@"):
                element.set(key[1:], str(child))
            elif key == "#text":
                element.text = str(child)
            elif isinstance(child, list):
                for item in child:
                    element.append(_data_to_element(key, item))
            else:
                element.append(_data_to_element(key, child))
    elif value is not None:
        element.text = str(value)
    return element


def replay_json_to_xml(value: str | bytes | dict[str, Any]) -> bytes:
    """Convert this module's JSON representation back to replay XML."""
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    data = json.loads(value) if isinstance(value, str) else value
    if not isinstance(data, dict):
        raise ValueError("Replay JSON must contain an object")
    return ET.tostring(_data_to_element("Replay", data), encoding="utf-8")


def _replay_xml(value: str | bytes | dict[str, Any]) -> bytes:
    if isinstance(value, Replay):
        return value.xml_data
    if isinstance(value, dict):
        return replay_json_to_xml(value)
    raw = value.encode("utf-8") if isinstance(value, str) else value
    stripped = raw.lstrip()
    if stripped.startswith(b"<"):
        return raw
    if stripped.startswith((b"{", b"[")):
        return replay_json_to_xml(raw)
    return decode_replay(raw)


def save_replay(
    replay: "Replay" | str | bytes | dict[str, Any], filename: str | Path
) -> Path:
    """Save replay data, converting according to the destination suffix.

    ``.bbr``, ``.xml`` and ``.json`` are recognized. Other suffixes preserve
    the supplied value as bytes/text (or JSON for mapping input).
    """
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".bbr":
        encoded = replay.bbr_data if isinstance(replay, Replay) else encode_replay(
            _replay_xml(replay)
        )
        path.write_text(encoded, encoding="ascii")
    elif suffix == ".xml":
        path.write_bytes(_replay_xml(replay))
    elif suffix == ".json":
        json_text = (
            json.dumps(replay.json_data, ensure_ascii=False, indent=2)
            if isinstance(replay, Replay)
            else replay_xml_to_json(_replay_xml(replay))
        )
        path.write_text(json_text + "\n", encoding="utf-8")
    elif isinstance(replay, Replay):
        source = replay.source_data
        if isinstance(source, bytes):
            path.write_bytes(source)
        elif isinstance(source, str):
            path.write_text(source, encoding="utf-8")
        else:
            path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    elif isinstance(replay, bytes):
        path.write_bytes(replay)
    elif isinstance(replay, str):
        path.write_text(replay, encoding="utf-8")
    else:
        path.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


class Replay:
    """A replay backed by BBR, XML or JSON with lazy representation conversion."""

    def __init__(
        self,
        *,
        bbr_data: str | None = None,
        xml_data: bytes | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> None:
        supplied = sum(value is not None for value in (bbr_data, xml_data, json_data))
        if supplied != 1:
            raise ValueError("Replay requires exactly one source representation")
        self._bbr_data = bbr_data
        self._xml_data = xml_data
        self._json_data = json_data
        self._source_kind = (
            "bbr" if bbr_data is not None else "xml" if xml_data is not None else "json"
        )

    @classmethod
    def from_bbr(cls, data: str | bytes) -> "Replay":
        return cls(bbr_data=data.decode("ascii") if isinstance(data, bytes) else data)

    @classmethod
    def from_xml(cls, data: str | bytes) -> "Replay":
        return cls(xml_data=data.encode("utf-8") if isinstance(data, str) else data)

    @classmethod
    def from_json(cls, data: str | bytes | dict[str, Any]) -> "Replay":
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        parsed = json.loads(data) if isinstance(data, str) else data
        if not isinstance(parsed, dict):
            raise ValueError("Replay JSON must contain an object")
        return cls(json_data=parsed)

    @property
    def bbr_data(self) -> str:
        if self._bbr_data is None:
            self._bbr_data = encode_replay(self.xml_data)
        return self._bbr_data

    @property
    def xml_data(self) -> bytes:
        if self._xml_data is None:
            self._xml_data = (
                decode_replay(self._bbr_data)
                if self._bbr_data is not None
                else replay_json_to_xml(self._json_data or {})
            )
        return self._xml_data

    @property
    def json_data(self) -> dict[str, Any]:
        if self._json_data is None:
            self._json_data = replay_xml_to_dict(self.xml_data)
        return self._json_data

    @property
    def source_data(self) -> str | bytes | dict[str, Any]:
        if self._source_kind == "bbr":
            return self._bbr_data or ""
        if self._source_kind == "xml":
            return self._xml_data or b""
        return self._json_data or {}

    def decode(self) -> bytes:
        """Return replay XML, decoding lazily when necessary."""
        return self.xml_data

    def redact_ip_addresses(self) -> "Replay":
        """Return a new XML-backed Replay with participant IPs anonymized."""
        return Replay.from_xml(redact_replay_ip_addresses(self.xml_data))

    def save(self, filename: str | Path) -> Path:
        """Save in the representation selected by the filename suffix."""
        return save_replay(self, filename)

    def timeline(self):
        """Parse the replay into a structured, JSON-serializable match timeline."""
        from .timeline import ReplayTimeline

        return ReplayTimeline.from_xml(self.xml_data)
