# Liscribe v2 — Terminal-only distribution

Install and run Liscribe from the terminal. No .app bundle.

**Install:** `./install.sh`

- Requires Python 3.10+, Homebrew, and `portaudio` (`brew install portaudio`).
- Optional: `brew install --cask blackhole-2ch` for speaker capture.
- Creates a venv in the repo and runs `pip install -e .`.
- Cleans any existing liscribe lines from `~/.zshrc`, then adds: `alias liscribe='<repo>/liscribe'` (the `liscribe` script in the repo root is a wrapper that runs the app).
- Prints a permissions hint: allow **Terminal** (or **Python**) in System Settings → Privacy & Security for Accessibility, Input Monitoring, and Microphone.

**Run:** `liscribe` (after `source ~/.zshrc` or a new terminal). From Shortcuts or other automation (which don’t load `.zshrc`), run the wrapper by full path, e.g. `/Users/you/repos/liscribe/liscribe`.

**Uninstall:** `./uninstall.sh` — removes the alias from `.zshrc`, config, cache, and login item.
