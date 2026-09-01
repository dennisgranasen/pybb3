# pybb3 competition/games capture update

Base: current `main` files from the previously verified merge-fix checkpoint,
plus the two manager/competition captures discussed on 2026-09-01.

Updated:
- `src/bb3/client.py`
- `src/bb3/models.py`
- `tests/test_competition_and_games.py` (new)
- `docs/messages.json`
- `docs/PROTOCOL.md`
- `BACKLOG.md`

Implementation:
- GetGames filter envelope + GameList/GameData
- GetGameResult + structured GameResult
- GetMatchStatistics + decoded statistic labels/values
- GetSppResult, GetMatchDiceRolls, GetBattlePassGameXpGain
- GetCompetitionFormats, GetAllRaces, GetAvailableGetGamesTeamValues
- GetCompetition + Competition model
- GetCompetitionSetting + complete captured CompetitionSetting model
- GetCompetitionMenu
- GetCompetitionDay
- GetCompetitionSchedule + schedule/contest/match models
- GetCompetitionRanking
- GetCompetitionParticipantsByGamer
- GetNextMatch
- GetCompetitionGamerRegisteredTeams
- GetCompetitionGamerBanDuration

Documentation also preserves earlier findings:
- no application-level logout request observed
- weekly free Warpstone status (`Amount=10`) is observed; claim mutation unknown
- reward/cosmetic account endpoints remain P3

Deliberately not inferred:
- numeric enum meanings for game type/outcome/order
- competition format/admission/timer/status enum meanings
- encoding semantics for non-empty GetGames name filters
- FreeVc claim endpoint

Security:
- no raw capture or account/Steam identifiers are included
- tests use sanitized synthetic UUID/name fixtures only
