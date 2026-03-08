# Liscribe v2 — Build Plan

> **How to use this document**
> Read the rubric first (`docs/v2-rubric.md`). The rubric is the source of truth
> for what success looks like. This plan is the ordered sequence of work to get
> there. Each phase has a single goal, explicit file changes, and a done
> condition. Complete phases in order. Do not start a phase until the previous
> phase's done condition is fully met.
>
> Phases 1–2 produce no runnable app. Phase 3 produces the first
> launchable skeleton. Everything after adds behaviour.

---

## Phase Status

| Phase | Name | Status |
|---|---|---|
| 1 | Strip to engine foundation | ✅ Done — 53 tests passing |
| 2 | Architecture + scaffold | ✅ Done — scaffold in place, 53 tests passing |
| 3 | Menu bar + panel skeleton | ✅ Done — app.py + services + panel stubs, 53 tests passing |
| 4 | Scribe workflow | ✅ Done — 246 tests passing |
| 5 | Transcribe workflow | ✅ Done — prefill from Scribe, model list with download status, init delay/retry |
| 6 | Dictate workflow | ✅ Done — hotkey state machine, floating panel, paste, Setup Required |
| 7 | Settings | ✅ Done — 388 tests passing; all tabs, hotkey pickers, Save and quit to apply hotkeys |
| 8 | Onboarding | ✅ Done — 412 tests passing; first-launch wizard, replay from Settings |
| 8b | Onboarding loading state | ⬜ Pending — do last |
| 9 | Bundle + install | ⬜ Next |
| 10 | Word Replacement | ⬜ |
| 11 | Refactor (panel layer + services) | ⬜ |

---

## Phase 1 — Strip to Engine Foundation ✅

**Done.** 53 tests passing on Python 3.13 via `.venv/bin/pytest`.

Engine files kept verbatim (config.py was later extended with `CACHE_DIR` for shared cache root — used by `app_instance`, transcriber):
```
src/liscribe/__init__.py
src/liscribe/config.py
src/liscribe/notes.py
src/liscribe/output.py
src/liscribe/platform_setup.py
src/liscribe/recorder.py
src/liscribe/transcribe_worker.py
src/liscribe/transcriber.py
src/liscribe/waveform.py
```

---

## Phase 2 — Architecture + Scaffold

**Goal:** Define the C4 architecture, then create the empty folder structure
and stub files that all subsequent phases fill in. No logic is written.
No UI is visible yet.

**Done when:** The folder structure below exists, every stub file imports
cleanly, and `.venv/bin/pytest` still shows 53 passed.

---

### C4 Architecture

#### Context — what Liscribe is and who uses it

```
┌─────────────────────────────────────────────────────┐
│  User (Mac, git-clone audience)                     │
│                                                     │
│  Uses Liscribe to:                                  │
│  · Record + transcribe meetings/audio (Scribe)      │
│  · Dictate text into any app (Dictate)              │
│  · Transcribe existing audio files (Transcribe)     │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Liscribe.app  (menu bar resident, no terminal)     │
│                                                     │
│  Reads from: microphone, system audio (BlackHole)  │
│  Writes to:  local filesystem (transcripts, WAVs)  │
│  Uses:       faster-whisper models (local only)    │
│  Never:      network calls after model download    │
└─────────────────────────────────────────────────────┘
```

#### Container — major building blocks

```
┌─────────────────────────────────────────────────────────────────┐
│  Liscribe.app                                                   │
│                                                                 │
│  ┌─────────────┐   ┌──────────────────────────────────────┐   │
│  │  Menu Bar   │   │  Panel Layer (pywebview)             │   │
│  │  (rumps)    │──▶│                                      │   │
│  │             │   │  ScribePanel   TranscribePanel       │   │
│  │  Dropdown   │   │  DictatePanel  SettingsPanel         │   │
│  │  Hotkeys    │   │  OnboardingPanel                     │   │
│  └─────────────┘   └────────────────────┬─────────────────┘   │
│                                          │                      │
│  ┌───────────────────────────────────────▼─────────────────┐  │
│  │  Services Layer                                          │  │
│  │                                                          │  │
│  │  AudioService     ModelService     ConfigService        │  │
│  │  (recorder.py)    (transcriber.py) (config.py)         │  │
│  └───────────────────────────────────────────────────────  ┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Engine Layer (v1 carry-forward, frozen)                 │  │
│  │                                                          │  │
│  │  recorder  transcriber  output  notes                    │  │
│  │  transcribe_worker  waveform  config  platform_setup     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### Component — inside the Panel Layer

```
Each panel is a self-contained component:

