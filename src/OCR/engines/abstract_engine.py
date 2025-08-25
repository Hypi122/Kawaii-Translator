from abc import ABC, abstractmethod

class AbstractOcrEngine(ABC):
    def __init__(self, **kwargs):
        self.initialized = False
        try:
            self._setupEngine(**kwargs)
            self.initialized = True
        except:
            print("OCR Engine initialization failed.")
        return

    @abstractmethod
    def _setupEngine(self, **kwargs):
        """
        Method that loads engine and prepares it for work.
        Performs necessary imports.
        """
        pass

    @abstractmethod
    def predict(self, image):
        """
        Args:
            image (np.array): The input image to perform OCR on.

        Returns:
            str: The extracted and formatted (with newlines) text.
        """
        pass

    @property
    def isWorking(self):
        """
        Returns true if engine initialized successfully
        """
        return self.initialized