"""
Screen capture backends with a uniform frozen-frame API.

Backends:
  - PortalBackend:  Wayland via xdg-desktop-portal (org.freedesktop.portal.Screenshot over D-Bus)
  - QtGrabBackend:  X11 via QScreen.grabWindow
  - PillowBackend:  Windows / macOS / fallback via PIL.ImageGrab

Public API (pinned, used by the overlay, OCR pipeline and e2e tests):
  CaptureError, CapturedScreen, CaptureBackend, PortalBackend, QtGrabBackend,
  PillowBackend, get_capture_backend, capture_frozen_screen,
  qimage_to_bgr_array, crop_selection, union_screen_geometry
"""
from __future__ import annotations

import abc
import math
import secrets
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab

from PyQt6 import QtDBus
from PyQt6.QtCore import QUrl, QRect, QEventLoop, QTimer, QObject, pyqtSlot
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from Util.platform import is_wayland, is_x11


class CaptureError(Exception):
    pass


@dataclass
class CapturedScreen:
    image: np.ndarray   # full-desktop frozen image, BGR, uint8, (H, W, 3)
    scale_x: float      # image_width  / union_of_screens_logical_width
    scale_y: float      # image_height / union_of_screens_logical_height


class CaptureBackend(abc.ABC):
    @abc.abstractmethod
    def capture(self) -> CapturedScreen:
        pass


def get_capture_backend() -> CaptureBackend:
    # Wayland takes precedence even if DISPLAY is also set (XWayland quirk).
    if is_wayland():
        return PortalBackend()
    if is_x11():
        return QtGrabBackend()
    return PillowBackend()


def capture_frozen_screen() -> CapturedScreen:
    return get_capture_backend().capture()


def union_screen_geometry() -> QRect:
    # The overlay (screenshot.py) uses this same union rect for its geometry; start_selection() re-syncs to it before each capture.
    rect = QRect()
    for screen in QApplication.screens():
        rect = rect.united(screen.geometry())
    return rect


def qimage_to_bgr_array(image: QImage) -> np.ndarray:
    if image.isNull():
        raise CaptureError("null QImage")
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    if bpl < w * 3:
        raise CaptureError("QImage row stride smaller than width*3")

    # Stride pitfall: QImage rows are 4-byte aligned, so bytesPerLine() can be
    # larger than w*3 (e.g. width 101 -> bpl 304). constBits() exposes the raw
    # backing buffer; in PyQt6 it is a sip.voidptr whose length is unknown until
    # setsize() is called with the true buffer size (some versions return a
    # memoryview that may need the same treatment).
    buf = img.constBits()
    if hasattr(buf, "setsize"):
        buf.setsize(img.sizeInBytes())
    buf = bytes(buf)

    if bpl == w * 3:
        # Unpadded fast path: the whole buffer is one contiguous RGB row block.
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
    else:
        # Padded: copy row by row, dropping the trailing pad bytes.
        flat = np.frombuffer(buf, dtype=np.uint8).reshape(h, bpl)
        arr = np.empty((h, w, 3), dtype=np.uint8)
        for i in range(h):
            arr[i] = flat[i, : w * 3].reshape(w, 3)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def crop_selection(captured: CapturedScreen, rect: QRect) -> np.ndarray | None:
    # Map overlay-local logical coordinates to image pixels using the SAME
    # scales used when the frozen frame was built, so selection and crop stay
    # self-consistent. floor/ceil keeps the crop conservative (never loses a
    # partially covered pixel), clamps keep it inside the image.
    x1 = max(0, math.floor(rect.x() * captured.scale_x))
    y1 = max(0, math.floor(rect.y() * captured.scale_y))
    x2 = min(captured.image.shape[1], math.ceil((rect.x() + rect.width()) * captured.scale_x))
    y2 = min(captured.image.shape[0], math.ceil((rect.y() + rect.height()) * captured.scale_y))
    if x2 <= x1 or y2 <= y1:
        return None
    return captured.image[y1:y2, x1:x2].copy()


