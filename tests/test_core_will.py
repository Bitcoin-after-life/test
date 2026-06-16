"""
Tests for ``bal.core.will``.

Covers WillItem, Will static methods, and exception classes.

Run:
    source electrum/env/bin/activate
    python3 tests/test_core_will.py
"""

import sys
import os
import copy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.will import WillItem, Will
from bal.core.willexecutors import Willexecutors

# A valid serialized Bitcoin transaction hex (1 input + 1 P2PKH output, version 2)
_VALID_TX_HEX = (
    "01000000012a5c9a94fcde98f5581cd00162c60a13936ceb75389ea65b"
    "f38633b424eb4031000000006c493046022100a82bbc57a0136751e543"
    "3f41cf000b3f1a99c6744775e76ec764fb78c54ee100022100f9e80b7d"
    "e89de861dc6fb0c1429d5da72c2b6b2ee2406bc9bfb1beedd729d98501"
    "2102e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae3"
    "5cdb84d2f6ffffffff0140420f00000000001976a914230ac37834073a"
    "42146f11ef8414ae929feaafc388ac00000000"
)


def _make_minimal_willitem_dict(**overrides):
    """Return a minimal dict that can construct a WillItem."""
    d = {
        "tx": _VALID_TX_HEX,
        "heirs": {"alice": ["addr1", 5000, "30d"]},
        "willexecutor": None,
        "status": "",
        "description": "",
        "time": 0,
        "change": "",
        "baltx_fees": 100,
    }
    d.update(overrides)
    return d


def _make_willitem_blank():
    """Create a fresh WillItem from scratch."""
    item = WillItem(_make_minimal_willitem_dict())
    # Reset STATUS to clean defaults
    item.STATUS = copy.deepcopy(WillItem.STATUS_DEFAULT)
    return item


def test_willitem_default_status():
    assert WillItem.STATUS_DEFAULT["VALID"][1] is True
    assert WillItem.STATUS_DEFAULT["COMPLETE"][1] is False
    assert WillItem.STATUS_DEFAULT["INVALIDATED"][1] is False
    assert WillItem.STATUS_DEFAULT["REPLACED"][1] is False


def test_willitem_set_get_status():
    # Create a WillItem from a copy of another to avoid tx parsing issues
    item = _make_willitem_blank()
    assert item.get_status("VALID") is True

    result = item.set_status("COMPLETE", True)
    assert result is True
    assert item.get_status("COMPLETE") is True

    # Setting to same value returns None
    result = item.set_status("COMPLETE", True)
    assert result is None


def test_willitem_invalidated_clears_valid():
    item = _make_willitem_blank()
    assert item.get_status("VALID") is True

    item.set_status("INVALIDATED", True)
    assert item.get_status("INVALIDATED") is True
    assert item.get_status("VALID") is False  # INVALIDATED clears VALID


def test_willitem_replaced_clears_valid():
    item = _make_willitem_blank()
    item.set_status("REPLACED", True)
    assert item.get_status("VALID") is False


def test_willitem_pushed_clears_push_fail():
    item = _make_willitem_blank()
    item.set_status("PUSH_FAIL", True)
    assert item.get_status("PUSH_FAIL") is True

    item.set_status("PUSHED", True)
    assert item.get_status("PUSHED") is True
    assert item.get_status("PUSH_FAIL") is False
    assert item.get_status("CHECK_FAIL") is False


def test_willitem_checked_sets_pushed():
    item = _make_willitem_blank()
    item.set_status("CHECKED", True)
    assert item.get_status("PUSHED") is True
    assert item.get_status("PUSH_FAIL") is False


def test_willitem_to_dict():
    item = _make_willitem_blank()
    d = item.to_dict()
    assert "heirs" in d
    assert "tx" in d
    assert "VALID" in d


def test_willitem_str_repr():
    item = _make_willitem_blank()
    s = str(item)
    assert isinstance(s, str)
    r = repr(item)
    assert r == s


# ------------------------------------------------------------------ #
# Will static methods
# ------------------------------------------------------------------ #

