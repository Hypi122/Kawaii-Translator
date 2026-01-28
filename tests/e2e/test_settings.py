import json
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QTabWidget, QInputDialog, QMessageBox

def get_settings_subtabs(settings_tab):
    tab_widgets = settings_tab.findChildren(QTabWidget)
    assert len(tab_widgets) > 0, "No QTabWidget found in settings tab"
    return tab_widgets[0]

def navigate_to_openai_tab(settings_tab):
    settings_tabs = get_settings_subtabs(settings_tab)
    settings_tabs.setCurrentIndex(1)
    return settings_tabs.currentWidget()

def get_save_button(settings_tab):
    buttons = settings_tab.findChildren(QPushButton)
    return next(btn for btn in buttons if btn.text() == "Save Settings")

class TestGeneralTab:
    def test_change_ocr_engine_switches_to_windows_ocr(self, main_window, qtbot):
        settings_tab = main_window.tabs.widget(0)
        ocr_engine_btn = settings_tab.ocrEngineBtn
        
        windows_ocr_index = ocr_engine_btn.findText("WindowsOCR")
        assert windows_ocr_index >= 0, "WindowsOCR engine not found"
        
        ocr_engine_btn.setCurrentIndex(windows_ocr_index)
        
        qtbot.waitUntil(lambda: ocr_engine_btn.isEnabled(), timeout=2000)
        
        assert main_window.OcrManager.getCurrentEngine() == "WindowsOCR"

    def test_change_translation_engine_adds_google_translate(self, main_window, qtbot):
        settings_tab = main_window.tabs.widget(0)
        translate_engine_btn = settings_tab.translateEngineBtn
        
        translate_engine_btn.showPopup()
        
        # google_translate_index = translate_engine_btn.findText("GoogleTranslate")
        # assert google_translate_index >= 0, "GoogleTranslate engine not found"
        
        # item_rect = translate_engine_btn.view().visualRect(
        #     translate_engine_btn.model.index(google_translate_index, 0)
        # )
        # click_pos = item_rect.center()
        
        # qtbot.mouseClick(
        #     translate_engine_btn.view().viewport(),
        #     Qt.MouseButton.LeftButton,
        #     pos=click_pos
        # )
        translate_engine_btn.setCheckedItems(["Dummy", "GoogleTranslate"])

        qtbot.waitUntil(lambda: translate_engine_btn.isEnabled(), timeout=2000)
        
        # Verify both engines are now selected
        checked_items = translate_engine_btn.checkedItemsText()
        assert "Dummy" in checked_items
        assert "GoogleTranslate" in checked_items
        
        # Verify the translation manager was updated
        active_engines = main_window.TranslationManager.getCurrentEngine()
        assert "Dummy" in active_engines
        assert "GoogleTranslate" in active_engines
    
    def test_save_settings_saves_changes_to_disk(self, main_window, qtbot, mock_settings, test_settings_path):
        settings_tab = main_window.tabs.widget(0)
        
        ocr_engine_btn = settings_tab.ocrEngineBtn
        windows_ocr_index = ocr_engine_btn.findText("WindowsOCR")
        ocr_engine_btn.setCurrentIndex(windows_ocr_index)
        qtbot.waitUntil(lambda: ocr_engine_btn.isEnabled(), timeout=2000)
        
        translate_engine_btn = settings_tab.translateEngineBtn
        translate_engine_btn.showPopup()
        translate_engine_btn.setCheckedItems(["Dummy", "GoogleTranslate"])
        
        translation_language_input = settings_tab.translationLanguageInput
        translation_language_input.setText("pl")
        
        save_button = get_save_button(settings_tab)
        qtbot.mouseClick(save_button, Qt.MouseButton.LeftButton)
        
        # Verify settings in memory
        assert mock_settings.get("ocr_engine") == "WindowsOCR"
        assert "Dummy" in mock_settings.get("translation_engine")
        assert "GoogleTranslate" in mock_settings.get("translation_engine")
        assert mock_settings.get("translation_target_lang") == "pl"
        
        # Verify settings saved in JSON file
        with open(test_settings_path, 'r', encoding='utf-8') as f:
            json_settings = json.load(f)
        
        assert json_settings["ocr_engine"] == "WindowsOCR"
        assert "Dummy" in json_settings["translation_engine"]
        assert "GoogleTranslate" in json_settings["translation_engine"]
        assert json_settings["translation_target_lang"] == "pl"

    
