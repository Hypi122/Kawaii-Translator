from __future__ import annotations

import logging

from PyQt6.QtWidgets import QWidget, QApplication, QMessageBox
from PyQt6.QtGui import QMouseEvent, QPainter, QPen, QColor, QBrush, QImage, QPixmap
from PyQt6.QtCore import Qt, QSize, QRect, pyqtSignal, QEventLoop

import numpy as np
import cv2
from PIL import ImageGrab

from Util.platform import is_linux
from App.capture import CaptureError, capture_frozen_screen, crop_selection, union_screen_geometry
from App.overlay_geometry import local_selection_to_union, screen_origin_in_union, screen_image_slice

logger = logging.getLogger(__name__)

def _screens():
    """All attached QScreens. Seam for tests (mirrors QtGrabBackend._screens in capture.py)."""
    return QApplication.screens()


def _show_overlay_on_screen(overlay, screen):
    """Show `overlay` fullscreen on `screen`'s output.

    On Wayland, compositors only honor QWindow.setScreen() for FULLSCREEN
    windows; for normal windows placement is compositor policy (KWin was
    observed moving both overlays onto one output and clamping height to the
    panel workarea). So: force native window creation (winId) so the QWindow
    handle exists, pin the handle to `screen`, then showFullScreen(). The
    frameless + translucent attributes are set in __init__ before winId(), so
    translucent fullscreen painting keeps working.
    Seam for tests (fake screens are not QScreen instances)."""
    overlay.winId()  # force native window creation; makes windowHandle() valid
    handle = overlay.windowHandle()
    if handle is not None:
        handle.setScreen(screen)
    overlay.showFullScreen()


def _overlay_actual_screen(overlay):
    """QScreen the overlay's window ACTUALLY sits on (compositor truth), or
    None before the native window exists. Seam for tests."""
    handle = overlay.windowHandle()
    return handle.screen() if handle is not None else None


def _connect_screen_changed(overlay, callback):
    """Subscribe callback(new_screen) to the overlay window's screenChanged
    signal. No-op when the native window doesn't exist. Seam for tests."""
    handle = overlay.windowHandle()
    if handle is not None:
        handle.screenChanged.connect(callback)

def _build_frozen_pixmap(frozen) -> QPixmap:
    """ndarray (BGR) -> QPixmap. ascontiguousarray: QImage needs contiguous rows."""
    data = np.ascontiguousarray(frozen.image)
    h, w = data.shape[:2]
    qimg = QImage(data.data, w, h, w * 3, QImage.Format.Format_BGR888)
    return QPixmap.fromImage(qimg.copy())  # .copy(): deep-copy — data buffer is owned by numpy

def _frozen_matches_screens(frozen, screens):
    """True when `screens` still produce the union the frozen image was sized
    from: the union implied by image+scale (image_size / scale) must equal the
    union of the current screen geometries, and the set must be non-empty.
    Pure — unit-testable with fake screens."""
    if not screens:
        return False
    union = QRect()
    for screen in screens:
        union = union.united(screen.geometry())
    implied_w = round(frozen.image.shape[1] / frozen.scale_x)
    implied_h = round(frozen.image.shape[0] / frozen.scale_y)
    return (implied_w, implied_h) == (union.width(), union.height())

