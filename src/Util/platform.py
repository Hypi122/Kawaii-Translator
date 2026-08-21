"""
Minimal platform-detection helpers (stdlib only).
"""
import os
import sys


def is_windows():
    return sys.platform.startswith("win")


def is_linux():
    return sys.platform == "linux"


def is_macos():
    return sys.platform == "darwin"


def is_wayland():
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return True
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def is_x11():
    if os.environ.get("XDG_SESSION_TYPE") == "x11":
        return True
    return bool(os.environ.get("DISPLAY"))