ScribePanel
  ├── HTML/CSS view (pywebview)
  ├── ScribeBridge  — JS↔Python calls (recording controls, waveform, notes)
  └── ScribeController — orchestrates AudioService + ModelService

TranscribePanel
  ├── HTML/CSS view
  ├── TranscribeBridge
  └── TranscribeController — file input → ModelService → output

DictatePanel  (floating, near cursor)
  ├── HTML/CSS view (minimal: waveform + timer only)
  ├── DictateBridge
  └── DictateController — hotkey state machine + AudioService + paste

SettingsPanel
  ├── HTML/CSS view (tabbed: General, Models, Hotkeys, Deps, Help)
  ├── SettingsBridge
  └── reads/writes ConfigService directly

OnboardingPanel
  ├── HTML/CSS view (stepped wizard)
  ├── OnboardingBridge
  └── calls real workflows for practice steps

Shared services (not panels):
  AudioService    — wraps recorder.py; one instance, shared across panels
  ModelService    — wraps transcriber.py; download, load, run
  ConfigService   — wraps config.py; single source of config truth
  HotkeyService   — pynput listener; fires callbacks to DictateController
                    and ScribeController
```

**Canonical C4 diagrams** — Level 1 (Context), Level 2 (Container), and Level 3 (Component) are maintained as Mermaid C4 diagrams in **docs/architecture.md**. Use that file for rendered diagrams and single-instance / panel-load behaviour.

---

### New Folder Structure to Create

Create these empty files exactly. Content comes in later phases.

```
src/liscribe/
├── app.py                     # rumps App entry point — Phase 3
├── app_instance.py            # single-instance lock + activate socket (one process per user)
├── bridge/
│   ├── __init__.py
│   ├── scribe_bridge.py       # Phase 4
│   ├── transcribe_bridge.py   # Phase 5
│   ├── dictate_bridge.py      # Phase 6
│   ├── settings_bridge.py     # Phase 7
│   └── onboarding_bridge.py   # Phase 8
├── controllers/
│   ├── __init__.py
│   ├── scribe_controller.py   # Phase 4
│   ├── transcribe_controller.py # Phase 5
│   ├── dictate_controller.py  # Phase 6
│   └── onboarding_controller.py # Phase 8
├── services/
│   ├── __init__.py
│   ├── audio_service.py       # Phase 3
│   ├── model_service.py       # Phase 3
│   ├── config_service.py      # Phase 3
│   └── hotkey_service.py      # Phase 3
└── ui/
    ├── panels/
    │   ├── scribe.html        # Phase 4
    │   ├── transcribe.html    # Phase 5
    │   ├── dictate.html       # Phase 6
    │   ├── settings.html      # Phase 7
    │   └── onboarding.html    # Phase 8
    └── assets/
        └── style.css          # Phase 3 — shared base styles
```

**Scaffold command:**
```bash
mkdir -p src/liscribe/bridge \
         src/liscribe/controllers \
         src/liscribe/services \
         src/liscribe/ui/panels \
         src/liscribe/ui/assets

