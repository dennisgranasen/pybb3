#!/usr/bin/env python3
"""Download one available BB3 replay and print its complete JSON to stdout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bb3 import BB3Client
from bb3.replay import replay_xml_to_json


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("replays"))
    parser.add_argument("--helper", help="path to BB3SteamAuth")
    parser.add_argument("--cache-path", default=".bb3-steam-auth.json")
    parser.add_argument("--search-size", type=int, default=25)
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("bbr", "xml", "json"),
        default=("bbr", "xml", "json"),
        help="formats to save (default: bbr xml json)",
    )
    return parser.parse_args()


def find_official_replay_game(client, *, search_size: int, progress):
    """Find a replay-bearing match in a public official competition."""
    progress("Looking for public official competitions...")
    competitions = client.list_official_competitions(limit=search_size)
    if not competitions:
        raise RuntimeError("No public official competition was found")

    for name, competition_id in competitions:
        progress(f"Searching official competition {name or competition_id}...")
        for game in client.list_matches(
            competition_id,
            limit=search_size,
            completed=True,
            has_replay=True,
        ):
            if game.game_id:
                return game
    raise RuntimeError("No completed official match with a replay was found")


def main() -> int:
    args = parse_args()
    progress = lambda message: print(message, file=sys.stderr, flush=True)
    progress("Starting Steam authentication...")
    with BB3Client.from_steam(helper=args.helper, cache_path=args.cache_path) as client:
        progress("Connected. Logging in to BB3...")
        client.login()
        progress("Logged in.")
        game = find_official_replay_game(
            client, search_size=args.search_size, progress=progress
        )
        progress(f"Downloading replay for game {game.game_id}...")
        replay = client.download_replay(game.game_id)
        anonymous = replay.redact_ip_addresses()

    for replay_format in args.formats:
        path = args.output_dir / f"{game.game_id}.{replay_format}"
        anonymous.save(path)
        if not path.is_file():
            raise RuntimeError(f"Replay was not saved correctly: {path}")
        progress(f"Saved and verified: {path}")
    print(replay_xml_to_json(anonymous.xml_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
