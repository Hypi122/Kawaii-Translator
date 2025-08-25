from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel, QPushButton, QSplitter
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QRunnable, QThreadPool, Qt

class WorkerSignals(QObject):
    """Signals from a running worker thread.

    finished
        dict translated text
    """

    finished = pyqtSignal(dict)
    # Error text, re-enable on failures
    error = pyqtSignal(str)

class Worker(QRunnable):

    def __init__(self, fn, **kwargs):
        super().__init__()
        self.signals = WorkerSignals()
        self.fn = fn
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        result = ""
        try:
            result = self.fn(**self.kwargs)
            if result is None:
                return
            self.signals.finished.emit(result)
        except Exception as e:
            print("Error!", e)
            try:
                self.signals.error.emit(str(e))
            except Exception:
                pass

class OcrWindow(QWidget):
    retranslateRequested = pyqtSignal(str)

    def __init__(self, TranslationManager):
        super().__init__()
        self.setWindowTitle("Kawaii Translator - OCR")
        self.TranslationManager = TranslationManager
        self.threadpool = QThreadPool()
        self.setMinimumSize(700,400)
        self.setup_ui()

        if hasattr(self.TranslationManager, 'signals') and self.TranslationManager.signals:
            self.TranslationManager.signals.translationReady.connect(self.on_translation_ready)
            self.TranslationManager.signals.translationError.connect(self.on_translation_error)
            self.TranslationManager.signals.translationChunk.connect(self.on_translation_chunk)
            self.TranslationManager.signals.translationComplete.connect(self.on_translation_complete)
        else:
            print("ERROR: No signals in TranslationManager.")

    def setup_ui(self):
        layout = QVBoxLayout(self)

        ocrLayout = QVBoxLayout()

        self.ocrTextboxLabel = QLabel("Ocr")
        self.ocrTextbox = QPlainTextEdit()

        self.translationTextboxLabel = QLabel("Translated")

        self.retranslateBtn = QPushButton("Re-translate")
        self.retranslateBtn.pressed.connect(self.startRetranslate)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        # Create container for OCR components
        ocrContainer = QWidget()
        ocrContainerLayout = QVBoxLayout(ocrContainer)
        ocrContainerLayout.setContentsMargins(0, 0, 0, 0)
        ocrContainerLayout.addWidget(self.ocrTextboxLabel)
        ocrContainerLayout.addWidget(self.ocrTextbox)

        # Create container for translation components
        translationContainer = QWidget()
        self.translationContainerLayout = QHBoxLayout(translationContainer)
        self.translationContainerLayout.setContentsMargins(0, 0, 0, 0)
        self.translationContainerLayout.addWidget(self.translationTextboxLabel)
        self.translationWidgets = {}

        self.splitter.addWidget(ocrContainer)
        self.splitter.addWidget(translationContainer)

        # Why there isnt a way to make everything non-collapsible by default???
        self.splitter.setCollapsible(0, False)  # OCR container
        self.splitter.setCollapsible(1, False)  # Translation container
        
        ocrLayout.addWidget(self.retranslateBtn)

        layout.addWidget(self.splitter)
        layout.addLayout(ocrLayout)
    
    # https://stackoverflow.com/questions/9374063/remove-all-items-from-a-layout
    def clearLayout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clearLayout(item.layout())

    def setup_translation_ui(self):
        # Clear the layout
        self.clearLayout(self.translationContainerLayout)
        self.translationWidgets = {}

        for engine in self.TranslationManager._active_engines.keys():
            layout = QVBoxLayout()
            text_edit = QPlainTextEdit()
            layout.addWidget(QLabel(engine))
            layout.addWidget(text_edit)
            self.translationContainerLayout.addLayout(layout)
            self.translationWidgets[engine] = text_edit

    def setOcr(self, text):
        self.ocrTextbox.setPlainText(text)
    
    # we can use that for both streaming and non-streaming
    # because translation gets cleared in setup_translation_ui
    def setTranslation(self, text, engine=None):
        if engine==None:
            # TODO: set to all ig
            return
        if engine in self.translationWidgets:
            current_text = self.translationWidgets[engine].toPlainText()
            self.translationWidgets[engine].setPlainText(current_text+text)

    def translateOcr(self, TranslationManager, text):
        TranslationManager.translate(text)
    
    def startRetranslate(self):
        self.retranslateBtn.setEnabled(False)
        self.retranslateBtn.setText("Translating...")

        self.setup_translation_ui()
        worker = Worker(
            fn=self.translateOcr,
            TranslationManager=self.TranslationManager,
            text=self.ocrTextbox.toPlainText()
        )

        self.threadpool.start(worker)

    @pyqtSlot(str, str)
    def on_translation_ready(self, engine, translated_text):
        self.setTranslation(translated_text, engine=engine)
        self.retranslateBtn.setEnabled(True)
        self.retranslateBtn.setText("Re-translate")

    @pyqtSlot(str, str)
    def on_translation_error(self, engine, error_text):
        self.setTranslation(f"Error: {error_text}", engine=engine)
        self.retranslateBtn.setEnabled(True)
        self.retranslateBtn.setText("Re-translate")

    @pyqtSlot(str, str)
    def on_translation_chunk(self, engine, chunk):
        self.setTranslation(chunk, engine=engine)

    @pyqtSlot(str)
    def on_translation_complete(self, engine):
        self.retranslateBtn.setEnabled(True)
        self.retranslateBtn.setText("Re-translate")
