"""
bal.gui.qt.common
=================

Shared imports and tiny helper utilities for the Qt GUI layer.

Every other ``bal.gui.qt`` module does ``from .common import *`` so that the
long list of Electrum / PyQt6 imports lives in a single place.  This file also
hosts a few GUI helpers that do not deserve a module of their own:

    * :class:`shown_cv`       - trivial mutable "is this tab shown?" holder.
    * :func:`add_widget`      - add a labelled widget (plus optional help) to a grid.
    * :func:`log_error`       - format an exception traceback for a dialog.
    * :func:`export_meta_gui` - export plugin metadata to a JSON file.
    * :class:`CheckAliveError`- raised when the "check alive" date is in the past.
"""

import copy
import enum
import os
import subprocess
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import partial
from typing import Any, Callable, Mapping, Optional, Union

from electrum.bitcoin import (NLOCKTIME_BLOCKHEIGHT_MAX, NLOCKTIME_MAX,
                              NLOCKTIME_MIN)
from electrum.gui.qt.amountedit import BTCAmountEdit
from electrum.gui.qt.main_window import ElectrumWindow, StatusBarButton
from electrum.gui.qt.my_treeview import MyTreeView
from electrum.gui.qt.password_dialog import PasswordDialog
from electrum.gui.qt.transaction_dialog import TxDialog
from electrum.gui.qt.util import (Buttons, CancelButton, ColorScheme,
                                  EnterButton, HelpButton, MessageBoxMixin,
                                  OkButton, TaskThread, WindowModalDialog,
                                  char_width_in_lineedit, getSaveFileName,
                                  import_meta_gui, read_QIcon_from_bytes,
                                  read_QPixmap_from_bytes, webopen)
from electrum.i18n import _
from electrum.logging import get_logger
from electrum.network import BestEffortRequestFailed, Network, TxBroadcastError
from electrum.payment_identifier import PaymentIdentifier
from electrum.plugin import hook
from electrum.transaction import SerializationError, Transaction, tx_from_any
from electrum.util import (DECIMAL_POINT, FileExportFailed, UserCancelled,
                           decimal_point_to_base_unit_name, read_json_file,
                           write_json_file)
from PyQt6.QtCore import (QDateTime, QModelIndex, QPersistentModelIndex, QSize,
                          Qt, QTimer, pyqtSignal)
from PyQt6.QtGui import (QColor, QPainter, QPalette, QStandardItem,
                         QStandardItemModel)
from PyQt6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QCheckBox,
                             QComboBox, QDateTimeEdit, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QTextEdit, QMenu,
                             QMenuBar, QPushButton, QScrollArea, QSizePolicy,
                             QSpinBox, QStackedWidget, QStyle, QStyleOptionFrame,
                             QVBoxLayout, QWidget, QDialog)

# --- Core (GUI-free) logic layer ---
from ...core.plugin_base import BalPlugin, BalTimestamp
from ...core.heirs import (HEIR_DUST_AMOUNT, HEIR_REAL_AMOUNT,
                           HeirAmountIsDustException, Heirs)
from ...core.util import Util
from ...core.will import (AmountException, HeirChangeException,
                          HeirNotFoundException, NoHeirsException,
                          NotCompleteWillException, NoWillExecutorNotPresent,
                          TxFeesChangedException, Will,
                          WillexecutorChangeException, WillExecutorNotPresent,
                          WillExpiredException, WillItem, WillPostponedException)
from ...core.willexecutors import Willexecutors

# --- Presentation helpers ---
from .theme import server_status_text, server_status_tooltip, status_color
from .window_utils import (bring_to_front, show_modal, show_on_top,
                           stop_thread, top_level_of)

_logger = get_logger(__name__)


class shown_cv:
    _type = bool

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value




def add_widget(grid, label, widget, row, help_):
    grid.addWidget(QLabel(_(label)), row, 0)
    grid.addWidget(widget, row, 1)
    grid.addWidget(HelpButton(help_), row, 2)




class CheckAliveError(Exception):
    def __init__(self, timestamp_to_check):
        self.timestamp_to_check = timestamp_to_check

    def __str__(self):
        return "Check alive expired please update it: {}".format(
            datetime.fromtimestamp(self.timestamp_to_check).isoformat()
        )




def log_error(exec_info, window=None):
    """Log an error and optionally show it.

    ``exec_info`` may be either a ``sys.exc_info()`` triple
    ``(type, value, traceback)`` or a single exception instance (callers use
    both forms), so we handle both and always try to log a full traceback.
    """
    _logger.error(f"LOG_ERROR: {exec_info}")
    exc = None
    if isinstance(exec_info, BaseException):
        exc = exec_info
    elif isinstance(exec_info, (tuple, list)) and len(exec_info) >= 2:
        # sys.exc_info() form: the exception instance is the 2nd element.
        exc = exec_info[1]
    try:
        if exc is not None:
            _logger.error(
                "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
            )
        else:
            _logger.error(traceback.format_exc())
    except Exception:
        _logger.error(traceback.format_exc())

    if window is not None:
        # show_error expects a human-readable message, not a triple.
        window.show_error(str(exc) if exc is not None else str(exec_info))




def export_meta_gui(electrum_window, title, exporter):
    filter_ = "All files (*)"
    filename = getSaveFileName(
        parent=electrum_window,
        title=_("Select file to save your {}".format(title)),
        filename="BALplugin_{}_{}_{}".format(
            BalPlugin.chainname, str(electrum_window.wallet), title
        ),
        filter=filter_,
        config=electrum_window.config,
    )
    if not filename:
        return
    try:
        exporter(filename)
    except FileExportFailed as e:
        electrum_window.show_critical(str(e))
    else:
        electrum_window.show_message(
            _("Your {0} were exported to '{1}'".format(title, str(filename)))
        )


