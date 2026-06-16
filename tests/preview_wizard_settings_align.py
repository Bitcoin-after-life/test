#!/usr/bin/env python3
"""Visual PREVIEW for the wizard "Bitcoin After Life Will Settings" rows.

Reproduces the structure of WillSettingsWidget in its VERTICAL layout (the one
used by the "Build your will" wizard):

  row 1: [icon][combo "Date"][date field]      (delivery time / locktime)
  row 2: [icon][combo "Date"][date field]      (check alive / threshold)
  row 3: [calendar button]                      (calendar export)
  row 4: [icon "丰"][spin "5"]                    (tx fees)

The icons are HelpButtons, which pin themselves to a fixed width
(2.2 * char_width_in_lineedit()).  This preview reproduces that original icon
size and shows:

  * BEFORE: calendar/fee stretch to the right edge -> rows wider than dates.
  * AFTER : icons keep their ORIGINAL fixed width; every row is capped to the
            date-row width and left aligned, so all rows fit in the same block
            and line up on both edges.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/preview_wizard_settings_align.py
Writes preview_wizard_before.png / preview_wizard_after.png in the repo root.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QComboBox,
    QLineEdit, QSpinBox, QLabel,
)
from PyQt6.QtGui import QFontMetrics  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402


def _char_w():
    fm = QFontMetrics(QApplication.instance().font())
    return fm.horizontalAdvance("0")


def _icon(text):
    """Mimic HelpButton: a QToolButton pinned to 2.2 * char width."""
    b = QToolButton()
    b.setText(text)
    b.setFixedWidth(round(2.2 * _char_w()))
    return b


def _date_row():
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)
    icon = _icon("📅")
    combo = QComboBox()
    combo.addItems(["Raw", "Date"])
    combo.setCurrentIndex(1)
    field = QLineEdit("04/06/2028 00:00")
    h.addWidget(icon)
    h.addWidget(combo)
    h.addWidget(field)
    h.addStretch(1)
    w._prefix = icon
    return w


def _fee_row():
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)
    icon = _icon("丰")
    spin = QSpinBox()
    spin.setValue(5)
    spin.setMaximum(10000)
    h.addWidget(icon)
    h.addWidget(spin)
    w._prefix = icon
    return w


def _calendar_button():
    return QToolButton()


def _panel():
    panel = QWidget()
    box = QVBoxLayout(panel)
    box.addWidget(QLabel("Bitcoin After Life Will Settings"))
    return panel, box


def build_before():
    panel, box = _panel()
    box.addWidget(_date_row())
    box.addWidget(_date_row())
    box.addWidget(_calendar_button())
    box.addWidget(_fee_row())
    panel.resize(760, 220)
    return panel


def build_after():
    panel, box = _panel()
    r1 = _date_row()
    r2 = _date_row()
    cal = _calendar_button()
    r4 = _fee_row()

    # icons keep their original fixed width (no resizing)
    icon_w = r1._prefix.sizeHint().width()

    row_w = max(r1.sizeHint().width(), r2.sizeHint().width())
    for r in (r1, r2, r4):
        r.setFixedWidth(row_w)

    cal_row = QWidget()
    cb = QHBoxLayout(cal_row)
    cb.setContentsMargins(0, 0, 0, 0)
    cb.setSpacing(0)
    sp = QWidget()
    sp.setFixedWidth(icon_w)
    cb.addWidget(sp)
    cb.addWidget(cal)
    cal_row.setFixedWidth(row_w)

    box.addWidget(r1, alignment=Qt.AlignmentFlag.AlignLeft)
    box.addWidget(r2, alignment=Qt.AlignmentFlag.AlignLeft)
    box.addWidget(cal_row, alignment=Qt.AlignmentFlag.AlignLeft)
    box.addWidget(r4, alignment=Qt.AlignmentFlag.AlignLeft)
    panel.resize(760, 220)
    return panel


def main():
    app = QApplication.instance() or QApplication([])
    for builder, name in (
        (build_before, "preview_wizard_before.png"),
        (build_after, "preview_wizard_after.png"),
    ):
        panel = builder()
        panel.show()
        app.processEvents()
        panel.grab().save(name)
        print("wrote", name)


if __name__ == "__main__":
    main()
