"""Pure geometry helpers for per-screen overlay windows (Linux freeze-first path).

Mapping uses the uniform-scale approximation already used by the capture
backends and crop_selection (image_px = union_logical_px * image_size /
union_size per axis); mixed-DPR multi-monitor setups remain approximate
(pre-existing, documented limitation).
"""

from PyQt6.QtCore import QPoint, QRect, QSize


def screen_origin_in_union(screen_geometry: QRect, union: QRect) -> QPoint:
    """Where a screen's top-left corner sits in union-logical coordinates
    (handles negative-origin layouts: union may start left of / above (0,0))."""
    return screen_geometry.topLeft() - union.topLeft()


def local_selection_to_union(local_rect: QRect, origin_in_union: QPoint) -> QRect:
    """Lift a window-local selection rect into union-logical coordinates by
    translating it by the screen's origin within the union."""
    return local_rect.translated(origin_in_union)


def screen_image_slice(screen_geometry: QRect, union: QRect, image_size: QSize,
                       scale_x: float, scale_y: float) -> QRect:
    """Sub-rect of the frozen full-desktop image (device px) that the overlay for
    `screen_geometry` should paint. Rounding (round()) mirrors QtGrabBackend's
    canvas composition in capture.py; the result is clamped (intersected) to the
    image bounds so screens partially outside the image (rounding, mixed-DPR)
    never yield an out-of-bounds source rect. Returns an empty QRect when the
    screen lies fully outside the image."""
    origin = screen_origin_in_union(screen_geometry, union)
    raw = QRect(round(origin.x() * scale_x),
                round(origin.y() * scale_y),
                round(screen_geometry.width() * scale_x),
                round(screen_geometry.height() * scale_y))
    return raw.intersected(QRect(0, 0, image_size.width(), image_size.height()))