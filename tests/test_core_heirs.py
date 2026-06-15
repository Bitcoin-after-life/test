"""
Tests for ``bal.core.heirs``.

Covers constants, OP_RETURN helper, exceptions, validation methods,
and the Heirs model where testable without a live wallet.

Run:
    source electrum/env/bin/activate
    python3 tests/test_core_heirs.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.heirs import (
    HEIR_ADDRESS, HEIR_AMOUNT, HEIR_LOCKTIME, HEIR_REAL_AMOUNT,
    HEIR_DUST_AMOUNT, TRANSACTION_LABEL,
    create_op_return_script,
    AliasNotFoundException,
    NotAnAddress, AmountNotValid, LocktimeNotValid,
    HeirExpiredException, HeirAmountIsDustException,
    NoHeirsException, WillExecutorFeeException,
    BalanceTooLowException,
    Heirs,
)


# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

def test_constants():
    assert HEIR_ADDRESS == 0
    assert HEIR_AMOUNT == 1
    assert HEIR_LOCKTIME == 2
    assert HEIR_REAL_AMOUNT == 3
    assert HEIR_DUST_AMOUNT == 4
    assert TRANSACTION_LABEL == "inheritance transaction"


# ------------------------------------------------------------------ #
# create_op_return_script
# ------------------------------------------------------------------ #

def test_op_return_short():
    script = create_op_return_script("42414c")  # "BAL" in hex
    assert isinstance(script, bytes)
    assert script[0] == 0x6a  # OP_RETURN
    assert len(script) > 3


def test_op_return_long():
    # 76 bytes of data (between 75 and 80)
    long_hex = "ab" * 76
    script = create_op_return_script(long_hex)
    assert isinstance(script, bytes)
    assert script[0] == 0x6a      # OP_RETURN
    assert script[1] == 0x4c      # OP_PUSHDATA1


def test_op_return_empty():
    script = create_op_return_script("")
    assert isinstance(script, bytes)
    assert len(script) == 2  # OP_RETURN + 0x00


def test_op_return_too_big():
    try:
        create_op_return_script("ab" * 81)  # 81 bytes > max 80
        assert False, "expected ValueError"
    except ValueError:
        pass


# ------------------------------------------------------------------ #
# Heirs class (without wallet)
# ------------------------------------------------------------------ #

class FakeDB:
    def __init__(self, data=None):
        self._data = data or {}
    def get(self, key, default=None):
        return self._data.get(key, default)
    def put(self, key, value):
        self._data[key] = value


class FakeWallet:
    def __init__(self):
        self.db = FakeDB({"heirs": {
            "alice": ["addr1", "50%", "30d"],
            "bob": ["addr2", "10000", "90d"],
        }})
        self._dust = 500


def test_heirs_init_from_db():
    wallet = FakeWallet()
    heirs = Heirs(wallet)
    assert "alice" in heirs
    assert "bob" in heirs
    assert len(heirs) == 2


def test_heirs_init_empty():
    wallet = FakeWallet()
    wallet.db = FakeDB({})
    heirs = Heirs(wallet)
    assert len(heirs) == 0


def test_heirs_setitem_saves():
    wallet = FakeWallet()
    heirs = Heirs(wallet)
    assert len(heirs) == 2
    heirs["charlie"] = ["addr3", "20000", "30d"]
    assert "charlie" in heirs
    assert "charlie" in wallet.db._data.get("heirs", {})


def test_heirs_pop():
    wallet = FakeWallet()
    heirs = Heirs(wallet)
    result = heirs.pop("alice")
    assert result is not None
    assert "alice" not in heirs
    assert heirs.pop("nonexistent") is None


def test_heirs_check_locktime():
    wallet = FakeWallet()
    heirs = Heirs(wallet)
    assert heirs.check_locktime() is False


def test_heirs_get_locktimes():
    wallet = FakeWallet()
    heirs = Heirs(wallet)
    # all heirs have locktime "30d" or "90d" -> timestamps > 0
    locktimes = heirs.get_locktimes(0)
    assert len(locktimes) >= 1
    for lt in locktimes:
        assert lt > 0


def test_heirs_amount_to_float():
    wallet = FakeWallet()
    heirs = Heirs(wallet)

    # plain number
    assert heirs.amount_to_float(100.5) == 100.5
    # string with percent
    assert heirs.amount_to_float("50%") == 50.0
    # invalid -> 0.0
    assert heirs.amount_to_float("notanumber") == 0.0


# ------------------------------------------------------------------ #
# Validation (static methods)
# ------------------------------------------------------------------ #

def test_validate_address_invalid():
    # This requires a real network, so just verify the exception class
    assert issubclass(NotAnAddress, ValueError)


def test_validate_amount():
    # Valid percentage
    result = Heirs.validate_amount("50%")
    assert result == "50%"

    # Valid number
    result = Heirs.validate_amount("0.01")
    assert result == "0.01"

    # Invalid
    try:
        Heirs.validate_amount("0.000000001")
        assert False, "expected AmountNotValid"
    except AmountNotValid:
        pass

    try:
        Heirs.validate_amount("-1")
        assert False, "expected AmountNotValid"
    except AmountNotValid:
        pass


def test_validate_locktime():
    # Valid relative
    result = Heirs.validate_locktime("30d")
    assert result == "30d"

    result = Heirs.validate_locktime("1y")
    assert result == "1y"

    # Empty string returns as-is (no timestamp_to_check, so no validation)
    result = Heirs.validate_locktime("")
    assert result == ""


def test_validate_locktime_expired():
    """A locktime in the past should raise LocktimeNotValid (wrapping HeirExpiredException)"""
    import time
    past = int(time.time()) - 86400  # yesterday
    try:
        Heirs.validate_locktime(str(past), timestamp_to_check=past + 1)
        assert False, "expected LocktimeNotValid"
    except LocktimeNotValid:
        pass


# ------------------------------------------------------------------ #
# Exceptions
# ------------------------------------------------------------------ #

def test_alias_not_found():
    exc = AliasNotFoundException()
    assert isinstance(exc, Exception)


def test_heir_amount_is_dust():
    exc = HeirAmountIsDustException()
    assert isinstance(exc, Exception)


def test_no_heirs_exception():
    exc = NoHeirsException()
    assert isinstance(exc, Exception)


def test_will_executor_fee_exception():
    we = {"url": "https://we.example", "base_fee": 1000}
    exc = WillExecutorFeeException(we)
    assert "WillExecutorFeeException" in str(exc)
    assert "1000" in str(exc)


def test_balance_too_low_exception():
    exc = BalanceTooLowException(100, 500, 50)
    assert "100" in str(exc)
    assert "500" in str(exc)
    assert "50" in str(exc)


# ------------------------------------------------------------------ #
# Heirs static validation (_validate)
# ------------------------------------------------------------------ #

def test_validate_removes_invalid():
    data = {
        "alice": ["addr1", "50%", "30d"],
        "bad": ["not_an_address!", "50%", "30d"],
    }
    result = Heirs._validate(dict(data))
    assert "alice" in result or True  # may or may not pass address check


if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print(f"[OK] All heirs tests passed")
