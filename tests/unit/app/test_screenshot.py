import logging

import numpy as np
import pytest
from PIL import Image

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtWidgets import QApplication

from App import capture as capture_mod
from App import screenshot as screenshot_mod
from App.capture import CapturedScreen
from App.overlay_geometry import screen_image_slice
from App.screenshot import (
    ScreenshotController,
    ScreenshotOverlay,
    _connect_screen_changed,
    _frozen_matches_screens,
    _overlay_actual_screen,
    _show_overlay_on_screen,
)


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


class _FakeScreen:
    def __init__(self, geometry):
        self._g = geometry

    def geometry(self):
        return self._g


class _FakeSignal:
    """Minimal Qt-signal stand-in: connect() records callbacks, emit() calls them."""
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class _FakeWindowHandle:
    """QWindow stand-in: just the screenChanged signal _connect_screen_changed uses."""
    def __init__(self):
        self.screenChanged = _FakeSignal()


# Two-screen layout used by the Linux per-screen overlay tests.
UNION = QRect(0, 0, 4480, 1440)
SCREEN_A = QRect(0, 0, 2560, 1440)
SCREEN_B = QRect(2560, 0, 1920, 1440)


def _patch_linux_two_screens(monkeypatch, frozen):
    """Wire screenshot_mod to the Linux freeze-first path with two fake screens."""
    monkeypatch.setattr(screenshot_mod, "is_linux", lambda: True)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", lambda: frozen)
    monkeypatch.setattr(screenshot_mod, "union_screen_geometry", lambda: UNION)
    monkeypatch.setattr(screenshot_mod, "_screens",
                        lambda: [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)])
    monkeypatch.setattr(screenshot_mod, "_show_overlay_on_screen", lambda overlay, screen: None)


def _select_on_second_screen(controller):
    """Assert the per-screen overlay setup and drive a selection on screen B
    (scheduled inside _wait_for_frozen_selection's event loop)."""
    assert len(controller.overlays) == 2
    assert controller.overlays[1].imageSlice == QRect(2560, 0, 1920, 1440)
    # One shared pixmap, not N deep copies of the full desktop.
    assert controller.overlays[0].frozenPixmap is controller.overlays[1].frozenPixmap
    # Local rect (10,10,100x100) on screen B -> union (2570,10,100x100);
    # second click lands one pixel short so the rect is exactly 100x100.
    _schedule_drag(controller.overlays[1], QPoint(10, 10), QPoint(109, 109))


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

    controller = ScreenshotController()
    assert controller.overlays == []


def test_linux_creates_one_overlay_per_screen_and_crops_second_screen_selection(qtbot, monkeypatch):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    _patch_linux_two_screens(monkeypatch, frozen)

    controller = ScreenshotController()
    QTimer.singleShot(100, lambda: _select_on_second_screen(controller))

    img = controller.start_selection()

    assert img is not None
    # Exact crop through the origin lift: local (10,10,100x100) on screen B -> union.
    np.testing.assert_array_equal(img, frozen.image[10:110, 2570:2670])
    assert all(ov.isVisible() is False for ov in controller.overlays)
    # Teardown freed every overlay's ref to the shared pixmap + frozen ndarray.
    assert all(ov.frozenPixmap is None for ov in controller.overlays)


def test_linux_no_screens_returns_none_without_hanging(qtbot, monkeypatch):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    _StubQMessageBox.calls = []
    monkeypatch.setattr(screenshot_mod, "is_linux", lambda: True)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", lambda: frozen)
    monkeypatch.setattr(screenshot_mod, "union_screen_geometry", lambda: UNION)
    monkeypatch.setattr(screenshot_mod, "_screens", lambda: [])
    monkeypatch.setattr(screenshot_mod, "_show_overlay_on_screen", lambda overlay, screen: None)
    monkeypatch.setattr(screenshot_mod, "QMessageBox", _StubQMessageBox)

    controller = ScreenshotController()
    # With zero screens the freeze verification in _freeze_verified can never
    # match (empty screen set fails _frozen_matches_screens), so after one
    # re-freeze it raises CaptureError and start_selection reports it via the
    # error dialog — nothing could ever quit the selection loop with zero
    # overlays, so it must never reach it. A watchdog turns a regression hang
    # into a red test instead of stalling the whole suite.
    watchdog = QTimer()
    watchdog.setInterval(5000)
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(
        lambda: pytest.fail("start_selection hung: no-screens guard regressed"))
    watchdog.start()
    img = controller.start_selection()
    watchdog.stop()

    assert img is None
    assert controller.overlays == []
    assert len(_StubQMessageBox.calls) == 1
    args, _ = _StubQMessageBox.calls[0]
    assert args[1] == "Screenshot capture failed"
    assert "Screen configuration changed" in args[2]


