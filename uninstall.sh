#!/usr/bin/env bash
set -euo pipefail

# ── Liscribe uninstaller ────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
CONFIG_DIR="$HOME/.config/liscribe"
CACHE_DIR="$HOME/.cache/liscribe"
ALIAS_MARKER="# liscribe"

info()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
fail()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*"; }

detect_shell_rc() {
    local sh
    sh="$(basename "${SHELL:-/bin/zsh}")"
    case "$sh" in
        zsh)  echo "$HOME/.zshrc" ;;
        bash) echo "$HOME/.bashrc" ;;
        *)    echo "$HOME/.${sh}rc" ;;
    esac
}

echo ""
info "Liscribe uninstaller"
echo ""
echo "  This will remove:"
echo "    - Python venv        ($VENV_DIR)"
echo "    - Config directory   ($CONFIG_DIR)"
echo "    - Model cache        ($CACHE_DIR)"
echo "    - Shell alias from   $(detect_shell_rc)"
echo ""
read -rp "  Continue? [y/N] " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "  Aborted."
    exit 0
fi

# ── 1. Remove Python venv ───────────────────────────────────────────────────

info "Removing Python virtual environment"

if [[ -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
    ok "Removed $VENV_DIR"
else
    warn "No venv found at $VENV_DIR — skipping"
fi

# ── 2. Reset config ─────────────────────────────────────────────────────────

info "Removing config and settings"

if [[ -d "$CONFIG_DIR" ]]; then
    rm -rf "$CONFIG_DIR"
    ok "Removed $CONFIG_DIR"
else
    warn "No config found at $CONFIG_DIR — skipping"
fi

# ── 3. Remove model cache ───────────────────────────────────────────────────

info "Removing model cache"

if [[ -d "$CACHE_DIR" ]]; then
    rm -rf "$CACHE_DIR"
    ok "Removed $CACHE_DIR"
else
    warn "No cache found at $CACHE_DIR — skipping"
fi

# ── 4. Remove shell alias ───────────────────────────────────────────────────

info "Removing shell alias"

SHELL_RC="$(detect_shell_rc)"

if [[ -f "$SHELL_RC" ]]; then
    existing="$(grep "$ALIAS_MARKER" "$SHELL_RC" 2>/dev/null || true)"
    if [[ -n "$existing" ]]; then
        echo "  Found: $existing"
        sed_backup=".liscribe-bak"
        sed -i"$sed_backup" "/$ALIAS_MARKER/d" "$SHELL_RC"
        rm -f "${SHELL_RC}${sed_backup}"
        ok "Removed liscribe alias from $SHELL_RC"
    else
        warn "No liscribe alias found in $SHELL_RC"
    fi
else
    warn "Shell config $SHELL_RC not found — skipping"
fi

# ── 5. Optionally remove Homebrew dependencies ──────────────────────────────

info "Homebrew dependencies"

brew_deps=()
for pkg in portaudio blackhole-2ch switchaudio-osx; do
    if brew list "$pkg" &>/dev/null; then
        brew_deps+=("$pkg")
    fi
done

if (( ${#brew_deps[@]} == 0 )); then
    warn "No liscribe-related brew packages found"
else
    echo ""
    echo "  The following brew packages were found:"
    for pkg in "${brew_deps[@]}"; do
        echo "    - $pkg"
    done
    echo ""
    read -rp "  Remove these brew packages? [y/N] " brew_yn
    if [[ "$brew_yn" == [yY] ]]; then
        for pkg in "${brew_deps[@]}"; do
            echo "  Removing $pkg..."
            brew uninstall "$pkg" 2>/dev/null || warn "Could not remove $pkg"
            ok "Removed $pkg"
        done
    else
        ok "Keeping brew packages"
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
info "Uninstall complete"
echo ""
echo "  Open a new terminal (or source $(detect_shell_rc)) to clear the alias."
echo "  The liscribe source code is still in: $SCRIPT_DIR"
echo "  To fully remove, run: rm -rf $SCRIPT_DIR"
echo ""
