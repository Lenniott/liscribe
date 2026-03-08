# Liscribe v2 — Rubric of Success

> This document defines what "done" means for every part of Liscribe v2.
> Nothing gets planned or built until each section is verified by Ben.
>
> **Document maintenance:** Keep this rubric in sync with `docs/plan-v2.md` (phase status and done conditions) and `docs/architecture.md` (C4 diagrams and behaviour). When a phase is signed off, update the rubric success criteria checkboxes and the plan; when architecture or app lifecycle changes, update architecture.md. See `docs/starter.md` and `docs/reviewer.md` for the maintenance workflow.

---

## Stack

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.10+ | Carries forward v1 engine verbatim |
| Menu bar | rumps | Purpose-built Python Mac menu bar; simple, well-documented |
| Panels | pywebview | HTML/CSS rendered in Apple's WKWebView — no Xcode, no signing |
| Audio | sounddevice + PortAudio | Unchanged from v1 |
| Transcription | faster-whisper | Unchanged from v1 |
| Speaker capture | BlackHole (brew) | Unchanged from v1 |
| Distribution | Terminal + alias in .zshrc | git clone → ./install.sh → run liscribe from terminal |
| Config storage | JSON at ~/.config/liscribe/config.json | Unchanged from v1 |
| Developer account | Not required | Unsigned .app; users click "Open Anyway" in Gatekeeper once |

---

## Principles (non-negotiable)

1. **Separation of concerns** — Scribe, Dictate, and Transcribe are independent modules. They share no UI surface and no state at runtime.
2. **TDD** — every behaviour has a test before an implementation.
3. **Seamless UX onboarding** — first launch guides the user through permissions, model download, and a live practice run of each workflow.
4. **Feedback — no hidden behaviour** — every state change the app makes is visible to the user. No silent failures, no masked operations.
5. **100% local after setup** — once models are downloaded, zero network calls.
6. **C4 modelling** — architecture documented at Context, Container, and Component level before implementation begins.
7. **Sketch UI before planning** — wireframes approved before any code is written.

---

## Hotkeys

| Workflow | Trigger | Notes |
|---|---|---|
| Scribe | `⌃ ⌥ L` | Opens the Scribe panel; recording starts immediately |
| Dictate | `Right Control` — double-tap or hold | Dictate is always listening in background; no panel to "open" first. Double-tap = toggle on/off. Hold = record while held |

Both hotkeys are configurable in Settings → Hotkeys.

---

## UI Sketches

These are the approved layout references. Pixel-perfect implementation follows these shapes and hierarchies.

---

### Menu Bar — Dropdown

The menu bar icon is a small waveform or microphone glyph, top-right system tray.

```
 ┌──────────────────────────────────────┐
 │  🎙 Liscribe                         │
 │   Scribe                      ⌃⌥L   │
 │   Dictate     ⌃⌃  /  hold ⌃         │
 │   Transcribe                         │
 │   Settings                           │
 │   Quit                               │
 └──────────────────────────────────────┘
```

Notes:
- Dictate row shows both trigger modes inline as a permanent reminder — double-tap `⌃⌃` or hold `⌃`
- No separators, no sub-menus — every item is a direct action or panel open
- "Quit" removes the icon from the menu bar entirely; user must reopen the .app to get it back
- Start on Login lives in Settings → General (not in this menu)

---

### Scribe Panel — Recording State

Opens as a floating panel anchored below the menu bar icon.

```
 ┌──────────────────────────────────────────────┐
 │  ● Scribe                          00:04:22  │
 ├──────────────────────────────────────────────┤
 │                                              │
 │   ▁▂▃▄▅▄▃▂▁▂▃▅▆▅▄▃▂▁▂▃▄▅▄▃▂▁▂▃▅▆▅▄▃▂▁      │
 │                                              │
 │   ┌──────────────────────────────────────┐  │
 │   │  Add a note...                       │  │
 │   └──────────────────────────────────────┘  │
 │                                              │
 │   Mic   [MacBook Pro Mic          ▾]         │
 │   Speaker capture   [●──────────────] ON     │
 │                                              │
 │   Models  [✓] base  [ ] small  [ ] medium    │
 │                                              │
 │   ~/transcripts                   [Change]  │
 │                                              │
 │   ┌─────────────────────┐  ┌──────────────┐ │
 │   │     Cancel          │  │ ■ Stop & Save│ │
 │   └─────────────────────┘  └──────────────┘ │
 └──────────────────────────────────────────────┘
```

