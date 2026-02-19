# Liscribe — User Workflow Diagrams & Manual Test Scripts

_Source of truth for style: Recording Screen. Use this doc to manually test every workflow._

---

## App Entry Points

There are two ways to launch liscribe:

```
rec                   →  LiscribeApp (Home → Recording → Transcribing → Home)
rec --no-ui           →  RecordingApp (direct recording TUI, no Home/Transcribing flow)
```

All workflows below assume `LiscribeApp` (the full TUI shell, started with `rec`).

---

## Workflow 1: Record → Save → Transcribe → Done

This is the primary happy path.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAUNCH                                                                      │
│  $ rec                                                                       │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  HOME SCREEN                                                                 │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          liscribe                                      │  │
│  │                   Listen & transcribe locally                          │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  ^r  Record          ← FOCUSED on load                          │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  ^p  Preferences                                                 │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  ^t  Transcripts                                                 │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                          │  │
│  │  ^c  Quit                                                                │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
             ACTION: Press ^r  OR  Click "^r Record"  OR  Tab + Enter
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  RECORDING SCREEN                                                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ [accent bg]  liscribe  ●  REC  00:00:00    [^o Speaker ▶] [^l Mic]   │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ Mic: Built-in Microphone                                               │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │ │ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁▂▃▄▅▆▇█▇▆▅ (waveform animating)                  │ │  │
│  │ └────────────────────────────────────────────────────────────────────┘ │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │ │  [1] My first note                                                  │ │  │
│  │ └────────────────────────────────────────────────────────────────────┘ │  │
│  │ Notes are added to the transcript as footnotes.                        │  │
│  │ ┌──────────────────────────────────────────────────────────────────┐   │  │
│  │ │ Type a note, press Enter...       ← FOCUSED on load              │   │  │
│  │ └──────────────────────────────────────────────────────────────────┘   │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ [^s Stop & Save]            [spacer]                    [^C Cancel]   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘

  THINGS TO TEST ON RECORDING SCREEN:
  ✓ Timer increments every second
  ✓ Waveform animates when speaking
  ✓ Note input is focused (cursor visible, primary-colour border)
  ✓ Type note → Enter → note appears in list, input clears
  ✓ ^n → focus returns to note input at any time
  ✓ ^l → mic select modal opens (see Workflow 4)
  ✓ ^o → speaker waveform toggles (see Workflow 5)

                             │
             ACTION: Press ^s  OR  Click "^s Stop & Save"
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  TRANSCRIBING SCREEN                                                         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          liscribe                                      │  │
│  │                       Transcribing…                                    │  │
│  │  Model: base                                                           │  │
│  │  [progress bar - not yet implemented, see TRANSCRIPTION_PROGRESS_PLAN] │  │
│  │                                                                        │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Back to Home   (disabled / greyed out)                          │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ... transcription runs in background subprocess ...                         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          liscribe                                      │  │
│  │                            Done                                        │  │
│  │  Saved: 2024-01-15_10-30-00.md                                        │  │
│  │                                                                        │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Back to Home   ← NOW ACTIVE, should be auto-focused            │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  THINGS TO TEST ON TRANSCRIBING SCREEN:                                      │
│  ✓ "Transcribing…" shown while in progress                                   │
│  ✓ Model name shown ("Model: base")                                          │
│  ✗ Progress bar — NOT YET IMPLEMENTED                                        │
│  ✓ "Back to Home" is greyed/disabled during transcription                    │
│  ! "Back to Home" should receive focus automatically when done (BUG)         │
│  ✓ "Done" shown with filename when complete                                  │
│  ✓ On error: "Transcription failed" + error message                          │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
         ACTION: Press Enter  OR  Click "Back to Home"
                             │
                             ▼
                        HOME SCREEN
```

---

## Workflow 2: Record → Cancel

```
HOME SCREEN
     │
     │  Press ^r
     ▼
