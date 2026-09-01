# bb3-client

Unofficial headless Python client for the Blood Bowl 3 backend protocol, based on observed traffic from the legitimate game client.

> Reverse-engineering project. Not affiliated with Cyanide, Nacon, Games Workshop or Valve.

## Current status

Capture-verified or end-to-end verified:

- BB3 TCP framing and XML request/response handling
- headless Steam authentication through a SteamKit2 helper
- BB3 login
- dynamic Cyanide backend discovery through the bootstrap service
- replay download and decode
- team creation
- player hire/fire/rename
- team improvements
- team name and motto
- team cosmetic setters and collection discovery tags
- team formations
- optional loading/querying of the game's local `BB3Rules.json`
- recovery-oriented analysis tools for Wireshark Follow TCP Stream exports

Some methods intentionally remain unimplemented where the exact request body has not yet been captured (notably team deletion).

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Steam authentication

BB3 Steam AppID is `1016950`.

The helper in `steam-helper/` uses SteamKit2. Build it with:

```bash
dotnet build steam-helper/BB3SteamAuth.csproj
```

One-time bootstrap:

```bash
BB3SteamAuth bootstrap
```

For persistent headless use, provide `STEAM_USERNAME` and `STEAM_REFRESH_TOKEN` securely. Never commit passwords, Steam Guard data, refresh tokens or BB3 auth tokens.

BB3 expects the Steam ticket as:

```text
raw Steam ticket bytes
-> uppercase hexadecimal ASCII
-> Base64
```

The helper stays connected to Steam while the Python process uses the ticket.

## Dynamic backend discovery

The application server is **not** a fixed IP/port. The retail client was observed calling:

```http
GET /lobby/bb3-win-steam-shipping-57968 HTTP/1.1
Host: bootstrap6-bb3.cyanide-studio.com:28006
```

with a response such as:

```text
tcp://app18.bb3.cyanide-studio.com:17010
```

`BB3Client` performs this discovery automatically when `host` and `port` are omitted. CLI `--host` and `--port` remain available as debug overrides.

## Replays

```bash
bb3 replay GAME_UUID --helper /path/to/BB3SteamAuth --output replay.xml
```

Replay payload decoding:

```text
ReplayData
-> Base64 decode
-> Base64 decode
-> zlib decompress
-> Replay XML
```

## External BB3 rules data

The game ships a useful rules database in its own data files, for example under an `OfflineServer/bb3rulesengine` directory. This repository does **not** redistribute that file.

Point the client at your local copy:

```bash
export BB3_RULES_FILE=/path/to/BB3Rules.json
```

or load it directly:

```python
from bb3_client import BB3Rules

rules = BB3Rules.load("/path/to/BB3Rules.json")
wardancer = rules.position_by_code(1102)
print(wardancer.name)
print(rules.position_characteristics(wardancer.name))
print(rules.position_skills(wardancer.name))
print(rules.sha256)
```

The file contains rule definitions such as races, positions, characteristics, skills, skill-category affinities, roster definitions, special rules, casualties, inducements and team improvements. Runtime/backend state remains separate from these static definitions.

`BB3Rules.json` and `bb3rulesengine/` are ignored by Git.

## Team cosmetics

Verified collection tags:

| Slot | Collection tag | Setter |
|---|---|---|
| Jersey pattern | `TeamCustoJerseyPattern` | `RequestSetTeamJerseyPattern` |
| Colors | `TeamCustoColor` | primary/secondary/tertiary color setters |
| Cheerleader | `TeamCustoCheerleader` | `RequestSetTeamCheerleader` |
| Coach | `TeamCustoCoach` | `RequestSetTeamCoach` |
| Pitch | `TeamCustoPitch` | `RequestSetTeamPitch` |
| Stadium | `TeamCustoStadium` | `RequestSetTeamStadium` |
| Coach zone | `TeamCustoCoachZone` | `RequestSetTeamCoachZone` |
| Staff zone | `TeamCustoStaffZone` | `RequestSetTeamStaffZone` |
| Cheerleader zone | `TeamCustoCheerleaderZone` | `RequestSetTeamCheerleaderZone` |
| Dice | `TeamCustoDice` | `RequestSetTeamDice` |
| Ball | `TeamCustoBall` | `RequestSetTeamBall` |

Logo/emblem discovery/setter and the exact collection `Item` vs `Instance` ID semantics are still open reverse-engineering items.

## Team improvements

Captured `RequestUpdateTeamImprovements` uses a **signed delta** in `Quantity`, not an absolute quantity. The standard IDs observed are 1–5; when available, prefer resolving rule IDs through the local `BB3Rules.json` instead of duplicating game rules in application code.

## Formations

Captured formation types:

| Type | Meaning |
|---:|---|
| 0 | Defensive |
| 1 | Offensive |

Formation `Data` is Base64-encoded JSON containing a `pitchMap`.

## Capture tools

List/recover BB3 frames from a raw Follow TCP Stream export:

```bash
python tools/parse_tcp_stream.py stream.bin
```

Analyze collection tags and cosmetic setters across **all `.bin` files in a directory**:

```bash
python tools/analyze_collection_tags.py .
```

## Known gaps

- exact `RequestDeleteTeam` body
- typed `ResponseGetTeamRoster`/`ResponseGetRoster` models
- game discovery (`GetGames` -> result -> replay) as a high-level API
- logo/emblem setter and discovery tag
- collection item vs item-instance ID semantics for cosmetics
- level-up/skills write API
- journeymen/redraft workflows
- long-lived async event dispatcher/reconnect semantics
- replay semantic event/enumeration layer
