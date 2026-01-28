import pytest
from PyQt6.QtCore import Qt, QPoint, QTimer

def test_app_ocr_capture_hotkey_shows_window_with_ocr_and_translation(main_window, qtbot):
    # Use QTimer to schedule clicks after the event loop in getImage() is running
    # getImage() is blocking (loop.exec())
    QTimer.singleShot(100, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.screenshotOverlay,
        Qt.MouseButton.LeftButton,
        pos=QPoint(100, 100)
    ))
    QTimer.singleShot(200, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.screenshotOverlay,
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

def test_app_ocr_only_hotkey_shows_window_with_only_ocr(main_window, qtbot):
    # see comment in: test_app_ocr_capture_hotkey_shows_window_with_ocr_and_translation
    QTimer.singleShot(100, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.screenshotOverlay,
        Qt.MouseButton.LeftButton,
        pos=QPoint(100, 100)
    ))
    QTimer.singleShot(200, lambda: qtbot.mouseClick(
        main_window.screenshot_controller.screenshotOverlay,
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

def test_app_cancel_selection_cancels_screenshot_selection(main_window, qtbot, mocker):
    spy_cancel = mocker.spy(main_window.screenshot_controller, 'cancel_selection')
    
    QTimer.singleShot(100, lambda:main_window.hotkey_manager.hotkey_triggered.emit('cancel_selection'))

    main_window.hotkey_manager.hotkey_triggered.emit('ocr_capture')

    spy_cancel.assert_called_once()
    assert main_window.screenshot_controller.screenshotOverlay.isVisible() == False