touch src/liscribe/app.py \
      src/liscribe/bridge/__init__.py \
      src/liscribe/bridge/scribe_bridge.py \
      src/liscribe/bridge/transcribe_bridge.py \
      src/liscribe/bridge/dictate_bridge.py \
      src/liscribe/bridge/settings_bridge.py \
      src/liscribe/bridge/onboarding_bridge.py \
      src/liscribe/controllers/__init__.py \
      src/liscribe/controllers/scribe_controller.py \
      src/liscribe/controllers/transcribe_controller.py \
      src/liscribe/controllers/dictate_controller.py \
      src/liscribe/controllers/onboarding_controller.py \
      src/liscribe/services/__init__.py \
      src/liscribe/services/audio_service.py \
      src/liscribe/services/model_service.py \
      src/liscribe/services/config_service.py \
      src/liscribe/services/hotkey_service.py \
      src/liscribe/ui/panels/scribe.html \
      src/liscribe/ui/panels/transcribe.html \
      src/liscribe/ui/panels/dictate.html \
      src/liscribe/ui/panels/settings.html \
      src/liscribe/ui/panels/onboarding.html \
      src/liscribe/ui/assets/style.css
```

**Done condition:**
- [ ] All folders and files exist
- [ ] `.venv/bin/pytest` still shows 53 passed (empty stubs don't break anything)

---

## Phase 3 — Menu Bar + Panel Skeleton

**Goal:** A launchable `.app` (or `python app.py`) that shows the Liscribe
menu bar icon with the correct dropdown. Clicking each menu item opens a blank
panel window. Nothing functional yet — just the chrome working.

**New deps to add to `pyproject.toml` and install:**
```
rumps>=0.4.0
pywebview>=5.0.0
pynput>=1.7.6
```

**Files to write:**

`src/liscribe/app.py`
- rumps App subclass
- Menu: Scribe, Dictate, Transcribe, Settings, Quit
- Each item calls the correct panel open method
- Hotkey registration via HotkeyService on startup

`src/liscribe/services/config_service.py`
- Thin wrapper around `config.py`
- Single shared instance pattern
- Exposes typed getters/setters for all v2 config keys

`src/liscribe/services/audio_service.py`
- Wraps `recorder.py`
- Exposes: `list_mics()`, `start(mic, speaker)`, `stop()`, `get_levels()`
- Single instance — only one recording can be active at a time

`src/liscribe/services/model_service.py`
- Wraps `transcriber.py`
- Exposes: `list_models()`, `is_downloaded(model)`, `download(model)`,
  `transcribe(wav_path, models)`

`src/liscribe/services/hotkey_service.py`
- pynput global listener
- Fires registered callbacks on: scribe_trigger, dictate_double_tap,
  dictate_hold_start, dictate_hold_end

`src/liscribe/ui/assets/style.css`
- Base styles shared across all panels
- Dark background, system font stack, consistent spacing

**Done condition:**
- [x] `python src/liscribe/app.py` shows menu bar icon
- [x] All 5 menu items are present and labelled correctly (Scribe, Dictate, Transcribe, Settings, Quit)
- [x] Clicking each item opens a blank (white or styled) panel window
- [x] Quit removes the icon
- [x] Second launch does not open a duplicate — single-instance lock and activate socket (see `app_instance.py`); second process activates existing app and exits
- [x] `.venv/bin/pytest` still 53 passed (or higher after later phases)

---

## Phase 4 — Scribe Workflow

**Goal:** Scribe panel fully functional end-to-end per the rubric.

**Files to write:**

`src/liscribe/ui/panels/scribe.html`
- Matches the approved sketch exactly
- Live waveform (JS polling bridge)
- Notes textarea
- Mic dropdown
- Speaker capture toggle
- Model checkboxes
- Save path + Change button
- Cancel / Stop & Save buttons
- Transitions to transcribing state in-panel
- No-model graceful degradation state

`src/liscribe/bridge/scribe_bridge.py`
- JS-callable methods: `get_mics()`, `get_models()`, `get_save_path()`,
  `set_save_path()`, `toggle_speaker()`, `set_mic()`, `toggle_model()`,
  `get_waveform()`, `add_note()`, `stop_and_save()`, `cancel()`,
  `open_in_transcribe(wav_path)`

`src/liscribe/controllers/scribe_controller.py`
- Orchestrates AudioService + ModelService
- Manages recording session state
- Handles cancel prompt logic
- Triggers transcription after stop
- Passes results to output.py

**New tests to write before implementation:**
```
tests/test_scribe_controller.py
tests/test_scribe_bridge.py
```

**Done condition — all rubric Scribe criteria met:**
- [ ] Panel opens from menu bar and `⌃⌥L`
- [ ] Recording starts immediately on open
- [ ] Waveform live
- [ ] Notes → timestamped footnotes in markdown
- [ ] Speaker toggle works mid-session
- [ ] Mic swap mid-recording doesn't interrupt file
- [ ] Mic fallback visible if preferred unavailable
- [ ] Speaker OFF → single stream; ON → `in:`/`out:` labels, bleed suppressed
- [ ] 2+ models → 2+ files with model suffix
- [ ] WAV kept/deleted per global setting
- [x] No model → WAV saved, "Open in Transcribe →" button shown, wav_path logged (pre-fill wired in Phase 5)
- [ ] Cancel prompts Stop & Save or Discard
- [ ] Transcription progress visible per model
- [ ] Tests written and passing before UI wired up

---

## Phase 5 — Transcribe Workflow ✅

**Goal:** Transcribe panel fully functional end-to-end per the rubric.

**First task:** Wire Scribe’s "Open in Transcribe →" so that `open_in_transcribe(wav_path)` opens the Transcribe panel with `wav_path` pre-filled (via TranscribeBridge). **Done** — prefill uses `get_initial_state()`, `set_audio_path()`, `set_output_folder()`.

**Files written:**

`src/liscribe/ui/panels/transcribe.html`
- File picker (.wav .mp3 .m4a)
- Output folder picker
- Model checkboxes (download status: disabled + "(not downloaded)" for unavailable models; init delay + retry so list populates like Scribe)
- Transcribe button (disabled until file selected)
- In-progress state (per-model progress bars)
- Complete state (per-file Open Transcript buttons)

`src/liscribe/bridge/transcribe_bridge.py`
- JS-callable: `get_initial_state()`, `pick_file()`, `pick_folder()`, `set_audio_path()`, `set_output_folder()`, `get_models()`, `set_models()`, `transcribe()`, `get_progress()`, `open_transcript(path)`

**Tests:**
```
tests/test_transcribe_bridge.py
tests/test_transcribe_controller.py
```

**Done condition — all rubric Transcribe criteria met:**
- [x] File picker accepts .wav .mp3 .m4a; rejects others with visible error
- [x] Output folder defaults to global setting, overridable
- [x] Model list shows download status and disables unavailable models (matches Scribe)
- [x] 2+ models → 2+ files with model suffix
- [x] Progress visible per model; ✕ hidden until all complete
- [x] Each completed file has Open Transcript button
- [x] Corrupt/unsupported file → visible error, never silent

---

## Phase 6 — Dictate Workflow ✅

**Goal:** Dictate fully functional — both hotkey modes, floating panel,
paste, fallback to clipboard. Setup Required modal for missing permissions.

**Files to write:**

`src/liscribe/controllers/dictate_controller.py`
- Hotkey state machine (double-tap toggle + hold modes)
- Uses HotkeyService callbacks
- Uses AudioService for recording
- Uses ModelService for transcription
- Paste via pyperclip + pynput keyboard simulation
- Auto-enter logic
- Clipboard fallback when no focused input

`src/liscribe/ui/panels/dictate.html`
- Minimal: waveform + elapsed timer only
- Positioned near cursor (pywebview window positioning)

`src/liscribe/bridge/dictate_bridge.py`
- `get_waveform()`, `get_elapsed()`

**New tests:**
```
tests/test_dictate_controller.py
```

**Done condition — all rubric Dictate criteria met:**
- [x] Double-tap toggle works
- [x] Hold mode works
- [x] Both modes available simultaneously
- [x] Panel near focused input, doesn't steal focus
- [x] Text pasted at cursor
- [x] Auto-enter respects setting
- [x] No focused input → clipboard + notification
- [x] Missing permission → Setup Required modal with Help ↗ link
- [x] Permission granted → next trigger works without restart
- [ ] Word replacements (scope Dictate or Both) applied before paste — see Phase 10

---

## Phase 7 — Settings

**Goal:** Settings panel fully functional. All tabs. All persistence.

**Files to write:**

`src/liscribe/ui/panels/settings.html`
- Six tabs: General, Models, Hotkeys, Replacements, Deps, Help
- General: save folder, mic, WAV retention, auto-enter, start on login,
  open-with app picker
- Models: download/remove per model, Scribe defaults, Dictate model
- Hotkeys: Scribe shortcut, Dictate trigger key, mode info row
- Replacements: full CRUD for replacement rules — UI and bridge methods
  defined in Phase 10; Phase 7 integrates them into the settings panel shell
- Deps: live permission status + deep links, BlackHole status + guide
- Help: topic list → detail pages with named anchors

`src/liscribe/bridge/settings_bridge.py`
- `get_config()`, `set_config(key, value)`
- `list_models()`, `download_model(name)`, `remove_model(name)`
- `get_permissions()` — live check, not cached
- `open_system_settings(pane)`
- `pick_app()` — opens /Applications picker
- `open_help(anchor)` — navigates Help tab to named section
- `get_app_version()`
- `restart_app()` — quits and relaunches so hotkey changes take effect (launchd one-shot when .app, subprocess when dev)

**New tests:**
```
tests/test_settings_bridge.py
```

**Done condition — all rubric Settings criteria met:**
- [x] All settings persist across restarts
- [x] Model download shows progress and confirms completion
- [x] Removing default model prompts replacement before deletion
- [x] Permission status live (not cached)
- [x] Each permission has one-tap path to correct System Settings pane
- [x] App picker opens /Applications; icon + name shown
- [x] Open Transcript uses `open -a AppName file`
- [x] Start on Login registers/deregisters immediately
- [x] Help tab renders all topics; detail pages open correctly
- [x] Help ↗ from any Setup Required modal navigates to correct page
- [x] Privacy policy readable inline
- [x] GitHub link opens in browser
- [x] Setup Required modal fires for any missing config, not just Dictate

Hotkey changes (Scribe shortcut, Dictate trigger key) are applied after the user clicks "Save and quit" in Settings → Hotkeys; the app restarts via a launchd one-shot when running as .app, or a subprocess when running from the command line.

---

## Phase 8 — Onboarding

**Goal:** First-launch wizard. Interactive, uses real workflows for practice
steps. Re-accessible from Settings.

**Files to write:**

`src/liscribe/ui/panels/onboarding.html`
- 8-step wizard matching the rubric
- Step 1: Welcome
- Step 2: Permissions (Mic, Accessibility, Input Monitoring)
- Step 3: Model download (not skippable)
- Step 4: BlackHole (skippable)
- Step 5: Practice Dictate (real workflow)
- Step 6: Practice Scribe (real workflow)
- Step 7: Practice Transcribe (bundled sample audio)
- Step 8: Done

`src/liscribe/controllers/onboarding_controller.py`
- Tracks completion state in config
- Blocks app access until complete on first launch
- Exposes replay from Settings

`src/liscribe/bridge/onboarding_bridge.py`
- `get_step()`, `advance()`, `back()`
- `request_permission(type)`, `check_permission(type)`
- `download_model(name)`, `get_download_progress()`
- `is_complete()`

**Bundled sample audio:**
```
src/liscribe/ui/assets/sample.wav   — short (~5s) spoken sentence
```

**New tests:**
```
tests/test_onboarding_controller.py
tests/test_onboarding_bridge.py
```

**Done condition — all rubric Onboarding criteria met:**
- [x] Cannot be skipped on first launch
- [x] Each permission confirmed before advancing
- [x] Model download not skippable
- [x] Each practice step uses real workflow
- [x] User can go back to any step
- [x] Completion persists; subsequent launches go straight to menu bar
- [x] Replay from Settings restarts from step 1

---

## Phase 8b — Onboarding loading state (do last)

**Goal:** For steps that wait on the backend (e.g. after Continue/Back), show a loading state instead of a blank or stale view until the backend responds. Keeps UX clear and avoids the impression that the button did nothing.

**Scope:**
- Identify steps that call `advance()` or `back()` and then wait on `get_step()` (or similar) before binding handlers.
- Add a loading state (spinner and/or “Loading…”) that is shown as soon as navigation is triggered and hidden when the new step’s content is ready.
- Apply consistently so any step that depends on the backend shows loading until data is available.

**Done when:**
- [ ] Every onboarding step that waits for the backend shows an explicit loading state for the duration of that wait.
- [ ] Loading state is removed once the new step is bound and rendered.
- [ ] Rubric “Onboarding loading state” criterion is met.

---

## Phase 9 — Bundle + Install

**Goal:** `./install.sh` on a fresh Mac produces a working `.app` in
`/Applications/Liscribe.app`. No terminal required after that.

**Files to write:**

`install.sh`
- Check Python 3.10+
- Check/install Homebrew deps: portaudio, blackhole-2ch (optional)
- Create venv
- `pip install -e .`
- `pip install py2app`
- `python setup.py py2app`
- Copy `.app` to `/Applications`
- Open Liscribe on first launch

`setup.py` (py2app config)
- Entry point: `src/liscribe/app.py`
- Include: all `ui/` assets, `sample.wav`
- Exclude: test files, `__pycache__`

`uninstall.sh`
- Remove `/Applications/Liscribe.app`
- Remove `~/.config/liscribe/`
- Remove model cache
- Remove login item if set

**Done condition:**
- [ ] `./install.sh` runs to completion on a clean venv
- [ ] `/Applications/Liscribe.app` opens without terminal
- [ ] Menu bar icon appears on launch
- [ ] Gatekeeper "Open Anyway" is the only friction for new users
- [ ] `./uninstall.sh` removes all traces

---

## Phase 10 — Word Replacement

**Goal:** Implement word replacement as a pure engine function, wire it into
Scribe output and Dictate paste, and add the Replacements tab to Settings.

Phase 10 sits after Bundle+Install because it touches Scribe output, Dictate,
and the Settings panel — all three must be stable before adding a
cross-cutting post-processing layer.

**Done when:** all rubric Word Replacement success criteria are met and
`.venv/bin/pytest` count has increased from Phase 9's final count.

---

**New engine file:**

`src/liscribe/replacements.py`
- Pure function: `apply(text: str, rules: list[dict], scope: str) -> str`
- No imports outside stdlib — no config, no services, no UI
- Handles all three types: simple, newline, wrap (next word only)
- Case-insensitive, whole-word matching (not substring)
- Written test-first — this is the most testable file in the project
- Not on the frozen engine list — it is new code, not v1 carry-forward

---

**ConfigService changes:**

- Add `replacement_rules` property — `list[dict]`, returns default ruleset
  if the key is absent from config
- Default rules seeded on first read if the key is missing; no separate
  migration step required

Default rules (seeded automatically):

| Trigger | Output | Type | Scope |
|---|---|---|---|
| hashtag | # | simple | both |
| todo | [ ] | simple | both |
| open bracket | [ | simple | both |
| close bracket | ] | simple | both |
| dash | - | simple | both |
| newline | \n | newline | both |

---

**Integration points:**

`src/liscribe/services/model_service.py`
- `save_transcript()` retrieves rules from `ConfigService` and calls
  `replacements.apply(text, rules, scope="transcripts")` before writing the
  markdown file
- `output.py` is not changed — the apply call happens in the service layer,
  keeping the engine file frozen

`src/liscribe/controllers/dictate_controller.py` (Phase 6)
- `DictateController` calls `replacements.apply(text, rules, scope="dictate")`
  before paste
- Add a `# TODO Phase 10: wire replacements before paste` comment in the
  Phase 6 stub so Phase 6 implementors do not forget

