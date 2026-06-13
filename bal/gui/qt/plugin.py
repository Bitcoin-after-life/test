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

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"
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