def test_linux_screens_vanish_after_freeze_returns_none(qtbot, monkeypatch):
    """Screens present during the freeze check but gone by placement time: the
    empty-overlays belt-and-braces guard must abort with None — no dialog, no
    hang."""
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    _StubQMessageBox.calls = []
    screen_sets = [[_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)], []]
    screens_calls = []

    def stateful_screens():
        screens_calls.append(1)
        return screen_sets.pop(0) if screen_sets else []

    _patch_linux_two_screens(monkeypatch, frozen)
    monkeypatch.setattr(screenshot_mod, "_screens", stateful_screens)
    monkeypatch.setattr(screenshot_mod, "QMessageBox", _StubQMessageBox)

    controller = ScreenshotController()
    watchdog = QTimer()
    watchdog.setInterval(5000)
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(
        lambda: pytest.fail("start_selection hung: screens-vanish guard regressed"))
    watchdog.start()
    img = controller.start_selection()
    watchdog.stop()

    assert img is None
    assert controller.overlays == []
    # First _screens() call fed the _freeze_verified match check (screens
    # present -> freeze accepted); the second fed overlay placement (empty).
    assert len(screens_calls) == 2
    # The empty-overlays guard is a silent abort — the CaptureError dialog is
    # only for freeze verification failures.
    assert _StubQMessageBox.calls == []


def test_linux_negative_origin_layout_crops_through_screen_origin(qtbot, monkeypatch):
    neg_union = QRect(-1920, 0, 4480, 1440)
    screen_left = QRect(-1920, 0, 1920, 1440)   # origin-in-union (0,0)
    screen_right = QRect(0, 0, 2560, 1440)      # origin-in-union (1920,0)
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    monkeypatch.setattr(screenshot_mod, "is_linux", lambda: True)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", lambda: frozen)
    monkeypatch.setattr(screenshot_mod, "union_screen_geometry", lambda: neg_union)
    monkeypatch.setattr(screenshot_mod, "_screens",
                        lambda: [_FakeScreen(screen_left), _FakeScreen(screen_right)])
    monkeypatch.setattr(screenshot_mod, "_show_overlay_on_screen", lambda overlay, screen: None)

    controller = ScreenshotController()
    # Screen at origin (0,0) -> origin-in-union (1920,0): a 100x100 selection
    # starting at its local (10,10) maps to image columns 1930..2029.
    QTimer.singleShot(100, lambda: _schedule_drag(
        controller.overlays[1], QPoint(10, 10), QPoint(109, 109)))

    img = controller.start_selection()

    assert len(controller.overlays) == 2
    assert img is not None
    np.testing.assert_array_equal(img, frozen.image[10:110, 1930:2030])


def test_linux_cancel_closes_all_overlays(qtbot, monkeypatch):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    _patch_linux_two_screens(monkeypatch, frozen)

    controller = ScreenshotController()
    QTimer.singleShot(100, controller.cancel_selection)

    img = controller.start_selection()

    assert img is None
    assert len(controller.overlays) == 2
    assert all(ov.isVisible() is False for ov in controller.overlays)


