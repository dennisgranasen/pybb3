#!/usr/bin/env python3
"""Print decoded IpAddress values from replay XML/BBR or converted JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bb3.replay import (
    decode_replay,
    extract_ip_addresses_from_data,
    extract_replay_ip_addresses,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help=".bbr/.xml/.json file, or - for stdin")
    return parser.parse_args()


def main() -> int:
    source = parse_args().file
    raw = sys.stdin.buffer.read() if str(source) == "-" else source.read_bytes()
    stripped = raw.lstrip()
    if stripped.startswith((b"{", b"[")):
        addresses = extract_ip_addresses_from_data(json.loads(raw))
    else:
        replay_xml = raw if stripped.startswith(b"<") else decode_replay(raw)
        addresses = extract_replay_ip_addresses(replay_xml)
    for address in addresses:
        print(address)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
