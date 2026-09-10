#!/usr/bin/env python3
"""Print decoded IpAddress values from replay XML/BBR or converted JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bb3.client import BB3Client


def main() -> int:
    with BB3Client.from_steam() as c:
        c.login()
        competitions = c.list_official_competitions()
        for competition in competitions:
            print(competition)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
