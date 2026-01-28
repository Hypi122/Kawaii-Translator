import pytest
import numpy as np

from OCR.ocr_manager import OcrManager, DummyOcrEngine

@pytest.fixture
def mock_settings(mocker):
    mockSettings = mocker.patch('OCR.ocr_manager.settings_service')
    mockSettings.get.return_value = {}
    
    # HACK to unregister preset engines (register with empty settings) 
    # has to be done due to engine registering at import, aka before settings_service patch 
    OcrManager.registerPresetEngines()

    return mockSettings


@pytest.fixture
def sample_image():
    return np.zeros((100, 100, 3), dtype=np.uint8)

class TestDummyOcrEngine:
    def test_is_working_after_setup_returns_true(self):
        engine = DummyOcrEngine()
        assert engine.isWorking is True

    def test_predict_returns_dummy_text_for_sample_image(self, sample_image):
        engine = DummyOcrEngine()
        assert engine.predict(sample_image) == "Dummy OCR'd Text"


class TestOcrManagerInit:
    def test_init_loads_dummy_engine(self, mock_settings):
        manager = OcrManager("Dummy")
        assert manager.getCurrentEngine() == "Dummy"

    def test_init_invalid_engine_raises_keyerror(self, mock_settings):
        with pytest.raises(KeyError):
            OcrManager("NonExistentEngine")


class TestOcrManagerPredict:
    def test_predict_delegates_to_engine_and_returns_text(self, mock_settings, sample_image):
        manager = OcrManager("Dummy")
        result = manager.predict(sample_image)

        assert result == "Dummy OCR'd Text"


class TestOcrManagerAvailableEngines:
    def test_available_engines_includes_registered_engines(self, mock_settings):
        manager = OcrManager("Dummy")
        engines = manager.available_engines()
        assert engines == ['Dummy', 'PaddleOCR', 'WindowsOCR', 'MangaOCR']


class TestOcrManagerGetCurrentEngine:
    def test_getCurrentEngine_returns_engine_name(self, mock_settings):
        manager = OcrManager("Dummy")
        assert manager.getCurrentEngine() == "Dummy"


class TestOcrManagerSwapEngine:
    def test_swap_engine_to_same_engine_does_not_reload(self, mock_settings, mocker):
        spy = mocker.spy(DummyOcrEngine, "_setupEngine")
        manager = OcrManager("Dummy")
        original_engine = manager._current_engine
        
        manager.swap_engine("Dummy")
        
        assert spy.call_count == 1
        assert manager._current_engine is original_engine

    def test_swap_engine_changes_current_engine(self, mock_settings, mocker):
        manager = OcrManager("Dummy")
        assert manager.getCurrentEngine() == "Dummy"
        
        mock_engine = mocker.MagicMock()
        manager._registerEngine("MockEngine", mock_engine)
        
        manager.swap_engine("MockEngine")
        
        assert manager.getCurrentEngine() == "MockEngine"
        

class TestOcrManagerRegisterPresetEngines:
    def test_registerPresetEngines_creates_openai_engines_from_settings(self, mock_settings):
        mock_settings.get.return_value = {
            "preset1": {"url": "http://test1", "model": "model1", "key": "key1"},
            "preset2": {"url": "http://test2", "model": "model2", "key": "key2"}
        }
        
        OcrManager.registerPresetEngines()
        
        engines = list(OcrManager._available_engines.keys())
        assert "OpenAI Api preset1" in engines
        assert "OpenAI Api preset2" in engines

    def test_registerPresetEngines_clears_old_presets_before_registering_new(self, mock_settings):
        mock_settings.get.return_value = {"old_preset": {}}
        OcrManager.registerPresetEngines()
        assert "OpenAI Api old_preset" in OcrManager._available_engines
        
        mock_settings.get.return_value = {"new_preset": {}}
        OcrManager.registerPresetEngines()
        
        assert "OpenAI Api old_preset" not in OcrManager._available_engines
        assert "OpenAI Api new_preset" in OcrManager._available_engines