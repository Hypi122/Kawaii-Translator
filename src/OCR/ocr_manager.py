import gc
from OCR.engines.abstract_engine import AbstractOcrEngine
from OCR.engines.paddleocr_engine import PaddleOcrEngine
from OCR.engines.windows_ocr_engine import WindowsOcrEngine
from OCR.engines.mangaocr_engine import MangaOcrEngine
from OCR.engines.openai_compatible_engine import OpenAiCompatibleOcrEngine
from App.settings_service import settings_service

class DummyOcrEngine(AbstractOcrEngine):
    def _setupEngine(self, **kwargs):
        print("Loading Dummy OCR Engine")
    def predict(self, image):
        return "Dummy OCR'd Text"

class OcrManager:
    
    _available_engines = {}
    _engine_presets = {}  # Store preset names for engines

    def __init__(self, name, **kwargs):
        engine_class = self._available_engines[name]
        # Add preset name to kwargs if this is a preset engine
        if name in self._engine_presets:
            kwargs['preset_name'] = self._engine_presets[name]
        self._current_engine = engine_class(**kwargs)
        self._current_engine_name = name
        if not self._current_engine.isWorking:
            raise RuntimeError(f"Selected engine '{name}' could not be initialized. Check dependencies/configuration.")

        print(f"OcrManager initialized with engine: {name}")

    @classmethod
    def _registerEngine(cls, name, engine, preset_name=None):
        cls._available_engines[name] = engine
        if preset_name is not None:
            cls._engine_presets[name] = preset_name

    def predict(self, image):
        return self._current_engine.predict(image)
    
    def available_engines(self):
        return list(self._available_engines.keys())

    def getCurrentEngine(self):
        return self._current_engine_name

    def swap_engine(self, name, **kwargs):
        # Don't change engine if it's already the current one
        if self._current_engine_name == name:
            # Check if preset engines have the same parameters
            if name in self._engine_presets:
                preset_name = self._engine_presets[name]
                if kwargs.get('preset_name') == preset_name:
                    return
            else:
                return

        if self._current_engine is not None:
            del self._current_engine
            self._current_engine = None
            gc.collect()
        engine_class = self._available_engines[name]
        # Add preset name to kwargs if this is a preset engine
        if name in self._engine_presets:
            kwargs['preset_name'] = self._engine_presets[name]
        self._current_engine = engine_class(**kwargs)
        self._current_engine_name = name
    
    @classmethod
    def registerPresetEngines(cls):
        # Clear existing preset engines
        preset_engines_to_remove = [name for name in cls._available_engines.keys() if name.startswith("OpenAI Api ")]
        for engine_name in preset_engines_to_remove:
            del cls._available_engines[engine_name]
            if engine_name in cls._engine_presets:
                del cls._engine_presets[engine_name]

        # Register current presets
        presets = settings_service.get("ocr_presets")
        if presets:
            for preset in presets:
                cls._registerEngine("OpenAI Api "+preset, OpenAiCompatibleOcrEngine, preset_name=preset)

OcrManager._registerEngine("Dummy", DummyOcrEngine)
OcrManager._registerEngine("PaddleOCR", PaddleOcrEngine)
OcrManager._registerEngine("WindowsOCR", WindowsOcrEngine)
OcrManager._registerEngine("MangaOCR", MangaOcrEngine)
OcrManager.registerPresetEngines()