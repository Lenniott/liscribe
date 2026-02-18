#!/usr/bin/env bash
set -euo pipefail

# ── Liscribe installer ──────────────────────────────────────────────────────
# Usage: git clone <repo> && cd liscribe && ./install.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
ALIAS_MARKER="# liscribe"
MIN_PYTHON_MINOR=10

info()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
fail()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*"; }
die()   { fail "$*"; exit 1; }

# ── 1. Prerequisites ────────────────────────────────────────────────────────

info "Checking prerequisites"

[[ "$(uname)" == "Darwin" ]] || die "Liscribe requires macOS."
ok "macOS detected"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 \
                 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidate" &>/dev/null; then
        minor="$("$candidate" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)" || continue
        if (( minor >= MIN_PYTHON_MINOR )); then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    die "Python 3.$MIN_PYTHON_MINOR+ not found. Install with: brew install python@3.13"
fi
py_version="$("$PYTHON" -c 'import sys; print(sys.version_info.minor)')"
ok "Python 3.$py_version ($PYTHON)"

if ! command -v brew &>/dev/null; then
    die "Homebrew not found. Install from https://brew.sh"
fi
ok "Homebrew"

# ── 2. Brew dependencies ────────────────────────────────────────────────────

info "Checking Homebrew dependencies"

install_brew_if_missing() {
    local pkg="$1"
    if brew list "$pkg" &>/dev/null; then
        ok "$pkg already installed"
        return 0
    fi
    warn "$pkg not installed — installing..."
    brew install "$pkg"
    ok "$pkg installed"
}

install_brew_if_missing portaudio

printf '\n'
read -rp "  Enable speaker/system-audio capture? (requires BlackHole) [y/N] " speaker_yn
if [[ "$speaker_yn" == [yY] ]]; then
    install_brew_if_missing blackhole-2ch
    install_brew_if_missing switchaudio-osx
fi

# ── 3. Python venv & package ────────────────────────────────────────────────

info "Setting up Python environment"

if [[ -d "$VENV_DIR" ]]; then
    warn "Existing .venv found — recreating"
    rm -rf "$VENV_DIR"
fi

"$PYTHON" -m venv "$VENV_DIR"
ok "Virtual environment created"

printf '  Installing dependencies (this may take a minute)...'
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR" --quiet
printf '\r'
ok "liscribe installed into venv                        "

# ── 4. Interactive configuration ─────────────────────────────────────────────

info "Configuration"

WHISPER_MODELS=("tiny" "base" "small" "medium" "large")
WHISPER_DESCS=(
    "~75 MB,  fastest, least accurate"
    "~150 MB, good balance for short recordings"
    "~500 MB, higher accuracy"
    "~1.5 GB, near-best accuracy, slower"
    "~3 GB,   best accuracy, slowest"
)

echo ""
echo "  Available whisper models:"
for i in "${!WHISPER_MODELS[@]}"; do
    printf '    %d. %-8s %s\n' $((i+1)) "${WHISPER_MODELS[$i]}" "${WHISPER_DESCS[$i]}"
done
echo ""

default_model=2
while true; do
    read -rp "  Choose a model [1-${#WHISPER_MODELS[@]}] (default: $default_model): " model_choice
    model_choice="${model_choice:-$default_model}"
    if [[ "$model_choice" =~ ^[1-5]$ ]]; then
        break
    fi
    warn "Enter a number between 1 and ${#WHISPER_MODELS[@]}"
done
chosen_model="${WHISPER_MODELS[$((model_choice-1))]}"
ok "Model: $chosen_model"

echo ""
read -rp "  Transcription language (ISO 639-1 code, e.g. en, fr, de, or 'auto') [en]: " chosen_lang
chosen_lang="${chosen_lang:-en}"
chosen_lang="$(echo "$chosen_lang" | tr '[:upper:]' '[:lower:]')"
ok "Language: $chosen_lang"

"$VENV_DIR/bin/python" -c "
from liscribe.config import load_config, save_config, init_config_if_missing
init_config_if_missing()
cfg = load_config()
cfg['whisper_model'] = '$chosen_model'
cfg['language'] = '$chosen_lang'
save_config(cfg)
"
ok "Config saved to ~/.config/liscribe/config.json"

# ── 5. Shell alias ──────────────────────────────────────────────────────────

info "Shell alias setup"

detect_shell_rc() {
    local sh
    sh="$(basename "${SHELL:-/bin/zsh}")"
    case "$sh" in
        zsh)  echo "$HOME/.zshrc" ;;
        bash) echo "$HOME/.bashrc" ;;
        *)    echo "$HOME/.${sh}rc" ;;
    esac
}

SHELL_RC="$(detect_shell_rc)"
REC_BIN="$VENV_DIR/bin/rec"

echo ""
read -rp "  Alias name (default: rec): " alias_name
alias_name="${alias_name:-rec}"

ALIAS_LINE="alias ${alias_name}='${REC_BIN}'  ${ALIAS_MARKER}"

if [[ -f "$SHELL_RC" ]]; then
    existing="$(grep "$ALIAS_MARKER" "$SHELL_RC" 2>/dev/null || true)"
    if [[ -n "$existing" ]]; then
        warn "Found existing liscribe alias in $SHELL_RC:"
        echo "    $existing"
        read -rp "  Remove and replace it? [Y/n] " replace_yn
        if [[ "$replace_yn" != [nN] ]]; then
            sed_backup=".liscribe-bak"
            sed -i"$sed_backup" "/$ALIAS_MARKER/d" "$SHELL_RC"
            rm -f "${SHELL_RC}${sed_backup}"
            ok "Removed old alias"
        else
            warn "Keeping existing alias — skipping"
            alias_name=""
        fi
    fi
fi

if [[ -n "$alias_name" ]]; then
    touch "$SHELL_RC"
    printf '\n%s\n' "$ALIAS_LINE" >> "$SHELL_RC"
    ok "Added to $SHELL_RC: $ALIAS_LINE"
fi

# ── 6. Download whisper model ────────────────────────────────────────────────

info "Whisper model"

echo ""
read -rp "  Download/verify the '$chosen_model' model now? [Y/n] " dl_yn
if [[ "$dl_yn" != [nN] ]]; then
    echo "  Downloading '$chosen_model' (this may take a moment)..."
    "$VENV_DIR/bin/python" -c "
from liscribe.transcriber import load_model
load_model('$chosen_model')
"
    ok "Model '$chosen_model' ready"
else
    warn "Skipped — model will download on first use"
fi

# ── 7. Done ──────────────────────────────────────────────────────────────────

echo ""
info "Installation complete!"
echo ""
echo "  To start using liscribe, either:"
echo "    1. Open a new terminal, or"
echo "    2. Run: source $SHELL_RC"
echo ""
echo "  Then:"
echo "    ${alias_name:-rec} -f ~/transcripts              # record mic"
echo "    ${alias_name:-rec} -f ~/transcripts -s           # record mic + speaker"
echo "    ${alias_name:-rec} setup                         # re-configure model/language"
echo "    ${alias_name:-rec} devices                       # list audio devices"
echo ""
