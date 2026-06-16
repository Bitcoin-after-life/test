#!/usr/bin/env python3
"""Visual PREVIEW: replace the final countdown with a "Close" button.

Mocks the "Building Will" dialog content (the result rows are built exactly as
the real dialog builds them) and shows the proposed bottom "Close" button that
replaces the "Please wait 5secs" auto-closing countdown.

BEFORE: last line is the countdown "Please wait 5secs" (dialog auto-closes).
AFTER : a real "Close" button at the bottom; the user closes when ready.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/preview_building_will_close_btn.py
Writes preview_buildwill_before.png / preview_buildwill_after.png.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt  # noqa: E402

COLOR_OK = "#05ad05"


def _ok(text="Ok"):
    return "<font color='{}'><b>{}</b></font>".format(COLOR_OK, text)


def _rows(after: bool):
    """The exact result rows the real dialog shows on a clean run.

    BEFORE keeps the old lowercase "checking variables" and the "All done"
    row directly under the others.  AFTER applies the two text fixes:
    capitalised "Checking variables" + a blank separator row above "All done".
    """
    if not after:
        return [
            "checking variables:\t" + _ok("Ok"),
            "Checking your will:\t" + _ok("Ok"),
            "Signing your will:\t<b>Nothing to do</b>",
            "Broadcasting your will to executors:\t<b>Nothing to do</b>",
            "All done:\t" + _ok("Ok"),
        ]
    return [
        "Checking variables:\t" + _ok("Ok"),
        "Checking your will:\t" + _ok("Ok"),
        "Signing your will:\t<b>Nothing to do</b>",
        "Broadcasting your will to executors:\t<b>Nothing to do</b>",
        "",  # blank separator row
        "All done:\t" + _ok("Ok"),
    ]


def _build(after: bool) -> QWidget:
    panel = QWidget()
    panel.setMinimumWidth(600)
    v = QVBoxLayout(panel)
    v.addWidget(QLabel("<b>Building Will:</b>"))

    rows = QWidget()
    rv = QVBoxLayout(rows)
    rv.setContentsMargins(8, 4, 8, 4)
    for line in _rows(after):
        lbl = QLabel(line)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        rv.addWidget(lbl)
    v.addWidget(rows)

    if not after:
        # BEFORE: the countdown row (auto-close).
        wait = QLabel("Please wait 5secs")
        v.addWidget(wait)
    else:
        # AFTER: a Close button row, right aligned (standard dialog layout).
        v.addSpacing(8)
        btn_row = QWidget()
        h = QHBoxLayout(btn_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.setMinimumWidth(90)
        h.addWidget(close)
        v.addWidget(btn_row)

    panel.resize(620, 230)
    return panel


def main():
    app = QApplication.instance() or QApplication([])
    for after, name in ((False, "preview_buildwill_before.png"),
                        (True, "preview_buildwill_after.png")):
        panel = _build(after)
        panel.show()
        app.processEvents()
        panel.grab().save(name)
        print("wrote", name)


if __name__ == "__main__":
    main()
