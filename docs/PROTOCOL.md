# BB3 protocol notes

Status vocabulary:

- **VERIFIED** — confirmed against the live backend or a captured exchange
- **OBSERVED** — present in a capture, without complete semantic verification
- **INFERRED** — implementation-supported interpretation not yet live-verified
- **UNKNOWN** — deliberately unresolved

The machine-readable request catalog is [`messages.json`](messages.json).

## Framing and tokens

**VERIFIED**

```text
uint32 LE header_length
header XML
body bytes
```

`MessageToken` is transport correlation, body `<Token>` is the application
request sequence, and `<AuthToken>` is the Steam-derived BB3 credential.
Keepalives consume transport tokens.

## Response contract

**VERIFIED from multiple captured responses**

A response can succeed without `<Result>`. Empty `<Exceptions/>` plus no direct
`<Exception>` is a valid success response. If `<Result>` is present, `0` is a
failure. `Exception/Desc` is Base64 in observed server errors.

## Session shutdown

**OBSERVED**

An official-client shutdown/logout capture contained no application-level
logout or disconnect request. The final parsed BB3 messages were ordinary
`NotificationKeepAlive` traffic, after which the application stream ended.

Do not invent a `RequestLogout`. Current pybb3 shutdown should close the TCP
socket and Steam helper. Exact TCP FIN/RST parity and abandoned-session timeout
remain transport-level research items.

## Steam AuthToken

**VERIFIED**

```text
raw Steam auth-session-ticket bytes
-> uppercase hexadecimal ASCII
-> Base64
```

## Team listing

**VERIFIED**

```xml
<RequestGetTeamsOfGamer>
  <Size>9</Size>
  <Start>0</Start>
  <GamerId/>
  <Races/>
  <Order>4</Order>
  <Descending>true</Descending>
  <Name/>
  <Competing/>
  <IsCustom/>
  <IsTemplate><IsTemplateItem>false</IsTemplateItem></IsTemplate>
</RequestGetTeamsOfGamer>
```

Response: `ResponseGetTeams`.

Team-to-competition lookup:

```xml
<RequestGetTeamsCompetitions>
  <TeamIds><TeamIdsItem>BASE64(team UUID)</TeamIdsItem></TeamIds>
</RequestGetTeamsCompetitions>
```

## Team roster

**VERIFIED**

The request field is `IdTeam`, not `TeamId`:

```xml
<RequestGetTeamRoster>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <IdTeam>BASE64(team UUID)</IdTeam>
</RequestGetTeamRoster>
```

`ResponseGetTeamRoster` succeeds without `<Result>`.

The response contains two semantically distinct player structures:

- `Roster/RaceRoster/.../RosterSlotLine`: position/roster templates, including
  base characteristics, starting skills, cost, maximum and skill-category
  availability/cost metadata.
- `Roster/TeamRoster/TeamRosterSlot/Player`: actual current players, including
  backend IDs, names, SPP, level-up state, current skills, characteristics,
  MNG/dead/retirement state and value.

Do not treat template `Player` records as hired players. The outer
`TeamRosterSlot/Number` and inner `Player/Number` have both been observed and
must be preserved separately until their exact semantics are fully mapped.

The response also contains `RosterizedInducements`, `CanAddStarplayer`,
`CanBeRedrafted`, `CanBeUpdatedReason` and `Nb_slots`.

## Delete team

**VERIFIED**

```xml
<RequestDeleteTeam>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <IdTeam>BASE64(team UUID)</IdTeam>
</RequestDeleteTeam>
```

Success:

```xml
<ResponseDeleteTeam>
  <Exceptions/>
  <Token>...</Token>
  <ShouldCache>0</ShouldCache>
</ResponseDeleteTeam>
```

No `<Result>` is required.

## Player advancement

### Read available improvements

**VERIFIED**

```xml
<RequestGetPlayerImprovements>
  <IdPlayer>BASE64(player UUID)</IdPlayer>
</RequestGetPlayerImprovements>
```

