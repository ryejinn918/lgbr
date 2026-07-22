"""Fnguide login, search, and download automation."""

from fnsearch.browser import LOGIN_URL, goto_login, launch_browser, open_login
from fnsearch.session import (
    SessionRun,
    capture_session,
    hold_session,
    load_session,
    login,
    login_and_capture,
    logout,
    verify_session,
)
from fnsearch.status import clear_status, get_status, set_status

__all__ = [
    "LOGIN_URL",
    "SessionRun",
    "capture_session",
    "clear_status",
    "get_status",
    "goto_login",
    "hold_session",
    "launch_browser",
    "load_session",
    "login",
    "login_and_capture",
    "logout",
    "open_login",
    "set_status",
    "verify_session",
]
