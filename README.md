# Liscribe

100% offline terminal audio recorder and transcriber for macOS.
![Liscribe home screenshot](liscribe_home.png)

Record from your microphone (and optionally system audio via BlackHole), transcribe locally with faster-whisper, and save Markdown transcripts — all without any network access.

## Install

Requires macOS, Python 3.10+, and [Homebrew](https://brew.sh).

```bash
git clone <repo-url> liscribe
cd liscribe
./install.sh
```

The installer will:

1. Check and install Homebrew dependencies (PortAudio, optionally BlackHole)
2. Create a Python virtual environment and install the package
3. Let you choose a whisper model and transcription language
4. Set up a shell alias (default: `rec`)

Open a new terminal after install, then you're ready to go.

## Uninstall

```bash
cd liscribe
./uninstall.sh
```

This removes the virtual environment, config, model cache, and shell alias. Optionally removes Homebrew dependencies (portaudio, blackhole-2ch, switchaudio-osx).

## Usage
![Liscribe record screenshot](liscribe_rec.png)
### Interactive TUI

Just run `rec` with no arguments to open the interactive interface:

```bash
rec
```

From the home screen you can:

- **Record** — start a recording with a live waveform display; add timestamped notes during the session; save to trigger transcription
- **Transcripts** — browse, copy, open, or delete saved transcripts
- **Preferences** — configure general settings, save location, Whisper model/language, dictation, and dependencies
- **Help** — full command reference

Transcription runs in the background with a real-time progress bar. When done, open the transcript directly in your configured editor.

### CLI

For scripting or headless use:

```bash
rec -f /path/to/save              # Record mic, save to folder (opens TUI recording screen)
rec -f /path/to/save -s           # Record mic + speaker (BlackHole), source-labeled merge
rec -f /path/to/save --mic "USB"  # Use a specific microphone
rec -h                            # Save to ./docs/transcripts in current directory
rec transcribe file.wav           # Transcribe existing audio (or rec t file.wav)
rec devices                       # List available input devices
rec setup                         # Re-configure model, language, check deps
rec config --show                 # Show current config
rec dictate                       # System-wide dictation: double-tap ⌥ to record, paste transcript
rec dictate --model tiny          # Use a faster model for dictation
rec dictate --hotkey right_ctrl   # Use a different trigger key
rec dictate --no-sounds           # Disable system sounds
rec --help                        # Full command and option list
```

During recording you can type notes; they are timestamped and included in the transcript as footnote references [1], [2] and a Notes section.

With `-s`, Liscribe records two source tracks (`mic.wav`, `speaker.wav`) and writes a merged chronological transcript where speaker labels are deterministic:

```text
[00:03.2] YOU: ...
[00:05.7] THEM: ...
```

### Dictation

`rec dictate` runs a persistent listener in your terminal. Double-tap **Right Option (⌥)**
from any app — browser, Slack, notes — to start recording. Tap it once more to stop. The
transcript is pasted at the cursor in whatever window is focused.

Feedback while recording:
- macOS system sounds at each stage (start / stop / paste / error)
- macOS notification toasts with a preview of the pasted text
- Live waveform + elapsed timer in the terminal window

First run: macOS will prompt for **Input Monitoring** and **Accessibility** permissions in
System Settings → Privacy & Security. Grant both, then re-run.

Configure in **Preferences → Dictation** in the TUI, or directly in config.

For permission setup and auto-start, see [docs/dictation-setup.md](docs/dictation-setup.md).

## Models and transcription

- **Default model** comes from config (`whisper_model`). Override per run with `--tiny`, `--base`, `--small`, `--medium`, `--large` (short: `-xxs`, `-xs`, `-sm`, `-md`, `-lg`).
- **Multi-model:** pass multiple flags (e.g. `rec -f ~/out -sm -md`) to get one transcript per model; filenames get a model suffix when using more than one; clipboard gets the highest-quality result.
- Download and remove models from **Preferences → Whisper** in the TUI, or run `rec setup`.

## Configuration

Config lives at `~/.config/liscribe/config.json`. Edit directly or use **Preferences** in the TUI. See `config.example.json` for all options with descriptions.

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `whisper_model` | `base` | Model size: `tiny`, `base`, `small`, `medium`, `large` |
| `language` | `en` | ISO 639-1 code (`en`, `fr`, `de`, ...) or `auto` for auto-detect |
| `save_folder` | `~/transcripts` | Default output folder (override with `-f`) |
| `open_transcript_app` | `cursor` | Editor for "Open transcript" — `cursor`, `code`, `vim`, `nvim`, or `default` |
| `dictation_model` | `base` | Whisper model for dictation (`tiny` for fastest response) |
| `dictation_hotkey` | `right_option` | Trigger key: `right_option`, `right_ctrl`, `right_shift`, `caps_lock` |
| `dictation_sounds` | `true` | Play macOS system sounds for each dictation stage |

## System Requirements

- **macOS**
- **Python 3.10+**
- **Homebrew**
- **PortAudio** — installed automatically by `install.sh`
- **BlackHole + switchaudio-osx** (optional, for `-s` speaker capture) — offered during install

### BlackHole Setup (for speaker capture)

After installing BlackHole (offered during `./install.sh`):

1. Open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup")
2. Click **+** → **Create Multi-Output Device**
3. Check your speakers/headphones **and** BlackHole 2ch
4. Now `rec -f path -s` will switch output to this device during recording

## Architecture

See [docs/architecture.md](docs/architecture.md) for C4 diagrams.

## License

Liscribe is free software: you can redistribute it and/or modify it under
the terms of the **GNU General Public License** as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version.

You should have received a copy of the GNU General Public License along with
this program. If not, see <https://www.gnu.org/licenses/>.