RECORDING SCREEN (recording in progress)
     │
     │  Press ^c  OR  Click "^C Cancel"
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONFIRM CANCEL MODAL (overlay on recording screen)                          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │   Discard recording? Unsaved audio will be lost.    │                    │
│  │                                                      │                    │
│  │  ► Yes, discard recording   ← OptionList, focused   │                    │
│  │    No, keep recording                               │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                                                                              │
│  THINGS TO TEST:                                                             │
│  ✓ OptionList receives focus on modal open                                   │
│  ✓ Arrow keys move selection                                                 │
│  ✓ y key → selects "Yes" directly                                            │
│  ✓ n key → selects "No" directly                                             │
│  ✓ Escape → dismisses modal (keeps recording)                                │
│  ✓ Enter on "Yes" → recording discarded → back to Home                       │
│  ✓ Enter on "No" → back to recording, unchanged                              │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
        Press y / Enter on "Yes"          Press n / Escape / Enter on "No"
                │                                        │
                ▼                                        ▼
          HOME SCREEN                          RECORDING SCREEN (resumed)
```

---

## Workflow 3: Preferences

```
HOME SCREEN
     │
     │  Press ^p  OR  Click "^p Preferences"
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PREFERENCES HUB SCREEN                                                      │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          liscribe                                      │  │
│  │                        Preferences                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Dependency check   ← should be focused on load                 │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Alias                                                           │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Whisper                                                         │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Save location                                                   │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Back to Home                                                    │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  THINGS TO TEST:                                                             │
│  ✓ First button (Dependency check) is focused on load                        │
│  ✓ Tab cycles through all buttons in order                                   │
│  ✓ Escape → back to Home (BACK_BINDINGS)                                     │
│  ✓ Click/Enter on each button opens sub-screen                               │
│  ✓ In each sub-screen: Escape → back to Preferences                          │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
       Click/Enter on one of the four options
                             │
          ┌──────────────────┼──────────────────────┐
          ▼                  ▼                       ▼
  DEPENDENCY CHECK     ALIAS SCREEN          WHISPER SCREEN
  SCREEN               (edit alias)          (select language,
  (lists brew deps,                           model, check
  install status)                             installed)
          │                  │                       │
          └──────────────────┼──────────────────────┘
                             │
                     Escape / Back
                             │
                             ▼
                    PREFERENCES HUB
                             │
                     Escape / Back
                             │
                             ▼
                        HOME SCREEN
```

---

## Workflow 4: Change Mic (mid-recording)

```
RECORDING SCREEN
     │
     │  Press ^l  OR  Click "^l Mic" button
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  MIC SELECT MODAL (overlay on recording screen)                              │
│                                                                              │
│  ┌──────────────────────────────────────────────┐                           │
│  │  Select microphone:                           │                           │
│  │  ► [0] Built-in Microphone (1ch) ◄           │  ← current mic marked     │
│  │    [1] External USB Mic (2ch)                │                           │
│  │    [2] AirPods (1ch)                         │                           │
│  └──────────────────────────────────────────────┘                           │
│                                                                              │
│  THINGS TO TEST:                                                             │
│  ✓ OptionList has focus on open                                               │
│  ✓ Current device marked with ◄                                              │
│  ✓ Arrow keys move selection                                                 │
│  ✓ Enter → switches mic mid-recording; notification shown "Switched to: X"   │
│  ✓ Escape → cancels; notification "Mic unchanged"                            │
│  ✓ Recording continues without interruption during mic switch                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Workflow 5: Toggle Speaker Capture

