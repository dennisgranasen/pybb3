# Capture-verified protocol enums

This file names only values whose meaning was displayed by the official BB3
client in the 2026-09-01 league/competition capture. The corresponding Python
`IntEnum` classes live in `bb3.enums`. Unresolved numeric fields remain integers.

## Competition format (`Format`)

| Value | Python name | Official-client label |
| ---: | --- | --- |
| 1 | `CompetitionFormat.KNOCK_OUT` | Knock Out |
| 2 | `CompetitionFormat.ROUND_ROBIN` | Round Robin |
| 3 | `CompetitionFormat.WISSEN` | Wissen |

## Admission mode (`AdmissionMode`)

| Value | Python name | Official-client label |
| ---: | --- | --- |
| 1 | `AdmissionMode.FREE` | Free |
| 2 | `AdmissionMode.TICKETS` | Tickets |
| 3 | `AdmissionMode.INVITATION_ONLY` | Invitation only |

## Timer ID (`TimerId`)

| Value | Python name | Official-client label |
| ---: | --- | --- |
| 2 | `TimerId.STRICT_ONE_MINUTE` | Strict 1 min |
| 6 | `TimerId.UNLIMITED` | Unlimited time |

`TimerId=1` was displayed as `Competitive`, but the capture did not expose its
precise clock/bonus-time parameters. It is intentionally not assigned a Python
enum member yet.

## Competition status (`Status`)

| Value | Python name | Official-client label |
| ---: | --- | --- |
| 1 | `CompetitionStatus.CREATED` | Created |

Statuses 2 and 3 were used as filters but were not labelled in this capture.

## League member roles

| Value | Python name | Server label |
| ---: | --- | --- |
| 3 | `LeagueRole.ADMIN` | Admin |
| 4 | `LeagueRole.MEMBER` | Member |

## Board permissions

Permission names below are decoded server labels. Some were explicitly marked
unlocalized by the server, but their identifiers and symbolic names are stable
observations from the capture.

| Value | Python name | Decoded server name |
| ---: | --- | --- |
| 8 | `CAN_UPDATE_SETTING` | CanUpdateSetting |
| 16 | `CAN_READ_LEAGUE_TICKETS` | CanReadLeagueTickets |
| 17 | `CAN_OFFER_LEAGUE_TICKET` | CanOfferLeagueTicket |
| 18 | `CAN_ACCEPT_LEAGUE_TICKET` | CanAcceptLeagueTicket |
| 19 | `CAN_DELETE_LEAGUE_TICKET` | CanDeleteLeagueTicket |
| 20 | `CAN_REFUSE_LEAGUE_TICKET` | CanRefuseLeagueTicket |
| 21 | `CAN_UPDATE_LEAGUE_SETTING` | CanUpdateLeagueSetting |
| 22 | `CAN_END_LEAGUE` | CanEndLeague |
| 23 | `CAN_KICK_LEAGUE_MEMBER` | CanKickLeagueMember |
| 24 | `CAN_CREATE_LEAGUE_COMPETITION` | CanCreateLeagueCompetition |
| 25 | `CAN_GET_LEAGUE_MEMBERS` | CanGetLeagueMembers |
| 26 | `CAN_MANAGE_LEAGUE_NEWS` | CanManageLeagueNews |
| 27 | `CAN_GET_LEAGUE_NEWS` | CanGetLeagueNews |

## Verified value lists without semantic enum names

- `RequestGetCompetitionContestFormats(CompetitionFormat=1)` returned
  `2, 3, 4, 5`; their labels are not known.
- Team-count choices depend on competition format:
  - Knock Out: powers of two from 2 through 256.
  - Round Robin: every integer from 2 through 128.
  - Wissen: even integers from 2 through 128.
- Team-value extrema returned:
  `900000, 1000000, 1500000, 1600000, 1700000, 1900000, 2000000,
  2500000, 3500000, 5000000`.
- Redraft treasury-cap choices are 1,000,000 through 1,600,000 in 50,000
  increments; the observed redraft-period range was 0 through 30.