class ScreenshotController():
    def __init__(self):
        super().__init__()
        # Windows/macOS live path: one persistent union-spanning overlay
        # (clients position windows freely there) — behavior UNCHANGED.
        self.screenshotOverlay = ScreenshotOverlay()
        # Linux freeze-first path: one overlay PER QScreen, rebuilt each
        # selection (monitor layout can change between captures).
        self.overlays: list[ScreenshotOverlay] = []

    def start_selection(self):
        # Linux freeze-first flow: capture the desktop BEFORE the overlay is shown.
        # This also avoids capturing our own translucent overlay into the image —
        # a latent bug in live-capture flows (the selection UI would appear in the grab).
        if is_linux():
            try:
                frozen = self._freeze_verified()
            except CaptureError as e:
                QMessageBox.critical(None, "Screenshot capture failed", str(e))
                return None
            return self._frozen_selection_linux(frozen)
        # --- Windows/macOS live path (unchanged) ---
        frozen = None
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
        for overlay in self.overlays:
            overlay.cancelSelection()
        self.screenshotOverlay.cancelSelection()

    def _frozen_selection_linux(self, frozen):
        """Per-screen overlays over the frozen desktop (Linux, X11 + Wayland).

        The frozen image is ONE picture of the whole composited desktop, but
        compositors won't let a client self-position or span outputs, so a single
        union-spanning window gets squished onto one monitor. Instead: one overlay
        per QScreen, each painting its monitor's slice. Slices use the SAME global
        scale factors the capture computed (uniform-scale approximation; mixed-DPR
        multi-monitor setups remain approximate — pre-existing, see
        App.overlay_geometry and QtGrabBackend composition notes).

        Overlays are placed FULLSCREEN on their intended output via
        _show_overlay_on_screen (on Wayland compositors only honor setScreen for
        fullscreen windows); each is then re-synced to the screen its window
        ACTUALLY landed on by _reconcile_overlay_screen, because compositors may
        relocate normal windows (KWin was observed moving both overlays onto one
        output and clamping height to the panel workarea). Slice/offset are set
        before showing so the first paint is already correct; the post-show
        reconcile fixes any compositor relocation.
        """
        union = union_screen_geometry()
        self.overlays = []
        screens = _screens()
        for screen in screens:
            overlay = ScreenshotOverlay(screen.geometry(), union)
            self.overlays.append(overlay)
        if not self.overlays:
            # Nothing would ever quit the selection loop -> permanent hang.
            # Belt-and-braces: backends already raise on empty unions.
            return None
        # QPixmap is implicitly shared in Qt, so one pixmap serves all overlays.
        pixmap = _build_frozen_pixmap(frozen)
        for screen, overlay in zip(screens, self.overlays):
            overlay.setFrozenScreen(
                frozen,
                image_slice=screen_image_slice(
                    screen.geometry(), union,
                    QSize(frozen.image.shape[1], frozen.image.shape[0]),
                    frozen.scale_x, frozen.scale_y),
                pixmap=pixmap)
        for screen, overlay in zip(screens, self.overlays):
            _show_overlay_on_screen(overlay, screen)
            self._reconcile_overlay_screen(overlay, screen, screens, union, frozen, pixmap)
        if not any(overlay._boundScreenGeometry is not None for overlay in self.overlays):
            # Every overlay was closed during placement (e.g. the compositor put
            # them all on outputs outside the frozen set) -> nothing could ever
            # quit the selection loop. Mirror of the empty-overlays guard above.
            logger.warning("All overlays were closed during placement; aborting selection")
            for overlay in self.overlays:
                overlay.reset_state()
                overlay.close()
                overlay.setFrozenScreen(None)
            return None
        return self._wait_for_frozen_selection(self.overlays, frozen)

    def _freeze_verified(self):
        """Freeze the desktop, verifying the screen set still matches what the
        frozen image/scale was computed from. One re-freeze on mismatch (hotplug
        flap); persistent mismatch raises CaptureError (existing dialog flow)."""
        for attempt in (1, 2):
            frozen = capture_frozen_screen()  # hard CaptureError propagates (no retry)
            if _frozen_matches_screens(frozen, _screens()):
                return frozen
            if attempt == 1:
                logger.warning("Screen set changed during capture; re-freezing once")
            else:
                logger.warning("Screen set still mismatched after re-freeze; giving up")
        raise CaptureError("Screen configuration changed while capturing the desktop; please try again.")

    def _rebind_overlay_to_screen(self, overlay, screen_geometry, screens, union, frozen, pixmap):
        """Repoint `overlay`'s imageSlice + unionOffset at `screen_geometry` — the
        screen its window ACTUALLY sits on — using the same overlay_geometry
        helpers as at creation. If no screen in the frozen set has that geometry
        (screen flap), close the overlay: never map clicks to nonexistent
        coordinates. Returns True if rebound, False if closed."""
        match = next((s for s in screens if s.geometry() == screen_geometry), None)
        if match is None:
            logger.warning("Overlay landed on screen %s which is not part of the frozen capture; closing it",
                           screen_geometry)
            overlay.close()
            overlay._boundScreenGeometry = None
            return False
        overlay.setFrozenScreen(
            frozen,
            image_slice=screen_image_slice(
                screen_geometry, union,
                QSize(frozen.image.shape[1], frozen.image.shape[0]),
                frozen.scale_x, frozen.scale_y),
            pixmap=pixmap)
        overlay.unionOffset = screen_origin_in_union(screen_geometry, union)
        overlay._boundScreenGeometry = QRect(screen_geometry)
        overlay.update()
        return True

    def _reconcile_overlay_screen(self, overlay, intended_screen, screens, union, frozen, pixmap):
        """Post-show truth re-sync: if the compositor put the window somewhere
        else, rebind slice+offset to the ACTUAL screen; then track future moves."""
        actual = _overlay_actual_screen(overlay)
        if actual is not None and actual.geometry() != intended_screen.geometry():
            self._rebind_overlay_to_screen(overlay, actual.geometry(), screens, union, frozen, pixmap)
        _connect_screen_changed(
            overlay,
            lambda new_screen, ov=overlay: self._on_overlay_screen_changed(
                ov, new_screen, screens, union, frozen, pixmap))

    def _on_overlay_screen_changed(self, overlay, new_screen, screens, union, frozen, pixmap):
        if new_screen is None or getattr(overlay, "_rebinding", False):
            return
        if overlay._boundScreenGeometry is None:
            return  # foreign-closed overlay must never be revived by a late screenChanged
        if overlay not in self.overlays:
            return  # stale connection from a previous selection round
        geometry = new_screen.geometry()
        if overlay._boundScreenGeometry is not None and geometry == overlay._boundScreenGeometry:
            return  # no-op move (same output) — avoids churn/recursion loops
        overlay._rebinding = True
        try:
            self._rebind_overlay_to_screen(overlay, geometry, screens, union, frozen, pixmap)
        finally:
            overlay._rebinding = False

    def _wait_for_frozen_selection(self, overlays, frozen):
        """Block until ANY overlay completes or the user cancels, then tear down
        ALL overlays (a selection cannot span monitors) and crop the winner."""
        QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
        loop = QEventLoop()
        for overlay in overlays:
            overlay.selectionFinished.connect(loop.quit)
        loop.exec()
        QApplication.restoreOverrideCursor()

        rect = next((r for r in (ov.selectionUnionRect() for ov in overlays) if r is not None), None)
        img = crop_selection(frozen, rect) if rect is not None else None
        for overlay in overlays:
            overlay.reset_state()
            overlay.close()
            # Drop refs to the shared pixmap + frozen ndarray; the closed QWidget
            # shells stay in self.overlays until the next selection replaces the list.
            overlay.setFrozenScreen(None)
        return img