Notes:
- No X/close button during active recording — Cancel is the only exit
- Clicking Cancel (or attempting any close gesture) prompts:
  ```
  ┌─────────────────────────────────────────┐
  │  Recording in progress                  │
  │                                         │
  │  Stop and save, or discard?             │
  │                                         │
  │  [  Discard  ]       [ Stop & Save  ]   │
  └─────────────────────────────────────────┘
  ```
- Red dot + elapsed timer in header — always visible
- Waveform reflects live mic input (+ speaker if speaker capture is ON)
- Notes field focused by default; typing is passive, no click required
- Speaker toggle shows ON/OFF state clearly; toggling mid-session is safe
- Mic dropdown lists all available inputs; selecting mid-recording swaps source without interrupting the file
- Save path: click "Change" opens a folder picker

---

### Scribe Panel — Transcribing State

Replaces recording content in-panel after Stop is pressed.

```
 ┌──────────────────────────────────────────────┐
 │  Scribe — Transcribing                       │
 ├──────────────────────────────────────────────┤
 │                                              │
 │   base    ████████████████░░░░   82%         │
 │   small   ░░░░░░░░░░░░░░░░░░░░   queued      │
 │                                              │
 │   Saving to ~/transcripts/                   │
 │   2025-03-05_1042_base.md                    │
 │   2025-03-05_1042_small.md                   │
 │                                              │
 └──────────────────────────────────────────────┘
```

### Scribe Panel — No Model Available (graceful degradation)

When Stop & Save is pressed but no downloaded model is selected, Scribe saves the WAV and surfaces a route to Transcribe instead of failing silently.

```
 ┌──────────────────────────────────────────────┐
 │  Scribe — Recording Saved                    │
 ├──────────────────────────────────────────────┤
 │                                              │
 │   Audio saved to:                            │
 │   ~/transcripts/2025-03-05_1042.wav          │
 │                                              │
 │   No transcription model was available.      │
 │   You can transcribe this file later.        │
 │                                              │
 │   ┌────────────────────────────────────┐    │
 │   │    Open in Transcribe  →           │    │
 │   └────────────────────────────────────┘    │
 │                                              │
 └──────────────────────────────────────────────┘
```

Notes:
- "Open in Transcribe →" opens the Transcribe panel with the audio file path and output folder pre-filled — user only needs to pick a model and press Transcribe
- WAV is always kept in this state regardless of the global WAV retention setting (it is the only output)
- Progress bars per model shown in normal transcribing state; filenames confirmed only when written to disk

---

### Setup Required — Modal (universal pattern)

Any workflow or action that requires a configuration step that hasn't been completed uses this modal pattern. The title and body text are specific to the missing item, but the structure is always the same.

Examples that trigger it: Accessibility missing when Dictate fires, Input Monitoring missing when Dictate fires, BlackHole not installed when speaker capture is toggled on in Scribe, no model downloaded when any workflow attempts transcription.

```
 ┌─────────────────────────────────────────────┐
 │  [Permission / Setup Name] Required         │
 ├─────────────────────────────────────────────┤
 │                                             │
 │  [One sentence: what this enables]          │
 │                                             │
 │  1. [Step one]                              │
 │  2. [Step two]                              │
 │  3. [Step three]                            │
 │  4. Return here — [feature] will work       │
 │     straight away                           │
 │                                             │
 │  ┌─────────────────────────────────────┐   │
 │  │      [Primary action]  →            │   │
 │  └─────────────────────────────────────┘   │
 │                                             │
 │     [ Not now ]    [ Help  ↗ ]             │
 └─────────────────────────────────────────────┘
```

Notes:
- "Help ↗" deep-links directly to the relevant section in Settings → Help
- "Not now" dismisses without completing setup — the triggering action does not proceed
- Once the setup is completed, no restart required — the next attempt works immediately
- This modal is never shown during onboarding (onboarding handles all setup inline)

---

### Dictate — Floating Panel