def test_per_screen_overlay_paints_its_image_slice(qtbot, monkeypatch):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    # __init__ reads union_screen_geometry() (for unionOffset), so the union must
    # be patched BEFORE constructing the overlay — same ordering the controller
    # path guarantees (both seams read the same fake union).
    monkeypatch.setattr(screenshot_mod, "union_screen_geometry", lambda: UNION)

    overlay = ScreenshotOverlay(SCREEN_B)
    qtbot.addWidget(overlay)
    slice_rect = screen_image_slice(SCREEN_B, UNION, QSize(4480, 1440), 1.0, 1.0)
    assert slice_rect == QRect(2560, 0, 1920, 1440)
    overlay.setFrozenScreen(frozen, image_slice=slice_rect)
    assert overlay.imageSlice == QRect(2560, 0, 1920, 1440)

    # Rendering technique: QWidget.render() into an explicit QImage, NOT grab().
    # grab() renders at the widget screen's devicePixelRatio (rescaled output on
    # HiDPI displays would break per-pixel sampling); a QImage target is always
    # DPR 1.0, so the widget paints 1:1 into device pixels on every platform.
    # Verified pixel-identical to grab() output at DPR 1.0 (offscreen + X11).
    canvas = QImage(overlay.size(), QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    overlay.render(canvas)

    assert canvas.size() == QSize(1920, 1440)
    # The dim layer is black at alpha 90/255 over the painted slice, so each
    # channel must be round(src * 165/255) (255-90 = 165); +-1 absorbs Qt's
    # internal rounding. Alpha 255 pins that the frozen slice was ACTUALLY
    # painted: skipping the drawPixmap would leave transparent black, not the
    # dimmed gradient.
    for x, y in [(0, 0), (100, 50), (1919, 1439)]:
        color = canvas.pixelColor(x, y)
        src = frozen.image[y, x + 2560]  # window x -> image x + screen origin
        expected = [round(int(v) * 165 / 255) for v in src]
        got = [color.blue(), color.green(), color.red()]  # src is BGR
        assert color.alpha() == 255
        assert all(abs(g - e) <= 1 for g, e in zip(got, expected)), \
            f"({x},{y}): got BGRA {got + [color.alpha()]}, expected ~{expected}"


def test_linux_single_screen_controller_flow(qtbot, monkeypatch):
    single = QRect(0, 0, 1920, 1080)
    frozen = CapturedScreen(_gradient_img(1080, 1920), scale_x=1.0, scale_y=1.0)

    monkeypatch.setattr(screenshot_mod, "is_linux", lambda: True)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", lambda: frozen)
    monkeypatch.setattr(screenshot_mod, "union_screen_geometry", lambda: single)
    monkeypatch.setattr(screenshot_mod, "_screens", lambda: [_FakeScreen(single)])
    monkeypatch.setattr(screenshot_mod, "_show_overlay_on_screen", lambda overlay, screen: None)

    controller = ScreenshotController()
    QTimer.singleShot(100, lambda: _schedule_drag(controller.overlays[0], QPoint(10, 10), QPoint(109, 109)))

    img = controller.start_selection()

    # N=1 regression guard: exactly one overlay, whose union offset is (0,0), so
    # the local drag (10,10)-(109,109) crops union rect (10,10,100x100) — the
    # exact frozen pixels, one pixel short on the second click per QRect corner
    # semantics (see _schedule_drag).
    assert img is not None
    assert img.shape == (100, 100, 3)
    np.testing.assert_array_equal(img, frozen.image[10:110, 10:110])
    assert len(controller.overlays) == 1


def test_linux_shows_each_overlay_fullscreen_on_its_screen(qtbot, monkeypatch):
    """_show_overlay_on_screen must force native window creation (winId), pin
    the QWindow handle to the intended screen, and only then go fullscreen —
    in that exact order (Wayland compositors only honor setScreen for fullscreen
    windows)."""
    for screen in (_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)):
        overlay = ScreenshotOverlay(screen.geometry(), UNION)
        qtbot.addWidget(overlay)

        events = []

        class _FakeHandle:
            def setScreen(self, s):
                events.append(("setScreen", s))

        handle = _FakeHandle()
        monkeypatch.setattr(overlay, "winId",
                            lambda: (events.append(("winId",)), 1)[1])
        monkeypatch.setattr(overlay, "windowHandle",
                            lambda: (events.append(("windowHandle",)), handle)[1])
        monkeypatch.setattr(overlay, "showFullScreen",
                            lambda: events.append(("showFullScreen",)))

        screenshot_mod._show_overlay_on_screen(overlay, screen)

        assert [e[0] for e in events] == \
            ["winId", "windowHandle", "setScreen", "showFullScreen"]
        # setScreen pins the overlay to ITS screen, between window creation and
        # the fullscreen show.
        assert events[2][1] is screen


