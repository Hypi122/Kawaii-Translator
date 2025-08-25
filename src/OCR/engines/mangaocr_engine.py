from .abstract_engine import AbstractOcrEngine
from PIL import Image

class MangaOcrEngine(AbstractOcrEngine):
    def _setupEngine(self, **kwargs):
        try:
            from manga_ocr import MangaOcr
            self._mangaocr = MangaOcr()
            print("MangaOCR initialized")
        except Exception as e:
            print(f"Could not load MangaOCR engine: {e}")

    def predict(self, image):
        if self.isWorking:
            try:
                # Convert numpy array to PIL Image
                # image is in BGR format from OpenCV
                rgb_image = Image.fromarray(image[:, :, ::-1])  # Convert BGR to RGB
                # Perform OCR
                text = self._mangaocr(rgb_image)
                return text
            except Exception as e:
                print(f"Error during MangaOCR prediction: {e}")
                return ""
        else:
            print("Error: MangaOCR not initialized")
            return ""