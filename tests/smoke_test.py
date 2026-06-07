"""
Smoke test for the BAL Electrum plugin.

Goal: after every refactor step, prove that the plugin still imports cleanly
under a real Electrum 4.7.2 + PyQt6 install, and that a handful of pure-logic
behaviours produce *exactly* the same results as before (regression guard).

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py <PLUGIN_IMPORT_NAME>

where <PLUGIN_IMPORT_NAME> is the dotted module path the plugin is reachable
at, e.g. "electrum.plugins.BAL" (original) or "electrum.plugins.bal" (new).
"""
import importlib
import sys

PKG = sys.argv[1] if len(sys.argv) > 1 else "electrum.plugins.BAL"


def imp(mod):
    return importlib.import_module(f"{PKG}.{mod}")


def main():
    # --- Qt must be initialised before importing any gui module ---
    from PyQt6.QtWidgets import QApplication  # noqa
    _app = QApplication.instance() or QApplication([])

    results = {}

    # 1) Core modules import (these must be GUI-free).
    bal = imp_core("bal", "core.plugin_base")
    util = imp_core("util", "core.util")
    heirs = imp_core("heirs", "core.heirs")
    will = imp_core("will", "core.will")
    we = imp_core("willexecutors", "core.willexecutors")

    # 2) GUI module imports.
    qt = imp_gui()

    # 3) Behaviour checks (pure logic, must be identical across versions).
    BalTimestamp = bal.BalTimestamp
    assert BalTimestamp("30d").duration_to_days() == 30, "BalTimestamp 30d"
    assert BalTimestamp("1y").duration_to_days() == 365, "BalTimestamp 1y"
    assert str(BalTimestamp("7d")) == "7d", "BalTimestamp str"

    Util = util.Util
    assert Util.is_perc("50%") is True
    assert Util.is_perc("100") is False
    assert Util.text_to_hex("BAL") == "42414c"
    assert Util.hex_to_text("42414c") == "BAL"
    assert Util.int_locktime(days=1) == 86400

    # heirs constants must keep the same column layout (very delicate!)
    assert heirs.HEIR_ADDRESS == 0
    assert heirs.HEIR_AMOUNT == 1
    assert heirs.HEIR_LOCKTIME == 2
    assert heirs.HEIR_REAL_AMOUNT == 3
    assert heirs.HEIR_DUST_AMOUNT == 4

    # WillItem default status table must stay intact.
    assert will.WillItem.STATUS_DEFAULT["VALID"][1] is True

    # 4) Plugin class wiring.
    assert qt.Plugin.__bases__[0] is bal.BalPlugin
    for h in ("create_status_bar", "init_menubar", "load_wallet", "close_wallet"):
        assert hasattr(qt.Plugin, h), f"missing hook {h}"

    print(f"[OK] smoke test passed for package '{PKG}'")


def imp_core(old_name, new_name):
    """Import a core module, trying the new layout first then the old flat one."""
    for candidate in (new_name, old_name):
        try:
            return importlib.import_module(f"{PKG}.{candidate}")
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(f"cannot import {old_name}/{new_name} from {PKG}")


def imp_gui():
    for candidate in ("gui.qt.plugin", "qt"):
        try:
            return importlib.import_module(f"{PKG}.{candidate}")
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(f"cannot import gui module from {PKG}")


if __name__ == "__main__":
    main()
