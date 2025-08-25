from .abstract_engine import AbstractTranslationEngine
from App.settings_service import settings_service
import asyncio

class GoogleTranslateTranslationEngine(AbstractTranslationEngine):
    def _setupEngine(self, **kwargs):
        try:
            from googletrans import Translator
            self._translator = Translator()
            print("Google Translate initialized")
        except:
            print("Couldnt load Google translate engine")
    
    def translate(self, text):
        try:
            # Get the current running event loop if one exists
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # If no event loop is running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        lang = settings_service.get("translation_source_lang")
        dest = settings_service.get("translation_target_lang")
        
        # Run the async translation task until it's complete
        result = loop.run_until_complete(
            self._translator.translate(text, dest=dest, src=lang)
        )
        return result.text