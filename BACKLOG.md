# pybb3 Backlog

This document tracks reverse-engineering and implementation work for `pybb3`.

The goal is to build a headless Python client/SDK for Blood Bowl 3 that can authenticate through Steam, communicate with the Cyanide backend, manage teams, retrieve match data, and expose stable higher-level APIs.

## Status legend

* `DONE` — implemented and verified against the live BB3 backend
* `PARTIAL` — implemented but incomplete or not fully verified
* `TODO` — known work item
* `RESEARCH` — protocol behavior still needs reverse engineering
* `BLOCKED` — cannot proceed until additional protocol/data is captured

Priority:

* `P0` — required for core functionality
* `P1` — important
* `P2` — useful
* `P3` — optional / polish

---

# 1. Authentication and connection

## DONE — Steam authentication

Priority: `P0`

Implemented:

* SteamKit2 helper
* Steam login
* Steam auth session ticket for BB3 AppID `1016950`
* conversion of Steam ticket to BB3 `AuthToken`
* Python client can launch the Steam helper automatically
* verified on Windows
* verified on Linux

BB3 token transformation:

```text
raw Steam auth-session-ticket bytes
→ uppercase HEX
→ ASCII bytes
→ Base64
```

Requirements:

* never log Steam passwords
* never log Steam refresh tokens
* never log Steam auth tickets
* never log BB3 AuthTokens

---

## DONE — Environment configuration

Priority: `P0`

Expected configuration:

```dotenv
STEAM_USERNAME=
# STEAM_PASSWORD=

BB3_PATH=

# Optional overrides:
# BB3_RULES_ENGINE_ZIP=
# BB3_DATA_ZIP=
```

Expected behavior:

1. operating-system environment variables
2. `.env`
3. interactive prompt

`STEAM_USERNAME` is the Steam login name, not SteamID64.

Password must use a secure prompt when not supplied.

---

## DONE — Dynamic BB3 backend discovery

Priority: `P0`

Do not hardcode the BB3 application server.

Known bootstrap flow:

```text
GET http://bootstrap6-bb3.cyanide-studio.com:28006/lobby/{client_version}

→ tcp://host:port
```

The returned host/port must be used for the TCP connection.

---

## TODO — Improve session lifecycle

Priority: `P1`

Observed server error:

```text
Code 11
This account is already logged in
```

Tasks:

* determine whether BB3 has an explicit logout request
* identify any logout/disconnect message used by the official client
* ensure TCP sockets always close on normal exit
* ensure sockets close on exceptions
* ensure Steam helper process terminates correctly
* test interrupted/debugger-aborted sessions
* determine server timeout for abandoned sessions

Acceptance criteria:

* normal `with BB3Client...` exit does not leave an active BB3 account session
* helper process does not remain orphaned
* login immediately after a clean previous session succeeds

---

# 2. Protocol core

## DONE — BB3 framing

Priority: `P0`

Known frame format:

```text
uint32 little-endian header_length
<header XML: header_length bytes>
<body: Data.size bytes>
repeat
```

Header contains fields such as:

```xml
<Header>
  <Data
    type="textxml"
    size="..."
    zipped="false"
    MessageName="..."
    MessageToken="..."
    sizeBeforeCompression="..."
  />
</Header>
```

---

## DONE — Message token handling

Priority: `P0`

Important distinction:

```text
Header MessageToken
!=
Body <Token>
```

Known behavior:

* header `MessageToken` is transport/request correlation
* body `<Token>` is application request sequence
* keepalive messages consume transport tokens

Do not merge these counters.

---

## DONE — Initial connection sequence

Priority: `P0`

Observed startup sequence includes:

```text
NotificationKeepAlive
KeepAliveAdvice
RequestGetServerStatus
RequestGetGamerConfig
RequestLogin
```

---

## DONE — Structured server exceptions

Priority: `P1`

Current error handling should expose structured exception data.

Desired API:

```python
try:
    ...
except BB3RequestError as exc:
    print(exc.code)
    print(exc.description)
    print(exc.message_name)
```

Requirements:

