"""
bal.gui.qt.lists
================

Tree/list views (subclasses of Electrum's ``MyTreeView``) and their toolbars.

    * HeirListWidget        - editable list of heirs (address / amount / locktime).
    * PreviewList           - preview of the will transactions before signing.
    * WillExecutorListWidget- list of will-executor servers.
    * WillExecutorWidget    - container combining the list with add/import buttons.

These views call back into the :class:`BalWindow` controller (passed at
construction) for all business actions, so the heavy logic stays in ``window``
and ``dialogs``.
"""

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"
from .widgets import BalCheckBox, PercAmountEdit, WillSettingsWidget
from .dialogs import BalBuildWillDialog


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
        # self._bal_parent = parent
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

            items[-1].setBackground(QColor(status_color(bal_tx)))

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
#        self._bal_parent = bal_window.window
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
        self._bal_parent = parent
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
            if Willexecutors.is_selected(self._bal_parent.willexecutors_list[sel_key]):
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
            wout[k] = self._bal_parent.willexecutors_list[k]
        self._bal_parent.update_willexecutors(wout)

        self._bal_parent.save_willexecutors()
        self.update()

    def get_edit_key_from_coordinate(self, row, col):
        role = self.ROLE_HEIR_KEY + col
        a = self.get_role_data_from_coordinate(row, col, role=role)
        return a

    def delete(self, selected_keys):
        for key in selected_keys:
            del self._bal_parent.willexecutors_list[key]

        self._bal_parent.save_willexecutors()
        self.update()

    def select(self, selected_keys):
        for wid, w in self._bal_parent.willexecutors_list.items():
            if wid in selected_keys:
                w["selected"] = True
        self._bal_parent.save_willexecutors()
        self.update()

    def deselect(self, selected_keys):
        for wid, w in self._bal_parent.willexecutors_list.items():
            if wid in selected_keys:
                w["selected"] = False
        self._bal_parent.save_willexecutors()
        self.update()

    def on_edited(self, idx, edit_key, *, text):
        # prior_name = self._bal_parent.willexecutors_list[edit_key]
        col = idx.column()
        try:
            if col == self.Columns.URL:
                self._bal_parent.willexecutors_list[text] = self._bal_parent.willexecutors_list[
                    edit_key
                ]
                del self._bal_parent.willexecutors_list[edit_key]
            if col == self.Columns.BASE_FEE:
                self._bal_parent.willexecutors_list[edit_key]["base_fee"] = (
                    Util.encode_amount(text, self.get_decimal_point())
                )
            if col == self.Columns.ADDRESS:
                self._bal_parent.willexecutors_list[edit_key]["address"] = text
            if col == self.Columns.INFO:
                self._bal_parent.willexecutors_list[edit_key]["info"] = text
            self._bal_parent.save_willexecutors()
            self.update()
        except Exception:
            pass

    def update(self):
        if self._bal_parent.willexecutors_list is None:
            return
        try:
            current_key = self.get_role_data_for_current_item(
                col=self.Columns.URL, role=self.ROLE_HEIR_KEY
            )
            self.model().clear()
            self.update_headers(self.__class__.headers)

            set_current = None

            for url, value in self._bal_parent.willexecutors_list.items():
                labels = [""] * len(self.Columns)
                labels[self.Columns.URL] = url
                if Willexecutors.is_selected(value):

                    labels[self.Columns.SELECTED] = [
                        read_QIcon_from_bytes(
                            self._bal_parent.bal_plugin.read_file("icons/confirmed.png")
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
                            self._bal_parent.bal_plugin.read_file(
                                "icons/status_connected.png"
                            )
                        ),
                        "",
                    ]
                else:
                    labels[self.Columns.STATUS] = [
                        read_QIcon_from_bytes(
                            self._bal_parent.bal_plugin.read_file("icons/unconfirmed.png")
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
        self._bal_parent = parent
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
        # NOTE: the original plugin downloaded the list with a *direct*,
        # synchronous call on the GUI thread here (NOT via a BalWaitingDialog /
        # TaskThread).  We keep that behaviour and add precise diagnostics so a
        # failure shows the *exact* URL and error instead of a generic timeout.
        from electrum.network import Network

        chainname = BalPlugin.chainname
        # The original used this hardcoded URL; the refactor made it
        # configurable.  Try the configured server first, then fall back to the
        # original hardcoded endpoint, so a bad/stale config value cannot break
        # the download.
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
        errors = []
        net = Network.get_instance()
        _logger.info(f"download_list: network instance present = {net is not None}")
        for url in candidates:
            _logger.info(f"download_list: trying {url}")
            try:
                resp = Willexecutors.send_request("get", url, timeout=20)
                _logger.info(
                    f"download_list: response type={type(resp).__name__} "
                    f"len={len(resp) if hasattr(resp, '__len__') else 'n/a'}"
                )
                if resp:
                    result = resp
                    for w in result:
                        if w not in ("status", "url"):
                            Willexecutors.initialize_willexecutor(
                                result[w], w, None,
                                self.bal_window.willexecutors.get(w, None),
                            )
                    break
                else:
                    errors.append(f"{url}: empty response")
            except Exception as e:
                _logger.error(f"download_list: {url} -> {type(e).__name__}: {e}")
                errors.append(f"{url}: {type(e).__name__}: {e}")

        if result:
            self.bal_window.willexecutors.update(result)
            self.willexecutors_list.update(result)
            self.will_executor_list_widget.update()
            Willexecutors.save(self.bal_window.bal_plugin, self.willexecutors_list)
        else:
            # Control test: try a plain direct HTTPS request (NOT through
            # Electrum's Network layer).  If this succeeds while the Electrum
            # request above timed out, the problem is Electrum's network/proxy
            # state, not the user's connection or the server.
            control = self._direct_https_probe(candidates[0] if candidates else "")
            detail = "\n".join(errors) if errors else _("Unknown error")
            self.bal_window.show_warning(
                _("Could not download the will-executors list.")
                + "\n\n" + _("Details (via Electrum network):") + f"\n{detail}\n\n"
                + _("Direct connection test:") + f"\n{control}\n\n"
                + _("Check your internet connection and the server URL, "
                    "then try again.")
            )

    @staticmethod
    def _direct_https_probe(url):
        """Best-effort direct HTTPS GET bypassing Electrum's Network layer.

        Used only for diagnostics when the normal download fails, to tell apart
        a connectivity problem from an Electrum-network-state problem.
        """
        if not url:
            return "skipped (no url)"
        try:
            import urllib.request
            req = urllib.request.Request(
                url, headers={"user-agent": "BalPlugin-probe"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
                return f"OK (HTTP {r.status}, {len(data)} bytes)"
        except Exception as e:
            return f"{type(e).__name__}: {e}"
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


