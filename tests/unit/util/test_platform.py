import sys

import pytest

from Util.platform import is_linux, is_macos, is_windows, is_wayland, is_x11


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)


class TestIsWayland:
    def test_isWayland_true_whenXdgSessionTypeIsWayland(self, clean_env, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        assert is_wayland() is True

    def test_isWayland_true_whenWaylandDisplayIsSet(self, clean_env, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert is_wayland() is True

    def test_isWayland_falseWhenX11SessionWithDisplay(self, clean_env, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        monkeypatch.setenv("DISPLAY", ":0")
        assert is_wayland() is False


class TestIsX11:
    def test_isX11_trueWhenDisplayIsSet(self, clean_env, monkeypatch):
        monkeypatch.setenv("DISPLAY", ":0")
        assert is_x11() is True

    def test_isX11_trueWhenXdgSessionTypeIsX11(self, clean_env, monkeypatch):
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        assert is_x11() is True

    def test_isX11_falseWithCleanEnv(self, clean_env):
        assert is_x11() is False


class TestPlatformFamily:
    def test_isLinux_matchesSysPlatform(self):
        assert is_linux() == (sys.platform == "linux")

    def test_isWindows_matchesSysPlatform(self):
        assert is_windows() == sys.platform.startswith("win")

    def test_isMacos_matchesSysPlatform(self):
        assert is_macos() == (sys.platform == "darwin")