* decode Base64 `<Exception><Desc>`
* expose numeric exception code
* preserve raw response for diagnostics
* support both `<Exception>` and `<Exceptions>`
* do not assume every successful response contains `<Result>`

Implemented:

* `BB3RequestError` exposes `code`, `description`, `message_name`,
  `raw_response`, and the original response `frame`
* both direct `<Exception>` and wrapped `<Exceptions>` responses are handled
* failure descriptions are Base64-decoded when possible
* `request()` consistently returns a validated XML root
* `request_frame()` preserves low-level raw frame access
* automatically formatted error messages redact labelled secrets

Known successful response example:

```xml
<ResponseCreateTeam>
  <Exceptions/>
  <Token>4</Token>
  <IdTeam>...</IdTeam>
  <ShouldCache>0</ShouldCache>
</ResponseCreateTeam>
```

There is no `<Result>` field in this response.

Acceptance criteria:

* `ResponseCreateTeam` is treated as successful
* `ResponseLogin Result=0` raises a structured error
* error description is decoded automatically

---

# 3. Team management

## DONE — Create team

Priority: `P0`

Verified against live BB3 backend on:

* Windows
* Linux

Known request:

```xml
<RequestCreateTeam>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <Name>BASE64(team name)</Name>
  <Race>...</Race>
  <Motto>...</Motto>
  <IsCustom>false</IsCustom>
  <TeamRecruitmentId/>
  <ChosenSpecialRule/>
</RequestCreateTeam>
```

Successful response contains:

```xml
<IdTeam>BASE64(team UUID)</IdTeam>
```

`create_team()` must return the decoded team UUID.

---

## BLOCKED — Get team / roster

Priority: `P0`

Reverse engineer and implement the response for retrieving the full current team roster.

Current blocker:

* the repository has no captured or sanitized `ResponseGetTeamRoster` body
* field names and nesting cannot be implemented without inventing protocol data

Required next input:

* one sanitized successful roster response, preferably for a team containing
  players, skills, an injury, and team improvements

Primary target:

```text
ResponseGetTeamRoster
```

Need to expose:

* team UUID
* team name
* race
* treasury
* dedicated fans
* rerolls
* apothecary
* assistant coaches
* cheerleaders
* players
* player UUIDs
* player names
* position IDs
* skills
* SPP
* injuries
* MNG
* temporary retirement state
* current team value
* inducement-related state if present

Acceptance criteria:

```python
team = client.get_team(team_id)

print(team.name)
print(team.players)
```

should return structured Python models rather than raw XML.

---

## DONE — Hire player from position

Priority: `P1`

Known request:

```xml
<RequestHirePlayerFromPosition>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <TeamId>BASE64(team UUID)</TeamId>
  <Position>POSITION_ID</Position>
</RequestHirePlayerFromPosition>
```

Response returns a player UUID.

Verify against live backend if not already covered by integration tests.

---

## DONE — Rename player

Priority: `P1`

Known request:

```text
RequestSetPlayerName
```

Fields:

* player ID
* Base64 name

---

## DONE — Fire player

Priority: `P1`

Known request:

```xml
<RequestFirePlayers>
  <IdTeam>...</IdTeam>
  <IdPlayers/>
  <PlayerFireInfos>
    <PlayerFireInfosItem>
      <PlayerId>...</PlayerId>
      <TemporarilyRetire>false</TemporarilyRetire>
    </PlayerFireInfosItem>
  </PlayerFireInfos>
</RequestFirePlayers>
```

`Result=1` has been observed.

---

## RESEARCH — Temporary retirement

Priority: `P2`

The current static rules data exposes temporary-retirement semantics for injuries.

Need to determine live API behavior for:

```xml
<TemporarilyRetire>true</TemporarilyRetire>
```

Tasks:

* determine which casualties permit retirement
* verify server validation
* determine how retired players appear in team responses
* determine reactivation/healing behavior

---

## TODO — Delete team

Priority: `P1`

A delete-team request is known to exist but the request body is not yet confirmed.

Current client behavior should remain:

```python
raise NotImplementedError
```

until protocol semantics are verified.

Tasks:

