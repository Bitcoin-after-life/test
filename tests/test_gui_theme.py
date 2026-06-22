"""
Tests for ``bal.gui.qt.theme``.

Covers ``status_color`` priority logic.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_gui_theme.py
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 2)[0])

from bal.gui.qt.theme import status_color


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

class FakeWillItem:
    def __init__(self, **status_flags):
        self._status = dict(status_flags)
    def get_status(self, name):
        return self._status.get(name, False)


# ------------------------------------------------------------------ #
# Priority-ordered statuses
# ------------------------------------------------------------------ #

def test_color_invalidated():
    assert status_color(FakeWillItem(INVALIDATED=True)) == "#f87838"


def test_color_invalidated_overrides_lower():
    # PENDING was renamed to MEMPOOL (A2).
    item = FakeWillItem(INVALIDATED=True, MEMPOOL=True, COMPLETE=True)
    assert status_color(item) == "#f87838"


def test_color_replaced():
    assert status_color(FakeWillItem(REPLACED=True)) == "#ff97e9"


def test_color_updated():
    # UPDATED is a new status (A2): light violet. It is checked after REPLACED
    # but before CONFIRMED/MEMPOOL in the priority list. The original violet
    # (#800080) was too dark to read, so it was lightened to #b266b2.
    assert status_color(FakeWillItem(UPDATED=True)) == "#b266b2"


def test_color_confirmed():
    assert status_color(FakeWillItem(CONFIRMED=True)) == "#bfbfbf"


def test_color_mempool():
    # PENDING was renamed to MEMPOOL (A2); the colour (yellow) is unchanged.
    assert status_color(FakeWillItem(MEMPOOL=True)) == "#ffce30"


# ------------------------------------------------------------------ #
# Branching statuses (CHECK_FAIL / CHECKED / PUSH_FAIL / PUSHED / COMPLETE)
# ------------------------------------------------------------------ #

def test_color_check_fail_not_checked():
    item = FakeWillItem(CHECK_FAIL=True)
    assert status_color(item) == "#e83845"


def test_color_check_fail_ignored_if_checked():
    item = FakeWillItem(CHECK_FAIL=True, CHECKED=True)
    assert status_color(item) == "#8afa6c"


def test_color_checked():
    assert status_color(FakeWillItem(CHECKED=True)) == "#8afa6c"


def test_color_push_fail():
    assert status_color(FakeWillItem(PUSH_FAIL=True)) == "#e83845"


def test_color_pushed():
    assert status_color(FakeWillItem(PUSHED=True)) == "#73f3c8"


def test_color_complete():
    assert status_color(FakeWillItem(COMPLETE=True)) == "#2bc8ed"


def test_color_default():
    assert status_color(FakeWillItem()) == "#ffffff"


def test_color_check_fail_overrides_push_fail():
    item = FakeWillItem(CHECK_FAIL=True, PUSH_FAIL=True)
    assert status_color(item) == "#e83845"


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All theme tests passed")
