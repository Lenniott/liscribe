# Agent Prompt — Add Word Replacement to Liscribe v2 Plan

## Your task

Add a new feature — **Word Replacement** — to `docs/plan.md` and `docs/rubric.md`.
Do not implement any code. Do not modify any existing files other than those two docs.
Your output is documentation only.

---

## What the feature is

Liscribe produces text from speech. The user has no keyboard during recording,
so certain characters and formatting cannot be spoken naturally. Word Replacement
solves this by substituting spoken trigger words with defined output text at the
point of text production.

**Example:** the user says "hashtag project" — the transcript reads "# project".

### Three replacement types

**1. Simple replacement**
A single spoken word is replaced by a symbol or short string.
```
spoken:  "hashtag"
output:  "#"
```

**2. Newline replacement**
A spoken word produces a symbol followed by a line break.
```
spoken:  "newline"
output:  "\n"
```

**3. Wrap replacement**
A spoken word wraps the word or phrase that immediately follows it.
The user defines a prefix and a suffix.
```
spoken:  "bold hello world"
output:  "**hello world**"   (where prefix="**" suffix="**")

spoken:  "highlight important"
output:  "==important=="     (where prefix="==" suffix="==")
```
For wrap type: replacement applies to the next contiguous word only,
unless the user defines a phrase boundary (e.g. "bold start ... bold end").
Keep the initial implementation simple — next word only.

### Matching rules
- Matching is always case-insensitive
- Trigger words must be whole words — not substrings
  (`"hash"` must not match inside `"hashtag"`)
- Replacement happens after transcription, before output is written to file
  or pasted (for Dictate)

### Scope
Each replacement rule has a scope setting:
- **Transcripts** — applies to Scribe and Transcribe output files
- **Dictate** — applies to Dictate paste output
- **Both** — applies everywhere

### Default rules (ship with the app, user can edit or delete)

| Trigger | Output | Type | Scope |
|---|---|---|---|
| hashtag | # | simple | both |
| todo | [ ] | simple | both |
| open bracket | [ | simple | both |
| close bracket | ] | simple | both |
| dash | - | simple | both |
| newline | \n | newline | both |

---

## Where this lives in the architecture

Word Replacement is a pure text post-processing step. It sits between
transcription output and file write / paste.

- **Engine:** add `src/liscribe/replacements.py` — pure function, no I/O,
  takes text + rules, returns transformed text. This is an engine-layer file.
  It has no knowledge of config, UI, or services.
- **Service:** `ConfigService` stores and retrieves the replacement rules list.
- **Integration points:**
  - `output.py` calls `replacements.apply(text, rules)` before writing markdown
  - `DictateController` calls `replacements.apply(text, rules)` before paste
- **UI:** new tab in Settings panel — "Replacements"

---

## What to add to docs/rubric.md

Add a new section **Word Replacement** with:

### Feature description
- Spoken trigger words are substituted with defined output at point of production
- Three types: simple, newline, wrap (next word only)
- Case-insensitive matching, whole-word only
- Per-rule scope: Transcripts, Dictate, or Both
- Ships with 6 default rules (listed above)
- User can add, edit, and delete rules in Settings → Replacements

### Settings — Replacements tab sketch
```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General     │  Word Replacements                     │
 │  Models      │                                        │
 │  Hotkeys     │  Trigger       Output    Type   Scope  │
 │  Deps        │  ──────────────────────────────────    │
 │  Replacements│  hashtag       #         simple  both  │
 │  Help    ◀   │  todo          [ ]       simple  both  │
 │              │  open bracket  [         simple  both  │
 │              │  close bracket ]         simple  both  │
 │              │  dash          -         simple  both  │
 │              │  newline       ↵         newline both  │
 │              │                                        │
 │              │  [ + Add replacement ]                 │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

Add rule form (shown inline when + is clicked):
```
 Trigger word   [ _____________ ]
 Type           ( ) Simple  ( ) Newline  ( ) Wrap
 Output / Prefix [ _____________ ]
 Suffix (wrap)   [ _____________ ]   (shown only for Wrap type)
 Scope          ( ) Transcripts  ( ) Dictate  (●) Both
 [ Save ]  [ Cancel ]