class ScreenshotOverlay(QWidget):
    selectionFinished = pyqtSignal()

    def __init__(self, screen_geometry: QRect | None = None, union: QRect | None = None):
        super().__init__()
        self.startPoint = None
        self.endPoint = None
        self.currentPoint = None
        self.isSelecting = False
        self.frozen = None
        self.frozenPixmap = None
        self.imageSlice = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Single source of truth for the desktop union rect (see union_screen_geometry).
        # The per-screen Linux path passes the already-snapshot union (no TOCTOU
        # re-read across hotplug); callers that don't pass one — the Windows/macOS
        # persistent overlay — have it read here.
        if union is None:
            union = union_screen_geometry()
        self.setGeometry(screen_geometry if screen_geometry is not None else union)
        # Local (0,0) of this window expressed in union-logical coordinates:
        # (0,0) for the union-spanning overlay (Windows/macOS live path — unchanged);
        # for per-screen Linux overlays, the screen's origin within the union
        # (negative-origin layouts handled).
        self.unionOffset = screen_origin_in_union(self.geometry(), union)
        self._boundScreenGeometry = QRect(self.geometry())
        self._rebinding = False

    def setFrozenScreen(self, frozen, image_slice: QRect | None = None, pixmap: QPixmap | None = None):
        """Set the frozen full-desktop image (Linux). None restores the live translucent mode (Windows/macOS).

        image_slice: sub-rect of the frozen image this window paints; None = whole image, legacy union behavior.
        pixmap: pre-built shared QPixmap of the frozen full-desktop image, reused by all per-screen overlays."""
        self.frozen = frozen
        if frozen is None:
            self.frozenPixmap = None
        elif pixmap is not None:
            # QPixmap is implicitly shared in Qt, so one pixmap serves all overlays.
            self.frozenPixmap = pixmap
        else:
            self.frozenPixmap = _build_frozen_pixmap(frozen)
        self.imageSlice = image_slice

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

        # Frozen mode (Linux): paint the frozen desktop slice for this window
        # (per-screen overlays paint their monitor's slice; the union-spanning
        # overlay paints the whole image) instead of showing through.
        if self.frozenPixmap is not None:
            src = self.imageSlice if self.imageSlice is not None else self.frozenPixmap.rect()
            if not src.isEmpty():
                painter.drawPixmap(self.rect(), self.frozenPixmap, src)

        # black semitransparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))  
        
        if self.isSelecting and self.startPoint is not None and self.currentPoint is not None:
            rect = QRect(self.startPoint, self.currentPoint).normalized()

            if self.frozenPixmap is not None:
                # Show the selected region un-dimmed: redraw the frozen image clipped to the rect.
                painter.save()
                painter.setClipRect(rect)
                src = self.imageSlice if self.imageSlice is not None else self.frozenPixmap.rect()
                if not src.isEmpty():
                    painter.drawPixmap(self.rect(), self.frozenPixmap, src)
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
        self.startPoint = None
        self.endPoint = None
        self.currentPoint = None
        self.isSelecting = False
        self.update()

    def selectionUnionRect(self):
        """Completed selection as a union-logical QRect, or None until both points
        exist (cancel leaves it None). Per-screen overlays lift local coords by
        their screen origin; the union overlay's offset is (0,0), i.e. unchanged."""
        if self.startPoint is None or self.endPoint is None:
            return None
        return local_selection_to_union(QRect(self.startPoint, self.endPoint).normalized(), self.unionOffset)

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
        QApplication.restoreOverrideCursor()

        # now that seleciton finished we either have both coords
        # or operation was cancelled by user

        rect = self.selectionUnionRect()
        img = None
        if rect is not None:
            if self.frozen is not None:
                # Test seam: the controller's Linux path crops via
                # _wait_for_frozen_selection instead; this branch serves direct
                # single-window use (and the unit tests).
                img = crop_selection(self.frozen, rect)
            else:
                # Live capture (Windows/macOS): PIL.ImageGrab
                # ImageGrab.grab() takes a tuple of (left, top, right, bottom)
                bbox = (
                    rect.x(),
                    rect.y(),
                    rect.x() + rect.width(),
                    rect.y() + rect.height()
                )
                screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
                
                # Convert to numpy array (OpenCV format)
                img = np.array(screenshot)
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        self.reset_state()
        return img # np.array image in BGR or None