---

**Settings — Replacements tab:**

`src/liscribe/ui/panels/settings.html`
- Add "Replacements" as the fifth tab (between Hotkeys and Deps)
- Table view of all rules: Trigger | Output | Type | Scope
- "+ Add replacement" opens inline add form
- Each row has Edit and Delete actions
- Delete of a default rule shows a confirmation prompt
- Add/Edit form fields: Trigger word, Type (Simple/Newline/Wrap), Output/Prefix,
  Suffix (shown only for Wrap type), Scope (Transcripts/Dictate/Both)
- Validation: empty trigger or empty output shows an inline error and blocks save

`src/liscribe/bridge/settings_bridge.py`
- Add to the existing bridge:
  - `get_replacements() -> list[dict]`
  - `add_replacement(trigger, type, output, prefix, suffix, scope) -> dict`
  - `update_replacement(index, trigger, type, output, prefix, suffix, scope) -> dict`
  - `delete_replacement(index) -> dict`
- All mutating methods write back through `ConfigService.replacement_rules`
- Validation in the bridge: returns `{"ok": False, "error": "..."}` for empty
  trigger or empty output, never writes an invalid rule

---

**New tests to write before implementation:**

```
tests/test_replacements.py
```

Must cover (all written before `replacements.py` is implemented):
- Simple replacement replaces trigger with output string
- Simple replacement is case-insensitive (`Hashtag` and `HASHTAG` match)
- Whole-word match only — `"hash"` rule does not match inside `"hashtag"`
- Newline replacement produces `\n` at the replacement point
- Wrap replacement removes trigger and wraps the immediately following word
  in prefix + suffix