def test_overlay_actual_screen_none_without_native_window(qtbot):
    """Before a native window exists there is no compositor truth: the actual
    screen is None and subscribing to screenChanged is a safe no-op."""
    overlay = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(overlay)

    # Never shown, winId() never forced -> no QWindow handle.
    assert overlay.windowHandle() is None
    assert screenshot_mod._overlay_actual_screen(overlay) is None

    called = []
    screenshot_mod._connect_screen_changed(overlay, lambda s: called.append(s))
    assert called == []


def test_rebind_recomputes_slice_and_offset_for_actual_screen(qtbot):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    pixmap = screenshot_mod._build_frozen_pixmap(frozen)
    overlay = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(overlay)
    controller = ScreenshotController()

    result = controller._rebind_overlay_to_screen(
        overlay, SCREEN_B, [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)],
        UNION, frozen, pixmap)

    assert result is True
    assert overlay.imageSlice == QRect(2560, 0, 1920, 1440)
    assert overlay.unionOffset == QPoint(2560, 0)
    assert overlay._boundScreenGeometry == SCREEN_B
    # The pre-built shared pixmap is reused, not rebuilt per overlay.
    assert overlay.frozenPixmap is pixmap
    # Aspect invariant: the slice keeps the target screen's aspect ratio up to
    # rounding (a +-1px rounding on each axis moves the ratio by <0.002).
    assert overlay.imageSlice.width() / overlay.imageSlice.height() == pytest.approx(
        SCREEN_B.width() / SCREEN_B.height(), abs=0.005)


def test_rebind_closes_overlay_for_foreign_screen(qtbot, monkeypatch, caplog):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    pixmap = screenshot_mod._build_frozen_pixmap(frozen)
    overlay = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(overlay)
    overlay.setFrozenScreen(frozen, image_slice=QRect(0, 0, 2560, 1440), pixmap=pixmap)
    slice_before = QRect(overlay.imageSlice)
    offset_before = QPoint(overlay.unionOffset)

    closed = []
    monkeypatch.setattr(overlay, "close", lambda: closed.append(True))

    controller = ScreenshotController()
    with caplog.at_level(logging.WARNING, logger="App.screenshot"):
        result = controller._rebind_overlay_to_screen(
            overlay, QRect(5000, 0, 800, 600),
            [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)],
            UNION, frozen, pixmap)

    assert result is False
    assert closed == [True]
    assert overlay._boundScreenGeometry is None
    # Never map clicks to coordinates of a screen that isn't in the frozen set.
    assert overlay.imageSlice == slice_before
    assert overlay.unionOffset == offset_before
    assert "not part of the frozen capture" in caplog.text


def test_linux_resync_when_compositor_moves_overlay(qtbot, monkeypatch):
    """KWin-style relocation: the compositor put overlay 0 (built for screen A)
    onto screen B's output. The post-show reconcile must rebind its slice and
    offset to where the window ACTUALLY sits, so clicks lift through screen B's
    origin in the union."""
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    _patch_linux_two_screens(monkeypatch, frozen)
    # Compositor truth: every overlay window reports screen B as its output.
    monkeypatch.setattr(screenshot_mod, "_overlay_actual_screen",
                        lambda overlay: _FakeScreen(SCREEN_B))

    controller = ScreenshotController()

    def assert_rebound_then_drag():
        overlay = controller.overlays[0]
        assert overlay.imageSlice == QRect(2560, 0, 1920, 1440)
        assert overlay.unionOffset == QPoint(2560, 0)
        assert overlay._boundScreenGeometry == SCREEN_B
        _schedule_drag(overlay, QPoint(100, 100), QPoint(200, 200))

    QTimer.singleShot(100, assert_rebound_then_drag)

    img = controller.start_selection()

    assert img is not None
    # Local (100,100)-(200,200) on the rebound overlay -> union rect at
    # (2660,100); QRect includes both corners so the crop is 101x101 exact
    # frozen pixels (see _schedule_drag for the corner semantics).
    assert img.shape == (101, 101, 3)
    np.testing.assert_array_equal(img, frozen.image[100:201, 2660:2761])


