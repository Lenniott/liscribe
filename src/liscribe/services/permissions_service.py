"""macOS permission checks for Dictate workflow.

Checks Accessibility and Input Monitoring at runtime (never cached).
Used by DictateController to gate dictation and by the Settings → Deps tab
(Phase 7) to show live permission status.

No engine imports. All platform checks use standard macOS APIs via ctypes or
system commands. Fails gracefully on non-macOS and when frameworks are absent.
"""

from __future__ import annotations

import logging
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


def check_input_monitoring() -> bool:
    """Return True if this process has Input Monitoring permission.

    Input Monitoring cannot be checked programmatically without triggering
    a permission prompt. Best-effort: we try importing pynput and doing a
    quick listener creation, catching PermissionError / similar failures.

    Returns False on non-macOS.

    Note: On macOS 14+ pynput may raise during listener start if permission
    is absent. This check is advisory — the actual failure will surface when
    HotkeyService tries to start the listener.
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


def has_dictate_permissions() -> tuple[bool, list[str]]:
    """Check all permissions required for Dictate.

    Returns (all_granted, list_of_missing_permission_names).
    The list is empty when all permissions are granted.

    Checked live every call — never cached.
    """
    missing: list[str] = []

    if not check_accessibility():
        missing.append("Accessibility")

    if not check_input_monitoring():
        missing.append("Input Monitoring")

    return (len(missing) == 0, missing)


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
