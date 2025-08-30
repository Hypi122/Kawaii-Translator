from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QMainWindow, QPushButton, QWidget, QVBoxLayout, QTabWidget, QMessageBox

from App.tabs.settings_tab import SettingsTab
from App.ocr_window import OcrWindow

from App.hotkey_manager import HotkeyManager
from App.screenshot import ScreenshotController

class MainWindow(QMainWindow):
    def __init__(self, OcrManager, TranslationManager):
        super().__init__()
        self.OcrManager = OcrManager
        self.TranslationManager = TranslationManager

        self.setWindowTitle("Kawaii Translator")
        self.setMinimumWidth(400)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Initialize hotkey manager
        self.hotkey_manager = HotkeyManager()
        self.hotkey_manager.hotkey_triggered.connect(self.handleHotkey)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.addTab(SettingsTab(self.OcrManager, self.hotkey_manager, self.TranslationManager), "Settings")

        self.screenshot_controller = ScreenshotController()
        self.ocrWindow = OcrWindow(self.TranslationManager)

    def handleHotkey(self, action):
        """Handle hotkey actions"""
        if action == 'ocr_capture':
            img = self.screenshot_controller.start_selection()

            if img is None:
                return
            ocrText = self.OcrManager.predict(img)            
            
            self.ocrWindow.show()
            self.ocrWindow.activateWindow()
            self.ocrWindow.raise_()
            self.ocrWindow.setOcr(ocrText, self.OcrManager.getCurrentEngine())
            self.ocrWindow.startRetranslate()

        elif action == 'cancel_selection':
            self.screenshot_controller.cancel_selection()
        else:
            print(f"Unknown hotkey action: {action}")