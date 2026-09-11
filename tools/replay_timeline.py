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
    parser.add_argument(
        "--narrative", action="store_true",
        help="write the compact, non-duplicated LLM narrative format",
    )
    parser.add_argument(
        "--include-moves", action="store_true",
        help="include routine successful movement in narrative format",
    )
    parser.add_argument(
        "--include-evidence", action="store_true",
        help="include raw protocol messages in narrative format",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="indent narrative JSON",
    )
    args = parser.parse_args()
    raw = args.replay.read_bytes()
    replay = Replay.from_xml(raw) if args.replay.suffix.lower() == ".xml" else Replay.from_bbr(raw)
    timeline = replay.timeline()
    if args.narrative:
        indent = 2 if args.pretty else None
        if args.output:
            timeline.save_narrative(
                args.output, indent=indent, include_moves=args.include_moves,
                include_evidence=args.include_evidence,
            )
        else:
            print(timeline.to_narrative_json(
                indent=indent, include_moves=args.include_moves,
                include_evidence=args.include_evidence,
            ))
    elif args.output:
        timeline.save(args.output)
    else:
        print(timeline.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
