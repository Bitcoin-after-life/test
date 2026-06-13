"""
bal.gui.qt.window_utils
=======================

Centralized window/dialog presentation helpers.

The original plugin opened dialogs inconsistently: some with ``exec()``
(modal, stays on top) and some with ``show()`` (modeless, can fall *behind*
the main Electrum window). It also relied on a per-instance ``self.parent``
attribute that shadows :meth:`QWidget.parent`, and it never gave non-modal
dialogs focus, so they could disappear behind Electrum.

To fix this *without changing the business logic*, all the "how is this window
shown / focused / parented" concerns are collected here. The rest of the GUI
code just calls these helpers, so the behaviour is consistent and easy to
audit.

None of these helpers change *what* a dialog does — only its parenting,
modality and z-order/focus.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


def top_level_of(widget):
    """Return the proper top-level window to use as a dialog parent.

    Electrum widgets expose ``top_level_window()``; when available we use it so
    the dialog is anchored to the real top-level Electrum window (and therefore
    stays in front of it). Falls back to the widget's own ``window()`` or the
    widget itself.
    """
    if widget is None:
        return None
    # Electrum's MessageBoxMixin / ElectrumWindow provide top_level_window().
    tlw = getattr(widget, "top_level_window", None)
    if callable(tlw):
        try:
            return tlw()
        except Exception:
            pass
    # Plain QWidget: window() returns the top-level container.
    if isinstance(widget, QWidget):
        try:
            return widget.window()
        except Exception:
            pass
    return widget


def bring_to_front(dialog):
    """Make a *visible* dialog actually appear in front and take focus.

    ``raise_()`` alone is not enough on some window managers (notably Windows):
    without ``activateWindow()`` the dialog can stay behind the main window.
    """
    try:
        dialog.raise_()
        dialog.activateWindow()
    except Exception:
        pass


def stop_thread(thread):
    """Safely stop and join an Electrum ``TaskThread`` if present.

    The original code commented out thread teardown, leaving background
    threads running after a dialog closed (which could touch destroyed widgets
    or keep network connections open until Electrum was restarted).  This
    stops the thread and waits for it to finish, guarding against ``None`` and
    any teardown error.
    """
    if thread is None:
        return
    try:
        thread.stop()
    except Exception:
        pass
    try:
        thread.wait()
    except Exception:
        pass


def show_modal(dialog):
    """Show *dialog* modally and return the result of ``exec()``.

    Modal dialogs always stay in front of their parent, which is the desired
    behaviour for the plugin's editing/confirmation dialogs.
    """
    try:
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
    except Exception:
        pass
    bring_to_front(dialog)
    return dialog.exec()


def show_on_top(dialog, *, modal_to_window=True):
    """Show *dialog* non-modally but guaranteed in front of Electrum.

    Use this for the few dialogs that must remain non-modal (e.g. the
    transaction dialog the user may want to keep open alongside the wallet).
    It sets window-modality (so it stays above its parent window without
    blocking the whole application) and gives it focus.

    Set ``modal_to_window=False`` for a completely modeless window.
    """
    try:
        if modal_to_window:
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
        else:
            dialog.setWindowModality(Qt.WindowModality.NonModal)
    except Exception:
        pass
    dialog.show()
    bring_to_front(dialog)
    return dialog
