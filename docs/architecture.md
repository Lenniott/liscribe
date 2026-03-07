# Liscribe v2 — C4 Architecture

> Defined in Phase 2. Implementation fills in from Phase 3 onward.

---

## Context — what Liscribe is and who uses it

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

---

## Container — major building blocks

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

---

## Component — inside the Panel Layer

Each panel is a self-contained component:

**ScribePanel**
- HTML/CSS view (pywebview)
- ScribeBridge — JS↔Python calls (recording controls, waveform, notes)
- ScribeController — orchestrates AudioService + ModelService

**App–panel contract (Scribe)**  
The app owns Scribe window lifecycle and confirm-close behaviour. It wires four callbacks through ScribeBridge so the panel can trigger app actions:

- **close_panel** — destroy the Scribe window (e.g. after “Leave and discard”).
- **request_close** — trigger the native close flow (same confirm dialog as the red X).
- **transcription_finished** — app sets `confirm_close = False` so the red X closes without prompting.
- **open_in_transcribe** — open Transcribe panel with prefill (from Scribe).

The app sets **confirm_close** on the pywebview window (True while recording/transcribing so the red X shows the confirm dialog; False after transcription is done). The Cocoa backend reads this at close time. This is part of the window contract: see “Window options” below.

**Window options (pywebview)**  
For Scribe, the app passes `confirm_close=True` when creating the window and later mutates `window.confirm_close` (True/False). The pywebview Cocoa layer reads this attribute when the user hits the red X to decide whether to show the “Recording in progress…” dialog. If pywebview changes how confirm works, this contract may need updating.

**TranscribePanel**
- HTML/CSS view
- TranscribeBridge
- TranscribeController — file input → ModelService → output

**DictatePanel** (floating, near cursor)
- HTML/CSS view (minimal: waveform + timer only)
- DictateBridge
- DictateController — hotkey state machine + AudioService + paste

**SettingsPanel**
- HTML/CSS view (tabbed: General, Models, Hotkeys, Deps, Help)
- SettingsBridge
- reads/writes ConfigService directly

**OnboardingPanel**
- HTML/CSS view (stepped wizard)
- OnboardingBridge
- calls real workflows for practice steps

**Shared services (not panels):**
- **AudioService** — wraps recorder.py; one instance, shared across panels
- **ModelService** — wraps transcriber.py; download, load, run
- **ConfigService** — wraps config.py; single source of config truth
- **HotkeyService** — pynput listener; fires callbacks to DictateController and ScribeController
