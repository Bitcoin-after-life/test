"""
Tests for wallet/db-dependent methods in ``bal.core.heirs``.

Uses mocking to simulate Electrum wallet, db, and bitcoin module.

Run:
    source electrum/env/bin/activate
    QT_QPA_PLATFORM=offscreen python3 tests/test_core_heirs_extra.py
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.heirs import (
    Heirs, create_op_return_script, reduce_outputs,
    HEIR_ADDRESS, HEIR_AMOUNT, HEIR_LOCKTIME, HEIR_REAL_AMOUNT,
)
from bal.core.willexecutors import Willexecutors


# ------------------------------------------------------------------ #
# Heirs db-dependent methods
# ------------------------------------------------------------------ #

def test_heirs_init_from_db():
    wallet = MagicMock()
    wallet.db.get        .return_value = {"alice": ["bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", 5000, "30d"]}
    h = Heirs(wallet)
    assert "alice" in h


def test_heirs_init_empty_db():
    wallet = MagicMock()
    wallet.db.get.return_value = {}
    h = Heirs(wallet)
    assert len(h) == 0


def test_heirs_save():
    wallet = MagicMock()
    wallet.db.get.return_value = {}
    h = Heirs(wallet)
    h["bob"] = ["bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", 3000, "60d"]
    wallet.db.put.assert_called()


def test_heirs_pop_saves():
    wallet = MagicMock()
    wallet.db.get.return_value = {"bob": ["bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", 3000, "60d"]}
    h = Heirs(wallet)
    h.pop("bob")
    wallet.db.put.assert_called()


# ------------------------------------------------------------------ #
# Heirs wallet-dependent methods
# ------------------------------------------------------------------ #

def test_heirs_normalize_perc():
    wallet = MagicMock()
    wallet.dust_threshold.return_value = 500
    heir_list = {"a": ["bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", "50%", "30d"]}
    h = Heirs.__new__(Heirs)
    h._Heirs__normal_perc = True
    h.update(heir_list)
    h.normalize_perc(heir_list, 100000, 100000, wallet)
    # "50%" of 100000 = 50000 → above dust threshold, value stays
    assert h["a"][HEIR_AMOUNT] == "50%"


def test_heirs_prepare_lists():
    wallet = MagicMock()
    wallet.dust_threshold.return_value = 500
    h = Heirs.__new__(Heirs)
    h.update({"a": ["bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", 5000, "30d"]})
    result, onlyfixed = h.prepare_lists(100000, 100, wallet)
    assert len(result) > 0
    assert isinstance(result, dict)


# ------------------------------------------------------------------ #
# ALL-DUST GUARD (prepare_lists) - owner request, v0.4.7
#
# The plugin must REFUSE to build an inheritance when EVERY heir's share is
# below the Bitcoin dust limit (HeirAmountIsDustException), but must keep
# building normally when at least one heir is valid - including the tricky
# case where the valid heir lives on a DIFFERENT locktime than the dust one.
# These three tests pin that behaviour down so it cannot silently regress.
# ------------------------------------------------------------------ #

def test_prepare_lists_all_dust_raises():
    """All heirs below the dust limit -> HeirAmountIsDustException.

    Reproduces the owner's log: a very small wallet balance split between
    percentage heirs gives each one a tiny share (like 214/316/3 sat), all
    below the dust threshold. prepare_lists must then REFUSE to build the
    "empty" inheritance and raise the exception.

    NOTE: we deliberately use *percentage* heirs with a *small* balance. With
    fixed amounts and a large balance the leftover funds are redistributed to
    the heirs (so they would no longer be dust) - that is a different, valid
    case and is covered by the other prepare_lists tests.
    """
    from bal.core.heirs import HeirAmountIsDustException

    wallet = MagicMock()
    wallet.dust_threshold.return_value = 500
    h = Heirs.__new__(Heirs)
    # Tiny balance (800 sat) split 40%/60% -> each share is far below 500.
    h.update({
        "a": ["bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", "40%", "30d"],
        "b": ["bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", "60%", "30d"],
    })
    raised = False
    try:
        h.prepare_lists(800, 100, wallet)
    except HeirAmountIsDustException:
        raised = True
    assert raised, "all-dust will must raise HeirAmountIsDustException"


def test_prepare_lists_mixed_dust_continues():
    """Some dust + at least one valid heir -> build continues normally.

    The guard must NOT fire here: one heir's share is dust (a 1% slice of a
    small balance), the other is a valid fixed amount, so the inheritance is
    still feasible (unchanged behaviour).
    """
    from bal.core.heirs import HeirAmountIsDustException

    wallet = MagicMock()
    wallet.dust_threshold.return_value = 500
    h = Heirs.__new__(Heirs)
    h.update({
        "ok":   ["bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", 5000, "30d"],
        "dust": ["bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", "1%", "30d"],
    })
    raised = False
    try:
        result, _onlyfixed = h.prepare_lists(5200, 100, wallet)
    except HeirAmountIsDustException:
        raised = True
    assert not raised, "a mix of dust + valid heirs must NOT be blocked"
    assert isinstance(result, dict) and len(result) > 0


def test_prepare_lists_multi_locktime_continues():
    """Dust heir and valid heir on DIFFERENT locktimes -> build continues.

    This pins down the false-positive fix: prepare_transactions only ever sees
    the lowest locktime, so the dust check MUST live in prepare_lists (which
    sees ALL locktimes). A dust heir at the earlier date must not block a valid
    heir at the later date.
    """
    from bal.core.heirs import HeirAmountIsDustException

    wallet = MagicMock()
    wallet.dust_threshold.return_value = 500
    h = Heirs.__new__(Heirs)
    h.update({
        "early_dust": ["bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", "1%", "30d"],
        "late_valid": ["bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", 5000, "60d"],
    })
    raised = False
    try:
        result, _onlyfixed = h.prepare_lists(5200, 100, wallet)
    except HeirAmountIsDustException:
        raised = True
    assert not raised, "valid heir on a later locktime must NOT be blocked"
    assert isinstance(result, dict) and len(result) > 0


# ------------------------------------------------------------------ #
# Heirs static methods (pure but use Electrum constants)
# ------------------------------------------------------------------ #

def test_validate_address_valid():
    with patch("bal.core.heirs.bitcoin.is_address", return_value=True):
        result = Heirs.validate_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        assert result == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"


def test_validate_address_invalid():
    with patch("bal.core.heirs.bitcoin.is_address", return_value=False):
        from bal.core.heirs import NotAnAddress
        try:
            Heirs.validate_address("bad")
            assert False, "should have raised"
        except NotAnAddress:
            pass


# ------------------------------------------------------------------ #
# create_op_return_script (pure)
# ------------------------------------------------------------------ #

def test_create_op_return_script():
    data = "42414c"  # "BAL" in hex
    script = create_op_return_script(data)
    assert script.startswith(b"\x6a")


# ------------------------------------------------------------------ #
# reduce_outputs (pure)
# ------------------------------------------------------------------ #

def test_reduce_outputs_noop():
    outputs = [("bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", 1000), ("bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", 2000)]
    reduce_outputs(5000, 5000, 100, outputs)  # no crash, no modification


def test_reduce_outputs_reduces():
    class FakeOut:
        def __init__(self, v):
            self.value = v
    outputs = [FakeOut(1000), FakeOut(2000)]
    reduce_outputs(100, 5000, 10, outputs)
    assert outputs[0].value < 1000


# ------------------------------------------------------------------ #
# Willexecutors (pure / light mocking)
# ------------------------------------------------------------------ #

def test_willexecutors_compute_id():
    wid = Willexecutors.compute_id({"url": "example.com", "chain": "mainnet"})
    assert isinstance(wid, str)
    assert "example.com" in wid


def test_willexecutors_is_selected():
    assert Willexecutors.is_selected({}) is False
    data = {"url": "x"}
    assert Willexecutors.is_selected(data) is False
    assert Willexecutors.is_selected(data, True) is True
    assert data.get("selected") is True


def test_willexecutors_get_we_url_from_response():
    class FakeResp:
        url = "http://example.com/willexecutor"
    result = Willexecutors.get_we_url_from_response(FakeResp())
    # With 4 path segments, result is first 2 segments joined
    assert result == "http:/"
    # More realistic: a deeper URL returns the host part
    class FakeResp2:
        url = "http://example.com/api/v1/endpoint"
    result2 = Willexecutors.get_we_url_from_response(FakeResp2())
    assert "example.com" in result2


def test_willexecutors_initialize_willexecutor():
    we = {}
    Willexecutors.initialize_willexecutor(we, "http://example.com")
    assert len(we) > 0


def test_willexecutors_get_willexecutor_transactions_empty():
    assert Willexecutors.get_willexecutor_transactions({}) == {}


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All heirs/willexecutors extra tests passed")
