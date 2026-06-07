"""
bal.qt
======

Compatibility shim for Electrum's plugin loader.

Electrum loads a Qt plugin by importing the ``qt`` module of the plugin package
and looking for a ``Plugin`` class.  The real implementation lives in the
well-separated ``bal.gui.qt`` sub-package, so this module re-exports the
``Plugin`` class from ``bal.gui.qt.plugin``.

Why this file is not a one-line relative import
-----------------------------------------------
A plain ``from .gui.qt.plugin import Plugin`` works fine when the plugin is
installed as an *internal* plugin (under ``electrum/plugins/bal``).  However,
when the very same code is loaded as an *external* plugin from a ``.zip``,
Electrum 4.7.x imports the package under the synthetic top-level name
``electrum_external_plugins.bal`` and only executes the package ``__init__`` and
this ``qt`` module.  It never registers the intermediate parent packages
(``electrum_external_plugins`` itself, ``...bal.gui``, ``...bal.gui.qt``).  As a
result, a relative import that has to walk up to those parents fails with::

    ModuleNotFoundError: No module named 'electrum_external_plugins'

To make the plugin work *both* as an internal package and as an external zip,
this shim resolves and imports ``Plugin`` defensively:

1. It works out the name of the package this module lives in
   (``__package__``), whatever Electrum decided to call it.
2. It makes sure every parent package in that chain exists in
   ``sys.modules`` so Python's import machinery can resolve sub-modules.
3. It imports the ``.gui.qt.plugin`` sub-module via :func:`importlib.import_module`
   using the resolved absolute name.

This keeps the clean ``core`` / ``gui`` layout while staying robust to how the
plugin is loaded.
"""

import importlib
import sys


def _ensure_parent_packages(pkg_name: str) -> None:
    """Make sure every ancestor package of *pkg_name* is in ``sys.modules``.

    When loaded from a zip as an external plugin, Electrum only executes the
    plugin package ``__init__`` and the ``qt`` module.  The synthetic root
    package (e.g. ``electrum_external_plugins``) and any intermediate packages
    may be missing from ``sys.modules``, which breaks relative/absolute
    sub-module imports.  We backfill them here using this module's own loader
    so that ``importlib`` can find sibling sub-packages.
    """
    parts = pkg_name.split(".")
    # Walk from the top-most ancestor down to (but not including) pkg_name.
    for i in range(1, len(parts)):
        ancestor = ".".join(parts[:i])
        if ancestor in sys.modules:
            continue
        try:
            importlib.import_module(ancestor)
        except Exception:
            # The synthetic root (e.g. 'electrum_external_plugins') often has no
            # real spec.  Create a minimal namespace package stub so that the
            # import machinery can still resolve its children.
            import types

            module = types.ModuleType(ancestor)
            module.__path__ = []  # mark as a (namespace) package
            sys.modules[ancestor] = module


# The package this module belongs to. Could be 'electrum.plugins.bal' (internal)
# or 'electrum_external_plugins.bal' (external zip), depending on how Electrum
# loaded us.
_PKG = __package__ or "bal"

_ensure_parent_packages(_PKG)

# Import the real implementation using the fully-qualified, run-time package
# name so it works regardless of the synthetic prefix Electrum assigned.
_plugin_module = importlib.import_module(_PKG + ".gui.qt.plugin")

Plugin = _plugin_module.Plugin  # noqa: F401  (re-exported for Electrum)
