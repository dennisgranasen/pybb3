# Update manifest

Based on current `dennisgranasen/pybb3` main plus captures through 2026-09-01.

Modified:
- src/bb3/client.py
- src/bb3/models.py
- src/bb3/__init__.py
- docs/PROTOCOL.md
- docs/messages.json
- BACKLOG.md
- README.md

Added:
- tests/test_advancement_and_roster.py
- tests/fixtures/team_roster.xml
- tests/fixtures/player_improvements.xml
- tests/fixtures/characteristic_roll.xml

Not changed:
- src/bb3/rules.py (already has skill_by_code)
- pyproject.toml (already registers live/destructive markers)