class PillowBackend(CaptureBackend):
    def capture(self):
        union = union_screen_geometry()
        if union.isEmpty():
            raise CaptureError("no screens detected")
        try:
            # NO bbox kwarg — bbox is the broken bit of ImageGrab on Linux.
            shot = ImageGrab.grab(all_screens=True)
        except Exception as e:
            raise CaptureError(f"screen grab failed: {e}") from e
        rgb = np.asarray(shot)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return CapturedScreen(bgr, bgr.shape[1] / union.width(), bgr.shape[0] / union.height())


class QtGrabBackend(CaptureBackend):
    # Kept as a method so tests can stub it.
    def _screens(self):
        return QApplication.screens()

    def capture(self):
        screens = self._screens()
        union = union_screen_geometry()
        if union.isEmpty():
            raise CaptureError("no screens detected")
        max_dpr = max((s.devicePixelRatio() for s in screens), default=1.0)
        canvas_w = round(union.width() * max_dpr)
        canvas_h = round(union.height() * max_dpr)
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

        for screen in screens:
            try:
                pm = screen.grabWindow(0)
                if pm.isNull():
                    raise CaptureError(f"failed to grab screen '{screen.name()}'")
                img = qimage_to_bgr_array(pm.toImage())

                # Screen rect in canvas coordinates (canvas is scaled by max_dpr).
                rel = screen.geometry().translated(-union.topLeft())
                x0 = round(rel.x() * max_dpr)
                y0 = round(rel.y() * max_dpr)
                tw = round(rel.width() * max_dpr)
                th = round(rel.height() * max_dpr)

                inter = cv2.INTER_AREA if (tw < img.shape[1] or th < img.shape[0]) else cv2.INTER_LINEAR
                resized = cv2.resize(img, (tw, th), interpolation=inter)

                # Clamp the paste ROI to the canvas: sx/sy >= 0 and ex/ey <=
                # canvas bounds, so slicing the resized image with indices
                # (sy-y0 .. ey-y0, sx-x0 .. ex-x0) never goes negative or out
                # of range.
                sx = max(0, x0)
                sy = max(0, y0)
                ex = min(canvas_w, x0 + tw)
                ey = min(canvas_h, y0 + th)
                if sx < ex and sy < ey:
                    canvas[sy:ey, sx:ex] = resized[sy - y0:ey - y0, sx - x0:ex - x0]
            except CaptureError:
                raise
            except Exception as e:
                raise CaptureError(f"failed to capture screen '{screen.name()}': {e}") from e

        # For uniform devicePixelRatio setups this composition is pixel-exact;
        # with mixed-DPR multi-monitor layouts it is approximate (each screen's
        # native pixels are rescaled to the max_dpr canvas). Acceptable
        # trade-off; the overlay crop uses the same scale factors, so selection
        # and crop stay self-consistent.
        return CapturedScreen(canvas, canvas_w / union.width(), canvas_h / union.height())


class _PortalWatcher(QObject):
    """Receives the portal's async Response(u, a{sv}) signal.

    QDBusConnection.connect() in PyQt6 only accepts pyqtSlot-decorated bound
    methods of a QObject — plain functions/lambdas raise TypeError.
    """

    def __init__(self, backend):
        super().__init__()
        self._backend = backend

    # The org.freedesktop.portal.Request::Response signal has D-Bus signature
    # (ua{sv}): the code arg is a uint32 and MUST be declared "uint" — an
    # int-declared slot connects fine but silently drops real portal responses
    # (the exact bug this fixes). "QVariantMap" is the C++ type name for a{sv};
    # verified accepted by PyQt6 6.11.0 at both class-creation and call time (a
    # Python dict argument marshals in without error).
    @pyqtSlot("uint", "QVariantMap")
    def on_response(self, code, results):
        try:
            results = dict(results)
        except Exception:
            results = None  # unreadable vardict — surfaced as an error after the loop
        self._backend._response = (code, results)
        self._backend._loop.quit()


