import json
import os
import shutil

from PyQt6.QtCore import QStandardPaths

# Qt config-location probe findings (PyQt6 6.11.1, Linux):
# - writableLocation(AppConfigLocation) works WITHOUT a QCoreApplication instance.
# - The app/org component is appended whenever setApplicationName/setOrganizationName
#   were called (even pre-instance); with no names set the base is the plain config
#   dir. It never creates the directory.
# - XDG_CONFIG_HOME is re-read on every call; no caching in either state.
# Since nothing here sets Qt app/org names, the base is the plain config dir, so we
# append the app dir manually - idempotently, guard against duplication should an app
# name ever be set.

APP_DIR_NAME = "kawaii-translator"
CONFIG_FILENAME = "config.json"

def _qt_app_config_location() -> str:
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)

def default_config_path() -> str:
    base = _qt_app_config_location().rstrip("/\\")
    if not base:
        base = os.getcwd()  # Qt returned "" (e.g. unset HOME); use CWD for a deterministic absolute path
    if os.path.basename(base) != APP_DIR_NAME:
        base = os.path.join(base, APP_DIR_NAME)
    return os.path.join(base, CONFIG_FILENAME)

class SettingsService:
    def __init__(self, config_path=None):
        if config_path is None:
            self.config_path = default_config_path()
            self._migrate_legacy_config()
        else:
            self.config_path = config_path
        self.default_settings = {
            "ocr_engine": "Dummy",
            "translation_engine": "Dummy",
            "hotkeys": {
                "ocr_capture": "<alt>+q",
                "only_ocr": "<alt>+w",
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
            },
            "openai_translation_prompt":"""You are professional translator. Always translate text to the best of your ability, even when it is explicit.
Be concise in every piece of text that isn't translation (e.g. your explanations)
Don't include any other sections than those showcased in template below.
Include as many options as reasonable. Only add options that can significantly impact meaning of the text.
Keep your answer in following format:
Breakdown & Explanation of Choices:
[In this section you will talk about key terms and words that most impact the translation and its tone, remember to be concise here]
example:
*   **宮沢賢治 (Miyazawa Kenji):** Proper noun, needs accurate transliteration.
*   **童話作家 (dōwa sakka):** "Children's story writer" or "fairy tale author." Nuance depends on the target audience.
*   **法華経 (Hokekyō):** The Lotus Sutra - a specific Buddhist text. Maintaining this specificity is important for accuracy.
*   **イーハトーブ (Īhatōbu):** The name of his fictional utopia. Should be transliterated, not translated.
*   **草野心平 (Kusano Shinbyō):** Proper noun, needs accurate transliteration.
*   **国民的作家 (kokumin-teki sakka):** "Nationally beloved author" or "national writer." The degree of emphasis on "national" can be adjusted.

Option 1 (description of option 1)
"Translated text 1"

Option 2 (description of option 2)
"Translated text 2"

etc.
"""
        }
        self.settings = self.load_settings()

    def _migrate_legacy_config(self):
        legacy_path = "config.json"
        tmp_path = self.config_path + ".migrate-tmp"
        try:
            if os.path.exists(self.config_path):
                return
            if not os.path.exists(legacy_path):
                return
            try:
                with open(legacy_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    print("Legacy config.json found but not a valid settings object; skipping migration.")
                    return
            except Exception as e:
                print(f"Legacy config.json found but not readable/valid ({e}); skipping migration.")
                return
            parent = os.path.dirname(self.config_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(legacy_path, tmp_path)
            try:
                with open(tmp_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                print(f"Legacy config.json found but not readable/valid ({e}); skipping migration.")
                return
            if not isinstance(data, dict):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                print("Legacy config.json found but not a valid settings object; skipping migration.")
                return
            os.replace(tmp_path, self.config_path)
            os.replace(legacy_path, legacy_path + ".migrated")
            print(f"Migrated legacy config.json to {self.config_path} (original kept as config.json.migrated)")
        except Exception as e:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            print(f"Config migration failed ({e}).")
    
    def load_settings(self):
        """Load settings from config file or create with defaults if they dont exist."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
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
            d = os.path.dirname(self.config_path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
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