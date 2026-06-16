"""
bal.gui.qt.dialogs
==================

All modal/non-modal dialogs of the plugin.

    * BalDialog                  - common base dialog (icon, close handling).
    * BalWizard* (Dialog/Widget) - the step-by-step "create your will" wizard.
    * BalWaitingDialog /
      BalBlockingWaitingDialog   - progress dialogs for background tasks.
    * BalBuildWillDialog         - the central build/sign/push/broadcast flow.
    * WillDetailDialog           - shows the full will tree for one wallet.
    * WillExecutorDialog         - manage the list of will-executor servers.

To keep the dialogs verbatim while avoiding import cycles with the list views,
the few list classes they reference are imported lazily inside the methods that
use them (see ``lists`` imports below).
"""

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"
from .widgets import (BalCheckBox, BalLineEdit, BalTextEdit, BalTxFeesWidget,
                      LockTimeWidget, PercAmountEdit, ThresholdTimeWidget,
                      WillSettingsWidget, WillWidget)
from .calendar import BalCalendar
# NOTE: list views (HeirListWidget, PreviewList, WillExecutorWidget) are
# imported lazily where needed to avoid a dialogs<->lists import cycle.


class BalDialog(QDialog,MessageBoxMixin):
    _stopping = False
    def __init__(self, parent, bal_plugin, title=None, icon="icons/bal16x16.png"):
        import signal
        from PyQt6.QtCore import QMetaObject, Qt
        from PyQt6.QtWidgets import QApplication
        def handler(signum, frame):
            QMetaObject.invokeMethod(self, "close", Qt.ConnectionType.QueuedConnection)

        #signal.signal(signal.SIGINT, handler)
        # NOTE: do NOT store this as ``self.parent`` - that would shadow
        # QWidget.parent() and can make the dialog disappear behind Electrum.
        self._bal_parent = parent
        self.thread = None
        # Anchor the dialog to the *top-level* Electrum window so it always
        # stays in front of it (instead of falling behind).
        super().__init__(top_level_of(parent))
        if title:
            self.setWindowTitle(title)
        # WindowModalDialog.__init__(self,parent)
        self.setWindowIcon(read_QIcon_from_bytes(bal_plugin.read_file(icon)))
        
    def closeEvent(self, event):
        self._stopping = True
        # NOTE: we deliberately do NOT stop ``self.thread`` here.
        #
        # Electrum's ``TaskThread`` delivers results via ``on_done`` which calls
        # ``cb_done`` (often ``self.accept`` -> closes this dialog) *before*
        # ``cb_result`` (``on_success`` -> e.g. updating the will-executor
        # list).  If we stop/join the thread inside ``closeEvent`` the close
        # triggered by ``accept`` tears the thread down *before* ``on_success``
        # runs, so the downloaded data is silently dropped.  The original plugin
        # left this commented out for exactly this reason; subclasses that own a
        # genuinely long-lived thread stop it explicitly in their own close
        # handler.
        super().closeEvent(event)

    def hideEvent(self, event):
        self._stopping = True
        super().hideEvent(event)


class BalWizardDialog(BalDialog):
    def __init__(self, bal_window: "BalWindow"):
        assert bal_window
        BalDialog.__init__(
            self, bal_window.window, bal_window.bal_plugin, _("Bal Wizard Setup")
        )
        self.setMinimumSize(800, 400)
        self.bal_window = bal_window
        self._bal_parent = bal_window.window
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
        self._bal_parent = parent
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
        self._bal_parent.close()

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
        # Lazy import to avoid a dialogs<->lists import cycle (lists imports
        # BalBuildWillDialog from this module at load time).
        from .lists import HeirListWidget
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
        # Lazy import to avoid a dialogs<->lists import cycle.
        from .lists import WillExecutorWidget
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

        # The wizard ("Build your will") is the ONLY place the delivery time,
        # check alive and fee can be edited, so it is the only read_only=False.
        layout.addWidget(WillSettingsWidget(self.bal_window, self, "v",
                                            read_only=False))
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
        # IMPORTANT: keep the *application-modal* exec() of the original code.
        # This dialog is driven by a TaskThread whose result (on_success, e.g.
        # populating the will-executor list) is delivered via a queued signal
        # while exec() spins the modal event loop.  Switching to window-modal
        # changed how the modal loop interacts with that delivery and could
        # cause the downloaded list to never be applied.  We only add the
        # raise/activate so the dialog stays visible, without altering modality.
        bring_to_front(self)
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
        # show popup (window-modal + on top so it is actually visible)
        show_on_top(self)
        # Refresh the GUI so the popup is painted (and message_label drawn)
        # BEFORE we block the GUI thread running the task; otherwise the popup
        # appears empty/frozen.
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        QApplication.processEvents()
        try:
            # block and run given task
            task()
        finally:
            # close popup
            self.accept()