* capture official client deleting a test team
* identify exact request message name
* identify request body
* identify success response
* implement
* add explicit safety guard for destructive operation

Acceptance criteria:

```python
client.delete_team(team_id)
```

works only when the exact protocol has been verified.

---

## DONE — Team improvements

Priority: `P1`

Known request:

```xml
<RequestUpdateTeamImprovements>
  <TeamId>...</TeamId>
  <Improvements>
    <ImprovementsItem>
      <ImprovementId>...</ImprovementId>
      <Quantity>...</Quantity>
    </ImprovementsItem>
  </Improvements>
</RequestUpdateTeamImprovements>
```

`Quantity` is a signed delta.

Known improvement IDs `1–5` have been confirmed from modern BB3 rules data.

---

## DONE — Team name and motto setters

Priority: `P2`

Known messages:

```text
RequestSetTeamName
RequestSetTeamMotto
```

---

# 4. Player advancement

## RESEARCH — Player level-ups

Priority: `P0`

Need to reverse engineer:

* available improvement choices
* characteristic increases
* selected primary skills
* selected secondary skills
* random primary skills
* random secondary skills
* SPP costs
* server-side validation
* skill duplication rules
* characteristic maximums
* increase/reduction interactions

Tasks:

1. capture player advancement flow
2. identify request messages
3. map skill IDs to `BB3Rules`
4. model advancement state
5. expose high-level API

Desired API:

```python
choices = client.get_player_advancement_options(player_id)

client.apply_player_advancement(
    player_id,
    ...
)
```

---

# 5. Match and game discovery

## TODO — GetGames

Priority: `P0`

Implement retrieval of games associated with the authenticated account/team.

Need to determine:

* pagination
* active games
* finished games
* competition IDs
* team IDs
* opponent IDs
* timestamps
* game result references

---

## TODO — GetGameResult

Priority: `P0`

Implement structured match-result retrieval.

Desired flow:

```text
GetGames
→ GetGameResult
→ DownloadReplay
```

This should allow pybb3 to discover games automatically rather than requiring a manually supplied game UUID.

---

## DONE — Replay download

Priority: `P0`

Known request:

```xml
<RequestDownloadReplay>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <GameId>BASE64(game UUID)</GameId>
</RequestDownloadReplay>
```

Replay payload decoding:

```text
Base64
→ Base64
→ zlib
→ Replay XML
```

---

## TODO — Structured MatchResult models

Priority: `P0`

MatchResult should be treated as the canonical semantic match result.

Need structured models for:

* teams
* coaches
* score
* touchdowns
* casualties
* winnings
* SPP
* MVP
* player results
* competition
* timestamps
* match status
* concession
* disconnect
* redraft-related state if present

Avoid requiring consumers to parse raw XML.

---

## TODO — Replay semantic event API

Priority: `P1`

Replay XML contains semantic events such as:

```text
Event*
ReplayStep
BoardState
InitialBoardState
```

Desired API:

```python
replay.events
replay.match_result
replay.initial_state
```

Prefer semantic events for analysis.

Do not expand every BoardState into large application-domain models unless necessary.

---

# 6. Formations

## DONE — Retrieve formations

Priority: `P2`

Known message:

```text
RequestGetTeamFormations
```

---

## DONE — Save formation

Priority: `P2`

Known request:

```xml
<RequestSaveFormation>
  <Formation>
    <Id/>
    <TeamId>...</TeamId>
    <Name>BASE64(name)</Name>
    <Data>BASE64(JSON)</Data>
    <Type>0</Type>
  </Formation>
</RequestSaveFormation>
```

Known `Data` example:

```json
{
  "pitchMap": {
    "(X=7,Y=0)": {
      "number": 1
    }
  }
}
```

Known formation types:

```text
0 = Defensive
1 = Offensive
```

---

## RESEARCH — Formation player-number semantics

Priority: `P2`

The `number` field likely maps to player roster number.

Verify this explicitly.

Also verify whether supplying an existing Formation `Id` updates an existing formation.

---

## DONE — Remove formation

Priority: `P2`

Known message:

```text
RequestRemoveFormations
```

