# Liscribe

100% offline terminal audio recorder and transcriber for macOS.

Record from your microphone (and optionally system audio via BlackHole), transcribe locally with faster-whisper, and save Markdown transcripts — all without any network access.

## Quick Start

```bash
# Clone and set up
cd liscribe
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Record (mic only)
rec -f ~/transcripts

# Record mic + system audio (requires BlackHole)
rec -f ~/transcripts -s
```

## System Requirements (macOS)

- **Python 3.10+**
- **PortAudio** — `brew install portaudio`
- **BlackHole** (optional, for `-s` speaker capture) — [existential.audio/blackhole](https://existential.audio/blackhole/)
- **switchaudio-osx** (optional, for `-s`) — `brew install switchaudio-osx`

### BlackHole Setup (for speaker capture)

1. Install BlackHole 2ch: `brew install blackhole-2ch`
2. Open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup")
3. Click **+** → **Create Multi-Output Device**
4. Check your speakers/headphones **and** BlackHole 2ch
5. Now `rec -f path -s` will switch output to this device during recording

## Usage

```bash
rec -f /path/to/save              # Record mic, save audio to folder
rec -f /path/to/save -s           # Record mic + speaker (BlackHole)
rec -f /path/to/save --mic "USB"  # Use a specific microphone
rec devices                       # List available input devices
rec setup                         # Check dependencies, download whisper model
rec config --show                 # Show current config
```

## Configuration

Config lives at `~/.config/liscribe/config.json`. See `config.example.json` for all options with descriptions.

## Architecture

See [docs/architecture.md](docs/architecture.md) for C4 diagrams.
