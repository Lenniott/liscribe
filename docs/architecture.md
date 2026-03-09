# Liscribe v2 — C4 Architecture

> Defined in Phase 2. Implementation fills in from Phase 3 onward.
> Diagrams use [Mermaid C4](https://mermaid.js.org/syntax/c4.html) (compatible with C4-PlantUML).

---

## Level 1 — System Context

Who uses the system and what the system does.

```mermaid
C4Context
    Person(user, "User", "Mac, git-clone audience. Uses Scribe (record + transcribe), Dictate, Transcribe (existing files).")
    System(liscribe, "Liscribe", "Menu bar app, no terminal. Reads mic + system audio (BlackHole). Writes transcripts/WAVs. faster-whisper, local only. No network after model download.")
    Rel(user, liscribe, "Uses")
```

---

## Level 2 — Container

Major building blocks inside Liscribe.

```mermaid
C4Container
    Person(user, "User")
    Container_Boundary(liscribe, "Liscribe.app") {
        Container(menubar, "Menu Bar", "rumps", "Dropdown, hotkeys (Scribe, Dictate, Transcribe, Settings)")
        Container(panels, "Panel Layer", "pywebview", "ScribePanel, TranscribePanel, DictatePanel, SettingsPanel, OnboardingPanel")
        Container(services, "Services", "Python", "AudioService, ModelService, ConfigService, HotkeyService")
        Container(engine, "Engine", "Python", "recorder, transcriber, output, notes, transcribe_worker, waveform, config, platform_setup, replacements")
    }
    Rel(user, menubar, "Uses")
    Rel(menubar, panels, "Opens")
    Rel(panels, services, "Uses")
    Rel(services, engine, "Wraps")
```

**Single instance**  
Only one Liscribe process runs per user. A file lock under `~/.cache/liscribe` plus a Unix socket are used so a second launch does not start a duplicate; instead it signals the existing instance to activate (bring to front) and exits. See `app_instance` in the codebase.

**Menu bar icon**  
The menu bar item is controlled in `app.py`. When available (macOS 11+), the app uses an NSImage built from the SF Symbol "mic" (dark rounded rect with white mic glyph) and sets it as the application icon; otherwise it falls back to `MENU_BAR_TITLE` (default `"🎙"`). To change the fallback, edit `MENU_BAR_TITLE`; to use a different image, see `_menubar_icon_image()` in `app.py`.

**Process display name**  
On launch, the app sets the process display name (e.g. "Liscribe") via the macOS ApplicationServices API so CMD+Tab and the Dock show the app name instead of "Python" when run as a script.

**Distribution**  
Install via `./install.sh` (venv + alias in `~/.zshrc`). Run `liscribe` from the terminal to start the app. Uninstall via `./uninstall.sh` (removes alias, config, cache).

---

## Level 3 — Component (Panel Layer)

Components inside the Panel Layer. Each panel follows the same pattern: HTML view, Bridge (JS↔Python), Controller.

```mermaid
C4Component
    Container_Boundary(panel_layer, "Panel Layer") {
        Component(scribe, "ScribePanel", "HTML + pywebview", "Record, waveform, notes. ScribeBridge, ScribeController.")
        Component(transcribe, "TranscribePanel", "HTML + pywebview", "File picker, model list. TranscribeBridge, TranscribeController.")
        Component(dictate, "DictatePanel", "HTML + pywebview", "Waveform, timer. DictateBridge, DictateController.")
        Component(settings, "SettingsPanel", "HTML + pywebview", "Tabs: General, Models, Hotkeys, Replacements, Deps, Help. SettingsBridge.")
        Component(onboarding, "OnboardingPanel", "HTML + pywebview", "Wizard, practice steps. OnboardingBridge, OnboardingController.")
    }
    Container_Ext(services, "Services", "Python", "AudioService, ModelService, ConfigService, HotkeyService")
    Rel(scribe, services, "Uses")
    Rel(transcribe, services, "Uses")
    Rel(dictate, services, "Uses")
    Rel(settings, services, "Reads/writes Config")
    Rel(onboarding, services, "Calls workflows")
```

---

## Panel contracts and behaviour

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

**Panel load — pywebview API readiness**  
The JS bridge (`pywebview.api`) may not be injectable immediately on `window.load`. Panels that depend on it for initial data (e.g. model list, mic list) should delay the first API call briefly (e.g. 80 ms), then retry once after a short backoff (e.g. 250 ms) if the result is empty. Scribe and Transcribe both use this pattern so the model list and device list populate reliably instead of staying blank.

**TranscribePanel**
- HTML/CSS view
- TranscribeBridge
- TranscribeController — file input → ModelService → output

**DictatePanel** (floating, near cursor)
- HTML/CSS view (minimal: waveform + timer only)
- DictateBridge
- DictateController — hotkey state machine + AudioService + paste

**SettingsPanel**
- HTML/CSS view (tabbed: General, Models, Hotkeys, Replacements, Deps, Help)
- SettingsBridge — exposes `restart_app()` so the user can apply hotkey changes (app quits and relaunches via launchd when running as .app)
- reads/writes ConfigService directly

**OnboardingPanel**
- HTML/CSS view (stepped wizard)
- OnboardingBridge
- OnboardingController — tracks completion in config, blocks app until complete on first launch, exposes replay from Settings
- calls real workflows for practice steps

**Shared services (not panels):**
- **AudioService** — wraps recorder.py; one instance, shared across panels
- **ModelService** — wraps transcriber.py; download, load, run
- **ConfigService** — wraps config.py; single source of config truth
- **HotkeyService** — pynput listener; fires callbacks to DictateController and ScribeController
