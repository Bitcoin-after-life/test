"""
bal.gui.qt.plugin
=================

The Qt entry point of the plugin.

:class:`Plugin` subclasses :class:`bal.core.plugin_base.BalPlugin` and adds the
Electrum ``@hook`` methods that wire the plugin into the Qt GUI (status-bar
button, Tools menu, wallet load/close, settings dialog).  Electrum instantiates
this class because the package ``manifest.json`` declares ``available_for:
["qt"]`` and the loader imports ``qt.py`` (a thin shim re-exporting this class).

One :class:`bal.gui.qt.window.BalWindow` is created per top-level wallet window
and cached in ``self.bal_windows``.
"""

from electrum.gui.qt.main_window import StatusBarButton

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"
from .common import read_QIcon_from_bytes
from .widgets import BalCheckBox, BalLineEdit, BalTextEdit
from .window import BalWindow
from .dialogs import BalDialog


def _window_key(window):
    """Return a stable, hashable identity for an Electrum top-level window.

    The original code used ``window.winId`` (the *bound method*, not its
    result) as a dict key.  That happened to work because the same window
    object yields the same bound method, but it is semantically wrong and
    fragile across window re-creation / multiple wallets.  ``id(window)`` is a
    stable, correct identity for the lifetime of the window object.
    """
    return id(window)


