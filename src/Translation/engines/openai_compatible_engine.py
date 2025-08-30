from .abstract_engine import AbstractTranslationEngine
from App.settings_service import settings_service

class OpenAiCompatibleTranslationEngine(AbstractTranslationEngine):
    def _setupEngine(self, **kwargs):
        self.preset_name = kwargs.get('preset_name', 'default')  # Default to 'default' preset
        self.prompt = ""
        self.load_settings()
    @property
    def supports_streaming(self):
        return True

    def load_settings(self):
        from openai import OpenAI
        
        self.prompt = settings_service.get("openai_translation_prompt")
        # Get settings based on preset
        presets = settings_service.get("translation_presets")
        if presets and self.preset_name in presets:
            preset = presets[self.preset_name]
            base_url = preset.get("url") or ""
            api_key = preset.get("key") or ""
            self.model = preset.get("model") or ""
        else:
            # Fallback to default preset if specified preset not found
            if presets and "default" in presets:
                preset = presets["default"]
                base_url = preset.get("url") or ""
                api_key = preset.get("key") or ""
                self.model = preset.get("model") or ""
            else:
                base_url = ""
                api_key = ""
                self.model = ""
            
        self._client = OpenAI(
        #   base_url="https://openrouter.ai/api/v1",
        base_url=base_url,
        api_key=api_key)
        self.target_lang = settings_service.get("translation_target_lang")

    def translate(self, text):
        self.load_settings()
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                    {
                        "role": "user",
                        "content": f"{self.prompt} Translate to {self.target_lang} following text: {text}"
                    }
            ]
        )
        return completion.choices[0].message.content
    
    def translate_stream(self, text, chunk_callback, complete_callback=None):
        self.load_settings()
        completion = self._client.chat.completions.create(
            model=self.model,
            stream=True,
            messages=[
                    {
                        "role": "user",
                        "content": f"{self.prompt} Translate to {self.target_lang} following text: {text}"
                    }
            ]
        )
        for chunk in completion:
            if chunk.choices[0].delta.content is not None:
                chunk_callback(chunk.choices[0].delta.content)
        
        if complete_callback:
            complete_callback()