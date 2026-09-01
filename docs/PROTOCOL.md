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
logout or disconnect message. The final parsed BB3 messages were an ordinary
`NotificationKeepAlive` exchange and then the application byte stream ended.

No `RequestLogout` (or equivalent) should be implemented without capture
evidence. Current pybb3 behavior should close the TCP socket cleanly and release
the Steam helper. Exact TCP FIN/RST parity and abandoned-session timeout remain
transport/lifecycle research items.

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

## League search

**OBSERVED**

Captured request:

```xml
<RequestSearchLeagues>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <Size>9</Size>
  <Start>0</Start>
  <Name/>
  <GamerId>BASE64(gamer UUID)</GamerId>
  <IsOfficial>
    <IsOfficialItem>false</IsOfficialItem>
  </IsOfficial>
  <IsGamerMember>
    <IsGamerMemberItem>true</IsGamerMemberItem>
  </IsGamerMember>
  <CanGamerCreateCompetitions/>
  <HasCompetitions/>
  <IncludePersonalLeagues>true</IncludePersonalLeagues>
  <Order>2</Order>
  <Descending>true</Descending>
</RequestSearchLeagues>
```

Response: `ResponseSearchLeagues`.

Observed `LeagueHeader` data includes league ID/name, creator, `BoardId`,
`CompetitionSettingId`, `NbCompetition`, `NbMember`, cross-play state and UGC
identifiers. Exact enum semantics for `Order` are not assigned here.

## Weekly free Warpstone

**OBSERVED protocol; product semantics confirmed from UI behavior**

Request:

```xml
<RequestGetFreeVcData>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
</RequestGetFreeVcData>
```

Observed response:

```xml
<ResponseGetFreeVcData>
  <Token>...</Token>
  <Result>1</Result>
  <ShouldCache>0</ShouldCache>
  <FreeVc>
    <Retrieved>1</Retrieved>
    <Amount>10</Amount>
    <Id>1</Id>
    <AvailableAt>BASE64(timestamp)</AvailableAt>
  </FreeVc>
</ResponseGetFreeVcData>
```

The feature is the weekly free 10-Warpstone reward. `Amount=10` is present on
the wire. One captured `AvailableAt` decoded to `2026-09-07 14:00:00`.

`Retrieved` is observed but its exact state semantics should be verified with a
capture taken while the reward is claimable.

The request that actually claims the reward has not yet been captured. Do not
invent a claim endpoint.

## Battle-pass and progression reward unlocks

**OBSERVED**

The manager/home capture includes write requests for available rewards:

```xml
<RequestUnlockBattlePassAvailableRewards>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <BattlePassIds>
    <BattlePassIdsItem>13</BattlePassIdsItem>
  </BattlePassIds>
</RequestUnlockBattlePassAvailableRewards>
```

The observed response was `ResponseUnlockBattlePassAvailableRewards` with
`Result=1` and an `UnlockedLevels` container.

`RequestUnlockGamerProgressionAvailableRewards` was also observed, but its
complete request body is not documented here until the relevant capture body is
reviewed explicitly.

These account-reward endpoints are low-priority conveniences, not core
team-management protocol.

## Gamer profile cosmetics

**OBSERVED**

The capture contains collection tags and setters for manager/gamer profile
customization including `GamerAvatar`, `GamerBanner`, `GamerFrame`,
`GamerTitle`, `RequestSetGamerAvatar`, `RequestSetGamerBanner` and
`RequestSetGamerFrame`.

These are intentionally low priority. Do not conflate manager/gamer cosmetics
with team cosmetics.

## Replay

**VERIFIED**

`RequestDownloadReplay` uses `GameId` Base64. Replay payload decode:

```text
ReplayData -> Base64 -> Base64 -> zlib -> XML
```

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
