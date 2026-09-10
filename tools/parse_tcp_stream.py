#!/usr/bin/env python3
"""
Recovery-oriented parser for Wireshark Follow TCP Stream raw exports.

Important: Follow TCP Stream output can interleave the two TCP directions,
which means a frame body may be interrupted by a frame from the opposite
direction. This parser is intended for reverse-engineering captures, not for
live protocol handling.
"""

import argparse
import struct
import xml.etree.ElementTree as ET
from pathlib import Path


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
        raw = data[header_start:header_end]
        try:
            root = ET.fromstring(raw.decode("utf-8"))
            d = root.find("Data")
            if d is None or "MessageName" not in d.attrib:
                raise ValueError
            int(d.attrib.get("size", "0"))
        except Exception:
            pos = header_start + 1
            continue
        return frame_start


def frame_header(data: bytes, offset: int):
    if offset + 4 > len(data):
        return None
    header_len = struct.unpack_from("<I", data, offset)[0]
    if not 20 <= header_len <= 10000:
        return None
    start = offset + 4
    end = start + header_len
    try:
        root = ET.fromstring(data[start:end].decode("utf-8"))
        d = root.find("Data")
        if d is None:
            return None
        return {
            "header_end": end,
            "size": int(d.attrib.get("size", "0")),
            "name": d.attrib.get("MessageName", "?"),
            "mt": d.attrib.get("MessageToken", "-"),
            "zipped": d.attrib.get("zipped", "?"),
        }
    except Exception:
        return None


def token_from_body(body: bytes):
    try:
        root = ET.fromstring(body.decode("utf-8", errors="replace"))
        return root.findtext("Token") or "-"
    except Exception:
        return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    args = ap.parse_args()

    data = Path(args.file).read_bytes()
    offset = 0
    n = 0

    while offset < len(data):
        info = frame_header(data, offset)
        if info is None:
            nxt = find_next_frame(data, offset + 1)
            if nxt is None:
                break
            print(f"[!] desync {offset} -> {nxt}")
            offset = nxt
            continue

        declared_end = info["header_end"] + info["size"]
        next_info = frame_header(data, declared_end) if declared_end < len(data) else None

        if next_info:
            actual_end = declared_end
            warning = ""
        else:
            nxt = find_next_frame(data, declared_end)
            actual_end = nxt if nxt is not None else len(data)
            actual_size = actual_end - info["header_end"]
            delta = actual_size - info["size"]
            warning = (
                f" [size mismatch: declared={info['size']}, "
                f"actual={actual_size}, delta={delta:+}]"
                if nxt is not None else ""
            )

        body = data[info["header_end"]:actual_end]
        token = token_from_body(body)
        print(
            f"{n:03d} offset={offset:<8} "
            f"MessageName={info['name']:<35} "
            f"MT={info['mt']:<4} Token={token:<4} "
            f"size={info['size']:<7} zipped={info['zipped']}{warning}"
        )
        n += 1
        offset = actual_end


if __name__ == "__main__":
    main()