Does not open from the menu bar. Appears automatically near the focused text input when the Right Control trigger fires. Disappears after paste completes.

```
 ┌─────────────────────────────┐
 │  ●  00:03   ▁▂▄▅▃▂▁▃▄▅▃▁   │
 └─────────────────────────────┘
```

Notes:
- Waveform + elapsed time only — nothing else
- Positioned adjacent to the cursor / focused input field, not fixed to a screen edge
- No close button — dismisses automatically on stop
- Does not steal keyboard focus from the target app

---

### Transcribe Panel — Input State

Opens from menu bar → Transcribe.

```
 ┌──────────────────────────────────────────────┐
 │  Transcribe                              ✕   │
 ├──────────────────────────────────────────────┤
 │                                              │
 │   Audio file                                 │
 │   ┌────────────────────────────────────┐    │
 │   │  No file selected           Browse │    │
 │   └────────────────────────────────────┘    │
 │                                              │
 │   Output folder                              │
 │   ┌────────────────────────────────────┐    │
 │   │  ~/transcripts              Browse │    │
 │   └────────────────────────────────────┘    │
 │                                              │
 │   Models                                     │
 │   [✓] base   [ ] small   [ ] medium          │
 │                                              │
 │   ┌────────────────────────────────────┐    │
 │   │           Transcribe               │    │
 │   └────────────────────────────────────┘    │
 │                                              │
 └──────────────────────────────────────────────┘
```

Notes:
- "Transcribe" button disabled until a valid file is selected
- Output folder defaults to global setting; changing here is session-only

---

### Transcribe Panel — In Progress

```
 ┌──────────────────────────────────────────────┐
 │  Transcribing…                               │
 ├──────────────────────────────────────────────┤
 │                                              │
 │   meeting-notes.m4a                          │
 │                                              │
 │   base    ████████████████████   done ✓      │
 │   small   ████████░░░░░░░░░░░░   54%         │
 │                                              │
 │   ~/transcripts/meeting-notes_base.md        │
 │   ~/transcripts/meeting-notes_small.md       │
 │                                              │
 └──────────────────────────────────────────────┘
```

Notes:
- No ✕ while transcription is in progress — prevents orphaned processes
- ✕ appears once all models are done

### Transcribe Panel — Complete

```
 ┌──────────────────────────────────────────────┐
 │  Transcribe — Done                       ✕   │
 ├──────────────────────────────────────────────┤
 │                                              │
 │   meeting-notes.m4a                          │
 │                                              │
 │   base    ████████████████████   done ✓      │
 │   small   ████████████████████   done ✓      │
 │                                              │
 │   ~/transcripts/meeting-notes_base.md        │
 │   [ Open Transcript ]                        │
 │                                              │
 │   ~/transcripts/meeting-notes_small.md       │
 │   [ Open Transcript ]                        │
 │                                              │
 └──────────────────────────────────────────────┘
```

Notes:
- One "Open Transcript" button per output file
- Opens using the command set in Settings → General → Open transcripts with
- ✕ available once transcription is complete

---

### Settings Panel — General Tab

Opens from menu bar → Settings. Standard Mac settings window (not a popover).

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General ◀   │  Default save folder                   │
 │  Models      │  ┌──────────────────────────────────┐  │
 │  Hotkeys     │  │  ~/transcripts           Browse  │  │
 │  Replacements│  └──────────────────────────────────┘  │
 │  Deps        │                                        │
 │              │                                        │
 │              │  Default microphone                    │
 │              │  [ MacBook Pro Microphone          ▾]  │
 │              │                                        │
 │              │  WAV files after transcription         │
 │              │  ( ) Keep    (●) Delete                │
 │              │                                        │
 │              │  Dictation auto-enter after paste      │
 │              │  [●───────────────────────────] ON     │
 │              │                                        │
 │              │  Start on Login                        │
 │              │  [●───────────────────────────] ON     │
 │              │                                        │
 │              │  Open transcripts with                 │
 │              │  ┌──────────────────────┐ [Change]   │  │
 │              │  │  🅒  Cursor          │            │  │
 │              │  └──────────────────────┘            │  │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

---

