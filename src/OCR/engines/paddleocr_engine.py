from .abstract_engine import AbstractOcrEngine
# from memory_profiler import profile
import gc

class PaddleOcrEngine(AbstractOcrEngine):
    def _setupEngine(self, **kwargs):
        self.prediction_count = 0
        self.reload_threshold = 4
        try:
            from paddleocr import PaddleOCR
            self._paddleocr = PaddleOCR(
                use_doc_orientation_classify=True, 
                use_doc_unwarping=True, 
                use_textline_orientation=True)
        except:
            print("Couldnt load PaddleOCR engine")
    
    # Doesnt even clean everything smh
    def memoryLeakHack(self):
        if hasattr(self, '_paddleocr'):
            del self._paddleocr
            self._paddleocr = None
        gc.collect()
        self._setupEngine()

    # @profile
    def predict(self, image):

        # I hate paddleocr I hate paddleocr I hate paddleocr I hate paddleocr 
        # there's memory leak in library itself :/
        # (at least on cpu, without high performance inference)
        if self.prediction_count >= self.reload_threshold:
            self.memoryLeakHack()

        if self.isWorking:
            result = self._paddleocr.predict(image)
            self.prediction_count += 1
            texts = []
            for res in result:
                texts.append("\n".join(res["rec_texts"]))
            formatted_text = "\n\n".join(texts)
            return formatted_text
        else:
            print("Error: PaddleOCR not initialized")