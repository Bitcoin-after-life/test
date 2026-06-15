"""
bal.gui.qt.window
=================

The :class:`BalWindow` controller: one instance per Electrum wallet window.

This is the orchestration layer that ties together the heirs list, the will
preview, the will-executors and the various dialogs.  It owns the per-wallet
state (``heirs``, ``will``, ``willitems``, ``will_settings``) and exposes the
high-level actions (build / check / sign / broadcast / invalidate the will,
import/export, etc.) that the menus, tabs and dialogs invoke.

The actual Bitcoin logic lives in :mod:`bal.core`; this class only coordinates
it with the GUI.
"""

import threading

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"
from .widgets import LockTimeWidget, PercAmountEdit, WillSettingsWidget
from .dialogs import (BalBlockingWaitingDialog, BalBuildWillDialog, BalDialog,
                      BalWaitingDialog, BalWizardDialog, WillDetailDialog,
                      WillExecutorDialog)
from .lists import HeirListWidget, PreviewList, WillExecutorWidget


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
        # Guard against wiring the menu/tabs more than once for the same window.
        # Electrum may invoke both the ``init_menubar`` hook and our hot-init
        # path (``init_qt`` -> ``_setup_window``) for the same window, e.g. when
        # Electrum restarts with the plugin already enabled.  Calling
        # ``init_menubar_tools`` twice would add the Heirs/Will tabs and the
        # menu actions twice, producing the garbled/condensed menu entry.
        self._menubar_initialized = False
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
        # Idempotent: only wire the tabs + menu actions once per window.
        # A second call (e.g. init_menubar hook *and* the hot-init path both
        # firing) would otherwise duplicate the Heirs/Will tabs and the
        # Will-Executors / toggle actions, which Qt renders as a broken,
        # condensed menu entry under the Electrum logo.
        if self._menubar_initialized:
            _logger.info("init_menubar_tools: already initialised, skipping")
            return
        self._menubar_initialized = True
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
        # Keep it in front of Electrum (window-modal) instead of letting it
        # fall behind the main window.
        show_on_top(self.willexecutor_dialog)

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
        if multiverse:
            return
        # Coerce the locktime to a plain serializable scalar: will_settings is
        # read from Electrum's config and a non-primitive value here would end
        # up inside the heirs dict and break json_db persistence (this was one
        # path to the "cannot pickle '_thread.RLock' object" error).
        locktime = self.will_settings["locktime"]
        if not isinstance(locktime, (int, float, str)):
            locktime = str(locktime)
        # Iterate over a snapshot of the keys: assigning to self.heirs[...]
        # triggers Heirs.__setitem__ -> save(), which mutates the mapping while
        # we iterate it.  Building the new values first and applying them after
        # the loop avoids "dict changed size during iteration" and the repeated
        # save() on every heir.
        updates = {
            heir: [self.heirs[heir][0], self.heirs[heir][1], locktime]
            for heir in list(self.heirs)
        }
        for heir, value in updates.items():
            self.heirs[heir] = value

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
            # Electrum's own TxDialog: keep it in front of the main window.
            show_on_top(d, modal_to_window=False)
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
        # Wallet is closing: run the closing "build will" task and tear down
        # the plugin's tabs/menu.  Each step is isolated so that one failure
        # does not leave the GUI half-initialised (which previously forced the
        # user to restart Electrum).  Errors are logged instead of silently
        # swallowed.
        if self.disable_plugin:
            return

        # 1) Business logic: build/save the will on close (unchanged behaviour).
        try:
            close_window = BalBuildWillDialog(self)
            close_window.build_will_task()
            self.save_willitems()
        except Exception as e:
            _logger.error(f"on_close: build/save will failed: {e}")

        # 2) GUI teardown - each action guarded independently.
        def _safe(desc, fn):
            try:
                fn()
            except Exception as e:
                _logger.error(f"on_close: {desc} failed: {e}")

        _safe("close heirs tab", lambda: self.heirs_tab.close())
        _safe("close will tab", lambda: self.will_tab.close())
        _safe(
            "remove willexecutors menu action",
            lambda: self.tools_menu.removeAction(
                self.tools_menu.willexecutors_action
            ),
        )
        _safe("toggle heirs tab off", lambda: self.window.toggle_tab(self.heirs_tab))
        _safe("toggle will tab off", lambda: self.window.toggle_tab(self.will_tab))
        _safe("refresh tabs", lambda: self.window.tabs.update())

        # 3) Reset in-memory state so re-enabling/re-opening starts clean.
        self.willitems = {}
        self.will = {}
        self.heirs = {}
        self.willexecutors = {}
        self.disable_plugin = True
        self.ok = False
        # The tabs/menu actions were removed above; allow init_menubar_tools to
        # re-wire them if this same window is reused for another wallet.
        self._menubar_initialized = False

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

        # Initialise statuses + show the list immediately.
        for url in willexecutors:
            willexecutors[url].setdefault("broadcast_status", _("waiting..."))
        try:
            self.waiting_dialog.update(getMsg(willexecutors))
        except Exception:
            pass

        error = {"flag": False}
        already_present = []

        def on_each(url, willexecutor, ok, exc):
            # Runs from a worker thread.  We only do book-keeping + a thread-safe
            # signal-based UI update here; the heavier "already present" check
            # path (which itself does network I/O) is handled below in the main
            # task thread to keep the original sequential behaviour for it.
            if isinstance(exc, Willexecutors.AlreadyPresentException):
                already_present.append(url)
                willexecutor["broadcast_status"] = _("checking...")
            elif ok:
                for wid in willexecutor.get("txsids", []):
                    self.willitems[wid].set_status("PUSHED", True)
                willexecutor["broadcast_status"] = _("Success")
            else:
                for wid in willexecutor.get("txsids", []):
                    self.willitems[wid].set_status("PUSH_FAIL", True)
                error["flag"] = True
                willexecutor["broadcast_status"] = _("Failed")
            willexecutor.pop("txs", None)
            try:
                self.waiting_dialog.update(getMsg(willexecutors))
            except Exception:
                pass

        if self.waiting_dialog._stopping:
            return
        # Push to all servers in parallel (each server keeps its own retry
        # behaviour, but a slow/dead server no longer blocks the others).
        Willexecutors.push_transactions_parallel(willexecutors, on_each=on_each)

        # Handle the "already present" servers: verify each stored tx.  This
        # keeps the exact original check logic, just executed after the parallel
        # push has identified which servers need it.
        for url in already_present:
            willexecutor = willexecutors[url]
            for wid in willexecutor.get("txsids", []):
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

        if error["flag"]:
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
        # Servers are now contacted in parallel (see
        # Willexecutors.check_transactions_parallel) with a fast-fail timeout and
        # a global deadline, so a single slow/dead will-executor no longer
        # freezes the "checking transaction" dialog for minutes.  The dialog
        # shows live progress plus an elapsed-time counter (Xs / DEADLINEs).
        targets = [(wid, w.we["url"]) for wid, w in will.items() if w.we]
        total = len(targets)
        deadline = Willexecutors.CHECK_GLOBAL_DEADLINE
        done = {"count": 0}

        def _status_line():
            return "{} {}/{} ({}s / {}s)".format(
                _("Checking transactions"), done["count"], total,
                min(int(time.time() - start), deadline), deadline,
            )

        def on_each(wid, url, res, exc):
            # Reuse the original per-item logic: set_check_willexecutor handles
            # both a real response and a None/failure (-> CHECK_FAIL).
            try:
                will[wid].set_check_willexecutor(res)
            except Exception as e:
                _logger.error(f"check on_each error for {wid}: {e}")
            done["count"] += 1
            self.waiting_dialog.update(_status_line())

        def on_timeout(wid, url):
            # The global deadline elapsed before this server answered: mark the
            # item as failed (None response) so the user can retry later.
            try:
                will[wid].set_check_willexecutor(None)
            except Exception as e:
                _logger.error(f"check on_timeout error for {wid}: {e}")

        def on_tick():
            if getattr(self.waiting_dialog, "_stopping", False):
                return
            self.waiting_dialog.update(_status_line())

        if total:
            self.waiting_dialog.update(_status_line())
            Willexecutors.check_transactions_parallel(
                targets, on_each=on_each, on_timeout=on_timeout, on_tick=on_tick
            )

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

    def fetch_will_executors_list(self, old_willexecutors):
        """Download the will-executor list (runs inside the TaskThread worker).

        Tries the configured server first, then the original hardcoded endpoint,
        so a stale/bad config value cannot break the download.  Detailed
        per-attempt diagnostics are written to the Electrum log only; the user
        sees a simple message.  No business logic in ``bal.core`` is changed.

        Returns the downloaded dict (empty ``{}`` on failure).
        """
        chainname = BalPlugin.chainname
        configured = self.bal_plugin.WELIST_SERVER.get()
        candidates = []
        for base in (configured, "https://welist.bitcoin-after.life/"):
            if not base:
                continue
            base = base if base.endswith("/") else base + "/"
            url = f"{base}data/{chainname}?page=0&limit=100"
            if url not in candidates:
                candidates.append(url)

        result = {}
        net = Network.get_instance()
        _logger.info(f"fetch_will_executors_list: network present = {net is not None}")
        for url in candidates:
            _logger.info(f"fetch_will_executors_list: trying {url}")
            try:
                # Fast-fail with a couple of short retries instead of the
                # default 10x/3s storm: if the user's connection is flaky we
                # want to fall back to the next URL (and then show the simple
                # error message) quickly, not freeze for minutes.
                resp = Willexecutors.send_request(
                    "get", url, timeout=10, max_retries=1, retry_sleep=1,
                )
                _logger.info(
                    f"fetch_will_executors_list: resp type={type(resp).__name__} "
                    f"len={len(resp) if hasattr(resp, '__len__') else 'n/a'}"
                )
                if resp:
                    result = resp
                    for w in result:
                        if w not in ("status", "url"):
                            Willexecutors.initialize_willexecutor(
                                result[w], w, None,
                                old_willexecutors.get(w, None),
                            )
                    break
                _logger.warning(f"fetch_will_executors_list: {url} -> empty response")
            except Exception as e:
                _logger.error(
                    f"fetch_will_executors_list: {url} -> {type(e).__name__}: {e}"
                )
        return result

    # Simple, user-facing message shown when the download fails for any reason
    # (the technical cause is in the Electrum log).
    DOWNLOAD_FAILED_MESSAGE = (
        "Could not download the will-executors list.\n\n"
        "This is usually caused by your internet connection or a firewall, "
        "not by the plugin. Please check your connection (a VPN often helps) "
        "and try again."
    )

    def download_list(self, willexecutors, fn_on_success, fn_on_failure=None):
        if fn_on_failure is None:
            fn_on_failure = log_error

        base_msg = _("Downloading will-executors list...")
        download_start = time.time()
        # Upper bound shown to the user.  fetch_will_executors_list tries up to
        # two endpoints, each with timeout=10 and one retry (~21s worst case),
        # so ~45s is a realistic maximum.  Showing "Xs / 45s" tells the user how
        # long they may have to wait instead of an open-ended counter.
        download_deadline = 45

        def task():
            # Heartbeat: show an elapsed-seconds counter (with the max wait made
            # explicit) while the (blocking) download runs, so the user sees time
            # advancing instead of a seemingly frozen dialog on a slow link.
            stop_heartbeat = threading.Event()

            def _heartbeat():
                while not stop_heartbeat.wait(1.0):
                    if getattr(self.waiting_dialog, "_stopping", False):
                        return
                    try:
                        self.waiting_dialog.update(
                            "{} ({}s / {}s)".format(
                                base_msg,
                                min(int(time.time() - download_start),
                                    download_deadline),
                                download_deadline,
                            )
                        )
                    except Exception:
                        return

            hb = threading.Thread(target=_heartbeat, name="bal-dl-hb",
                                  daemon=True)
            hb.start()
            try:
                return self.fetch_will_executors_list(willexecutors)
            finally:
                stop_heartbeat.set()

        def on_success(result):
            if result:
                self.willexecutors.update(result)
                fn_on_success(result)
            else:
                self.show_warning(_(self.DOWNLOAD_FAILED_MESSAGE))

        def on_failure(exc_info):
            _logger.error(f"download_list failed: {exc_info}")
            self.show_warning(_(self.DOWNLOAD_FAILED_MESSAGE))

        self.waiting_dialog = BalWaitingDialog(
            self, base_msg, task, on_success, on_failure, exe=False
        )
        self.waiting_dialog.exe()

    def ping_willexecutors_task(self, wes):
        _logger.info("ping willexecutots task")
        # Track per-url state for the live status text.  Servers are contacted
        # in parallel (see Willexecutors.ping_servers_parallel), so a single
        # unreachable server no longer blocks all the others: the whole batch
        # now takes about as long as the slowest server instead of the sum of
        # every server's (possibly timing-out) request.
        pinged = set()
        failed = set()
        total = len(wes)
        ping_start = time.time()

        ping_deadline = Willexecutors.PUSH_GLOBAL_DEADLINE

        def get_title():
            # Header shows progress + an elapsed-seconds counter with the max
            # wait made explicit (e.g. "3s / 30s"), so the user sees time
            # advancing and knows how long it may take, instead of a seemingly
            # frozen dialog.
            answered = len(pinged) + len(failed)
            msg = _("Ping Will-Executors:")
            msg += "  {}/{} ({}s / {}s)".format(
                answered, total,
                min(int(time.time() - ping_start), ping_deadline),
                ping_deadline,
            )
            msg += "\n\n"
            for url in wes:
                urlstr = "{:<50}: ".format(url[:50])
                if url in pinged:
                    urlstr += _("Ok")
                elif url in failed:
                    urlstr += _("Ko")
                else:
                    urlstr += _("waiting...")
                urlstr += "\n"
                msg += urlstr
            return msg

        def on_each(url, we, ok):
            if ok:
                pinged.add(url)
            else:
                failed.add(url)
            try:
                self.waiting_dialog.update(get_title())
            except Exception:
                pass

        # Show the initial "waiting..." list immediately.
        try:
            self.waiting_dialog.update(get_title())
        except Exception:
            pass

        # Refresh the elapsed-seconds counter while the (blocking) parallel ping
        # runs.  The tick is driven from THIS thread by ping_servers_parallel,
        # the same thread that drives on_each, so the dialog repaint is reliable.
        def on_tick():
            if getattr(self.waiting_dialog, "_stopping", False):
                return
            try:
                self.waiting_dialog.update(get_title())
            except Exception:
                pass

        Willexecutors.ping_servers_parallel(wes, on_each=on_each, on_tick=on_tick)

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
        # This dialog is meant to be modal (per its name); show it on top so it
        # cannot disappear behind the Electrum window.
        show_on_top(self.dw)

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


