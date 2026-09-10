import base64
import ipaddress
import itertools
import json
from collections import defaultdict
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


def decode_replay_data(
    replay_data: str, *, redact_ip_addresses: bool = True
) -> bytes:
    layer1 = base64.b64decode(replay_data)
    layer2 = base64.b64decode(layer1)
    xml = zlib.decompress(layer2)
    if not xml.lstrip().startswith(b"<Replay"):
        raise ValueError("Decoded ReplayData is not Replay XML")
    if redact_ip_addresses:
        return redact_replay_ip_addresses(xml)
    return xml


def encode_replay_data(xml: bytes) -> str:
    """Encode replay XML using the ReplayData/.bbr wire representation."""
    compressed = zlib.compress(xml)
    inner = base64.b64encode(compressed)
    return base64.b64encode(inner).decode("ascii")