def test_will_get_sorted_will():
    # Use a simple dict structure that will[key]["tx"].locktime works
    class FakeTx:
        def __init__(self, locktime):
            self.locktime = locktime

    will = {
        "b": {"tx": FakeTx(200)},
        "a": {"tx": FakeTx(100)},
    }
    sorted_will = Will.get_sorted_will(will)
    assert len(sorted_will) == 2
    assert sorted_will[0][1]["tx"].locktime == 100
    assert sorted_will[1][1]["tx"].locktime == 200


def test_will_only_valid():
    item1 = _make_willitem_blank()
    item2 = _make_willitem_blank()
    item2.set_status("INVALIDATED", True)

    will = {"a": item1, "b": item2}
    valid = list(Will.only_valid(will))
    assert "a" in valid
    assert "b" not in valid


def test_will_only_valid_list():
    item1 = _make_willitem_blank()
    item2 = _make_willitem_blank()
    item2.set_status("INVALIDATED", True)

    will = {"a": item1, "b": item2}
    result = Will.only_valid_list(will)
    assert "a" in result
    assert "b" not in result


def _make_will_with_heirs(heirs, tx_locktime):
    """Build a single-item will whose stored heirs == ``heirs`` and whose
    frozen tx.locktime == ``tx_locktime`` (what the will-executors hold)."""
    item = WillItem(_make_minimal_willitem_dict(heirs=copy.deepcopy(heirs)))
    item.STATUS = copy.deepcopy(WillItem.STATUS_DEFAULT)
    item.tx.locktime = tx_locktime
    return {"willid_1": item}


def test_check_heirs_unchanged_is_coherent():
    """No heir change -> the will stays coherent (no rebuild)."""
    lt = 1900000000
    heirs = {"alice": ["addr_alice", 5000, str(lt)]}
    will = _make_will_with_heirs(heirs, lt)
    result = Will.check_willexecutors_and_heirs(
        will, copy.deepcopy(heirs), {}, False, 0, 100
    )
    assert result is True


def test_check_heir_removed_triggers_rebuild():
    """Removing an heir MUST be detected (HeirNotFoundException), so the Check
    button and on_close rebuild the inheritance.  Regression test for the bug
    where a removed heir silently stayed in the transaction."""
    from bal.core.will import HeirNotFoundException
    lt = 1900000000
    will_heirs = {
        "alice": ["addr_alice", 5000, str(lt)],
        "bob": ["addr_bob", 3000, str(lt)],
    }
    current_heirs = {"alice": ["addr_alice", 5000, str(lt)]}  # bob removed
    will = _make_will_with_heirs(will_heirs, lt)
    raised = False
    try:
        Will.check_willexecutors_and_heirs(
            will, current_heirs, {}, False, 0, 100
        )
    except HeirNotFoundException:
        raised = True
    assert raised, "removing an heir must raise HeirNotFoundException"


def test_check_heir_added_triggers_rebuild():
    """Adding an heir must be detected (HeirNotFoundException)."""
    from bal.core.will import HeirNotFoundException
    lt = 1900000000
    will_heirs = {"alice": ["addr_alice", 5000, str(lt)]}
    current_heirs = {
        "alice": ["addr_alice", 5000, str(lt)],
        "bob": ["addr_bob", 3000, str(lt)],  # added
    }
    will = _make_will_with_heirs(will_heirs, lt)
    raised = False
    try:
        Will.check_willexecutors_and_heirs(
            will, current_heirs, {}, False, 0, 100
        )
    except HeirNotFoundException:
        raised = True
    assert raised, "adding an heir must raise HeirNotFoundException"


