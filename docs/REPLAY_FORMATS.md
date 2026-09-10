# Replay download formats

`BB3Client.download_replay(game_id)` returns decoded replay XML in memory and
redacts participant IP addresses by default.

Pass `output_dir` to save the replay. All representations are saved by default:

```python
replay_xml = client.download_replay(game_id, output_dir="replays")
```

- `GAME_ID.bbr`: redacted XML repacked as zlib, Base64, then Base64 again
- `GAME_ID.xml`: redacted decoded XML
- `GAME_ID.json`: JSON converted from the redacted XML

Select a subset with `formats`:

```python
client.download_replay(
    game_id,
    output_dir="replays",
    formats=("bbr", "json"),
)
```

The `tools/download_any_replay.py` script owns the example policy for finding a
replay in a public official competition. It accepts the same format selection:

```bash
tools/download_any_replay.py --formats bbr xml json
tools/download_any_replay.py --formats bbr json
```

Its JSON output is written to stdout and progress is written to stderr.

Extract redacted IP addresses from any saved representation with:

```bash
tools/replay_ips.py replays/GAME_ID.bbr
tools/replay_ips.py replays/GAME_ID.xml
tools/replay_ips.py replays/GAME_ID.json
```

The `.bbr` representation is produced only after IP redaction. Decoding a saved
`.bbr` therefore yields the same bytes as the corresponding saved `.xml` file.
