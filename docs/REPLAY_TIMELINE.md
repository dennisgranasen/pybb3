# Replay timeline

`Replay.timeline()` interprets protocol messages in order and combines them
into match-domain events. The output is intended for statistics, match reports
and UI use; it is not merely a renamed dump of the replay XML.

```python
from bb3.replay import Replay

timeline = Replay.from_bbr(open("match.bbr", "rb").read()).timeline()
timeline.save("match.timeline.json")
```

The top-level object contains `before_match`, `turns`, `after_match`, and the
flat `events` list. Each playable team turn carries its global ordinal,
`team_id`, `half`, drive number and `team_turn` (1--8 within the half). Setup
and kick-off sequences remain available in the flat list but are not mixed
into the following playable turn. A core event identifies who acted and who
was affected:

```json
{
  "type": "block",
  "actor": {"kind": "player", "id": 40, "name": "Attacker", "team_id": 1},
  "target": {"kind": "player", "id": 11, "name": "Defender", "team_id": 0},
  "outcome": "defender_down",
  "effects": [
    {"type": "push", "subject": {"id": 11}},
    {"type": "knockdown", "subject": {"id": 11}},
    {"type": "armour_roll", "subject": {"id": 11}, "outcome": true},
    {"type": "injury", "subject": {"id": 11}, "outcome": "stunned"}
  ],
  "source_sequences": [21, 22, 23]
}
```

A block can span several `EventExecuteSequence` elements. A
`ResultBlockRoll` can be followed by push/follow-up interaction in one sequence
while the matching `ResultBlockOutcome` arrives in the next sequence. The
continuation is correlated by attacker/defender rather than by blindly trusting
the last `PlayerStep` in the later sequence; BB3 can already have started a
subsequent catch or other step there. Once the outcome arrives the completed
block is reduced before BoardState-derived possession changes. Low-level decoded
messages remain under `details.messages` as evidence and for future protocol
research.

Currently reduced core events include movement/falls, blocks and their effects,
pass/catch/handoff/interception/foul actions identified by `StepType`,
kick-off/weather events, turn endings and concessions. Unsupported protocol
messages are retained when they form part of a core event but are not emitted
as noisy standalone timeline entries.

## Stateful cause tracking and fallback

The parser keeps the active team/player, declared `SequenceType`, active special
card and current ball carrier while consuming replay steps in order. This lets
damage after a foul, crowd surf, wizard or other multi-step action retain its
cause. Special-card consequences use `caused_by` to refer to the corresponding
`special_card` event.

Changes to `BoardState/Ball` produce `possession_gained`, `ball_loose` or
`possession_changed`. Every known `StepType` has a semantic fallback, so newer
skills and special actions still identify actor and target. Relevant unknown
result messages become `unclassified` events with their complete decoded
evidence and are counted in `unresolved`; they are never silently discarded.
Pure movement has no semantic `target`; a target carried by the wire-level
`PlayerStep` is retained as `details.action_target` for a later block, blitz or
other declared action.

Kick-off `DEVIATE` rolls are emitted as `kickoff_deviation`. Activation
negatraits are emitted as `negatrait_check` with the specific rule in
`details.trait`; successful checks remain available to semantic consumers.
Animal Savagery keeps the outcomes `passed`, `teammate_hit`, or
`activation_lost`; the declared action target, eligible teammates, selected
victim and resulting armour/injury effects are retained. A failed Foul
Appearance check emits the declared action (for example `block`) with outcome
`prevented`, its actor and intended target, and a `foul_appearance` effect.

The state model and replay enum tables are based on observed replays and
corroborated against the MIT-licensed
[ZFLStats BloodBowl3 parser](https://github.com/sjogrenm/ZFLStats/tree/main/BloodBowl3).

Run the converter with:

```console
python tools/replay_timeline.py match.bbr -o match.timeline.json
```

## Compact narrative export

For LLM input, use the non-duplicated narrative projection instead of the full
research/debug representation:

```python
timeline.save_narrative("match.narrative.json")
```

Or from the command line (using `-o` writes UTF-8 directly and avoids
PowerShell redirection changing the encoding):

```console
python tools/replay_timeline.py match.bbr --narrative -o match.narrative.json
```

It stores each event once, embeds turn context directly in playable events,
uses compact `{kind, id}` participant references, summarizes the final score,
removes raw protocol messages and omits routine successful movement without
effects. Pure phase markers, normal turn endings, effect-free stand-ups and the
large raw `inducements_data` payload are also omitted. Names remain available
in `match.teams` and `match.players`.

Optional switches restore information for positional narration or debugging:

```python
text = timeline.to_narrative_json(
    include_moves=True,
    include_evidence=True,
    indent=2,
)
```

The narrative format is identified by `format: pybb3-narrative-timeline` and
`version: 1`. Event array order remains canonical; event IDs are references,
not a sorting key.

Every pass/fail dice test is exposed as a named `checks` entry. A check contains
its purpose (`dodge`, `rush`, `tentacles`, `bone_head`, and so on), subject,
effective target number, every attempt in order, final outcome, and reroll
information. Team rerolls are identified from the explicit team-reroll
question/result messages; skill rerolls are kept as skill-sourced attempts and
do not become team rerolls merely because a team reroll was also available.
When BB3 supplies `Difficulty`, pybb3 uses it as `required` and
retains the unmodified `Requirement` as `base_required` when the two differ.
Never present an attempt merely as “Roll: N”. Roll-derived entries are removed
from narrative `effects` when represented by `checks`; effects are reserved for
remaining consequences such as pushes, knockdowns and removals.

```json
{
  "type": "move",
  "outcome": "completed",
  "checks": [
    {
      "type": "dodge",
      "required": 2,
      "attempts": [{"dice": [4], "outcome": "passed"}],
      "outcome": "passed"
    },
    {
      "type": "rush",
      "required": 2,
      "attempts": [
        {"dice": [1], "outcome": "failed"},
        {"dice": [5], "outcome": "passed", "reroll": "team"}
      ],
      "outcome": "passed",
      "reroll_offered": ["team"],
      "reroll_used": true
    }
  ]
}
```

## Regression testing with local replays

Synthetic unit tests cover protocol shapes and reducer edge cases. A separate
local replay suite can additionally run semantic invariants against real `.bbr`
files without committing those replays:

```console
pytest -m testdata -v
```

Files under `testdata/*.bbr` are intentionally gitignored. The suite checks
cross-event invariants such as unique/valid references, turn ownership, reroll
consistency, movement-check subjects, turnover causes, pass-group context and
the set of unresolved protocol message types.

`unresolved` is deliberately retained as a forward-compatibility signal. New
message types should be inspected and either normalized or explicitly classified
rather than silently added to a permanent ignore list.
