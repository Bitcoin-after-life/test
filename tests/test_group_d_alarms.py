"""
Tests for Group D / D1 (configurable, distributed calendar reminders).

Covered behaviour:

  * the persisted ``NUM_REMINDERS`` configuration key exists and defaults to 3,
    and can be changed and read back;
  * ``compute_reminder_offsets(days, count)`` spreads the reminders across the
    check-alive period, always BEFORE the deadline (every offset >= 1), uses at
    most one reminder per available day, and never returns more reminders than
    requested.

``compute_reminder_offsets`` lives in ``bal.gui.qt.widgets`` (which imports
PyQt6), so these tests are run headless with ``QT_QPA_PLATFORM=offscreen`` like
the other GUI tests.

Run:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src \
        python3 -m pytest tests/test_group_d_alarms.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.plugin_base import BalConfig
from bal.gui.qt.widgets import compute_reminder_offsets


# ------------------------------------------------------------------ #
# Mocks
# ------------------------------------------------------------------ #

class FakeConfig:
    """Minimal mock for Electrum's config object (key/value store)."""

    def __init__(self):
        self._store = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set_key(self, key, value, save=True):
        self._store[key] = value


# ------------------------------------------------------------------ #
# NUM_REMINDERS config
# ------------------------------------------------------------------ #

def test_num_reminders_defaults_to_three():
    """D1: the reminder count defaults to 3."""
    cfg = FakeConfig()
    num = BalConfig(cfg, "bal_num_reminders", 3)
    assert num.get() == 3


def test_num_reminders_can_be_changed():
    """D1: the reminder count is persisted and read back."""
    cfg = FakeConfig()
    num = BalConfig(cfg, "bal_num_reminders", 3)
    num.set(5)
    assert BalConfig(cfg, "bal_num_reminders", 3).get() == 5


# ------------------------------------------------------------------ #
# compute_reminder_offsets - distribution rules
# ------------------------------------------------------------------ #

def test_offsets_long_period_three_reminders():
    """30-day period, 3 reminders: spread out, all before the deadline."""
    offsets = compute_reminder_offsets(30, 3)
    assert len(offsets) == 3
    # All strictly before the deadline (offset >= 1 means "n days before end").
    assert all(o >= 1 for o in offsets)
    # Sorted earliest-first (largest offset first).
    assert offsets == sorted(offsets, reverse=True)
    # One reminder near the start, one near the end.
    assert max(offsets) == 30
    assert min(offsets) == 1


def test_offsets_capped_at_one_per_day():
    """Short period: at most one reminder per available day."""
    # 2 days but 3 requested -> only 2 reminders, one per day.
    assert compute_reminder_offsets(2, 3) == [2, 1]
    # 1 day but 3 requested -> a single reminder, the day before the deadline.
    assert compute_reminder_offsets(1, 3) == [1]


def test_offsets_empty_when_no_room():
    """No reminders when there is no day before the deadline."""
    assert compute_reminder_offsets(0, 3) == []
    assert compute_reminder_offsets(-5, 3) == []
    # A non-positive count also yields nothing.
    assert compute_reminder_offsets(30, 0) == []


def test_offsets_never_exceed_requested_count():
    """The number of reminders never exceeds the requested count (max 5)."""
    offsets = compute_reminder_offsets(100, 5)
    assert len(offsets) == 5
    assert all(o >= 1 for o in offsets)
    # Distinct offsets only (no duplicate alarms on the same day).
    assert len(set(offsets)) == len(offsets)


def test_offsets_single_reminder_is_day_before_deadline():
    """A single requested reminder fires one day before the deadline."""
    assert compute_reminder_offsets(30, 1) == [1]
