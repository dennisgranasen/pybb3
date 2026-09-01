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

An official-client shutdown/logout capture contained no application-level
logout or disconnect request. The final parsed BB3 traffic was an ordinary
`NotificationKeepAlive` exchange, after which the BB3 byte stream ended.

Current interpretation:
- no explicit BB3 XML logout request has been observed
- clean session termination is therefore expected to happen at the TCP
  transport level

Remaining:
- verify immediate relogin after a clean pybb3 socket shutdown [DONE]
- measure server behavior / timeout after an abnormal process termination

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

`ResponseGetTeamRoster` protocol and response structure are **VERIFIED**. `RequestGetTeamRoster` uses `<IdTeam>`, not
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

## DONE — Delete team
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
- a normal-team capture with characteristics upgrade and `CanTakeSecondarySkill=1`
- duplicate-skill rejection behavior
- characteristic maximum/invalid-choice errors
- explicit live destructive tests behind opt-in flags

# 5. Match and game discovery

## TODO — GetGames
Priority: `P2`

Match discovery is currently secondary because the required game list can be
obtained through the external API. Implement this when direct backend-only
coverage becomes useful.

## TODO — GetGameResult
Priority: `P2`

Likewise secondary while the external API provides match results.

Desired eventual flow:
`GetGames -> GetGameResult -> DownloadReplay`.

## DONE — Replay download
Double Base64 + zlib decode is implemented.

## TODO — Structured MatchResult
Priority: `P2`

Useful later if pybb3 itself should become the canonical match-result provider.
For now, team-management and backend-only lifecycle operations take precedence.

## TODO — Replay semantic event API
Priority: `P2`

# 6. Formations

Retrieve/save/remove are implemented. Player-number semantics and update-vs-
create behavior remain research items.

# 7. Team customization / cosmetics

Setters are largely verified. Collection `Item.Id` vs `Instance.Id` semantics
and logo/emblem remain research items.

A manager-customization capture also observed profile cosmetics and setters for
gamer avatar, banner and frame, plus title collection tags. These are deliberately
very low priority for pybb3; document protocol evidence but do not spend core
implementation time on them.

# 8. Low-priority account / league conveniences

## OBSERVED — League search
Priority: `P2`

`RequestSearchLeagues -> ResponseSearchLeagues` is capture-observed. The
captured request supports filters for gamer membership, official status,
personal leagues, pagination and ordering. The response exposes league headers
including league ID/name, creator, board ID, competition-setting ID and member /
competition counts.

This may become useful if pybb3 needs direct backend league navigation instead
of relying on an external API.

## OBSERVED — Weekly free Warpstone status
Priority: `P3`

`RequestGetFreeVcData -> ResponseGetFreeVcData` is capture-observed.

Observed response fields:
- `FreeVc/Retrieved`
- `FreeVc/Amount`
- `FreeVc/Id`
- `FreeVc/AvailableAt`

The captured response had `Amount=10`. Product/UI behavior confirms this is the
weekly free 10-Warpstone reward. `AvailableAt` is Base64 text containing the
next availability timestamp.

Desired future convenience API:
- `get_free_warpstone_status()`
- `claim_free_warpstone()`
- optional idempotent CLI suitable for cron

Research still required:
- capture the actual claim request/response
- observe status when the reward is claimable (`Retrieved` semantics)
- observe duplicate / too-early claim behavior

Do not auto-claim as an implicit side effect of `login()`.

## OBSERVED — Battle-pass / progression reward unlocks
Priority: `P3`

The capture includes `RequestUnlockBattlePassAvailableRewards` and
`RequestUnlockGamerProgressionAvailableRewards`. These are potential future
explicit auto-claim helpers, but are not part of core team-management work.

## OBSERVED — Gamer profile / social / home data
Priority: `P3`

The same capture contains gamer profile/social, battle-pass, home-menu,
spotlight, collection and currency endpoints. Keep them in the protocol catalog
when exact request structure is known, but implementation is optional.

# 9. Static rules/data

Modern `bb3rulesengine.zip/Datas/BB3Rules.json` is authoritative. Do not merge
legacy `Rules.json` destructively.

Typed `PositionRule`, `RaceRule`, `SkillRule` and `TeamImprovementRule` already
exist. `BB3Rules.skill_by_code()` should be used to map advancement `Skill` IDs
instead of maintaining a duplicate hardcoded map.

# 10. Casualties and injuries

Modern casualty definitions are available. Runtime roster/match injury IDs still
need to be mapped automatically to static rules.

# 11. Redraft / journeymen

Both remain `RESEARCH` (`P1`) and require live protocol captures.

# 12. Capture tooling

pcap/pcapng half-stream reconstruction and redaction are partially implemented.
Continue improving real-capture verification, sequence-wraparound handling and
direct request/response correlation.

# 13. Testing

Live tests require `PYBB3_RUN_LIVE_TESTS=1`. Destructive tests additionally
require `PYBB3_ALLOW_DESTRUCTIVE_TESTS=1`.

Golden sanitized fixtures should include roster, player improvements,
characteristic roll, delete-team response, game listing and game result.

# 14. Immediate priorities

## P0
1. finish runtime injury/casualty mapping for roster players
2. finish player-advancement edge cases and validation behavior
3. redraft protocol
4. journeyman protocol

## P1
5. temporary-retirement semantics
6. immediate relogin / abnormal-session lifecycle behavior
7. competition/team-management protocol gaps not covered by the external API
8. collection-item ID semantics
9. event dispatcher
10. reconnect behavior
11. pcap reconstruction improvements

## P2
12. direct league-search/navigation support
13. `GetGames`
14. `GetGameResult`
15. structured `MatchResult`
16. replay semantic event API

## P3
17. weekly free Warpstone status / claim helper
18. battle-pass / gamer-progression reward claim helpers
19. gamer profile cosmetics/social/home-menu endpoints

# 15. Codex working rules

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
