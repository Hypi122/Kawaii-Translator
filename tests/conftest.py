import os

# Use offscreen Qt platform for headless runs; never overrides an explicit
# platform choice and does nothing when a display is present.
if "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
