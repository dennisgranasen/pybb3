# Merge-conflict repair package

Built from the intended pybb3 protocol update and rechecked against the current
GitHub `main` after conflict resolution.

Files in this package:
- src/bb3/client.py
- docs/messages.json
- docs/PROTOCOL.md
- BACKLOG.md
- README.md

Repairs:
- restores `_assert_success()` Result=0 handling and removes unreachable code
- removes duplicated merge fragments
- restores verified `RequestGetTeamRoster` / `IdTeam` catalog entry
- restores player advancement, DeleteTeam and team-listing message catalog entries
- removes stale roster-capture wording
- marks ResponseGetTeamRoster as already verified
- demotes GetGames/GetGameResult/MatchResult because those are available via API
