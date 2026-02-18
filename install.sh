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

# ── 2. Brew dependencies (check only; do not install) ────────────────────────

info "Checking Homebrew dependencies"

printf '\n'
read -rp "  Enable speaker/system-audio capture? (requires BlackHole) [y/N] " speaker_yn

# Check required: portaudio. If speaker requested, also check blackhole-2ch and switchaudio-osx.
MISSING=()
MISSING_CASK=()

if ! brew list portaudio &>/dev/null; then
    MISSING+=(portaudio)
fi

if [[ "$speaker_yn" == [yY] ]]; then
    if ! brew list --cask blackhole-2ch &>/dev/null; then
        MISSING_CASK+=(blackhole-2ch)
    fi
    if ! brew list switchaudio-osx &>/dev/null; then
        MISSING+=(switchaudio-osx)
    fi
fi

# If any dependency is missing, print instructions and exit (do not run brew install).
if [[ ${#MISSING[@]} -gt 0 ]] || [[ ${#MISSING_CASK[@]} -gt 0 ]]; then
    echo ""
    fail "Some dependencies are missing."
    echo ""
    for pkg in "${MISSING[@]}"; do
        case "$pkg" in
            portaudio)
                echo "  You need portaudio for audio recording in liscribe."
                echo "  More info: https://formulae.brew.sh/formula/portaudio"
                ;;
            switchaudio-osx)
                echo "  You need switchaudio-osx to switch system output when using speaker capture (-s)."
                echo "  More info: https://formulae.brew.sh/formula/switchaudio-osx"
                ;;
            *)
                echo "  You need $pkg for liscribe."
                echo "  More info: https://formulae.brew.sh/formula/$pkg"
                ;;
        esac
        echo ""
    done
    for pkg in "${MISSING_CASK[@]}"; do
        case "$pkg" in
            blackhole-2ch)
                echo "  You need blackhole-2ch for system/speaker audio capture (-s) in liscribe."
                echo "  More info: https://existential.audio/blackhole/ or https://formulae.brew.sh/cask/blackhole-2ch"
                ;;
            *)
                echo "  You need $pkg for liscribe."
                echo "  More info: https://formulae.brew.sh/cask/$pkg"
                ;;
        esac
        echo ""
    done
    echo "  Install the missing items above (e.g. with Homebrew), then run ./install.sh again."
    echo ""
    read -rp "  Do you want to see install commands? [y/N] " show_cmds
    if [[ "$show_cmds" == [yY] ]]; then
        echo ""
        for pkg in "${MISSING[@]}"; do
            echo "  brew install $pkg"
        done
        for pkg in "${MISSING_CASK[@]}"; do
            echo "  brew install --cask $pkg"
        done
        echo ""
        if [[ ${#MISSING_CASK[@]} -gt 0 ]]; then
            echo "  Note: Cask installs (e.g. BlackHole) may request your password and a reboot."
            echo ""
        fi
    fi
    exit 1
fi

# All required deps present — report and continue (no brew install from this script).
if brew list portaudio &>/dev/null; then
    ok "portaudio already installed"
fi
if [[ "$speaker_yn" == [yY] ]]; then
    if brew list --cask blackhole-2ch &>/dev/null; then
        ok "blackhole-2ch already installed"
    fi
    if brew list switchaudio-osx &>/dev/null; then
        ok "switchaudio-osx already installed"
    fi
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
# #region agent log
DEBUG_LOG="$SCRIPT_DIR/.cursor/debug-3b00e9.log"
# #endregion
for i in "${!WHISPER_MODELS[@]}"; do
    model_name="${WHISPER_MODELS[$i]}"
    installed_marker=""
    if "$VENV_DIR/bin/python" -c "from liscribe.transcriber import is_model_available; exit(0 if is_model_available('$model_name') else 1)" 2>/dev/null; then
        installed_marker=" ✓"
    fi
    printf '    %d. %-8s %s%s\n' $((i+1)) "$model_name" "${WHISPER_DESCS[$i]}" "$installed_marker"
done
echo ""
echo "  Enter numbers to download (e.g. 2,4,5 or 2-5 or all)"

default_model=2
sorted_indices=()
while true; do
    read -rp "  Models to download (default: $default_model): " model_choice
    model_choice="${model_choice:-$default_model}"
    # #region agent log
    echo "{\"sessionId\":\"3b00e9\",\"location\":\"install.sh:model_choice\",\"message\":\"model_choice\",\"data\":{\"raw\":\"$model_choice\"},\"timestamp\":$(date +%s)000}" >> "${DEBUG_LOG}" 2>/dev/null || true
    # #endregion
    
    # Parse "1,3,5", "1 3 5", "2-4", "all"
    indices=()
    if [[ "$model_choice" == "all" ]]; then
        for i in "${!WHISPER_MODELS[@]}"; do
            indices+=($((i+1)))
        done
    else
        # Replace commas with spaces, then split
        cleaned="${model_choice//,/ }"
        for part in $cleaned; do
            if [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
                # Range like "2-4"
                start="${BASH_REMATCH[1]}"
                end="${BASH_REMATCH[2]}"
                for ((i=start; i<=end; i++)); do
                    if (( i >= 1 && i <= ${#WHISPER_MODELS[@]} )); then
                        indices+=($i)
                    fi
                done
            elif [[ "$part" =~ ^[0-9]+$ ]]; then
                # Single number
                num=$((part))
                if (( num >= 1 && num <= ${#WHISPER_MODELS[@]} )); then
                    indices+=($num)
                fi
            fi
        done
    fi
    
    # Remove duplicates and sort (no associative arrays — Bash 3.2 / macOS compatible)
    if (( ${#indices[@]} > 0 )); then
        unique_indices=()
        for idx in "${indices[@]}"; do
            found=0
            # Check if idx already in unique_indices (handle empty array case)
            if (( ${#unique_indices[@]} > 0 )); then
                for u in "${unique_indices[@]}"; do
                    [[ "$u" == "$idx" ]] && { found=1; break; }
                done
            fi
            [[ $found -eq 0 ]] && unique_indices+=($idx)
        done
        # Sort unique indices
        if (( ${#unique_indices[@]} > 0 )); then
            IFS=$'\n' sorted_indices=($(sort -n <<<"${unique_indices[*]}"))
            unset IFS
        else
            sorted_indices=()
        fi
        # #region agent log
        echo "{\"sessionId\":\"3b00e9\",\"location\":\"install.sh:parsed\",\"message\":\"parsed_indices\",\"data\":{\"sorted\":\"${sorted_indices[*]}\",\"count\":${#sorted_indices[@]}},\"timestamp\":$(date +%s)000}" >> "${DEBUG_LOG}" 2>/dev/null || true
        # #endregion
        if (( ${#sorted_indices[@]} > 0 )); then
            break
        fi
    fi
    
    warn "Enter numbers (e.g. 2,4,5 or 2-5 or all)"
done

# Convert indices to model names
to_download=()
for idx in "${sorted_indices[@]}"; do
    to_download+=("${WHISPER_MODELS[$((idx-1))]}")
done

# Prompt for default model
default_idx=$default_model
# #region agent log
echo "{\"sessionId\":\"3b00e9\",\"location\":\"install.sh:default_check\",\"message\":\"default_model_check\",\"data\":{\"default_idx\":$default_idx,\"sorted_indices\":\"${sorted_indices[*]}\"},\"timestamp\":$(date +%s)000}" >> "${DEBUG_LOG}" 2>/dev/null || true
# #endregion
# Check if default is in selection (Bash 3.2 compatible)
default_in_selection=0
for idx in "${sorted_indices[@]}"; do
    if [[ "$idx" == "$default_idx" ]]; then
        default_in_selection=1
        break
    fi
done
if [[ $default_in_selection -eq 1 ]]; then
    # Default is in the selection, use it
    chosen_model="${WHISPER_MODELS[$((default_idx-1))]}"
    # #region agent log
    echo "{\"sessionId\":\"3b00e9\",\"location\":\"install.sh:default_set\",\"message\":\"default_model_set\",\"data\":{\"chosen\":\"$chosen_model\"},\"timestamp\":$(date +%s)000}" >> "${DEBUG_LOG}" 2>/dev/null || true
    # #endregion
else
    # Default not in selection, prompt
    echo ""
    echo "  Which model as default for recordings?"
    for idx in "${sorted_indices[@]}"; do
        printf '    %d. %s\n' "$idx" "${WHISPER_MODELS[$((idx-1))]}"
    done
    while true; do
        read -rp "  Default model (number): " default_choice
        if [[ "$default_choice" =~ ^[0-9]+$ ]]; then
            # Check if choice is in selection
            choice_in_selection=0
            for idx in "${sorted_indices[@]}"; do
                if [[ "$idx" == "$default_choice" ]]; then
                    choice_in_selection=1
                    break
                fi
            done
            if [[ $choice_in_selection -eq 1 ]]; then
                chosen_model="${WHISPER_MODELS[$((default_choice-1))]}"
                break
            fi
        fi
        warn "Enter a number from your selection"
    done
fi

if (( ${#to_download[@]} == 1 )); then
    ok "Model: ${to_download[0]}"
else
    ok "Models: ${to_download[*]}"
fi

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

# ── 6. Download whisper models ────────────────────────────────────────────────

info "Whisper models"

if (( ${#to_download[@]} == 0 )); then
    warn "No models selected — skipping download"
else
    models_str="${to_download[*]}"
    models_str="${models_str// /, }"
    echo ""
    read -rp "  Download ${#to_download[@]} model(s) now? ($models_str) [Y/n] " dl_yn
    if [[ "$dl_yn" != [nN] ]]; then
        for model_name in "${to_download[@]}"; do
            # Check if already installed
            if "$VENV_DIR/bin/python" -c "from liscribe.transcriber import is_model_available; exit(0 if is_model_available('$model_name') else 1)" 2>/dev/null; then
                echo "  Skipping '$model_name' (already installed)"
                continue
            fi
            echo "  Downloading '$model_name' (this may take a moment)..."
            if "$VENV_DIR/bin/python" -c "
from liscribe.transcriber import load_model
load_model('$model_name')
" 2>&1; then
                ok "Model '$model_name' ready"
            else
                warn "Failed to download '$model_name'"
            fi
        done
    else
        warn "Skipped — models will download on first use"
    fi
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
echo "    ${alias_name:-rec} setup                         # add/change models or language"
echo "    ${alias_name:-rec} devices                       # list audio devices"
echo ""
echo "  Use -xxs -xs -sm -md -lg to transcribe with multiple models (e.g. ${alias_name:-rec} -h -xxs -sm)."
echo "  Run ${alias_name:-rec} setup to download any models you did not install now."
echo ""
