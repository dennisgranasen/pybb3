#!/usr/bin/env python3
"""Download one available BB3 replay and print its complete JSON to stdout."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from bb3 import BB3Client
from bb3.replay import decode_replay_data, replay_xml_to_json


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
    root = client.get_competitions(
        size=search_size, start=0, is_official=[True], descending=True
    )
    competition_ids = []
    for competition in root.findall(".//Competition"):
        encoded_id = competition.findtext("Id")
        if not encoded_id:
            continue
        competition_id = base64.b64decode(encoded_id, validate=True).decode("utf-8")
        if competition_id not in competition_ids:
            competition_ids.append(competition_id)

    if not competition_ids:
        raise RuntimeError("No public official competition was found")

    for competition_id in competition_ids:
        progress(f"Searching official competition {competition_id} for replays...")
        games = client.get_games_model(
            size=search_size,
            start=0,
            is_over=[True],
            has_replay=[True],
            competition_ids=[competition_id],
            descending=True,
        )
        game = next((item for item in games.games if item.game_id), None)
        if game is not None:
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
        replay_xml = client.download_replay(
            game.game_id, output_dir=args.output_dir, formats=args.formats
        )

    for replay_format in args.formats:
        path = args.output_dir / f"{game.game_id}.{replay_format}"
        if not path.is_file():
            raise RuntimeError(f"Replay was not saved correctly: {path}")
        if replay_format == "xml" and path.read_bytes() != replay_xml:
            raise RuntimeError(f"Replay XML verification failed: {path}")
        if replay_format == "bbr":
            saved_xml = decode_replay_data(
                path.read_text(encoding="ascii"), redact_ip_addresses=False
            )
            if saved_xml != replay_xml:
                raise RuntimeError(f"Replay BBR verification failed: {path}")
        progress(f"Saved and verified: {path}")
    print(replay_xml_to_json(replay_xml))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