class TestOpenAiPresetTab:    
    def test_create_ocr_preset_adds_preset_to_combo_and_settings(self, main_window, qtbot, mock_settings, mocker):
        settings_tab = main_window.tabs.widget(0)
        navigate_to_openai_tab(settings_tab)
        
        mocker.patch.object(QInputDialog, 'getText', return_value=("test_ocr_preset", True))
        
        initial_count = settings_tab.ocr_preset_btn.count()
        
        qtbot.mouseClick(settings_tab.ocr_preset_create_btn, Qt.MouseButton.LeftButton)
        
        assert settings_tab.ocr_preset_btn.count() == initial_count + 1
        assert settings_tab.ocr_preset_btn.currentText() == "test_ocr_preset"
        
        presets = mock_settings.get("ocr_presets")
        assert "test_ocr_preset" in presets
        
        ocr_engines = main_window.OcrManager.available_engines()
        assert "OpenAI Api test_ocr_preset" in ocr_engines

    def test_create_ocr_preset_cancelled_does_not_add_preset(self, main_window, qtbot, mock_settings, mocker):
        settings_tab = main_window.tabs.widget(0)
        navigate_to_openai_tab(settings_tab)
        
        mocker.patch.object(QInputDialog, 'getText', return_value=("test_ocr_preset", False))
        
        initial_count = settings_tab.ocr_preset_btn.count()
        qtbot.mouseClick(settings_tab.ocr_preset_create_btn, Qt.MouseButton.LeftButton)
        
        assert settings_tab.ocr_preset_btn.count() == initial_count
        
        presets = mock_settings.get("ocr_presets")
        assert "test_ocr_preset" not in presets
        
        ocr_engines = main_window.OcrManager.available_engines()
        assert "OpenAI Api test_ocr_preset" not in ocr_engines
    
    def test_delete_ocr_preset_removes_preset_from_combo_and_settings(self, main_window, qtbot, mock_settings, mocker):
        settings_tab = main_window.tabs.widget(0)
        navigate_to_openai_tab(settings_tab)
        
        # Create two presets (need at least 2 to delete one)
        mocker.patch.object(QInputDialog, 'getText', return_value=("to_delete_ocr", True))
        qtbot.mouseClick(settings_tab.ocr_preset_create_btn, Qt.MouseButton.LeftButton)
        
        mocker.patch.object(QInputDialog, 'getText', return_value=("keep_ocr", True))
        qtbot.mouseClick(settings_tab.ocr_preset_create_btn, Qt.MouseButton.LeftButton)
        
        # Select the preset to delete
        settings_tab.ocr_preset_btn.setCurrentIndex(
            settings_tab.ocr_preset_btn.findText("to_delete_ocr")
        )
        
        mocker.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes)
        
        qtbot.mouseClick(settings_tab.ocr_preset_delete_btn, Qt.MouseButton.LeftButton)
        
        assert settings_tab.ocr_preset_btn.findText("to_delete_ocr") == -1
        assert settings_tab.ocr_preset_btn.findText("keep_ocr") != -1

        presets = mock_settings.get("ocr_presets")
        assert "to_delete_ocr" not in presets
        assert "keep_ocr" in presets
        
        ocr_engines = main_window.OcrManager.available_engines()
        assert "OpenAI Api to_delete_ocr" not in ocr_engines
        assert "OpenAI Api keep_ocr" in ocr_engines


    def test_create_translate_preset_adds_preset_to_combo_and_settings(self, main_window, qtbot, mock_settings, mocker):
        settings_tab = main_window.tabs.widget(0)
        navigate_to_openai_tab(settings_tab)
        
        mocker.patch.object(QInputDialog, 'getText', return_value=("test_translate_preset", True))
        
        initial_count = settings_tab.translation_preset_btn.count()
        
        qtbot.mouseClick(settings_tab.translation_preset_create_btn, Qt.MouseButton.LeftButton)
        
        assert settings_tab.translation_preset_btn.count() == initial_count + 1
        assert settings_tab.translation_preset_btn.currentText() == "test_translate_preset"
        
        presets = mock_settings.get("translation_presets")
        assert "test_translate_preset" in presets
        
        translation_engines = main_window.TranslationManager.available_engines()
        assert "OpenAI Api test_translate_preset" in translation_engines

    def test_create_translate_preset_cancelled_does_not_add_preset(self, main_window, qtbot, mock_settings, mocker):
        settings_tab = main_window.tabs.widget(0)
        navigate_to_openai_tab(settings_tab)
        
        mocker.patch.object(QInputDialog, 'getText', return_value=("test_translate_preset", False))
        
        initial_count = settings_tab.translation_preset_btn.count()
        qtbot.mouseClick(settings_tab.translation_preset_create_btn, Qt.MouseButton.LeftButton)
        
        assert settings_tab.translation_preset_btn.count() == initial_count
        
        presets = mock_settings.get("translation_presets")
        assert "test_translate_preset" not in presets
        
        translation_engines = main_window.TranslationManager.available_engines()
        assert "OpenAI Api test_translate_preset" not in translation_engines
    
    def test_delete_translate_preset_removes_preset_from_combo_and_settings(self, main_window, qtbot, mock_settings, mocker):
        settings_tab = main_window.tabs.widget(0)
        navigate_to_openai_tab(settings_tab)
        
        # Create two presets (need at least 2 to delete one)
        mocker.patch.object(QInputDialog, 'getText', return_value=("to_delete_translate", True))
        qtbot.mouseClick(settings_tab.translation_preset_create_btn, Qt.MouseButton.LeftButton)
        
        mocker.patch.object(QInputDialog, 'getText', return_value=("keep_translate", True))
        qtbot.mouseClick(settings_tab.translation_preset_create_btn, Qt.MouseButton.LeftButton)
        
        # Select the preset to delete
        settings_tab.translation_preset_btn.setCurrentIndex(
            settings_tab.translation_preset_btn.findText("to_delete_translate")
        )
        
        mocker.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes)
        
        qtbot.mouseClick(settings_tab.translation_preset_delete_btn, Qt.MouseButton.LeftButton)
        
        assert settings_tab.translation_preset_btn.findText("to_delete_translate") == -1
        assert settings_tab.translation_preset_btn.findText("keep_translate") != -1

        presets = mock_settings.get("translation_presets")
        assert "to_delete_translate" not in presets
        assert "keep_translate" in presets
        
        translation_engines = main_window.TranslationManager.available_engines()
        assert "OpenAI Api to_delete_translate" not in translation_engines
        assert "OpenAI Api keep_translate" in translation_engines