### Settings Panel — Models Tab

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General     │  Whisper Models                        │
 │  Models  ◀   │                                        │
 │  Hotkeys     │  tiny    ~75MB    ✓ Downloaded  [Remove]│
 │  Replacements│  base    ~145MB   ✓ Downloaded  [Remove]│
 │  Deps        │  small   ~466MB   [  Download  ]       │
 │  Help        │  medium  ~1.5GB   [  Download  ]       │
 │              │  large   ~3GB     [  Download  ]       │
 │              │                                        │
 │              │  Scribe default models                 │
 │              │  [✓] tiny  [✓] base  [ ] small         │
 │              │                                        │
 │              │  Dictate model                         │
 │              │  [ base                            ▾]  │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

---

### Settings Panel — Hotkeys Tab

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General     │  Keyboard Shortcuts                    │
 │  Models      │                                        │
 │  Hotkeys ◀   │  Open Scribe                           │
 │  Replacements│  [ ⌃ ⌥ L                    Change ]  │
 │  Deps        │                                        │
 │              │                                        │
 │              │  Dictate trigger key                   │
 │              │  [ Right Control             Change ]  │
 │              │                                        │
 │              │  Dictate modes (always both active)    │
 │              │  Double-tap  →  toggle recording       │
 │              │  Hold        →  record while held      │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

Notes:
- Dictate modes row is informational only — both are always available, no toggle needed

---

### Settings Panel — Dependencies Tab

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General     │  Permissions                           │
 │  Models      │                                        │
 │  Hotkeys     │  Microphone         ✓ Granted          │
 │  Replacements│  Accessibility      ✗ [ Open Settings ]│
 │  Deps    ◀   │  Input Monitoring   ✓ Granted          │
 │              │                                        │
 │              │  Audio Dependencies                    │
 │              │                                        │
 │              │  BlackHole 2ch      ✗ Not installed    │
 │              │  Required for speaker capture          │
 │              │  [ Setup Guide ]                       │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

Notes:
- Permission status checked live each time this tab is viewed — never cached
- "Open Settings" deep-links to the correct Privacy & Security pane
- "Setup Guide" opens the same BlackHole flow used in onboarding

---

### Settings Panel — Help Tab

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General     │  ┌────────────────────────────────┐   │
 │  Models      │  │  Getting Started                │   │
 │  Hotkeys     │  │  ▸ How to use Scribe            │   │
 │  Replacements│  │  ▸ How to use Dictate           │   │
 │  Deps        │  │  ▸ How to use Transcribe        │   │
 │  Help    ◀   │  └────────────────────────────────┘   │
 │              │                                        │
 │              │  ┌────────────────────────────────┐   │
 │              │  │  Setup & Configuration          │   │
 │              │  │  ▸ Permissions explained        │   │
 │              │  │  ▸ BlackHole setup              │   │
 │              │  │  ▸ Downloading models           │   │
 │              │  │  ▸ Hotkey customisation         │   │
 │              │  └────────────────────────────────┘   │
 │              │                                        │
 │              │  ┌────────────────────────────────┐   │
 │              │  │  Privacy & Security             │   │
 │              │  │  ▸ What data Liscribe stores    │   │
 │              │  │  ▸ Network activity             │   │
 │              │  │  ▸ Privacy policy               │   │
 │              │  └────────────────────────────────┘   │
 │              │                                        │
 │              │  ┌────────────────────────────────┐   │
 │              │  │  More                           │   │
 │              │  │  ▸ Uninstall Liscribe           │   │
 │              │  │  ▸ GitHub (README, diagrams,    │   │
 │              │  │    security audit)  ↗           │   │
 │              │  └────────────────────────────────┘   │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

Selecting any item opens a detail view within the Help tab:

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │  ← Setup & Configuration               │
 │  General     ├────────────────────────────────────────┤
 │  Models      │                                        │
 │  Hotkeys     │  ## BlackHole Setup                    │
 │  Deps        │                                        │
 │  Help    ◀   │  BlackHole is a virtual audio driver   │
 │              │  that lets Liscribe capture system     │
 │              │  audio alongside your microphone.      │
 │              │                                        │
 │              │  ### Install                           │
 │              │  1. Open Terminal                      │
 │              │  2. Run: brew install blackhole-2ch    │
 │              │  3. Restart your Mac                   │
 │              │                                        │
 │              │  ### Configure Audio MIDI Setup        │
 │              │  1. Open Audio MIDI Setup              │
 │              │  2. Click + → Multi-Output Device      │
 │              │  3. Check your speakers + BlackHole    │
 │              │                                        │
 │              │  [ Open Audio MIDI Setup → ]           │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

