from .abstract_engine import AbstractTranslationEngine

class DummyTranslationEngine(AbstractTranslationEngine):
    def _setupEngine(self, **kwargs):
        print("Loading Dummy Translation Engine")
    
    def translate(self, text):
        return "This is dummy translation"