"""macOS platform checks: PortAudio, BlackHole, switchaudio-osx, Multi-Output Device."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)


def is_macos() -> bool:
    return sys.platform == "darwin"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout.strip()
    except FileNotFoundError:
        return -1, ""
    except subprocess.TimeoutExpired:
        return -2, ""


def check_portaudio() -> tuple[bool, str]:
    """Check if PortAudio is available (needed by sounddevice)."""
    try:
        import sounddevice  # noqa: F401
        return True, "PortAudio is available."
    except OSError:
        return False, (
            "PortAudio not found. Install it with:\n"
            "  brew install portaudio\n"
            "Then restart your terminal."
        )


def check_blackhole() -> tuple[bool, str]:
    """Check if BlackHole virtual audio device is available."""
    if not is_macos():
        return False, "BlackHole is macOS-only."

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for d in devices:
            if "blackhole" in d["name"].lower():
                return True, f"BlackHole found: {d['name']}"
        return False, (
            "BlackHole not found. Install it with:\n"
            "  brew install blackhole-2ch\n"
            "Then restart your audio system or reboot."
        )
    except Exception as exc:
        return False, f"Could not query audio devices: {exc}"


def check_switchaudio() -> tuple[bool, str]:
    """Check if switchaudio-osx CLI is installed."""
    if shutil.which("SwitchAudioSource"):
        return True, "switchaudio-osx is available."
    return False, (
        "switchaudio-osx not found. Install it with:\n"
        "  brew install switchaudio-osx\n"
        "Needed for automatic audio routing with -s flag."
    )


def check_multi_output_device(device_name: str = "Multi-Output Device") -> tuple[bool, str]:
    """Check if a Multi-Output Device exists in macOS audio system."""
    if not is_macos():
        return False, "Multi-Output Device check is macOS-only."

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for d in devices:
            if device_name.lower() in d["name"].lower():
                return True, f"Multi-Output Device found: {d['name']}"
        return False, (
            f"Multi-Output Device '{device_name}' not found.\n"
            "Create it in Audio MIDI Setup:\n"
            "  1. Open Audio MIDI Setup (Spotlight → 'Audio MIDI Setup')\n"
            "  2. Click + → Create Multi-Output Device\n"
            "  3. Check your speakers/headphones AND BlackHole 2ch"
        )
    except Exception as exc:
        return False, f"Could not query audio devices: {exc}"


def get_current_output_device() -> str | None:
    """Get the current system audio output device name (macOS)."""
    if not is_macos():
        return None
    code, name = _run(["SwitchAudioSource", "-c", "-t", "output"])
    if code == 0 and name:
        return name
    return None


def set_output_device(device_name: str) -> bool:
    """Switch the macOS system audio output device."""
    if not is_macos():
        return False
    code, _ = _run(["SwitchAudioSource", "-s", device_name, "-t", "output"])
    if code == 0:
        logger.info("Switched audio output to: %s", device_name)
        return True
    logger.error("Failed to switch audio output to: %s", device_name)
    return False


def run_all_checks(include_speaker: bool = False) -> list[tuple[str, bool, str]]:
    """Run platform checks. Returns list of (check_name, passed, message)."""
    results: list[tuple[str, bool, str]] = []

    ok, msg = check_portaudio()
    results.append(("PortAudio", ok, msg))

    if include_speaker:
        ok, msg = check_blackhole()
        results.append(("BlackHole", ok, msg))

        ok, msg = check_switchaudio()
        results.append(("switchaudio-osx", ok, msg))

        ok, msg = check_multi_output_device()
        results.append(("Multi-Output Device", ok, msg))

    return results


# Map check name to brew install command (for TUI Install button)
_BREW_INSTALL: dict[str, list[str]] = {
    "PortAudio": ["brew", "install", "portaudio"],
    "BlackHole": ["brew", "install", "--cask", "blackhole-2ch"],
    "switchaudio-osx": ["brew", "install", "switchaudio-osx"],
    # Multi-Output Device: no brew, user creates in Audio MIDI Setup
}

_BREW_REMOVE: dict[str, list[str]] = {
    "PortAudio": ["brew", "uninstall", "portaudio"],
    "BlackHole": ["brew", "uninstall", "--cask", "blackhole-2ch"],
    "switchaudio-osx": ["brew", "uninstall", "switchaudio-osx"],
}


def get_install_command(check_name: str) -> list[str] | None:
    """Return the brew install command for a check, or None if not installable via brew."""
    return _BREW_INSTALL.get(check_name)


def get_remove_command(check_name: str) -> list[str] | None:
    """Return the brew uninstall command for a check, or None if not removable via brew."""
    return _BREW_REMOVE.get(check_name)


def run_install(check_name: str) -> tuple[bool, str]:
    """Run the install command for the given check. Returns (success, output_or_error)."""
    cmd = get_install_command(check_name)
    if not cmd:
        return False, "No install command (e.g. create Multi-Output Device in Audio MIDI Setup)."
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (result.stdout or "").strip() + "\n" + (result.stderr or "").strip()
        return result.returncode == 0, out or "(no output)"
    except subprocess.TimeoutExpired:
        return False, "Install timed out."
    except Exception as exc:
        return False, str(exc)


def run_remove(check_name: str) -> tuple[bool, str]:
    """Run the uninstall command for the given check. Returns (success, output_or_error)."""
    cmd = get_remove_command(check_name)
    if not cmd:
        return False, "No uninstall command for this dependency."
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (result.stdout or "").strip() + "\n" + (result.stderr or "").strip()
        return result.returncode == 0, out or "(no output)"
    except subprocess.TimeoutExpired:
        return False, "Uninstall timed out."
    except Exception as exc:
        return False, str(exc)
