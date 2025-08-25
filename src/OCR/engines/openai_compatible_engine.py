from .abstract_engine import AbstractOcrEngine
from App.settings_service import settings_service
import gc
import base64
from PIL import Image
import io

class OpenAiCompatibleOcrEngine(AbstractOcrEngine):
    def _setupEngine(self, **kwargs):
        self.preset_name = kwargs.get('preset_name', 'default')  # Default to 'default' preset
        self.load_settings()

    def load_settings(self):
        from openai import OpenAI
        
        # Get settings based on preset
        presets = settings_service.get("ocr_presets")
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

    def predict(self, image):
        if self.isWorking:
            # Convert numpy array to PIL Image
            # image is in BGR format from OpenCV
            rgb_image = Image.fromarray(image[:, :, ::-1])  # Convert BGR to RGB
            buffered = io.BytesIO()
            rgb_image.save(buffered, format="PNG")
            bb = base64.b64encode(buffered.getvalue()).decode('utf-8')

            self.load_settings()
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                        {
                            "role": "user",
                            "content": [
                                    { "type": "text", "text": "OCR extract text from this image. Output only text, without any explanation." },
                                    { "type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{bb}"}}
                                ]
                        }
                ]
            )
            return completion.choices[0].message.content
        else:
            print("Error: OpenAICompatible OCR not initialized")