# pybb3

Unofficial headless Python client for the Blood Bowl 3 backend protocol, based
on observed traffic from the legitimate game client.

> Reverse-engineering project. Not affiliated with Cyanide, Nacon, Slytherine,
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
- game listing, structured game results and decoded match statistics
- team creation, listing and roster retrieval
- league creation, lookup, members and permissions
- competition creation, discovery, participants and captured admin settings
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

Requires Python 3.11 or newer. Steam authentication uses the included
SteamKit2 helper, which targets .NET 10; install the .NET 10 SDK to run it
directly from this checkout. Run the commands below from the `pybb3` directory.

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For development and offline tests:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Live tests require `PYBB3_RUN_LIVE_TESTS=1`. Destructive tests additionally
require `PYBB3_ALLOW_DESTRUCTIVE_TESTS=1`.

## Steam authentication

BB3 Steam AppID is `1016950`.

From a source checkout, the client automatically runs the helper with
`dotnet run`. To use a built executable, pass `helper="/path/to/BB3SteamAuth"`
to `BB3Client.from_steam()` or set `BB3_STEAM_HELPER` to its executable path.

Credentials are resolved from environment variables, then a local `.env`,
then interactive prompts. Use `.env.example` as a template for
`STEAM_USERNAME` and optional game-data paths; leave the password unset to
enter it interactively. Complete any Steam Guard challenge when prompted.

```python
from bb3 import BB3Client

with BB3Client.from_steam() as client:
    client.login()
```

The default ignored Steam auth cache, `.bb3-steam-auth.json`, may contain a
persistent refresh token. Never
commit passwords, Guard data, refresh tokens, Steam tickets or BB3 AuthTokens.

## Command-line usage

The editable install provides the `bb3` command. Each command authenticates,
logs in and closes its session on completion.

```bash
bb3 --help
bb3 team-get TEAM_ID
bb3 replay GAME_ID --output replay.xml
```

The following commands modify the account: creating a team and hiring a player
using a roster-position ID, respectively.

```bash
bb3 team-create "My team" --race RACE_ID
bb3 player-hire TEAM_ID POSITION_ID
```

Replace uppercase placeholders with actual IDs; race and position IDs must be
integers. Each subcommand accepts `--helper` for an executable path and
`--client-version`. `--host` and `--port` are debugging overrides; normal use
relies on backend discovery. Use `bb3 COMMAND --help` for command options.

## Service integration

### Web and multi-user authentication

Services must keep one `SteamWebAuthFlow` per pending user login. The flow
starts the Steam helper in JSON-lines mode and returns either a Guard challenge
or an isolated `SteamAuthState`:

```python
from bb3 import SteamAuthState, SteamGuardChallenge, SteamWebAuthFlow

flow = SteamWebAuthFlow(helper="/app/steam-helper/BB3SteamAuth")
result = flow.start(username, password)

if isinstance(result, SteamGuardChallenge):
    if result.method in {"device_code", "email_code"}:
        result = flow.submit_code(code_from_user)
    elif result.method == "device_confirmation":
        result = flow.confirm_device()
```

The hosting service owns challenge IDs, user binding, expiry and rate limits.
Never select a flow using only a caller-supplied token: verify that the
authenticated application user owns it. Passwords are only needed by
`SteamWebAuthFlow.start()` and must not be stored or logged. Web credentials
are sent to the helper over stdin rather than exposed in its process environment.

After authentication, construct a separate ticket process and `BB3Client` for
each active session without using the shared CLI cache:

```python
from bb3 import BB3Client, SteamAuthProcess

steam_auth = SteamAuthProcess.from_state(result, helper="/app/steam-helper/BB3SteamAuth")
client = BB3Client(steam_auth=steam_auth)
client.__enter__()
client.login()
```

`BB3Client` is stateful and not thread-safe. A service must serialize calls for
each client with a per-session lock or request queue. Different clients may be
used concurrently. Always close the client on logout, expiry and shutdown.

BB3 AuthToken transformation:

```text
raw Steam ticket bytes
-> uppercase hexadecimal ASCII
-> Base64
```

## Dynamic backend discovery

Do not hardcode the application server. `BB3Client` uses the Cyanide bootstrap
service and connects to the returned `tcp://host:port`.

