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

Create a `.env` file in the directory where you run the client:

```dotenv
STEAM_USERNAME=my_steam_login_name
# STEAM_PASSWORD=
```

`STEAM_USERNAME` is the Steam account **login name**, not a SteamID64. The
password is optional and is best omitted: Python prompts without echoing it only
when cached Steam authentication is unavailable. Environment variables override
values in `.env`. A first login may also require Steam Guard interaction.

The ignored `.bb3-steam-auth.json` file stores the persistent Steam refresh
token and Guard state. Later runs normally reuse it without asking for a
password. The short-lived BB3 AuthToken is never stored there. Never commit
passwords, Steam Guard data, refresh tokens, Steam tickets, or BB3 auth tokens.

```python
from bb3 import BB3Client

with BB3Client.from_steam() as client:
    client.login()
    team_id = client.create_team(name="pybb3 Test", race_id=7)
    print(team_id)
```

Race `7` is Wood Elf. The helper remains connected while the client context is
open and is cleaned up on normal exit or exceptions.

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
bb3 replay GAME_UUID --output replay.xml
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

For archive and static-data APIs, the recommended configuration is the Blood
Bowl 3 installation root in `.env`:

```dotenv
BB3_PATH=C:\Program Files (x86)\Steam\steamapps\common\Blood Bowl 3
```

This resolves `BB3/Content/OfflineServer/bb3rulesengine.zip` and
`BB3/Content/OfflineServer/bb3.zip` beneath the installation. Advanced setups
can override either archive independently; any archive without an override
continues to resolve through `BB3_PATH`:

```dotenv
# BB3_RULES_ENGINE_ZIP=C:\path\to\bb3rulesengine.zip
# BB3_DATA_ZIP=C:\path\to\bb3.zip
```

Real environment variables override `.env` values. Resolve and validate the
configured archives with:

```python
from bb3 import BB3Data

data = BB3Data.from_env()
```

Point the client at your local copy:

```bash
export BB3_RULES_FILE=/path/to/BB3Rules.json
```

or load it directly:

```python
from bb3 import BB3Rules

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
