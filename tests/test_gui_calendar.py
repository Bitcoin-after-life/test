"""
Tests for ``bal.gui.qt.calendar``.

Covers BalCalendar static methods: format_time, ical_escape, fold_ical_line,
write_temp_ics, open_with_default_app.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_gui_calendar.py
"""

import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from bal.gui.qt.calendar import BalCalendar


# ------------------------------------------------------------------ #
# format_time
# ------------------------------------------------------------------ #

def test_format_time_utc():
    dt = datetime(2025, 6, 1, 12, 30, 45, tzinfo=timezone.utc)
    assert BalCalendar.format_time(dt) == "20250601T123045Z"


def test_format_time_non_utc():
    from datetime import timedelta
    tz = timezone(timedelta(hours=2))
    dt = datetime(2025, 1, 15, 8, 0, 0, tzinfo=tz)
    result = BalCalendar.format_time(dt)
    assert result.endswith("Z")
    assert result == "20250115T060000Z"


# ------------------------------------------------------------------ #
# ical_escape
# ------------------------------------------------------------------ #

def test_ical_escape_no_change():
    text = "hello world"
    assert BalCalendar.ical_escape(text) == "hello world"


def test_ical_escape_backslash():
    assert BalCalendar.ical_escape("a\\b") == "a\\\\b"


def test_ical_escape_semicolon():
    assert BalCalendar.ical_escape("a;b") == "a\\;b"


def test_ical_escape_comma():
    assert BalCalendar.ical_escape("a,b") == "a\\,b"


def test_ical_escape_multiline():
    text = "line1\r\nline2"
    result = BalCalendar.ical_escape(text)
    assert "\r\n" in result
    assert "line1" in result
    assert "line2" in result


def test_ical_escape_all():
    text = "\\;,"
    assert BalCalendar.ical_escape(text) == "\\\\\\;\\,"


# ------------------------------------------------------------------ #
# fold_ical_line
# ------------------------------------------------------------------ #

def test_fold_ical_line_short():
    line = "SUMMARY:Test"
    assert BalCalendar.fold_ical_line(line) == "SUMMARY:Test"


def test_fold_ical_line_long():
    line = "X-LONG:" + "a" * 100
    result = BalCalendar.fold_ical_line(line, limit=75)
    parts = result.split("\r\n ")
    assert len(parts) > 1
    assert result.startswith("X-LONG:")


def test_fold_ical_line_unicode():
    line = "DESCRIPTION:" + "\u20ac" * 40
    result = BalCalendar.fold_ical_line(line, limit=75)
    assert "\r\n " in result
    assert "\u20ac" in result


# ------------------------------------------------------------------ #
# write_temp_ics
# ------------------------------------------------------------------ #

def test_write_temp_ics():
    content = "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
    path = BalCalendar.write_temp_ics(content)
    try:
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == content.encode("utf-8")
    finally:
        os.unlink(path)


def test_write_temp_ics_empty():
    path = BalCalendar.write_temp_ics("")
    try:
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == b""
    finally:
        os.unlink(path)


# ------------------------------------------------------------------ #
# open_with_default_app
# ------------------------------------------------------------------ #

def test_open_with_default_app_not_found():
    result = BalCalendar.open_with_default_app(
        "/nonexistent/calendar_app", "/tmp/fake.ics"
    )
    assert result is False


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All calendar tests passed")
