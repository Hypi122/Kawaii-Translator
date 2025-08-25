from OCR.ocr_manager import OcrManager
from Translation.translation_manager import TranslationManager, TranslationSignals
from PyQt6.QtWidgets import QApplication, QWidget

from App.main_window import MainWindow
from App.settings_service import settings_service

def main():
    # Load OCR engine from settings
    ocr_engine = settings_service.get("ocr_engine")
    ocrProcessor = OcrManager(ocr_engine)

    translation_manager = settings_service.get("translation_engine")
    translationManager = TranslationManager(translation_manager, signals=TranslationSignals())

    app = QApplication([])
    window = MainWindow(ocrProcessor, translationManager)
    window.show()
    app.exec()
if __name__ == "__main__":
    main()