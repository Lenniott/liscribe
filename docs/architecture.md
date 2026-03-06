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