- Wrap replacement leaves text unchanged when trigger is the last word
- Scope `"transcripts"` rules are not applied when scope argument is `"dictate"`
- Scope `"dictate"` rules are not applied when scope argument is `"transcripts"`
- Scope `"both"` rules apply regardless of scope argument
- Multiple rules applied in sequence; order is the order of the rules list
- Text with no matching triggers passes through unchanged
- Rule with empty trigger raises `ValueError`
- Rule with unknown type raises `ValueError`

---

**Done condition:**

- [ ] `tests/test_replacements.py` written and passing before any integration work begins
- [ ] `replacements.py` has zero imports outside Python stdlib
- [ ] `replacements.apply()` is the only entry point — no other public functions
- [ ] Scribe output applies replacements (scope `"transcripts"`) before file write
- [ ] Dictate applies replacements (scope `"dictate"`) before paste
- [ ] Scope filtering correct: Transcripts rules not applied to Dictate and vice versa
- [ ] Replacements tab present in Settings with full CRUD (add, edit, delete)
- [ ] Default rules are present on first launch without manual setup
- [ ] Deleting a default rule requires confirmation; deleting a user rule does not
- [ ] Empty trigger or empty output shows a validation error and is never saved
- [ ] All rules persist across app restarts
- [ ] `.venv/bin/pytest` count increased from Phase 9's final count

