import re
import secrets

import cv2
import numpy as np
import pytest
from PIL import Image

from PyQt6 import QtDBus
from PyQt6.QtCore import QEventLoop, QMetaType, QObject, QRect, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap, qRgb

from App import capture


def _expected_bgr(w, h):
    """BGR equivalent of pattern pixel(x,y) RGB = (x%256, (y*5)%256, 128)."""
    xs = np.arange(w, dtype=np.int64)[None, :]
    ys = np.arange(h, dtype=np.int64)[:, None]
    r = np.broadcast_to(xs % 256, (h, w))
    g = np.broadcast_to((ys * 5) % 256, (h, w))
    b = np.full((h, w), 128, dtype=np.int64)
    return np.stack([b, g, r], axis=-1).astype(np.uint8)


def _fill_rgb888(w, h):
    img = QImage(w, h, QImage.Format.Format_RGB888)
    for y in range(h):
        for x in range(w):
            img.setPixel(x, y, qRgb(x % 256, (y * 5) % 256, 128))
    return img


def _solid_rgb888(w, h, rgb):
    img = QImage(w, h, QImage.Format.Format_RGB888)
    img.fill(qRgb(*rgb))
    return img


class TestQImageToBgrArray:
    def test_padded_odd_width_exact(self, qapp):
        img = _fill_rgb888(101, 50)
        # 101*3 = 303, QImage rows are 4-byte aligned -> bpl 304. Assert the
        # precondition so the test can't silently degrade to the fast branch.
        assert img.bytesPerLine() > 101 * 3
        result = capture.qimage_to_bgr_array(img)
        assert result.shape == (50, 101, 3)
        assert result.dtype == np.uint8
        np.testing.assert_array_equal(result, _expected_bgr(101, 50))

    def test_unpadded_width_exact_fast_branch(self, qapp):
        img = _fill_rgb888(100, 50)
        assert img.bytesPerLine() == 100 * 3
        result = capture.qimage_to_bgr_array(img)
        assert result.shape == (50, 100, 3)
        assert result.dtype == np.uint8
        np.testing.assert_array_equal(result, _expected_bgr(100, 50))

    def test_null_image_raises(self):
        with pytest.raises(capture.CaptureError, match="null QImage"):
            capture.qimage_to_bgr_array(QImage())


class TestGetCaptureBackend:
    def test_wayland_takes_precedence_even_with_x11(self, monkeypatch):
        monkeypatch.setattr(capture, "is_wayland", lambda: True)
        monkeypatch.setattr(capture, "is_x11", lambda: True)
        assert isinstance(capture.get_capture_backend(), capture.PortalBackend)

    def test_x11_uses_qt_grab(self, monkeypatch):
        monkeypatch.setattr(capture, "is_wayland", lambda: False)
        monkeypatch.setattr(capture, "is_x11", lambda: True)
        assert isinstance(capture.get_capture_backend(), capture.QtGrabBackend)

    def test_no_wayland_no_x11_uses_pillow(self, monkeypatch):
        monkeypatch.setattr(capture, "is_wayland", lambda: False)
        monkeypatch.setattr(capture, "is_x11", lambda: False)
        assert isinstance(capture.get_capture_backend(), capture.PillowBackend)


class TestCaptureFrozenScreen:
    def test_delegates_to_backend(self, monkeypatch):
        sentinel = capture.CapturedScreen(np.zeros((1, 1, 3), np.uint8), 1.0, 1.0)
        backend = capture.PillowBackend()
        monkeypatch.setattr(backend, "capture", lambda: sentinel)
        monkeypatch.setattr(capture, "get_capture_backend", lambda: backend)
        assert capture.capture_frozen_screen() is sentinel


