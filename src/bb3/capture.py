from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


class BB3CaptureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TCPPacket:
    timestamp: float
    source: str
    source_port: int
    destination: str
    destination_port: int
    sequence: int
    payload: bytes

    @property
    def direction(self) -> tuple[str, int, str, int]:
        return (
            self.source,
            self.source_port,
            self.destination,
            self.destination_port,
        )


@dataclass(frozen=True, slots=True)
class TCPStreamChunk:
    direction: tuple[str, int, str, int]
    sequence: int
    timestamp: float
    data: bytes


def read_tcp_packets(path: str | Path) -> list[TCPPacket]:
    return parse_tcp_packets(Path(path).read_bytes())


def parse_tcp_packets(data: bytes) -> list[TCPPacket]:
    if len(data) < 4:
        raise BB3CaptureError("Capture is truncated")
    if data[:4] == b"\x0a\x0d\x0d\x0a":
        records = _pcapng_records(data)
    else:
        records = _pcap_records(data)

    packets = []
    for timestamp, link_type, packet_data in records:
        packet = _decode_tcp_packet(timestamp, link_type, packet_data)
        if packet is not None and packet.payload:
            packets.append(packet)
    return packets


def reconstruct_half_streams(packets: Iterable[TCPPacket]) -> list[TCPStreamChunk]:
    """Reassemble each TCP direction independently, removing retransmissions."""
    grouped: dict[tuple[str, int, str, int], list[TCPPacket]] = {}
    for packet in packets:
        if packet.payload:
            grouped.setdefault(packet.direction, []).append(packet)

    result: list[TCPStreamChunk] = []
    for direction, direction_packets in grouped.items():
        direction_packets.sort(key=lambda packet: (packet.sequence, packet.timestamp))
        start = direction_packets[0].sequence
        timestamp = direction_packets[0].timestamp
        assembled = bytearray(direction_packets[0].payload)
        end = start + len(assembled)
        for packet in direction_packets[1:]:
            packet_end = packet.sequence + len(packet.payload)
            if packet.sequence > end:
                result.append(TCPStreamChunk(direction, start, timestamp, bytes(assembled)))
                start = packet.sequence
                timestamp = packet.timestamp
                assembled = bytearray(packet.payload)
                end = packet_end
                continue
            if packet_end > end:
                assembled.extend(packet.payload[end - packet.sequence :])
                end = packet_end
        result.append(TCPStreamChunk(direction, start, timestamp, bytes(assembled)))
    return sorted(result, key=lambda chunk: (chunk.timestamp, chunk.direction, chunk.sequence))


def _pcap_records(data: bytes) -> Iterator[tuple[float, int, bytes]]:
    magic = data[:4]
    formats = {
        b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
        b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
        b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
        b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
    }
    try:
        endian, resolution = formats[magic]
    except KeyError as exc:
        raise BB3CaptureError("Unsupported capture format") from exc
    if len(data) < 24:
        raise BB3CaptureError("Pcap global header is truncated")
    _, _, _, _, _, link_type = struct.unpack_from(endian + "HHiiii", data, 4)
    offset = 24
    while offset < len(data):
        if offset + 16 > len(data):
            raise BB3CaptureError("Pcap packet header is truncated")
        seconds, fraction, captured, _original = struct.unpack_from(
            endian + "IIII", data, offset
        )
        offset += 16
        end = offset + captured
        if end > len(data):
            raise BB3CaptureError("Pcap packet data is truncated")
        yield seconds + fraction / resolution, link_type, data[offset:end]
        offset = end