def test_screen_changed_rebinds_overlay(qtbot, monkeypatch):
    """A screenChanged emission after placement re-binds slice/offset to the
    new output through the closure wired up by _reconcile_overlay_screen."""
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    pixmap = screenshot_mod._build_frozen_pixmap(frozen)
    overlay = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(overlay)
    handle = _FakeWindowHandle()
    monkeypatch.setattr(overlay, "windowHandle", lambda: handle)
    # No compositor relocation at placement time: reconcile must only connect.
    monkeypatch.setattr(screenshot_mod, "_overlay_actual_screen", lambda ov: None)

    controller = ScreenshotController()
    controller.overlays = [overlay]
    screens = [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)]

    controller._reconcile_overlay_screen(
        overlay, _FakeScreen(SCREEN_A), screens, UNION, frozen, pixmap)

    assert len(handle.screenChanged.callbacks) == 1

    handle.screenChanged.emit(_FakeScreen(SCREEN_B))

    assert overlay.imageSlice == QRect(2560, 0, 1920, 1440)
    assert overlay.unionOffset == QPoint(2560, 0)
    assert overlay._boundScreenGeometry == SCREEN_B
    assert overlay.frozenPixmap is pixmap
    # try/finally must clear the reentrancy flag after the rebind.
    assert overlay._rebinding is False


def test_screen_changed_ignores_none_stale_noop_and_reentrancy(qtbot, monkeypatch):
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    pixmap = screenshot_mod._build_frozen_pixmap(frozen)
    screens = [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)]
    controller = ScreenshotController()
    rebinds = []
    monkeypatch.setattr(controller, "_rebind_overlay_to_screen",
                        lambda *args, **kwargs: rebinds.append(args))

    # (a) new_screen None (native window dying) -> immediate no-op.
    none_screen = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(none_screen)
    controller.overlays = [none_screen]
    controller._on_overlay_screen_changed(none_screen, None, screens, UNION, frozen, pixmap)
    assert rebinds == []
    assert none_screen._boundScreenGeometry == SCREEN_A

    # (b) stale connection: a foreign overlay not in self.overlays (a decoy is)
    #     must never be touched.
    decoy = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(decoy)
    foreign = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(foreign)
    controller.overlays = [decoy]
    controller._on_overlay_screen_changed(foreign, _FakeScreen(SCREEN_B), screens, UNION, frozen, pixmap)
    assert rebinds == []
    assert foreign.imageSlice is None
    assert foreign._boundScreenGeometry == SCREEN_A

    # (c) foreign-closed overlay (bound geometry already None) is never revived.
    closed = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(closed)
    closed._boundScreenGeometry = None
    controller.overlays = [closed]
    controller._on_overlay_screen_changed(closed, _FakeScreen(SCREEN_B), screens, UNION, frozen, pixmap)
    assert rebinds == []

    # (d) same geometry as bound -> no churn (guards rebind loops).
    same = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(same)
    controller.overlays = [same]
    controller._on_overlay_screen_changed(same, _FakeScreen(SCREEN_A), screens, UNION, frozen, pixmap)
    assert rebinds == []

    # (e) reentrant delivery while a rebind is in flight -> early return, and
    #     the guard must not clear the caller's flag.
    busy = ScreenshotOverlay(SCREEN_A, UNION)
    qtbot.addWidget(busy)
    controller.overlays = [busy]
    busy._rebinding = True
    controller._on_overlay_screen_changed(busy, _FakeScreen(SCREEN_B), screens, UNION, frozen, pixmap)
    assert rebinds == []
    assert busy.imageSlice is None
    assert busy._boundScreenGeometry == SCREEN_A
    assert busy._rebinding is True