```

### Success criteria
- [ ] Default rules are present on first launch and cannot be lost by accident
- [ ] User can add a rule with trigger, type, output, and scope
- [ ] User can edit any rule including defaults
- [ ] User can delete any rule; deleting a default shows a confirmation
- [ ] Case-insensitive whole-word matching — `Hashtag` and `HASHTAG` both match
- [ ] Simple replacement: trigger word replaced by output string
- [ ] Newline replacement: trigger word replaced by output + line break
- [ ] Wrap replacement: trigger word removed, following word wrapped in prefix/suffix
- [ ] Scope Transcripts: applies to Scribe and Transcribe file output only
- [ ] Scope Dictate: applies to Dictate paste only
- [ ] Scope Both: applies everywhere
- [ ] Replacements applied after transcription, before file write or paste
- [ ] Rules persist across restarts
- [ ] Empty trigger or empty output shows a validation error — never saves silently

---

## What to add to docs/plan.md

### Phase status table
Add a new row:
```
| 4b | Word Replacement | ⬜ |
```
This phase sits between Phase 4 (Scribe) and Phase 5 (Transcribe) because
Scribe is the first workflow to produce text output, making it the first
integration point.

### New phase — Phase 4b: Word Replacement

Insert after the Phase 4 section with this content:

---

**Goal:** Implement word replacement as a pure engine function, wire it into
Scribe output and Dictate paste, and add the Replacements tab to Settings.

**Done when:** all rubric Word Replacement success criteria are met and
`.venv/bin/pytest` count has increased from Phase 4's final count.

**New engine file:**
`src/liscribe/replacements.py`
- Pure function: `apply(text: str, rules: list[dict]) -> str`
- No imports from config, services, or UI
- Handles all three types: simple, newline, wrap
- Case-insensitive, whole-word matching
- Written test-first — this is the most testable file in the project

**ConfigService changes:**
- Add `get_replacement_rules() -> list[dict]`
- Add `set_replacement_rules(rules: list[dict]) -> None`
- Default rules seeded on first run if key missing from config

**Integration:**
- `output.py` — call `replacements.apply()` before markdown write
  (do this via the service layer — output.py must not import config directly)
- `DictateController` — call `replacements.apply()` before paste

**Settings — Replacements tab:**
- `src/liscribe/ui/panels/settings.html` — add Replacements tab
- `src/liscribe/bridge/settings_bridge.py` — add:
  - `get_replacements()`
  - `add_replacement(trigger, type, output, prefix, suffix, scope)`
  - `update_replacement(index, ...)`
  - `delete_replacement(index)`

**New tests to write before implementation:**
```
tests/test_replacements.py
```
Must cover:
- Simple replacement, case-insensitive
- Whole-word match only (not substring)
- Newline replacement produces correct line break
- Wrap replacement wraps next word only
- Scope filtering — Transcripts rules not applied to Dictate output
- Multiple rules applied in sequence
- Rule with empty trigger raises ValueError
- Rule with unknown type raises ValueError
- Text with no matching triggers passes through unchanged

**Done condition:**
- [ ] `tests/test_replacements.py` exists and passes before any integration work
- [ ] `replacements.py` has no imports outside stdlib
- [ ] Scribe output applies replacements before file write
- [ ] Dictate applies replacements before paste
- [ ] Replacements tab present in Settings with full CRUD
- [ ] Default rules present on first launch
- [ ] All rubric Word Replacement success criteria met
- [ ] `.venv/bin/pytest` count increased

---

## Rules for the agent

1. Only edit `docs/plan.md` and `docs/rubric.md`. No code.
2. Do not renumber existing phases — insert Phase 4b between 4 and 5.
3. Do not change any existing rubric criteria — only add new ones.
4. Do not add `replacements.py` to the engine frozen list — it is new code,
   not carried-forward v1 code. It can be modified freely.
5. After editing both docs, read them back and confirm the new phase
   is internally consistent with the architecture already defined.