def _pcapng_records(data: bytes) -> Iterator[tuple[float, int, bytes]]:
    offset = 0
    endian: str | None = None
    interfaces: list[tuple[int, float]] = []
    while offset < len(data):
        if offset + 12 > len(data):
            raise BB3CaptureError("Pcapng block header is truncated")
        raw_type = data[offset : offset + 4]
        if raw_type == b"\x0a\x0d\x0d\x0a":
            byte_order = data[offset + 8 : offset + 12]
            if byte_order == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif byte_order == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            else:
                raise BB3CaptureError("Invalid pcapng byte-order magic")
            interfaces = []
        elif endian is None:
            raise BB3CaptureError("Pcapng does not start with a section header")

        current_endian = endian or "<"
        block_type, block_length = struct.unpack_from(current_endian + "II", data, offset)
        if block_length < 12 or block_length % 4 or offset + block_length > len(data):
            raise BB3CaptureError("Invalid pcapng block length")
        trailing = struct.unpack_from(
            current_endian + "I", data, offset + block_length - 4
        )[0]
        if trailing != block_length:
            raise BB3CaptureError("Mismatched pcapng block length")

        if block_type == 1:
            link_type = struct.unpack_from(current_endian + "H", data, offset + 8)[0]
            options = data[offset + 16 : offset + block_length - 4]
            interfaces.append((link_type, _pcapng_timestamp_resolution(options, current_endian)))
        elif block_type == 6:
            if block_length < 32:
                raise BB3CaptureError("Enhanced packet block is truncated")
            interface_id, high, low, captured, _original = struct.unpack_from(
                current_endian + "IIIII", data, offset + 8
            )
            try:
                link_type, resolution = interfaces[interface_id]
            except IndexError as exc:
                raise BB3CaptureError("Unknown pcapng interface id") from exc
            packet_start = offset + 28
            packet_end = packet_start + captured
            if packet_end > offset + block_length - 4:
                raise BB3CaptureError("Enhanced packet data is truncated")
            ticks = (high << 32) | low
            yield ticks * resolution, link_type, data[packet_start:packet_end]
        offset += block_length


def _pcapng_timestamp_resolution(options: bytes, endian: str) -> float:
    offset = 0
    while offset + 4 <= len(options):
        code, length = struct.unpack_from(endian + "HH", options, offset)
        offset += 4
        value = options[offset : offset + length]
        offset += (length + 3) & ~3
        if code == 0:
            break
        if code == 9 and value:
            resolution = value[0]
            return 2.0 ** -(resolution & 0x7F) if resolution & 0x80 else 10.0 ** -resolution
    return 1e-6


def _decode_tcp_packet(timestamp: float, link_type: int, data: bytes) -> TCPPacket | None:
    if link_type == 1:  # Ethernet
        if len(data) < 14:
            return None
        protocol = struct.unpack_from("!H", data, 12)[0]
        offset = 14
        while protocol in (0x8100, 0x88A8):
            if len(data) < offset + 4:
                return None
            protocol = struct.unpack_from("!H", data, offset + 2)[0]
            offset += 4
        network = data[offset:]
    elif link_type == 101:  # Raw IP
        protocol = 0x86DD if data and data[0] >> 4 == 6 else 0x0800
        network = data
    else:
        return None

    if protocol == 0x0800:
        decoded = _decode_ipv4_tcp(network)
    elif protocol == 0x86DD:
        decoded = _decode_ipv6_tcp(network)
    else:
        return None
    if decoded is None:
        return None
    source, destination, source_port, destination_port, sequence, payload = decoded
    return TCPPacket(
        timestamp, source, source_port, destination, destination_port, sequence, payload
    )


def _decode_ipv4_tcp(data: bytes):
    if len(data) < 20 or data[0] >> 4 != 4:
        return None
    header_length = (data[0] & 0x0F) * 4
    total_length = struct.unpack_from("!H", data, 2)[0]
    if header_length < 20 or total_length < header_length or len(data) < total_length:
        return None
    # Skip every fragment (MF or non-zero offset); reassembly belongs below IP.
    if data[9] != 6 or struct.unpack_from("!H", data, 6)[0] & 0x3FFF:
        return None
    source = str(ipaddress.IPv4Address(data[12:16]))
    destination = str(ipaddress.IPv4Address(data[16:20]))
    return _decode_tcp(source, destination, data[header_length:total_length])


def _decode_ipv6_tcp(data: bytes):
    if len(data) < 40 or data[0] >> 4 != 6 or data[6] != 6:
        return None
    payload_length = struct.unpack_from("!H", data, 4)[0]
    if len(data) < 40 + payload_length:
        return None
    source = str(ipaddress.IPv6Address(data[8:24]))
    destination = str(ipaddress.IPv6Address(data[24:40]))
    return _decode_tcp(source, destination, data[40 : 40 + payload_length])


def _decode_tcp(source: str, destination: str, data: bytes):
    if len(data) < 20:
        return None
    source_port, destination_port, sequence = struct.unpack_from("!HHI", data, 0)
    header_length = (data[12] >> 4) * 4
    if header_length < 20 or header_length > len(data):
        return None
    return source, destination, source_port, destination_port, sequence, data[header_length:]
