from .abstract_engine import AbstractOcrEngine


class PaddleOcrEngine(AbstractOcrEngine):
    def _setupEngine(self, **kwargs):
        try:
            from paddleocr import PaddleOCR
            self._paddleocr = PaddleOCR(
                use_doc_orientation_classify=True, 
                use_doc_unwarping=True, 
                use_textline_orientation=True,
                enable_mkldnn=False)
        except:
            print("Couldnt load PaddleOCR engine")

    def predict(self, image):
        if self.isWorking:
            result = self._paddleocr.predict(image)
            texts = []
            for res in result:
                texts.append("\n".join(res["rec_texts"]))
            formatted_text = "\n\n".join(texts)
            return formatted_text
        else:
            print("Error: PaddleOCR not initialized")