class TestCropSelection:
    def _made(self):
        img = np.arange(200 * 400 * 3, dtype=np.uint8).reshape(200, 400, 3)
        return capture.CapturedScreen(img, 2.0, 1.0)

    def test_maps_logical_rect_with_scales(self):
        c = self._made()
        rect = QRect(10, 20, 50, 60)
        out = capture.crop_selection(c, rect)
        # x1=floor(10*2)=20, y1=floor(20*1)=20, x2=ceil(60*2)=120, y2=ceil(80)=80
        np.testing.assert_array_equal(out, c.image[20:80, 20:120])

    def test_clamps_rect_past_right_bottom_edges(self):
        c = self._made()
        rect = QRect(190, 180, 30, 40)  # sticks past width 400 / height 200 at (2.0, 1.0)
        out = capture.crop_selection(c, rect)
        # x1=380, x2=min(400, ceil(440))=400 ; y1=180, y2=min(200, 220)=200
        np.testing.assert_array_equal(out, c.image[180:200, 380:400])

    def test_clamps_negative_coords_to_zero(self):
        c = self._made()
        rect = QRect(-10, -5, 20, 20)
        out = capture.crop_selection(c, rect)
        # x1=max(0, floor(-20))=0, y1=max(0, -5)=0, x2=ceil(10*2)=20, y2=ceil(15)=15
        np.testing.assert_array_equal(out, c.image[0:15, 0:20])

    def test_fully_off_screen_rect_returns_none(self):
        c = self._made()
        rect = QRect(390, 0, 50, 10)  # x1=floor(780)=780 > image width 400
        assert capture.crop_selection(c, rect) is None

    def test_zero_size_rect_returns_none(self):
        c = self._made()
        rect = QRect(5, 5, 0, 0)
        assert capture.crop_selection(c, rect) is None

    def test_crop_is_a_copy(self):
        c = self._made()
        out = capture.crop_selection(c, QRect(10, 20, 50, 60))
        out[0, 0, 0] = 255
        assert c.image[20, 20, 0] != 255


class TestPillowBackend:
    def _fake_grab(self, error=None):
        class FakeImageGrab:
            def __init__(self):
                self.calls = []
            def grab(self, **kwargs):
                self.calls.append(kwargs)
                if error is not None:
                    raise error
                return Image.new("RGB", (320, 240), (10, 20, 30))
        return FakeImageGrab()

    def test_happy_path_scales_and_bgr(self, monkeypatch, qapp):
        fake = self._fake_grab()
        monkeypatch.setattr(capture, "ImageGrab", fake)
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect(0, 0, 160, 120))
        result = capture.PillowBackend().capture()
        assert result.image.shape == (240, 320, 3)
        assert result.image.dtype == np.uint8
        np.testing.assert_array_equal(result.image, np.full((240, 320, 3), (30, 20, 10), np.uint8))
        assert result.scale_x == 2.0
        assert result.scale_y == 2.0
        kwargs = fake.calls[0]
        assert "bbox" not in kwargs
        assert kwargs.get("all_screens") is True

    def test_grab_exception_wrapped(self, monkeypatch, qapp):
        fake = self._fake_grab(error=RuntimeError("boom"))
        monkeypatch.setattr(capture, "ImageGrab", fake)
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect(0, 0, 160, 120))
        with pytest.raises(capture.CaptureError, match="screen grab failed: boom"):
            capture.PillowBackend().capture()

    def test_no_screens_raises(self, monkeypatch, qapp):
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect())
        with pytest.raises(capture.CaptureError, match="no screens detected"):
            capture.PillowBackend().capture()


class _FakeScreen:
    def __init__(self, geometry, dpr=1.0, name="FakeScreen", pixmap=None):
        self._geometry = geometry
        self._dpr = dpr
        self._name = name
        self._pixmap = pixmap

    def geometry(self):
        return self._geometry

    def devicePixelRatio(self):
        return self._dpr

    def name(self):
        return self._name

    def grabWindow(self, window):
        return self._pixmap