## Leagues and competitions

The 2026-09-01 capture added verified league creation/lookup and competition
administration. Destructive mutations are explicit client calls:

```python
from bb3 import AdmissionMode, BB3Client, CompetitionFormat, TimerId

league = client.create_league_model("My league", logo_id=logo_id)
competition = client.create_competition_model(
    "Autumn Wissen",
    league.league_id,
    format=CompetitionFormat.WISSEN,
    participants_number_max=16,
    timer_id=TimerId.UNLIMITED,
    admission_mode=AdmissionMode.TICKETS,
)

client.set_allow_experienced_teams(competition.setting_id, True)
client.set_enable_match_consequences(competition.setting_id, True)
```

See [`docs/ENUMS.md`](docs/ENUMS.md) for verified numeric meanings and values
that deliberately remain unnamed.

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

`download_replay()` returns decoded XML bytes. Participant `IpAddress` fields
are Base64-encoded inside the XML; they are replaced in memory with stable RFC
5737 documentation addresses (`192.0.2.x`) before the bytes are returned:

```python
from pathlib import Path

with BB3Client.from_steam() as client:
    client.login()
    Path("replay.xml").write_bytes(client.download_replay(game_id))
```

Distinct source addresses remain distinguishable within one replay, but the
temporary mapping and original values are not retained. For private diagnostic
use only, redaction can be explicitly disabled with
`download_replay(game_id, redact_ip_addresses=False)` or the CLI flag
`--keep-ip-addresses`.

The wire encoding is:

```text
ReplayData -> Base64 -> Base64 -> zlib -> XML -> redact IpAddress in memory
```

### Live replay smoke script

The script below logs in, searches for any completed game with a replay,
downloads it with IP redaction enabled, verifies the saved `.bbr`, saves a JSON
copy and writes the complete JSON to stdout. Progress messages go to stderr, so
stdout remains pipe-friendly:

```bash
python tools/download_any_replay.py --output-dir replays
python tools/download_any_replay.py 2>download.log | jq .
```

The helper first discovers public official competitions, then searches those
competitions for a completed match with a replay. Progress is written to stderr,
while stdout contains only the complete replay JSON and remains safe to pipe.

Extract and Base64-decode only the `IpAddress` values from either saved format:

```bash
python tools/replay_ips.py replays/GAME_ID.bbr
python tools/replay_ips.py replays/GAME_ID.json
cat replays/GAME_ID.json | python tools/replay_ips.py -
```

Run the read-only live verification explicitly:

```bash
PYBB3_RUN_LIVE_TESTS=1 pytest -q tests/test_live_replay_redaction.py
```

The live test downloads a real replay into pytest's temporary directory and
asserts that every decoded `IpAddress` is one of the RFC 5737 values inserted by
the in-memory download redaction step.

## Games, results and statistics

Within an authenticated client session:

```python
games = client.get_games_model()
result = client.get_game_result_model(game_id)
statistics = client.get_match_statistics_model(match_id)
schedule = client.get_competition_schedule_model(competition_id, day)
```

Game IDs and match IDs are distinct endpoint inputs. Structured models preserve
raw XML, and statistics decode the server-provided category, name and value
fields. Corresponding methods without `_model` return protocol XML for these
endpoints. Numeric filter and status values are only named where verified.

## Documentation

- [Protocol reference](docs/PROTOCOL.md): framing and captured request semantics.
- [Enums](docs/ENUMS.md): verified numeric values and unresolved meanings.
- [Data sources](docs/DATA_SOURCES.md): local game archives and static rules.
- [Backlog](BACKLOG.md): implementation status and remaining research.

## Next protocol targets

The highest-priority remaining captures are redraft and journeymen, followed by
labels for unresolved competition status, contest-format and timer values.

## Support

If pybb3 is useful to you, you can support its development:

<a href="https://www.buymeacoffee.com/d.rock"><img src="https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee!&amp;emoji=&amp;slug=d.rock&amp;button_colour=40DCA5&amp;font_colour=ffffff&amp;font_family=Bree&amp;outline_colour=000000&amp;coffee_colour=FFDD00" alt="Buy me a coffee!" /></a>
