#!/usr/bin/env python3
"""Reconstruct BB3 candidate TCP half-streams from pcap or pcapng."""

from __future__ import annotations

import argparse

from bb3.capture import read_tcp_packets, reconstruct_half_streams
from bb3.security import redact_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--port", type=int, help="Only include flows using this TCP port")
    parser.add_argument("--output-prefix", help="Write contiguous chunks using this prefix")
    args = parser.parse_args()

    packets = read_tcp_packets(args.file)
    if args.port is not None:
        packets = [
            packet
            for packet in packets
            if args.port in (packet.source_port, packet.destination_port)
        ]
    chunks = reconstruct_half_streams(packets)
    for index, chunk in enumerate(chunks):
        source, source_port, destination, destination_port = chunk.direction
        print(
            f"{index:03d} {chunk.timestamp:.6f} "
            f"{source}:{source_port} -> {destination}:{destination_port} "
            f"seq={chunk.sequence} size={len(chunk.data)}"
        )
        if args.output_prefix:
            path = f"{args.output_prefix}-{index:03d}.bin"
            with open(path, "xb") as stream:
                stream.write(redact_bytes(chunk.data))
            print(f"      wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