class TestQtGrabBackend:
    def test_failed_grab_raises(self, qapp, monkeypatch):
        screen = _FakeScreen(QRect(0, 0, 100, 80), pixmap=QPixmap())  # null pixmap
        backend = capture.QtGrabBackend()
        monkeypatch.setattr(backend, "_screens", lambda: [screen])
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect(0, 0, 100, 80))
        with pytest.raises(capture.CaptureError, match="failed to grab screen 'FakeScreen'"):
            backend.capture()

    def test_no_screens_raises(self, qapp, monkeypatch):
        backend = capture.QtGrabBackend()
        monkeypatch.setattr(backend, "_screens", lambda: [])
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect())
        with pytest.raises(capture.CaptureError, match="no screens detected"):
            backend.capture()

    def test_composes_single_screen_exactly(self, qapp, monkeypatch):
        qimage = _fill_rgb888(100, 80)
        screen = _FakeScreen(QRect(0, 0, 100, 80), pixmap=QPixmap.fromImage(qimage))
        backend = capture.QtGrabBackend()
        monkeypatch.setattr(backend, "_screens", lambda: [screen])
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect(0, 0, 100, 80))
        result = backend.capture()
        assert result.scale_x == 1.0
        assert result.scale_y == 1.0
        np.testing.assert_array_equal(result.image, capture.qimage_to_bgr_array(qimage))

    def test_qtgrab_composes_negative_origin_screens(self, qapp, monkeypatch):
        screen_a = _FakeScreen(QRect(-1920, 0, 1920, 1080), name="A",
                               pixmap=QPixmap.fromImage(_solid_rgb888(1920, 1080, (255, 0, 0))))
        screen_b = _FakeScreen(QRect(0, 0, 1920, 1080), name="B",
                               pixmap=QPixmap.fromImage(_solid_rgb888(1920, 1080, (0, 255, 0))))
        backend = capture.QtGrabBackend()
        monkeypatch.setattr(backend, "_screens", lambda: [screen_a, screen_b])
        monkeypatch.setattr(capture, "union_screen_geometry", lambda: QRect(-1920, 0, 3840, 1080))
        result = backend.capture()
        # Screen A sits left of the origin: the canvas is translated by union.topLeft().
        assert result.image.shape == (1080, 3840, 3)
        assert result.scale_x == 1.0
        assert result.scale_y == 1.0
        np.testing.assert_array_equal(result.image[:, :1920, :], np.full((1080, 1920, 3), (0, 0, 255), np.uint8))
        np.testing.assert_array_equal(result.image[:, 1920:, :], np.full((1080, 1920, 3), (0, 255, 0), np.uint8))


# ---------------------------------------------------------------------------
# Fake QtDBus module: no real D-Bus anywhere. The backend subscribes to the
# request path before calling, so the fake's `connect` records the callback;
# fire_first() replays the portal's async Response signal deferred via
# QTimer.singleShot(0, ...) so it lands inside PortalBackend's QEventLoop.
# The fake interface's default reply is the object path of the first
# subscribed request, which equals the path the backend derived.
# ---------------------------------------------------------------------------
class FakeMessageType:
    ReplyMessage = 1
    ErrorMessage = 2
    NoMessage = 3


class FakeReplyMessage:
    def __init__(self, msg_type, arguments=(), error_message=""):
        self._type = msg_type
        self._arguments = list(arguments)
        self._error_message = error_message

    def type(self):
        return self._type

    def arguments(self):
        return self._arguments

    def errorMessage(self):
        return self._error_message


class FakeQDBusVariant:
    def __init__(self, value):
        self.value = value


class FakeQDBusConnection:
    session_instance = None

    def __init__(self, connected=True, base_service=":1.42"):
        self.connected_flag = connected
        self.base_service_name = base_service
        self.subscribed = []
        self.callbacks = []
        self.disconnected = []
        self.autofire = None
        self.connect_result = True

    @classmethod
    def sessionBus(cls):
        return cls.session_instance

    def isConnected(self):
        return self.connected_flag

    def baseService(self):
        return self.base_service_name

    def connect(self, service, path, interface, signal_name, callback):
        self.subscribed.append((service, path, interface, signal_name))
        self.callbacks.append(callback)
        if self.autofire is not None:
            # Deferred via the event loop so it lands inside the backend's
            # QEventLoop.exec() — never synchronously (that would deadlock).
            code, results = self.autofire
            self.autofire = None
            QTimer.singleShot(0, lambda: callback(code, results))
        return self.connect_result

    def disconnect(self, service, path, interface, signal_name, callback):
        self.disconnected.append((service, path, interface, signal_name, callback))

    def fire_first(self, code, results):
        self.autofire = (code, results)


