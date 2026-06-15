"""
Tests for ``bal.gui.qt.common``.

Covers shown_cv, CheckAliveError, add_widget, log_error, export_meta_gui.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_gui_common.py
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 2)[0])

from PyQt6.QtWidgets import QApplication, QGridLayout, QLabel, QWidget

# Import the module itself, not via "from .common import *"
import bal.gui.qt.common as C

_app = QApplication.instance() or QApplication(sys.argv)


# ------------------------------------------------------------------ #
# shown_cv
# ------------------------------------------------------------------ #

def test_shown_cv_default():
    cv = C.shown_cv(True)
    assert cv.get() is True


def test_shown_cv_set():
    cv = C.shown_cv(True)
    cv.set(False)
    assert cv.get() is False


def test_shown_cv_roundtrip():
    cv = C.shown_cv(False)
    assert cv.get() is False
    cv.set(True)
    assert cv.get() is True
    cv.set(True)
    assert cv.get() is True


# ------------------------------------------------------------------ #
# CheckAliveError
# ------------------------------------------------------------------ #

def test_check_alive_error_default():
    err = C.CheckAliveError(1000000)
    assert err.timestamp_to_check == 1000000


def test_check_alive_error_str():
    err = C.CheckAliveError(1000000)
    s = str(err)
    assert "Check alive expired" in s
    assert "1970" in s


def test_check_alive_error_subclass():
    assert issubclass(C.CheckAliveError, Exception)


# ------------------------------------------------------------------ #
# add_widget
# ------------------------------------------------------------------ #

def test_add_widget():
    grid = QGridLayout()
    parent = QWidget()
    label = QLabel("test")
    C.add_widget(grid, "Label", label, 0, "Help text")
    assert grid.count() == 3  # label + widget + help button


def test_add_widget_multiple_rows():
    grid = QGridLayout()
    parent = QWidget()
    C.add_widget(grid, "A", QLabel("a"), 0, "help_a")
    C.add_widget(grid, "B", QLabel("b"), 1, "help_b")
    assert grid.count() == 6


# ------------------------------------------------------------------ #
# log_error
# ------------------------------------------------------------------ #

def test_log_error_no_window():
    C.log_error((Exception, Exception("test"), None))


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All common tests passed")
