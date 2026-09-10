# Replay pipeline

Replay networking, transformation, anonymization and storage are deliberately
separate operations.

```python
replay = client.download_replay(game_id)
anonymous = replay.redact_ip_addresses()

anonymous.save("replays/game.bbr")
anonymous.save("replays/game.xml")
anonymous.save("replays/game.json")
```

`download_replay()` returns a `Replay` backed by the untouched `ReplayData`
string received from the server and never writes to disk. `replay.bbr_data`
therefore returns the exact server value until a transformed replay is created.
A response without `ReplayData` raises `ReplayNotFoundError`.

`Replay` can also be created with `Replay.from_xml()` or `Replay.from_json()`.
Its `bbr_data`, `xml_data` and `json_data` properties convert lazily and cache
the result. `redact_ip_addresses()` returns a new XML-backed object, leaving the
source object untouched; that new object is only encoded if BBR is requested.

`decode_replay()` transforms double-Base64/zlib BBR data to XML.
`encode_replay()` performs the inverse transformation. Neither function
anonymizes or writes data.

`redact_replay_ip_addresses()` accepts XML and replaces participant addresses
with stable RFC 5737 documentation addresses in memory.

`save_replay(data, filename)` uses the destination extension:

- `.bbr` writes double-Base64/zlib data
- `.xml` writes decoded XML
- `.json` writes the JSON representation
- every other extension preserves the supplied bytes or text

The three recognized representations can be converted between one another.

## Discovery helpers

```python
competitions = client.list_official_competitions()
matches = client.list_matches(competition_id)  # latest 10
matches = client.list_matches(competition_id, limit=50)
```

`list_official_competitions()` returns `(name, competition_id)` pairs.
`list_matches()` returns `GameData` objects newest first and supports `start`,
`completed` and `has_replay` filters.

`tools/download_any_replay.py` composes these primitives into the complete
download, decode, anonymize and save example. `tools/replay_ips.py` reads BBR,
XML or JSON and prints the decoded IP values.
