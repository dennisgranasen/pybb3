# BB3 protocol notes

## Framing

```text
uint32 LE header_length
header XML
body bytes
```

Header example:

```xml
<Header><Data
 type="textxml"
 size="208"
 zipped="false"
 MessageName="RequestSetPlayerName"
 MessageToken="23"
 sizeBeforeCompression="208"
/></Header>
```

## Tokens

Three different token concepts were observed:

- `MessageToken`: framing/request correlation counter
- body `<Token>`: application request counter
- `<AuthToken>`: Steam authentication ticket encoded for BB3

Keepalive traffic advances `MessageToken` without advancing body `<Token>`.

## Steam AuthToken

Observed working BB3 AuthToken:

```text
raw Steam auth session ticket (270 bytes observed)
-> uppercase hexadecimal string (540 ASCII bytes)
-> Base64 (720 characters observed)
```

## Replay

Request:

```xml
<RequestDownloadReplay>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <GameId>BASE64(game UUID)</GameId>
</RequestDownloadReplay>
```

Response contains `ReplayData`.

Decode:

```text
ReplayData
-> base64
-> base64
-> zlib
-> XML
```

## Team creation

```xml
<RequestCreateTeam>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <Name>BASE64(name)</Name>
  <Race>7</Race>
  <Motto/>
  <IsCustom>false</IsCustom>
  <TeamRecruitmentId/>
  <ChosenSpecialRule/>
</RequestCreateTeam>
```

Response returns Base64 `IdTeam`.

## Player hire

```xml
<RequestHirePlayerFromPosition>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <TeamId>BASE64(team UUID)</TeamId>
  <Position>1102</Position>
</RequestHirePlayerFromPosition>
```

Response returns `IdPlayer`.

Verified: Wood Elf Wardancer = position `1102`.

## Fire players

```xml
<RequestFirePlayers>
  <Token>...</Token>
  <ShouldCache>false</ShouldCache>
  <IdTeam>BASE64(team UUID)</IdTeam>
  <IdPlayers/>
  <PlayerFireInfos>
    <PlayerFireInfosItem>
      <PlayerId>BASE64(player UUID)</PlayerId>
      <TemporarilyRetire>false</TemporarilyRetire>
    </PlayerFireInfosItem>
  </PlayerFireInfos>
</RequestFirePlayers>
```

## Team improvements

IDs:

- 1 Apothecary
- 2 Cheerleader
- 3 Assistant coach
- 4 Reroll
- 5 Dedicated fans

`Quantity` is a signed delta.

## Team text

- `RequestSetTeamName`: `IdTeam`, `Name` Base64
- `RequestSetTeamMotto`: `IdTeam`, `Motto` Base64
- `RequestSetPlayerName`: `IdPlayer`, `Name` Base64

## Cosmetics

Observed setter pattern:

```text
RequestSetTeamX
  IdTeam = Base64 team UUID
  IdX    = Base64 cosmetic UUID
```

Verified slots:

- JerseyPattern (`IdJerseyPattern`)
- PrimaryColor (`IdColor`, endpoint-specific)
- SecondaryColor (`IdColor`, endpoint-specific)
- TertiaryColor (`IdColor`, endpoint-specific)
- Cheerleader
- Coach
- Pitch
- Stadium
- CoachZone
- StaffZone
- CheerleaderZone
- Dice
- Ball

Note: colors are special: all three setters use `<IdColor>`, not
`<IdPrimaryColor>`, `<IdSecondaryColor>` or `<IdTertiaryColor>`.

## Collection discovery

Observed:

- `TeamCustoJerseyPattern`
- `TeamCustoCheerleader`

Collection results distinguish `CollectionItem.Id` from
`CollectionItemInstance.Id`. Do not assume every setter consumes the same ID
kind until matched against a specific collection response.

## Formations

Get:

```xml
<RequestGetTeamFormations>
  ...
  <TeamId>BASE64(team UUID)</TeamId>
</RequestGetTeamFormations>
```

Save/create:

```xml
<RequestSaveFormation>
  ...
  <Formation>
    <Id/>
    <TeamId>BASE64(team UUID)</TeamId>
    <Name>BASE64(name)</Name>
    <Data>BASE64(JSON)</Data>
    <Type>0</Type>
  </Formation>
</RequestSaveFormation>
```

Response returns generated `Formation/Id`.

Types:

- 0 Defensive
- 1 Offensive

Decoded `Data`:

```json
{
  "pitchMap": {
    "(X=7,Y=0)": {"number": 1}
  }
}
```

Remove:

```xml
<RequestRemoveFormations>
  ...
  <FormationIds>
    <FormationIdsItem>BASE64(formation UUID)</FormationIdsItem>
  </FormationIds>
  <TeamId>BASE64(team UUID)</TeamId>
</RequestRemoveFormations>
```

## Bootstrap / application-server discovery

Application endpoints are dynamically assigned. Observed bootstrap request:

```http
GET /lobby/bb3-win-steam-shipping-57968 HTTP/1.1
Host: bootstrap6-bb3.cyanide-studio.com:28006
```

Observed response body:

```text
tcp://app18.bb3.cyanide-studio.com:17010
```

The client should use the returned hostname directly (allowing DNS to resolve it) rather than cache a concrete IP address. Previously observed application ports included 17004, 17005, 17010 and 17011; these should not be treated as constants.

## Cosmetic collection tags

Verified through `RequestCollectionItems` followed by the corresponding setter:

```text
TeamCustoJerseyPattern   -> RequestSetTeamJerseyPattern
TeamCustoColor           -> RequestSetTeamPrimaryColor / SecondaryColor / TertiaryColor
TeamCustoCheerleader     -> RequestSetTeamCheerleader
TeamCustoCoach           -> RequestSetTeamCoach
TeamCustoPitch           -> RequestSetTeamPitch
TeamCustoStadium         -> RequestSetTeamStadium
TeamCustoCoachZone       -> RequestSetTeamCoachZone
TeamCustoStaffZone       -> RequestSetTeamStaffZone
TeamCustoCheerleaderZone -> RequestSetTeamCheerleaderZone
TeamCustoDice            -> RequestSetTeamDice
TeamCustoBall            -> RequestSetTeamBall
```
