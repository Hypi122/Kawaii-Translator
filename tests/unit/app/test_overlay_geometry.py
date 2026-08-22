import numpy as np

from PyQt6.QtCore import QPoint, QRect, QSize

from App.capture import CapturedScreen, crop_selection
from App.overlay_geometry import (
    local_selection_to_union,
    screen_image_slice,
    screen_origin_in_union,
)


def _gradient_img(h, w):
    """Per-pixel pattern image (BGR): B=x, G=y, R=77. uint8 wraps, which is fine."""
    yy, xx = np.indices((h, w), dtype=np.uint8)
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = xx
    img[..., 1] = yy
    img[..., 2] = 77
    return img


def test_slice_screen_at_2560_0_in_4480x1440_union():
    union = QRect(0, 0, 4480, 1440)
    screen_a = QRect(0, 0, 2560, 1440)
    screen_b = QRect(2560, 0, 1920, 1440)

    assert screen_image_slice(screen_a, union, QSize(4480, 1440), 1.0, 1.0) == QRect(0, 0, 2560, 1440)
    assert screen_image_slice(screen_b, union, QSize(4480, 1440), 1.0, 1.0) == QRect(2560, 0, 1920, 1440)

    assert screen_image_slice(screen_a, union, QSize(8960, 2880), 2.0, 2.0) == QRect(0, 0, 5120, 2880)
    assert screen_image_slice(screen_b, union, QSize(8960, 2880), 2.0, 2.0) == QRect(5120, 0, 3840, 2880)


def test_slice_partially_outside_image_is_clamped():
    union = QRect(0, 0, 4480, 1440)
    screen = QRect(2560, 0, 1920, 1440)
    assert screen_image_slice(screen, union, QSize(3000, 1000), 1.0, 1.0) == QRect(2560, 0, 440, 1000)


def test_slice_negative_origin_layout():
    union = QRect(-1920, 0, 4480, 1440)
    screen_a = QRect(-1920, 0, 1920, 1440)
    screen_b = QRect(0, 0, 2560, 1440)

    assert screen_origin_in_union(screen_a, union) == QPoint(0, 0)
    assert screen_origin_in_union(screen_b, union) == QPoint(1920, 0)

    assert screen_image_slice(screen_a, union, QSize(4480, 1440), 1.0, 1.0) == QRect(0, 0, 1920, 1440)
    assert screen_image_slice(screen_b, union, QSize(4480, 1440), 1.0, 1.0) == QRect(1920, 0, 2560, 1440)


def test_slice_fully_outside_image_is_empty():
    union = QRect(0, 0, 4480, 1440)
    screen = QRect(5000, 0, 100, 100)
    assert screen_image_slice(screen, union, QSize(3000, 1000), 1.0, 1.0).isEmpty() is True


def test_local_to_union_then_crop_exact_pixels():
    union = QRect(-1920, 0, 4480, 1440)
    screen_b = QRect(0, 0, 2560, 1440)
    screen_a = QRect(-1920, 0, 1920, 1440)
    img = _gradient_img(1440, 4480)
    captured = CapturedScreen(img, scale_x=1.0, scale_y=1.0)
    local = QRect(10, 20, 100, 50)

    lifted = local_selection_to_union(local, screen_origin_in_union(screen_b, union))
    assert lifted == QRect(1930, 20, 100, 50)
    cropped = crop_selection(captured, lifted)
    assert cropped is not None
    assert cropped.shape == (50, 100, 3)
    np.testing.assert_array_equal(cropped[0, 0], np.array([1930, 20, 77]).astype(np.uint8))
    np.testing.assert_array_equal(cropped[-1, -1], np.array([2029, 69, 77]).astype(np.uint8))

    lifted_a = local_selection_to_union(local, screen_origin_in_union(screen_a, union))
    assert lifted_a == QRect(10, 20, 100, 50)
    cropped_a = crop_selection(captured, lifted_a)
    assert cropped_a is not None
    np.testing.assert_array_equal(cropped_a, img[20:70, 10:110])


def test_crop_floor_ceil_with_fractional_scale():
    union = QRect(0, 0, 100, 100)
    screen = QRect(0, 0, 100, 100)
    img = _gradient_img(150, 150)
    captured = CapturedScreen(img, scale_x=1.5, scale_y=1.5)
    local = QRect(3, 0, 5, 10)

    lifted = local_selection_to_union(local, screen_origin_in_union(screen, union))
    assert lifted == QRect(3, 0, 5, 10)

    cropped = crop_selection(captured, lifted)
    assert cropped is not None
    # x1=floor(3*1.5)=4, y1=floor(0*1.5)=0, x2=ceil(8*1.5)=12, y2=ceil(10*1.5)=15.
    assert cropped.shape == (15, 8, 3)
    np.testing.assert_array_equal(cropped, img[0:15, 4:12])
    np.testing.assert_array_equal(cropped[0, 0], np.array([4, 0, 77], dtype=np.uint8))