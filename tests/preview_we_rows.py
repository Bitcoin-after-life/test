#!/usr/bin/env python3
"""Visual PREVIEW focused on the WILL-EXECUTOR rows of the Building Will dialog.

Reproduces faithfully the three real variants built in dialogs.py:

  1. Broadcasting (push) result   -> line 774:  "{url} : {Ok|Ko}"   (plain, no color today)
  2. Timeout                      -> line 783:  "{url} : <font red>Timeout - no answer</font>"
  3. Checking already-present     -> line 825/834:
        "checking {url} - {wid} : Waiting"
        "checked  {url} - {wid} : True/False"   (plain, no color today)

Shows BEFORE (current) vs AFTER (proposed: result in bold, keeping label as-is).

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/preview_we_rows.py
Writes preview_we_before.png / preview_we_after.png in the repo root.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

COLOR_ERROR = "#ff0000"
COLOR_OK = "#05ad05"

URL1 = "https://executor.example.org"
URL2 = "https://other-executor.net"
WID = "a1b2c3"


def err(e):
    return "<font color='{}'>{}</font>".format(COLOR_ERROR, e)


# ---------------- BEFORE: exactly as the code builds today -----------------
def rows_before():
    return [
        # 1. push results (plain text, no color/bold today)
        "{} : {}".format(URL1, "Ok"),
        "{} : {}".format(URL2, "Ko"),
        # 2. timeout (already red, not bold)
        "{} : {}".format(URL1, err("Timeout - no answer")),
        # 3. already-present check
        "checking {} - {} : {}".format(URL1, WID, "Waiting"),
        "checked {} - {} : {}".format(URL1, WID, "True"),
        "checked {} - {} : {}".format(URL2, WID, "False"),
    ]


# ---------------- AFTER: result portion in bold, label unchanged -----------
def err_after(e):
    return "<font color='{}'><b>{}</b></font>".format(COLOR_ERROR, e)


def rows_after():
    return [
        # 1. push results: color + bold the Ok / Ko outcome
        "{} : <font color='{}'><b>{}</b></font>".format(URL1, COLOR_OK, "Ok"),
        "{} : <font color='{}'><b>{}</b></font>".format(URL2, COLOR_ERROR, "Ko"),
        # 2. timeout: bold the red message
        "{} : {}".format(URL1, err_after("Timeout - no answer")),
        # 3. already-present check: bold the result
        "checking {} - {} : <b>{}</b>".format(URL1, WID, "Waiting"),
        "checked {} - {} : <font color='{}'><b>{}</b></font>".format(
            URL1, WID, COLOR_OK, "True"
        ),
        "checked {} - {} : <font color='{}'><b>{}</b></font>".format(
            URL2, WID, COLOR_ERROR, "False"
        ),
    ]


def render(rows, title, path):
    full_text = "<br><br>".join(rows).replace("\n", "<br>")
    w = QWidget()
    w.setStyleSheet("background:#2b2b2b;")
    lay = QVBoxLayout(w)
    t = QLabel(title)
    t.setStyleSheet("color:#ffffff; font-size:15px; font-weight:bold;")
    lbl = QLabel(full_text)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet("color:#dddddd;")
    f = lbl.font()
    f.setPointSize(11)
    lbl.setFont(f)
    lay.addWidget(t)
    lay.addWidget(lbl)
    w.resize(560, 320)
    w.show()
    app.processEvents()
    w.grab().save(path)
    print(f"saved -> {path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    render(rows_before(), "Will-Executor rows  —  BEFORE",
           os.path.join(here, "preview_we_before.png"))
    render(rows_after(), "Will-Executor rows  —  AFTER",
           os.path.join(here, "preview_we_after.png"))
