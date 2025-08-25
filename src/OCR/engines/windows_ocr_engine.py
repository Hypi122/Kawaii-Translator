from .abstract_engine import AbstractOcrEngine
import asyncio
from PIL import Image
import numpy as np

class WindowsOcrEngine(AbstractOcrEngine):
    def _setupEngine(self, **kwargs):
        try:
            import winocr
            self._winocr = winocr
        except:
            print("Couldnt load Windows OCR engine")
    
    async def _ensure_coroutine(self, awaitable):
        return await awaitable

    def _recognize_pil_lines(self, img, language="en"):
        return asyncio.run(self._ensure_coroutine(self._winocr.recognize_pil(img, lang=language))).lines

    def predict(self, image):
        if self.isWorking:
            try:
                from App.settings_service import settings_service
                lang = settings_service.get("source_lang")

                # Convert numpy array to PIL Image
                # image is in BGR format from OpenCV
                rgb_image = Image.fromarray(image[:, :, ::-1])  # Convert BGR to RGB
                result = self._recognize_pil_lines(rgb_image, lang)
                texts = []
                for line in result:
                    texts.append(line.text)
                formatted_text = "\n".join(texts)
                return formatted_text
            except Exception as e:
                print(f"Error during Windows OCR prediction: {e}")
                return ""
        else:
            print("Error: Windows OCR not initialized")
            return ""