`ResponseGetPlayerImprovements` returns `SkillCategories` with server-provided
`Cost`, `CostRandom`, `TeamValue`, affinity/availability/choosability fields,
plus `CharacteristicCost`, `SpentSpp`, `IsCharacteristicAvailable` and
`IsCharacteristicChoosable`.

**Do not hardcode SPP costs.** Captures show costs change after previous
advancements; the server response is authoritative for the current player.

### Random skill

**VERIFIED**

```xml
<RequestAddPlayerRandomSkill>
  <IdPlayer>BASE64(player UUID)</IdPlayer>
  <Category>1</Category>
</RequestAddPlayerRandomSkill>
```

Response returns the selected `Skill` ID and `HasLeft`. One captured result was
`Skill=8`; current `BB3Rules.json` maps skill code `8` to `sprint`.

### Chosen skill

**VERIFIED**

Chosen primary and chosen secondary use the same request:

```xml
<RequestAddPlayerSkill>
  <IdPlayer>BASE64(player UUID)</IdPlayer>
  <Skill>SKILL_ID</Skill>
</RequestAddPlayerSkill>
```

Primary/secondary status is not sent as a separate field; server-side player
state/category affinity determines validity and cost.

### Characteristic increase

**VERIFIED**

Beginning the characteristic advancement performs the server-side roll:

```xml
<RequestBeginIncreasePlayerCharacteristic>
  <PlayerId>BASE64(player UUID)</PlayerId>
</RequestBeginIncreasePlayerCharacteristic>
```

Note the field name is `PlayerId` here, not `IdPlayer`.

Response contains:

- `Roll`
- `Characteristics/CharacteristicUpgrade`
  - `Id`
  - `Available`
  - `TeamValue`
  - `Message`
- `CanTakeSecondarySkill`

The roll determines which characteristics are available in a normal team. A
custom-team capture returned all characteristics as available; that is custom
team behavior and must not be generalized to ordinary advancement.

If the coach accepts a characteristic:

```xml
<RequestChooseIncreasePlayerCharacteristic>
  <PlayerId>BASE64(player UUID)</PlayerId>
  <ChosenCharacteristic>CHARACTERISTIC_ID</ChosenCharacteristic>
</RequestChooseIncreasePlayerCharacteristic>
```

If the coach rejects the rolled characteristic options and
`CanTakeSecondarySkill=1`, the UI permits taking a secondary skill instead.
The normal chosen-skill endpoint is already verified; no separate
primary/secondary request field has been observed.

## Games and match results

### Game search

**VERIFIED request contract**

`RequestGetGames -> ResponseGetGames` uses a broad filter envelope:

```xml
<RequestGetGames>
  <Size>...</Size>
  <Start>...</Start>
  <IsLive><IsLiveItem>true</IsLiveItem>...</IsLive>
  <IsOver>...</IsOver>
  <HasReplay><HasReplayItem>true</HasReplayItem>...</HasReplay>
  <LeagueIds>...</LeagueIds>
  <LeagueName/>
  <CompetitionIds>
    <CompetitionIdsItem>BASE64(competition UUID)</CompetitionIdsItem>
  </CompetitionIds>
  <CompetitionName/>
  <GamerIds>...</GamerIds>
  <GamerName/>
  <TeamIds><TeamIdsItem>BASE64(team UUID)</TeamIdsItem></TeamIds>
  <TeamName/>
  <MaxDaysSinceGame>20000</MaxDaysSinceGame>
  <MinRating>0</MinRating>
  <MaxRating>0</MaxRating>
  <MinTeamValue>0</MinTeamValue>
  <MaxTeamValue>0</MaxTeamValue>
  <GameType>...</GameType>
  <Races>...</Races>
  <OwnRaces>...</OwnRaces>
  <OpponentRaces>...</OpponentRaces>
  <ContainsAi>...</ContainsAi>
  <Outcome>...</Outcome>
  <Order>0</Order>
  <Descending>true</Descending>
</RequestGetGames>
```