---

## Phase 11 — Refactor (panel layer + services)

**Goal:** Reduce duplication and special-case logic identified in the Phase 7
Settings review (`docs/review-diff.md`). No new features; behaviour unchanged.
All refactors are optional improvements — do only if time permits and tests
stay green.

**Prerequisite:** Phases 1–10 done. Refactor is safe to run after Word
Replacement (Phase 10) so that Scribe, Dictate, Transcribe, Settings, and
Replacements are all stable.

---

**1. Bridge protocol**

- Define a `PanelBridge` protocol (or abstract base) in e.g.
  `src/liscribe/bridge/protocols.py`: optional `set_window(window)`, optional
  `close_window()`.
- ScribeBridge, TranscribeBridge, DictateBridge, SettingsBridge implement or
  extend it where applicable.
- Reduces repeated "if name == X and hasattr(js_api, 'set_window')" in
  `app._open_panel`; contract is explicit.

**Files:** `src/liscribe/bridge/protocols.py` (new), each bridge module,
`src/liscribe/app.py`.

---

**2. Panel registry**

- Replace panel-specific conditionals in `_open_panel` with a registry: name →
  `{url, title, width, height, js_api, confirm_close?, set_window?, fragment?}`.
- Adding a new panel = one registry entry; no new `if name == "..."` in
  `_open_panel`.

