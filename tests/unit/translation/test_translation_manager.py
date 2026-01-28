import pytest

from Translation.translation_manager import TranslationManager, TranslationSignals

@pytest.fixture
def mock_settings(mocker):
    mockSettings = mocker.patch('Translation.translation_manager.settings_service')
    mockSettings.get.return_value = {}
    
    # HACK to unregister preset engines (register with empty settings) 
    # has to be done due to engine registering at import, aka before settings_service patch 
    TranslationManager.registerPresetEngines()

    return mockSettings

class TestTranslationManagerInit:
    @pytest.mark.parametrize("engines,expected", [
        (["Dummy"], ["Dummy"]),
        (["NonExistentEngine"], []),
        (["NonExistentEngine", "Dummy"], ["Dummy"]),
    ])
    def test_init_loads_engines_from_configuration(self, mock_settings, engines, expected):
        manager = TranslationManager(engines)
        assert manager.getCurrentEngine() == expected


class TestTranslationManagerUpdateActiveEngines:
    def test_update_active_engines_clears_old_engines_and_adds_new(self, mock_settings, mocker):
        manager = TranslationManager(["Dummy"])

        # Add a mock engine
        mock_engine = mocker.MagicMock()
        mock_engine.return_value.isWorking = True
        manager._available_engines["MockEngine"] = mock_engine

        manager.update_active_engines(["MockEngine"])
        assert "Dummy" not in manager.getCurrentEngine()
        assert "MockEngine" in manager.getCurrentEngine()

        del manager._available_engines["MockEngine"]
    
    def test_update_active_engines_handles_failed_engines_by_skipping(self, mock_settings, mocker):
        mock_engine = mocker.MagicMock()
        mock_engine.return_value.isWorking = False
        manager = TranslationManager([])
        manager._available_engines["MockEngine"] = mock_engine
        
        manager.update_active_engines(["MockEngine"])

        assert "MockEngine" not in manager.getCurrentEngine()

        del manager._available_engines["MockEngine"]

class TestTranslationManagerTranslate:
    def test_translate_starts_thread_for_every_loaded_engine(self, mocker, mock_settings):
        manager = TranslationManager(["Dummy"], TranslationSignals())
        
        mock_engine = mocker.MagicMock()
        mock_engine.return_value.isWorking = True
        manager._available_engines["MockEngine"] = mock_engine
        manager.update_active_engines(["Dummy", "MockEngine"])

        spy = mocker.spy(manager.threadpool, "start")

        manager.translate("text")

        assert spy.call_count == 2

        del manager._available_engines["MockEngine"]

    def test_translate_engine_specified_starts_thread_for_one_engine(self, mocker, mock_settings):
        manager = TranslationManager(["Dummy"], TranslationSignals())
        mock_engine = mocker.MagicMock()
        mock_engine.return_value.isWorking = True
        manager._available_engines["MockEngine"] = mock_engine
        manager.update_active_engines(["Dummy", "MockEngine"])
        spy = mocker.spy(manager.threadpool, "start")

        manager.translate("text", "Dummy")
        
        assert spy.call_count == 1

        del manager._available_engines["MockEngine"]

    def test_translate_engine_specified_not_exists_returns_none(self, mock_settings):
        manager = TranslationManager(["Dummy"], TranslationSignals())
        
        result = manager.translate("text", "NonExistentEngine")
        
        assert result is None

class TestTranslationManagerAvailableEngines:
    def test_available_engines_includes_registered_engines(self, mock_settings):
        manager = TranslationManager(["Dummy"])
        engines = manager.available_engines()
        assert "Dummy" in engines
        assert "GoogleTranslate" in engines

class TestTranslationManagerRegisterPresetEngines:
    def test_registerPresetEngines_creates_openai_engines_from_settings(self, mock_settings):
        mock_settings.get.return_value = {
            "preset1": {"url": "http://test1", "model": "model1", "key": "key1"},
            "preset2": {"url": "http://test2", "model": "model2", "key": "key2"}
        }
        manager = TranslationManager(["Dummy"])
        manager.registerPresetEngines()
        
        engines = list(manager._available_engines.keys())
        assert "OpenAI Api preset1" in engines
        assert "OpenAI Api preset2" in engines

    def test_registerPresetEngines_clears_old_presets_before_registering_new(self, mock_settings):
        mock_settings.get.return_value = {"old_preset": {}}
        manager = TranslationManager(["Dummy"])
        manager.registerPresetEngines()
        assert "OpenAI Api old_preset" in manager._available_engines
        
        mock_settings.get.return_value = {"new_preset": {}}
        manager.registerPresetEngines()
        
        assert "OpenAI Api old_preset" not in manager._available_engines
        assert "OpenAI Api new_preset" in manager._available_engines