# pybb3

Unofficial headless Python client for the Blood Bowl 3 backend protocol, based
on observed traffic from the legitimate game client.

> Reverse-engineering project. Not affiliated with Cyanide, Nacon,
> Games Workshop or Valve.

The backend protocol is undocumented and may change without notice.
Some methods modify live account/team data.

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

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e '.[test]'
pytest
```

Live tests require `PYBB3_RUN_LIVE_TESTS=1`. Destructive account mutations must
also require `PYBB3_ALLOW_DESTRUCTIVE_TESTS=1`.

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

The highest-priority remaining captures are `GetGames` and `GetGameResult`, then
structured `MatchResult`, redraft and journeymen.
