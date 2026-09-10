# pybb3 replay timeline format

Status: draft specification for the timeline JSON produced by
`Replay.timeline().to_json()` after the v7 timeline patches.

This document is intended to be sufficient input for an LLM or deterministic
program that turns a pybb3 timeline into a factual, chronological match
narrative. Consumers must follow the semantics and uncertainty rules below and
must not infer facts that are absent from the data.

## 1. Purpose

The timeline is a semantic projection of a Blood Bowl 3 replay. Low-level replay
messages are read in order and, where possible, combined into domain events such
as movement, blocks, touchdowns, ball-possession changes, injuries and special
rules.

The format serves two simultaneous purposes:

1. `events` and `turns` provide normalized events suitable for narration and
   statistics.
2. `details.messages` preserves the decoded protocol evidence behind an event.

The normalized fields are the preferred source. Raw messages are evidence and a
forward-compatibility mechanism; they should only be interpreted when the
normalized event does not answer the question.

## 2. Top-level structure

```json
{
  "before_match": {
    "date": "string or null",
    "teams": ["Participant"],
    "players": ["Participant"],
    "events": ["BeforeMatchEvent"]
  },
  "turns": ["TimelineTurn"],
  "after_match": {"raw EndGame data": "..."},
  "events": ["TimelineEvent"],
  "unresolved": {
    "ProtocolMessageName": 3
  }
}
```

### `before_match`

- `date`: replay date when supplied by the replay.
- `teams`: known teams, represented as participants.
- `players`: known players, represented as participants.
- `events`: pre-match protocol events such as inducements, fan factor, kicking
  choice and setup. These currently retain protocol-oriented event names and
  payloads rather than full semantic summaries.

### `turns`

Playable team turns. Setup and kick-off pseudo-turns are excluded. In a normal
completed match there are 32 entries: eight turns per team per half.

### `after_match`

Decoded `EndGame` data. This is currently a mostly raw tree and may contain the
score, team results, player results, SPP, winnings, casualties and other
post-match data. Its internal shape follows the source replay and is not yet a
stable normalized schema.

### `events`

The canonical full event stream. It includes playable events as well as match
phase, setup/kick-off and match-ending events that may not belong to a playable
turn.

Array order is canonical. Do not sort by `id`: pending protocol sequences can be
reduced immediately before an already-created outer event, so IDs are unique
references but are not guaranteed to be in ascending chronological order.
`clock` can also be equal for multiple events.

### `unresolved`

A count by protocol message name for relevant messages that could not be
classified. An empty object means that all messages which the parser considers
relevant were classified; it does not prove that every possible BB3 mechanic is
known. A narrative generator should report or log non-empty values rather than
silently invent an interpretation.

## 3. Common data types

### Participant

```json
{
  "kind": "player | team",
  "id": 37,
  "name": "Rok-rok 'The pestilent'",
  "team_id": 1
}
```

| Field | Type | Meaning |
|---|---|---|
| `kind` | string | `player` or `team`. |
| `id` | integer or string | Replay-local participant identifier. |
| `name` | string or null | Decoded display name, if known. |
| `team_id` | integer or null | Team slot, normally `0` or `1`. For a team participant it equals `id`. |

Identity must be based on `(kind, id)`, not on `name`. Names are display data and
need not be unique.

### TimelineEffect

```json
{
  "type": "injury",
  "subject": {"kind": "player", "id": 42, "name": "Mephyn", "team_id": 1},
  "outcome": "stunned",
  "details": {}
}
```

| Field | Type | Meaning |
|---|---|---|
| `type` | string | Effect category. Extensible. |
| `subject` | Participant or null | Participant affected by the effect. |
| `outcome` | string, integer, boolean or null | Type-specific result. |
| `details` | object | Protocol evidence and additional fields. |

An effect's `subject` is not necessarily the parent event's `target`. For
example, a failed Animal Savagery check during a blitz can affect a teammate,
while the intended blitz target is stored separately.

