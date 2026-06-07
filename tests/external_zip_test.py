"""Regression test: load the plugin the way Electrum loads an *external* zip.

When a user installs the plugin via Electrum's "Plugins" dialog from a .zip,
Electrum 4.7.x imports it under the synthetic top-level package
``electrum_external_plugins.bal`` and only executes the package ``__init__``
and the ``qt`` module.  It does NOT pre-register the synthetic root package
nor the nested ``gui`` / ``gui.qt`` sub-packages.

A naive ``from .gui.qt.plugin import Plugin`` in ``qt.py`` therefore fails with::

    ModuleNotFoundError: No module named 'electrum_external_plugins'

This test reproduces that exact loading sequence against the built zip and
asserts that the resilient ``qt.py`` shim resolves the ``Plugin`` class.

Usage:
    QT_QPA_PLATFORM=offscreen \
    PYTHONPATH=<electrum-src> \
    python3 tests/external_zip_test.py <path-to-bal-electrum-plugin.zip>
"""

import importlib.util
import sys
import zipimport


def main(zip_path: str) -> int:
    base = "electrum_external_plugins.bal"
    gui = "qt"
    dirname = "bal"  # directory name inside the zip archive

    def exec_module_from_spec(spec, path):
        # Mirrors electrum.plugin.PluginManager.exec_module_from_spec
        module = importlib.util.module_from_spec(spec)
        sys.modules[path] = module
        spec.loader.exec_module(module)
        return module

    zi = zipimport.zipimporter(zip_path)

    # Step 1: load the package __init__ as electrum_external_plugins.bal
    init_spec = zi.find_spec(dirname)
    assert init_spec is not None, "could not find package __init__ inside zip"
    exec_module_from_spec(init_spec, base)

    # Step 2: load the qt entry-point as electrum_external_plugins.bal.qt
    full = f"{base}.{gui}"
    spec = importlib.util.find_spec(full)
    assert spec is not None, f"could not find spec for {full!r}"
    module = exec_module_from_spec(spec, full)

    # The loader expects a `Plugin` class to be exported.
    plugin_cls = getattr(module, "Plugin", None)
    assert plugin_cls is not None, "qt module did not export a Plugin class"

    print(f"[OK] external zip loads Plugin -> {plugin_cls!r}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
