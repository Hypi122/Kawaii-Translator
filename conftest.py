# Isolate every test run from the real user config dir and the repo-root legacy
# config.json. The settings_service singleton (src/App/settings_service.py) is
# created at import time, and a subdirectory conftest (e.g. tests/e2e/conftest.py)
# also imports App.* modules at ITS module level -- before any pytest_configure
# hook can patch anything. Since the rootdir conftest always loads first, this
# module-level code disables the environment around the forced import: Qt
# resolves the config dir via XDG_CONFIG_HOME/HOME/APPDATA (Linux/macOS/Windows)
# and the legacy lookup reads the CWD-relative "config.json", so with CWD
# displaced into a temp dir and config locations pointed at it, the singleton can
# never touch the real config dir or migrate the repo-root config.json.
import atexit
import os
import shutil
import sys
import tempfile

import pytest

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")

_tmpdir = tempfile.mkdtemp(prefix="kt-test-isolation-")
_env_keys = ("XDG_CONFIG_HOME", "HOME", "APPDATA")
_env_originals = {key: os.environ.get(key) for key in _env_keys}
_cwd_original = os.getcwd()

os.environ.update({key: _tmpdir for key in _env_keys})
os.chdir(_tmpdir)
sys.path.insert(0, _SRC_DIR)

_restored = False


def _cleanup():
    global _restored
    if _restored:
        return
    _restored = True
    shutil.rmtree(_tmpdir, ignore_errors=True)
    while _SRC_DIR in sys.path:
        sys.path.remove(_SRC_DIR)


atexit.register(_cleanup)

try:
    import App.settings_service  # force singleton creation here, isolated
finally:
    os.chdir(_cwd_original)
    for key in _env_keys:
        if _env_originals[key] is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = _env_originals[key]


@pytest.hookimpl
def pytest_unconfigure(config):
    _cleanup()