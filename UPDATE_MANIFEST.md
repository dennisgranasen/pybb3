# Capture documentation update

Updated from current pybb3 main documentation plus the
`stream-mgr-logout.bin` parser output.

Files:
- BACKLOG.md
- docs/PROTOCOL.md
- docs/messages.json

Changes:
- document that no application-level logout/disconnect request was observed
- document observed league search request/response
- document weekly free Warpstone status (`Amount=10`, `Retrieved`, `Id`,
  `AvailableAt`) and keep the unknown claim request as research
- add Battle Pass / gamer progression reward unlocks as P3 conveniences
- note gamer avatar/banner/frame/title customization as intentionally very low
  priority
- add only protocol fields actually present in reviewed captures; unknown request
  bodies remain empty rather than guessed
