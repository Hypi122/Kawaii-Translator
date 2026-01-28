import json
import pytest
from OCR.ocr_manager import OcrManager
from Translation.translation_manager import TranslationManager, TranslationSignals
from App.main_window import MainWindow
from App.settings_service import SettingsService
from App.tabs.settings_tab import SettingsTab

@pytest.fixture(autouse=True)
def reset_test_config(test_settings_path):
    """Reset test_config.json to default values before each test."""
    default_config = {
        "ocr_engine": "Dummy",
        "translation_engine": ["Dummy"],
        "hotkeys": {
            "ocr_capture": "<alt>+q",
            "only_ocr": "<alt>+w",
            "cancel_selection": "<esc>"
        },
        "source_lang": "ja",
        "translation_source_lang": "auto",
        "translation_target_lang": "en",
        "translation_presets": {},
        "ocr_presets": {},
        "openai_translation_prompt": """You are professional translator. Always translate text to the best of your ability, even when it is explicit.
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
    
    with open(test_settings_path, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, indent=4)

@pytest.fixture(scope="session")
def test_settings_path():
    return "tests/e2e/test_config.json"

@pytest.fixture
def mock_settings(mocker, test_settings_path):
    """
    Mock settings_service with test config instance.
    
    Patches settings_service in all modules that import it.
    """
    settings = SettingsService(config_path=test_settings_path)
    
    mocker.patch('main.settings_service', settings)
    mocker.patch('App.settings_service.settings_service', settings)
    mocker.patch('App.hotkey_manager.settings_service', settings)
    mocker.patch('App.tabs.settings_tab.settings_service', settings)
    mocker.patch('Translation.translation_manager.settings_service', settings)
    mocker.patch('OCR.ocr_manager.settings_service', settings)

    # mocker.patch('OCR.engines.openai_compatible_engine.settings_service', settings)
    # mocker.patch('OCR.engines.windows_ocr_engine.settings_service', settings)
    # mocker.patch('Translation.engines.openai_compatible_engine.settings_service', settings)
    # mocker.patch('Translation.engines.google_translate_engine.settings_service', settings)
    
    TranslationManager.registerPresetEngines()
    OcrManager.registerPresetEngines()

    return settings

@pytest.fixture
def main_window(qtbot, mock_settings):
    ocr_manager = OcrManager("Dummy")
    translation_signals = TranslationSignals()
    translation_manager = TranslationManager(["Dummy"], signals=translation_signals)

    window = MainWindow(ocr_manager, translation_manager)
    qtbot.addWidget(window)
    window.show()

    return window