"""macOS power assertion — prevent process sleep during recording.

Acquires a PreventUserIdleSystemSleep assertion via IOPMAssertionCreateWithName.
This allows the display to sleep and the screen to lock normally, but prevents
the OS from suspending processes.

All functions are no-ops on non-macOS platforms and fail silently on error.
Nothing in this module ever raises.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import sys

logger = logging.getLogger(__name__)

_ASSERTION_TYPE = "PreventUserIdleSystemSleep"
_ASSERTION_NAME = "Liscribe recording in progress"
_ASSERTION_LEVEL_ON = 255  # kIOPMAssertionLevelOn

_NO_ASSERTION: int = 0  # sentinel for "no active assertion"


def acquire_recording_assertion() -> int:
    """Acquire a system-sleep prevention assertion.

    Returns an assertion ID > 0 on success, or 0 if unavailable/failed.
    Safe to call from any thread.
    """
    if sys.platform != "darwin":
        return _NO_ASSERTION

    try:
        iokit = _load_iokit()
        if iokit is None:
            return _NO_ASSERTION

        assertion_id = ctypes.c_uint32(0)
        ret = iokit.IOPMAssertionCreateWithName(
            _ASSERTION_TYPE.encode(),
            _ASSERTION_LEVEL_ON,
            _ASSERTION_NAME.encode(),
            ctypes.byref(assertion_id),
        )
        if ret != 0:
            logger.debug("IOPMAssertionCreateWithName returned %d", ret)
            return _NO_ASSERTION

        logger.debug("Power assertion acquired: id=%d", assertion_id.value)
        return int(assertion_id.value)

    except Exception as exc:
        logger.debug("acquire_recording_assertion failed: %s", exc)
        return _NO_ASSERTION


def release_recording_assertion(assertion_id: int) -> None:
    """Release a previously acquired assertion.

    Safe to call with assertion_id=0 (no-op). Safe to call from any thread.
    """
    if sys.platform != "darwin" or assertion_id == _NO_ASSERTION:
        return

    try:
        iokit = _load_iokit()
        if iokit is None:
            return

        ret = iokit.IOPMAssertionRelease(ctypes.c_uint32(assertion_id))
        if ret != 0:
            logger.debug("IOPMAssertionRelease returned %d (id=%d)", ret, assertion_id)
        else:
            logger.debug("Power assertion released: id=%d", assertion_id)

    except Exception as exc:
        logger.debug("release_recording_assertion failed: %s", exc)


def _load_iokit() -> ctypes.CDLL | None:
    """Load IOKit framework. Returns None if unavailable."""
    try:
        path = ctypes.util.find_library("IOKit")
        if path is None:
            return None
        return ctypes.CDLL(path)
    except Exception as exc:
        logger.debug("Could not load IOKit: %s", exc)
        return None