def test_needs_server_check():
    """Check button selection logic: a VALID will with a will-executor that is
    not yet CHECKED must be queried on the server, even if it is not PUSHED
    (regression for the 'New / Not sent' wills that Check ignored)."""
    we = {"url": "https://we.example.com"}

    # New (not PUSHED) but has a will-executor -> must be checked.
    item_new = _make_willitem_blank()
    item_new.we = we
    assert Will.needs_server_check(item_new) is True

    # PUSHED but not CHECKED -> must be checked (previous behaviour).
    item_pushed = _make_willitem_blank()
    item_pushed.we = we
    item_pushed.set_status("PUSHED", True)
    assert Will.needs_server_check(item_pushed) is True

    # Already CHECKED -> no need to check again.
    item_checked = _make_willitem_blank()
    item_checked.we = we
    item_checked.set_status("CHECKED", True)
    assert Will.needs_server_check(item_checked) is False

    # No will-executor assigned -> nothing to check on a server.
    item_no_we = _make_willitem_blank()
    item_no_we.we = None
    assert Will.needs_server_check(item_no_we) is False

    # Not VALID (e.g. invalidated) -> not checked.
    item_invalid = _make_willitem_blank()
    item_invalid.we = we
    item_invalid.set_status("INVALIDATED", True)
    assert Will.needs_server_check(item_invalid) is False


def test_will_is_new():
    item1 = _make_willitem_blank()
    item1.set_status("COMPLETE", True)
    item2 = _make_willitem_blank()  # VALID but not COMPLETE
    will = {"a": item1, "b": item2}
    assert Will.is_new(will) is True


def test_will_get_min_locktime():
    class FakeTx:
        def __init__(self, locktime):
            self.locktime = locktime

    class FakeItem:
        def __init__(self, locktime, valid=True):
            self.tx = FakeTx(locktime)
            self._valid = valid
        def get_status(self, s):
            return self._valid if s == "VALID" else False

    will = {
        "a": FakeItem(100),
        "b": FakeItem(200),
    }
    assert Will.get_min_locktime(will) == 100

    # empty will
    assert Will.get_min_locktime({}) is None
    assert Will.get_min_locktime({}, default_value=999) == 999


def test_will_utxos_strs():
    class FakeUtxo:
        def __init__(self, s):
            self._s = s
        def to_str(self): return self._s

    utxos = [FakeUtxo("a:0"), FakeUtxo("b:1")]
    strs = Will.utxos_strs(utxos)
    assert strs == ["a:0", "b:1"]
    assert Will.utxos_strs([]) == []


def test_will_get_tx_from_any():
    tx = Will.get_tx_from_any(_VALID_TX_HEX)
    assert tx is not None
    assert hasattr(tx, "txid")


def test_will_check_tx_height():
    class FakeWallet:
        class TxInfo:
            tx_mined_status = type("MS", (), {"height": lambda self: 100})()
        def get_tx_info(self, tx):
            return self.TxInfo()

    wallet = FakeWallet()
    assert Will.check_tx_height("fake_tx", wallet) == 100


# ------------------------------------------------------------------ #
# Exception classes
# ------------------------------------------------------------------ #

def test_exceptions():
    from bal.core.will import (
        WillException, WillExpiredException, NotCompleteWillException,
        HeirChangeException, TxFeesChangedException, HeirNotFoundException,
        WillexecutorChangeException, NoWillExecutorNotPresent,
        WillExecutorNotPresent, NoHeirsException,
        AmountException, PercAmountException, FixedAmountException,
        WillPostponedException,
    )

    assert issubclass(WillExpiredException, WillException)
    assert issubclass(NotCompleteWillException, WillException)
    assert issubclass(HeirChangeException, NotCompleteWillException)
    assert issubclass(TxFeesChangedException, NotCompleteWillException)
    assert issubclass(HeirNotFoundException, NotCompleteWillException)
    assert issubclass(WillexecutorChangeException, NotCompleteWillException)
    assert issubclass(NoWillExecutorNotPresent, NotCompleteWillException)
    assert issubclass(WillExecutorNotPresent, NotCompleteWillException)
    assert issubclass(NoHeirsException, WillException)
    assert issubclass(PercAmountException, AmountException)
    assert issubclass(FixedAmountException, AmountException)
    # WillPostponedException is a NotCompleteWillException but MUST be caught
    # before it in task_phase1, so it triggers an on-chain invalidation.
    assert issubclass(WillPostponedException, NotCompleteWillException)

    # WillException default message
    exc = WillException()
    assert str(exc) == "WillException"
    exc2 = WillException("custom")
    assert str(exc2) == "custom"

    # WillExpiredException
    exc3 = WillExpiredException()
    assert isinstance(exc3, WillException)


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print(f"[OK] All Will tests passed")
