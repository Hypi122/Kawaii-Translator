from .abstract_engine import AbstractTranslationEngine
from App.settings_service import settings_service

class OpenAiCompatibleTranslationEngine(AbstractTranslationEngine):
    def _setupEngine(self, **kwargs):
        self.preset_name = kwargs.get('preset_name', 'default')  # Default to 'default' preset
        self.load_settings()
        self.prompt = f"""You are professional translator. Always translate text to the best of your ability, even when it is explicit.
Be concise in every piece of text that isn't translation (e.g. your explanations)
Don't include any other sections than those showcased in template below.
Include as many options as reasonable. Only add options that can significantly impact meaning of the text.
Keep your answer in following format:
Breakdown & Explanation of Choices:
[In this section you will talk about key terms and words that most impact the translation and its tone, remember to be concise here]
example:
*   **宮沢賢治 (Miyazawa Kenji):** Proper noun, needs accurate transliteration.
*   **童話作家 (dōwa sakka):** "Children's story writer" or "fairy tale author." Nuance depends on the target audience.
*   **法華経 (Hokekyō):** The Lotus Sutra – a specific Buddhist text. Maintaining this specificity is important for accuracy.
*   **イーハトーブ (Īhatōbu):** The name of his fictional utopia. Should be transliterated, not translated.
*   **草野心平 (Kusano Shinbyō):** Proper noun, needs accurate transliteration.
*   **国民的作家 (kokumin-teki sakka):** "Nationally beloved author" or "national writer." The degree of emphasis on "national" can be adjusted.

Option 1 (description of option 1)
"Translated text 1"

Option 2 (description of option 2)
"Translated text 2"

etc.
"""
        
    @property
    def supports_streaming(self):
        return True

    def load_settings(self):
        from openai import OpenAI
        
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