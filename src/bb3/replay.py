import base64
import itertools
import xml.etree.ElementTree as ET
import zlib


_DOCUMENTATION_IPV4_NETWORKS = ("192.0.2", "198.51.100", "203.0.113")


def _documentation_ipv4_addresses():
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
    addresses = _documentation_ipv4_addresses()

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
