"""

BAL

Bitcoin after life

"""

import copy
import enum
import os
import subprocess
import tempfile
import time
import traceback
from datetime import datetime, timezone
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
                                  read_QPixmap_from_bytes)
from electrum.i18n import _
from electrum.logging import get_logger
from electrum.network import BestEffortRequestFailed, Network, TxBroadcastError
from electrum.payment_identifier import PaymentIdentifier
from electrum.plugin import hook
from electrum.transaction import SerializationError, Transaction, tx_from_any
from electrum.util import (DECIMAL_POINT, FileExportFailed, UserCancelled,
                           decimal_point_to_base_unit_name, read_json_file,
                           write_json_file)
from PyQt6.QtCore import (QDateTime, QModelIndex, QPersistentModelIndex, Qt,
                          QTimer, pyqtSignal)
from PyQt6.QtGui import (QColor, QPainter, QPalette, QStandardItem,
                         QStandardItemModel)
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                             QDateTimeEdit, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QTextEdit, QMenu, QMenuBar, QPushButton,
                             QScrollArea, QSizePolicy, QSpinBox,
                             QStackedWidget, QStyle, QStyleOptionFrame,
                             QVBoxLayout, QWidget,QDialog)

from .bal import BalPlugin,BalTimestamp
from .heirs import HEIR_DUST_AMOUNT, HEIR_REAL_AMOUNT, Heirs
from .util import  Util
from .will import (AmountException, HeirChangeException, HeirNotFoundException,
                   NoHeirsException, NotCompleteWillException,
                   NoWillExecutorNotPresent, TxFeesChangedException, Will,
                   WillexecutorChangeException, WillExecutorNotPresent,
                   WillExpiredException, WillItem)
from .willexecutors import Willexecutors

_logger = get_logger(__name__)


class Plugin(BalPlugin):
    def __init__(self, parent, config, name):
        _logger.info("INIT BALPLUGIN")
        BalPlugin.__init__(self, parent, config, name)
        self.bal_windows = {}

    @hook
    def init_qt(self, gui_object):
        _logger.info("HOOK bal init qt")
        try:
            self.gui_object = gui_object
            for window in gui_object.windows:
                wallet = window.wallet
                if wallet:
                    window.show_warning(
                        _("Please restart Electrum to activate the BAL plugin"),
                        title=_("Success"),
                    )
                    return
                top_level_window=window.top_level_window()
                w = BalWindow(self, top_level_window)
                self.bal_windows[top_level_window.winId] = w
                for child in window.children():
                    if isinstance(child, QMenuBar):
                        for menu_child in child.children():
                            if isinstance(menu_child, QMenu):
                                try:
                                    if menu_child.title() == _("&Tools"):
                                        w.init_menubar_tools(menu_child)

                                except Exception as e:
                                    _logger.error(
                                        ("init_qt except:", menu_child.text())
                                    )
                                    raise e

        except Exception as e:
            _logger.error("Error loading plugini {}".format(e))
            raise e

    @hook
    def create_status_bar(self, sb):
        _logger.info("HOOK create status bar")
        b = StatusBarButton(
            read_QIcon_from_bytes(self.read_file("icons/bal32x32.png")),
            "Bal " + _("Bitcoin After Life"),
            partial(self.settings_dialog, sb),
            sb.height(),
        )
        sb.addPermanentWidget(b)

    @hook
    def init_menubar(self, window):
        _logger.info("HOOK init_menubar")
        w = self.get_window(window)
        w.init_menubar_tools(window.tools_menu)

    @hook
    def load_wallet(self, wallet, main_window):
        _logger.debug("HOOK load wallet")
        w = self.get_window(main_window)
        # havetoupdate = Util.fix_will_settings_tx_fees(wallet.db)
        w.wallet = wallet
        w.init_will()
        w.willexecutors = Willexecutors.get_willexecutors(
            self, update=False, bal_window=w
        )
        w.disable_plugin = False
        w.ok = True

    @hook
    def close_wallet(self, wallet):
        _logger.debug("HOOK close wallet")
        for _winid, win in self.bal_windows.items():
            if win.wallet == wallet:
                win.on_close()

    @hook
    def init_keystore(self):
        _logger.debug("init keystore")

    @hook
    def daemon_wallet_loaded(self, boh, wallet):
        _logger.debug("daemon wallet loaded")

    def get_window(self, window):
        window=window.top_level_window()
        w = self.bal_windows.get(window.winId, None)
        if w is None:
            w = BalWindow(self, window)
            self.bal_windows[window.winId] = w
        return w

    def requires_settings(self):
        return True

    def settings_widget(self, window):

        w = self.get_window(window.window)
        widget = QWidget()
        enterbutton = EnterButton(_("Settings"), partial(w.settings_dialog, window))

        widget.setLayout(Buttons(enterbutton, widget))
        return widget

    def password_dialog(self, msg=None, parent=None):
        parent = parent or self
        d = PasswordDialog(parent, msg)
        return d.run()

    def get_seed(self):
        password = None
        if self.wallet.has_keystore_encryption():
            password = self.password_dialog(parent=self.d.parent())
            if not password:
                raise UserCancelled()

        keystore = self.wallet.get_keystore()
        if not keystore or not keystore.has_seed():
            return
        self.extension = bool(keystore.get_passphrase(password))
        return keystore.get_seed(password)

    def settings_dialog(self, window=None, wallet=None):

        d = BalDialog(window, self, self.get_window_title("Settings"))
        d.setMinimumSize(100, 200)
        qicon = read_QPixmap_from_bytes(self.read_file("icons/bal16x16.png"))
        lbl_logo = QLabel()
        lbl_logo.setPixmap(qicon)

        # heir_ping_willexecutors = BalCheckBox(self.PING_WILLEXECUTORS)
        # heir_ask_ping_willexecutors = BalCheckBox(self.ASK_PING_WILLEXECUTORS)
        # heir_no_willexecutor = BalCheckBox(self.NO_WILLEXECUTOR)

        def on_multiverse_change():
            self.update_all()

        # heir_enable_multiverse = BalCheckBox(self.ENABLE_MULTIVERSE,on_multiverse_change)

        heir_hide_replaced = BalCheckBox(self.HIDE_REPLACED, on_multiverse_change)

        heir_hide_invalidated = BalCheckBox(self.HIDE_INVALIDATED, on_multiverse_change)
        heir_repush = QPushButton("Rebroadcast transactions")
        heir_repush.clicked.connect(partial(self.broadcast_transactions, True))
        bal_mode = QComboBox()
        options = ["Easy", "Advanced", "Experimental"]
        bal_mode.addItems(options)

        grid = QGridLayout(d)
        add_widget(
            grid,
            "Hide Replaced",
            heir_hide_replaced,
            1,  
            "Hide replaced transactions from will detail and list",
        )
        add_widget(
            grid,
            "Hide Invalidated",
            heir_hide_invalidated,
            2,
            "Hide invalidated transactions from will detail and list",
        )
        add_widget(
            grid,
            "Calendar App",
            BalLineEdit(self.CALENDAR_APP),
            3,
            "Default app used to open calendar",
        )
        add_widget(
            grid,
            "Event summary",
            BalLineEdit(self.EVENT_SUMMARY),
            4,
            (
                "Default message to be used in event summary\n"
                 "Variables:\n"
                 "  $wallet_name: name of wallet\n"
                 "  $heirs_complete: list of heirs name,address,amount\n"
                 #"  $will_details_complete: will details(id transaction, mining fees, willexecutor, willexecutor fees, locktime)\n"
             )
        )
        add_widget(
            grid,
            "Event sescription",
            BalTextEdit(self.EVENT_DESCRIPTION),
            5,
            (
                "Default message to be used in event description\n"
                 "Variables:\n"
                 "  $wallet_name: name of wallet\n"
                 "  $heirs_complete: list of heirs name,address,amount\n"
                 #"  $will_details_complete: will details(id transaction, mining fees, willexecutor, willexecutor fees, locktime)\n"
             )
        )
        #add_widget(grid, "Bal Mode", bal_mode, 4, "choose bal mode")

        # add_widget(
        #    grid,
        #    "Ping Willexecutors",
        #    heir_ping_willexecutors,
        #    3,
        #    "Ping willexecutors to get payment info before compiling will",
        # )
        # add_widget(
        #    grid,
        #    " - Ask before",
        #    heir_ask_ping_willexecutors,
        #    4,
        #    "Ask before to ping willexecutor",
        # )
        # add_widget(
        #    grid,
        #    "Backup Transaction",
        #    heir_no_willexecutor,
        #    5,
        #    "Add transactions without willexecutor",
        # )
        # add_widget(grid,"Enable Multiverse(EXPERIMENTAL/BROKEN)",heir_enable_multiverse,6,"enable multiple locktimes, will import.... ")
        grid.addWidget(heir_repush, 7, 0)
        grid.addWidget(
            HelpButton(
                "Broadcast all transactions to willexecutors including those already pushed"
            ),
            7,
            2,
        )

        if ret := bool(d.exec()):
            try:
                self.update_all()
                return ret
            except Exception:
                pass
        return False

    def broadcast_transactions(self, force):
        for _k, w in self.bal_windows.items():
            w.broadcast_transactions(force)

    def update_all(self):
        for _k, w in self.bal_windows.items():
            w.update_all()

    def get_window_title(self, title):
        return _("BAL - ") + _(title)