---

# 7. Team customization / cosmetics

## PARTIAL — Cosmetic setters

Priority: `P2`

Known collection tags and setters:

```text
TeamCustoJerseyPattern   → RequestSetTeamJerseyPattern

TeamCustoColor           → RequestSetTeamPrimaryColor
                         → RequestSetTeamSecondaryColor
                         → RequestSetTeamTertiaryColor

TeamCustoCheerleader     → RequestSetTeamCheerleader
TeamCustoCoach           → RequestSetTeamCoach
TeamCustoPitch           → RequestSetTeamPitch
TeamCustoStadium         → RequestSetTeamStadium
TeamCustoCoachZone       → RequestSetTeamCoachZone
TeamCustoStaffZone       → RequestSetTeamStaffZone
TeamCustoCheerleaderZone → RequestSetTeamCheerleaderZone
TeamCustoDice            → RequestSetTeamDice
TeamCustoBall            → RequestSetTeamBall
```

---

## RESEARCH — Collection item ID semantics

Priority: `P1`

Determine exact difference between:

```text
CollectionItem.Id
CollectionItemInstance.Id
```

Need to know which one each setter expects.

Tasks:

* capture complete `ResponseCollectionItems`
* correlate collection entries with setter requests
* correlate backend UUIDs with static asset/content IDs
* inspect whether account ownership is represented through instances

---

## RESEARCH — Team logo/emblem

Priority: `P2`

Need to identify:

* collection tag
* getter
* setter
* ID semantics

---

# 8. Static BB3 rules and data

## DONE — Read bb3rulesengine.zip

Priority: `P0`

Expected archive:

```text
BB3/Content/OfflineServer/bb3rulesengine.zip
```

Contains:

```text
Datas/BB3Rules.json
Datas/Effects.json
Datas/SPCs.json
Datas/TextGeneration.json
```

---

## DONE — Read bb3.zip

Priority: `P1`

Expected archive:

```text
BB3/Content/OfflineServer/bb3.zip
```

Known relevant files:

```text
Datas/BB3Rules.json
Datas/Rules.json
Datas/Locas.json
Datas/PredefinedTeams.json
Datas/ShopData.json
```

Do not merge all rule sources destructively.

---

## DONE — Authoritative modern rules API

Priority: `P0`

`bb3rulesengine.zip/Datas/BB3Rules.json` should be treated as the primary current rules source.

The older:

```text
bb3.zip/Datas/Rules.json
```

uses a different/legacy schema and must not silently override modern rules.

---

## DONE — Semantic rules-engine API

Priority: `P1`

Expected conceptual API:

```python
data.rules
data.effect_catalog
data.special_play_cards
data.textgen
```

Raw access should remain available for reverse engineering and forward compatibility.

---

## TODO — Strong typed rule models

Priority: `P1`

Add or improve semantic models for:

* races
* rosters
* positions
* characteristics
* skills
* skill categories
* inducements
* special rules
* casualties
* casualty effects
* star players
* special play cards
* effects

Consumers should not need to understand raw table layout for common operations.

Desired examples:

```python
race = data.rules.race_by_code(7)

position = data.rules.position_by_code(1102)

print(position.skills)
print(position.characteristics)
```

---

# 9. Casualties and injuries

## DONE — Current casualty definitions available

Priority: `P1`

Known modern casualty codes:

```text
0  no_casualty
1  badly_hurt
2  seriously_hurt
3  serious_injury
4  lasting_injury
5  smashed_knee
6  head_injury
7  broken_arm
8  neck_injury
9  dislocated_shoulder
10 dead
```

Modern rules data also exposes casualty effects including:

* characteristic penalties
* MNG
* niggling injuries
* permanent/temporary effects
* healability
* temporary retirement eligibility

---

## TODO — Map runtime injuries to static rules

Priority: `P1`

When roster/match responses expose injury IDs, resolve them automatically to semantic injury objects.

Desired API:

```python
player.injuries

for injury in player.injuries:
    print(injury.name)
    print(injury.miss_next_game)
    print(injury.characteristic_modifier)
```

---

