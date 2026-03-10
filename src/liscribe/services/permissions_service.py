"""macOS permission checks for Dictate workflow.

Checks Accessibility and Input Monitoring at runtime (never cached).
Used by DictateController to gate dictation and by the Settings → Deps tab
(Phase 7) to show live permission status.

No engine imports. All platform checks use standard macOS APIs via ctypes or
system commands. Fails gracefully on non-macOS and when frameworks are absent.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# System Settings pane identifiers (macOS Ventura+)
_PANE_ACCESSIBILITY = "com.apple.preference.security?Privacy_Accessibility"
_PANE_INPUT_MONITORING = "com.apple.preference.security?Privacy_ListenEvent"
_PANE_MICROPHONE = "com.apple.preference.security?Privacy_Microphone"

_PANE_URLS: dict[str, str] = {
    "accessibility": _PANE_ACCESSIBILITY,
    "input_monitoring": _PANE_INPUT_MONITORING,
    "microphone": _PANE_MICROPHONE,
}


def _is_macos() -> bool:
    return sys.platform == "darwin"


def check_accessibility() -> bool:
    """Return True if this process has Accessibility (AX) permission.

    Uses AXIsProcessTrusted() via AppKit/ApplicationServices.
    Returns False on non-macOS or if the check itself fails.
    """
    if not _is_macos():
        return False
    try:
        import AppKit  # noqa: F401 — ensures framework is available
        from ctypes import cdll, c_bool
        ax = cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        ax.AXIsProcessTrusted.restype = c_bool
        return bool(ax.AXIsProcessTrusted())
    except Exception:
        logger.debug("AXIsProcessTrusted check failed", exc_info=True)
        return False


def check_microphone() -> bool:
    """Return True if this process has Microphone permission (or can list input devices).

    Best-effort: try to query default input device. On macOS without mic permission
    this may still succeed depending on OS version; used for Settings → Deps display.
    """
    if not _is_macos():
        return False
    try:
        import sounddevice as sd
        _ = sd.query_devices(kind="input")
        return True
    except Exception:
        logger.debug("Microphone check failed", exc_info=True)
        return False


def check_input_monitoring() -> bool:
    """Return True if this process has Input Monitoring permission.

    Input Monitoring cannot be checked programmatically without triggering
    a permission prompt. Best-effort: we try importing pynput and doing a
    quick listener creation, catching PermissionError / similar failures.

    Returns False on non-macOS.

    Note: On macOS 14+ pynput may raise during listener start if permission
    is absent. This check is advisory — the actual failure will surface when
    HotkeyService tries to start the listener.

    WARNING: Do not call this from the pywebview JS bridge thread (e.g. from
    Settings panel). Use _check_input_monitoring_subprocess() there instead.
    """
    if not _is_macos():
        return False
    try:
        from pynput import keyboard as _kb

        # Creating a Listener and immediately stopping it is the least intrusive
        # way to probe Input Monitoring without installing a real handler.
        # On permission-denied systems this raises immediately.
        with _kb.Listener(on_press=None, on_release=None):
            pass
        return True
    except Exception:
        logger.debug("Input Monitoring check failed", exc_info=True)
        return False


def _check_input_monitoring_subprocess() -> bool:
    """Run the pynput listener check in a subprocess so the main process (or
    bridge thread) never creates a listener. Creating a listener on the
    pywebview bridge thread crashes the app on macOS.
    """
    if not _is_macos():
        return False
    script = """
from pynput import keyboard
try:
    with keyboard.Listener(on_press=None, on_release=None):
        pass
    print('true')
except Exception:
    print('false')
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Subprocess exits 0 and prints 'true' when granted; else False.
        return result.stdout.strip() == "true" if result.returncode == 0 else False
    except Exception:
        return False


def get_all_permissions() -> dict[str, bool]:
    """Return live status for all permissions used in Settings → Deps.

    Keys: microphone, accessibility, input_monitoring.
    Checked live every call — never cached.
    """
    return {
        "microphone": check_microphone(),
        "accessibility": check_accessibility(),
        "input_monitoring": _check_input_monitoring_subprocess(),
    }


def has_dictate_permissions() -> tuple[bool, list[str]]:
    """Check all permissions required for Dictate.

    Returns (all_granted, list_of_missing_permission_names).
    The list is empty when all permissions are granted.

    Checked live every call — never cached.
    Uses _check_input_monitoring_subprocess() so the main thread never creates
    a pynput listener (creating one when a Liscribe panel is key can crash the app).
    """
    missing: list[str] = []

    if not check_accessibility():
        missing.append("Accessibility")

    if not _check_input_monitoring_subprocess():
        missing.append("Input Monitoring")

    return (len(missing) == 0, missing)


def get_python_executable_paths() -> dict[str, str]:
    """Return the current Python executable paths for Input Monitoring guidance.

    Returns two paths:
    - "executable": sys.executable (the running binary, possibly a symlink)
    - "real_path": os.path.realpath(sys.executable) (resolved through all symlinks)

    Both are returned because macOS Input Monitoring may show either one depending
    on the Python installation (homebrew, pyenv, bundled .app, etc.).
    """
    executable = sys.executable
    real_path = os.path.realpath(executable)
    return {
        "executable": executable,
        "real_path": real_path,
    }


def open_system_settings(pane: str) -> None:
    """Open the specified macOS System Settings pane.

    pane: one of "accessibility", "input_monitoring", "microphone".
    No-op (with a warning) for unknown pane names or on non-macOS.
    """
    if not _is_macos():
        logger.warning("open_system_settings: not macOS, ignoring pane=%r", pane)
        return

    url = _PANE_URLS.get(pane)
    if url is None:
        logger.warning("open_system_settings: unknown pane %r", pane)
        return

    try:
        subprocess.run(
            ["open", f"x-apple.systempreferences:{url}"],
            check=False,
            timeout=5,
        )
    except Exception:
        logger.warning("open_system_settings: failed to open pane %r", pane, exc_info=True)