class Plugin(BalPlugin):
    def __init__(self, parent, config, name):
        _logger.info("INIT BALPLUGIN")
        BalPlugin.__init__(self, parent, config, name)
        self.bal_windows = {}
        # Status-bar buttons, keyed by id(sb.window()).  Tracking them lets us
        # remove a stale button before creating a fresh one when a wallet is
        # switched / Electrum is restarted, so the icon is never duplicated.
        self._statusbar_buttons = {}

    @hook
    def init_qt(self, gui_object):
        # Called when the plugin is enabled, including *hot* (while a wallet is
        # already open).  The original code gave up here and asked the user to
        # restart Electrum; instead we fully initialise the already-open
        # window(s) so the plugin works immediately.
        _logger.info("HOOK bal init qt")
        try:
            self.gui_object = gui_object
            for window in gui_object.windows:
                self._setup_window(window, load_open_wallet=True)
        except Exception as e:
            _logger.error("Error loading plugin {}".format(e))
            raise e

    @staticmethod
    def _close_plugins_manager_dialog():
        """Close Electrum's "Electrum Plugins" manager dialog if it is open.

        This is the native Electrum ``PluginsDialog`` (a ``WindowModalDialog``);
        it is not owned by this plugin, so we locate it among the application's
        top-level widgets and close it.  Failures are non-fatal: leaving the
        dialog open is harmless, so we never propagate exceptions from here.
        """
        Plugin._handle_plugins_manager_dialog(attempt=0)

    @staticmethod
    def _find_plugins_manager_dialogs():
        """Return the open Electrum "Electrum Plugins" manager dialog(s).

        The match is intentionally permissive: when our plugin is loaded from a
        zip (``electrum_external_plugins``), ``isinstance`` against the imported
        ``PluginsDialog`` class can fail due to differing module identities, so
        we also match by class name and by window title (including the localized
        title, since the user runs Electrum under a non-English locale).
        """
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception:
            return []
        try:
            from electrum.gui.qt.plugins_dialog import PluginsDialog
        except Exception:
            PluginsDialog = None
        app = QApplication.instance()
        if app is None:
            return []
        # Accept both the English title and the translated one.  We cannot rely
        # only on _() because the dialog object may have been built with a
        # different gettext binding than ours when loaded from a zip.
        titles = {"Electrum Plugins"}
        try:
            titles.add(_("Electrum Plugins"))
        except Exception:
            pass
        found = []
        for w in app.topLevelWidgets():
            try:
                is_match = False
                if PluginsDialog is not None and isinstance(w, PluginsDialog):
                    is_match = True
                elif type(w).__name__ == "PluginsDialog":
                    is_match = True
                elif w.windowTitle() in titles:
                    is_match = True
                if not is_match:
                    continue
                # Only count it as "open" if it is actually visible: after a
                # successful close()/reject() the QDialog object still lives in
                # topLevelWidgets() but becomes invisible, so filtering by
                # isVisible() is what tells "still open" from "already closed".
                visible = w.isVisible()
                _logger.info(
                    "plugins manager dialog match: cls={} title={!r} "
                    "visible={}".format(
                        type(w).__name__, w.windowTitle(), visible
                    )
                )
                if visible:
                    found.append(w)
            except Exception as e:
                _logger.debug("inspecting top-level widget failed: {}".format(e))
        return found

    @staticmethod
    def _try_dismiss_dialog(d):
        """Attempt to dismiss a (possibly modal) dialog as robustly as we can.

        A ``PluginsDialog`` is opened with ``exec()`` (a nested, *application-
        modal* event loop).  Inside such a loop a plain ``close()`` is not
        always honoured, so we also try ``reject()`` / ``done()`` which end the
        modal loop directly.  Any of these may fail depending on Qt state, so
        each is guarded independently.
        """
        try:
            from PyQt6.QtWidgets import QDialog
        except Exception:
            QDialog = None
        # 1) reject() / done(): the reliable way to end an exec() modal loop.
        if QDialog is not None and isinstance(d, QDialog):
            try:
                d.reject()
            except Exception as e:
                _logger.debug("reject() failed: {}".format(e))
            try:
                d.done(QDialog.DialogCode.Rejected)
            except Exception as e:
                _logger.debug("done() failed: {}".format(e))
        # 2) close(): covers non-QDialog top-levels and is a harmless extra.
        try:
            d.close()
        except Exception as e:
            _logger.debug("could not close plugins dialog: {}".format(e))

    @staticmethod
    def _handle_plugins_manager_dialog(attempt=0):
        """Try to auto-close the manager dialog; retry a few times.

        Enabling the plugin happens while Electrum's ``PluginsDialog`` may still
        be running its own modal event loop, so a single ``close()`` can be
        ignored. We retry on a short schedule and, if it is still open after the
        last attempt, fall back to bringing it to the front so the user notices
        it and closes it themselves (it must not linger in the background).
        """
        try:
            from PyQt6.QtCore import QTimer
        except Exception:
            QTimer = None
        # Schedule of retry delays (ms) measured from each call.
        retry_delays = [400, 800, 1500]
        dialogs = Plugin._find_plugins_manager_dialogs()
        _logger.info(
            "auto-close plugins dialog: attempt={} found={}".format(
                attempt, len(dialogs)
            )
        )
        for d in dialogs:
            Plugin._try_dismiss_dialog(d)
        # Re-check: anything still visible?
        still_open = Plugin._find_plugins_manager_dialogs()
        if not still_open:
            _logger.info("plugins dialog closed successfully")
            return
        if attempt < len(retry_delays) and QTimer is not None:
            QTimer.singleShot(
                retry_delays[attempt],
                lambda: Plugin._handle_plugins_manager_dialog(attempt + 1),
            )
            return
        # Final fallback: we could not close it -> at least raise it to the
        # front so it does not stay hidden in the background.
        _logger.info(
            "could not close plugins dialog after {} attempts; "
            "bringing it to front".format(attempt + 1)
        )
        for d in still_open:
            try:
                d.showNormal()
                d.raise_()
                d.activateWindow()
            except Exception as e:
                _logger.debug("could not raise plugins dialog: {}".format(e))

    def _setup_window(self, window, *, load_open_wallet):
        """Create the BalWindow for *window* and wire its menu (and, when
        enabling hot, the already-open wallet).

        This mirrors what the ``init_menubar`` + ``load_wallet`` hooks do at
        normal startup, so enabling the plugin while a wallet is open no longer
        requires restarting Electrum.
        """
        w = self.get_window(window)
        # Use Electrum's official tools_menu instead of searching the menubar
        # for a menu whose *translated* title equals "&Tools" (which breaks
        # under non-English locales).
        tools_menu = getattr(window, "tools_menu", None)
        if tools_menu is not None:
            try:
                w.init_menubar_tools(tools_menu)
            except Exception as e:
                _logger.error("init_qt: failed wiring tools menu: {}".format(e))
        if load_open_wallet and getattr(window, "wallet", None):
            # Replicate load_wallet() for the wallet that is already open.
            try:
                w.wallet = window.wallet
                w.init_will()
                w.willexecutors = Willexecutors.get_willexecutors(
                    self, update=False, bal_window=w
                )
                w.disable_plugin = False
                w.ok = True
            except Exception as e:
                _logger.error("init_qt: failed initialising open wallet: {}".format(e))
        return w

    @hook
    def create_status_bar(self, sb):
        # Show the BAL icon in the status bar (bottom-right): it signals that
        # the Bitcoin After Life plugin is installed and, when clicked, quickly
        # opens the plugin settings (settings_dialog).
        #
        # NOTE: this was NOT the "condensed menu/tabs" bug under the Electrum
        # logo -- that one was a Windows OverflowError (year 2038), fixed
        # separately.  The icon must therefore be kept.
        #
        # To avoid a duplicated icon on restart / wallet switch, we track the
        # button by id(sb.window()) and remove the stale one before creating a
        # fresh one.
        _logger.info("HOOK create status bar")
        key = id(sb.window())
        old = self._statusbar_buttons.pop(key, None)
        if old is not None:
            try:
                old.setParent(None)
                old.deleteLater()
            except Exception:
                pass
        b = StatusBarButton(
            read_QIcon_from_bytes(self.read_file("icons/bal32x32.png")),
            "Bal " + _("Bitcoin After Life"),
            lambda: self.settings_dialog(sb.window()),
            sb.height(),
        )
        sb.addPermanentWidget(b)
        self._statusbar_buttons[key] = b

        # When the plugin is enabled "hot" from Tools -> Plugins, Electrum keeps
        # its "Electrum Plugins" manager dialog open and even calls
        # bring_to_front on it. Enabling triggers reload_windows(), which
        # recreates the window and therefore fires this create_status_bar hook;
        # that makes this the right place to auto-close the leftover manager
        # dialog (Electrum 4.7.x no longer calls the old init_qt hook).
        #
        # We use a QTimer so this runs *after* Electrum's own bring_to_front
        # (QTimer.singleShot(100, ...)); a slightly larger delay makes our close
        # win. On a normal startup no PluginsDialog is open, so the helper is a
        # harmless no-op.
        QTimer.singleShot(250, self._close_plugins_manager_dialog)

    @hook
    def init_menubar(self, window):
        _logger.info("HOOK init_menubar")
        w = self.get_window(window)
        w.init_menubar_tools(window.tools_menu)
        # Also try here: init_menubar is one of the hooks fired when Electrum
        # recreates the window during a hot enable (reload_windows()), so it is
        # another reliable trigger to auto-close the leftover manager dialog.
        QTimer.singleShot(300, self._close_plugins_manager_dialog)

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
        # load_wallet is fired on the recreated window during a hot enable too;
        # use it as an extra trigger to auto-close the leftover manager dialog.
        QTimer.singleShot(350, self._close_plugins_manager_dialog)

    @hook
    def close_wallet(self, wallet):
        _logger.debug("HOOK close wallet")
        # Iterate over a snapshot: on_close() may mutate the GUI/state.
        for win in list(self.bal_windows.values()):
            if getattr(win, "wallet", None) == wallet:
                try:
                    win.on_close()
                except Exception as e:
                    _logger.error("close_wallet: on_close failed: {}".format(e))

    @hook
    def init_keystore(self):
        _logger.debug("init keystore")

    @hook
    def daemon_wallet_loaded(self, boh, wallet):
        _logger.debug("daemon wallet loaded")

    def get_window(self, window):
        window = window.top_level_window()
        key = _window_key(window)
        w = self.bal_windows.get(key, None)
        if w is None:
            w = BalWindow(self, window)
            self.bal_windows[key] = w
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

        # Auto-sign checkbox (Group B / B2). When ticked, the "Check" action
        # automatically signs and broadcasts the will after querying the
        # will-executor servers. Bound to the persisted AUTO_SIGN config; the
        # default is ON (see plugin_base.py).
        heir_auto_sign = BalCheckBox(self.AUTO_SIGN)

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
            "Auto-sign on Check",
            heir_auto_sign,
            3,
            (
                "When checking, automatically sign and broadcast the will "
                "transactions to their will-executors.\n"
                "The wallet password is requested only if the wallet is "
                "encrypted."
            ),
        )
        add_widget(
            grid,
            "Calendar App",
            BalLineEdit(self.CALENDAR_APP),
            4,
            "Default app used to open calendar",
        )
        add_widget(
            grid,
            "Event summary",
            BalLineEdit(self.EVENT_SUMMARY),
            5,
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
            "Event description",
            BalTextEdit(self.EVENT_DESCRIPTION),
            6,
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

        if ret := bool(show_modal(d)):
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