Notes:
- Each topic page is a named anchor — `help://blackhole-setup`, `help://accessibility`, `help://scribe` etc.
- Any modal "Help ↗" link navigates to Settings → Help and opens the correct page directly
- External links (GitHub) open in the default browser — the only intentional external navigation in the app
- Privacy policy content is inline in the app — users do not need to go online to read it
- GitHub link points to the repo README, architecture diagrams, and security audit
- "Uninstall" page documents what the app stores and where, with step-by-step removal instructions

---

## Workflows

### 1. Scribe

**Entry:** Menu bar → Scribe  **or**  `⌃ ⌥ L`

**Dual-source transcript (speaker capture ON):**
When speaker capture is enabled, Scribe records two streams independently — microphone and system audio — and produces a merged chronological transcript with source labels:

```
[00:03.2] in: Can you hear me okay?
[00:05.7] out: Yeah, loud and clear.
[00:08.1] in: Great, let's get started.
```

- `in:` = microphone (the user)
- `out:` = system audio via BlackHole (the other party / any audio playing)
- Lines are interleaved chronologically by timestamp
- Near-duplicate lines caused by mic bleed (the speaker audio bleeding into the mic) are suppressed

**Success criteria:**
- [x] Panel opens from menu bar and from hotkey `⌃ ⌥ L`
- [x] Recording starts immediately on panel open
- [x] Waveform reflects live audio input
- [x] Notes appear as timestamped footnotes in markdown output
- [x] Speaker toggle works mid-session cleanly
- [x] Mic selector swaps source mid-recording without interrupting the file
- [x] Preferred mic unavailable → silent fallback to system default + visible indicator
- [x] Speaker capture OFF → single-stream transcript, no source labels
- [x] Speaker capture ON → dual-stream transcript with `in:` / `out:` labels, merged chronologically
- [x] Near-duplicate lines from mic bleed are always suppressed in dual-source output — not configurable
- [x] 2+ models → 2+ transcript files each suffixed with model name
- [x] WAV retained or deleted per global setting
- [x] No model available → WAV saved, "Open in Transcribe →" action shown with file and output path pre-filled
- [x] Cancel and clicking any close gesture while recording prompts: Stop & Save or Discard
- [x] Stopping triggers transcription with visible per-model progress
- [x] Completed transcripts accessible after transcription completes

---

### 2. Transcribe

**Entry:** Menu bar → Transcribe

**Success criteria:**
- [x] Panel opens from menu bar
- [x] File picker accepts .wav, .mp3, .m4a; rejects others with a visible error
- [x] Output folder defaults to global setting, overridable per session
- [x] 2+ models → 2+ transcript files, each with model suffix
- [x] Progress visible per model during transcription; ✕ hidden until all models complete
- [x] Each completed file has an "Open Transcript" button using the command set in Settings
- [x] Corrupt or unsupported file shows a clear error — never a silent failure

---

### 3. Dictate

**Entry:** `Right Control` — double-tap to toggle **or** hold to record while held. Dictate is always listening while the app is running.

If Accessibility or Input Monitoring permission is missing when Dictate fires, the universal Setup Required modal is shown (see UI Sketches above). Dictate does not activate until the requirement is resolved.

**Success criteria:**
- [x] Double-tap starts recording; double-tap again stops and pastes
- [x] Hold starts recording; release stops and pastes
- [x] Both modes work at any time — no mode setting needed
- [x] Floating panel appears near focused input, not at a fixed screen position
- [x] Panel does not steal focus from the target app
- [x] Text is pasted at cursor in the correct app
- [x] Auto-enter after paste respects global setting
- [x] No focused input → paste to clipboard + system notification
- [x] Missing Accessibility or Input Monitoring → Setup Required modal with "Help ↗" link to correct Help section; Dictate does not activate
- [x] Once permission is granted, next trigger works immediately without restart
- [x] Dictate model set globally in Settings → Models

---

