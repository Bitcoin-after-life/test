#!/usr/bin/env python3
"""Render a visual PREVIEW (before/after) of the "Building Will" dialog text.

This is a throwaway, GUI-only helper used to show the user how the proposed
"bold results" formatting looks compared to the current rendering, BEFORE any
production code is changed.  It does NOT import the plugin; it just reproduces
the exact rich-text the dialog builds via ``msg_set_status`` / ``msg_ok`` /
``msg_error`` so the preview is faithful.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/preview_build_will_dialog.py
It writes two PNGs in the repo root: preview_before.png and preview_after.png.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

# Same colors as BalBuildWillDialog
COLOR_WARNING = "#cfa808"
COLOR_ERROR = "#ff0000"
COLOR_OK = "#05ad05"


# ---- current rendering (BEFORE) -------------------------------------------
def ok_before(e="Ok"):
    return "<font color='{}'>{}</font>".format(COLOR_OK, e)


def error_before(e):
    return "<font color='{}'>{}</font>".format(COLOR_ERROR, e)


def row_before(msg, status, color=None):
    if color is None:
        return f"{msg}:\t{status}"
    return "<font color={}>{}:\t{}</font>".format(color, msg, status)


# ---- proposed rendering (AFTER): results in bold --------------------------
def ok_after(e="Ok"):
    return "<font color='{}'><b>{}</b></font>".format(COLOR_OK, e)


def error_after(e):
    return "<font color='{}'><b>{}</b></font>".format(COLOR_ERROR, e)


def row_after(msg, status, color=None):
    # Left state label stays normal; only the result (status) becomes bold.
    if color is None:
        return f"{msg}:\t<b>{status}</b>"
    # When a color is given for the whole line, keep the label normal and bold
    # only the status portion.
    return "{}:\t<font color={}><b>{}</b></font>".format(msg, color, status)


def build_rows(mode):
    if mode == "before":
        ok, err, row = ok_before, error_before, row_before
    else:
        ok, err, row = ok_after, error_after, row_after
    rows = [
        row("checking variables", "Wait"),
        row("Checking your will", ok()),
        row("Signing your will", "Nothing to do"),
        row("Broadcasting your will to executors", "Nothing to do"),
        ok(),
        row("Invalidating old will", err("Ko")),
        "https://executor.example.org : " + ok(),
        "https://other.example.org : " + err("Ko"),
        "Please wait 2secs",
        row("Will-Executor excluded", "Skipped", COLOR_ERROR),
    ]
    return rows


def render(mode, path):
    rows = build_rows(mode)
    full_text = "<br><br>".join(rows).replace("\n", "<br>")
    w = QWidget()
    w.setStyleSheet("background:#2b2b2b;")
    lay = QVBoxLayout(w)
    title = QLabel(f"Building Will  —  {mode.upper()}")
    title.setStyleSheet("color:#ffffff; font-size:15px; font-weight:bold;")
    lbl = QLabel(full_text)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet("color:#dddddd; font-size:13px;")
    lbl_font = lbl.font()
    lbl_font.setPointSize(11)
    lbl.setFont(lbl_font)
    lay.addWidget(title)
    lay.addWidget(lbl)
    w.resize(560, 420)
    w.show()
    app.processEvents()
    pix = w.grab()
    pix.save(path)
    print(f"[{mode}] saved -> {path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    render("before", os.path.join(here, "preview_before.png"))
    render("after", os.path.join(here, "preview_after.png"))
