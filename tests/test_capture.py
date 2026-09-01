from __future__ import annotations

import ipaddress
import struct

from bb3.capture import TCPPacket, parse_tcp_packets, reconstruct_half_streams


def ethernet_ipv4_tcp(payload: bytes, sequence: int = 100) -> bytes:
    tcp = struct.pack("!HHIIHHHH", 12345, 17010, sequence, 0, 5 << 12, 0, 0, 0) + payload
    source = ipaddress.IPv4Address("192.0.2.1").packed
    destination = ipaddress.IPv4Address("198.51.100.2").packed
    total_length = 20 + len(tcp)
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, total_length, 1, 0x4000, 64, 6, 0, source, destination
    )
    ethernet = b"\x00" * 12 + struct.pack("!H", 0x0800)
    return ethernet + ip + tcp


def classic_pcap(packet: bytes) -> bytes:
    global_header = b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiiii", 2, 4, 0, 0, 65535, 1)
    record = struct.pack("<IIII", 10, 500000, len(packet), len(packet)) + packet
    return global_header + record


def pcapng_block(block_type: int, body: bytes) -> bytes:
    padding = b"\x00" * (-len(body) % 4)
    length = 12 + len(body) + len(padding)
    return struct.pack("<II", block_type, length) + body + padding + struct.pack("<I", length)


def pcapng(packet: bytes) -> bytes:
    section = pcapng_block(0x0A0D0D0A, b"\x4d\x3c\x2b\x1a" + struct.pack("<HHq", 1, 0, -1))
    interface = pcapng_block(1, struct.pack("<HHI", 1, 0, 65535))
    enhanced = pcapng_block(
        6, struct.pack("<IIIII", 0, 0, 10_500_000, len(packet), len(packet)) + packet
    )
    return section + interface + enhanced


def test_parse_classic_pcap_and_pcapng():
    raw_packet = ethernet_ipv4_tcp(b"BB3", 321)
    for capture in (classic_pcap(raw_packet), pcapng(raw_packet)):
        packets = parse_tcp_packets(capture)
        assert len(packets) == 1
        assert packets[0].source == "192.0.2.1"
        assert packets[0].destination_port == 17010
        assert packets[0].sequence == 321
        assert packets[0].payload == b"BB3"
        assert packets[0].timestamp == 10.5


def test_reconstruct_half_streams_handles_order_overlap_retransmission_and_gaps():
    def packet(sequence, payload, timestamp):
        return TCPPacket(timestamp, "a", 1, "b", 2, sequence, payload)

    chunks = reconstruct_half_streams([
        packet(103, b"def", 3),
        packet(100, b"abc", 1),
        packet(103, b"def", 2),
        packet(105, b"fghi", 4),
        packet(120, b"next", 5),
    ])

    assert [(chunk.sequence, chunk.data) for chunk in chunks] == [
        (100, b"abcdefghi"),
        (120, b"next"),
    ]
