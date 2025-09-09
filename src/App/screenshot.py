from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import QMouseEvent, QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal, QEventLoop

import numpy as np
import cv2
from PIL import ImageGrab

class ScreenshotController():
    def __init__(self):
        super().__init__()
        self.screenshotOverlay = ScreenshotOverlay()

    def start_selection(self):
        self.screenshotOverlay.show()
        self.screenshotOverlay.raise_()
        self.screenshotOverlay.activateWindow()

        image = self.screenshotOverlay.getImage()
        self.screenshotOverlay.close()
        return image
    
    def cancel_selection(self):
        self.screenshotOverlay.cancelSelection()

class ScreenshotOverlay(QWidget):
    selectionFinished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.startPoint = None
        self.endPoint = None
        self.currentPoint = None
        self.isSelecting = False
        self.isCancelled = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        desktop_rect = QRect()
        for screen in QApplication.screens():
            desktop_rect = desktop_rect.united(screen.geometry())

        self.setGeometry(desktop_rect)
    def cancelSelection(self):
        self.selectionFinished.emit()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self.isSelecting == False:
                self.startPoint = pos
                self.currentPoint = pos
                self.isSelecting = True
            else:
                 self.endPoint = self.currentPoint
                 self.isSelecting = False
                 self.selectionFinished.emit()
                 
            self.update()

    def mouseMoveEvent(self, event):
        if self.isSelecting:
            self.currentPoint = event.position().toPoint()
            self.update()

    def paintEvent(self, event):
        alpha = 90 # 90 = ~0.35 opacity (0-255)
        painter = QPainter(self)

        # black semitransparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))  
        
        if self.isSelecting and self.startPoint and self.currentPoint:
            rect = QRect(self.startPoint, self.currentPoint).normalized()

            # Clear the area under the rectangle to fully transparent
            # So our semitransparent blue doesn't blend with black
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)  # back to normal

            pen = QPen()
            pen.setWidth(2)
            pen.setColor(QColor(37, 96, 223, alpha)) # #2560DF
            painter.setPen(pen)

            brush = QBrush()
            brush = QBrush(QColor(86, 159, 255, alpha)) # #569FFF
            brush.setStyle(Qt.BrushStyle.SolidPattern)
            painter.setBrush(brush)

            painter.drawRect(rect)

    def reset_state(self):
        QApplication.restoreOverrideCursor()
        self.startPoint = None
        self.endPoint = None
        self.currentPoint = None
        self.isSelecting = False
        self.isCancelled = False
        self.update()

    # TODO: FIX AND UNDERSTAND WHATS GOING ON
    # I dont understand how that one is supposed to work
    # So i did it fully with an LLM
    # Should I have dispatched worker in ScreenshotController.start_selection()?
    def getImage(self):
        QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
        # waits until selectionFinished is emitted
        loop = QEventLoop()
        self.selectionFinished.connect(loop.quit)
        
        # CHAT gpt:
        # blocks until loop.quit is called
        # While blocked the GUI processes events.
        loop.exec()

        if self.isCancelled:
            self.reset_state()

        # now that seleciton finished we either have both coords
        # or operation was cancelled by user

        img = None
        if self.startPoint and self.endPoint:
            screenshot_rect = QRect(self.startPoint, self.endPoint).normalized()
            
            # ImageGrab.grab() takes a tuple of (left, top, right, bottom)
            bbox = (
                screenshot_rect.x(),
                screenshot_rect.y(),
                screenshot_rect.x() + screenshot_rect.width(),
                screenshot_rect.y() + screenshot_rect.height()
            )
            screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
            
            # Convert to numpy array (OpenCV format)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        self.reset_state()
        return img # np.array image in BGR or None