### TimelineEvent

```json
{
  "id": 250,
  "type": "animal_savagery",
  "clock": 3548397,
  "actor": {"kind": "player", "id": 37, "name": "Rok-rok", "team_id": 1},
  "target": {"kind": "player", "id": 46, "name": "Yesh", "team_id": 1},
  "outcome": "teammate_hit",
  "effects": [],
  "source_sequences": [323, 324, 325, 326],
  "caused_by": null,
  "details": {}
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Unique event reference. Do not use it for ordering. |
| `type` | string | Normalized event category. Extensible. |
| `clock` | integer or null | Replay clock supplied by BB3. Treat as an ordering/context value, not necessarily elapsed real-world milliseconds. |
| `actor` | Participant or null | Participant performing or initiating the action. |
| `target` | Participant or null | Direct recipient or selected victim of the normalized event. |
| `outcome` | string, integer, boolean or null | Type-specific result. |
| `effects` | array of TimelineEffect | Consequences produced or observed within the event. |
| `source_sequences` | array of integers | Low-level replay sequences combined into this event. |
| `caused_by` | event ID or null | Explicit causal link, currently used principally for special-card consequences. |
| `details` | object | Type-specific details plus raw evidence. |

`null` means unknown or inapplicable. It must not be narrated as a known player,
result or causal relation.

### TimelineTurn

```json
{
  "number": 17,
  "team_id": 1,
  "half": 2,
  "drive": 3,
  "team_turn": 1,
  "events": ["TimelineEvent"]
}
```

| Field | Type | Meaning |
|---|---|---|
| `number` | integer | Global playable-turn ordinal in this timeline. |
| `team_id` | integer or null | Team whose turn it is. |
| `half` | integer or null | Match half, normally `1` or `2`. |
| `drive` | integer or null | Drive ordinal. It increments when a new setup phase begins, including after touchdowns and at halftime. |
| `team_turn` | integer or null | That team's turn within the half, normally `1` through `8`. |
| `events` | array | Events belonging to the playable turn. |

The same logical events also appear in the top-level `events` stream. They are
not additional occurrences and must not be narrated twice. Match them by `id`.

## 4. Actor, target and effect rules

Use these rules literally:

- `actor` answers “who initiated or performed this normalized action?”
- `target` answers “who was the direct intended or selected recipient of this
  normalized action?”
- `effects[].subject` answers “who actually suffered or received this
  consequence?”
- `caused_by` is the only explicit cross-event causal link.
- `details.action_target` is the intended target of the declared larger action
  when the current event has another target. For example, Animal Savagery may
  target a teammate while `action_target` remains the opposing blitz target.
- A plain `move` deliberately has `target: null`. If its wire-level step carried
  a future action target, that participant is retained as
  `details.action_target`; do not narrate movement “against” that participant.
- `ball_loose.target` is the previous carrier. Its `actor` is the best-known
  active player and should not automatically be described as having caused the
  ball loss unless surrounding action data supports that statement.

## 5. Stable core event semantics

Event type strings are extensible. A consumer must tolerate unfamiliar types
and fall back to a neutral description or raw evidence.

### Match and turn context

| Type | Meaning |
|---|---|
| `match_start` | Match-start marker. |
| `match_end` | Match-end marker. |
| `new_game_phase` | Rules-engine phase transition; details retain the numeric phase. |
| `turn_end` | End of a turn or rules-engine pseudo-turn. `outcome` is commonly `completed` or `turnover`. Use membership in `turns` to distinguish playable turns. |
| `face_up_stunned_players` | Start-of-turn recovery of stunned players. |
| `concession` | A team or gamer concedes. |

### Movement and ball handling

| Type | Meaning and outcome |
|---|---|
| `move` | Movement segment by `actor`; `outcome` is `completed` or `failed`. Consequences such as `dodge`, `gfi`, injury or removal are effects. Consecutive moves by one player should normally be summarized. |
| `stand_up` | Player stands up. Checks can appear as effects. |
| `pass` | Pass attempt from actor to target. Outcome may be boolean or null; inspect effects/details. |
| `catch` | Catch attempt. |
| `handoff` | Handoff attempt. |
| `interception` | Interception attempt. |
| `throw_team_mate` | Throw Team-mate action. |
| `possession_gained` | `actor` becomes ball carrier. |
| `possession_changed` | `actor` is new carrier and `target` is previous carrier. |
| `ball_loose` | `target` was the carrier and the ball is no longer held. |
| `bounce`, `scatter`, `throw_in`, `ball_action` | Ball displacement or generic ball operation. |

Common movement/ball effects include `dodge`, `gfi`, `pick_up`, `catch`,
`pass`, `interception`, `bounce`, `scatter`, `deviate` and `throw_in`.
Boolean roll outcomes mean the protocol roll was successful (`true`) or failed
(`false`) in that effect's context.

### Blocks

```json
{
  "type": "block",
  "actor": "attacker participant",
  "target": "defender participant",
  "outcome": "defender_pushed_down",
  "effects": [
    {"type": "push", "subject": "defender"},
    {"type": "knockdown", "subject": "defender"},
    {"type": "armour_roll", "subject": "defender", "outcome": true},
    {"type": "injury", "subject": "defender", "outcome": "stunned"}
  ]
}
```

Known block outcomes:

| Outcome | Meaning |
|---|---|
| `attacker_down` | Attacker knocked down. |
| `both_down` | Both players knocked down unless later effects/skills modify it. |
| `both_wrestle_down` | Both players brought down through Wrestle. |
| `both_standing` | Neither player falls. |
| `pushed` | Defender pushed but not knocked down. |
| `defender_down` | Defender knocked down. |
| `defender_pushed_down` | Defender pushed and knocked down. |
| `prevented` | A declared block did not happen, for example because Foul Appearance failed. Do not count this as an executed block. |

Relevant effects:

- `push`: subject was pushed.
- `knockdown`: subject was knocked down.
- `wrestle_down`: subject was brought down through Wrestle.
- `armour_roll`: `true` means armour was broken; `false` means it held.
- `injury`: normalized outcome such as `stunned`, `ko`, `badly_hurt` or
  `casualty` where known.
- `casualty`: detailed casualty outcome.
- `player_removed`: player left the pitch; outcome describes the destination or
  situation, and `details.status_name` describes status.
- `apothecary`, `sent_off`, `raised_dead`: corresponding consequences.

### Touchdowns

`touchdown.actor` is the scoring player where known. A touchdown is normally
followed by `ball_loose`, setup and kick-off events. Do not describe that
post-touchdown ball loss as a fumble.

### Kick-off

| Type | Meaning |
|---|---|
| `kickoff_deviation` | Initial kicked-ball deviation (`RollType 26`). `actor` is the kicking team. `details.from`, `details.to` and `details.roll` preserve the protocol fields. The exact semantic labels “aimed square” and “landing square” are not yet guaranteed, so retain neutral `from`/`to` wording. |
| `kick_off_table` | Kick-off table event. Details contain protocol result data. |
| `weather_roll` | Weather roll/event. |
| `brilliant_coaching`, `cheering_fans`, `officious_ref`, `blitz` | Named kick-off or phase events when exposed by BB3. A `blitz` phase event must not be confused with a player's declared Blitz action in `details.declared_action`. |

Later `bounce`, `catch`, `touchback`, possession or ball events determine where
the ball finally ends up. Do not equate the deviation destination with final
possession.

### Animal Savagery

Animal Savagery may be a standalone event or a check effect attached to an
action that completes in the same reduced sequence, such as `stand_up`.

Standalone form:

```json
{
  "type": "animal_savagery",
  "actor": "player taking the check",
  "target": "selected teammate or null",
  "outcome": "passed | teammate_hit | activation_lost",
  "effects": [],
  "details": {
    "declared_action": "move | block | blitz | ...",
    "action_target": "original action target or null",
    "eligible_targets": ["teammates that could be selected"],
    "check": {"Requirement": "4", "Dice": "...", "Outcome": "..."}
  }
}
```

Outcome rules:

- `passed`: the Animal Savagery roll succeeded; `target` is null and the
  declared action may continue.
- `teammate_hit`: the roll failed and `target` is the selected teammate. Effects
  can include `knockdown`, `armour_roll`, `injury` and `player_removed`. The
  original action may subsequently continue against `details.action_target`.
- `activation_lost`: the roll failed and no valid teammate was selected; the
  declared action does not continue.

When Animal Savagery appears as an effect on `stand_up` or another completed
event, the effect's outcome gives the check result while the parent event
describes the action that actually happened.

### Foul Appearance

A failed Foul Appearance check is represented as the declared action with
`outcome: "prevented"`:

```json
{
  "type": "block",
  "actor": "player attempting the block",
  "target": "player with Foul Appearance",
  "outcome": "prevented",
  "effects": [
    {
      "type": "foul_appearance",
      "subject": "attempting player",
      "outcome": "failed",
      "details": {
        "source": "player with Foul Appearance",
        "Requirement": "2",
        "Dice": "..."
      }
    }
  ],
  "details": {"declared_action": "block"}
}
```

The action was attempted but not executed. A later block by another player is a
new event and must not be merged with this one.

### Fouls and unusual actions

Known or fallback event types can include `foul`, `stab`, `vomit`, `chainsaw`,
`chainsaw_foul`, `jump_over`, `land`, `bounce_player`, `fireball`, `zap`,
`treacherous_trap`, `geyser`, `hypnotic_gaze`, `tentacles`, `shadowing`,
`throw_a_rock` and `multiple_block`. Availability in the schema does not mean a
given mechanic was observed in a particular replay.

Special cards are emitted as `special_card`. Consequences linked through
`caused_by` should be narrated as consequences of that card. Without an
explicit `caused_by` link or strong normalized action context, do not invent a
cause from clock proximity alone.

## 6. `details` and raw message evidence

Most reduced events contain:

```json
{
  "details": {
    "messages": [
      {
        "type": "ResultRoll",
        "data": {
          "Requirement": "4",
          "Dice": {"Die": {"DieType": "0", "Value": "5"}},
          "RollType": "36",
          "Outcome": "1"
        }
      }
    ],
    "declared_action": "blitz"
  }
}
```

Important properties:

- Raw scalar values are commonly strings even when numeric.
- Repeated XML elements become arrays; single elements can remain objects.
- Empty XML values can become empty strings.
- The internal protocol schema is not stable API. Prefer normalized fields.
- `QuestionTeamRerollUsage` plus `ResultTeamRerollUsage` reveals whether a
  reroll was offered and used. Do not say a reroll was used unless `Used`
  confirms it.
- `declared_action` is derived from `SequenceType` and can describe a broad
  activation (`move`) while the completed step is more specific (`stand_up`).

## 7. Recommended narrative construction

### Step 1: establish identities and result

Build lookup tables from `before_match.teams` and `before_match.players`. Read
score and post-match facts from `after_match`, but only state fields that can be
identified unambiguously.

### Step 2: build turn context

Create a map from each turn event ID to:

```text
half, drive, team_turn, active team
```

Then traverse the top-level `events` array in its existing order. This preserves
kick-off and match-phase events while allowing playable events to be labelled
with their turn.

### Step 3: aggregate low-value movement

Do not narrate every `move` as a separate sentence. Combine consecutive movement
events by the same actor until one of these occurs:

- another actor acts;
- a roll or meaningful effect occurs;
- a block, pass, foul, ball event, touchdown or turn end occurs;
- the player reaches an important square if positional analysis is available.

Example neutral summary: “Rok-rok moved into position.” Only describe a dodge,
rush/GFI, pickup or failure when the corresponding effect supports it.

### Step 4: compose action chains

Combine adjacent events when normalized fields establish a shared action:

- Animal Savagery followed by a block/blitz by the same actor, using
  `details.declared_action` and `details.action_target`.
- Block plus its embedded push, knockdown, armour, injury and removal effects.
- Ball loss followed by bounce, catch, possession gain or touchdown reset.
- Special-card event plus events whose `caused_by` points to it.

Do not merge solely because two events share a clock.

### Step 5: choose narrative importance

High priority:

- touchdowns and final score;
- turnovers and possession changes;
- casualties, KOs, removals and send-offs;
- successful or prevented blocks that materially affect play;
- failed negatrait or Foul Appearance checks;
- passes, interceptions, fouls and special cards;
- kick-off table results with material effects.

Medium priority:

- armour breaks without lasting removal;
- important pushes, knockdowns, pickups, catches and failed dodges/rushes;
- drive and half transitions.

Low priority:

- routine movement;
- successful routine rolls that produce no tactical change;
- raw phase/timer events.

### Step 6: preserve uncertainty

Use cautious wording when:

- `actor`, `target` or effect subject is null;
- an outcome is null or numeric rather than normalized;
- `unresolved` is non-empty;
- only raw protocol fields support a claim;
- causation is inferred from proximity rather than `caused_by` or shared action
  metadata.

Suitable wording includes “the replay records”, “appears to”, “the ball became
loose”, or “an unidentified player”. Never manufacture player names, dice,
injuries, causality or tactical intent.

## 8. Validation invariants

A consumer or test suite should check:

1. Event IDs are unique.
2. Every `caused_by` value refers to an existing event ID.
3. Event-array order is preserved.
4. An event included in `turns` matches the same top-level event ID and is not
   narrated twice.
5. `team_turn` normally lies in `1..8` and `half` in `1..2` for a regulation
   match; variants or future rules may extend this.
6. Player participants with known `team_id` refer to a known team slot.
7. A completed block has actor and target where the replay identified them.
8. A block with outcome `prevented` is not counted as an executed block.
9. `animal_savagery` with outcome `teammate_hit` has a teammate target and a
   `knockdown` effect for that target.
10. `unresolved` is surfaced to diagnostics.

## 9. Minimal LLM instruction template

The following can be placed before a timeline JSON:

```text
You are given a pybb3 replay timeline conforming to TIMELINE_FORMAT_SPEC.md.
Write a chronological Blood Bowl match narrative.

