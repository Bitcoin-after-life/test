"""
Tests for the BASIC-mode calendar reminders.

Context: in BASIC mode the check-alive parameter is hidden and not managed by
the user, so calendar reminders cannot be spread over the check-alive period as
they are in ADVANCED mode. Instead the calendar uses three fixed reminders -
30, 10 and 1 day before the inheritance delivery date - and drops any reminder
that would fall in the past.

These tests pin the behaviour of the pure helper ``basic_reminder_offsets`` that
drives that decision.

``basic_reminder_offsets`` lives in ``bal.gui.qt.widgets`` (which imports
PyQt6), so these tests are run headless with ``QT_QPA_PLATFORM=offscreen`` like
the other GUI tests.

Run:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src \
        python3 -m pytest tests/test_group_g_basic_calendar.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.gui.qt.widgets import (BASIC_REMINDER_OFFSETS,
                                 basic_reminder_offsets)


def test_basic_offsets_all_future():
    """A far delivery date keeps all three fixed reminders (30, 10, 1)."""
    assert basic_reminder_offsets(365) == [30, 10, 1]


def test_basic_offsets_exactly_30_days():
    """Exactly 30 days away: the 30-day reminder is still valid (<=)."""
    assert basic_reminder_offsets(30) == [30, 10, 1]


def test_basic_offsets_drops_30_when_too_close():
    """20 days away: the 30-day reminder is in the past and is dropped."""
    assert basic_reminder_offsets(20) == [10, 1]


def test_basic_offsets_only_one_left():
    """5 days away: only the 1-day reminder remains."""
    assert basic_reminder_offsets(5) == [1]


def test_basic_offsets_empty_when_deadline_today():
    """Delivery date less than a day away: no reminder fits."""
    assert basic_reminder_offsets(0) == []


def test_basic_offsets_empty_when_negative():
    """A past delivery date (negative days) yields no reminders."""
    assert basic_reminder_offsets(-10) == []


def test_basic_offsets_are_a_subset_of_the_fixed_set():
    """Whatever the horizon, results are always a subset of the fixed offsets."""
    for horizon in (-1, 0, 1, 9, 10, 11, 29, 30, 100):
        result = basic_reminder_offsets(horizon)
        assert set(result).issubset(set(BASIC_REMINDER_OFFSETS))
        # Always sorted descending (earliest reminder first) and every offset >= 1.
        assert result == sorted(result, reverse=True)
        assert all(off >= 1 for off in result)


if __name__ == "__main__":
    test_basic_offsets_all_future()
    test_basic_offsets_exactly_30_days()
    test_basic_offsets_drops_30_when_too_close()
    test_basic_offsets_only_one_left()
    test_basic_offsets_empty_when_deadline_today()
    test_basic_offsets_empty_when_negative()
    test_basic_offsets_are_a_subset_of_the_fixed_set()
    print("all BASIC calendar reminder tests passed")
