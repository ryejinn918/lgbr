"""Cross-platform process status helpers."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def pid_is_alive(pid: int | None) -> bool:
    """Return whether a PID is running without signaling or terminating it."""
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True



def durable_workers_enabled() -> bool:
    """Whether API requests should be queued for long-lived worker processes."""
    return (os.environ.get("LGBR_DURABLE_WORKERS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
def _windows_pid_is_alive(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    access_denied = 5

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return ctypes.get_last_error() == access_denied
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)