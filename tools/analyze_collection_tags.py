#!/usr/bin/env python3
"""Analyze BB3 RequestCollectionItems / RequestSetTeam* traffic in all .bin files.

Designed for Wireshark Follow TCP Stream raw exports. The parser is recovery-
oriented because exports can interleave both TCP directions.
"""

from __future__ import annotations

import argparse
import base64
import struct
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


def decode_b64(value: str) -> str:
    if not value:
        return ""
    try:
        raw = base64.b64decode(value, validate=True)
        decoded = raw.decode("utf-8")
        if all(ch.isprintable() or ch in "\r\n\t" for ch in decoded):
            return decoded
    except Exception:
        pass
    return value


def find_next_frame(data: bytes, start: int):
    pos = start
    while True:
        header_start = data.find(b"<Header>", pos)
        if header_start < 0:
            return None
        frame_start = header_start - 4
        if frame_start < 0:
            pos = header_start + 1
            continue
        header_len = struct.unpack_from("<I", data, frame_start)[0]
        if not 20 <= header_len <= 10000:
            pos = header_start + 1
            continue
        header_end = header_start + header_len
        if header_end > len(data):
            return None
        try:
            root = ET.fromstring(data[header_start:header_end].decode("utf-8"))
            node = root.find("Data")
            if node is None or "MessageName" not in node.attrib:
                raise ValueError
            int(node.attrib.get("size", "0"))
        except Exception:
            pos = header_start + 1
            continue
        return frame_start


def parse_frame_header(data: bytes, offset: int):
    if offset + 4 > len(data):
        return None
    header_len = struct.unpack_from("<I", data, offset)[0]
    if not 20 <= header_len <= 10000:
        return None
    start = offset + 4
    end = start + header_len
    if end > len(data):
        return None
    try:
        root = ET.fromstring(data[start:end].decode("utf-8"))
        node = root.find("Data")
        if node is None:
            return None
        return {
            "header_end": end,
            "size": int(node.attrib.get("size", "0")),
            "name": node.attrib.get("MessageName", "?"),
            "mt": node.attrib.get("MessageToken", "-"),
        }
    except Exception:
        return None


def parse_frames(data: bytes, source: str):
    frames = []
    offset = 0
    while offset < len(data):
        info = parse_frame_header(data, offset)
        if info is None:
            nxt = find_next_frame(data, offset + 1)
            if nxt is None:
                break
            offset = nxt
            continue

        declared_end = info["header_end"] + info["size"]
        if declared_end <= len(data) and parse_frame_header(data, declared_end):
            body_end = declared_end
        else:
            nxt = find_next_frame(data, declared_end)
            body_end = nxt if nxt is not None else len(data)

        body = data[info["header_end"]:body_end]
        try:
            root = ET.fromstring(body.decode("utf-8", errors="replace"))
        except Exception:
            root = None
        frames.append({"source": source, "name": info["name"], "mt": info["mt"], "root": root})
        offset = body_end
    return frames


def collection_tags(root):
    if root is None:
        return []
    node = root.find("Tags")
    if node is None:
        return []
    return [decode_b64(x.text) for x in node.findall("TagsItem") if x.text]


def find_next_setter(frames, index, max_distance=8):
    source = frames[index]["source"]
    for next_index in range(index + 1, min(len(frames), index + max_distance + 1)):
        frame = frames[next_index]
        if frame["source"] != source:
            break
        name = frame["name"]
        if name.startswith("RequestSetTeam"):
            return name
        if name == "RequestCollectionItems":
            break
    return None


def extract_setter_values(frame):
    root = frame["root"]
    if root is None:
        return None
    team_id = root.findtext("IdTeam")
    result = {"team_id": decode_b64(team_id) if team_id else None, "field": None, "item_id": None}
    for child in root:
        if child.tag.startswith("Id") and child.tag != "IdTeam" and child.text:
            result["field"] = child.tag
            result["item_id"] = decode_b64(child.text)
            break
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", nargs="?", default=".", help="Directory containing .bin files")
    args = ap.parse_args()

    paths = sorted(Path(args.directory).glob("*.bin"))
    if not paths:
        raise SystemExit("No .bin files found.")

    frames = []
    for path in paths:
        parsed = parse_frames(path.read_bytes(), path.name)
        frames.extend(parsed)
        print(f"{path.name:<45} {len(parsed):>5} frames")

    tags_seen = Counter()
    relationships = defaultdict(set)

    print("\nCOLLECTION TAGS\n" + "=" * 100)
    for index, frame in enumerate(frames):
        if frame["name"] != "RequestCollectionItems":
            continue
        tags = collection_tags(frame["root"])
        setter = find_next_setter(frames, index)
        token = frame["root"].findtext("Token", "-") if frame["root"] is not None else "?"
        for tag in tags:
            tags_seen[tag] += 1
            if setter:
                relationships[tag].add(setter)
            print(f"{frame['source']} frame={index:03d} MT={frame['mt']} Token={token}\n  Tag     : {tag}")
            if setter:
                print(f"  Setter  : {setter}")

    print("\nUNIQUE TAGS\n" + "=" * 100)
    for tag, count in sorted(tags_seen.items()):
        print(f"{tag:<45} seen={count}")

    print("\nTAG -> SETTER MAPPING\n" + "=" * 100)
    for tag in sorted(relationships):
        print(f"{tag:<45} -> {', '.join(sorted(relationships[tag]))}")

    print("\nCOSMETIC SETTERS\n" + "=" * 100)
    for index, frame in enumerate(frames):
        if not frame["name"].startswith("RequestSetTeam") or frame["name"] in {
            "RequestSetTeamName", "RequestSetTeamMotto"
        }:
            continue
        values = extract_setter_values(frame)
        print(f"\n{frame['source']} frame={index:03d} MT={frame['mt']} {frame['name']}")
        if values:
            print(f"  Team    : {values['team_id']}")
            print(f"  Field   : {values['field']}")
            print(f"  Item ID : {values['item_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