## Settings

### Global
- Default transcript save folder
- Default microphone (with system default fallback)
- WAV retention: keep or delete (overridden to keep when no model available at record time)
- Dictation auto-enter: on/off
- Dictate model
- Scribe default models
- Open transcripts with: app picker (browses /Applications; stores the .app path; opens via subprocess `open -a AppName file`)
- Start on Login: on/off

**Success criteria:**
- [x] All global settings persist across app restarts
- [x] Model manager shows accurate status and file size
- [x] Downloading shows inline progress and confirms on completion
- [x] Removing a default model prompts replacement selection before deletion proceeds
- [x] Permission status is live (not cached) in Dependencies tab
- [x] Each permission has a one-tap path to the correct System Settings pane
- [x] "Open transcripts with" picker opens /Applications; selected app icon and name shown; persists across restarts
- [x] "Open Transcript" button opens the file via `open -a AppName file` — no PATH issues, no shell alias needed
- [x] Start on Login toggle registers and deregisters the app as a login item immediately on toggle
- [x] Help tab renders all topics; each topic opens a detail page within the tab
- [x] "Help ↗" from any Setup Required modal navigates directly to the correct Help page
- [x] Privacy policy is readable inline — no network access required
- [x] GitHub link opens in default browser
- [x] Setup Required modal fires for any workflow that requires a missing configuration — not just Dictate

Hotkey changes (Scribe shortcut, Dictate trigger key) take effect after the user clicks "Save and quit" in Settings → Hotkeys; the app restarts (launchd one-shot when .app, subprocess when run from command line).

---

## Word Replacement

Liscribe produces text from speech. Users cannot type during recording, so
certain characters and formatting cannot be spoken naturally. Word Replacement
substitutes spoken trigger words with defined output text at the point of
text production — after transcription, before file write or paste.

**Example:** the user says "hashtag project" — the output reads "# project".

### Three replacement types

**Simple** — a trigger word is replaced by a fixed string:
```
spoken:  "hashtag"   →   output: "#"
spoken:  "todo"      →   output: "[ ]"
```

**Newline** — a trigger word is replaced by a line break:
```
spoken:  "newline"   →   output: "\n"
```

**Wrap** — a trigger word is removed and the immediately following word is
wrapped in a prefix and a suffix. Applies to the next word only.
```
spoken:  "bold hello"       →   output: "**hello**"   (prefix="**" suffix="**")
spoken:  "highlight done"   →   output: "==done=="     (prefix="==" suffix="==")
```

### Matching rules

- Matching is always case-insensitive
- Trigger words must match whole words — `"hash"` does not match inside `"hashtag"`
- Replacement happens after transcription, before output is written to file or pasted

### Scope

Each rule has one of three scope values:

| Scope | Applies to |
|---|---|
| Transcripts | Scribe and Transcribe file output only |
| Dictate | Dictate paste output only |
| Both | All output — Scribe, Transcribe, and Dictate |

### Default rules (ship with the app)

| Trigger | Output | Type | Scope |
|---|---|---|---|
| hashtag | # | simple | both |
| todo | [ ] | simple | both |
| open bracket | [ | simple | both |
| close bracket | ] | simple | both |
| dash | - | simple | both |
| newline | ↵ | newline | both |

### Settings — Replacements tab

```
 ┌───────────────────────────────────────────────────────┐
 │  Settings                                         ✕   │
 ├──────────────┬────────────────────────────────────────┤
 │              │                                        │
 │  General     │  Word Replacements                     │
 │  Models      │                                        │
 │  Hotkeys     │  Trigger       Output    Type   Scope  │
 │  Replacements│  ──────────────────────────────────    │
 │  Deps        │  hashtag       #         simple  both  │
 │  Help        │  todo          [ ]       simple  both  │
 │              │  open bracket  [         simple  both  │
 │              │  close bracket ]         simple  both  │
 │              │  dash          -         simple  both  │
 │              │  newline       ↵         newline both  │
 │              │                                        │
 │              │  [ + Add replacement ]                 │
 │              │                                        │
 └──────────────┴────────────────────────────────────────┘
```

Add / Edit rule form (shown inline):

