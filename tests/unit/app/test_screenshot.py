import numpy as np
import pytest
from PIL import Image

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from App import capture as capture_mod
from App import screenshot as screenshot_mod
from App.capture import CapturedScreen
from App.screenshot import ScreenshotController, ScreenshotOverlay


def _gradient_img(h, w):
    """Per-pixel pattern image (BGR): B=x, G=y, R=77. uint8 wraps, which is fine."""
    yy, xx = np.indices((h, w), dtype=np.uint8)
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = xx
    img[..., 1] = yy
    img[..., 2] = 77
    return img


def _schedule_drag(overlay, start, end):
    """Press-drag-release selection, scheduled inside getImage()'s event loop.

    QTest.mouseMove does not deliver mouseMoveEvent on the Wayland platform
    (verified: only press/release reach the widget), which would leave
    currentPoint stuck at the start and produce a 1x1 rect. Synthesizing the
    move directly is deterministic on every platform.

    NOTE: QRect(start, end) includes BOTH corners (width = end.x()-start.x()+1),
    so to select a region of exactly (end.x()-start.x()) x (end.y()-start.y())
    pixels the second click must land one pixel short — the callers do that so
    the expected crop below stays in the "round" coordinates of the spec.
    """
    QTimer.singleShot(100, lambda: QApplication.sendEvent(overlay, _click_event(start)))
    QTimer.singleShot(200, lambda: QApplication.sendEvent(overlay, _move_event(end)))
    QTimer.singleShot(300, lambda: QApplication.sendEvent(overlay, _click_event(end)))


def _click_event(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _move_event(pos):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(pos),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


class _StubQMessageBox:
    calls = []

    @classmethod
    def critical(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))


def test_frozen_selection_crops_expected_region(qtbot):
    img = _gradient_img(1000, 2000)
    frozen = CapturedScreen(img, scale_x=1.0, scale_y=1.0)
    overlay = ScreenshotOverlay()
    qtbot.addWidget(overlay)
    overlay.setFrozenScreen(frozen)

    # Deliberately NOT shown: an unshown widget has no platform window, so the
    # live session can never deliver real mouse events to it. The widget's event
    # handlers still run when events are pushed via QApplication.sendEvent inside
    # getImage()'s QEventLoop (below), which keeps the real handlers under test
    # while making the selection immune to real-cursor interference.

    # End point one pixel short: QRect(start, end) includes both corners, so
    # (20,30)-(119,89) selects exactly the 100x60 box (20,30)-(120,90).
    _schedule_drag(overlay, QPoint(20, 30), QPoint(119, 89))

    image = overlay.getImage()

    assert image is not None
    assert image.shape == (60, 100, 3)
    np.testing.assert_array_equal(image, img[30:90, 20:120])


def test_frozen_crop_with_nonunity_scale(qtbot):
    img = _gradient_img(100, 200)
    frozen = CapturedScreen(img, scale_x=2.0, scale_y=0.5)
    overlay = ScreenshotOverlay()
    qtbot.addWidget(overlay)
    overlay.setFrozenScreen(frozen)

    # Deliberately NOT shown: an unshown widget has no platform window, so the
    # live session can never deliver real mouse events to it. The widget's event
    # handlers still run when events are pushed via QApplication.sendEvent inside
    # getImage()'s QEventLoop (below), which keeps the real handlers under test
    # while making the selection immune to real-cursor interference.

    # (10,20)-(29,59) selects a 20x40 box; with scales (2.0, 0.5) the mapping is
    # x1=floor(10*2)=20, y1=floor(20*0.5)=10, x2=ceil(30*2)=60, y2=ceil(60*0.5)=30.
    _schedule_drag(overlay, QPoint(10, 20), QPoint(29, 59))

    image = overlay.getImage()

    assert image is not None
    assert image.shape == (20, 40, 3)
    # Contract: x1=floor(10*2)=20, y1=floor(20*0.5)=10, x2=ceil(30*2)=60, y2=ceil(60*0.5)=30
    np.testing.assert_array_equal(image, img[10:30, 20:60])


def test_capture_error_shows_critical_and_returns_none(qtbot, monkeypatch):
    _StubQMessageBox.calls = []

    def boom():
        raise capture_mod.CaptureError("portal denied")

    monkeypatch.setattr(screenshot_mod, "is_linux", lambda: True)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", boom)
    monkeypatch.setattr(screenshot_mod, "QMessageBox", _StubQMessageBox)

    controller = ScreenshotController()
    img = controller.start_selection()

    assert img is None
    assert len(_StubQMessageBox.calls) == 1
    args, _ = _StubQMessageBox.calls[0]
    assert args[0] is None
    assert args[1] == "Screenshot capture failed"
    assert "portal denied" in args[2]
    assert controller.screenshotOverlay.isVisible() is False


def test_windows_live_path_untouched(qtbot, monkeypatch):
    calls = []

    class FakeImageGrab:
        def grab(self, **kwargs):
            calls.append(kwargs)
            return Image.new("RGB", (640, 480), (1, 2, 3))

    monkeypatch.setattr(screenshot_mod, "is_linux", lambda: False)
    monkeypatch.setattr(screenshot_mod, "ImageGrab", FakeImageGrab())

    overlay = ScreenshotOverlay()
    qtbot.addWidget(overlay)

    # Deliberately NOT shown: an unshown widget has no platform window, so the
    # live session can never deliver real mouse events to it. The widget's event
    # handlers still run when events are pushed via QApplication.sendEvent inside
    # getImage()'s QEventLoop (below), which keeps the real handlers under test
    # while making the selection immune to real-cursor interference.

    # (20,30)-(119,89) -> rect (20,30,100x60) -> bbox (20, 30, 120, 90).
    _schedule_drag(overlay, QPoint(20, 30), QPoint(119, 89))

    image = overlay.getImage()

    assert image is not None
    assert image.shape == (480, 640, 3)
    # PIL ImageGrab returns RGB; the legacy path converts to BGR via cvtColor.
    np.testing.assert_array_equal(image[0, 0], np.array([3, 2, 1], dtype=np.uint8))
    assert calls[0]["bbox"] == (20, 30, 120, 90)
    assert calls[0]["all_screens"] is True