**Files:** `src/liscribe/app.py` (and optionally a small `panel_registry.py` or
dict in app).

---

**3. Permissions “safe” check**

- Single abstraction for “get input monitoring status” that chooses in-process
  vs subprocess based on caller context (e.g. bridge thread vs main thread), or
  always use subprocess for `get_all_permissions()` and keep in-process only for
  `has_dictate_permissions()` with a shared implementation (e.g. one script
  file or one helper that subprocess invokes).
- Goal: pynput listener check implemented once; no duplicated script string.

**Files:** `src/liscribe/services/permissions_service.py`, possibly a small
`run_script_subprocess(script: str) -> (stdout, returncode)` helper.

---

**4. UI prefs API**

- Formalise “UI-only prefs” (e.g. `start_on_login`) as one interface: one file
  (`ui_prefs.json`), one module or class with get/set by key. ConfigService
  delegates to it for those keys so the bridge does not need special cases in
  `set_config` for “not in config.json”.

**Files:** `src/liscribe/services/config_service.py`, optionally
`src/liscribe/services/ui_prefs.py` (new). `settings_bridge.set_config` can
route via the API instead of hardcoding keys.

---

**5. Subprocess helper**

- Add `run_python_script(script: str, timeout: float = 5) -> (stdout: str,
  returncode: int)` (or similar) in e.g. `src/liscribe/utils/subprocess_helpers.py`.
