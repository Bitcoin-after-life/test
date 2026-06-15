"""
Tests for wallet-dependent methods in ``bal.core.will``.

Uses mocking to simulate Electrum wallet, network, and db.

Run:
    source electrum/env/bin/activate
    QT_QPA_PLATFORM=offscreen python3 tests/test_core_will_extra.py
"""

import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.will import Will, WillItem
from electrum.transaction import Transaction

_VALID_TX_HEX = (
    "01000000012a5c9a94fcde98f5581cd00162c60a13936ceb75389ea65b"
    "f38633b424eb4031000000006c493046022100a82bbc57a0136751e543"
    "3f41cf000b3f1a99c6744775e76ec764fb78c54ee100022100f9e80b7d"
    "e89de861dc6fb0c1429d5da72c2b6b2ee2406bc9bfb1beedd729d98501"
    "2102e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae3"
    "5cdb84d2f6ffffffff0140420f00000000001976a914230ac37834073a"
    "42146f11ef8414ae929feaafc388ac00000000"
)


# Patch Transaction.add_info_from_wallet so it's a no-op during all tests
_patcher = patch.object(Transaction, "add_info_from_wallet")
_patcher.start()


# ------------------------------------------------------------------ #
# Will.check_tx_height
# ------------------------------------------------------------------ #

def test_check_tx_height():
    wallet = MagicMock()
    wallet.get_tx_info.return_value.tx_mined_status.height.return_value = 100
    tx = MagicMock()
    assert Will.check_tx_height(tx, wallet) == 100


def test_check_tx_height_zero():
    wallet = MagicMock()
    wallet.get_tx_info.return_value.tx_mined_status.height.return_value = 0
    tx = MagicMock()
    assert Will.check_tx_height(tx, wallet) == 0





# ------------------------------------------------------------------ #
# Will.add_info_from_will
# ------------------------------------------------------------------ #

def test_add_info_from_will():
    wallet = MagicMock()
    willitem = MagicMock()
    will = {"wid": willitem}
    Will.add_info_from_will(will, "wid", wallet)
    willitem.tx.add_info_from_wallet.assert_called_once_with(wallet)


def test_add_info_from_will_no_wallet():
    willitem = MagicMock()
    will = {"wid": willitem}
    Will.add_info_from_will(will, "wid", None)


def test_add_info_from_will_tx_is_str():
    wallet = MagicMock()
    willitem = MagicMock()
    willitem.tx = _VALID_TX_HEX
    will = {"wid": willitem}
    Will.add_info_from_will(will, "wid", wallet)
    assert hasattr(willitem.tx, "add_info_from_wallet")


# ------------------------------------------------------------------ #
# Will.check_invalidated
# ------------------------------------------------------------------ #

def test_check_invalidated_confirmed():
    wallet = MagicMock()
    wallet.get_tx_info.return_value.tx_mined_status.height.return_value = 100
    item = WillItem({"tx": _VALID_TX_HEX, "heirs": {"a": ["addr", 100, "30d"]},
                     "willexecutor": None, "status": "", "description": "",
                     "time": 0, "change": "", "baltx_fees": 100})
    will = {"wid": item}
    Will.check_invalidated(will, [], wallet)
    assert item.get_status("CONFIRMED") is True


def test_check_invalidated_pending():
    wallet = MagicMock()
    wallet.get_tx_info.return_value.tx_mined_status.height.return_value = 0
    item = WillItem({"tx": _VALID_TX_HEX, "heirs": {"a": ["addr", 100, "30d"]},
                     "willexecutor": None, "status": "", "description": "",
                     "time": 0, "change": "", "baltx_fees": 100})
    will = {"wid": item}
    Will.check_invalidated(will, [], wallet)
    assert item.get_status("PENDING") is True


def test_check_invalidated_invalidated():
    wallet = MagicMock()
    wallet.get_tx_info.return_value.tx_mined_status.height.return_value = -1
    item = WillItem({"tx": _VALID_TX_HEX, "heirs": {"a": ["addr", 100, "30d"]},
                     "willexecutor": None, "status": "", "description": "",
                     "time": 0, "change": "", "baltx_fees": 100})
    will = {"wid": item}
    Will.check_invalidated(will, [], wallet)
    assert item.get_status("INVALIDATED") is True


# ------------------------------------------------------------------ #
# Will.check_will (exercises check_invalidated + search_rai)
# ------------------------------------------------------------------ #

def test_check_will():
    wallet = MagicMock()
    wallet.get_tx_info.return_value.tx_mined_status.height.return_value = 0
    item = WillItem({"tx": _VALID_TX_HEX, "heirs": {"a": ["addr", 100, "30d"]},
                     "willexecutor": None, "status": "", "description": "",
                     "time": 0, "change": "", "baltx_fees": 100})
    will = {"wid": item}
    Will.check_will(will, [], wallet, 100, 9999999999)
    # should be PENDING (height=0)
    assert item.get_status("PENDING") is True


# ------------------------------------------------------------------ #
# WillItem.__init__ with wallet
# ------------------------------------------------------------------ #

def test_willitem_init_with_wallet():
    wallet = MagicMock()
    w = {"tx": _VALID_TX_HEX, "heirs": {"a": ["addr", 100, "30d"]},
         "willexecutor": None, "status": "", "description": "",
         "time": 0, "change": "", "baltx_fees": 100}
    item = WillItem(w, wallet=wallet)
    assert item is not None


def test_willitem_init_without_wallet():
    w = {"tx": _VALID_TX_HEX, "heirs": {"a": ["addr", 100, "30d"]},
         "willexecutor": None, "status": "", "description": "",
         "time": 0, "change": "", "baltx_fees": 100}
    item = WillItem(w)
    assert item is not None


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All will-extra tests passed")
