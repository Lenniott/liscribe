# Settings TUI and CLI — Full TUI-First App

## Principle

**The whole app lives in the Textual TUI.** The CLI is a launcher: terminal commands jump to a specific screen for speed. Inside the app, every page is also reachable via **keyboard shortcuts**.

---

## CLI → Screen mapping (terminal shortcuts)

| Command | Lands on |
|--------|----------|
| `rec` | **Home** |
| `rec -i` / `rec --init` | **Record** TUI (start recording) |
| `rec preferences` | **Preferences** TUI (same info and actions as current `rec setup` and `rec config`) |
| `rec help` | **Help** TUI (same content as `rec --help`) |
| `rec devices` | **Devices** TUI (list input devices in the app, not in terminal) |

No separate `rec setup` or `rec config` in the long term — their behaviour lives in the Preferences TUI. Optionally keep `rec setup` / `rec config` as aliases that launch the TUI on the Preferences screen.

---

## Recording → Transcribing → Home flow

1. User is on **Record** (via Home button, `^r`, or `rec -i`).
2. Recording ends (Stop & Save or Cancel).
3. If saved: show **Transcribing** TUI (progress, model(s), maybe “Saved to …” / clipboard). No terminal transcription output — all in-app.
4. When transcribing finishes (or user dismisses): go back to **Home**.

Cancel during recording still returns to Home (no transcribing step).

---

## Screens and keyboard shortcuts

Each main destination has a keyboard shortcut so you can move without leaving the TUI:

- **Home** — hub: Record, Preferences, Transcripts, Help?, Devices?, Quit. Shortcuts: e.g. **^r** Record, **^p** Preferences, **^t** Transcripts, **^Q** Quit. (Help and Devices can be buttons or shortcuts from Home.)
- **Record** — current recording UI (waveform, mic, notes, Stop & Save / Cancel). Existing bindings (^s, ^C, ^l, ^o, ^n).
- **Preferences** — hub then sub-screens: Dependencies, Alias, Whisper, Save location (same actions as setup/config). Back to Home or Preferences hub.
- **Transcripts** — list from save_folder, copy to clipboard; back to Home.
- **Help** — scrollable text = same as `--help` (usage, options, subcommands). Back to Home.
- **Devices** — list input devices (like `rec devices` today). Back to Home.
- **Transcribing** — shown after Record when user saved; progress then “Done” / back to Home.

All styles from **rec.css**; screens in separate modules under **screens/**; **app.py** as controller (push_screen, initial screen from CLI args).

---

## Implementation summary

- **CLI:** Single entry that always launches the TUI. Parses “landing” intent: no args → Home; `-i`/`--init` → Record; subcommands `preferences`, `help`, `devices` → push that screen on startup. Pass through -f/-s/--mic etc. when going to Record.
- **App:** One Textual app. Startup: push the requested screen (Home, Record, Preferences, Help, or Devices). No process exit after recording — run transcription in-process and show Transcribing screen, then pop back to Home.
- **Screens (separate .py files):** Home, Recording, Transcribing, Preferences (hub + prefs_dependencies, prefs_alias, prefs_whisper, prefs_save_location), Transcripts, Help, Devices.
- **Preferences TUI** replicates setup + config: dependency check (+ Install), alias (update zshrc), Whisper (language, default model, download/remove models), save location.
- **Help TUI** renders the same text as Click’s `--help` (e.g. get_help from context or build a static string).
- **Devices TUI** uses existing `list_input_devices()` (or equivalent) and displays the list in a scrollable widget.

Implementation order: CLI (landing flags + subcommands) and single app entry → Home + keyboard shortcuts → Record screen → Transcribing screen and “back to Home” flow → Preferences (hub + all sub-screens) → Help screen → Devices screen → Transcripts screen.
