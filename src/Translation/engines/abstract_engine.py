from abc import ABC, abstractmethod

class AbstractTranslationEngine(ABC):
    def __init__(self, **kwargs):
        self.initialized = False
        try:
            self._setupEngine(**kwargs)
            self.initialized = True
        except:
            print("Translation Engine initialization failed.")
        return

    @abstractmethod
    def _setupEngine(self, **kwargs):
        """
        Method that loads engine and prepares it for work.
        Performs necessary imports.
        """
        pass

    @abstractmethod
    def translate(self, text):
        """
        Args:
            text (str): The input text to translate.

        Returns:
            str: The translated text.
        """
        pass

    def translate_stream(self, text, chunk_callback, complete_callback=None):
        """
        Stream translation with callbacks
        Args:
            text (str): Text to translate
            chunk_callback: Called with each text chunk (chunk: str)
            complete_callback: Called when streaming is complete (optional)
        """
        result = self.translate(text)
        chunk_callback(result)
        if complete_callback:
            complete_callback()

    @property
    def isWorking(self):
        """
        Returns true if engine initialized successfully
        """
        return self.initialized
    
    @property
    def supports_streaming(self):
        """Returns True if engine supports streaming responses"""
        return False