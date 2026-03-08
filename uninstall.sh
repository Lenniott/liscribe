#!/usr/bin/env bash
# Remove Liscribe: alias from .zshrc, config, cache, login item. Optionally .app if present.

set -e

APP_NAME="Liscribe"
APP_BUNDLE="/Applications/${APP_NAME}.app"
CONFIG_DIR="${HOME}/.config/liscribe"
CACHE_DIR="${HOME}/.cache/liscribe"
ZSHRC="${HOME}/.zshrc"

# Remove liscribe-related lines from .zshrc
clean_zshrc() {
  if [[ ! -f "$ZSHRC" ]]; then
    return
  fi
  if grep -q "liscribe" "$ZSHRC"; then
    echo "Removing liscribe alias from ~/.zshrc..."
    local tmp
    tmp=$(mktemp)
    grep -v "liscribe" "$ZSHRC" > "$tmp" || true
    mv "$tmp" "$ZSHRC"
  fi
}

remove_app() {
  if [[ -d "$APP_BUNDLE" ]]; then
    echo "Removing ${APP_BUNDLE}..."
    rm -rf "$APP_BUNDLE"
  fi
}

remove_config() {
  if [[ -d "$CONFIG_DIR" ]]; then
    echo "Removing ${CONFIG_DIR}..."
    rm -rf "$CONFIG_DIR"
  fi
}

remove_cache() {
  if [[ -d "$CACHE_DIR" ]]; then
    echo "Removing ${CACHE_DIR}..."
    rm -rf "$CACHE_DIR"
  fi
}

remove_login_item() {
  if osascript -e "tell application \"System Events\" to get the name of every login item" 2>/dev/null | grep -q "$APP_NAME"; then
    echo "Removing ${APP_NAME} from login items..."
    osascript -e "tell application \"System Events\" to delete login item \"${APP_NAME}\"" 2>/dev/null || true
  fi
}

remove_launchd_plist() {
  local plist="${HOME}/Library/LaunchAgents/com.liscribe.app.plist"
  if [[ -f "$plist" ]]; then
    echo "Removing LaunchAgent plist..."
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
  fi
}

clean_zshrc
remove_app
remove_config
remove_cache
remove_login_item
remove_launchd_plist
echo "Uninstall complete."
