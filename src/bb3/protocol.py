from __future__ import annotations

from dataclasses import dataclass
import socket
import struct
import xml.etree.ElementTree as ET


class BB3ProtocolError(RuntimeError):
    pass


@dataclass(slots=True)
class BB3Frame:
    message_name: str
    message_token: int
    body: str
    data_type: str | None = None
    zipped: str | None = None


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError(
                f"Connection closed while waiting for {size} bytes "
                f"(received {len(chunks)})"
            )
        chunks.extend(chunk)
    return bytes(chunks)


def recv_frame(sock: socket.socket) -> BB3Frame:
    header_len = struct.unpack("<I", recv_exact(sock, 4))[0]
    if not 1 <= header_len <= 10000:
        raise BB3ProtocolError(f"Invalid BB3 header length: {header_len}")

    header_bytes = recv_exact(sock, header_len)
    try:
        header_root = ET.fromstring(header_bytes.decode("utf-8"))
    except Exception as exc:
        raise BB3ProtocolError("Invalid BB3 XML header") from exc

    data_el = header_root.find("Data")
    if data_el is None:
        raise BB3ProtocolError("BB3 header has no Data element")

    body_size = int(data_el.attrib.get("size", "0"))
    body = recv_exact(sock, body_size).decode("utf-8", errors="replace")

    return BB3Frame(
        message_name=data_el.attrib.get("MessageName", ""),
        message_token=int(data_el.attrib.get("MessageToken", "0")),
        body=body,
        data_type=data_el.attrib.get("type"),
        zipped=data_el.attrib.get("zipped"),
    )


def send_frame(
    sock: socket.socket,
    message_name: str,
    message_token: int,
    body: str,
) -> None:
    body_bytes = body.encode("utf-8")
    header = (
        '<Header><Data '
        'type="textxml" '
        f'size="{len(body_bytes)}" '
        'zipped="false" '
        f'MessageName="{message_name}" '
        f'MessageToken="{message_token}" '
        f'sizeBeforeCompression="{len(body_bytes)}"'
        '/></Header>'
    ).encode("utf-8")

    sock.sendall(struct.pack("<I", len(header)) + header + body_bytes)


def parse_xml(body: str) -> ET.Element:
    try:
        return ET.fromstring(body)
    except Exception as exc:
        raise BB3ProtocolError("Invalid BB3 response XML") from exc


def text(root: ET.Element, name: str, default: str | None = None) -> str | None:
    value = root.findtext(name)
    return default if value is None else value