# 10. Special Play Cards

## DONE — Static SPC relationship model

Priority: `P2`

Known relationship:

```text
BB3Rules.bb3_rules_spc
→ SPCs.json
→ Effects.json
```

Example:

```text
SPC code 12
→ Experimental_Footgear
→ effect 19
→ additional skills + characteristic modifiers
```

---

## TODO — Runtime SPC protocol

Priority: `P3`

If useful, reverse engineer:

* available cards
* owned cards
* selected cards
* activation
* target selection
* triggered card effects

This is lower priority than core team and match APIs.

---

# 11. Shop and collection data

## PARTIAL — Static ShopData support

Priority: `P3`

Known tables:

```text
bb_content
bb_shop_item
bb_shop_item_category
bb_shop_item_content
```

Known content types include:

```text
Jersey
Starplayer
Ball
```

Important ID distinction:

```text
shop item id
content row id
asset/content id
```

Do not treat these as interchangeable.

---

## RESEARCH — Modern account collection mapping

Priority: `P2`

Static `ShopData.json` does not fully describe modern BB3 account customization.

Need to determine whether:

```text
backend collection UUID
→ asset/content ID
→ static content metadata
```

can be mapped reliably.

---

# 12. Redraft and season lifecycle

## RESEARCH — Redraft

Priority: `P1`

Need to capture and model:

* redraft eligibility
* redraft budget
* retained players
* agent fees
* rerolls/improvements retention
* player retirement
* journeymen
* treasury changes
* team state transitions

This is required before pybb3 can fully manage persistent league teams.

---

## RESEARCH — Journeymen

Priority: `P1`

Determine:

* how journeymen appear in roster responses
* whether they have temporary UUIDs
* how hiring after a match works
* how loner skills are represented
* request messages used to permanently hire them

---

# 13. Event and protocol discovery

## TODO — Message catalog

Priority: `P1`

Maintain a machine-readable catalog of known BB3 messages.

Suggested file:

```text
docs/messages.json
```

Fields:

```json
{
  "RequestCreateTeam": {
    "response": "ResponseCreateTeam",
    "status": "verified",
    "direction": "client_to_server"
  }
}
```

This should eventually include:

* request name
* response name
* direction
* known body fields
* Base64 fields
* verified/unverified status
* example capture reference if available

---

## TODO — Unknown enum tracking

Priority: `P2`

Maintain discovered but unresolved:

* event IDs
* state IDs
* match status IDs
* competition types
* player states
* error codes
* collection types

Do not silently guess enum meanings.

---

# 14. Capture tooling

## PARTIAL — Raw TCP capture parser

Priority: `P1`

Wireshark "Follow TCP Stream" raw exports may interleave both TCP directions.

This can cause incorrect:

```text
Data.size
```

interpretation.

Current parser should recover by scanning for plausible `<Header>` boundaries.

---

## TODO — Proper pcap half-stream reconstruction

Priority: `P1`

Implement parser that:

1. reads pcap/pcapng
2. identifies BB3 TCP connection
3. reconstructs each TCP direction independently
4. handles retransmissions
5. parses BB3 frames
6. correlates requests and responses

Desired output:

```text
timestamp
direction
MessageName
MessageToken
body Token
decoded body
```

---

## DONE — Sensitive-data redaction

Priority: `P0`

All capture/debug tooling must redact:

* AuthToken
* Steam tickets
* Steam refresh tokens
* passwords
* Steam Guard secrets/codes
* legacy Cyanide/API credentials

Redaction should happen before logs are persisted.

Implemented:

* central text redaction for XML, JSON, dotenv-style assignments, and bearer
  authorization values
* recursive mapping redaction for structured diagnostics
* BB3 request error messages are redacted while `raw_response` remains
  explicitly available for controlled diagnostics
* current capture tools emit frame metadata or non-secret collection IDs and
  do not persist decoded authentication request bodies

---

# 15. Client architecture

## TODO — Event dispatcher

Priority: `P1`

Current request/response API will eventually need to coexist with asynchronous server notifications.

Implement a dispatcher capable of:

