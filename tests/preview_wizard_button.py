#!/usr/bin/env python3
"""Visual PREVIEW: proposals to make the Wizard button more visible.

Renders the toolbar Wizard button (using the real icons/wizard.png) in several
styles so the user can pick one.  Nothing is changed in the plugin yet.

Variants:
  0. CURRENT  : icon only, default size (what ships today).
  A. BIGGER   : same icon, larger button + larger iconSize.
  B. ICON+TEXT: bigger icon plus a "Create your will" label.
  C. ACCENT   : icon + text on a colored (Bitcoin-orange) rounded button.
  D. ACCENT-BLUE: icon + text on a BAL-blue (#2bc8ed) rounded button.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/preview_wizard_button.py
Writes preview_wizardbtn_<id>.png in the repo root.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QHBoxLayout, QPushButton, QComboBox, QLineEdit,
    QLabel,
)
from PyQt6.QtGui import QIcon, QPixmap  # noqa: E402
from PyQt6.QtCore import QSize, Qt  # noqa: E402

ICON_PATH = os.path.join(os.path.dirname(__file__), "..", "bal", "icons",
                        "wizard.png")


def _icon():
    pm = QPixmap(ICON_PATH)
    return QIcon(pm)


def _toolbar_tail(parent):
    """The widgets that sit to the right of the wizard button, for context."""
    out = []
    icon = QPushButton(parent)
    icon.setText("📅")
    combo = QComboBox(parent)
    combo.addItems(["Raw", "Date"])
    combo.setCurrentIndex(1)
    field = QLineEdit("04/06/2028 00:00", parent)
    field.setFixedWidth(140)
    out += [icon, combo, field]
    return out


def _frame(make_wizard, label):
    panel = QWidget()
    v = QHBoxLayout(panel)
    v.setContentsMargins(10, 10, 10, 10)
    tag = QLabel(label, panel)
    tag.setFixedWidth(120)
    v.addWidget(tag)
    wiz = make_wizard(panel)
    v.addWidget(wiz)
    for w in _toolbar_tail(panel):
        v.addWidget(w)
    v.addStretch(1)
    panel.resize(720, 70)
    return panel


# ---- variants -------------------------------------------------------------
def v_current(parent):
    b = QPushButton(parent)
    b.setIcon(_icon())
    b.setToolTip("Wizard - Build your will")
    return b


def v_bigger(parent):
    b = QPushButton(parent)
    b.setIcon(_icon())
    b.setIconSize(QSize(36, 36))
    b.setFixedSize(48, 44)
    b.setToolTip("Wizard - Build your will")
    return b


def v_icon_text(parent):
    b = QPushButton("  Create your will", parent)
    b.setIcon(_icon())
    b.setIconSize(QSize(28, 28))
    b.setMinimumHeight(40)
    b.setStyleSheet("QPushButton{font-weight:bold;}")
    return b


def v_accent_orange(parent):
    b = QPushButton("  Create your will", parent)
    b.setIcon(_icon())
    b.setIconSize(QSize(28, 28))
    b.setMinimumHeight(40)
    b.setStyleSheet(
        "QPushButton{background-color:#f7931a;color:white;font-weight:bold;"
        "border:none;border-radius:8px;padding:6px 14px;}"
        "QPushButton:hover{background-color:#ffa733;}"
    )
    return b


def v_accent_blue(parent):
    b = QPushButton("  Create your will", parent)
    b.setIcon(_icon())
    b.setIconSize(QSize(28, 28))
    b.setMinimumHeight(40)
    b.setStyleSheet(
        "QPushButton{background-color:#2bc8ed;color:white;font-weight:bold;"
        "border:none;border-radius:8px;padding:6px 14px;}"
        "QPushButton:hover{background-color:#4fd6f3;}"
    )
    return b


def main():
    app = QApplication.instance() or QApplication([])
    variants = [
        (v_current, "0-CURRENT", "preview_wizardbtn_0_current.png"),
        (v_bigger, "A-BIGGER", "preview_wizardbtn_A_bigger.png"),
        (v_icon_text, "B-ICON+TEXT", "preview_wizardbtn_B_icontext.png"),
        (v_accent_orange, "C-ORANGE", "preview_wizardbtn_C_orange.png"),
        (v_accent_blue, "D-BLUE", "preview_wizardbtn_D_blue.png"),
    ]
    for make, label, name in variants:
        panel = _frame(make, label)
        panel.show()
        app.processEvents()
        panel.grab().save(name)
        print("wrote", name)


if __name__ == "__main__":
    main()
