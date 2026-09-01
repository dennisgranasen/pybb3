# pybb3

Unofficial headless Python client for the Blood Bowl 3 backend protocol, based
on observed traffic from the legitimate game client.

> Reverse-engineering project. Not affiliated with Cyanide, Nacon,
> Games Workshop or Valve.

## Current status

Capture-verified or end-to-end verified:

- BB3 TCP framing and XML request/response handling
- headless Steam authentication through a SteamKit2 helper
- BB3 login
- dynamic Cyanide backend discovery
- replay download/decode
- team creation, listing and roster retrieval
- player hire/fire/rename
- player advancement: options, random/chosen skill and characteristic roll/choice
- team deletion protocol
- team improvements
- team name/motto
- cosmetic setters and collection tags
- formations
- optional loading/querying of local `BB3Rules.json`
- capture-analysis tooling

The latest roster capture distinguishes roster-position templates in
`RaceRoster` from actual hired players in `TeamRoster`. The client preserves raw
XML alongside structured runtime models.

Full structured roster parsing also awaits a sanitized real
`ResponseGetTeamRoster`; the client deliberately does not guess unknown field
names or enum meanings.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e '.[test]'
pytest
```

Install test dependencies and run the offline suite with:

```bash
pip install -e '.[test]'
pytest
```

Live tests are skipped unless `PYBB3_RUN_LIVE_TESTS=1` is set. Tests that
mutate account state additionally require
`PYBB3_ALLOW_DESTRUCTIVE_TESTS=1`.

Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Steam authentication

BB3 Steam AppID is `1016950`.

```python
from bb3 import BB3Client

with BB3Client.from_steam() as client:
    client.login()
```

The ignored Steam auth cache may contain a persistent refresh token. Never
commit passwords, Guard data, refresh tokens, Steam tickets or BB3 AuthTokens.

BB3 AuthToken transformation:

```text
raw Steam ticket bytes
-> uppercase hexadecimal ASCII
-> Base64
```

## Dynamic backend discovery

Do not hardcode the application server. `BB3Client` uses the Cyanide bootstrap
service and connects to the returned `tcp://host:port`.

## Team roster

The captured request uses `IdTeam`:

```python
root = client.get_team_roster(team_id)
roster = client.get_team_roster_model(team_id)

for player in roster.players:
    print(player.name, player.spp, player.skill_ids)
```

`roster.positions` contains position-template data from `RaceRoster`;
`roster.players` contains current hired players from `TeamRoster`.

## Player advancement

```python
options = client.get_player_improvements(player_id)

for category in options.skill_categories:
    print(category.category, category.affinity, category.cost_random)
```

Do not hardcode SPP costs; the backend returns current costs.

Random skill:

```python
result = client.add_player_random_skill(player_id, category=1)
print(result.skill_id, result.has_left)
```

Chosen primary and secondary skills use the same endpoint:

```python
client.add_player_skill(player_id, skill_id=38)
```

Characteristic advancement is a two-step server-side flow:

```python
roll = client.begin_increase_player_characteristic(player_id)
print(roll.roll)
print(roll.can_take_secondary_skill)

for option in roll.characteristics:
    print(option.characteristic_id, option.available, option.team_value)

client.choose_increase_player_characteristic(player_id, characteristic_id=2)
```

The characteristic begin request performs the roll; `Available` is determined
by the result for a normal team. Custom teams can expose all characteristics and
should not be used to infer normal roll availability.

## Delete team

The exact request body is now capture-verified and implemented:

```python
client.delete_team(team_id)
```

Treat this as destructive. Automated live tests should remain explicit opt-in.

## External BB3 rules data

Use the game-shipped modern `BB3Rules.json`. `BB3Rules.skill_by_code()` maps
protocol `Skill` IDs to semantic static rules; for example the captured random
`Skill=8` resolves to `sprint`.

Runtime/backend state and static game rules remain separate layers.

## Replays

```text
ReplayData -> Base64 -> Base64 -> zlib -> XML
```

## Next protocol targets

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

Typed position views retain raw data while exposing common relationships:

```python
position = rules.position_by_code(1102)
print(position.characteristics)
print(position.skills)
print(position.record)
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

Reconstruct TCP directions independently from pcap or pcapng:

```bash
python tools/parse_pcap.py capture.pcapng --port 17010 --output-prefix bb3-stream
```

The pcap parser handles Ethernet or raw-IP IPv4/IPv6 TCP, separates both
directions, removes retransmitted overlap and splits streams at sequence gaps.
Written stream chunks are redacted with length-preserving replacements so BB3
frame offsets remain usable without persisting labelled credentials.

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
