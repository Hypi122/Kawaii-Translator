#!/usr/bin/env python3
"""Live Wayland verification: REAL portal backend + ScreenshotController, per-overlay
actual compositor placement, DP-2 synth selection, crop. Manual tool (uncommitted)."""
import math, os, sys, traceback
# venv also has a stale installed App copy; force src/ to win (real code under test).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from App import screenshot as ss
from App.screenshot import ScreenshotController

def _evt(etype, pos):
    return QMouseEvent(etype, QPointF(pos), Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


app = QApplication(sys.argv)
print(f"platform: {app.platformName()}")
controller = ScreenshotController()

# Cache the REAL frozen frame the flow captures.
_captured = {}
_orig_capture = ss.capture_frozen_screen
ss.capture_frozen_screen = lambda: (_captured.setdefault("frozen", _orig_capture()) or _captured["frozen"])
_state = {"names": [], "target": None}

def _hard_timeout():
    print("HARD TIMEOUT")
    os._exit(1)

def inspect():
    try:
        overlays = controller.overlays
        print(f"overlay count: {len(overlays)}")
        for i, ov in enumerate(overlays):
            handle = ov.windowHandle()
            screen = handle.screen() if handle is not None else None
            off = ov.unionOffset
            print(f"overlay[{i}]: intended={ov._boundScreenGeometry} "
                  f"actual_screen={screen.name() if screen else None} "
                  f"actual_screen_geometry={screen.geometry() if screen else None} "
                  f"widget_geometry={ov.geometry()} slice={ov.imageSlice} "
                  f"unionOffset=({off.x()},{off.y()})")
            _state["names"].append(screen.name() if screen else None)
        if not overlays:
            print("FAIL: no overlays")
            os._exit(1)
        target = next((ov for ov in overlays
                       if (ov.windowHandle() and ov.windowHandle().screen()
                           and ov.windowHandle().screen().name() == "DP-2")),
                      overlays[0])
        _state["target"] = target
        print(f"target overlay actual screen: {target.windowHandle().screen().name()}")
        # Press-move-press drag (mirrors test_screenshot.py's helpers).
        start, end = QPoint(300, 300), QPoint(420, 380)
        QApplication.sendEvent(target, _evt(QEvent.Type.MouseButtonPress, start))
        QApplication.sendEvent(target, _evt(QEvent.Type.MouseMove, end))
        QApplication.sendEvent(target, _evt(QEvent.Type.MouseButtonPress, end))
    except Exception:
        traceback.print_exc()
        os._exit(1)

def run():
    try:
        image = controller.start_selection()
        frozen = _captured.get("frozen")
        if frozen is not None:
            print(f"frozen image.shape={frozen.image.shape} "
                  f"scale_x={frozen.scale_x} scale_y={frozen.scale_y}")
        print(f"RESULT image={'None' if image is None else f'shape={image.shape} dtype={image.dtype}'}")

        target = _state["target"]
        union_rect = expected = None
        if target is not None:
            off = target.unionOffset
            union_rect = QRect(QPoint(300, 300), QPoint(420, 380)).normalized().translated(off)
            print(f"implied union rect: x={union_rect.x()} y={union_rect.y()} "
                  f"w={union_rect.width()} h={union_rect.height()}")
            if frozen is not None:
                x1 = max(0, math.floor(union_rect.x() * frozen.scale_x))
                y1 = max(0, math.floor(union_rect.y() * frozen.scale_y))
                x2 = min(frozen.image.shape[1], math.ceil((union_rect.x() + union_rect.width()) * frozen.scale_x))
                y2 = min(frozen.image.shape[0], math.ceil((union_rect.y() + union_rect.height()) * frozen.scale_y))
                expected = (y2 - y1, x2 - x1, 3)
                print(f"expected crop shape: {expected} "
                      f"({'= (81, 121, 3) at scale 1.0' if frozen.scale_x == 1.0 and frozen.scale_y == 1.0 else ''})")

        ok = True
        if len(controller.overlays) == 2:
            print("PASS: two overlays reported")
        else:
            print(f"FAIL: expected 2 overlays, got {len(controller.overlays)}")
            ok = False
        names = sorted(str(n) for n in _state["names"])
        if names == ["DP-1", "DP-2"]:
            print("PASS: actual screens are DP-2 and DP-1")
        else:
            print(f"FAIL: actual screens = {names}")
            ok = False
        if image is not None:
            print("PASS: image not None")
            if expected is not None and tuple(image.shape) == tuple(expected):
                print("PASS: crop shape matches expected")
            else:
                print(f"FAIL: crop shape {image.shape} != expected {expected}")
                ok = False
        else:
            print("FAIL: image is None")
            ok = False
        app.exit(0 if ok else 1)
    except Exception:
        traceback.print_exc()
        os._exit(1)

QTimer.singleShot(1500, inspect)
QTimer.singleShot(9000, _hard_timeout)
QTimer.singleShot(0, run)
sys.exit(app.exec())