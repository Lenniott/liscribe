#!/usr/bin/env bash
# Liscribe installer — guides you from zero to a running app.
# Each step tries to auto-fix before failing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
ZSHRC="${HOME}/.zshrc"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/.local/share/liscribe"

# ── Colours ──────────────────────────────────────────────────────────────────
BOLD=$'\e[1m'; RESET=$'\e[0m'
GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; CYAN=$'\e[36m'

step() { echo; echo "${BOLD}${CYAN}Step $1 — $2${RESET}"; }
ok()   { echo "  ${GREEN}✓${RESET}  $*"; }
info() { echo "     $*"; }
warn() { echo "  ${YELLOW}⚠${RESET}  $*"; }
die()  { echo; echo "  ${RED}✗${RESET}  $*" >&2; exit 1; }

MIN_MAJOR=3; MIN_MINOR=10

# ── Step 1 — Python 3.10+ ─────────────────────────────────────────────────
step 1 "Python 3.10+"

# Search for a qualifying Python: try versioned names first (newest → oldest),
# then fall back to unversioned python3. This handles the common case where
# python3 in PATH is an older system install but python3.14 (etc.) is also present.
PYTHON_CMD=""
_py_ok() {
  local cmd="$1"
  command -v "$cmd" &>/dev/null || return 1
  local major minor
  major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null) || return 1
  minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null) || return 1
  [[ "$major" -gt "$MIN_MAJOR" ]] || { [[ "$major" -eq "$MIN_MAJOR" ]] && [[ "$minor" -ge "$MIN_MINOR" ]]; }
}
for _candidate in python3.15 python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
  if _py_ok "$_candidate"; then
    PYTHON_CMD="$_candidate"
    break
  fi
done

if [[ -z "$PYTHON_CMD" ]]; then
  # Check if python3 exists but is just too old — give a more helpful message.
  if command -v python3 &>/dev/null; then
    PY_OLD=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "unknown")
    die "Python ${MIN_MAJOR}.${MIN_MINOR}+ is required (found python3 = ${PY_OLD}). Download Python 3.10+ from https://python.org/downloads then open a new terminal and run install.sh again."
  else
    die "Python ${MIN_MAJOR}.${MIN_MINOR}+ is required. Download it from https://python.org/downloads"
  fi
fi
PY_VER=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Python $PY_VER ($PYTHON_CMD)"

# ── Step 2 — Homebrew ─────────────────────────────────────────────────────
step 2 "Homebrew"
if ! command -v brew &>/dev/null; then
  echo
  info "Homebrew is needed to install audio libraries."
  read -r -p "     Install Homebrew now? [Y/n] " BREW_CHOICE
  BREW_CHOICE="${BREW_CHOICE:-Y}"
  if [[ "$BREW_CHOICE" =~ ^[Yy]$ ]]; then
    /bin/bash -c "$(curl -fsSL https://brew.sh/install.sh)"
    # Add brew to PATH for this session (Apple Silicon and Intel paths)
    if [[ -f /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -f /usr/local/bin/brew ]]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
    if ! command -v brew &>/dev/null; then
      die "Homebrew install finished but brew command not found. Open a new terminal and run install.sh again."
    fi
  else
    die "Homebrew is required. Install it from https://brew.sh then run install.sh again."
  fi
fi
ok "Homebrew $(brew --version 2>/dev/null | head -1 | awk '{print $2}')"

# ── Step 3 — portaudio ────────────────────────────────────────────────────
step 3 "portaudio (required for audio)"
if ! brew list portaudio &>/dev/null 2>&1; then
  info "Installing portaudio..."
  brew install portaudio
fi
ok "portaudio"

# ── Step 4 — BlackHole 2ch (optional) ────────────────────────────────────
step 4 "BlackHole 2ch (optional — records system audio)"
if ! brew list --cask blackhole-2ch &>/dev/null 2>&1; then
  echo
  read -r -p "     Install BlackHole for speaker capture (records both mic and system audio)? [y/N] " BH_CHOICE
  BH_CHOICE="${BH_CHOICE:-N}"
  if [[ "$BH_CHOICE" =~ ^[Yy]$ ]]; then
    brew install --cask blackhole-2ch
    ok "BlackHole 2ch installed"
  else
    info "Skipped. You can set it up later from Settings → Deps."
  fi
else
  ok "BlackHole 2ch"
fi

# ── Step 5 — Python venv + packages ──────────────────────────────────────
step 5 "Python venv + packages"
cd "$SCRIPT_DIR"
if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating virtual environment..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi
info "Installing packages (this may take a minute)..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -e . -q
ok "Packages installed"

# ── Step 6 — LaunchAgent plist (login startup) ────────────────────────────
step 6 "LaunchAgent (login startup)"
mkdir -p "$LAUNCH_AGENTS"
mkdir -p "$LOG_DIR"
PLIST_DST="${LAUNCH_AGENTS}/com.liscribe.app.plist"
# Preserve existing RunAtLoad so reinstall doesn't reset the user's preference.
EXISTING_RUN_AT_LOAD="false"
if [[ -f "$PLIST_DST" ]]; then
  VAL=$(/usr/libexec/PlistBuddy -c "Print :RunAtLoad" "$PLIST_DST" 2>/dev/null || echo "false")
  [[ "$VAL" == "true" ]] && EXISTING_RUN_AT_LOAD="true"
fi
cat > "$PLIST_DST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.liscribe.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>${SCRIPT_DIR}/liscribe</string>
    </array>
    <key>RunAtLoad</key>
    <${EXISTING_RUN_AT_LOAD}/>
    <key>KeepAlive</key>
    <false/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/liscribe.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/liscribe.log</string>
</dict>
</plist>
PLIST_EOF
ok "LaunchAgent plist written to $PLIST_DST"

# ── Step 7 — Shell alias ──────────────────────────────────────────────────
step 7 "Shell alias"
touch "$ZSHRC"
TMP_ZSHRC=$(mktemp)
grep -v "alias liscribe=" "$ZSHRC" > "$TMP_ZSHRC" || true
mv "$TMP_ZSHRC" "$ZSHRC"
echo "" >> "$ZSHRC"
echo "alias liscribe='${SCRIPT_DIR}/liscribe'" >> "$ZSHRC"
ok "Alias added to ~/.zshrc"

# ── Step 8 — Launch Liscribe ──────────────────────────────────────────────
step 8 "Launching Liscribe"
info "Starting Liscribe..."
"${SCRIPT_DIR}/liscribe" &

echo
echo "  ${GREEN}${BOLD}Liscribe is starting — look for the 🎙 icon in your menu bar (top right).${RESET}"
echo "  On first launch, Liscribe walks you through permissions and model setup."
echo
