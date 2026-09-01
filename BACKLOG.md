# pybb3 Backlog

This document tracks reverse-engineering and implementation work for `pybb3`.

Status: `DONE`, `PARTIAL`, `TODO`, `RESEARCH`, `BLOCKED`.
Priority: `P0` core, `P1` important, `P2` useful, `P3` optional.

# 1. Authentication and connection

## DONE — Steam authentication
SteamKit2 helper, AppID `1016950`, ticket -> uppercase HEX ASCII -> Base64,
Windows/Linux verified. Never log passwords, refresh tokens, tickets or BB3
AuthTokens.

## DONE — Environment configuration
Environment -> `.env` -> interactive prompt. `STEAM_USERNAME` is the login
name. Password should normally be prompted securely rather than persisted.

## DONE — Dynamic backend discovery
Use the bootstrap-returned `tcp://host:port`; never hardcode app servers.

## PARTIAL — Session lifecycle
Still research explicit logout (if any), abandoned-session timeout and immediate
relogin after a clean close.

# 2. Protocol core

## DONE — Framing, token handling and startup
Framing, separate transport/body counters, keepalive behavior and initial
status/config/login sequence are implemented.

## DONE — Structured server exceptions
Successful responses do not universally contain `<Result>`. Direct
`<Exception>` and wrapped `<Exceptions>` are supported; `Result=0` is failure.

# 3. Team management

## DONE — Create team
Verified live on Windows and Linux.

## PARTIAL — Get team / roster
Priority: `P0`

Protocol is now **VERIFIED**. `RequestGetTeamRoster` uses `<IdTeam>`, not
`<TeamId>`. A complete real response has been captured.

Implemented in this update:
- corrected request field
- structured parser that keeps `RaceRoster` templates separate from actual
  `TeamRoster` players
- player IDs/names/position/skills/SPP/level-up status/current characteristics
- roster-position cost/max/base skills/base characteristics/skill categories
- rosterized inducements
- raw XML preserved alongside semantic models

Remaining:
- map runtime casualty IDs to static casualty rules
- verify every currently unmodeled roster field
- verify exact meaning of outer `TeamRosterSlot/Number` vs inner `Player/Number`
- add treasury/improvement state once its canonical source in the team responses
  is pinned down

## DONE — Hire / rename / fire player
Known requests implemented.

## RESEARCH — Temporary retirement
Verify live semantics of `TemporarilyRetire=true`.

## PARTIAL — Delete team
Priority: `P1`

Protocol is now **VERIFIED**:

```xml
<RequestDeleteTeam><IdTeam>BASE64(team UUID)</IdTeam></RequestDeleteTeam>
```

Implementation is included in this update. Live destructive tests must remain
explicit opt-in.

## DONE — Team improvements
Signed `Quantity` delta, IDs 1-5 confirmed in modern static rules.

## PARTIAL — Team listing
`RequestGetTeamsOfGamer -> ResponseGetTeams` and
`RequestGetTeamsCompetitions -> ResponseGetTeamsCompetitions` are capture
verified and thin client methods are included. Structured team-list models can
follow after representative sanitized fixtures are added.

# 4. Player advancement

## PARTIAL — Player level-ups
Priority: `P0`

The normal advancement protocol is now sufficiently captured for implementation.

### VERIFIED
- `RequestGetPlayerImprovements`
- server-provided SPP costs / team values / availability / choosability
- `RequestAddPlayerRandomSkill`
- random response returns actual `Skill` ID and `HasLeft`
- `RequestAddPlayerSkill` for chosen primary
- the same `RequestAddPlayerSkill` for chosen secondary
- `RequestBeginIncreasePlayerCharacteristic`
- server-side characteristic roll and returned available characteristic list
- `CanTakeSecondarySkill`
- `RequestChooseIncreasePlayerCharacteristic`

Important semantics:
- never hardcode SPP costs; current costs come from the server
- `IdPlayer` is used by skill endpoints
- `PlayerId` is used by characteristic begin/choose endpoints
- normal characteristic availability is determined by the roll
- custom teams may expose all characteristics; do not use that capture as
  ordinary advancement behavior

Implemented in this update:
- read-only improvement model
- chosen/random skill methods
- characteristic begin/choose methods
- `CharacteristicRoll`/`CharacteristicUpgrade` models
- fixture-based tests

Remaining edge-case research:
- a normal-team capture with `CanTakeSecondarySkill=1`
- duplicate-skill rejection behavior
- characteristic maximum/invalid-choice errors
- explicit live destructive tests behind opt-in flags

# 5. Match and game discovery

## TODO — GetGames
Priority: `P0`
This is now the highest-value protocol capture target.

## TODO — GetGameResult
Priority: `P0`

Desired flow:
`GetGames -> GetGameResult -> DownloadReplay`.

## DONE — Replay download
Double Base64 + zlib decode is implemented.

## TODO — Structured MatchResult
Priority: `P0`
Canonical semantic result: teams, coaches, score, TDs, casualties, winnings,
SPP/MVP/player results, competition/timestamps/status/concession/disconnect.

## TODO — Replay semantic event API
Priority: `P1`

# 6. Formations

Retrieve/save/remove are implemented. Player-number semantics and update-vs-
create behavior remain research items.

# 7. Team customization / cosmetics

Setters are largely verified. Collection `Item.Id` vs `Instance.Id` semantics
and logo/emblem remain research items.

# 8. Static rules/data

Modern `bb3rulesengine.zip/Datas/BB3Rules.json` is authoritative. Do not merge
legacy `Rules.json` destructively.

Typed `PositionRule`, `RaceRule`, `SkillRule` and `TeamImprovementRule` already
exist. `BB3Rules.skill_by_code()` should be used to map advancement `Skill` IDs
instead of maintaining a duplicate hardcoded map.

# 9. Casualties and injuries

Modern casualty definitions are available. Runtime roster/match injury IDs still
need to be mapped automatically to static rules.

# 10. Redraft / journeymen

Both remain `RESEARCH` (`P1`) and require live protocol captures.

# 11. Capture tooling

pcap/pcapng half-stream reconstruction and redaction are partially implemented.
Continue improving real-capture verification, sequence-wraparound handling and
direct request/response correlation.

# 12. Testing

Live tests require `PYBB3_RUN_LIVE_TESTS=1`. Destructive tests additionally
require `PYBB3_ALLOW_DESTRUCTIVE_TESTS=1`.

Golden sanitized fixtures should include roster, player improvements,
characteristic roll, delete-team response, game listing and game result.

# 13. Immediate priorities

## P0
1. land/verify player advancement API
2. `GetGames`
3. `GetGameResult`
4. structured `MatchResult`

## P1
5. graceful session lifecycle/logout
6. collection-item ID semantics
7. runtime injury mapping
8. redraft
9. journeymen
10. event dispatcher
11. reconnect behavior
12. pcap reconstruction improvements

# 14. Codex working rules

1. Read this backlog first.
2. Inspect existing implementation before creating parallel abstractions.
3. Extend existing APIs rather than duplicating them.
4. Do not assume all responses contain `<Result>`.
5. Preserve raw protocol/data alongside semantic abstractions.
6. Never invent protocol fields or enum meanings.
7. Mark evidence as verified / observed / inferred / unknown.
8. Add sanitized fixture tests for parsers/protocol behavior.
9. Never log credentials/tokens.
10. Never hardcode discovered application servers.
11. Destructive live tests require explicit opt-in.
12. Update this backlog when protocol knowledge changes.
