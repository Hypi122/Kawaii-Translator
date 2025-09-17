from .abstract_engine import AbstractTranslationEngine
from App.settings_service import settings_service
import requests
import json

class DeepLXTranslationEngine(AbstractTranslationEngine):
    def _setupEngine(self, **kwargs):
        try:
            self.api_url = settings_service.get("deeplx_api_url")
            print("DeepLX initialized")
        except Exception as e:
            print(f"Could not load DeepLX engine: {e}")
    
    def translate(self, text):
        try:
            self.api_url = settings_service.get("deeplx_api_url")
            
            # Get language settings
            source_lang = settings_service.get("translation_source_lang") or "AUTO"
            target_lang = settings_service.get("translation_target_lang") or "EN"
            
            # Prepare the request payload
            payload = {
                "text": text,
                "source_lang": source_lang,
                "target_lang": target_lang
            }
            
            # Make the API request
            response = requests.post(
                self.api_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload)
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            result = response.json()
            return result.get("data", text)
        except Exception as e:
            print(f"DeepLX translation error: {e}")
            return f"DeepLX translation error: {e}"