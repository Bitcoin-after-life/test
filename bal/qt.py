"""
bal.qt
======

Thin compatibility shim for Electrum's plugin loader.

Electrum loads a Qt plugin by importing the ``qt`` module of the plugin package
and looking for a ``Plugin`` class.  The real implementation now lives in the
well-separated :mod:`bal.gui.qt` sub-package, so this file simply re-exports the
:class:`Plugin` class from :mod:`bal.gui.qt.plugin`.

Keeping this shim means the package layout can stay clean (logic in ``core``,
GUI in ``gui/qt``) without changing what Electrum expects to import.
"""

from .gui.qt.plugin import Plugin  # noqa: F401  (re-exported for Electrum)