class FakeQDBusInterface:
    reply_override = None
    instances = []

    def __init__(self, service, path, interface, bus):
        self.service = service
        self.path = path
        self.interface = interface
        self.bus = bus
        self.calls = []
        FakeQDBusInterface.instances.append(self)

    def call(self, method, *args):
        self.calls.append((method, args))
        if FakeQDBusInterface.reply_override is not None:
            reply = FakeQDBusInterface.reply_override
            FakeQDBusInterface.reply_override = None
            return reply
        if self.bus.subscribed:
            # Default: reply carries the request object path the backend derived.
            return FakeReplyMessage(FakeMessageType.ReplyMessage, [self.bus.subscribed[0][1]])
        return FakeReplyMessage(FakeMessageType.ReplyMessage, [])


class FakeQtDBus:
    QDBusConnection = FakeQDBusConnection
    QDBusInterface = FakeQDBusInterface
    QDBusVariant = FakeQDBusVariant

    class QDBusMessage:
        MessageType = FakeMessageType


@pytest.fixture
def qtdbus(monkeypatch):
    FakeQDBusInterface.reply_override = None
    FakeQDBusInterface.instances = []
    conn = FakeQDBusConnection()
    FakeQDBusConnection.session_instance = conn
    monkeypatch.setattr(capture, "QtDBus", FakeQtDBus)
    return conn


