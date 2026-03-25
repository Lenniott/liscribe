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

# kCFStringEncodingUTF8
_kCFStringEncodingUTF8 = 0x08000100


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

        cf = _load_corefoundation()

        # Build proper CFStringRef args when CoreFoundation is available (always
        # true on real macOS). When CF is absent (non-macOS test environments
        # where IOKit is mocked), pass null void pointers — the mock accepts any
        # value, and this branch can never execute on real macOS without CF.
        if cf is not None:
            assertion_type = _cf_string(cf, _ASSERTION_TYPE)
            assertion_name = _cf_string(cf, _ASSERTION_NAME)
        else:
            assertion_type = ctypes.c_void_p(0)
            assertion_name = ctypes.c_void_p(0)
            cf = None  # ensure we don't try CFRelease below

        _set_iopm_argtypes(iokit)

        assertion_id = ctypes.c_uint32(0)
        ret = iokit.IOPMAssertionCreateWithName(
            assertion_type,
            _ASSERTION_LEVEL_ON,
            assertion_name,
            ctypes.byref(assertion_id),
        )
        if cf is not None:
            if assertion_type:
                cf.CFRelease(assertion_type)
            if assertion_name:
                cf.CFRelease(assertion_name)

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


def _load_corefoundation() -> ctypes.CDLL | None:
    """Load CoreFoundation framework. Returns None if unavailable."""
    try:
        path = ctypes.util.find_library("CoreFoundation")
        if path is None:
            return None
        return ctypes.CDLL(path)
    except Exception as exc:
        logger.debug("Could not load CoreFoundation: %s", exc)
        return None


def _cf_string(cf: ctypes.CDLL, text: str) -> ctypes.c_void_p | None:
    """Create a CFStringRef from a Python str. Caller must CFRelease the result."""
    try:
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        result = cf.CFStringCreateWithCString(None, text.encode("utf-8"), _kCFStringEncodingUTF8)
        return ctypes.c_void_p(result) if result else None
    except Exception as exc:
        logger.debug("_cf_string failed for %r: %s", text, exc)
        return None


def _set_iopm_argtypes(iokit: ctypes.CDLL) -> None:
    """Set IOPMAssertionCreateWithName argtypes so ctypes passes CFStringRef correctly."""
    iokit.IOPMAssertionCreateWithName.restype = ctypes.c_uint32
    iokit.IOPMAssertionCreateWithName.argtypes = [
        ctypes.c_void_p,   # CFStringRef AssertionType
        ctypes.c_uint32,   # IOPMAssertionLevel AssertionLevel
        ctypes.c_void_p,   # CFStringRef AssertionName
        ctypes.POINTER(ctypes.c_uint32),  # IOPMAssertionID *AssertionID
    ]
