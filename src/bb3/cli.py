from __future__ import annotations

import argparse
from pathlib import Path

from .client import BB3Client
from .constants import DEFAULT_CLIENT_VERSION


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--helper",
        help="Path to BB3SteamAuth (auto-detected by default)",
    )
    parser.add_argument("--host", help="Debug override; default uses bootstrap discovery")
    parser.add_argument("--port", type=int, help="Debug override; default uses bootstrap discovery")
    parser.add_argument("--client-version", default=DEFAULT_CLIENT_VERSION)


def authenticated_client(args):
    client = BB3Client.from_steam(
        helper=args.helper,
        host=args.host,
        port=args.port,
        client_version=args.client_version,
    )
    try:
        client.__enter__()
        client.login()
    except Exception:
        client.close()
        raise
    return client


def cmd_replay(args) -> int:
    client = authenticated_client(args)
    try:
        xml = client.download_replay(args.game_id)
        Path(args.output).write_bytes(xml)
        print(args.output)
        return 0
    finally:
        client.close()


def cmd_team_get(args) -> int:
    client = authenticated_client(args)
    try:
        root = client.get_team(args.team_id)
        import xml.etree.ElementTree as ET
        print(ET.tostring(root, encoding="unicode"))
        return 0
    finally:
        client.close()


def cmd_team_create(args) -> int:
    client = authenticated_client(args)
    try:
        team_id = client.create_team(args.name, args.race)
        print(team_id)
        return 0
    finally:
        client.close()


def cmd_player_hire(args) -> int:
    client = authenticated_client(args)
    try:
        player_id = client.hire_player_from_position(
            args.team_id,
            args.position,
        )
        print(player_id)
        return 0
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(prog="bb3")
    sub = parser.add_subparsers(dest="command", required=True)

    replay = sub.add_parser("replay")
    replay.add_argument("game_id")
    replay.add_argument("--output", default="replay.xml")
    add_connection_args(replay)
    replay.set_defaults(func=cmd_replay)

    team = sub.add_parser("team-get")
    team.add_argument("team_id")
    add_connection_args(team)
    team.set_defaults(func=cmd_team_get)

    create = sub.add_parser("team-create")
    create.add_argument("name")
    create.add_argument("--race", type=int, required=True)
    add_connection_args(create)
    create.set_defaults(func=cmd_team_create)

    hire = sub.add_parser("player-hire")
    hire.add_argument("team_id")
    hire.add_argument("position", type=int)
    add_connection_args(hire)
    hire.set_defaults(func=cmd_player_hire)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