class TestPortalBackend:
    def test_happy_path_returns_image_and_deletes_temp(self, qtdbus, qtbot, tmp_path):
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((16, 32, 3), (30, 20, 10), np.uint8))  # imwrite takes BGR
        qtdbus.fire_first(0, {"uri": png.as_uri()})
        backend = capture.PortalBackend()
        result = backend.capture()
        assert result.image.shape == (16, 32, 3)
        np.testing.assert_array_equal(result.image, np.full((16, 32, 3), (30, 20, 10), np.uint8))
        assert not png.exists()

    def test_denial_raises(self, qtdbus, qtbot, tmp_path):
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((8, 8, 3), 0, np.uint8))
        qtdbus.fire_first(1, {"uri": png.as_uri()})
        with pytest.raises(capture.CaptureError, match="denied"):
            capture.PortalBackend().capture()

    def test_timeout_raises(self, qtdbus, qtbot):
        backend = capture.PortalBackend()
        backend.timeout_ms = 100  # callback never fired
        with pytest.raises(capture.CaptureError, match="timed out"):
            backend.capture()

    def test_dbus_error_reply_raises(self, qtdbus, qtbot):
        FakeQDBusInterface.reply_override = FakeReplyMessage(
            FakeMessageType.ErrorMessage, error_message="portal exploded")
        with pytest.raises(capture.CaptureError, match="portal exploded"):
            capture.PortalBackend().capture()

    def test_session_bus_not_connected_raises(self, qtdbus):
        qtdbus.connected_flag = False
        with pytest.raises(capture.CaptureError, match="session bus"):
            capture.PortalBackend().capture()

    def test_subscribe_failure_raises(self, qtdbus):
        qtdbus.connect_result = False
        with pytest.raises(capture.CaptureError, match="Failed to subscribe to portal response"):
            capture.PortalBackend().capture()

    def test_screenshot_call_uses_portal_interface(self, qtdbus, qtbot, tmp_path):
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((8, 8, 3), 0, np.uint8))
        qtdbus.fire_first(0, {"uri": png.as_uri()})
        capture.PortalBackend().capture()
        iface = FakeQDBusInterface.instances[-1]
        method, args = iface.calls[0]
        assert method == "Screenshot"
        assert args[0] == ""
        options = args[1]
        assert isinstance(options["handle_token"], str)
        assert options["handle_token"].startswith("kawaii_translator_")
        assert options["interactive"] is False

    def test_screenshot_options_raw_values(self, qtdbus, qtbot, tmp_path):
        # Raw values, NOT QDBusVariant-wrapped: PyQt6 auto-wraps dict values
        # exactly once when marshalling a{sv}; an explicit QDBusVariant gets
        # double-wrapped (v(v)) and the real portal rejects the call with
        # "Expected type 'b' for option 'interactive', got 'v'".
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((8, 8, 3), 0, np.uint8))
        qtdbus.fire_first(0, {"uri": png.as_uri()})
        capture.PortalBackend().capture()
        method, args = FakeQDBusInterface.instances[-1].calls[0]
        assert method == "Screenshot"
        assert args[0] == "" and isinstance(args[0], str)
        options = args[1]
        assert options  # non-empty
        assert all(not isinstance(v, FakeQDBusVariant) for v in options.values())
        assert options["interactive"] is False
        assert isinstance(options["handle_token"], str)
        assert options["handle_token"].startswith("kawaii_translator_")

    def test_portal_request_path_derivation_is_spec_compliant(self, qtdbus, qtbot, tmp_path):
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((16, 32, 3), (30, 20, 10), np.uint8))
        qtdbus.fire_first(0, {"uri": png.as_uri()})
        result = capture.PortalBackend().capture()
        assert result.image.shape == (16, 32, 3)

        # The fake's default reply echoes the pre-subscribed (derived) request
        # path, so a correct derivation yields exactly one subscription on it;
        # any mismatched sender-mangling would fail the assertions below.
        assert len(qtdbus.subscribed) == 1
        service, path, interface, signal_name = qtdbus.subscribed[0]
        assert service == "org.freedesktop.portal.Desktop"
        assert interface == "org.freedesktop.portal.Request"
        assert signal_name == "Response"
        prefix = "/org/freedesktop/portal/desktop/request/1_42/kawaii_translator_"
        assert path.startswith(prefix)
        assert re.fullmatch(r"[A-Za-z0-9_]+", path[len(prefix):])

    def test_portal_resubscribes_when_reply_path_differs(self, qtdbus, qtbot, tmp_path):
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((16, 32, 3), (30, 20, 10), np.uint8))
        other_path = "/org/freedesktop/portal/desktop/request/1_42/kawaii_translator_OTHER"
        FakeQDBusInterface.reply_override = FakeReplyMessage(FakeMessageType.ReplyMessage, [other_path])
        qtdbus.fire_first(0, {"uri": png.as_uri()})
        result = capture.PortalBackend().capture()
        assert result.image.shape == (16, 32, 3)
        assert len(qtdbus.subscribed) == 2
        assert len(qtdbus.disconnected) == 2
        assert qtdbus.subscribed[1][1] == other_path
        assert qtdbus.disconnected[1][1] == other_path

    def test_portal_imread_failure_deletes_temp_file_and_raises(self, qtdbus, qtbot, tmp_path):
        path = tmp_path / "shot.png"
        path.write_bytes(b"not a png")
        qtdbus.fire_first(0, {"uri": path.as_uri()})
        with pytest.raises(capture.CaptureError):
            capture.PortalBackend().capture()
        assert not path.exists()

    def test_portal_uri_with_spaces_is_decoded(self, qtdbus, qtbot, tmp_path):
        png = tmp_path / "my shot.png"
        cv2.imwrite(str(png), np.full((16, 32, 3), (30, 20, 10), np.uint8))
        uri = png.as_uri()  # percent-encodes the space as %20
        assert "%20" in uri
        qtdbus.fire_first(0, {"uri": uri})
        result = capture.PortalBackend().capture()
        assert result.image.shape == (16, 32, 3)
        np.testing.assert_array_equal(result.image, np.full((16, 32, 3), (30, 20, 10), np.uint8))
        assert not png.exists()

    def test_subscribed_callback_is_pyqtslot_watcher_method(self, qtdbus, qtbot, tmp_path):
        # Bus-independent pin of the QtDBus contract: QDBusConnection.connect()
        # only accepts pyqtSlot-decorated bound methods of a QObject; a plain
        # closure/lambda crashes live. Guard CI runs that have no session bus
        # (where TestPortalBackendRealBus is skipped) against reintroducing one.
        png = tmp_path / "shot.png"
        cv2.imwrite(str(png), np.full((8, 8, 3), 0, np.uint8))
        qtdbus.fire_first(0, {"uri": png.as_uri()})
        capture.PortalBackend().capture()
        assert qtdbus.callbacks, "backend must subscribe"
        for cb in qtdbus.callbacks:
            assert isinstance(cb.__self__, QObject), "callback must be a bound method of a QObject instance"
            assert cb.__name__ == "on_response", "callback must be the watcher slot, not a closure"
            assert hasattr(type(cb.__self__), "on_response"), "slot must live on the watcher class"
        # disconnect must reference the same bound slot that was connected
        assert len(qtdbus.disconnected) == len(qtdbus.subscribed)
        for cb, disc in zip(qtdbus.callbacks, qtdbus.disconnected):
            assert disc[4] == cb

    def test_response_slot_declares_uint(self):
        # Pins the @pyqtSlot("uint", "QVariantMap") decorator so a revert to
        # "int" fails fast in CI without needing a session bus: the portal's
        # Response signal is (ua{sv}), and an int-declared slot would silently
        # drop every real response (the silent-drop bug this fixes).
        found = False
        mo = capture._PortalWatcher.staticMetaObject
        for i in range(mo.methodCount()):
            method = mo.method(i)
            if method.name() == b"on_response":
                assert method.parameterTypes()[0] == b"uint"
                found = True
                break
        assert found, "on_response slot not found in _PortalWatcher meta object"


