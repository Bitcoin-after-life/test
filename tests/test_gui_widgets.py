"""
Tests for ``bal.gui.qt.widgets``.

Covers testable widgets without requiring a running Electrum wallet:
  - ClickableLabel
  - BalLineEdit, BalTextEdit, BalCheckBox
  - _LockTimeEditor (static/class methods)
  - LockTimeRawEdit (numbify, checkbdy, replace_str)
  - PercAmountEdit

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_gui_widgets.py
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 2)[0])

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from electrum.util import DECIMAL_POINT, decimal_point_to_base_unit_name

_app = QApplication.instance() or QApplication(sys.argv)


# ------------------------------------------------------------------ #
# ClickableLabel
# ------------------------------------------------------------------ #

def test_clickable_label_creation():
    from bal.gui.qt.widgets import ClickableLabel
    lbl = ClickableLabel("test")
    assert lbl.text() == "test"
    assert hasattr(lbl, "doubleClicked")


# ------------------------------------------------------------------ #
# BalLineEdit
# ------------------------------------------------------------------ #

def test_bal_line_edit():
    from bal.gui.qt.common import shown_cv
    from bal.gui.qt.widgets import BalLineEdit
    cv = shown_cv("initial")
    edit = BalLineEdit(cv)
    assert edit.text() == "initial"
    cv.set("updated")
    assert cv.get() == "updated"


# ------------------------------------------------------------------ #
# BalTextEdit
# ------------------------------------------------------------------ #

def test_bal_text_edit():
    from bal.gui.qt.common import shown_cv
    from bal.gui.qt.widgets import BalTextEdit
    cv = shown_cv("multi\nline")
    edit = BalTextEdit(cv)
    assert edit.toPlainText() == "multi\nline"
    cv.set("changed")
    assert cv.get() == "changed"


# ------------------------------------------------------------------ #
# BalCheckBox
# ------------------------------------------------------------------ #

def test_bal_check_box():
    from bal.gui.qt.common import shown_cv
    from bal.gui.qt.widgets import BalCheckBox
    cv = shown_cv(True)
    cb = BalCheckBox(cv)
    assert cb.isChecked() is True
    cv.set(False)
    assert cv.get() is False


def test_bal_check_box_on_click():
    from bal.gui.qt.common import shown_cv
    from bal.gui.qt.widgets import BalCheckBox
    calls = []
    def handler():
        calls.append(1)
    cv = shown_cv(True)
    cb = BalCheckBox(cv, on_click=handler)
    cb.click()
    assert len(calls) == 1


# ------------------------------------------------------------------ #
# _LockTimeEditor
# ------------------------------------------------------------------ #

def test_locktime_editor_is_acceptable():
    from bal.gui.qt.widgets import _LockTimeEditor
    assert _LockTimeEditor.is_acceptable_locktime(100) is True
    assert _LockTimeEditor.is_acceptable_locktime(0) is True
    assert _LockTimeEditor.is_acceptable_locktime(-1) is False
    assert _LockTimeEditor.is_acceptable_locktime(None) is True


def test_locktime_editor_is_acceptable_string():
    from bal.gui.qt.widgets import _LockTimeEditor
    assert _LockTimeEditor.is_acceptable_locktime("100") is True
    assert _LockTimeEditor.is_acceptable_locktime("abc") is False
    assert _LockTimeEditor.is_acceptable_locktime("") is True


def test_locktime_editor_min_max():
    from bal.gui.qt.widgets import _LockTimeEditor
    assert _LockTimeEditor.min_allowed_value >= 0
    assert _LockTimeEditor.max_allowed_value > _LockTimeEditor.min_allowed_value


# ------------------------------------------------------------------ #
# LockTimeRawEdit
# ------------------------------------------------------------------ #

def test_locktime_raw_edit_replace_str():
    # replace_str only strips the day ("d") and year ("y") suffixes. The
    # block-height suffix ("b") was removed (A1), so "b" is NOT stripped
    # anymore (locktimes are always UNIX timestamps now).
    from bal.gui.qt.widgets import LockTimeRawEdit
    assert LockTimeRawEdit.replace_str("123d") == "123"
    assert LockTimeRawEdit.replace_str("456y") == "456"
    # "b" is left untouched (no longer a recognised suffix)
    assert LockTimeRawEdit.replace_str("789b") == "789b"
    # only d/y are stripped; a stray "b" remains
    assert LockTimeRawEdit.replace_str("12d34y56b") == "123456b"


def test_locktime_raw_edit_checkbdy():
    from bal.gui.qt.widgets import LockTimeRawEdit
    # character at expected position matches appendix
    pos, s = LockTimeRawEdit.checkbdy(None, "123d", 4, "d")
    assert s == "123d"
    # character at expected position does not match
    pos, s = LockTimeRawEdit.checkbdy(None, "123x", 4, "d")
    assert s == "123x"


def test_locktime_raw_edit_numbify_empty():
    parent = QWidget()
    from bal.gui.qt.widgets import LockTimeRawEdit
    edit = LockTimeRawEdit(parent)
    edit.setText("")
    edit.numbify()
    assert edit.text() == ""


def test_locktime_raw_edit_numbify_days():
    parent = QWidget()
    from bal.gui.qt.widgets import LockTimeRawEdit
    edit = LockTimeRawEdit(parent)
    # Use setText + numbify to simulate user typing
    edit.blockSignals(True)
    edit.setText("30d")
    edit.blockSignals(False)
    edit.numbify()
    # Should be "30d" with isdays=True
    assert edit.text() == "30d"


def test_locktime_raw_edit_numbify_years():
    parent = QWidget()
    from bal.gui.qt.widgets import LockTimeRawEdit
    edit = LockTimeRawEdit(parent)
    edit.blockSignals(True)
    edit.setText("2y")
    edit.blockSignals(False)
    edit.numbify()
    assert edit.text() == "2y"


def test_locktime_raw_edit_get_set_value():
    parent = QWidget()
    from bal.gui.qt.widgets import LockTimeRawEdit
    edit = LockTimeRawEdit(parent)
    edit.set_value("90d")
    val = edit.get_value()
    assert val is not None
    assert "d" in val


# ------------------------------------------------------------------ #
# PercAmountEdit
# ------------------------------------------------------------------ #

def test_perc_amount_edit_numbify_percent():
    from bal.gui.qt.widgets import PercAmountEdit
    parent = QWidget()
    edit = PercAmountEdit(8, parent=parent)
    edit.blockSignals(True)
    edit.setText("50%")
    edit.blockSignals(False)
    edit.numbify()
    assert edit.is_perc is True
    # After numbify: "50%" -> strip % -> add back -> "50%"
    assert edit.text() == "50%"


def test_perc_amount_edit_numbify_no_percent():
    from bal.gui.qt.widgets import PercAmountEdit
    parent = QWidget()
    edit = PercAmountEdit(8, parent=parent)
    edit.blockSignals(True)
    edit.setText("123")
    edit.blockSignals(False)
    edit.numbify()
    assert edit.is_perc is False
    assert edit.text() == "123"


def test_perc_amount_get_amount_from_text():
    from bal.gui.qt.widgets import PercAmountEdit
    parent = QWidget()
    edit = PercAmountEdit(8, parent=parent)
    # With percent
    result = edit._get_amount_from_text("50%")
    assert result is not None
    # Without percent
    result = edit._get_amount_from_text("123.45")
    assert result is not None
    # Invalid
    result = edit._get_amount_from_text("abc")
    assert result is None


def test_perc_amount_get_text_from_amount():
    from bal.gui.qt.widgets import PercAmountEdit
    parent = QWidget()
    edit = PercAmountEdit(lambda: 8, parent=parent)
    edit.numbify()  # sets is_perc
    text = edit._get_text_from_amount(100)
    assert isinstance(text, str)


def test_perc_amount_get_text_from_amount_perc():
    from bal.gui.qt.widgets import PercAmountEdit
    parent = QWidget()
    edit = PercAmountEdit(lambda: 8, parent=parent)
    edit.blockSignals(True)
    edit.setText("50%")
    edit.blockSignals(False)
    edit.numbify()  # sets is_perc = True
    text = edit._get_text_from_amount(100)
    assert "%" in text


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All widget tests passed")