class BalBuildWillDialog(BalDialog):
    updatemessage = pyqtSignal()
    COLOR_WARNING = "#cfa808"
    COLOR_ERROR = "#ff0000"
    COLOR_OK = "#05ad05"

    def __init__(self, bal_window, parent=None):
        if not parent:
            parent = bal_window.window
        BalDialog.__init__(self, parent, bal_window.bal_plugin, _("Building Will"))
        # (parent already stored as self._bal_parent by BalDialog.__init__)
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
        # exec() already shows the dialog modally; route through the helper so
        # it is window-modal and brought to the front (no separate show()).
        show_modal(self)

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
        except WillPostponedException as e:
            # An already signed/sent will is being postponed.  Like an expired
            # will, the previously committed coins must be invalidated on-chain
            # FIRST (otherwise a will-executor could broadcast the old,
            # earlier-locktime tx and execute the inheritance too early).  We
            # return (None, tx) so phase 2 asks the user to sign and broadcast
            # the invalidation; afterwards the user presses Prepare again to
            # rebuild the new (postponed) inheritance.
            _logger.debug(f"postponed {e}")
            self.msg_set_checking(_("Postponed: invalidating old will"))
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

            # Only push to the will-executors the user actually selected.  We
            # filter the mapping up-front so push_transactions_parallel only
            # talks to the relevant servers.
            selected = {
                url: we
                for url, we in willexecutors.items()
                if Willexecutors.is_selected(self.bal_window.willexecutors.get(url))
            }

            # Servers that report "already present" need their stored tx
            # verified afterwards (network I/O); collect them here and process
            # them sequentially after the parallel push, keeping the original
            # check logic untouched.
            already_present = []
            retry_flag = {"value": False}
            total = len(selected)
            done = {"count": 0}

            deadline = Willexecutors.PUSH_GLOBAL_DEADLINE

            def _status_line():
                # e.g. "Broadcasting your will to executors: 2/3 (5s / 30s)".
                # The "/ 30s" makes the maximum wait explicit, so the user knows
                # the wizard will proceed by then (the global deadline) instead
                # of wondering how long the counter will keep climbing.
                return "{} {}/{} ({}s / {}s)".format(
                    _("Broadcasting"), done["count"], total,
                    min(int(time.time() - push_start), deadline), deadline,
                )

            def on_each(url, willexecutor, ok, exc):
                # Runs from a worker thread.  Do only thread-safe book-keeping
                # plus a signal-based UI update (msg_edit_row emits a pyqtSignal,
                # which is marshalled to the GUI thread).
                if isinstance(exc, Willexecutors.AlreadyPresentException):
                    already_present.append(url)
                elif ok:
                    for wid in willexecutor["txsids"]:
                        self.bal_window.willitems[wid].set_status("PUSHED", True)
                else:
                    for wid in willexecutor["txsids"]:
                        self.bal_window.willitems[wid].set_status("PUSH_FAIL", True)
                    retry_flag["value"] = True
                done["count"] += 1
                # Show the per-server result (Ok/Ko) in bold + color so the
                # outcome stands out, keeping the server URL in normal weight.
                result = self.msg_ok("Ok") if ok else self.msg_error("Ko")
                self.msg_edit_row("{} : {}".format(url, result))
                self.msg_set_pushing(_status_line())

            def on_timeout(url, willexecutor):
                # The global deadline elapsed before this server answered.  Mark
                # its txs as failed (so the user can retry later) and show it.
                for wid in willexecutor.get("txsids", []):
                    self.bal_window.willitems[wid].set_status("PUSH_FAIL", True)
                retry_flag["value"] = True
                self.msg_edit_row(
                    "{} : {}".format(url, self.msg_error(_("Timeout - no answer")))
                )

            if self._stopping:
                return
            # Push to all selected will-executors in parallel: a slow/dead
            # server no longer blocks the others, so the wizard's "Broadcasting"
            # step is no longer sequential.  Each server keeps a short retry
            # behaviour, and a global deadline guarantees the wizard always
            # proceeds even if a server never answers.
            push_start = time.time()
            self.msg_set_pushing(_status_line())

            # Refresh the elapsed-seconds counter while the (blocking) parallel
            # push runs, so the user sees time advancing instead of a frozen
            # "Trasmissione".  The tick is driven from THIS (Task) thread by
            # push_transactions_parallel, the same thread that drives on_each, so
            # the pyqtSignal repaint is reliable (a separate heartbeat thread's
            # signal emissions were not being marshalled and never repainted).
            def on_tick():
                if self._stopping:
                    return
                self.msg_set_pushing(_status_line())

            Willexecutors.push_transactions_parallel(
                selected, on_each=on_each, on_timeout=on_timeout, on_tick=on_tick
            )

            # Final summary line with the total elapsed time.
            self.msg_set_pushing(
                "{}/{} ({}s)".format(done["count"], total,
                                     int(time.time() - push_start))
            )
            retry = retry_flag["value"]

            # Verify the "already present" servers (sequential, original logic).
            self.bal_plugin = self.bal_window.bal_plugin
            for url in already_present:
                for wid in willexecutors[url]["txsids"]:
                    if self._stopping:
                        return
                    row = self.msg_edit_row(
                        "checking {} - {} : <b>{}</b>".format(
                            self.bal_window.willitems[wid].we["url"], wid, "Waiting"
                        )
                    )
                    w = self.bal_window.willitems[wid]
                    w.set_check_willexecutor(
                        Willexecutors.check_transaction(wid, w.we["url"])
                    )
                    # Show the CHECKED result in bold + color (green True /
                    # red False) so the outcome stands out, keeping the server
                    # URL and tx id in normal weight.
                    checked = self.bal_window.willitems[wid].get_status("CHECKED")
                    result = self.msg_ok(checked) if checked else self.msg_error(checked)
                    row = self.msg_edit_row(
                        "checked {} - {} : {}".format(
                            self.bal_window.willitems[wid].we["url"],
                            wid,
                            result,
                        ),
                        row,
                    )

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
        # Stop AND join the thread, then propagate the close event (previously
        # it neither waited nor called super().closeEvent()).
        stop_thread(getattr(self, "thread", None))
        super().closeEvent(event)

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
        # Results are shown in bold so the outcome stands out from the
        # left-side state label (which stays in normal weight).
        return "<font color='{}'><b>{}</b></font>".format(self.COLOR_ERROR, e)

    def msg_ok(self, e="Ok"):
        # Results are shown in bold (see msg_error).
        return "<font color='{}'><b>{}</b></font>".format(self.COLOR_OK, e)

    def msg_warning(self, e):
        # Results are shown in bold (see msg_error).
        return "<font color='{}'><b>{}</b></font>".format(self.COLOR_WARNING, e)

    def msg_set_status(self, msg, row=None, status=None, color=None):
        # The left "state" label keeps its normal weight; only the right-side
        # result (``status``) is rendered in bold so it is easy to read at a
        # glance.  ``status`` may already contain rich-text emitted by
        # msg_ok/msg_error/msg_warning (which add their own <b>...</b>); wrapping
        # it again in <b> is harmless for those cases.
        status = "Wait" if status is None else status
        if color is None:
            line = "{}:\t<b>{}</b>".format(_(msg), status)
        else:
            line = "{}:\t<font color={}><b>{}</b></font>".format(
                _(msg), color, status
            )
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

        # Lazy import to avoid a dialogs<->lists import cycle.
        from .lists import WillExecutorWidget
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
        # raise_() alone does not grab focus on some window managers (Windows);
        # activateWindow() ensures the dialog actually comes to the front.
        bring_to_front(self)

    def closeEvent(self, event):
        event.accept()


