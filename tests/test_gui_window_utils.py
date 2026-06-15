"""
Tests for ``bal.gui.qt.window_utils``.

Covers top_level_of, bring_to_front, stop_thread, show_modal, show_on_top.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_gui_window_utils.py
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 2)[0])

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from bal.gui.qt.window_utils import (
    bring_to_front, show_modal, show_on_top, stop_thread, top_level_of,
)

_app = QApplication.instance() or QApplication(sys.argv)


# ------------------------------------------------------------------ #
# top_level_of
# ------------------------------------------------------------------ #

def test_top_level_of_child():
    w = QWidget()
    child = QWidget(w)
    assert top_level_of(child) is w


def test_top_level_of_plain_widget():
    w = QWidget()
    assert top_level_of(w) is w.window()


def test_top_level_of_none():
    assert top_level_of(None) is None


def test_top_level_of_dialog():
    d = QDialog()
    assert top_level_of(d) is d.window()


# ------------------------------------------------------------------ #
# bring_to_front
# ------------------------------------------------------------------ #

def test_bring_to_front_dialog():
    d = QDialog()
    bring_to_front(d)


def test_bring_to_front_widget():
    w = QWidget()
    bring_to_front(w)


# ------------------------------------------------------------------ #
# stop_thread
# ------------------------------------------------------------------ #

def test_stop_thread_none():
    stop_thread(None)


# ------------------------------------------------------------------ #
# show_modal / show_on_top (smoke tests - can't check exec result)
# ------------------------------------------------------------------ #

def test_show_modal_no_crash():
    d = QDialog()
    QTimer.singleShot(0, d.reject)
    result = show_modal(d)
    assert result == QDialog.DialogCode.Rejected


def test_show_on_top_no_crash():
    d = QDialog()
    result = show_on_top(d, modal_to_window=True)
    assert result is d
    d.close()


def test_show_on_top_non_modal():
    d = QDialog()
    result = show_on_top(d, modal_to_window=False)
    assert result is d
    d.close()


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All window_utils tests passed")
