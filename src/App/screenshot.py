from PyQt6.QtWidgets import QWidget, QApplication, QMessageBox
from PyQt6.QtGui import QMouseEvent, QPainter, QPen, QColor, QBrush, QImage, QPixmap
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal, QEventLoop

import numpy as np
import cv2
from PIL import ImageGrab

from Util.platform import is_linux
from App.capture import CaptureError, capture_frozen_screen, crop_selection, union_screen_geometry

class ScreenshotController():
    def __init__(self):
        super().__init__()
        self.screenshotOverlay = ScreenshotOverlay()

    def start_selection(self):
        # Linux freeze-first flow: capture the desktop BEFORE the overlay is shown.
        # This also avoids capturing our own translucent overlay into the image —
        # a latent bug in live-capture flows (the selection UI would appear in the grab).
        frozen = None
        if is_linux():
            try:
                frozen = capture_frozen_screen()
            except CaptureError as e:
                QMessageBox.critical(None, "Screenshot capture failed", str(e))
                return None
        self.screenshotOverlay.setFrozenScreen(frozen)
        # Re-sync overlay geometry with the current screen layout: the overlay is
        # constructed once at startup, but monitors/scaling can change mid-session,
        # and the frozen image's scale factors are computed at capture time.
        self.screenshotOverlay.setGeometry(union_screen_geometry())
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
        self.frozen = None
        self.frozenPixmap = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Single source of truth for the desktop union rect (see union_screen_geometry).
        self.setGeometry(union_screen_geometry())

    def setFrozenScreen(self, frozen):
        """Set the frozen full-desktop image (Linux). None restores the live translucent mode (Windows/macOS)."""
        self.frozen = frozen
        self.frozenPixmap = None
        if frozen is not None:
            # ndarray (BGR) -> QPixmap. ascontiguousarray: QImage needs contiguous rows.
            data = np.ascontiguousarray(frozen.image)
            h, w = data.shape[:2]
            qimg = QImage(data.data, w, h, w * 3, QImage.Format.Format_BGR888)
            self.frozenPixmap = QPixmap.fromImage(qimg.copy())  # .copy(): deep-copy — data buffer is owned by numpy

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

        # Frozen mode (Linux): paint the frozen desktop stretched to the overlay
        # geometry (which spans the union of screens) instead of showing through.
        if self.frozenPixmap is not None:
            painter.drawPixmap(self.rect(), self.frozenPixmap)

        # black semitransparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))  
        
        if self.isSelecting and self.startPoint and self.currentPoint:
            rect = QRect(self.startPoint, self.currentPoint).normalized()

            if self.frozenPixmap is not None:
                # Show the selected region un-dimmed: redraw the frozen image clipped to the rect.
                painter.save()
                painter.setClipRect(rect)
                painter.drawPixmap(self.rect(), self.frozenPixmap)
                painter.restore()
            else:
                # Clear the area under the rectangle to fully transparent (live mode)
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

            if self.frozen is not None:
                # Crop the frozen image through the SAME scale factors used to paint it
                # (image_px / union_logical_px), so selection and crop stay self-consistent
                # even with awkward multi-monitor geometries. crop_selection clamps to bounds.
                img = crop_selection(self.frozen, screenshot_rect)
            else:
                # Live capture (Windows/macOS): PIL.ImageGrab
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