---
name: Centralize screen shortcuts
overview: Centralize keyboard shortcuts in a shared bindings module and a base screen class so all "back" screens and recording/home screens get their bindings from one place instead of repeating BINDINGS and action_back on each screen.
todos: []
---

# Centralize shortcuts for all screens

## Current state

- **Back (Escape)**: Eight screens each define the same `BINDINGS = [Binding("escape", "back", "Back")]` and nearly identical `action_back()` (pop_screen; some then push Home if stack is empty): devices_screen, help_screen, preferences, transcripts, prefs_dependencies, prefs_alias, prefs_whisper, prefs_save_location.
- **Recording**: Same six bindings (stop_save, cancel, change_mic, toggle_speaker, focus_notes, screenshot) are defined on both RecordingApp (app.py) and RecordingScreen (screens/recording.py), with action logic duplicated in both.
- **Home**: HomeScreen defines four bindings (record, preferences, transcripts, quit) and the corresponding actions.

## Speaker toggle (recording screen) — keep as-is

The **speaker toggle** (`^o` / `action_toggle_speaker`) is more complex than the other recording bindings and must **not** be moved to any shared mixin or base:

- It calls into `RecordingSession` (enable_speaker_capture, open/close speaker stream, patch callback for waveform).
- It manages `self.speaker`, `self.waveform_speaker`, and DOM (button label, CSS class `waveform-speaker-on`, waveform widget updates).
- Startup in `on_mount` also wires speaker (set_output_device, open speaker stream, patch callback).

The plan only centralizes the **binding list** (`RECORDING_BINDINGS`). All **action methods** for recording—including `action_toggle_speaker`, `action_add_speaker_capture`, and `action_remove_speaker_capture`—stay on **RecordingApp** and **RecordingScreen** respectively. No shared base or mixin for recording actions.

## Approach

1. **Shared bindings constants** — One module defines the binding lists (keys and labels only).
2. **Base screen class** — A `BackScreen` base provides escape→back and a single `action_back()` so individual screens don’t repeat bindings or back logic.

Modals (MicSelectScreen, ConfirmCancelScreen) keep their own bindings (cancel / yes / no).

## Implementation

### 1. Add shared bindings and base screen

Create **src/liscribe/screens/base.py**:

- **Binding lists**: `BACK_BINDINGS`, `RECORDING_BINDINGS` (same six as today in app.py), `HOME_BINDINGS` (four from home.py).
- **BackScreen(Screen)**: `BINDINGS = BACK_BINDINGS`; `action_back()` does `pop_screen()` and, if stack empty, lazy-import HomeScreen and push it.

### 2. Switch “back” screens to BackScreen

In each of the eight screens: inherit from `BackScreen`, remove local `BINDINGS` and `action_back` (and any button handler that only called them).

### 3. Use shared bindings for Recording and Home

- **RecordingApp** (app.py): `BINDINGS = RECORDING_BINDINGS` from base; leave all `action_*` (including speaker toggle) on the app.
- **RecordingScreen** (screens/recording.py): `BINDINGS = RECORDING_BINDINGS` from base; leave all `action_*` (including speaker toggle) on the screen.
- **HomeScreen** (screens/home.py): `BINDINGS = HOME_BINDINGS` from base; keep screen-specific actions.

### 4. Exports

In screens/__init__.py, export `BackScreen` if needed; binding constants stay in base for use by screens and app.

## Result

- One place for “back” binding and behavior (BackScreen + BACK_BINDINGS).
- One place for recording **shortcut definitions** (RECORDING_BINDINGS); recording **actions** (including the complex speaker toggle) remain on RecordingApp and RecordingScreen.
- One place for home shortcut definitions (HOME_BINDINGS).