```
 Trigger word   [ _____________ ]
 Type           ( ) Simple  ( ) Newline  ( ) Wrap
 Output / Prefix [ _____________ ]
 Suffix (wrap)   [ _____________ ]   ← shown only for Wrap type
 Scope          ( ) Transcripts  ( ) Dictate  (●) Both
 [ Save ]  [ Cancel ]
```

### Success criteria

- [ ] Default rules are present on first launch without any manual setup
- [ ] Default rules survive app restarts and config reloads unchanged
- [ ] User can add a rule specifying trigger, type, output/prefix, suffix, and scope
- [ ] User can edit any existing rule, including the defaults
- [ ] User can delete any rule; deleting a default rule shows a confirmation prompt before proceeding
- [ ] Case-insensitive whole-word matching — `Hashtag`, `hashtag`, and `HASHTAG` all match the same rule
- [ ] Substring non-match — a rule for `"hash"` does not fire when the word is `"hashtag"`
- [ ] Simple replacement: trigger word replaced by the output string
- [ ] Newline replacement: trigger word replaced by a line break at that position
- [ ] Wrap replacement: trigger word removed, next word wrapped in prefix + suffix
- [ ] Wrap replacement: if the trigger is the last word, output is unchanged
- [ ] Scope Transcripts: rule applies to Scribe and Transcribe file output, not to Dictate paste
- [ ] Scope Dictate: rule applies to Dictate paste output, not to Scribe or Transcribe files
- [ ] Scope Both: rule applies to all output — Scribe, Transcribe, and Dictate
- [ ] Replacements applied after transcription, before file write or paste — never mid-recording
- [ ] Multiple rules applied in sequence in the order they appear in the list
- [ ] Rules persist across app restarts
- [ ] Empty trigger or empty output shows an inline validation error and is never saved to config
- [ ] Engine function `replacements.apply()` has zero imports outside Python stdlib

---

## Onboarding (First Launch)

**Trigger:** First launch only. Re-accessible via Settings → "Replay setup guide".

**Steps:**
1. Welcome — what Liscribe is, three workflow overview
2. Permissions — Microphone, Accessibility, Input Monitoring; each confirmed before advancing
3. Model download — choose at least one, download, confirm; not skippable
4. BlackHole (optional) — guided setup; skippable but clearly labelled "required for speaker capture"
5. Practice: Dictate — user triggers dictation, speaks, sees text pasted
6. Practice: Scribe — user records, stops, sees transcript generated
7. Practice: Transcribe — user picks bundled sample audio, runs transcription, sees output
8. Done — summary of setup, entry point to each workflow

**Success criteria:**
- [x] Cannot be skipped on first launch
- [x] Each permission step confirms grant status before allowing advance
- [x] Model download is not skippable — at least one model must be present to proceed
- [x] Each practice step uses the real workflow, not a mock
- [x] User can navigate back to any previous step
- [x] Completion marks onboarding done; subsequent launches go straight to menu bar
- [x] "Replay setup guide" in Settings restarts the full flow
- [ ] **Loading state (Phase 8b):** Steps that wait on the backend (e.g. after Continue/Back) show an explicit loading state (e.g. spinner or “Loading…”) until the new step is ready; no blank or stale content during the wait.

---

## Architecture Requirements

- [x] C4 Context, Container, and Component diagrams written and maintained in **docs/architecture.md** (Mermaid C4)
- [x] UI sketches (this document) approved before implementation
- [x] Each module (Scribe, Transcribe, Dictate, Settings, Onboarding) defines a clear interface — no module reaches into another's internals
- [x] Shared concerns (config, audio device management, model management) extracted into standalone services with defined ownership
- [x] Single instance: one process per user; second launch activates existing app and exits (documented in architecture.md; implemented in app_instance.py)

---

## Out of Scope for v2

- Cloud sync or backup
- Speaker diarisation (who said what)
- Real-time live transcription during recording (transcript produced after stop, not during)
- iOS / iPadOS port
- Custom vocabulary or model fine-tuning
- Any network call after initial model download

---

*Status: In progress — Scribe, Transcribe, Dictate, Settings, and Onboarding verified per plan-v2 Phases 4–8. Word Replacement pending.*
*Rubric, plan-v2, and architecture maintenance: see docs/starter.md and docs/reviewer.md.*