class shown_cv:
    _type = bool

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class BalWindow:
    def __init__(self, bal_plugin: "BalPlugin", window: "ElectrumWindow"):
        self.bal_plugin = bal_plugin
        self.window = window
        self.heirs = {}
        self.will = {}
        self.willitems = {}
        self.willexecutors = {}
        self.will_settings = None
        self.ok = False
        self.disable_plugin = True
        self.bal_plugin.get_decimal_point = self.window.get_decimal_point

        if self.window.wallet:
            self.wallet = self.window.wallet
            if not self.will_settings:
                self.will_settings = self.bal_plugin.WILL_SETTINGS.get()
                Util.fix_will_settings_tx_fees(self.will_settings)
            self.heirs = Heirs(self.wallet)

            self.heirs_tab = self.create_heirs_tab()
            self.will_tab = self.create_will_tab()
            self.heirs_tab.wallet = self.wallet
            self.will_tab.wallet = self.wallet

    def init_menubar_tools(self, tools_menu):
        self.tools_menu = tools_menu

        def add_optional_tab(tabs, tab, icon, description):
            tab.tab_icon = icon
            tab.tab_description = description
            tab.tab_pos = len(tabs)
            if tab.is_shown_cv.get():
                tabs.addTab(tab, icon, description.replace("&", ""))

        def add_toggle_action(tab):
            is_shown = tab.is_shown_cv.get()
            tab.menu_action = self.window.view_menu.addAction(
                tab.tab_description, lambda: self.window.toggle_tab(tab)
            )
            tab.menu_action.setCheckable(True)
            tab.menu_action.setChecked(is_shown)

        add_optional_tab(
            self.window.tabs,
            self.heirs_tab,
            read_QIcon_from_bytes(self.bal_plugin.read_file("icons/heir.png")),
            _("&Heirs"),
        )
        add_optional_tab(
            self.window.tabs,
            self.will_tab,
            read_QIcon_from_bytes(self.bal_plugin.read_file("icons/will.png")),
            _("&Will"),
        )
        tools_menu.addSeparator()
        self.tools_menu.willexecutors_action = tools_menu.addAction(
            _("&Will-Executors"), self.show_willexecutor_dialog
        )
        self.window.view_menu.addSeparator()
        add_toggle_action(self.heirs_tab)
        add_toggle_action(self.will_tab)

    def load_willitems(self):
        self.willitems = {}
        for wid, w in self.will.items():
            self.willitems[wid] = WillItem(w, wallet=self.wallet)
        if self.willitems:
            self.will_list_widget.will = self.willitems
            self.will_list_widget.update_will(self.willitems)
            self.will_tab.update()

    def save_willitems(self):
        keys = list(self.will.keys())
        for k in keys:
            del self.will[k]
        for wid, w in self.willitems.items():
            self.will[wid] = w.to_dict()

    def init_will(self):
        _logger.info("********************init_____will____________**********")
        if not self.willexecutors:
            self.willexecutors = Willexecutors.get_willexecutors(
                self.bal_plugin, update=False, bal_window=self
            )
        if not self.heirs:
            self.heirs = Heirs._validate(Heirs(self.wallet))
            self.heirs_tab.update()
        if not self.will:
            self.will = self.wallet.db.get_dict("will")
            Util.fix_will_tx_fees(self.will)
            if self.will:
                self.willitems = {}
                try:
                    self.load_willitems()
                except Exception:
                    self.disable_plugin = True
                    self.show_warning(
                        _("Please restart Electrum to activate the BAL plugin"),
                        title=_("Success"),
                    )
                    self.close_wallet()
                    return

        # if not self.will_settings:
        #    self.will_settings = self.wallet.db.get_dict("will_settings")
        #    Util.fix_will_settings_tx_fees(self.will_settings)

        #    _logger.info("will_settings: {}".format(self.will_settings))
        #    if not self.will_settings:
        #        Util.copy(self.will_settings, self.bal_plugin.default_will_settings())
        #        _logger.debug("not_will_settings {}".format(self.will_settings))
        #    self.bal_plugin.validate_will_settings(self.will_settings)
        #    self.heir_list_widget.update_will_settings()
        #    self.heir_list_widget.update()

    def init_wizard(self):
        wizard_dialog = BalWizardDialog(self)
        wizard_dialog.exec()

    def show_willexecutor_dialog(self):
        self.willexecutor_dialog = WillExecutorDialog(self)
        self.willexecutor_dialog.show()

    def create_heirs_tab(self):
        if not self.heirs:
            self.heirs = Heirs(self.wallet)
        self.heir_list_widget = HeirListWidget(self, self.window)
        tab = self.window.create_list_tab(self.heir_list_widget)
        tab.is_shown_cv = shown_cv(False)
        return tab

    def create_will_tab(self):
        self.will_list_widget = PreviewList(self, self.window, None)
        tab = self.window.create_list_tab(self.will_list_widget)
        tab.is_shown_cv = shown_cv(True)
        return tab

    def new_heir_dialog(self, heir_key=None):
        heir = self.heirs.get(heir_key)
        title = "New heir"
        if heir:
            title = f"Edit: {heir_key}"

        d = BalDialog(
            self.window, self.bal_plugin, self.bal_plugin.get_window_title(_(title))
        )

        vbox = QVBoxLayout(d)
        grid = QGridLayout()

        heir_name = QLineEdit()
        heir_name.setFixedWidth(32 * char_width_in_lineedit())
        heir_address = QLineEdit()
        heir_address.setFixedWidth(32 * char_width_in_lineedit())
        heir_amount = PercAmountEdit(self.window.get_decimal_point)

        if heir:
            heir_name.setText(str(heir_key))
            heir_address.setText(str(heir[0]))
            heir_amount.setText(
                str(Util.decode_amount(heir[1], self.window.get_decimal_point()))
            )
            self.heir_locktime = LockTimeWidget(self, self.window, heir[2])

        # heir_is_xpub = QCheckBox()

        new_heir_button = QPushButton(_("Add another heir"))
        self.add_another_heir = False

        def new_heir():
            self.add_another_heir = True
            d.accept()

        new_heir_button.clicked.connect(new_heir)
        new_heir_button.setDefault(True)

        grid.addWidget(QLabel(_("Name")), 1, 0)
        grid.addWidget(heir_name, 1, 1)
        grid.addWidget(HelpButton(_("Unique name or description about heir")), 1, 2)

        grid.addWidget(QLabel(_("Address")), 2, 0)
        grid.addWidget(heir_address, 2, 1)
        grid.addWidget(HelpButton(_("heir bitcoin address")), 2, 2)

        grid.addWidget(QLabel(_("Amount")), 3, 0)
        grid.addWidget(heir_amount, 3, 1)
        grid.addWidget(HelpButton(_("Fixed or Percentage amount if end with %")), 3, 2)

        locktime_label = QLabel(_("Locktime"))
        enable_multiverse = self.bal_plugin.ENABLE_MULTIVERSE.get()
        if enable_multiverse:
            grid.addWidget(locktime_label, 4, 0)
            grid.addWidget(self.heir_locktime, 4, 1)
            grid.addWidget(HelpButton(_("locktime")), 4, 2)

        vbox.addLayout(grid)
        buttons = [CancelButton(d), OkButton(d)]
        if not heir:
            buttons.append(new_heir_button)
        vbox.addLayout(Buttons(*buttons))
        while d.exec():
            # TODO SAVE HEIR
            heir = [
                heir_name.text(),
                heir_address.text(),
                Util.encode_amount(heir_amount.text(), self.window.get_decimal_point()),
                str(self.will_settings["locktime"]),
            ]
            try:
                self.set_heir(heir)
                if self.add_another_heir:
                    self.new_heir_dialog()
                break
            except Exception as e:
                self.show_error(str(e))

    def set_heir(self, heir):
        heir = list(heir)
        if not self.bal_plugin.ENABLE_MULTIVERSE.get():
            heir[3] = self.will_settings["locktime"]

        h = Heirs.validate_heir(heir[0], heir[1:])
        self.heirs[heir[0]] = h
        self.heir_list_widget.update()
        return True

    def delete_heirs(self, heirs):
        for heir in heirs:
            try:
                del self.heirs[heir]
            except Exception as e:
                _logger.debug(f"error deleting heir: {heir} {e}")
                pass
        self.heirs.save()
        self.heir_list_widget.update()
        return True

    def import_heirs(self):
        import_meta_gui(
            self.window,
            _("heirs"),
            self.heirs.import_file,
            self.heir_list_widget.update,
        )

    def export_heirs(self):
        export_meta_gui(self.window, "heirs.json", self.heirs.export_file)

    def prepare_will(self, ignore_duplicate=False, keep_original=False):
        will = self.build_inheritance_transaction(
            ignore_duplicate=ignore_duplicate, keep_original=keep_original
        )
        return will

    def delete_not_valid(self, txid, s_utxo):
        raise NotImplementedError()

    def update_will(self, will):
        Will.update_will(self.willitems, will)
        self.willitems.update(will)
        Will.normalize_will(self.willitems, self.wallet)

    def build_will(self, ignore_duplicate=True, keep_original=True):
        _logger.debug("building will...")
        will = {}
        # willtodelete = []
        # willtoappend = {}
        try:
            self.willexecutors = Willexecutors.get_willexecutors(
                self.bal_plugin, update=False, bal_window=self
            )
            if not self.no_willexecutor:

                f = False
                for _u, w in self.willexecutors.items():
                    if Willexecutors.is_selected(w):
                        f = True
                if not f:
                    _logger.error("No Will-Executor or backup transaction selected")
                    raise NoWillExecutorNotPresent(
                        "No Will-Executor or backup transaction selected"
                    )
            txs = self.heirs.get_transactions(
                self.bal_plugin,
                self.window.wallet,
                self.will_settings["baltx_fees"],
                None,
                self.date_to_check,
            )

            _logger.info(f"txs built: {txs}")
            creation_time = time.time()
            if txs:
                for txid in txs:
                    # txtodelete = []
                    _break = False
                    tx = {}
                    tx["tx"] = txs[txid]
                    tx["my_locktime"] = txs[txid].my_locktime
                    tx["heirsvalue"] = txs[txid].heirsvalue
                    tx["description"] = txs[txid].description
                    tx["willexecutor"] = copy.deepcopy(txs[txid].willexecutor)
                    tx["status"] = _("New")
                    tx["baltx_fees"] = txs[txid].tx_fees
                    tx["time"] = creation_time
                    tx["heirs"] = copy.deepcopy(txs[txid].heirs)
                    tx["txchildren"] = []
                    will[txid] = WillItem(tx, _id=txid, wallet=self.wallet)
                self.update_will(will)
            else:
                _logger.info("No transactions was built")
                _logger.info(f"will-settings: {self.will_settings}")
                _logger.info(f"date_to_check:{self.date_to_check}")
                _logger.info(f"heirs: {self.heirs}")
                return {}
        except Exception as e:
            _logger.info(f"Exception build_will: {e}")
            raise e
            pass
        return self.willitems

    def check_will(self):
        return Will.is_will_valid(
            self.willitems,
            self.block_to_check,
            self.date_to_check,
            self.will_settings["baltx_fees"],
            self.window.wallet.get_utxos(),
            heirs=self.heirs,
            willexecutors=self.willexecutors,
            self_willexecutor=self.no_willexecutor,
            wallet=self.wallet,
            callback_not_valid_tx=self.delete_not_valid,
        )

    def show_message(self, text):
        self.window.show_message(text)

    def show_warning(self, text, parent=None):
        self.window.show_warning(text, parent=None)

    def show_error(self, text):
        self.window.show_error(text)

    def show_critical(self, text):
        self.window.show_critical(text)

    def update_combo_setting_widgets(
        self,
        new_value,
        field,
        update_all=False,
        update_will_dialog=False,
        update_heirs_dialog=False,
    ):
        if (update_all or update_will_dialog) and hasattr(self,'will_list_widget'):
            self.update_widget_combo(self.will_list_widget,field,new_value)
        if update_all or update_heirs_dialog and hasattr(self,'heir_list_widget'):
            self.update_widget_combo(self.heir_list_widget,field,new_value)


    def update_widget_combo(self,widget,field,value):
        try:
            widget.will_settings_widget.widgets[field].set_index(value)
        except Exception as _e:
            pass
    def update_widget_value(self, widget, field, value):
        try:
            widget.will_settings_widget.widgets[field].set_value(value)
        except Exception as _e:
            pass

    def update_setting_widgets(
        self,
        new_value,
        field,
        update_all=False,
        update_will_dialog=False,
        update_heirs_dialog=False,
    ):
        if update_all or update_heirs_dialog:
            self.update_widget_value(self.heir_list_widget, field, new_value)
        if update_all or update_will_dialog:
            self.update_widget_value(self.will_list_widget, field, new_value)
        self.will_settings[field] = new_value
        self.bal_plugin.WILL_SETTINGS.set(self.will_settings)

    def init_heirs_to_locktime(self, multiverse=False):
        #pass
        for heir in self.heirs:
            h = self.heirs[heir]
            if not multiverse:
                self.heirs[heir] = [h[0], h[1], self.will_settings["locktime"]]

    def init_class_variables(self):
        if not self.heirs:
            raise NoHeirsException(_("Heirs are not defined"))
        try:
            self.date_to_check = BalTimestamp(self.will_settings['threshold']).to_timestamp()
            # found = False
            self.locktime_blocks = self.bal_plugin.LOCKTIME_BLOCKS.get()
            self.current_block = Util.get_current_height(self.wallet.network)
            self.block_to_check = 0
            self.no_willexecutor = self.bal_plugin.NO_WILLEXECUTOR.get()
            self.willexecutors = Willexecutors.get_willexecutors(
                self.bal_plugin, update=True, bal_window=self, task=False
            )
            if self.date_to_check < datetime.now().timestamp():
                raise CheckAliveError(self.date_to_check)

            self.init_heirs_to_locktime(self.bal_plugin.ENABLE_MULTIVERSE.get())

        except Exception as e:
            log_error(e )
            _logger.error(f"init_class_variables: {e}")

            raise e

    def build_inheritance_transaction(self, ignore_duplicate=True, keep_original=True):
        try:
            if self.disable_plugin:
                _logger.info("plugin is disabled")
                return
            if not self.heirs:
                _logger.warning("not heirs {}".format(self.heirs))
                return
            try:
                self.init_class_variables()
                Will.check_amounts(
                    self.heirs,
                    self.willexecutors,
                    self.window.wallet.get_utxos(),
                    self.date_to_check,
                    self.window.wallet.dust_threshold(),
                )
            except AmountException as e:
                self.show_warning(
                    _(
                        f"In the inheritance process, the entire wallet will always be fully emptied. Your settings require an adjustment of the amounts.{e}"
                    )
                )
            except CheckAliveError:
                self.show_error(
                    _(
                        "CheckAlive is in the past please update it to a date in the future but less than locktime"
                    )
                )
                return
            locktime = Util.parse_locktime_string(self.will_settings["locktime"])
            if locktime < self.date_to_check:
                self.show_error(_("locktime is lower than threshold"))
                return
            if not self.no_willexecutor:
                f = False
                for _k, we in self.willexecutors.items():
                    if Willexecutors.is_selected(we):
                        f = True
                if not f:
                    self.show_error(
                        _(" no backup transaction or willexecutor selected")
                    )
                    return

            try:
                self.check_will()
            except WillExpiredException:
                self.invalidate_will()
                return
            except NoHeirsException:
                return
            except NotCompleteWillException as e:
                _logger.info("{}:{}".format(type(e), e))
                message = False
                if isinstance(e, HeirChangeException):
                    message = "Heirs changed:"
                elif isinstance(e, WillExecutorNotPresent):
                    message = "Will-Executor not present:"
                elif isinstance(e, WillexecutorChangeException):
                    message = "Will-Executor changed"
                elif isinstance(e, TxFeesChangedException):
                    message = "Txfees are changed"
                elif isinstance(e, HeirNotFoundException):
                    message = "Heir not found"

                if message:
                    self.show_message(
                        f"{_(message)}:\n {e}\n{_('will have to be built')}"
                    )

                _logger.info("build will")
                self.build_will(ignore_duplicate, keep_original)

                try:
                    self.check_will()
                    for wid, _w in self.willitems.items():
                        self.wallet.set_label(wid, "BAL Transaction")
                except WillExpiredException as e:
                    self.invalidate_will()
                except NotCompleteWillException as e:
                    self.show_error(
                        "Error:{}\n {}".format(
                            str(e),
                            _("Please, check your heirs, locktime and threshold!"),
                        )
                    )

                self.window.history_list.update()
                self.window.utxo_list.update()
            self.update_all()
            return self.willitems
        except Exception as e:
            raise e

    def show_transaction_real(
        self,
        tx: Transaction,
        *,
        parent: "ElectrumWindow",
        prompt_if_unsaved: bool = False,
        external_keypairs: Mapping[bytes, bytes] = None,
        payment_identifier: "PaymentIdentifier" = None,
    ):
        try:
            d = TxDialog(
                tx,
                parent=parent,
                prompt_if_unsaved=prompt_if_unsaved,
                external_keypairs=external_keypairs,
                # payment_identifier=payment_identifier,
            )
            d.setWindowIcon(
                read_QIcon_from_bytes(self.bal_plugin.read_file("icons/bal16x16.png"))
            )
        except SerializationError as e:
            _logger.error("unable to deserialize the transaction")
            parent.show_critical(
                _("Electrum was unable to deserialize the transaction:") + "\n" + str(e)
            )
        else:
            d.show()
            return d

    def show_transaction(self, tx=None, txid=None, parent=None):
        if not parent:
            parent = self.window
        if txid is not None and txid in self.willitems:
            tx = self.willitems[txid].tx
        if not tx:
            raise Exception(_("no tx"))
        return self.show_transaction_real(tx, parent=parent)

    def invalidate_will(self):
        def on_success(result):
            if result:
                self.show_message(
                    _(
                        "Please sign and broadcast this transaction to invalidate current will"
                    )
                )
                self.wallet.set_label(result.txid(), "BAL Invalidate")
                self.show_transaction(result)
            else:
                self.show_message(_("No transactions to invalidate"))

        def on_failure(exec_info):
            log_error(exec_info, self.bal_window)

        fee_per_byte = self.will_settings.get("baltx_fees", 1)
        task = partial(Will.invalidate_will, self.willitems, self.wallet, fee_per_byte)
        msg = _("Calculating Transactions")
        self.waiting_dialog = BalWaitingDialog(
            self, msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def sign_transactions(self, password):
        try:
            txs = {}
            signed = None
            tosign = None

            def get_message():
                msg = ""
                if signed:
                    msg = _(f"signed: {signed}\n")
                return msg + _(f"signing: {tosign}")

            for txid in Will.only_valid(self.willitems):
                wi = self.willitems[txid]
                tx = copy.deepcopy(wi.tx)
                if wi.get_status("COMPLETE"):
                    txs[txid] = tx
                    continue
                tosign = txid
                try:
                    self.waiting_dialog.update(get_message())
                except Exception:
                    pass
                for txin in tx.inputs():
                    prevout = txin.prevout.to_json()
                    if prevout[0] in self.willitems:
                        change = self.willitems[prevout[0]].tx.outputs()[prevout[1]]
                        txin._trusted_value_sats = change.value
                        try:
                            txin.script_descriptor = change.script_descriptor
                        except Exception:
                            pass
                        txin.is_mine = True
                        txin._TxInput__address = change.address
                        txin._TxInput__scriptpubkey = change.scriptpubkey
                        txin._TxInput__value_sats = change.value

                self.wallet.sign_transaction(tx, password, ignore_warnings=True)
                signed = tosign
                # is_complete = False
                if tx.is_complete():
                    # is_complete = True
                    wi.set_status("COMPLETE", True)
                txs[txid] = tx
        except Exception:
            return None
        return txs

    def get_wallet_password(self, message=None, parent=None):
        parent = self.window if not parent else parent
        password = None
        if self.wallet.has_keystore_encryption():
            password = self.bal_plugin.password_dialog(parent=parent, msg=message)
            if password is None:
                return False
            try:
                self.wallet.check_password(password)
            except Exception as e:
                self.show_error(str(e))
                password = self.get_wallet_password(message)
        return password

    def on_close(self):
        try:
            if not self.disable_plugin:
                close_window = BalBuildWillDialog(self)
                close_window.build_will_task()
                self.save_willitems()
                self.heirs_tab.close()
                self.will_tab.close()
                self.tools_menu.removeAction(self.tools_menu.willexecutors_action)
                self.window.toggle_tab(self.heirs_tab)
                self.window.toggle_tab(self.will_tab)
                self.window.tabs.update()
        except Exception:
            pass

    def ask_password_and_sign_transactions(self, callback=None):
        def on_success(txs):
            if txs:
                for txid, tx in txs.items():
                    self.willitems[txid].tx = copy.deepcopy(tx)
                    self.will[txid] = self.willitems[txid].to_dict()
                try:
                    self.will_list_widget.update()
                except Exception:
                    pass
                if callback:
                    try:
                        callback()
                    except Exception as e:
                        raise e

        def on_failure(exec_info):
            log_error(exec_info, self.bal_window)

        password = self.get_wallet_password()
        task = partial(self.sign_transactions, password)
        msg = _("Signing transactions...")
        self.waiting_dialog = BalWaitingDialog(
            self, msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def broadcast_transactions(self, force=False):
        def on_success(sulcess):
            self.will_list_widget.update()
            if sulcess:
                _logger.info("error, some transaction was not sent")
                self.show_warning(_("Some transaction was not broadcasted"))
                return
            _logger.debug("OK, sulcess transaction was sent")
            self.show_message(
                _("All transactions are broadcasted to respective Will-Executors")
            )

        def on_failure(exec_info):
            log_error(exec_info, self.bal_window)
            # a,b,c = err
            # _logger.error(f"fail to broadcast transactions:{err}")
            # _logger.error(f"error: {b}")
            # _logger.error("traceback ")
            # tb = c
            # while tb is not None:
            #    frame = tb.tb_frame
            #    _logger.error("file:", frame.f_code.co_filename)
            #    _logger.error("name:", frame.f_code.co_name)
            #    _logger.error("line:", tb.tb_lineno)
            #    _logger.error("lasti:", tb.tb_lasti)
            #    tb = tb.tb_next

        task = partial(self.push_transactions_to_willexecutors, force)
        msg = _("Selecting Will-Executors")
        self.waiting_dialog = BalWaitingDialog(
            self, msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def push_transactions_to_willexecutors(self, force=False):
        willexecutors = Willexecutors.get_willexecutor_transactions(self.willitems)

        def getMsg(willexecutors):
            msg = "Broadcasting Transactions to Will-Executors:\n"
            for url in willexecutors:
                msg += f"{url}:\t{willexecutors[url]['broadcast_status']}\n"
            return msg

        error = False
        for url in willexecutors:
            if self.waiting_dialog._stopping:
                return
            willexecutor = willexecutors[url]
            self.waiting_dialog.update(getMsg(willexecutors))
            if "txs" in willexecutor:
                try:
                    if Willexecutors.push_transactions_to_willexecutor(
                        willexecutors[url]
                    ):
                        for wid in willexecutors[url]["txsids"]:
                            self.willitems[wid].set_status("PUSHED", True)
                        willexecutors[url]["broadcast_status"] = _("Success")
                    else:
                        for wid in willexecutors[url]["txsids"]:
                            self.willitems[wid].set_status("PUSH_FAIL", True)
                            error = True
                        willexecutors[url]["broadcast_status"] = _("Failed")
                    del willexecutor["txs"]
                except Willexecutors.AlreadyPresentException:
                    for wid in willexecutor["txsids"]:
                        if self.waiting_dialog._stopping:
                            return
                        self.waiting_dialog.update(
                            "checking {} - {} : {}".format(
                                self.willitems[wid].we["url"], wid, "Waiting"
                            )
                        )
                        w = self.willitems[wid]
                        w.set_check_willexecutor(
                            Willexecutors.check_transaction(wid, w.we["url"])
                        )
                        self.waiting_dialog.update(
                            "checked {} - {} : {}".format(
                                self.willitems[wid].we["url"],
                                wid,
                                self.willitems[wid].get_status("CHECKED"),
                            )
                        )

        if error:
            return True

    def export_json_file(self, path):
        for wid in self.willitems:
            self.willitems[wid].set_status("EXPORTED", True)
            self.will[wid] = self.willitems[wid].to_dict()
        write_json_file(path, self.will)

    def export_will(self):
        try:
            export_meta_gui(self.window, "will.json", self.export_json_file)
        except Exception as e:
            self.show_error(str(e))
            raise e

    def import_will(self):
        def sulcess():
            self.will_list_widget.update_will(self.willitems)

        import_meta_gui(self.window, _("will"), self.import_json_file, sulcess)

    def import_json_file(self, path):
        try:
            data = read_json_file(path)
            willitems = {}
            for k, v in data.items():
                data[k]["tx"] = tx_from_any(v["tx"])
                willitems[k] = WillItem(data[k], _id=k)
            self.update_will(willitems)
        except Exception as e:
            raise e
            # raise FileImportFailed(_("Invalid will file"))

    def check_transactions_task(self, will):
        start = time.time()
        for wid, w in will.items():
            if self.waiting_dialog._stopping:
                return
            if w.we:
                self.waiting_dialog.update(
                    "checking transaction: {}\n willexecutor: {}".format(wid, w.we["url"])
                )

                w.set_check_willexecutor(Willexecutors.check_transaction(wid, w.we["url"]))

        if time.time() - start < 3:
            time.sleep(3 - (time.time() - start))

    def check_transactions(self, will):
        def on_success(result):
            if hasattr(self,"waiting_dialog"):
                del self.waiting_dialog
            self.update_all()
            pass

        def on_failure(exec_info):
            log_error(exec_info, self)
            # _logger.error(f"error checking transactions {e}")
            # pass

        task = partial(self.check_transactions_task, will)
        msg = _("Check Transaction")
        self.waiting_dialog = BalWaitingDialog(
            self, msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def update_willexecutor_list_widget(self, parent, willexecutors):
        try:
            parent.willexecutors_list.update(willexecutors)
            parent.will_executor_list_widget.update()
        except Exception as e:
            _logger.error(f"impossible to update will_executor_list_widget {e}")
        self.will_executors.update()

    def download_list(self, willexecutors, fn_on_success, fn_on_failure=None):

        def on_success(result):
            self.willexecutors.update(result)
            fn_on_success(result)

        def on_failure(exec_info):
            fn_on_failure(exec_info)

        if fn_on_failure is None:
            fn_on_failure = log_error
        welist_server = self.bal_plugin.WELIST_SERVER.get()
        task = partial(Willexecutors.download_list, willexecutors, welist_server)
        msg = _(f"Downloading willexecutors list from {welist_server}")
        self.waiting_dialog = BalWaitingDialog(
            self, msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def ping_willexecutors_task(self, wes):
        _logger.info("ping willexecutots task")
        pinged = []
        failed = []

        def get_title():
            msg = _("Ping Will-Executors:")
            msg += "\n\n"
            for url in wes:
                urlstr = "{:<50}: ".format(url[:50])
                if url in pinged:
                    urlstr += "Ok"
                elif url in failed:
                    urlstr += "Ko"
                else:
                    urlstr += "--"
                urlstr += "\n"
                msg += urlstr

            return msg

        for url, we in wes.items():
            try:
                self.waiting_dialog.update(get_title())
            except Exception:
                pass
            wes[url] = Willexecutors.get_info_task(url, we)
            if wes[url]["status"] == "KO":
                failed.append(url)
            else:
                pinged.append(url)

    def ping_willexecutors(self, wes, fn_on_success, fn_on_failure=None):
        def on_success(result):
            fn_on_success(result)

        def on_failure(exec_info):
            fn_on_failure(exec_info)

        if not fn_on_failure:
            fn_on_failure = log_error
        _logger.info("ping willexecutors")
        task = partial(self.ping_willexecutors_task, wes)
        msg = _("Ping Will-Executors")
        self.waiting_dialog = BalWaitingDialog(
            self, msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def preview_modal_dialog(self):
        self.dw = WillDetailDialog(self)
        self.dw.show()

    def update_all(self):
        try:
            Will.add_willtree(self.willitems)
            all_utxos = self.wallet.get_utxos()
            utxos_list = Will.utxos_strs(all_utxos)
            Will.check_invalidated(self.willitems, utxos_list, self.wallet)

            self.will_list_widget.update_will(self.willitems)
            self.heirs_tab.update()
            self.will_tab.update()
            self.will_list_widget.update()
        except Exception as e:
            _logger.error(f"error while updating window: {e}")


def add_widget(grid, label, widget, row, help_):
    grid.addWidget(QLabel(_(label)), row, 0)
    grid.addWidget(widget, row, 1)
    grid.addWidget(HelpButton(help_), row, 2)


class ClickableLabel(QLabel):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class BalTxFeesWidget(QWidget):
    valueChanged = pyqtSignal()
    current_value = None

    def __init__(self, bal_window, parent, value=None):
        super().__init__(parent)
        self.bal_window = bal_window
        layout = QHBoxLayout(self)
        self.txfee_widget = QSpinBox(self)
        self.txfee_widget.setMinimum(1)
        self.txfee_widget.setMaximum(10000)
        value = (
            value
            if value
            else self.bal_window.bal_plugin.WILL_SETTINGS.get()["baltx_fees"]
        )
        self.set_value(value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "baltx_fees"
        ]
        self.txfee_widget.valueChanged.connect(self.on_heir_tx_fees)
        #label = ClickableLabel("＄")
        #label.doubleClicked.connect(self.doubleclick)
        #layout.addWidget(label)
        button = HelpButton(_("mining fees expressed in sats/vbyte to be used in the Bitcoin transaction.\nHigher value ensure your transaction will be confirmed"))
        button.setText("丰")
        button.setStyleSheet("font-size: 16px;")
        layout.addWidget(button)
        layout.addWidget(self.txfee_widget)

    def doubleclick(self, event=None):
        pass
    def get_value(self):
        return self.txfee_widget.value()

    def set_value(self, value, emit=True):
        value = int(value) if value is not None else 20
        if getattr(self, "_updating", False):
            return

        self._updating = True
        try:
            self.current_value = value
            spin = self.txfee_widget
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

        finally:
            self._updating = False

        if emit:
            spin.valueChanged.emit(value)

    def on_heir_tx_fees(self, value=None, update_all=True):
        if value != self.current_value:
            try:
                self.set_value(value)
                if update_all:
                    self.bal_window.update_setting_widgets(
                        self.get_value(), "baltx_fees", True
                    )
            except Exception as e:
                _logger.error(f"error while trying to update txfees{e}")
                log_error(e)
        else:
            pass


class _LockTimeEditor:
    min_allowed_value = NLOCKTIME_MIN
    max_allowed_value = NLOCKTIME_MAX
    alarm = None

    def get_value(self) -> Optional[int]:
        raise NotImplementedError()

    def set_value(self, x: Any, force=True) -> None:
        raise NotImplementedError()

    @classmethod
    def is_acceptable_locktime(cls, x: Any) -> bool:
        if not x:  # e.g. empty string
            return True
        try:
            x = int(x)
        except Exception as _e:
            return False
        return cls.min_allowed_value <= x <= cls.max_allowed_value

    @staticmethod
    def get_max_allowed_timestamp() -> int:
        ts = NLOCKTIME_MAX
        # Test if this value is within the valid timestamp limits (which is platform-dependent).
        # see #6170
        try:
            datetime.fromtimestamp(ts)
        except (OSError, OverflowError):
            ts = 2**31 - 1  # INT32_MAX
            datetime.fromtimestamp(ts)  # test if raises
        return ts


class BalTimeEditWidget(QWidget, _LockTimeEditor):
    valueEdited = pyqtSignal()
    _setting_locktime = False
    current_value = None
    current_index = None
    default_value = None

    help_text = (
        "if you choose Raw, you can insert various options based on suffix:\n"
        + " - d: number of days after current day(ex: 1d means tomorrow)\n"
        + " - y: number of years after currrent day(ex: 1y means one year from today)\n"
    )
    label_text = None
    base_field = None

    def __init__(self, bal_window, parent, default_locktime=None):
        super().__init__(parent)
        self.bal_window = bal_window

        hbox = QHBoxLayout()
        self.setLayout(hbox)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        self.setMinimumWidth(40 * char_width_in_lineedit())
        self.locktime_raw_e = TimeRawEditWidget(self, time_edit=self)
        self.locktime_date_e = LockTimeDateEdit(self, time_edit=self)
        self.editors = [self.locktime_raw_e, self.locktime_date_e]
        self.combo = QComboBox()
        options = [_("Raw"), _("Date")]
        self.option_index_to_editor_map = {
            0: self.locktime_raw_e,
            1: self.locktime_date_e,
        }
        self.combo.addItems(options)
        default_index = 0
        if not default_locktime:
            default_locktime = self.bal_window.bal_plugin.WILL_SETTINGS.get()[self.base_field]
        try:
            int(default_locktime)
            default_index = 1
        except Exception:
            default_index = 0
        #hbox.addWidget(QLabel(self.label_text))
        help_button=HelpButton(self.help_text)
        help_button.setText(self.label_text)
        #help_button.setStyleSheet("font-size: 155555);
        hbox.addWidget(help_button)
        self.combo.currentIndexChanged.connect(self.on_current_index_changed)

        for w in self.editors:
            w.setVisible(False)
            w.setEnabled(False)

        self.editor = self.option_index_to_editor_map[default_index]
        self.editor.setVisible(True)
        self.editor.setEnabled(True)
        self.set_index(default_index)
        #self.on_current_index_changed(default_index)
        self.set_value(default_locktime)
        self.current_value=default_locktime
        hbox.addWidget(self.combo)
        for w in self.editors:
            hbox.addWidget(w)

        hbox.addStretch(1)
        # spssscer_widget = QWidget()
        # spacer_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # hbox.addWidget(spacer_widget)
        self.valueEdited.connect(lambda: self.update_will_settings(True))
        self.locktime_raw_e.editingFinished.connect(self.valueEdited.emit)
        self.locktime_date_e.dateTimeChanged.connect(self.valueEdited.emit)
        #self.combo.currentIndexChanged.connect(self.valueEdited.emit)

    def update_will_settings(
        self,
        update_all=False,
        update_will_dialog=False,
        update_heirs_dialog=False,
    ):
        self.bal_window.update_setting_widgets(
            self.get_value(),
            self.base_field,
            update_all,
            update_will_dialog,
            update_heirs_dialog,
        )

    def on_current_index_changed(self, i):
        self.current_index = i
        for w in self.editors:
            w.setVisible(False)
            w.setEnabled(False)
        # prev_locktime = self.editor.get_value()
        self.editor = self.option_index_to_editor_map[i]
        if i==0:
            self.editor.set_value(self.bal_window.bal_plugin.default_will_settings_relative()[self.base_field])
        else:
            self.editor.set_value(self.bal_window.bal_plugin.default_will_settings_absolute()[self.base_field])
        self.valueEdited.emit()
        # if self.editor.is_acceptable_locktime(prev_locktime):
        #    self.editor.set_value(prev_locktime, force=False)
        self.editor.setVisible(True)
        self.editor.setEnabled(True)
        self.bal_window.update_combo_setting_widgets(i, self.base_field,True)

    def get_value(self) -> Optional[str]:
        val = self.editor.get_value()
        #return self.current_value
        return val

    def set_index(self, index):
        if self.current_index != index:
            self.combo.setCurrentIndex(index)
            #self.on_current_index_changed(index, force)

    def set_value(
        self,
        x: Any,
        force=None,
        update_all=False,
        update_will_dialog=False,
        update_heirs_dialog=False,
    ) -> None:
        if not x:
            if self.current_index == 0:
                x = self.bal_window.bal_plugin.default_will_settings_relative()[self.base_field]
            elif self.current_index == 1:
                x = self.bal_window.bal_plugin.default_will_settings_absolute()[self.base_field]
        if x != self.get_value():
            self.editor.set_value(x)
            self.current_value = x
            self.bal_window.update_setting_widgets(x, self.base_field)


class TimeRawEditWidget(QWidget):
    editingFinished = pyqtSignal()

    def is_acceptable_locktime(self, value):
        return True

    def __init__(self, parent, time_edit=None):
        super().__init__(parent)
        self.editor = LockTimeRawEdit(parent, time_edit)
        self.label = QLabel("")
        self.label.setFixedWidth(10 * char_width_in_lineedit())
        self.layout = QHBoxLayout(self)
        self.layout.addWidget(self.editor)
        self.layout.addWidget(self.label)
        self.editor.editingFinished.connect(self.editingFinished.emit)
        self.get_value = self.editor.get_value
        self.set_value = self.editor.set_value


class LockTimeRawEdit(QLineEdit, _LockTimeEditor):
    def __init__(self, parent=None, time_edit=None):
        QLineEdit.__init__(self, parent)
        self.setFixedWidth(12 * char_width_in_lineedit())
        self.textChanged.connect(self.numbify)
        self.isdays = False
        self.isyears = False
        self.isblocks = False
        self.time_edit = time_edit

    @staticmethod
    def replace_str(text):
        return str(text).replace("d", "").replace("y", "").replace("b", "")

    def checkbdy(self, s, pos, appendix):
        try:
            charpos = pos - 1
            charpos = max(0, charpos)
            charpos = min(len(s) - 1, charpos)
            if appendix == s[charpos]:
                s = self.replace_str(s) + appendix
                pos = charpos
        except Exception:
            pass
        return pos, s

    def numbify(self):
        text = self.text().strip()
        # chars = '0123456789bdy' removed the option to choose locktime by block
        chars = "0123456789dy"
        pos = self.cursorPosition()
        pos = len("".join([i for i in text[:pos] if i in chars]))
        s = "".join([i for i in text if i in chars])
        self.isdays = False
        self.isyears = False
        self.isblocks = False

        pos, s = self.checkbdy(s, pos, "d")
        pos, s = self.checkbdy(s, pos, "y")
        pos, s = self.checkbdy(s, pos, "b")

        if "d" in s:
            self.isdays = True
        if "y" in s:
            self.isyears = True
        if "b" in s:
            self.isblocks = True

        if self.isdays:
            s = self.replace_str(s) + "d"
        if self.isyears:
            s = self.replace_str(s) + "y"
        if self.isblocks:
            s = self.replace_str(s) + "b"
        self.blockSignals(True)
        self.setText(s)
        self.blockSignals(False)
        # self.set_value(s, force=False)
        self.current_value = s
        # setText sets Modified to False.  Instead we want to remember
        # if updates were because of user modification.
        self.setModified(self.hasFocus())
        self.setCursorPosition(pos)

    def get_value(self) -> Optional[str]:
        try:
            return str(self.text())
        except Exception:
            return None

    def set_value(self, x: Any, force=True) -> None:
        if x != self.get_value():
            self.blockSignals(True)
            self.setText(str(x))
            self.blockSignals(False)
            self.numbify()


class LockTimeDateEdit(QDateTimeEdit, _LockTimeEditor):
    min_allowed_value = NLOCKTIME_BLOCKHEIGHT_MAX + 1
    max_allowed_value = _LockTimeEditor.get_max_allowed_timestamp()

    def __init__(self, parent=None, time_edit=None):
        QDateTimeEdit.__init__(self, parent)
        self.setMinimumDateTime(datetime.fromtimestamp(self.min_allowed_value))
        self.setMaximumDateTime(datetime.fromtimestamp(self.max_allowed_value))
        #self.setDateTime(QDateTime.currentDateTime())
        self.time_edit = time_edit

    def get_value(self) -> Optional[int]:
        #dt = self.dateTime().toPyDateTime()
        #locktime = int(time.mktime(dt.timetuple()))
        #p#
        #dt = dt_edit.dateTime()
        ## QDateTimets = dt.toSecsSinceEpoch()

        dt = self.dateTime()
        _ts = dt.toSecsSinceEpoch()

        return _ts


    def set_value(self, x: Any, force=False) -> None:
        if not self.is_acceptable_locktime(x):
            self.setDateTime(QDateTime.currentDateTime())
            return
        try:
            x = int(x)
        except Exception as e:
            x = QDateTime.currentDateTime().timestamp()
        finally:
            _dt = datetime.fromtimestamp(x)
            #if self.alarm != dt:
            self.setDateTime(_dt)
            self.alarm = _dt


class ThresholdTimeWidget(BalTimeEditWidget):
    help_text = (
        "Check to ask for invalidation.\n\n"
        "When less then this time is missing, ask to invalidate.\n"
        "If you fail to invalidate during this time, your transactions will be delivered to your heirs.\n\n"
        f"{BalTimeEditWidget.help_text}"
    )
    label_text = "🚨"
    #label_text = "Check Alive"
    base_field = "threshold"

    def __init__(self, bal_window, parent, init_value=None):
        if init_value is None:
            init_value = bal_window.bal_plugin.WILL_SETTINGS.get()["threshold"]
        super().__init__(bal_window, parent, init_value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "threshold"
        ]


class LockTimeWidget(BalTimeEditWidget):
    help_text = (
        "Set Locktime for transactions.\n"
        "Any time is needed transaction will be anticipated by 1day\n"
        f"{BalTimeEditWidget.help_text}"
    )
    label_text = "🚛"
    #label_text = "Locktime"
    base_field = "locktime"

    def __init__(self, bal_window, parent, init_value=None):
        if init_value is None:
            init_value = bal_window.bal_plugin.WILL_SETTINGS.get()["locktime"]
        super().__init__(bal_window, parent, init_value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "locktime"
        ]


class WillSettingsWidget(QWidget):

    def __init__(self, bal_window: "BalWindow", parent, layout_type="h"):
        self.widgets = {}
        QWidget.__init__(self, parent)
        self.bal_window = bal_window
        box = QHBoxLayout(self) if layout_type == "h" else QVBoxLayout(self)

        self.calendar_button = QPushButton()
        self.calendar_button.setIcon(
            read_QIcon_from_bytes(
                self.bal_window.bal_plugin.read_file("icons/calendar.png")
            )
        )
        self.calendar_button.clicked.connect(self.open_or_save_calendar)
        self.widgets["locktime"] = LockTimeWidget(bal_window, self)
        self.widgets["threshold"] = ThresholdTimeWidget(bal_window, self)
        self.widgets["locktime"].valueEdited.connect(self.on_locktime_change)
        self.widgets["threshold"].valueEdited.connect(self.on_locktime_change)
        # self.widgets['baltx_fees'].valueChange.connect(self.bal_window.update_setting_widgets)
        self.on_locktime_change()
        self.widgets["baltx_fees"] = BalTxFeesWidget(bal_window, self)
        if not hasattr(bal_window, "txfee_widgets"):
            bal_window.txfee_widgets = []

        w = self.widgets["baltx_fees"]
        if w not in bal_window.txfee_widgets:
            bal_window.txfee_widgets.append(w)
        box.addWidget(self.widgets["locktime"])
        box.addWidget(self.widgets["threshold"])
        box.addWidget(self.calendar_button)
        box.addWidget(self.widgets["baltx_fees"])

    def create_alarms(self, alarm_start, alarm_end):
        days = (alarm_end - alarm_start).days+1
        lines = []
        for i in range(1, days):
            lines.extend(
                [
                    "BEGIN:VALARM",
                    f"TRIGGER;RELATED=END:-P{i}D",
                    "ACTION:DISPLAY",
                    # f"DESCRIPTION:{self.bal_window.bal_plugin.ALARM_DESCRIPTION.get()}",
                    "END:VALARM",
                ]
            )
        return lines

    def open_or_save_calendar(self):
        now = BalCalendar.format_time(datetime.now())

        locktime = self.widgets["locktime"].alarm
        threshold = self.widgets["threshold"].alarm
        alarm_end = BalCalendar.format_time(locktime)
        alarm_start = BalCalendar.format_time(threshold)
        days_difference = (locktime - threshold).days

        heirs_details = "\r\n".join(f" {heir} - {self.bal_window.heirs[heir][0]}, {self.bal_window.heirs[heir][1]}" for heir in self.bal_window.heirs)
        event_description = BalCalendar.ical_escape(
                f"{self.bal_window.bal_plugin.EVENT_DESCRIPTION.get()}".replace("$wallet_name",str(self.bal_window.wallet)).replace("$heirs_complete",heirs_details)
        )
        #event_description =f"{event_description}{heirs_details}"
        uid = f"bal-{str(self.bal_window.wallet)}"
        summary = BalCalendar.ical_escape(
            f"{self.bal_window.bal_plugin.EVENT_SUMMARY.get()}".replace("$wallet_name",str(self.bal_window.wallet))
        )
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:-//Bitcoin After Life//Electrum Plugin/{BalPlugin.__version__}",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{alarm_end}",
            f"DTEND:{alarm_end}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{event_description}",
        ]
        lines.extend(self.create_alarms(threshold, locktime))
        lines.extend([
            "END:VEVENT",
            "END:VCALENDAR",
        ])

        lines = [s.rstrip("\r\n") for s in lines]
        ics_content = "\r\n".join(lines) + "\r\n"
        self.temp_path = BalCalendar.write_temp_ics(ics_content)
        opened = BalCalendar.open_with_default_app(
            self.bal_window.bal_plugin.CALENDAR_APP.get(), self.temp_path
        )
        if opened:
            _logger.info(f"File opened with default app: {self.temp_path}")
        else:
            export_meta_gui(
                self.bal_window.window, f"will_event.ics",self.save_to_cwd

            )


    def save_to_cwd(self,filename="event.ics"):
        target = os.path.abspath(filename)
        # se il file esiste, sovrascrive
        _logger.debug(f"save_to_cwd {self.temp_path},{filename}")
        with open(self.temp_path, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
        return target

    def on_locktime_change(self):
        locktime = self.widgets["locktime"].get_value()
        threshold = self.widgets["threshold"].get_value()
        locktime = BalTimestamp(locktime)
        threshold = BalTimestamp(threshold)

        min_locktime = min(
                Will.get_min_locktime(self.bal_window.willitems, NLOCKTIME_MAX),
                locktime.to_timestamp(),
        )
        td = threshold.to_date(min_locktime, True)
        self.widgets["threshold"].alarm=td
        self.bal_window.will_settings["real_threshold"]=td.timestamp()
        try:
            self.widgets["threshold"].editor.label.setText(td.strftime("%Y-%m-%d"))
        except Exception as _e:
            pass

        td = locktime.to_date()
        alarm = BalTimestamp(min_locktime).to_date()
        self.widgets["locktime"].alarm=alarm
        self.bal_window.will_settings["real_locktime"]=td.timestamp()
        try:
            self.widgets["locktime"].editor.label.setText(td.strftime("%Y-%m-%d"))
        except Exception as _e:
            pass


class PercAmountEdit(BTCAmountEdit):
    def __init__(self, decimal_point, is_int=False, parent=None, *, max_amount=None):
        super().__init__(decimal_point, is_int, parent, max_amount=max_amount)

    def numbify(self):
        text = self.text().strip()
        if text == "!":
            self.shortcut.emit()
            return
        pos = self.cursorPosition()
        chars = "0123456789%"
        chars += DECIMAL_POINT

        s = "".join([i for i in text if i in chars])

        if "%" in s:
            self.is_perc = True
            s = s.replace("%", "")
        else:
            self.is_perc = False

        if DECIMAL_POINT in s:
            p = s.find(DECIMAL_POINT)
            s = s.replace(DECIMAL_POINT, "")
            s = s[:p] + DECIMAL_POINT + s[p : p + 8]
        if self.is_perc:
            s += "%"

        self.setText(s)
        self.setModified(self.hasFocus())
        self.setCursorPosition(pos)

    def _get_amount_from_text(self, text: str) -> Union[None, Decimal, int]:
        try:
            text = text.replace(DECIMAL_POINT, ".")
            text = text.replace("%", "")
            return (Decimal)(text)
        except Exception:
            return None

    def _get_text_from_amount(self, amount):
        out = super()._get_text_from_amount(amount)
        if self.is_perc:
            out += "%"
        return out

    def paintEvent(self, event):
        QLineEdit.paintEvent(self, event)
        if self.base_unit:
            panel = QStyleOptionFrame()
            self.initStyleOption(panel)
            textRect = self.style().subElementRect(
                QStyle.SubElement.SE_LineEditContents, panel, self
            )
            textRect.adjust(2, 0, -10, 0)
            painter = QPainter(self)
            painter.setPen(ColorScheme.GRAY.as_color())
            if len(self.text()) == 0:
                painter.drawText(
                    textRect,
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    self.base_unit() + " or perc value",
                )


class BalDialog(QDialog,MessageBoxMixin):
    _stopping = False
    def __init__(self, parent, bal_plugin, title=None, icon="icons/bal16x16.png"):
        import signal
        from PyQt6.QtCore import QMetaObject, Qt
        from PyQt6.QtWidgets import QApplication
        def handler(signum, frame):
            QMetaObject.invokeMethod(self, "close", Qt.ConnectionType.QueuedConnection)

        #signal.signal(signal.SIGINT, handler)
        self.parent = parent
        self.thread = None
        super().__init__(parent) 
        if title:
            self.setWindowTitle(title)
        # WindowModalDialog.__init__(self,parent)
        self.setWindowIcon(read_QIcon_from_bytes(bal_plugin.read_file(icon)))
        
    def closeEvent(self, event):
        self._stopping = True
        #if self.thread:
        #    self.thread.stop()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._stopping = True
        #if self.thread:
        #    self.thread.stop()
        super().hideEvent(event)

class BalWizardDialog(BalDialog):
    def __init__(self, bal_window: "BalWindow"):
        assert bal_window
        BalDialog.__init__(
            self, bal_window.window, bal_window.bal_plugin, _("Bal Wizard Setup")
        )
        self.setMinimumSize(800, 400)
        self.bal_window = bal_window
        self.parent = bal_window.window
        self.layout = QVBoxLayout(self)
        self.widget = BalWizardHeirsWidget(
            bal_window, self, self.on_next_heir, None, self.on_cancel_heir
        )
        self.layout.addWidget(self.widget)

    def next_widget(self, widget):
        self.layout.removeWidget(self.widget)
        self.widget.close()
        self.widget = widget
        self.layout.addWidget(self.widget)
        # self.update()
        # self.repaint()

    def on_next_heir(self):
        self.next_widget(
            BalWizardLocktimeAndFeeWidget(
                self.bal_window,
                self,
                self.on_next_locktimeandfee,
                self.on_previous_heir,
                self.on_cancel_heir,
            )
        )

    def on_previous_heir(self):
        self.next_widget(
            BalWizardHeirsWidget(
                self.bal_window, self, self.on_next_heir, None, self.on_cancel_heir
            )
        )

    def on_cancel_heir(self):
        pass

    def on_next_wedonwload(self):
        self.next_widget(
            BalWizardWEWidget(
                self.bal_window,
                self,
                self.on_next_we,
                self.on_next_locktimeandfee,
                self.on_cancel_heir,
            )
        )

    def on_next_we(self):
        close_window = BalBuildWillDialog(self.bal_window)
        close_window.build_will_task()
        self.close()
        # self.next_widget(BalWizardLocktimeAndFeeWidget(self.bal_window,self,self.on_next_locktimeandfee,self.on_next_wedonwload,self.on_next_wedonwload.on_cancel_heir))

    def on_next_locktimeandfee(self):
        self.next_widget(
            BalWizardWEDownloadWidget(
                self.bal_window,
                self,
                self.on_next_wedonwload,
                self.on_next_heir,
                self.on_cancel_heir,
            )
        )

    def on_accept(self):
        self.bal_window.update_all()
        pass

    def on_reject(self):
        pass

    def on_close(self):
        self.bal_window.update_all()
        pass

    def closeEvent(self, event):
        self._stopping = True
        # self.bal_window.heir_list_widget.will_settings_widget.update_will_settings()
        pass


class BalWizardWidget(QWidget):
    title = None
    message = None

    def __init__(
        self, bal_window: "BalWindow", parent, on_next, on_previous, on_cancel
    ):
        QWidget.__init__(self, parent)
        self.vbox = QVBoxLayout(self)
        self.bal_window = bal_window
        self.parent = parent
        self.on_next = on_next
        self.on_cancel = on_cancel
        self.titleLabel = QLabel(self.title)
        self.vbox.addWidget(self.titleLabel)
        self.messageLabel = QLabel(_(self.message))
        self.vbox.addWidget(self.messageLabel)

        self.content = self.get_content()
        self.content_container = QWidget()
        self.containrelayout = QVBoxLayout(self.content_container)
        self.containrelayout.addWidget(self.content)

        self.vbox.addWidget(self.content_container)

        spacer_widget = QWidget()
        spacer_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.vbox.addWidget(spacer_widget)

        self.buttons = []
        if on_previous:
            self.on_previous = on_previous
            self.previous_button = QPushButton(_("Previous"))
            self.previous_button.clicked.connect(self._on_previous)
            self.buttons.append(self.previous_button)

        self.next_button = QPushButton(_("Next"))
        self.next_button.clicked.connect(self._on_next)
        self.buttons.append(self.next_button)

        self.abort_button = QPushButton(_("Cancel"))
        self.abort_button.clicked.connect(self._on_cancel)
        self.buttons.append(self.abort_button)

        self.vbox.addLayout(Buttons(*self.buttons))

    def _on_cancel(self):
        self.on_cancel()
        self.parent.close()

    def _on_next(self):
        if self.validate():
            self.on_next()

    def _on_previous(self):
        self.on_previous()

    def get_content(self):
        pass

    def validate(self):
        return True


class BalWizardHeirsWidget(BalWizardWidget):
    title = "Bitcoin After Life Heirs"
    message = (
        "Please add your heirs\n remember that 100% of wallet balance will be spent"
    )

    def get_content(self):
        self.heir_list_widget = HeirListWidget(self.bal_window, self)
        button_add = QPushButton(_("Add"))
        button_add.clicked.connect(self.add_heir)
        button_import = QPushButton(_("Import"))
        button_import.clicked.connect(self.import_from_file)
        button_export = QPushButton(_("Export"))
        button_export.clicked.connect(self.export_to_file)
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.addWidget(self.heir_list_widget)
        vbox.addLayout(Buttons(button_add, button_import, button_export))
        return widget

    def import_from_file(self):
        self.bal_window.import_heirs()
        self.heir_list_widget.update()

    def export_to_file(self):
        self.bal_window.export_heirs()

    def add_heir(self):
        self.bal_window.new_heir_dialog()
        self.heir_list_widget.update()

    def validate(self):
        return True


class BalWizardWEDownloadWidget(BalWizardWidget):
    title = _("Bitcoin After Life Will-Executors")
    message = _("Choose willexecutors download method")

    def get_content(self):
        # question = QLabel()
        self.combo = QComboBox()
        self.combo.addItems(
            [
                "Automatically download and select willexecutors",
                "Only download willexecutors list",
                "Import willexecutor list from file",
                "Manual",
            ]
        )
        # heir_name.setFixedWidth(32 * char_width_in_lineedit())
        return self.combo

    def validate(self):
        return True

    def _on_next(self):

        index = self.combo.currentIndex()
        _logger.debug(f"selected index:{index}")
        if index < 3:
            self.bal_window.willexecutors = Willexecutors.get_willexecutors(
                self.bal_window.bal_plugin
            )

            if index == 2:

                def do_nothing():
                    self.bal_window.willexecutors.update(self.willexecutors)
                    Willexecutors.save(
                        self.bal_window.bal_plugin, self.bal_window.willexecutors
                    )
                    pass

                import_meta_gui(
                    self.bal_window.window,
                    _("willexecutors"),
                    self.import_json_file,
                    do_nothing,
                )

            if index < 2:

                def on_success(willexecutors):
                    def ping_on_success(result):
                        ping_on_done()

                    def ping_on_failure(exec_info):
                        ping_on_done()

                    def ping_on_done():
                        if index < 1:
                            for we in self.bal_window.willexecutors:
                                if self.bal_window.willexecutors[we]["status"] == 200:
                                    self.bal_window.willexecutors[we]["selected"] = True
                        Willexecutors.save(
                            self.bal_window.bal_plugin, self.bal_window.willexecutors
                        )

                    self.bal_window.ping_willexecutors(
                        self.bal_window.willexecutors, ping_on_success, ping_on_failure
                    )

                self.bal_window.download_list(self.bal_window.willexecutors, on_success)

        elif index == 3:
            # TODO DO NOTHING
            pass

        self.bal_window.will_list_widget.update()
        if self.validate():
            return self.on_next()

    def import_json_file(self, path):
        data = read_json_file(path)
        data = self._validate(data)
        self.willexecutors = data

    def _validate(self, data):
        return data


class BalWizardWEWidget(BalWizardWidget):
    title = "Bitcoin After Life Will-Executors"
    message = _("Configure and select your willexecutors")

    def get_content(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.addWidget(
            WillExecutorWidget(
                self,
                self.bal_window,
                Willexecutors.get_willexecutors(self.bal_window.bal_plugin),
            )
        )
        return widget


class BalWizardLocktimeAndFeeWidget(BalWizardWidget):
    title = "Bitcoin After Life Will Settings"
    message = _("")

    def get_content(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(WillSettingsWidget(self.bal_window, self, "v"))
        spacer_widget = QWidget()
        spacer_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(spacer_widget)
        return widget


class BalWaitingDialog(BalDialog):
    updatemessage = pyqtSignal([str], arguments=["message"])

    def __init__(
        self,
        bal_window: "BalWindow",
        message: str,
        task,
        on_success=None,
        on_error=None,
        on_cancel=None,
        exe=True,
    ):
        assert bal_window
        BalDialog.__init__(
            self, bal_window.window, bal_window.bal_plugin, _("Please wait")
        )
        self.message_label = QLabel(message)
        vbox = QVBoxLayout(self)
        vbox.addWidget(self.message_label)
        self.updatemessage.connect(self.update_message)
        if on_cancel:
            self.cancel_button = CancelButton(self)
            self.cancel_button.clicked.connect(on_cancel)
            vbox.addLayout(Buttons(self.cancel_button))
        self.accepted.connect(self.on_accepted)
        self.task = task
        self.on_success = on_success
        self.on_error = on_error
        self.on_cancel = on_cancel
        if exe:
            self.exe()

    def exe(self):
        self.thread = TaskThread(self)
        self.thread.finished.connect(self.deleteLater)  # see #3956
        self.thread.finished.connect(self.finished)
        self.thread.add(self.task, self.on_success, self.accept, self.on_error)
        self.exec()

    def hello(self):
        pass

    def finished(self):
        pass


    def on_accepted(self):
        pass

    def update_message(self, msg):
        self.message_label.setText(msg)

    def update(self, msg):
        self.updatemessage.emit(msg)

    def getText(self):
        return self.message_label.text()



class BalBlockingWaitingDialog(BalDialog):
    def __init__(self, bal_window: "BalWindow", message: str, task: Callable[[], Any]):
        BalDialog.__init__(self, bal_window, bal_window.bal_plugin, _("Please wait"))
        self.message_label = QLabel(message)
        vbox = QVBoxLayout(self)
        vbox.addWidget(self.message_label)
        self.finished.connect(self.deleteLater)  # see #3956
        # show popup
        self.show()
        # refresh GUI; needed for popup to appear and for message_label to get drawn
        # QCoreApplication.processEvents()
        # QCoreApplication.processEvents()
        try:
            # block and run given task
            task()
        finally:
            # close popup
            self.accept()

class BalLineEdit(QLineEdit):
    def __init__(self,variable):
        QLineEdit.__init__(self)
        self.setText(variable.get())
        def on_edit():
            variable.set(self.text())
        self.editingFinished.connect(on_edit)

class BalTextEdit(QTextEdit):
    def __init__(self,variable):
        QTextEdit.__init__(self)
        self.setPlainText(variable.get())
        def on_edit():
            variable.set(self.toPlainText())
        self.textChanged.connect(on_edit)

class BalCheckBox(QCheckBox):
    def __init__(self, variable, on_click=None):
        QCheckBox.__init__(self)
        self.setChecked(variable.get())
        self.on_click = on_click

        def on_check(v):
            variable.set(v == 2)
            #variable.get()
            if self.on_click:
                self.on_click()

        self.stateChanged.connect(on_check)


class BalBuildWillDialog(BalDialog):
    updatemessage = pyqtSignal()
    COLOR_WARNING = "#cfa808"
    COLOR_ERROR = "#ff0000"
    COLOR_OK = "#05ad05"

    def __init__(self, bal_window, parent=None):
        if not parent:
            parent = bal_window.window
        BalDialog.__init__(self, parent, bal_window.bal_plugin, _("Building Will"))
        self.parent = parent
        self.updatemessage.connect(self.msg_update)
        self.bal_window = bal_window
        self.bal_plugin = bal_window.bal_plugin
        self.message_label = QLabel(_("Building Will:"))
        self.vbox = QVBoxLayout(self)
        self.vbox.addWidget(self.message_label, 0)
        self.qwidget = QWidget(self)
        self.vbox.addWidget(self.qwidget, 1)
        self.labelsbox = QVBoxLayout(self.qwidget)
        self.setMinimumWidth(600)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.labels = []
        self.check_row = None
        self.inval_row = None
        self.build_row = None
        self.sign_row = None
        self.push_row = None
        self.network = Network.get_instance()
        self._stopping = False
        self.thread = TaskThread(self)
        self.thread.finished.connect(self.task_finished)  # see #3956

    def task_finished(self):
        pass

    def build_will_task(self):
        _logger.debug("build will task to be started")
        self.thread.add(
            self.task_phase1,
            on_success=self.on_success_phase1,
            on_done=self.on_accept,
            on_error=self.on_error_phase1,
        )
        self.show()
        self.exec()

    def task_phase1(self):
        if self._stopping:
            return
        txs = None
        _logger.debug("close plugin phase 1 started")
        varrow = self.msg_set_status("checking variables")
        try:
            self.bal_window.init_class_variables()
        except CheckAliveError as cae:
            fee_per_byte = self.bal_window.will_settings.get("baltx_fees", 1)
            tx = Will.invalidate_will(
                self.bal_window.willitems, self.bal_window.wallet, fee_per_byte
            )
            if tx:
                _logger.debug(
                    "during phase1 CAE: {}, Continue to invalidate".format(cae)
                )
                self.msg_set_status("checking variables",varrow, "Check Alive Threshold Passed: you have to Invalidate your old Will",self.COLOR_ERROR)
            else:
                raise cae
            return None, tx
        except NoHeirsException:
            self.msg_set_status("checking variables", varrow,"No Heirs",self.COLOR_ERROR)
            #self.msg_set_checking("No Heirs")
            return False, None
        except Exception as e:
            raise e
        try:
            _logger.debug("checking variables")
            Will.check_amounts(
                self.bal_window.heirs,
                self.bal_window.willexecutors,
                self.bal_window.window.wallet.get_utxos(),
                self.bal_window.date_to_check,
                self.bal_window.window.wallet.dust_threshold(),
            )
            _logger.debug("variables ok")
            self.msg_set_status("checking variables:", varrow, "Ok", self.COLOR_OK)
        except AmountException:
            self.msg_set_checking(
                self.msg_warning(
                    "In the inheritance process, "
                    + "the entire wallet will always be fully emptied. \n"
                    + "Your settings require an adjustment of the amounts"
                )
            )

        self.msg_set_checking()
        have_to_build = False
        try:
            self.bal_window.check_will()
            self.msg_set_checking(self.msg_ok())
        except WillExpiredException:
            _logger.debug("expired")
            self.msg_set_checking("Expired")
            fee_per_byte = self.bal_window.will_settings.get("baltx_fees", 1)
            return None, Will.invalidate_will(
                self.bal_window.willitems, self.bal_window.wallet, fee_per_byte
            )
        except NoHeirsException as e:
            _logger.debug("no heirs")
            self.msg_set_checking("No Heirs")
        except NotCompleteWillException as e:
            _logger.debug(f"not complete {e} true")
            message = False
            have_to_build = True
            if isinstance(e, HeirChangeException):
                message = _("Heirs changed:")
            elif isinstance(e, WillExecutorNotPresent):
                message = _("Will-Executor not present")
            elif isinstance(e, WillexecutorChangeException):
                message = _("Will-Executor changed")
            elif isinstance(e, TxFeesChangedException):
                message = _("Txfees are changed")
            elif isinstance(e, HeirNotFoundException):
                message = _("Heir not found")
            if message:
                _logger.debug(f"message: {message}")
                self.msg_set_checking(message)
            else:
                self.msg_set_checking("New")

        if have_to_build:
            self.msg_set_building()
            try:
                txs = self.bal_window.build_will()
                if not txs:
                    self.msg_set_building(
                        _("Balance is too low, or CheckAlive is in the past.Skipped"),
                        color = self.COLOR_ERROR,
                    )
                    return False, None

                self.bal_window.check_will()
                for wid in Will.only_valid(self.bal_window.willitems):
                    self.bal_window.wallet.set_label(wid, "BAL Transaction")
                self.msg_set_building(self.msg_ok())
            except WillExecutorNotPresent:
                self.msg_set_status(
                    _("Will-Executor excluded"), None, _("Skipped"), self.COLOR_ERROR
                )

            except Exception as e:
                self.msg_set_building(self.msg_error(e))
                return False, None

        # excluded_heirs = []
        for wid in Will.only_valid(self.bal_window.willitems):
            heirs = self.bal_window.willitems[wid].heirs
            for hid, heir in heirs.items():
                if "DUST" in str(heir[HEIR_REAL_AMOUNT]):
                    self.msg_set_status(
                        f"{hid},{heir[HEIR_DUST_AMOUNT]} is DUST",
                        None,
                        f"Excluded from will {wid}",
                        self.COLOR_WARNING,
                    )

        have_to_sign = False
        for wid in Will.only_valid(self.bal_window.willitems):
            if not self.bal_window.willitems[wid].get_status("COMPLETE"):
                have_to_sign = True
                break
        return have_to_sign, txs

    def on_accept(self):
        self.bal_window.update_all()
        pass

    def on_accept_phase2(self):
        self.bal_window.update_all()
        pass

    def on_error_push(self):
        pass

    def wait(self, secs):
        wait_row = None
        for i in range(secs, 0, -1):
            if self._stopping:
                return
            wait_row = self.msg_edit_row(_(f"Please wait {i}secs"), wait_row)
            time.sleep(1)
        self.msg_del_row(wait_row)

    def loop_broadcast_invalidating(self, tx):
        if self._stopping:
            return
        self.msg_set_invalidating("Broadcasting")
        try:
            tx.add_info_from_wallet(self.bal_window.wallet)
            self.network.run_from_another_thread(tx.add_info_from_network(self.network))
            txid = self.network.run_from_another_thread(
                self.network.broadcast_transaction(tx, timeout=120), timeout=120
            )
            self.msg_set_invalidating(self.msg_ok())
            if not txid:
                _logger.debug(f"should not be none txid: {txid}")

        except TxBroadcastError as e:
            _logger.error(f"fail to broadcast transaction:{e}")
            msg = e.get_message_for_gui()
            self.msg_set_invalidating(self.msg_error(msg))
        except BestEffortRequestFailed as e:
            self.msg_set_invalidating(self.msg_error(e))

    def loop_push(self):
        if self._stopping:
            return
        self.msg_set_pushing(_("Broadcasting"))
        retry = False
        try:

            willexecutors = Willexecutors.get_willexecutor_transactions(
                self.bal_window.willitems
            )
            for url, willexecutor in willexecutors.items():
                if self._stopping:
                    return
                try:
                    if Willexecutors.is_selected(
                        self.bal_window.willexecutors.get(url)
                    ):
                        _logger.debug(f"{url}: {willexecutor}")
                        if not Willexecutors.push_transactions_to_willexecutor(
                            willexecutor
                        ):
                            for wid in willexecutor["txsids"]:
                                self.bal_window.willitems[wid].set_status(
                                    "PUSH_FAIL", True
                                )
                            retry = True
                        else:
                            for wid in willexecutor["txsids"]:
                                self.bal_window.willitems[wid].set_status(
                                    "PUSHED", True
                                )
                except Willexecutors.AlreadyPresentException:
                    for wid in willexecutor["txsids"]:
                        if self._stopping:
                            return
                        row = self.msg_edit_row(
                            "checking {} - {} : {}".format(
                                self.bal_window.willitems[wid].we["url"], wid, "Waiting"
                            )
                        )
                        self.bal_plugin = self.bal_window.bal_plugin
                        w = self.bal_window.willitems[wid]

                        w.set_check_willexecutor(
                            Willexecutors.check_transaction(wid, w.we["url"])
                        )
                        row = self.msg_edit_row(
                            "checked {} - {} : {}".format(
                                self.bal_window.willitems[wid].we["url"],
                                wid,
                                self.bal_window.willitems[wid].get_status("CHECKED"),
                            ),
                            row,
                        )

                except Exception as e:
                    _logger.error(f"loop push error:{e}")
                    raise e
            if retry:
                raise Exception("retry")

        except Exception as e:
            self.msg_set_pushing(self.msg_error(e))
            self.wait(10)
            if not self._stopping:
                pass
                # self.loop_push()

    def invalidate_task(self, password, bal_window, tx):
        if self._stopping:
            return
        _logger.debug(f"invalidate tx: {tx}")
        # fee_per_byte = bal_window.will_settings.get("baltx_fees", 1)
        tx = self.bal_window.wallet.sign_transaction(tx, password)
        try:
            if tx:
                if tx.is_complete():
                    self.loop_broadcast_invalidating(tx)
                    self.wait(5)
                else:
                    raise Exception("tx not complete")
            else:
                raise Exception("not tx")
        except Exception as e:
            (f"exception:{e}")
            self.msg_set_invalidating(f"Error: {e}")
            raise Exception("Impossible to sign") from e

    def on_success_invalidate(self, success):
        self.thread.add(
            self.task_phase1,
            on_success=self.on_success_phase1,
            on_done=self.on_accept,
            on_error=self.on_error_phase1,
        )

    def on_success_phase1(self, result):
        if self._stopping:
            return
        self.have_to_sign, tx = list(result)
        # if not tx:
        #    self.msg_edit_row(self.msg_error("Error, no tx was built"))
        #    return
        _logger.debug("have to sign {}".format(self.have_to_sign))
        password = None
        if self.have_to_sign is None:
            _logger.debug("have to invalidate")
            self.msg_set_invalidating()
            # need to sign invalidate and restart phase 1

            password = self.bal_window.get_wallet_password(
                _("Invalidate your old will"), parent=self
            )
            if password is False:
                self.msg_set_invalidating(_("Aborted"))
                self.wait(3)
                self.close()
                return
            self.thread.add(
                partial(self.invalidate_task, password, self.bal_window, tx),
                on_success=self.on_success_invalidate,
                on_done=self.on_accept,
                on_error=self.on_error,
            )

            return

        elif self.have_to_sign:
            password = self.bal_window.get_wallet_password(
                _("Sign your will"), parent=self
            )
            if password is False:
                self.msg_set_signing(_("Aborted"))
        else:
            self.msg_set_signing(_("Nothing to do"))
        self.thread.add(
            partial(self.task_phase2, password),
            on_success=self.on_success_phase2,
            on_done=self.on_accept_phase2,
            on_error=self.on_error_phase2,
        )
        return

    def on_success_phase2(self, arg=False):
        self.thread.stop()
        self.bal_window.save_willitems()
        self.msg_edit_row(_("Finished"))
        self.close()

    def closeEvent(self, event):
        self._stopping = True
        self.thread.stop()

    def task_phase2(self, password):
        if self._stopping:
            return
        if self.have_to_sign:
            try:
                if txs := self.bal_window.sign_transactions(password):
                    for txid, tx in txs.items():
                        self.bal_window.willitems[txid].tx = copy.deepcopy(tx)
                    self.bal_window.save_willitems()
                    self.msg_set_signing(self.msg_ok())
            except Exception as e:
                self.msg_set_signing(self.msg_error(e))

        self.msg_set_pushing()
        have_to_push = False
        for wid in Will.only_valid(self.bal_window.willitems):
            w = self.bal_window.willitems[wid]
            if w.we and w.get_status("COMPLETE") and not w.get_status("PUSHED"):
                have_to_push = True
        if not have_to_push:
            self.msg_set_pushing(_("Nothing to do"))
        else:
            try:
                self.loop_push()
                self.msg_set_pushing(self.msg_ok())

            except Exception as e:
                # td = traceback.format_exc()
                self.msg_set_pushing(self.msg_error(e))
        self.msg_edit_row(self.msg_ok())
        self.wait(5)

    def on_error(self, error):
        _logger.error(error)
        pass

    def on_error_phase1(self, error):
        self.bal_window.update_all()
        a, b, c = error
        self.msg_edit_row(self.msg_error(f"Error: {b}"))
        _logger.error(f"error phase1: {b}")
        button=QPushButton(_("Close"))
        button.clicked.connect(self.close)
        self.vbox.addWidget(button)
        self.resize(self.vbox.sizeHint()+button.sizeHint()*2)
        self.repaint()
    def on_error_phase2(self, error):
        self.bal_window.upade_all()
        a, b, c = error
        self.msg_edit_row(self.msg_error(f"Error: {b}"))
        _logger.error(f"error phase2: {b}")

    def msg_set_checking(self, status="Waiting", row=None):
        row = self.check_row if row is None else row
        self.check_row = self.msg_set_status(_("Checking your will"), row, status)

    def msg_set_invalidating(self, status=None, row=None):
        row = self.inval_row if row is None else row
        self.inval_row = self.msg_set_status(
            _("Invalidating old will"), self.inval_row, status
        )

    def msg_set_building(self, status=None, row=None,color=None):
        row = self.build_row if row is None else row
        self.build_row = self.msg_set_status(
            "Building your will", self.build_row, status, color
        )

    def msg_set_signing(self, status=None, row=None):
        row = self.sign_row if row is None else row
        self.sign_row = self.msg_set_status("Signing your will", self.sign_row, status)

    def msg_set_pushing(self, status=None, row=None):
        row = self.push_row if row is None else row
        self.push_row = self.msg_set_status(
            "Broadcasting your will to executors", self.push_row, status
        )

    def msg_set_waiting(self, status=None, row=None):
        row = self.wait_row if row is None else row
        self.wait_row = self.msg_edit_row(f"Please wait {status}secs", self.wait_row)

    def msg_error(self, e):
        return "<font color='{}'>{}</font>".format(self.COLOR_ERROR, e)

    def msg_ok(self, e="Ok"):
        return "<font color='{}'>{}</font>".format(self.COLOR_OK, e)

    def msg_warning(self, e):
        return "<font color='{}'>{}</font".format(self.COLOR_WARNING, e)

    def msg_set_status(self, msg, row=None, status=None, color=None):
        status = "Wait" if status is None else status
        if color is None:
            line = f"{_(msg)}:\t{status}"
        else:
            line = "<font color={}>{}:\t{}</font>".format(color, _(msg), status)
        return self.msg_edit_row(line, row)

    def ask_password(self, msg=None):
        self.password = self.bal_window.get_wallet_password(msg, parent=self)

    def msg_edit_row(self, line, row=None):
        try:
            self.labels[row] = line
        except Exception:
            self.labels.append(line)
            row = len(self.labels) - 1

        self.updatemessage.emit()

        return row

    def msg_del_row(self, row):
        try:
            del self.labels[row]
        except Exception:
            pass
        self.updatemessage.emit()

    # def clear_layout(self,layout):
    #    while layout.count():
    #        item = layout.takeAt(0)
    #        w = item.widget()
    #        if w:
    #            w.setParent(None)
    #            w.deleteLater()

    # def msg_update(self):
    #    self.clear_layout(self.labelsbox)
    #    for label in self.labels:
    #        label=label.replace("\n","<br>")
    #        qlabel=QLabel(label)
    #        qlabel.setWordWrap(True)
    #        self.labelsbox.addWidget(qlabel)

    #    self.labelsbox.activate()
    #    self.qwidget.setMinimumSize(self.labelsbox.sizeHint())
    #    self.qwidget.adjustSize()
    #    from PyQt6.QtWidgets import QApplication
    #    QApplication.processEvents()
    #
    #    self.adjustSize()
    def msg_update(self):
        full_text = "<br><br>".join(self.labels).replace("\n", "<br>")
        self.message_label.setText(full_text)
        self.message_label.adjustSize()
        # self.setMinimumHeight(len(self.labels)*40)
        self.resize(self.sizeHint())

    def get_text(self):
        return self.message_label.text()

    pass


class HeirListWidget(MyTreeView, MessageBoxMixin):
    class Columns(MyTreeView.BaseColumnsEnum):
        NAME = enum.auto()
        ADDRESS = enum.auto()
        AMOUNT = enum.auto()

    headers = {
        Columns.NAME: _("Name"),
        Columns.ADDRESS: _("Address"),
        Columns.AMOUNT: _("Amount"),
    }
    filter_columns = [Columns.NAME, Columns.ADDRESS]

    ROLE_SORT_ORDER = Qt.ItemDataRole.UserRole + 1000

    ROLE_HEIR_KEY = Qt.ItemDataRole.UserRole + 4000
    key_role = ROLE_HEIR_KEY

    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        editor.setText(index.data())

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text())

    def __init__(self, bal_window: "BalWindow", parent):
        super().__init__(
            parent=parent,
            main_window=bal_window.window,
            stretch_column=self.Columns.NAME,
            editable_columns=[
                self.Columns.NAME,
                self.Columns.ADDRESS,
                self.Columns.AMOUNT,
            ],
        )
        self.decimal_point = bal_window.window.get_decimal_point()
        self.bal_window = bal_window

        try:
            self.setModel(QStandardItemModel(self))
            self.sortByColumn(self.Columns.NAME, Qt.SortOrder.AscendingOrder)
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        except Exception:
            pass

        self.setSortingEnabled(True)
        self.std_model = self.model()

        self.update()

    def on_activated(self, idx):
        self.on_double_click(idx)

    def on_double_click(self, idx):
        edit_key = self.get_edit_key_from_coordinate(idx.row(), idx.column())
        self.bal_window.heirs.get(edit_key)
        self.bal_window.new_heir_dialog(edit_key)

    def on_edited(self, idx, edit_key, *, text):
        original = prior_name = self.bal_window.heirs.get(edit_key)
        if not prior_name:
            return
        col = idx.column()
        try:
            if col == 2:
                text = Util.encode_amount(text, self.decimal_point)
            elif col == 0:
                self.bal_window.delete_heirs([edit_key])
                edit_key = text
            prior_name[col - 1] = text
            prior_name.insert(0, edit_key)
            prior_name = tuple(prior_name)
        except Exception:
            prior_name = (
                (edit_key,) + prior_name[: col - 1] + (text,) + prior_name[col:]
            )

        try:
            self.bal_window.set_heir(prior_name)
        except Exception:
            pass

            try:
                self.bal_window.set_heir((edit_key,) + original)
            except Exception:
                self.update()

    def delete_heirs(self, selected_keys):
        self.bal_window.delete_heirs(selected_keys)
        self.update()

    def create_menu(self, position):
        menu = QMenu()
        idx = self.indexAt(position)
        column = idx.column() or self.Columns.NAME
        selected_keys = []
        for s_idx in self.selected_in_column(self.Columns.NAME):
            sel_key = self.model().itemFromIndex(s_idx).data(0)
            selected_keys.append(sel_key)
        if selected_keys and idx.isValid():
            column_title = self.model().horizontalHeaderItem(column).text()
            # ok
            column_data = "\n".join(
                self.model().itemFromIndex(s_idx).text()
                for s_idx in self.selected_in_column(column)
            )
            menu.addAction(
                _("Copy {}").format(column_title),
                lambda: self.place_text_on_clipboard(column_data, title=column_title),
            )
            if column in self.editable_columns:
                item = self.model().itemFromIndex(idx)
                if item.isEditable():
                    persistent = QPersistentModelIndex(idx)
                    menu.addAction(
                        _("Edit {}").format(column_title),
                        lambda p=persistent: self.edit(QModelIndex(p)),
                    )
            menu.addAction(_("Delete"), lambda: self.delete_heirs(selected_keys))
        menu.exec(self.viewport().mapToGlobal(position))

    def update(self):
        current_key = self.get_role_data_for_current_item(
            col=self.Columns.NAME, role=self.ROLE_HEIR_KEY
        )
        self.model().clear()
        self.update_headers(self.__class__.headers)
        set_current = None
        for key in sorted(self.bal_window.heirs.keys()):
            heir = self.bal_window.heirs[key]
            labels = [""] * len(self.Columns)
            labels[self.Columns.NAME] = key
            labels[self.Columns.ADDRESS] = heir[0]
            labels[self.Columns.AMOUNT] = Util.decode_amount(
                heir[1], self.decimal_point
            )

            items = [QStandardItem(x) for x in labels]
            items[self.Columns.NAME].setEditable(True)
            items[self.Columns.ADDRESS].setEditable(True)
            items[self.Columns.AMOUNT].setEditable(True)
            items[self.Columns.NAME].setData(
                key, self.ROLE_HEIR_KEY + self.Columns.NAME
            )
            items[self.Columns.ADDRESS].setData(
                key, self.ROLE_HEIR_KEY + self.Columns.ADDRESS
            )
            items[self.Columns.AMOUNT].setData(
                key, self.ROLE_HEIR_KEY + self.Columns.AMOUNT
            )

            row_count = self.model().rowCount()
            self.model().insertRow(row_count, items)

            if key == current_key:
                idx = self.model().index(row_count, self.Columns.NAME)
                set_current = QPersistentModelIndex(idx)
        try:
            self.will_settings_widget.on_locktime_change()
        except Exception as e:
            pass
        self.set_current_idx(set_current)
        # FIXME refresh loses sort order; so set "default" here:
        self.filter()

    def refresh_row(self, key, row):
        # nothing to update here
        pass

    def get_edit_key_from_coordinate(self, row, col):
        a = self.get_role_data_from_coordinate(row, col, role=self.ROLE_HEIR_KEY + col)
        return a

    def create_toolbar(self, config):
        toolbar, menu = self.create_toolbar_with_menu("")
        menu.addAction(_("&New Heir"), self.bal_window.new_heir_dialog)
        menu.addAction(_("Import"), self.bal_window.import_heirs)
        menu.addAction(_("Export"), lambda: self.bal_window.export_heirs())

        newHeirButton = QPushButton(_("New Heir"))
        newHeirButton.clicked.connect(self.bal_window.new_heir_dialog)

        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        self.will_settings_widget = WillSettingsWidget(self.bal_window, self)

        layout.addWidget(self.will_settings_widget)
        layout.addWidget(newHeirButton)

        toolbar.insertWidget(2, widget)

        return toolbar

    def build_transactions(self):
        # will = self.bal_window.prepare_will()
        self.bal_window.prepare_will()


class PreviewList(MyTreeView, MessageBoxMixin):
    class Columns(MyTreeView.BaseColumnsEnum):
        LOCKTIME = enum.auto()
        TXID = enum.auto()
        WILLEXECUTOR = enum.auto()
        STATUS = enum.auto()

    headers = {
        Columns.LOCKTIME: _("Locktime"),
        Columns.TXID: _("Txid"),
        Columns.WILLEXECUTOR: _("Will-Executor"),
        Columns.STATUS: _("Status"),
    }

    ROLE_HEIR_KEY = Qt.ItemDataRole.UserRole + 2000
    key_role = ROLE_HEIR_KEY

    def createEditor(self, parent, option, index):
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        editor.setText(index.data())

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text())

    def __init__(self, bal_window: "BalWindow", parent, will):
        super().__init__(
            parent=parent,
            main_window=bal_window.window,
            stretch_column=self.Columns.TXID,
        )
        # self.parent = parent
        self.bal_window = bal_window
        self.decimal_point = bal_window.window.get_decimal_point

        if will is not None:
            self.will = will
        else:
            self.will = bal_window.willitems

        try:
            self.setModel(QStandardItemModel(self))
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.sortByColumn(self.Columns.NAME, Qt.SortOrder.AscendingOrder)
        except Exception as e:
            pass

        self.setSortingEnabled(True)
        self.std_model = self.model()

        self.update()

    def on_activated(self, idx):
        self.on_double_click(idx)

    def on_double_click(self, idx):
        idx = self.model().index(idx.row(), self.Columns.TXID)
        sel_key = self.model().itemFromIndex(idx).data(0)
        self.show_transaction([sel_key])

    def create_menu(self, position):
        menu = QMenu()
        idx = self.indexAt(position)
        column = idx.column() or self.Columns.TXID
        selected_keys = []
        for s_idx in self.selected_in_column(self.Columns.TXID):
            sel_key = self.model().itemFromIndex(s_idx).data(0)
            selected_keys.append(sel_key)
        if selected_keys and idx.isValid():
            column_title = self.model().horizontalHeaderItem(column).text()
            # column_data = "\n".join(
            #    self.model().itemFromIndex(s_idx).text()
            #    for s_idx in self.selected_in_column(column)
            # )

            menu.addAction(
                _("details").format(column_title),
                lambda: self.show_transaction(selected_keys),
            ).setEnabled(len(selected_keys) < 2)
            menu.addAction(
                _("check ").format(column_title),
                lambda: self.check_transactions(selected_keys),
            )
            if self.bal_window.bal_plugin.ENABLE_MULTIVERSE.get():
                try:
                    self.importaction = self.menu.addAction(
                        _("Import"), self.import_will
                    )
                except Exception:
                    pass

            menu.addSeparator()
            menu.addAction(
                _("delete").format(column_title), lambda: self.delete(selected_keys)
            )

        menu.exec(self.viewport().mapToGlobal(position))

    def delete(self, selected_keys):
        for key in selected_keys:
            del self.will[key]
            try:
                del self.bal_window.willitems[key]
            except Exception:
                pass
            try:
                del self.bal_window.will[key]
            except Exception:
                pass
        self.update()

    def check_transactions(self, selected_keys):
        wout = {}
        for k in selected_keys:
            wout[k] = self.will[k]
        if wout:
            self.bal_window.check_transactions(wout)
        self.update()

    def show_transaction(self, selected_keys):
        for key in selected_keys:
            self.bal_window.show_transaction(self.will[key].tx)

        self.update()

    def select(self, selected_keys):
        self.selected += selected_keys
        self.update()

    def deselect(self, selected_keys):
        for key in selected_keys:
            self.selected.remove(key)
        self.update()

    def update_will(self, will):
        self.will.update(will)
        self.update()

    def replace(self, set_current, current_key, txid, bal_tx):
        if self.bal_window.bal_plugin._hide_replaced and bal_tx.get_status("REPLACED"):
            return False
        if self.bal_window.bal_plugin._hide_invalidated and bal_tx.get_status(
            "INVALIDATED"
        ):
            return False

        if not isinstance(bal_tx, WillItem):
            bal_tx = WillItem(bal_tx)

        tx = bal_tx.tx

        labels = [""] * len(self.Columns)
        labels[self.Columns.LOCKTIME] = str(BalTimestamp(tx.locktime))
        labels[self.Columns.TXID] = txid
        we = "None"
        if bal_tx.we:
            we = bal_tx.we["url"]
        labels[self.Columns.WILLEXECUTOR] = we
        status = bal_tx.status
        if len(bal_tx.status) > 53:
            status = "...{}".format(status[-50:])
        labels[self.Columns.STATUS] = status

        items = []
        for e in labels:
            if isinstance(e, list):
                try:
                    items.append(QStandardItem(*e))
                except Exception as e:
                    pass
            else:
                items.append(QStandardItem(str(e)))

            items[-1].setBackground(QColor(bal_tx.get_color()))

        row_count = self.model().rowCount()
        self.model().insertRow(row_count, items)
        if txid == current_key:
            idx = self.model().index(row_count, self.Columns.TXID)
            set_current = QPersistentModelIndex(idx)
        self.set_current_idx(set_current)
        return set_current

    def update(self):
        try:
            self.menu.removeAction(self.importaction)
        except Exception:
            pass

        if self.will is None:
            return

        current_key = self.get_role_data_for_current_item(
            col=self.Columns.TXID, role=self.ROLE_HEIR_KEY
        )
        self.model().clear()
        self.update_headers(self.__class__.headers)

        set_current = None
        for txid, bal_tx in self.will.items():
            tmp = self.replace(set_current, current_key, txid, bal_tx)
            if tmp:
                set_current = tmp
        self.sortByColumn(self.Columns.LOCKTIME, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(True)
        try:
            self.will_settings_widget.on_locktime_change()
        except Exception as _e:
            pass

    def create_toolbar(self, config):
        toolbar, menu = self.create_toolbar_with_menu("")
        menu.addAction(_("Prepare"), self.build_transactions)
        menu.addAction(_("Display"), self.bal_window.preview_modal_dialog)
        menu.addAction(_("Sign"), self.ask_password_and_sign_transactions)
        menu.addAction(_("Export"), self.export_will)
        if self.bal_window.bal_plugin.ENABLE_MULTIVERSE.get():
            self.importaction = menu.addAction(_("Import"), self.import_will)
        menu.addAction(_("Broadcast"), self.broadcast)
        menu.addAction(_("Check"), self.check)
        menu.addAction(_("Invalidate"), self.invalidate_will)

        wizard = QPushButton()
        wizard.setIcon(
            read_QIcon_from_bytes(
                self.bal_window.bal_plugin.read_file("icons/wizard.png")
            )
        )
        wizard.clicked.connect(self.bal_window.init_wizard)
        # display = QPushButton(_("Display"))
        # display.clicked.connect(self.bal_window.preview_modal_dialog)

        refresh = QPushButton()
        refresh.setIcon(
            read_QIcon_from_bytes(
                self.bal_window.bal_plugin.read_file("icons/reload.png")
            )
        )
        refresh.clicked.connect(self.check)

        widget = QWidget(self)
        hlayout = QHBoxLayout(widget)
        self.will_settings_widget = WillSettingsWidget(self.bal_window, self)
        hlayout.addWidget(self.will_settings_widget)
        hlayout.addWidget(wizard)
        hlayout.addWidget(refresh)
        toolbar.insertWidget(2, widget)

        self.menu = menu
        self.toolbar = toolbar
        return toolbar

    def hide_replaced(self):
        self.bal_window.bal_plugin.hide_replaced()
        self.update()

    def hide_invalidated(self):
        self.bal_window.bal_plugin.hide_invalidated()
        self.update()

    def build_transactions(self):
        will = self.bal_window.prepare_will()
        if will:
            self.update_will(will)

    def export_json_file(self, path):
        write_json_file(path, self.will)

    def export_will(self):
        self.bal_window.export_will()
        self.update()

    def import_will(self):
        self.bal_window.import_will()

    def ask_password_and_sign_transactions(self):
        self.bal_window.ask_password_and_sign_transactions(callback=self.update)

    def broadcast(self):
        self.bal_window.broadcast_transactions()
        self.update()

    def check(self):
        close_window = BalBuildWillDialog(self.bal_window)
        close_window.build_will_task()

        will = {}
        for wid, w in self.bal_window.willitems.items():
            if (
                w.get_status("VALID")
                and w.get_status("PUSHED")
                and not w.get_status("CHECKED")
            ):
                will[wid] = w
        if will:
            self.bal_window.check_transactions(will)
        self.update()

    def invalidate_will(self):
        self.bal_window.invalidate_will()
        self.update()


# class PreviewDialog(BalDialog, MessageBoxMixin):
#    def __init__(self, bal_window, will):
#        self.parent = bal_window.window
#        BalDialog.__init__(
#            self, bal_window=bal_window, bal_plugin=bal_window.bal_plugin
#        )
#        self.bal_plugin = bal_window.bal_plugin
#        self.gui_object = self.bal_plugin.gui_object
#        self.config = self.bal_plugin.config
#        self.bal_window = bal_window
#        self.wallet = bal_window.window.wallet
#        self.format_amount = bal_window.window.format_amount
#        self.base_unit = bal_window.window.base_unit
#        self.format_fiat_and_units = bal_window.window.format_fiat_and_units
#        self.fx = bal_window.window.fx
#        self.format_fee_rate = bal_window.window.format_fee_rate
#        self.show_address = bal_window.window.show_address
#        if not will:
#            self.will = bal_window.willitems
#        else:
#            self.will = will
#        self.setWindowTitle(_("Transactions Preview"))
#        self.setMinimumSize(1000, 200)
#        self.size_label = QLabel()
#        self.transactions_list = PreviewList(self.bal_window,self, self.will)
#
#        try:
#            self.bal_window.init_class_variables()
#        except Exception as e:
#            _logger.error(f"PreviewDialog Exception: {e}")
#        self.check_will()
#
#        vbox = QVBoxLayout(self)
#        vbox.addWidget(self.size_label)
#        vbox.addWidget(self.transactions_list)
#        buttonbox = QHBoxLayout()
#
#        b = QPushButton(_("Sign"))
#        b.clicked.connect(self.transactions_list.ask_password_and_sign_transactions)
#        buttonbox.addWidget(b)
#
#        b = QPushButton(_("Export Will"))
#        b.clicked.connect(self.transactions_list.export_will)
#        buttonbox.addWidget(b)
#
#        b = QPushButton(_("Broadcast"))
#        b.clicked.connect(self.transactions_list.broadcast)
#        buttonbox.addWidget(b)
#
#        b = QPushButton(_("Invalidate will"))
#        b.clicked.connect(self.transactions_list.invalidate_will)
#        buttonbox.addWidget(b)
#
#        vbox.addLayout(buttonbox)
#
#        self.update()
#
#    def update_will(self, will):
#        self.will.update(will)
#        self.transactions_list.update_will(will)
#        self.update()
#
#    def update(self):
#        self.transactions_list.update()
#
#    def is_hidden(self):
#        return self.isMinimized() or self.isHidden()
#
#    def show_or_hide(self):
#        if self.is_hidden():
#            self.bring_to_top()
#        else:
#            self.hide()
#
#    def bring_to_top(self):
#        self.show()
#        self.raise_()
#
#    def closeEvent(self, event):
#        event.accept()


class WillDetailDialog(BalDialog):
    def __init__(self, bal_window):

        self.will = bal_window.willitems
        self.threshold = bal_window.will_settings["real_threshold"]

        self.bal_window = bal_window
        Will.add_willtree(self.will)
        super().__init__(bal_window.window, bal_window.bal_plugin)
        self.config = bal_window.window.config
        self.wallet = bal_window.wallet
        self.format_amount = bal_window.window.format_amount
        self.base_unit = bal_window.window.base_unit
        self.format_fiat_and_units = bal_window.window.format_fiat_and_units
        self.fx = bal_window.window.fx
        self.format_fee_rate = bal_window.window.format_fee_rate
        self.decimal_point = bal_window.window.get_decimal_point()
        self.base_unit_name = decimal_point_to_base_unit_name(self.decimal_point)
        self.setWindowTitle(_("Will Details"))
        self.setMinimumSize(670, 700)
        self.vlayout = QVBoxLayout()
        w = QWidget()
        hlayout = QHBoxLayout(w)

        b = QPushButton(_("Sign"))
        b.clicked.connect(self.ask_password_and_sign_transactions)
        hlayout.addWidget(b)

        b = QPushButton(_("Broadcast"))
        b.clicked.connect(self.broadcast_transactions)
        hlayout.addWidget(b)

        b = QPushButton(_("Export"))
        b.clicked.connect(self.export_will)
        hlayout.addWidget(b)
        b = QPushButton(_("Invalidate"))
        b.clicked.connect(bal_window.invalidate_will)
        hlayout.addWidget(b)
        self.vlayout.addWidget(w)

        self.paint_scroll_area()
        self.vlayout.addWidget(
            QLabel(_("Expiration date: ") + str(BalTimestamp(self.threshold)))
        )
        self.vlayout.addWidget(self.scrollbox)
        w = QWidget()
        hlayout = QHBoxLayout(w)
        hlayout.addWidget(
            QLabel(_("Valid Txs:") + str(len(Will.only_valid_list(self.will))))
        )
        hlayout.addWidget(QLabel(_("Total Txs:") + str(len(self.will))))
        self.vlayout.addWidget(w)
        self.setLayout(self.vlayout)

    def paint_scroll_area(self):
        self.scrollbox = QScrollArea()
        viewport = QWidget(self.scrollbox)
        self.willlayout = QVBoxLayout(viewport)
        self.detailsWidget = WillWidget(parent=self)
        self.willlayout.addWidget(self.detailsWidget)

        self.scrollbox.setWidget(viewport)
        viewport.setLayout(self.willlayout)

    def ask_password_and_sign_transactions(self):
        self.bal_window.ask_password_and_sign_transactions(callback=self.update)
        self.update()

    def broadcast_transactions(self):
        self.bal_window.broadcast_transactions()
        self.update()

    def export_will(self):
        self.bal_window.export_will()

    def toggle_replaced(self):
        self.bal_window.bal_plugin.hide_replaced()
        toggle = _("Hide")
        if self.bal_window.bal_plugin._hide_replaced:
            toggle = _("Unhide")
        self.toggle_replace_button.setText(f"{toggle} {_('replaced')}")
        self.update()

    def toggle_invalidated(self):
        self.bal_window.bal_plugin.hide_invalidated()
        toggle = _("Hide")
        if self.bal_window.bal_plugin._hide_invalidated:
            toggle = _("Unhide")
        self.toggle_invalidate_button.setText(_(f"{toggle} {_('invalidated')}"))
        self.update()

    def update(self):
        self.will = self.bal_window.willitems
        pos = self.vlayout.indexOf(self.scrollbox)
        self.vlayout.removeWidget(self.scrollbox)
        self.paint_scroll_area()
        self.vlayout.insertWidget(pos, self.scrollbox)
        super().update()


class WillWidget(QWidget):
    def __init__(self, father=None, parent=None):
        super().__init__()
        vlayout = QVBoxLayout()
        self.setLayout(vlayout)
        self.will = parent.bal_window.willitems
        self.parent = parent
        for w in self.will:
            if (
                self.will[w].get_status("REPLACED")
                and self.parent.bal_window.bal_plugin._hide_replaced
            ):
                continue
            if (
                self.will[w].get_status("INVALIDATED")
                and self.parent.bal_window.bal_plugin._hide_invalidated
            ):
                continue
            f = self.will[w].father
            if father == f:
                qwidget = QWidget()
                # childWidget = QWidget()
                hlayout = QHBoxLayout(qwidget)
                qwidget.setLayout(hlayout)
                vlayout.addWidget(qwidget)
                detailw = QWidget()
                detaillayout = QVBoxLayout()
                detailw.setLayout(detaillayout)

                willpushbutton = QPushButton(w)

                willpushbutton.clicked.connect(
                    partial(self.parent.bal_window.show_transaction, txid=w)
                )
                detaillayout.addWidget(willpushbutton)
                locktime = str(BalTimestamp(self.will[w].tx.locktime))
                creation = str(BalTimestamp(self.will[w].time))

                def qlabel(title, value):
                    label = "<b>" + _(str(title)) + f":</b>\t{str(value)}"
                    return QLabel(label)

                detaillayout.addWidget(qlabel("Locktime", locktime))
                detaillayout.addWidget(qlabel("Creation Time", creation))
                try:
                    total_fees = (
                        self.will[w].tx.input_value() - self.will[w].tx.output_value()
                    )
                except Exception:
                    total_fees = -1
                decoded_fees = total_fees
                fee_per_byte = round(total_fees / self.will[w].tx.estimated_size(), 3)
                fees_str = str(decoded_fees) + " (" + str(fee_per_byte) + " sats/vbyte)"
                detaillayout.addWidget(qlabel("Transaction fees:", fees_str))
                detaillayout.addWidget(qlabel("Status:", self.will[w].status))
                detaillayout.addWidget(QLabel(""))
                detaillayout.addWidget(QLabel("<b>Heirs:</b>"))
                for heir in self.will[w].heirs:
                    if 'w!ll3x3c"' not in heir:
                        decoded_amount = Util.decode_amount(
                            self.will[w].heirs[heir][3], self.parent.decimal_point
                        )
                        detaillayout.addWidget(
                            qlabel(
                                heir, f"{decoded_amount} {self.parent.base_unit_name}"
                            )
                        )
                if self.will[w].we:
                    detaillayout.addWidget(QLabel(""))
                    detaillayout.addWidget(QLabel(_("<b>Willexecutor:</b:")))
                    decoded_amount = Util.decode_amount(
                        self.will[w].we["base_fee"], self.parent.decimal_point
                    )

                    detaillayout.addWidget(
                        qlabel(
                            self.will[w].we["url"],
                            f"{decoded_amount} {self.parent.base_unit_name}",
                        )
                    )
                detaillayout.addStretch()
                pal = QPalette()
                pal.setColor(
                    QPalette.ColorRole.Window, QColor(self.will[w].get_color())
                )
                detailw.setAutoFillBackground(True)
                detailw.setPalette(pal)

                hlayout.addWidget(detailw)
                hlayout.addWidget(WillWidget(w, parent=parent))


class WillExecutorListWidget(MyTreeView):
    class Columns(MyTreeView.BaseColumnsEnum):
        SELECTED = enum.auto()
        URL = enum.auto()
        STATUS = enum.auto()
        BASE_FEE = enum.auto()
        INFO = enum.auto()
        ADDRESS = enum.auto()

    headers = {
        Columns.SELECTED: _(""),
        Columns.URL: _("Url"),
        Columns.STATUS: _("S"),
        Columns.BASE_FEE: _("Base fee"),
        Columns.INFO: _("Info"),
        Columns.ADDRESS: _("Default Address"),
    }

    filter_columns = [Columns.URL]

    ROLE_SORT_ORDER = Qt.ItemDataRole.UserRole + 3000
    ROLE_HEIR_KEY = Qt.ItemDataRole.UserRole + 3001
    key_role = ROLE_HEIR_KEY

    def __init__(self, parent: "WillExecutorWidget"):
        super().__init__(
            parent=parent,
            stretch_column=self.Columns.ADDRESS,
            editable_columns=[
                self.Columns.URL,
                self.Columns.BASE_FEE,
                self.Columns.ADDRESS,
                self.Columns.INFO,
            ],
        )
        self.parent = parent
        try:
            self.setModel(QStandardItemModel(self))
            self.sortByColumn(self.Columns.SELECTED, Qt.SortOrder.AscendingOrder)
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        except Exception:
            pass
        self.setSortingEnabled(True)
        self.std_model = self.model()
        self.config = parent.bal_plugin.config
        self.get_decimal_point = parent.bal_plugin.get_decimal_point

        self.update()

    def create_menu(self, position):
        menu = QMenu()
        idx = self.indexAt(position)
        column = idx.column() or self.Columns.URL
        selected_keys = []
        for s_idx in self.selected_in_column(self.Columns.URL):
            sel_key = self.model().itemFromIndex(s_idx).data(0)
            selected_keys.append(sel_key)
        if selected_keys and idx.isValid():
            column_title = self.model().horizontalHeaderItem(column).text()
            # column_data = "\n".join(
            #    self.model().itemFromIndex(s_idx).text()
            #    for s_idx in self.selected_in_column(column)
            # )
            if Willexecutors.is_selected(self.parent.willexecutors_list[sel_key]):
                menu.addAction(
                    _("deselect").format(column_title),
                    lambda: self.deselect(selected_keys),
                )
            else:
                menu.addAction(
                    _("select").format(column_title), lambda: self.select(selected_keys)
                )
            if column in self.editable_columns:
                item = self.model().itemFromIndex(idx)
                if item.isEditable():
                    persistent = QPersistentModelIndex(idx)
                    menu.addAction(
                        _("Edit {}").format(column_title),
                        lambda p=persistent: self.edit(QModelIndex(p)),
                    )

            menu.addAction(
                _("Ping").format(column_title),
                lambda: self.ping_willexecutors(selected_keys),
            )
            menu.addSeparator()
            menu.addAction(
                _("delete").format(column_title), lambda: self.delete(selected_keys)
            )

        menu.exec(self.viewport().mapToGlobal(position))

    def ping_willexecutors(self, selected_keys):
        wout = {}
        for k in selected_keys:
            wout[k] = self.parent.willexecutors_list[k]
        self.parent.update_willexecutors(wout)

        self.parent.save_willexecutors()
        self.update()

    def get_edit_key_from_coordinate(self, row, col):
        role = self.ROLE_HEIR_KEY + col
        a = self.get_role_data_from_coordinate(row, col, role=role)
        return a

    def delete(self, selected_keys):
        for key in selected_keys:
            del self.parent.willexecutors_list[key]

        self.parent.save_willexecutors()
        self.update()

    def select(self, selected_keys):
        for wid, w in self.parent.willexecutors_list.items():
            if wid in selected_keys:
                w["selected"] = True
        self.parent.save_willexecutors()
        self.update()

    def deselect(self, selected_keys):
        for wid, w in self.parent.willexecutors_list.items():
            if wid in selected_keys:
                w["selected"] = False
        self.parent.save_willexecutors()
        self.update()

    def on_edited(self, idx, edit_key, *, text):
        # prior_name = self.parent.willexecutors_list[edit_key]
        col = idx.column()
        try:
            if col == self.Columns.URL:
                self.parent.willexecutors_list[text] = self.parent.willexecutors_list[
                    edit_key
                ]
                del self.parent.willexecutors_list[edit_key]
            if col == self.Columns.BASE_FEE:
                self.parent.willexecutors_list[edit_key]["base_fee"] = (
                    Util.encode_amount(text, self.get_decimal_point())
                )
            if col == self.Columns.ADDRESS:
                self.parent.willexecutors_list[edit_key]["address"] = text
            if col == self.Columns.INFO:
                self.parent.willexecutors_list[edit_key]["info"] = text
            self.parent.save_willexecutors()
            self.update()
        except Exception:
            pass

    def update(self):
        if self.parent.willexecutors_list is None:
            return
        try:
            current_key = self.get_role_data_for_current_item(
                col=self.Columns.URL, role=self.ROLE_HEIR_KEY
            )
            self.model().clear()
            self.update_headers(self.__class__.headers)

            set_current = None

            for url, value in self.parent.willexecutors_list.items():
                labels = [""] * len(self.Columns)
                labels[self.Columns.URL] = url
                if Willexecutors.is_selected(value):

                    labels[self.Columns.SELECTED] = [
                        read_QIcon_from_bytes(
                            self.parent.bal_plugin.read_file("icons/confirmed.png")
                        ),
                        "",
                    ]
                else:
                    labels[self.Columns.SELECTED] = ""
                labels[self.Columns.BASE_FEE] = Util.decode_amount(
                    value.get("base_fee", 0), self.get_decimal_point()
                )
                if str(value.get("status", 0)) == "200":
                    labels[self.Columns.STATUS] = [
                        read_QIcon_from_bytes(
                            self.parent.bal_plugin.read_file(
                                "icons/status_connected.png"
                            )
                        ),
                        "",
                    ]
                else:
                    labels[self.Columns.STATUS] = [
                        read_QIcon_from_bytes(
                            self.parent.bal_plugin.read_file("icons/unconfirmed.png")
                        ),
                        "",
                    ]
                labels[self.Columns.ADDRESS] = str(value.get("address", ""))
                labels[self.Columns.INFO] = str(value.get("info", ""))

                items = []
                for e in labels:
                    if isinstance(e, list):
                        try:
                            items.append(QStandardItem(*e))
                        except Exception as e:
                            pass
                    else:
                        items.append(QStandardItem(e))
                items[self.Columns.SELECTED].setEditable(False)
                items[self.Columns.URL].setEditable(True)
                items[self.Columns.ADDRESS].setEditable(True)
                items[self.Columns.INFO].setEditable(True)
                items[self.Columns.BASE_FEE].setEditable(True)
                items[self.Columns.STATUS].setEditable(False)

                items[self.Columns.URL].setData(
                    url, self.ROLE_HEIR_KEY + self.Columns.URL
                )
                items[self.Columns.BASE_FEE].setData(
                    url, self.ROLE_HEIR_KEY + self.Columns.BASE_FEE
                )
                items[self.Columns.INFO].setData(
                    url, self.ROLE_HEIR_KEY + self.Columns.INFO
                )
                items[self.Columns.ADDRESS].setData(
                    url, self.ROLE_HEIR_KEY + self.Columns.ADDRESS
                )
                row_count = self.model().rowCount()
                self.model().insertRow(row_count, items)
                if url == current_key:
                    idx = self.model().index(row_count, self.Columns.URL)
                    set_current = QPersistentModelIndex(idx)
                self.set_current_idx(set_current)
            self.filter()
        except Exception as e:
            _logger.error(f"error updating willexcutor {e}")
            raise e


class WillExecutorWidget(QWidget, MessageBoxMixin):
    def __init__(self, parent, bal_window, willexecutors=None):
        self.bal_window = bal_window
        self.bal_plugin = bal_window.bal_plugin
        self.parent = parent
        MessageBoxMixin.__init__(self)
        QWidget.__init__(self, parent)
        if willexecutors:
            self.willexecutors_list = willexecutors
        else:
            self.willexecutors_list = Willexecutors.get_willexecutors(self.bal_plugin)

        self.size_label = QLabel()
        self.will_executor_list_widget = WillExecutorListWidget(self)

        vbox = QVBoxLayout(self)
        vbox.addWidget(self.size_label)

        widget = QWidget()
        hbox = QHBoxLayout(widget)
        hbox.addWidget(QLabel(_("Add transactions without willexecutor")))
        heir_no_willexecutor = BalCheckBox(self.bal_plugin.NO_WILLEXECUTOR)
        hbox.addWidget(heir_no_willexecutor)
        spacer_widget = QWidget()
        spacer_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        hbox.addWidget(spacer_widget)
        vbox.addWidget(widget)

        vbox.addWidget(self.will_executor_list_widget)
        buttonbox = QHBoxLayout()

        b = QPushButton(_("Add"))
        b.clicked.connect(self.add)
        buttonbox.addWidget(b)

        b = QPushButton(_("Download List"))
        b.clicked.connect(self.download_list)
        buttonbox.addWidget(b)

        b = QPushButton(_("Import"))
        b.clicked.connect(self.import_file)
        buttonbox.addWidget(b)

        b = QPushButton(_("Export"))
        b.clicked.connect(self.export_file)
        buttonbox.addWidget(b)

        b = QPushButton(_("Ping All"))
        b.clicked.connect(self.update_willexecutors)
        buttonbox.addWidget(b)

        vbox.addLayout(buttonbox)
        # self.will_executor_list_widget.update()

    def add(self):
        self.willexecutors_list["http://localhost:8080"] = {
            "info": "New Will Executor",
            "base_fee": 0,
            "status": "-1",
        }
        self.will_executor_list_widget.update()

    def download_list(self, wes=None):
        if not wes:
            wes = self.willexecutors_list
        self.bal_window.download_list(wes, self.save_willexecutors)
        self.update()

    def export_file(self, path):
        export_meta_gui(
            self.bal_window.window, "willexecutors.json", self.export_json_file
        )

    def export_json_file(self, path):
        write_json_file(path, self.willexecutors_list)

    def import_file(self):
        import_meta_gui(
            self.bal_window.window,
            _("willexecutors"),
            self.import_json_file,
            self.willexecutors_list.update,
        )

    def update_willexecutors(self, wes=None):
        if not wes:
            wes = self.willexecutors_list
        self.bal_window.ping_willexecutors(wes, self.save_willexecutors)

    def import_json_file(self, path):
        data = read_json_file(path)
        data = self._validate(data)
        self.willexecutors_list.update(data)
        self.will_executor_list_widget.update()

    # TODO validate willexecutor json import file
    def _validate(self, data):
        return data

    def save_willexecutors(self, wes=None):
        if not wes:
            wes = self.willexecutors_list
        self.willexecutors_list.update(wes)
        self.will_executor_list_widget.update()
        Willexecutors.save(self.bal_window.bal_plugin, self.willexecutors_list)


class WillExecutorDialog(BalDialog, MessageBoxMixin):
    def __init__(self, bal_window, parent=None):
        if not parent:
            parent = bal_window.window
        BalDialog.__init__(self, parent, bal_window.bal_plugin)
        self.bal_plugin = bal_window.bal_plugin
        self.config = self.bal_plugin.config
        self.bal_window = bal_window
        self.willexecutors_list = Willexecutors.get_willexecutors(self.bal_plugin)

        self.setWindowTitle(_("Will-Executor Service List"))
        self.setMinimumSize(1000, 200)

        vbox = QVBoxLayout(self)
        self.will_executor_list_widget = WillExecutorWidget(
            self, self.bal_window, self.willexecutors_list
        )
        vbox.addWidget(self.will_executor_list_widget)

    def is_hidden(self):
        return self.isMinimized() or self.isHidden()

    def show_or_hide(self):
        if self.is_hidden():
            self.bring_to_top()
        else:
            self.hide()

    def bring_to_top(self):
        self.show()
        self.raise_()

    def closeEvent(self, event):
        event.accept()


class CheckAliveError(Exception):
    def __init__(self, timestamp_to_check):
        self.timestamp_to_check = timestamp_to_check

    def __str__(self):
        return "Check alive expired please update it: {}".format(
            datetime.fromtimestamp(self.timestamp_to_check).isoformat()
        )


def log_error(exec_info, window=None):
    _logger.error(f"LOG_ERROR: {exec_info}")
    #tb = traceback.format_exc()
    try:
        tb=exec_info[1]
        _logger.error(tb)
    except Exception:
        tb = traceback.format_exc()
        _logger.error(tb)


    if window is not None:
        window.show_error(exec_info)


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


class BalCalendar:
    @staticmethod
    def write_temp_ics(content):
        fd, path = tempfile.mkstemp(prefix="event_", suffix=".ics")
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
        return path

    @staticmethod
    def open_with_default_app(calendar_app, path):
        _logger.debug("opening calendar app")
        try:
            subprocess.check_call([calendar_app, path])
            return True
        except Exception as e:
            _logger.error(f"starting calendar app {e}")
            return False


    @staticmethod
    def format_time(time):
        return time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        #return time.astimezone(timezone.utc).strftime("%Y%m%d")

    @staticmethod
    def ical_escape(text: str) -> str:
        # escape per RFC5545: backslash, ; , newlines
        text = text.encode("utf-8")
        text = (
            text.replace(b"\\", b"\\\\")
            .replace(b";", b"\\;")
            .replace(b",", b"\\,")
        )
        out =""
        temp=text.split(b"\r\n")
        for s in temp:
            encoded= s
            cut =0
            while len(encoded) >75:
                cut+=5
                encoded=f"{s[:len(s)-cut]}"
                if encoded[-1]==b"\\" and encoded[-2]!=b"\\\\":
                    cut += 1
                encoded=f"{s[:len(s)-cut]}"
                encoded=f"{encoded}...\r\n".encode("utf-8")
            if cut>0:
                out+=str(f"{s[:len(s)-cut].decode()}...\r\n")
            else:
                out+=str(f"{s.decode()}\r\n")

        return out[:-2]

    @staticmethod
    def fold_ical_line(line: str, limit: int = 75) -> str:
        # ritorna linee separate da CRLF e folding con spazio iniziale sulle righe successive
        encoded = line.encode("utf-8")
        parts = []
        while len(encoded) > limit:
            # taglia senza spezzare byte UTF-8
            cut = limit
            while (encoded[cut] & 0xC0) == 0x80:  # byte di continuazione UTF-8
                cut -= 1
            parts.append(encoded[:cut].decode("utf-8"))
            encoded = encoded[cut:]
        parts.append(encoded.decode("utf-8"))
        return "\r\n ".join(parts)
