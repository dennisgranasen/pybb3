# BB3 management capture notes — 2026-09-06

This file records only semantics directly observed in the supplied capture.

## League languages

`RequestGetLeagueLangs` has no request-specific fields. `ResponseGetLeagueLangs` contains `Default` and repeated `Langs/LeagueLang` entries with integer `Id` and base64-encoded `Name`.

Observed IDs include:

- 0 — All languages
- 1 — Français
- 2 — English
- 3 — Deutsch
- 4 — Italiano
- 5 — Español
- 6 — Русский
- 7 — 日本語
- 8 — 繁體中文
- 9 — Polski
- 11 — Português (Brasil)
- 12 — 简体中文
- 13 — 한국어

## Competition gamer number

Request field: `IdCompetition` (base64).

Response fields:

- `Value` — gamer count
- `AIs` — AI count

## Competition tickets

Request fields:

- `Size`
- `Start`
- `CompetitionId` (base64)
- repeated `Type/TypeItem`
- repeated `Status/StatusItem`

Observed request values were `Type=[1, 0]` and `Status=[0]`. Their labels are not inferred.

Response contains separate `GamerTickets` and `TeamTickets` containers plus `Total`.

## Gamer valid teams

`RequestGetCompetitionGamerValidTeams` uses the normal team-list pagination/filter envelope plus `CompetitionId`. The response wraps each team with at least:

- `IsValid`
- repeated base64 `Hints`
- `IsFixable`
- `Team`

## League news

Observed CRUD operations:

- `RequestGetLeagueNews`: `Size`, `Start`, `LeagueId`
- `RequestCreateLeagueNews`: `LeagueId`, `Title`, `Description`
- `RequestUpdateLeagueNews`: `NewsId`, `Title`, `Description`
- `RequestDeleteLeagueNews`: `NewsId`

IDs/text fields are base64 encoded where applicable.

## Competition membership

Observed join request:

- `IdTeam` (base64)
- `IdCompetition` (base64)

Observed quit request:

- `ParticipantId` (base64)
- `CompetitionId` was empty in the captured official-client request

The update therefore permits an optional competition ID when quitting but defaults to the captured empty element.