Captured values included `GameType` values `0,1,2,4` and `Outcome` values
`0,1,2`, but their enum meanings are deliberately **UNKNOWN** here.

`ResponseGetGames` contains `Total` and repeated `Games/GameData` records with,
among other data, `GameId`, `MatchId`, home/away gamers, teams and scores,
validation state, pending-validation state and competition data.

### Game result

**VERIFIED**

```xml
<RequestGetGameResult>
  <GameId>BASE64(game UUID)</GameId>
</RequestGetGameResult>
```

`ResponseGetGameResult/GameResult` was observed with:

- `GameId`, `MatchId`
- home/away teams and gamers
- `HomeScore`, `AwayScore`
- `HomeValidation`, `AwayValidation`
- `HomeHasConceded`, `AwayHasConceded`
- `HasReplay`, `IsLive`, `HasPendingValidation`
- embedded `Competition`
- home/away ladder rating/division gains
- home/away treasury + dedicated-fan result gains
- MVP and gamer progression XP gain data

### Match statistics

**VERIFIED**

```xml
<RequestGetMatchStatistics>
  <MatchId>BASE64(match UUID)</MatchId>
</RequestGetMatchStatistics>
```

`ResponseGetMatchStatistics` contains home/away gamer statistics and repeated
team `Statistic` records. Observed statistic fields are:

- `Id`
- `CategoryId`
- `CategoryName` — Base64 text
- `Name` — Base64 text
- `Value` — Base64 text
- `IsHighlight`

Observed labels include touchdowns, casualties, kills, injuries, running and
passing yards, blocks, fouls and other game statistics. Semantic meaning should
come from the returned labels rather than a duplicate hardcoded ID map.

### Additional captured match endpoints

**VERIFIED request contracts**

```text
RequestGetSppResult(GameId) -> ResponseGetSppResult
RequestGetMatchDiceRolls(MatchId) -> ResponseGetMatchDiceRolls
RequestGetBattlePassGameXpGain(GameId) -> ResponseGetBattlePassGameXpGain
RequestGetAvailableGetGamesTeamValues -> ResponseGetAvailableGetGamesTeamValues
```

The SPP and dice-roll responses are preserved as raw XML by the current client
until representative structured models are justified.

## Competitions

### Competition

**VERIFIED**

```xml
<RequestGetCompetition>
  <IdCompetition>BASE64(competition UUID)</IdCompetition>
</RequestGetCompetition>
```

The returned `Competition` contains, among other fields, `Id`, `Name`,
`SettingId`, `LeagueId`, `Day`, `Format`, `Status`, registration/division flags,
cross-play state, board/logo/UGC identifiers and creator data.

### Competition setting

**VERIFIED**

```xml
<RequestGetCompetitionSetting>
  <SettingId>BASE64(setting UUID)</SettingId>
</RequestGetCompetitionSetting>
```

One complete captured `Setting` contained:

```text
RedraftOnTeamRegistration
ContestFormat
BannedSpecialCards
ContestsRedraftPeriod
BannedPitches
AllowApplication
MaxParticipants
HasPassword
AllowParticipantMatchValidation
AutomaticAdvancement
AllowTeamCreation
TimerId
AllowExperiencedTeams
AllowCustomTeams
Format
RedraftOnCompetitionEnd
AllowTicketOffer
EnableRanking
AccumulateTreasuryForRedraft
RedraftTreasuryCap
AdmissionMode
AllowTicketRequest
AutomaticValidation
EnableMatchConsequences
AllowAiTeams
```

The numeric enum meanings of `ContestFormat`, `Format`, `TimerId` and
`AdmissionMode` are not inferred from a single capture.

### Competition day and schedule

**VERIFIED**