class PortalBackend(CaptureBackend):
    # Timeout for the async xdg-desktop-portal roundtrip (ms).
    timeout_ms = 30_000

    def _subscribe_response(self, bus, service, path):
        """Connect _PortalWatcher.on_response to the portal Response signal.

        Returns the watcher; its bound slot MUST be given to the matching
        bus.disconnect call. Raises CaptureError if connect fails.
        """
        watcher = _PortalWatcher(self)
        ok = bus.connect(service, path, "org.freedesktop.portal.Request", "Response", watcher.on_response)
        if not ok:
            raise CaptureError(f"Failed to subscribe to portal response on {path}")
        return watcher

    def capture(self):
        # Pre-subscribed request path pattern: the reply of the Screenshot D-Bus
        # call is a request object path, and the actual result arrives
        # asynchronously as a Response(code, results) signal on that request.
        # The request path is deterministic: given the caller's unique bus name
        # and the "handle_token" option (which must be [A-Za-z0-9_] only) it is
        # /org/freedesktop/portal/desktop/request/<SENDER>/<TOKEN> with SENDER
        # being the unique name minus its leading ':' and '.' replaced by '_'.
        # Subscribing BEFORE the call removes the race where the portal would
        # reply before we connected (the spec-safe pattern).
        bus = QtDBus.QDBusConnection.sessionBus()
        if not bus.isConnected():
            raise CaptureError("D-Bus session bus unavailable; is xdg-desktop-portal installed and running?")

        token = "kawaii_translator_" + secrets.token_hex(8)
        sender = bus.baseService()  # e.g. ":1.42"
        sender_part = sender[1:].replace(".", "_") if sender else ""
        request_path = f"/org/freedesktop/portal/desktop/request/{sender_part}/{token}"

        self._response = None
        self._loop = QEventLoop()
        service = "org.freedesktop.portal.Desktop"
        subscriptions = []
        try:
            # Pre-subscribe (spec-safe, avoids the reply race).
            subscriptions.append((request_path, self._subscribe_response(bus, service, request_path)))

            iface = QtDBus.QDBusInterface(service, "/org/freedesktop/portal/desktop",
                                          "org.freedesktop.portal.Screenshot", bus)
            # Raw values on purpose: PyQt6 marshals a Python dict as a{sv} and
            # auto-wraps each value in a variant exactly once (v(b)/v(s)).
            # Explicit QDBusVariant values get double-wrapped (v(v(b))) and the
            # real portal rejects them with "Expected type 'b' for option
            # 'interactive', got 'v'". Verified against the live portal.
            options = {"interactive": False, "handle_token": token}
            reply = iface.call("Screenshot", "", options)
            if reply.type() == QtDBus.QDBusMessage.MessageType.ErrorMessage:
                raise CaptureError(f"portal Screenshot call failed: {reply.errorMessage()}")
            args = reply.arguments()
            if not args:
                raise CaptureError("portal returned malformed reply (no request handle)")
            reply_path = str(args[0])  # QDBusObjectPath -> str
            if reply_path and reply_path != request_path and reply_path not in [p for p, _ in subscriptions]:
                subscriptions.append((reply_path, self._subscribe_response(bus, service, reply_path)))  # belt-and-braces if portal used a different handle

            # Must integrate with the Qt loop (this runs on the GUI thread from a
            # slot); the nested QEventLoop keeps the UI processing events, and the
            # timeout ensures we never block forever.
            QTimer.singleShot(self.timeout_ms, self._loop.quit)
            self._loop.exec()
        finally:
            for p, watcher in subscriptions:
                bus.disconnect(service, p, "org.freedesktop.portal.Request", "Response", watcher.on_response)

        if self._response is None:
            raise CaptureError("screenshot portal timed out after 30s (no Response signal received)")
        code, results = self._response
        if results is None:  # unreadable vardict — surfaced here rather than dying in the dispatcher
            raise CaptureError("portal returned unreadable response results")
        if code != 0:
            raise CaptureError(f"screenshot request denied by portal (response code {code}) — the permission dialog may have been dismissed or denied")
        uri = results.get("uri", "")
        path = QUrl(str(uri)).toLocalFile()
        if not path:
            raise CaptureError(f"portal returned no usable screenshot URI: {uri!r}")
        try:
            img = cv2.imread(path)
        finally:
            Path(path).unlink(missing_ok=True)  # portal writes a temp file — always delete it
        if img is None:
            raise CaptureError(f"failed to load portal screenshot file: {path}")

        union = union_screen_geometry()
        if union.isEmpty():
            raise CaptureError("no screens detected")
        return CapturedScreen(img, img.shape[1] / union.width(), img.shape[0] / union.height())