* request/response correlation
* keepalive handling
* unsolicited notifications
* callbacks/subscriptions
* replay/live-game events
* graceful cancellation

---

## TODO — Reconnect behavior

Priority: `P1`

Determine and implement:

* reconnect after network drop
* authentication after reconnect
* account-session behavior
* request retry safety
* idempotent vs destructive requests

Never automatically retry destructive operations unless safety is proven.

---

## TODO — Async client

Priority: `P2`

Consider:

```python
async with AsyncBB3Client.from_steam() as client:
    ...
```

Only implement after synchronous API/protocol behavior is stable.

---

# 16. Testing

## DONE — Unit tests

Priority: `P0`

Existing tests cover at least parts of:

* encoding
* replay decoding
* backend discovery
* rules/static data
* archive loading
* protocol helpers

---

## PARTIAL — Live integration tests

Priority: `P1`

Live tests must be opt-in.

Never run against a real account during ordinary unit tests.

Suggested markers:

```python
@pytest.mark.live
@pytest.mark.destructive
```

Example:

```bash
pytest -m live
```

Team creation should additionally require an explicit destructive flag.

Example:

```bash
PYBB3_ALLOW_DESTRUCTIVE_TESTS=1
```

Acceptance criteria:

* unit tests never access Steam or BB3 backend
* live tests are clearly separated
* destructive tests require explicit opt-in

Implemented:

* live tests require `PYBB3_RUN_LIVE_TESTS=1`
* destructive tests additionally require `PYBB3_ALLOW_DESTRUCTIVE_TESTS=1`
* pytest markers are registered centrally
* test collection itself performs no network or account mutation

---

## TODO — Golden protocol fixtures

Priority: `P1`

Store sanitized protocol fixtures for:

* login success
* login failure
* create team
* hire player
* fire player
* formations
* collection items
* replay response
* roster response

Tests should operate against sanitized captures rather than requiring live backend access.

---

# 17. Documentation

## TODO — Protocol documentation

Priority: `P1`

Maintain:

```text
docs/PROTOCOL.md
```

Include:

* framing
* token semantics
* Base64 conventions
* bootstrap discovery
* authentication
* known request/response pairs
* exception semantics
* replay encoding

Clearly label everything as:

```text
VERIFIED
INFERRED
UNKNOWN
```

---

## TODO — Data source documentation

Priority: `P1`

Maintain:

```text
docs/DATA_SOURCES.md
```

Document source precedence and intended usage for:

```text
bb3rulesengine.zip
bb3.zip
BB3Rules.json
Rules.json
Effects.json
SPCs.json
TextGeneration.json
ShopData.json
```

---

# 18. Immediate priorities

Codex should generally work in this order unless a task explicitly says otherwise.

## P0

1. `ResponseGetTeamRoster`
2. `GetGames`
3. `GetGameResult`
4. structured MatchResult
5. player advancement protocol

## P1

6. graceful session lifecycle/logout
7. delete-team protocol
8. collection-item ID semantics
9. runtime injury mapping
10. redraft
11. journeymen
12. event dispatcher
13. reconnect behavior
14. proper pcap half-stream reconstruction

## P2

15. cosmetics completeness
16. formation semantics
17. typed static-rule convenience APIs
18. async client

## P3

19. Special Play Card runtime API
20. legacy shop/content mapping improvements

---

# 19. Codex working rules

When Codex works on this repository:

1. Read this backlog before starting protocol work.
2. Inspect existing implementation before creating a parallel abstraction.
3. Prefer extending existing public APIs over adding duplicate APIs.
4. Do not assume all BB3 responses contain `<Result>`.
5. Preserve raw protocol/data access alongside semantic abstractions.
6. Never invent protocol fields or enum meanings.
7. Clearly distinguish:

   * verified from live backend
   * observed in captures
   * inferred
   * unknown
8. Add tests for every parser/protocol behavior where a sanitized fixture is available.
9. Never log or commit credentials/tokens.
10. Do not hardcode dynamically discovered BB3 application servers.
11. Destructive live tests must require explicit opt-in.
12. Update this backlog when a task is completed or when new protocol behavior is discovered.
