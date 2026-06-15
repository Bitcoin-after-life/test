"""Regression tests for the GUI window/lifecycle fixes (B1-B10).

These tests need a QApplication but run head-less under
``QT_QPA_PLATFORM=offscreen``.  They check the *behaviour* of the centralized
window helpers and assert that the known bug patterns are gone, without trying
to drive a full Electrum session.

Usage:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
        python3 tests/gui_fixes_test.py <PKG>
where <PKG> is e.g. electrum.plugins.bal
"""

import ast
import importlib
import inspect
import sys


def _active_source_without_strings(module) -> str:
    """Return module source with docstrings/strings removed.

    Lets us assert a token is absent from *executable* code even if it still
    appears inside an explanatory docstring/comment.
    """
    src = inspect.getsource(module)
    tree = ast.parse(src)
    # collect string-constant spans to drop
    class _S(ast.NodeVisitor):
        def __init__(self):
            self.spans = []
        def visit_Constant(self, node):
            if isinstance(node.value, str) and hasattr(node, "end_lineno"):
                self.spans.append((node.lineno, node.end_lineno))
            self.generic_visit(node)
    s = _S(); s.visit(tree)
    drop = set()
    for a, b in s.spans:
        drop.update(range(a, b + 1))
    lines = src.splitlines()
    kept = [ln for i, ln in enumerate(lines, start=1)
            if i not in drop and not ln.lstrip().startswith("#")]
    return "\n".join(kept)


def main(pkg: str) -> int:
    from PyQt6.QtWidgets import QApplication, QDialog, QWidget
    app = QApplication.instance() or QApplication(sys.argv)

    wu = importlib.import_module(pkg + ".gui.qt.window_utils")

    # top_level_of: returns the top-level container of a child widget
    w = QWidget(); child = QWidget(w)
    assert wu.top_level_of(child) is w
    assert wu.top_level_of(None) is None
    print("[OK] top_level_of")

    # bring_to_front / stop_thread must never raise on edge inputs
    wu.bring_to_front(QDialog())
    wu.stop_thread(None)
    print("[OK] bring_to_front / stop_thread(None)")

    # _window_key: stable and unique per window
    plugin_mod = importlib.import_module(pkg + ".gui.qt.plugin")
    a, b = QWidget(), QWidget()
    assert plugin_mod._window_key(a) == plugin_mod._window_key(a)
    assert plugin_mod._window_key(a) != plugin_mod._window_key(b)
    print("[OK] _window_key stable & unique")

    # B3/B4: no winId bound-method key, no 'restart Electrum' surrender in
    # *executable* code (docstrings explaining the old behaviour are allowed).
    active = _active_source_without_strings(plugin_mod)
    assert "winId" not in active, "winId still used in executable code"
    print("[OK] no winId in executable code")

    win_mod = importlib.import_module(pkg + ".gui.qt.window")
    active_win = _active_source_without_strings(win_mod)
    assert "restart Electrum" not in active_win
    print("[OK] no 'restart Electrum' surrender in window.py code")

    # B1: BalDialog must not shadow QWidget.parent() with an attribute
    dialogs_mod = importlib.import_module(pkg + ".gui.qt.dialogs")
    dsrc = inspect.getsource(dialogs_mod)
    assert "self.parent =" not in dsrc, "self.parent assignment still present"
    print("[OK] no self.parent shadowing in dialogs.py")

    # REGRESSION: BalDialog.closeEvent / hideEvent must NOT stop the task
    # thread.  Electrum's TaskThread.on_done calls cb_done (often self.accept,
    # which closes the dialog) BEFORE cb_result (on_success, e.g. updating the
    # will-executor list).  If the base closeEvent stopped/joined the thread,
    # the auto-close from accept() would tear the thread down before
    # on_success ran and the downloaded list would be silently dropped.
    close_src = inspect.getsource(dialogs_mod.BalDialog.closeEvent)
    hide_src = inspect.getsource(dialogs_mod.BalDialog.hideEvent)
    assert "stop_thread" not in close_src, (
        "BalDialog.closeEvent must not stop the thread (drops download result)")
    assert "stop_thread" not in hide_src, (
        "BalDialog.hideEvent must not stop the thread (drops download result)")
    print("[OK] BalDialog.closeEvent/hideEvent do not kill the task thread")

    # REGRESSION: init_menubar_tools must be idempotent.  Electrum can invoke
    # both the init_menubar hook and the hot-init path (init_qt -> _setup_window)
    # for the same window (e.g. on restart with the plugin already enabled);
    # wiring the tabs/menu actions twice produces a garbled, condensed menu
    # entry under the Electrum logo.  Verify the guard flag is in place.
    bal_window_cls = win_mod.BalWindow
    menubar_src = inspect.getsource(bal_window_cls.init_menubar_tools)
    assert "_menubar_initialized" in menubar_src, (
        "init_menubar_tools must guard against double initialisation")
    init_src = inspect.getsource(bal_window_cls.__init__)
    assert "_menubar_initialized" in init_src, (
        "_menubar_initialized must be initialised in BalWindow.__init__")
    onclose_src = inspect.getsource(bal_window_cls.on_close)
    assert "_menubar_initialized" in onclose_src, (
        "on_close must reset _menubar_initialized so the window can be reused")
    print("[OK] init_menubar_tools is idempotent (no duplicate tabs/menu)")

    # REGRESSION: create_status_bar MUST add the BAL status-bar icon (bottom
    # right of the Electrum window).  It signals that the plugin is installed
    # and, when clicked, opens the plugin settings.  An earlier change wrongly
    # turned this into a no-op while chasing the "condensed menu" bug (whose
    # real cause was a Windows OverflowError, fixed elsewhere), which made the
    # icon disappear.  The icon must stay, and must not be duplicated on
    # restart / wallet switch (hence the _statusbar_buttons book-keeping).
    csb_body = inspect.getsource(plugin_mod.Plugin.create_status_bar)
    csb_code = "\n".join(
        line for line in csb_body.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "StatusBarButton" in csb_code, (
        "create_status_bar must build a StatusBarButton (the BAL icon)")
    assert "addPermanentWidget" in csb_code, (
        "create_status_bar must add the BAL icon to the status bar")
    assert "settings_dialog" in csb_code, (
        "clicking the BAL icon must open settings_dialog")
    assert "_statusbar_buttons" in csb_code, (
        "create_status_bar must track buttons to avoid duplicate icons")
    # __init__ must initialise the tracking dict.
    init_code = inspect.getsource(plugin_mod.Plugin.__init__)
    assert "_statusbar_buttons" in init_code, (
        "Plugin.__init__ must initialise self._statusbar_buttons")
    print("[OK] create_status_bar adds the BAL icon + opens settings on click")

    print(f"\n[OK] all GUI-fix checks passed for package {pkg!r}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
