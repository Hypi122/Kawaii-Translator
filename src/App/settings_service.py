import json
import os

class SettingsService:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.default_settings = {
            "ocr_engine": "Dummy",
            "translation_engine": "Dummy",
            "hotkeys": {
                "ocr_capture": "<alt>+q",
                "cancel_selection": "<esc>"
            },
            "source_lang": "ja",
            "translation_source_lang": "auto",
            "translation_target_lang": "en",
            "translation_presets": {
                # "default": {
                #     "url": "",
                #     "model": "",
                #     "key": ""
                # }
            },
            "ocr_presets": {
                # "default": {
                #     "url": "",
                #     "model": "",
                #     "key": ""
                # }
            }
        }
        self.settings = self.load_settings()
    
    def load_settings(self):
        """Load settings from config file or create with defaults if they dont exist."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    loaded_settings = json.load(f)
                
                # Merge with defaults to ensure all keys exist
                settings = self.default_settings.copy()
                self._merge_dict(settings, loaded_settings)
                self.save_settings(settings)
                return settings
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading settings: {e}. Using defaults.")
                return self.default_settings.copy()
        else:
            # Create config file with default settings
            self.save_settings(self.default_settings)
            return self.default_settings.copy()

    def _merge_dict(self, base, update):
        """Recursively merge update dict into base dict."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_dict(base[key], value)
            else:
                base[key] = value

    def save_settings(self, settings = None):
        """Save settings to config file."""
        if settings is None:
            settings = self.settings

        try:
            with open(self.config_path, 'w') as f:
                json.dump(settings, f, indent=4)
        except IOError as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key):
        """Get a setting value by key, returning default from default_settings if not found."""
        keys = key.split('.')
        value = self.settings
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            default_value = self.default_settings
            try:
                for k in keys:
                    default_value = default_value[k]
                return default_value
            except (KeyError, TypeError):
                return None
    
    def set(self, key, value):
        """Set a setting value by key."""
        keys = key.split('.')
        settings = self.settings
        
        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in settings or not isinstance(settings[k], dict):
                settings[k] = {}
            settings = settings[k]
        
        # Set the value
        settings[keys[-1]] = value
        
        # Save changes
        self.save_settings()

# Global instance of settings service
settings_service = SettingsService()