# BB3 data sources

Status vocabulary used here:

- **VERIFIED** — implemented and verified against the described local archive
- **OBSERVED** — present in inspected game data, but not necessarily exposed semantically
- **UNKNOWN** — relationship or runtime meaning is unresolved

The game installation is an external input. This project does not redistribute
game data.

## Source precedence

1. **VERIFIED:** `bb3rulesengine.zip/Datas/BB3Rules.json` is the authoritative
   modern rules source.
2. **VERIFIED:** the remaining files in `bb3rulesengine.zip` supplement those
   rules; they do not replace them.
3. **VERIFIED:** `bb3.zip/Datas/Rules.json` uses an older, incompatible schema
   and must never silently override modern rules.
4. **OBSERVED:** `bb3.zip` contains supporting localization, predefined-team
   and shop/content data.

Raw access must remain available even when a typed semantic view exists. This
allows newer game versions to add fields without pybb3 discarding them.

## `bb3rulesengine.zip`

Resolved by `BB3_RULES_ENGINE_ZIP`, or beneath `BB3_PATH` at:

```text
BB3/Content/OfflineServer/bb3rulesengine.zip
```

| File | Status | Intended use |
|---|---|---|
| `Datas/BB3Rules.json` | VERIFIED | Current races, positions, skills, characteristics, rosters, special rules, casualties, inducements and team improvements |
| `Datas/Effects.json` | OBSERVED | Effect definitions referenced by rules and special play cards |
| `Datas/SPCs.json` | OBSERVED | Special Play Card definitions and effect relationships |
| `Datas/TextGeneration.json` | OBSERVED | Text-generation definitions; keep separate from gameplay rules |

## `bb3.zip`

Resolved by `BB3_DATA_ZIP`, or beneath `BB3_PATH` at:

```text
BB3/Content/OfflineServer/bb3.zip
```

| File | Status | Intended use |
|---|---|---|
| `Datas/BB3Rules.json` | OBSERVED | Packaged rules data; compare explicitly, never merge by filename alone |
| `Datas/Rules.json` | VERIFIED legacy schema | Compatibility/research only |
| `Datas/Locas.json` | OBSERVED | Localization identifiers and text |
| `Datas/PredefinedTeams.json` | OBSERVED | Predefined/offline team data |
| `Datas/ShopData.json` | OBSERVED | Shop items, categories and content relationships |

## ID boundaries

The following namespaces are distinct unless a captured or static relationship
proves otherwise:

- backend entity UUID
- rule `code`
- rule/table row identifier
- collection item UUID
- collection item instance UUID
- shop item identifier
- shop content row identifier
- asset/content identifier

**UNKNOWN:** a reliable modern mapping from backend collection UUIDs to static
shop/content assets has not been established.

## API behavior

`BB3Data.from_env()` resolves and validates archive locations. `BB3Rules`
provides raw table access through `records()`, `by_code()` and `by_name()`, plus
typed convenience views for positions, races, skills and team improvements.
Typed views retain their original `RuleRecord`.