- `_check_input_monitoring_subprocess` calls it with the existing script string.
- Makes it easy to add other “run snippet in subprocess” checks without
  duplicating subprocess boilerplate.

**Files:** New helper module, `src/liscribe/services/permissions_service.py`.

---

**6. Panel bootstrap (Settings)**

- Refactor Settings load handler into a small pattern: list of async data
  loaders (loadMics, loadConfig, …) and list of render steps
  (applyConfigToGeneral, applyConfigToHotkeys, refreshModels, refreshPermissions).
- Same behaviour; order and dependencies explicit and easier to test or reuse.

**Files:** `src/liscribe/ui/panels/settings.html` (JS only).

---

**Done condition:**

- [ ] All existing tests pass; no behaviour change to user-visible features.
- [ ] Each refactor item (1–6) is either implemented and documented or
  explicitly skipped with a one-line “Phase 11: skipped — reason” in the
  relevant file or in the plan.
- [ ] If Bridge protocol or Panel registry is done: `_open_panel` has no new
  special cases; new panels would add a registry entry only.
- [ ] If Permissions safe check is done: input monitoring check logic exists in
  one place only.
- [ ] If UI prefs API is done: ConfigService (or dedicated module) exposes one
  interface for UI prefs; bridge does not hardcode key names for “not in
  config.json”.
- [ ] If Subprocess helper is done: permissions_service uses it; no duplicated
  subprocess run logic.
- [ ] If Panel bootstrap is done: Settings load is a clear sequence of loaders
  + render steps.

---

## Rules for agents working on this plan

1. **Read the rubric before each phase.** The rubric defines done, not this
   plan. If they conflict, the rubric wins.

2. **Write tests before implementation.** Every controller and bridge gets
   tests written first. UI HTML does not need unit tests.

3. **Never modify engine files** (`recorder.py`, `transcriber.py`, `output.py`,
   `notes.py`, `transcribe_worker.py`, `waveform.py`, `config.py`). These are frozen.
   Exception: `config.py` may define path constants (e.g. `CACHE_DIR`); transcriber may
   reference them. If a bug is found in engine code, note it — don't fix it in place.

4. **One phase at a time.** Do not start Phase N+1 until Phase N's done
   condition is fully met and confirmed.

5. **Services are singletons.** AudioService, ModelService, ConfigService,
   HotkeyService are instantiated once in `app.py` and passed down.
   Panels do not instantiate services directly.

6. **Panels communicate only through their bridge.** A panel's HTML calls
   JS functions exposed by its bridge. The bridge calls the controller.
   The controller calls services. Nothing skips a layer.

7. **No network calls.** After model download, zero outbound connections.
   The GitHub link in Help opens the browser — that is the only exception.