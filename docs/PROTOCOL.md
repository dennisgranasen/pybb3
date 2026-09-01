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