def test_linux_all_overlays_closed_returns_none_without_hanging(qtbot, monkeypatch, caplog):
    """The compositor dropped every overlay onto an output outside the frozen
    set: all overlays get closed during placement, so nothing could ever quit
    the selection loop — the all-closed guard aborts with None instead."""
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    _patch_linux_two_screens(monkeypatch, frozen)
    foreign = QRect(5000, 0, 800, 600)
    monkeypatch.setattr(screenshot_mod, "_overlay_actual_screen",
                        lambda overlay: _FakeScreen(foreign))

    controller = ScreenshotController()
    with caplog.at_level(logging.WARNING, logger="App.screenshot"):
        watchdog = QTimer()
        watchdog.setInterval(5000)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(
            lambda: pytest.fail("start_selection hung: all-overlays-closed guard regressed"))
        watchdog.start()
        img = controller.start_selection()
        watchdog.stop()

    assert img is None
    assert len(controller.overlays) == 2
    assert all(ov._boundScreenGeometry is None for ov in controller.overlays)
    # Teardown dropped every ref to the shared pixmap + frozen ndarray.
    assert all(ov.frozenPixmap is None for ov in controller.overlays)
    assert caplog.text.count("not part of the frozen capture") == 2
    assert "All overlays were closed during placement" in caplog.text


def test_frozen_matches_screens_true_for_matching_union():
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    screens = [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)]
    assert _frozen_matches_screens(frozen, screens) is True
    # Non-unity scale: image pixels / scale must still round to the union size.
    half = CapturedScreen(_gradient_img(720, 2240), scale_x=0.5, scale_y=0.5)
    assert _frozen_matches_screens(half, screens) is True


def test_frozen_matches_screens_false_for_wrong_union():
    # 3000px-wide freeze vs the 4480px two-screen union (layout flapped
    # mid-capture): sizes disagree.
    frozen = CapturedScreen(_gradient_img(1440, 3000), scale_x=1.0, scale_y=1.0)
    screens = [_FakeScreen(SCREEN_A), _FakeScreen(SCREEN_B)]
    assert _frozen_matches_screens(frozen, screens) is False


def test_frozen_matches_screens_false_for_empty_screens():
    frozen = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    assert _frozen_matches_screens(frozen, []) is False


def test_linux_screen_flap_refreezes_once_and_proceeds(qtbot, monkeypatch, caplog):
    """First freeze caught a mid-hotplug layout, the re-freeze is consistent:
    exactly two captures, then the selection proceeds off the SECOND image."""
    stale = CapturedScreen(_gradient_img(1440, 3000), scale_x=1.0, scale_y=1.0)
    good = CapturedScreen(_gradient_img(1440, 4480), scale_x=1.0, scale_y=1.0)
    results = [stale, good]
    freeze_calls = []

    def popping_capture():
        freeze_calls.append(1)
        return results.pop(0)

    _patch_linux_two_screens(monkeypatch, good)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", popping_capture)

    controller = ScreenshotController()
    QTimer.singleShot(100, lambda: _select_on_second_screen(controller))

    with caplog.at_level(logging.WARNING, logger="App.screenshot"):
        img = controller.start_selection()

    # Selection completed against the re-frozen image: local (10,10,100x100)
    # on screen B -> union (2570,10) -> exact pixels of the SECOND capture.
    assert img is not None
    np.testing.assert_array_equal(img, good.image[10:110, 2570:2670])
    assert len(freeze_calls) == 2
    assert "re-freezing once" in caplog.text


def test_linux_persistent_screen_flap_shows_error_dialog(qtbot, monkeypatch):
    """Layout never settles: one re-freeze, still mismatched -> CaptureError
    dialog, None, and exactly two capture attempts (no retry loop)."""
    bad = CapturedScreen(_gradient_img(1440, 3000), scale_x=1.0, scale_y=1.0)
    freeze_calls = []

    def always_mismatched():
        freeze_calls.append(1)
        return bad

    _patch_linux_two_screens(monkeypatch, bad)
    monkeypatch.setattr(screenshot_mod, "capture_frozen_screen", always_mismatched)
    _StubQMessageBox.calls = []
    monkeypatch.setattr(screenshot_mod, "QMessageBox", _StubQMessageBox)

    controller = ScreenshotController()
    img = controller.start_selection()

    assert img is None
    assert controller.overlays == []
    assert len(_StubQMessageBox.calls) == 1
    args, _ = _StubQMessageBox.calls[0]
    assert args[0] is None
    assert args[1] == "Screenshot capture failed"
    assert "Screen configuration changed" in args[2]
    assert len(freeze_calls) == 2
