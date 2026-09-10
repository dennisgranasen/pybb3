#!/usr/bin/env python3
"""Extract a structured JSON timeline from a BB3 replay file."""

from __future__ import annotations

import argparse
from pathlib import Path

from bb3.replay import Replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    raw = args.replay.read_bytes()
    replay = Replay.from_xml(raw) if args.replay.suffix.lower() == ".xml" else Replay.from_bbr(raw)
    timeline = replay.timeline()
    if args.output:
        timeline.save(args.output)
    else:
        print(timeline.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
