import gc
from Translation.engines.abstract_engine import AbstractTranslationEngine
from Translation.engines.dummy_engine import DummyTranslationEngine
from Translation.engines.google_translate_engine import GoogleTranslateTranslationEngine
from Translation.engines.openai_compatible_engine import OpenAiCompatibleTranslationEngine
from Translation.engines.deeplx_engine import DeepLXTranslationEngine
from App.settings_service import settings_service
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool, pyqtSlot

class TranslationWorkerSignals(QObject):
    finished = pyqtSignal(str, str)  # engine_name, result
    error = pyqtSignal(str, str)     # engine_name, error_message
    chunk = pyqtSignal(str, str)  # engine_name, chunk_text
    complete = pyqtSignal(str)    # engine_name

class TranslationWorker(QRunnable):
    def __init__(self, engine_name, engine, text, signals):
        super().__init__()
        self.engine_name = engine_name
        self.engine = engine
        self.text = text
        self.signals = signals  # TranslationWorkerSignals

    @pyqtSlot()
    def run(self):
        try:
            if self.engine.supports_streaming:
                self.engine.translate_stream(self.text,
                                             lambda chunk: self.signals.chunk.emit(self.engine_name, chunk),
                                             lambda: self.signals.complete.emit(self.engine_name))
            else:
                result = self.engine.translate(self.text)
                self.signals.finished.emit(self.engine_name, result)
        except Exception as e:
            self.signals.error.emit(self.engine_name, str(e))


class TranslationSignals(QObject):
    translationReady = pyqtSignal(str, str)  # engine_name, translated_text
    translationError = pyqtSignal(str, str)  # engine_name, error_message
    translationChunk = pyqtSignal(str, str)  # engine_name, chunk_text
    translationComplete = pyqtSignal(str)    # engine_name
class TranslationManager:
    
    _available_engines = {}
    _engine_presets = {}  # Store preset names for engines

    def __init__(self, names, signals=None, **kwargs):
        self._active_engines  = {}
        self.signals = signals
        self.update_active_engines(names, **kwargs)
        self.threadpool = QThreadPool()
    
    def update_active_engines(self, names: list, **kwargs):
        # Clean up old engines
        for engine in self._active_engines.values():
            del engine
        self._active_engines.clear()
        gc.collect()

        for name in names:
            if name in self._available_engines:
                engine_class = self._available_engines[name]
                if name in self._engine_presets:
                    kwargs['preset_name'] = self._engine_presets[name]
                instance = engine_class(**kwargs)
                if instance.isWorking:
                    self._active_engines[name] = instance
                else:
                    print(f"Engine '{name}' could not be initialized.")
    
    def translate(self, text, engine_name=None):
        if engine_name is not None:
            if engine_name in self._active_engines:
                engines = [(engine_name, self._active_engines[engine_name])]
            else:
                return
        else:
            engines = self._active_engines.items()
        
        for name, engine in engines:
            signals = TranslationWorkerSignals()
            worker = TranslationWorker(name, engine, text, signals)
            if engine.supports_streaming:
                signals.chunk.connect(self.signals.translationChunk)
                signals.complete.connect(self.signals.translationComplete)
                signals.error.connect(self.signals.translationError)
            else:
                signals.finished.connect(self.signals.translationReady)
                signals.error.connect(self.signals.translationError)

            self.threadpool.start(worker)
    
    def available_engines(self):
        return list(self._available_engines.keys())

    def getCurrentEngine(self):
        return list(self._active_engines)

    def swap_engine(self, name, **kwargs):
        self.update_active_engines(name,**kwargs)
    
    @classmethod
    def _registerEngine(cls, name, engine, preset_name=None):
        cls._available_engines[name] = engine
        if preset_name is not None:
            cls._engine_presets[name] = preset_name

    @classmethod
    def registerPresetEngines(cls):
        # Clear existing preset engines
        preset_engines_to_remove = [name for name in cls._available_engines.keys() if name.startswith("OpenAI Api ")]
        for engine_name in preset_engines_to_remove:
            del cls._available_engines[engine_name]
            if engine_name in cls._engine_presets:
                del cls._engine_presets[engine_name]

        # Register current presets
        presets = settings_service.get("translation_presets")
        if presets:
            for preset in presets:
                cls._registerEngine("OpenAI Api "+preset, OpenAiCompatibleTranslationEngine, preset_name=preset)

TranslationManager._registerEngine("Dummy", DummyTranslationEngine)
TranslationManager._registerEngine("GoogleTranslate", GoogleTranslateTranslationEngine)
TranslationManager._registerEngine("DeepLX", DeepLXTranslationEngine)
TranslationManager.registerPresetEngines()