```xml
<RequestGetCompetitionDay>
  <IdCompetition>BASE64(competition UUID)</IdCompetition>
</RequestGetCompetitionDay>
```

The observed response returned `<Value>9</Value>`.

```xml
<RequestGetCompetitionSchedule>
  <IdCompetition>BASE64(competition UUID)</IdCompetition>
  <Day>9</Day>
</RequestGetCompetitionSchedule>
```

`ResponseGetCompetitionSchedule` contains:

```text
Schedule
  Contest*
    Matches
      Match*
        Status
        GameId
        HomeGamer / AwayGamer
        HomeTeam / AwayTeam
        HomeScore / AwayScore
        Id
    Id
    Format
Day
Competition
```

The schedule can therefore represent both competition pairings and played
matches; exact `Status` enum meanings remain unresolved.

### Ranking, participants and next match

**VERIFIED request contracts**

```text
RequestGetCompetitionRanking(Size, Start, IdCompetition, Races)
  -> ResponseGetCompetitionRanking

RequestGetCompetitionParticipantsByGamer(CompetitionId, GamerId)
  -> ResponseGetCompetitionRanking

RequestGetNextMatch(ParticipantId)
  -> ResponseGetNextMatch

RequestGetCompetitionGamerRegisteredTeams(GamerId, CompetitionId)
  -> ResponseGetCompetitionGamerRegisteredTeams

RequestGetCompetitionGamerBanDuration(CompetitionId, GamerId)
  -> ResponseGetCompetitionGamerBanDuration

RequestGetCompetitionMenu(CompetitionId)
  -> ResponseGetCompetitionMenu

RequestGetCompetitionFormats
  -> ResponseGetCompetitionFormats
```

The fact that `RequestGetCompetitionParticipantsByGamer` returns
`ResponseGetCompetitionRanking` is capture-observed and intentional.

## League and competition administration

**VERIFIED from the 2026-09-01 official-client capture**

Implemented request families:

- create/get league, league settings/description/member/member list
- gamer permissions for a league or competition board
- competition search and creation
- admission modes, allowed team counts, contest formats, team-value extrema,
  pitches and redraft possible values
- competition description/day count/participants/password
- participant limit, experienced teams, automatic validation, custom teams,
  match consequences, forced/banned pitches and TV min/max mutations

These response contracts are intentionally asymmetric:

```text
RequestGetCompetitionParticipantsByGamer -> ResponseGetCompetitionRanking
RequestSetAllowCustomTeams              -> ResponseSetCompetitionSetting
RequestSetEnableMatchConsequences       -> ResponseSetCompetitionSetting
```

The captured competition-description mutation uses the exact field spelling
`Idcompetition` (lower-case `c`), unlike the read endpoint's `IdCompetition`.

All string identifiers and user-facing strings in these bodies are Base64.
See [`ENUMS.md`](ENUMS.md) for capture-verified numeric meanings.

### Management additions from 2026-09-06

**OBSERVED in the official-client capture and implemented**

See the [capture notes](../CAPTURE_NOTES_20260906.md) for the original
observations. The current client also exposes:

| Python method | Request-specific fields | Return value |
| --- | --- | --- |
| `get_league_languages()` | None (`RequestGetLeagueLangs`) | Dictionary of integer language IDs to decoded names |
| `get_league_password(league_id)` | `LeagueId` | Decoded password |
| `set_league_description(league_id, description)` | `LeagueId`, `Description` | Raw response XML |
| `get_league_news(league_id, size=4, start=0)` | `Size`, `Start`, `LeagueId` | Raw response XML |
| `create_league_news(league_id, title, description)` | `LeagueId`, `Title`, `Description` | Raw response XML |
| `update_league_news(news_id, title, description)` | `NewsId`, `Title`, `Description` | Raw response XML |
| `delete_league_news(news_id)` | `NewsId` | Raw response XML |
| `get_competition_gamer_number(competition_id)` | `IdCompetition` | `(gamers, ais)` from `Value` and `AIs` |
| `get_competition_tickets(competition_id)` | `Size`, `Start`, `CompetitionId`, `Type/TypeItem`, `Status/StatusItem` | Raw response XML |
| `get_competition_gamer_valid_teams(competition_id, gamer_id)` | Team-list filter envelope plus `CompetitionId` | Raw response XML |
| `join_competition(team_id, competition_id)` | `IdTeam`, `IdCompetition` | Raw response XML |
| `quit_competition(participant_id, competition_id=None)` | `ParticipantId`, `CompetitionId` | Raw response XML |