```
RECORDING SCREEN (speaker capture OFF: ^o Speaker ▶)
     │
     │  Press ^o  OR  Click "^o Speaker ▶"
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  RECORDING SCREEN (speaker capture ON: ^o Speaker ▼)                        │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ [accent bg]  liscribe ● REC 00:00:12 + Speaker    [^o Speaker ▼] [^l] │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ Mic: Built-in Microphone                                               │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │ │ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁   (mic waveform)                                 │ │  │
│  │ └────────────────────────────────────────────────────────────────────┘ │  │
│  │ Speaker                                                                │  │
│  │ ┌────────────────────────────────────────────────────────────────────┐ │  │
│  │ │ ▃▄▅▆▇█▇▆▅▄▃   (speaker waveform, now visible)                     │ │  │
│  │ └────────────────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  THINGS TO TEST:                                                             │
│  ✓ Status bar gains "+ Speaker"                                              │
│  ✓ Speaker waveform section appears below mic waveform                       │
│  ✓ Speaker button label changes ▶ → ▼                                       │
│  ✓ Notification "Speaker capture added"                                      │
│  ✓ ^o again → speaker waveform hides; notification "Speaker capture off"    │
│  ! Requires BlackHole virtual audio device on macOS                          │
│  ! If BlackHole not found: error notification shown, no crash                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Workflow 6: View Transcripts

```
HOME SCREEN
     │
     │  Press ^t  OR  Click "^t Transcripts"
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  TRANSCRIPTS SCREEN                                                          │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          liscribe                                      │  │
│  │                        Transcripts                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │ [Scrollable list]                                                │  │  │
│  │  │   15-01-2024   2024-01-15_10-30-00.md                           │  │  │
│  │  │   ┌──────────────────────────────────────────────────────────┐  │  │  │
│  │  │   │  Copy to clipboard                                       │  │  │  │
│  │  │   └──────────────────────────────────────────────────────────┘  │  │  │
│  │  │   14-01-2024   2024-01-14_15-22-00.md                           │  │  │
│  │  │   ┌──────────────────────────────────────────────────────────┐  │  │  │
│  │  │   │  Copy to clipboard                                       │  │  │  │
│  │  │   └──────────────────────────────────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │  Back to Home                                                    │  │  │
│  │  └──────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  THINGS TO TEST:                                                             │
│  ✓ Transcripts listed newest first                                           │
│  ✓ Empty state: "No transcripts yet. Record and save to see them here."      │
│  ✓ Tab reaches each Copy button and Back button                              │
│  ✓ Click/Enter on Copy → notification "Copied to clipboard"                  │
│  ✓ Escape → back to Home                                                     │
│  ✓ Click/Enter Back to Home → back to Home                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Workflow 7: Quit

```
HOME SCREEN
     │
     │  Press ^c
     ▼
App exits (terminal returns to shell prompt)
No confirmation dialog — immediate exit.

THINGS TO TEST:
✓ ^c at Home exits cleanly (no Python traceback)
✓ Terminal returns to normal (no mangled cursor/state)
```

---

## Keyboard Shortcut Reference

### Home Screen

| Key | Action |
|-----|--------|
| `^r` | Open Recording screen |
| `^p` | Open Preferences |
| `^t` | Open Transcripts |
| `^c` | Quit app |
| `Tab` | Cycle through buttons |
| `Enter` | Activate focused button |

### Recording Screen

| Key | Action |
|-----|--------|
| `^s` | Stop recording and save |
| `^c` | Open Cancel confirm modal |
| `^l` | Open Mic select modal |
| `^o` | Toggle speaker capture |
| `^n` | Focus note input |
| `^y` | Screenshot (Textual built-in) |
| `Tab` | Cycle: Speaker btn → Mic btn → note input → Save btn → Cancel btn |
| `Enter` (in note input) | Submit note |

### Confirm Cancel Modal

| Key | Action |
|-----|--------|
| `y` | Confirm cancel (discard recording) |
| `n` | Keep recording |
| `Escape` | Keep recording |
| `↑` / `↓` | Navigate options |
| `Enter` | Select highlighted option |

### Mic Select Modal

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate mic list |
| `Enter` | Select microphone |
| `Escape` | Cancel (keep current mic) |

### Preferences / All Back-Screens

| Key | Action |
|-----|--------|
| `Escape` | Go back one screen |
| `Tab` | Cycle through buttons |
| `Enter` | Activate focused button |

### Transcribing Screen

| Key | Action | Notes |
|-----|--------|-------|
| (none while running) | — | btn-back disabled |
| `Enter` | Go back to Home | Only after transcription complete |
| `Tab` | Reach btn-back | After transcription complete |

---

## Focus State Summary (What Should Be Focused on Each Screen Load)

| Screen | Expected Initial Focus | Currently Set? |
|--------|----------------------|----------------|
| HomeScreen | `btn-record` | No explicit set (Textual default) — verify |
| RecordingScreen | `#note-input` | **Yes** (`on_mount` explicit) |
| TranscribingScreen | Nothing (btn-back disabled) | Bug — nothing focused |
| TranscribingScreen (done) | `btn-back` | Bug — not auto-focused |
| PreferencesHubScreen | `btn-deps` | No explicit set (Textual default) — verify |
| PrefsDependenciesScreen | First button/item | Not read — verify |
| PrefsAliasScreen | Input field | Not read — verify |
| PrefsWhisperScreen | First option | Not read — verify |
| PrefsSaveLocationScreen | Input field | Not read — verify |
| TranscriptsScreen | First Copy button or Back? | No explicit set — verify |
| MicSelectScreen | `OptionList` | Textual default — verify |
| ConfirmCancelScreen | `OptionList` | Textual default — verify |
