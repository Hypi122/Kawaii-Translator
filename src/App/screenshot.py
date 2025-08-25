from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import QMouseEvent, QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal, QEventLoop

import numpy as np
import cv2
import mss

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
        self.setWindowOpacity(0.35)
        self.setStyleSheet("background-color: rgb(0, 0, 0);")
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
        if type(self.startPoint) != type(None) and type(self.currentPoint) != type(None):
            painter = QPainter(self)
            pen = QPen()
            pen.setWidth(2)
            pen.setColor(QColor("#2560DF"))
            painter.setPen(pen)

            brush = QBrush()
            brush.setColor(QColor("#569FFF"))
            brush.setStyle(Qt.BrushStyle.SolidPattern)
            painter.setBrush(brush)

            # transform startPoint, endPoint into x,y,w,h
            rect = QRect(self.startPoint, self.currentPoint).normalized()
            painter.drawRect(rect)

    # TODO: FIX AND UNDERSTAND WHATS GOING ON
    # I dont understand how that one is supposed to work
    # So i did it fully with an LLM
    # Should I have dispatched worker in ScreenshotController.start_selection()?
    def getImage(self):
        # waits until selectionFinished is emitted
        loop = QEventLoop()
        self.selectionFinished.connect(loop.quit)
        
        # CHAT gpt:
        # blocks until loop.quit is called
        # While blocked the GUI processes events.
        loop.exec()

        if self.isCancelled:
            self.startPoint = None
            self.endPoint = None
            self.currentPoint = None
            self.isSelecting = False
            self.isCancelled = False
            self.update()

        # now that seleciton finished we either have both coords
        # or operation was cancelled by user

        img = None
        if self.startPoint and self.endPoint:
            screenshot_rect = QRect(self.startPoint, self.endPoint).normalized()

            with mss.mss() as sct:
                monitor = {
                    "top": screenshot_rect.y(),
                    "left": screenshot_rect.x(),
                    "width": screenshot_rect.width(),
                    "height": screenshot_rect.height()
                }
                screenshot = sct.grab(monitor)
                
                # Convert to numpy array (OpenCV format)
                img = np.array(screenshot)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # Clear stuff
        self.startPoint = None
        self.endPoint = None
        self.currentPoint = None
        self.isSelecting = False
        self.update() # Clear the drawn selection from the overlay
        
        return img # np.array image in BGR or None