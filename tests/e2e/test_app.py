import numpy as np
import pytest
from PyQt6.QtCore import Qt, QPoint, QTimer

from App import capture as capture_mod
from Util.platform import is_linux

@pytest.mark.skipif(not is_linux(), reason="per-screen overlays are the Linux freeze-first path")
def test_app_ocr_capture_hotkey_shows_window_with_ocr_and_translation(main_window, qtbot, monkeypatch):
    # Inject a fake capture backend — never touch the real portal/D-Bus from tests.
    class _FakeBackend:
        def capture(self):
            # Size the fake image to the REAL union so selections stay in-bounds
            # regardless of which monitor is screens[0].
            union = capture_mod.union_screen_geometry()
            h, w = union.height(), union.width()
            return capture_mod.CapturedScreen(
                image=np.full((h, w, 3), 200, dtype=np.uint8), scale_x=1.0, scale_y=1.0)
    monkeypatch.setattr(capture_mod, "get_capture_backend", lambda: _FakeBackend())

    # Use QTimer to schedule clicks after the controller's selection wait loop
    # (_wait_for_frozen_selection on Linux) starts blocking.
    # Linux per-screen path: click the first per-screen overlay; the lambda
    # resolves the attribute at fire time, after start_selection() built it.
    QTimer.singleShot(100, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.overlays[0],
        Qt.MouseButton.LeftButton,
        pos=QPoint(100, 100)
    ))
    QTimer.singleShot(200, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.overlays[0],
        Qt.MouseButton.LeftButton,
        pos=QPoint(200, 200)
    ))
    
    main_window.hotkey_manager.hotkey_triggered.emit('ocr_capture')

    qtbot.waitUntil(lambda: main_window.ocrWindow.isVisible(), timeout=2000)
    qtbot.waitUntil(lambda: main_window.ocrWindow.ocrTextbox.toPlainText() != "", timeout=1000)

    assert main_window.ocrWindow.ocrTextboxLabel.text() == "OCR (Dummy)"
    assert main_window.ocrWindow.ocrTextbox.toPlainText() == "Dummy OCR'd Text"
    
    qtbot.waitUntil(lambda: main_window.ocrWindow.translationWidgets.get("Dummy") and
                    main_window.ocrWindow.translationWidgets["Dummy"].toPlainText() != "", timeout=2000)

    assert "Dummy" in main_window.ocrWindow.translationWidgets
    assert main_window.ocrWindow.translationWidgets["Dummy"].toPlainText() == "This is dummy translation"

@pytest.mark.skipif(not is_linux(), reason="per-screen overlays are the Linux freeze-first path")
def test_app_ocr_only_hotkey_shows_window_with_only_ocr(main_window, qtbot, monkeypatch):
    # Inject a fake capture backend — never touch the real portal/D-Bus from tests.
    class _FakeBackend:
        def capture(self):
            # Size the fake image to the REAL union so selections stay in-bounds
            # regardless of which monitor is screens[0].
            union = capture_mod.union_screen_geometry()
            h, w = union.height(), union.width()
            return capture_mod.CapturedScreen(
                image=np.full((h, w, 3), 200, dtype=np.uint8), scale_x=1.0, scale_y=1.0)
    monkeypatch.setattr(capture_mod, "get_capture_backend", lambda: _FakeBackend())

    # see comment in: test_app_ocr_capture_hotkey_shows_window_with_ocr_and_translation
    QTimer.singleShot(100, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.overlays[0],
        Qt.MouseButton.LeftButton,
        pos=QPoint(100, 100)
    ))
    QTimer.singleShot(200, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.overlays[0],
        Qt.MouseButton.LeftButton,
        pos=QPoint(200, 200)
    ))
    
    main_window.hotkey_manager.hotkey_triggered.emit('only_ocr')

    qtbot.waitUntil(lambda: main_window.ocrWindow.isVisible(), timeout=2000)
    qtbot.waitUntil(lambda: main_window.ocrWindow.ocrTextbox.toPlainText() != "", timeout=1000)

    assert main_window.ocrWindow.ocrTextboxLabel.text() == "OCR (Dummy)"
    assert main_window.ocrWindow.ocrTextbox.toPlainText() == "Dummy OCR'd Text"
    
    assert "Dummy" not in main_window.ocrWindow.translationWidgets
    assert len(main_window.ocrWindow.translationWidgets) == 0

def test_app_cancel_selection_cancels_screenshot_selection(main_window, qtbot, mocker, monkeypatch):
    # Inject a fake capture backend — never touch the real portal/D-Bus from tests.
    class _FakeBackend:
        def capture(self):
            # Size the fake image to the REAL union so selections stay in-bounds
            # regardless of which monitor is screens[0].
            union = capture_mod.union_screen_geometry()
            h, w = union.height(), union.width()
            return capture_mod.CapturedScreen(
                image=np.full((h, w, 3), 200, dtype=np.uint8), scale_x=1.0, scale_y=1.0)
    monkeypatch.setattr(capture_mod, "get_capture_backend", lambda: _FakeBackend())

    spy_cancel = mocker.spy(main_window.screenshot_controller, 'cancel_selection')
    
    QTimer.singleShot(100, lambda:main_window.hotkey_manager.hotkey_triggered.emit('cancel_selection'))

    main_window.hotkey_manager.hotkey_triggered.emit('ocr_capture')

    spy_cancel.assert_called_once()
    # Linux per-screen path: every per-screen overlay must be hidden after cancel.
    overlays = main_window.screenshot_controller.overlays
    assert len(overlays) >= 1
    assert all(ov.isVisible() is False for ov in overlays)