def _session_bus_connected():
    # Hedge against Qt/QtDBus crashing (rather than returning not-connected)
    # when the session bus environment is empty, so the skip guard is safe.
    try:
        return QtDBus.QDBusConnection.sessionBus().isConnected()
    except Exception:
        return False


@pytest.mark.skipif(not _session_bus_connected(), reason="no session bus")
class TestPortalBackendRealBus:
    def test_synthetic_portal_response_roundtrip(self, qapp):
        bus = QtDBus.QDBusConnection.sessionBus()
        sender = bus.baseService()
        sender_part = sender[1:].replace(".", "_")
        token = "kawaii_translator_test_" + secrets.token_hex(8)
        request_path = f"/org/freedesktop/portal/desktop/request/{sender_part}/{token}"

        backend = capture.PortalBackend()
        backend._response = None
        backend._loop = QEventLoop()

        # We subscribe with our own unique name (bus.baseService()) instead of
        # the portal's well-known name "org.freedesktop.portal.Desktop" because
        # we cannot emit D-Bus signals as the portal without owning that name.
        # QtDBus's match rule matches our own unique name, and the subscribe
        # mechanism itself (real bus, no mocks) is exactly what capture() uses.
        watcher = backend._subscribe_response(bus, sender, request_path)
        disconnected = None
        try:
            msg = QtDBus.QDBusMessage.createSignal(
                request_path, "org.freedesktop.portal.Request", "Response")
            # The first argument is deliberately marshalled as a true D-Bus
            # uint32 ('u'): the portal's Response signal is (ua{sv}) and the
            # slot is declared "uint". A Python int would marshal as INT32 and
            # be silently dropped by the uint slot — this test is the
            # regression pin for the silent-drop bug (if the slot is reverted
            # to int, this test fails by timing out). QMetaType.Type.UInt is
            # an enum that QDBusArgument.add() rejects, so .value (the plain
            # int id) is passed. The raw dict marshals as a{sv} with each
            # value auto-wrapped in a variant by PyQt6; they arrive
            # pre-unwrapped (plain str) in the slot.
            code_arg = QtDBus.QDBusArgument()
            code_arg.add(0, QMetaType.Type.UInt.value)
            msg.setArguments([code_arg, {"uri": "file:///tmp/fake.png"}])
            bus.send(msg)
            QTimer.singleShot(5000, backend._loop.quit)
            backend._loop.exec()

            # _response is not None distinguishes a real delivery from the 5s
            # timeout guard firing.
            assert backend._response is not None
            code, results = backend._response
            assert code == 0
            assert results == {"uri": "file:///tmp/fake.png"}
            assert isinstance(results.get("uri"), str)
            assert QUrl(results["uri"]).toLocalFile() == "/tmp/fake.png"
        finally:
            disconnected = bus.disconnect(sender, request_path,
                                          "org.freedesktop.portal.Request",
                                          "Response", watcher.on_response)
        assert disconnected is True

    def test_connect_rejects_plain_callable(self, qapp):
        bus = QtDBus.QDBusConnection.sessionBus()
        # Pins the PyQt6 QtDBus contract: connect() rejects plain callables that
        # are not pyqtSlot-decorated QObject methods. The original live crash
        # was: "TypeError: callable must be a method of a QtCore.QObject
        # instance decorated by QtCore.pyqtSlot".
        try:
            ok = bus.connect(bus.baseService(), "/org/kawaii/contract",
                             "org.kawaii.Test", "Response",
                             lambda code, results: None)
        except TypeError:
            pass
        else:
            assert ok is False

    def test_screenshot_options_vardict_bool_not_variant_on_wire(self, qapp):
        # Real-bus round-trip smoke test of the exact raw-form call
        # construction the backend now uses: QDBusInterface.call("Screenshot",
        # "", {"interactive": False, "handle_token": str}) -> registered object
        # -> QVariantMap slot -> native bool/str. Passing proves the call is
        # well-formed enough to be delivered, invoked, and replied to on the
        # real session bus. Honest caveat: a QVariantMap-typed receiver
        # normalizes raw and QDBusVariant-wrapped dict values identically, so
        # this seam cannot discriminate a wire 'b' from a nested 'v' either
        # way. The real pin is TestPortalBackend.test_screenshot_options_raw_values
        # (fake seam, asserts no QDBusVariant wrapping reaches the call) plus
        # the live-portal verification that the raw form is accepted while the
        # QDBusVariant form is rejected with "Expected type 'b' for option
        # 'interactive', got 'v'".
        class FakePortal(QObject):
            def __init__(self):
                super().__init__()
                self.received = None

            @pyqtSlot(str, "QVariantMap", result=str)
            def Screenshot(self, parent_window, options):
                self.received = (parent_window, dict(options))
                return "/fake/request"

        bus = QtDBus.QDBusConnection.sessionBus()
        path = f"/org/kawaiitranslator/test/portal_{secrets.token_hex(8)}"
        obj = FakePortal()
        ok = bus.registerObject(path, "org.kawaiitranslator.TestPortal", obj,
                                QtDBus.QDBusConnection.RegisterOption.ExportAllSlots)
        assert ok, "failed to register test portal object"
        try:
            options = {"interactive": False,
                       "handle_token": "kawaii_translator_test_" + secrets.token_hex(8)}
            iface = QtDBus.QDBusInterface(bus.baseService(), path,
                                          "org.kawaiitranslator.TestPortal", bus)
            iface.setTimeout(5000)
            reply = iface.call("Screenshot", "", options)
            assert reply.type() == QtDBus.QDBusMessage.MessageType.ReplyMessage, \
                f"call failed: {reply.errorMessage()}"
            assert obj.received is not None, "registered Screenshot slot never invoked"
            assert obj.received[0] == ""
            opts = obj.received[1]
            assert isinstance(opts["interactive"], bool) and opts["interactive"] is False
            assert isinstance(opts["handle_token"], str)
            assert opts["handle_token"].startswith("kawaii_translator_test_")
        finally:
            bus.unregisterObject(path)