Use the top-level events array in its existing order and use turns only to add
half, drive and team-turn context. Never narrate the duplicated turn copies as
additional events. Identify people by participant kind/id and display their
names when available.

Prioritize touchdowns, ball possession, turnovers, blocks with meaningful
effects, injuries/removals, fouls, passes, special rules and kick-off results.
Compress routine consecutive movement. For every action distinguish actor,
direct target and effect subjects. Treat outcome=prevented as an attempted but
unexecuted action.

Combine Animal Savagery with its declared action when action_target and the
following event support the connection. Describe a selected teammate and all
armour/injury/removal effects before continuing the original action. Do not
invent causal links that are not supported by caused_by, normalized fields or
shared action metadata.

If unresolved is non-empty, mention that some protocol events could not be
interpreted. Do not guess missing names, results, dice or intent. Finish with a
concise match summary based on after_match and the normalized touchdown and
removal events.
```

## 10. Versioning guidance

This is an additive, extensible format. Future parser versions may add event
types, effect types and detail fields. Consumers should:

- ignore unknown object fields;
- retain unknown event/effect types;
- avoid closed exhaustive enums in deserialization;
- key behavior on normalized semantics, not raw message layout;
- record the parser/spec version externally until a top-level version field is
  added.

Recommended future addition:

```json
{
  "format": "pybb3-replay-timeline",
  "version": 1
}
```
