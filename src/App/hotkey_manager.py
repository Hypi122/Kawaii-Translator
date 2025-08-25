from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

from App.settings_service import settings_service

class HotkeyManager(QObject):
    # Signal emitted when a hotkey is triggered
    hotkey_triggered = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hotkeys = {}
        self.listeners = []
        self.load_settings()
        self.start_listening()

    def load_settings(self):
        """Load hotkey settings from the settings service"""
        hotkeys = settings_service.get("hotkeys")
        self.hotkeys.update(hotkeys)
    
    def update_hotkey(self, new_hotkey, action):
        self.hotkeys[action] = new_hotkey

    def get_hotkeys(self):
        return self.hotkeys.copy()
    
    def start_listening(self):
        # Stop any existing listeners
        self.stop_listening()
        
        # Create a new listener
        self.listener = keyboard.GlobalHotKeys({
            hotkey: lambda a=action: self.hotkey_triggered.emit(a)
            for action, hotkey in self.hotkeys.items()
        })
        
        # Start the listener in a separate thread
        self.listener.start()
        self.listeners.append(self.listener)
    
    def stop_listening(self):
        for listener in self.listeners:
            if listener.is_alive():
                listener.stop()
        self.listeners.clear()
    
    def restart_listening(self):
        # Restart hotkey listening (when hotkeys are updated)
        self.stop_listening()
        self.start_listening()