Pagination arguments are keyword-only. Ticket queries default to `size=15`,
`start=0`, `ticket_types=(1, 0)` and `statuses=(0,)`. The response keeps
`GamerTickets`, `TeamTickets` and `Total` separate; ticket type/status labels
remain unknown.

Valid-team responses wrap teams with `IsValid`, Base64 `Hints` and `IsFixable`.
Quitting uses the participant ID, not the team ID, and sends an empty
`CompetitionId` element by default, matching the capture. Joining, quitting,
description changes and news create/update/delete modify backend state.

## Account conveniences

### Weekly free Warpstone

**OBSERVED protocol; product semantics confirmed from UI behavior**

```xml
<RequestGetFreeVcData>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
</RequestGetFreeVcData>
```

Observed response fields:

```text
FreeVc/Retrieved
FreeVc/Amount
FreeVc/Id
FreeVc/AvailableAt
```

The captured response had `Amount=10`; the feature is the weekly free
10-Warpstone reward. One `AvailableAt` value decoded to
`2026-09-07 14:00:00`.

The actual claim request has not been captured. Do not invent it.

### Battle-pass / gamer progression rewards

**OBSERVED**

`RequestUnlockBattlePassAvailableRewards` and
`RequestUnlockGamerProgressionAvailableRewards` were observed. These are P3
convenience candidates, not core team/competition functionality.

### Gamer profile cosmetics

**OBSERVED**

Gamer avatar/banner/frame/title collection data and avatar/banner/frame setters
were observed. They are intentionally very low priority and are distinct from
team cosmetics.

## Replay

**VERIFIED**

`RequestDownloadReplay` uses `GameId` Base64. The server payload itself is kept
lossless by `download_replay()` and exposed through a `Replay` object:

```text
ReplayData -> Base64 -> Base64 -> zlib -> XML
```

`MatchResult/GamerResults/GamerResult/IpAddress` contains a Base64-encoded
participant IP address in observed replay XML. `Replay.redact_ip_addresses()`
returns a new XML-backed replay in which each distinct source address is
replaced with a stable RFC 5737 documentation address. The original downloaded
`Replay` remains untouched. CLI replay export redacts by default; preserving
source addresses requires the explicit `--keep-ip-addresses` diagnostic flag.

`tools/download_any_replay.py` exercises login, official competition discovery,
competition-scoped `GetGames`, replay download, explicit redaction, on-disk
verification and XML-to-JSON conversion. `tools/replay_ips.py` accepts `.bbr`,
XML, JSON or stdin and prints only decoded IP addresses. The opt-in live test
uses the same request path and verifies the explicitly redacted replay contains
only documentation addresses.

Semantic interpretation is a separate layer: `Replay.timeline()` combines
ordered protocol messages into normalized match-domain events while preserving
decoded message evidence for diagnostics and future protocol work.

## Existing verified team operations

- `RequestCreateTeam`
- `RequestHirePlayerFromPosition`
- `RequestSetPlayerName`
- `RequestFirePlayers`
- `RequestUpdateTeamImprovements`
- team name/motto setters
- formation get/save/remove
- verified cosmetic setters listed in `messages.json`

## Bootstrap discovery

**VERIFIED**

The application server is dynamically discovered through the Cyanide bootstrap
endpoint and must not be hardcoded.
