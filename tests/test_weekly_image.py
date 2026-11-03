"""2026-11-04 (owner): the Friday channel picture (scraper/weekly_image.py)."""
from __future__ import annotations

import datetime as dt
import io

import pytest
from PIL import Image

import weekly_image

ROWS = [("תל אביב יפו", 7950), ("ירושלים", 5800), ("מודיעין מכבים רעות", 6100), ("חיפה", 3900)]


@pytest.mark.parametrize("raqm", [False, pytest.param(True, marks=pytest.mark.skipif(
    not weekly_image.use_raqm(), reason="Pillow has no RAQM here"))])
def test_the_picture_is_a_1080_by_1350_png_in_the_site_colours(raqm):
    png = weekly_image.render_weekly_png(ROWS, dt.date(2026, 10, 7), dt.date(2026, 11, 6), raqm=raqm)
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG" and image.size == (1080, 1350)
    assert image.getpixel((10, 10)) == (0xFB, 0xF7, 0xEF)  # cream


def test_hebrew_goes_right_to_left_without_raqm_numbers_stay_as_they_are():
    assert weekly_image._visual("חיפה") == "הפיח"
    assert weekly_image._visual("דירת 3 חדרים") == "םירדח 3 תריד"
    assert weekly_image._visual("7.10 עד 6.11.2026") == "6.11.2026 דע 7.10"
    assert weekly_image._visual("המחיר: ₪4,000") == "₪4,000 :ריחמה"
    assert weekly_image._visual("todira.app") == "todira.app"


def test_the_date_range_names_the_year_once_unless_it_changes():
    assert weekly_image.date_range(dt.date(2026, 10, 7), dt.date(2026, 11, 6)) == "7.10 עד 6.11.2026"
    assert weekly_image.date_range(dt.date(2026, 12, 5), dt.date(2027, 1, 4)) == "5.12.2026 עד 4.1.2027"


def test_no_rows_is_an_error_so_the_post_goes_out_as_text():
    with pytest.raises(ValueError):
        weekly_image.render_weekly_png([], dt.date(2026, 10, 7), dt.date(2026, 11, 6))


def test_the_font_and_its_licence_are_bundled():
    assert (weekly_image.FONTS / "Rubik-Bold.ttf").is_file() and (weekly_image.FONTS / "Rubik-Regular.ttf").is_file()
    assert "SIL Open Font License" in (weekly_image.FONTS / "OFL.txt").read_text()
