"""
Comprehensive tests for ``bal.core.plugin_base``.

Covers BalTimestamp, BalConfig, and BalPlugin static helpers.

Run:
    source electrum/env/bin/activate
    python3 tests/test_core_plugin_base.py
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from datetime import datetime, date, timedelta
from bal.core.plugin_base import BalTimestamp, BalPlugin, BalConfig


# ------------------------------------------------------------------ #
# BalTimestamp
# ------------------------------------------------------------------ #

def test_bt_create_and_str():
    bt = BalTimestamp("30d")
    assert bt.unit == "d"
    assert bt.value == 30

    bt2 = BalTimestamp("1y")
    assert bt2.unit == "y"
    assert bt2.value == 1

    bt3 = BalTimestamp(1700000000)
    assert bt3.unit is None
    assert bt3.value == 1700000000

    bt4 = BalTimestamp("garbage")
    # fallback: value=1, unit=None
    assert bt4.value == 1
    assert bt4.unit is None

    bt5 = BalTimestamp(0)
    assert bt5.unit is None
    assert bt5.value == 0

    bt6 = BalTimestamp("7d")
    assert str(bt6) == "7d"

    bt7 = BalTimestamp("2y")
    assert str(bt7) == "2y"

    # absolute timestamp str -> ISO format
    bt8 = BalTimestamp(1700000000)
    s = str(bt8)
    assert "202" in s or "197" in s  # year present


def test_bt_duration_to_days():
    assert BalTimestamp("30d").duration_to_days() == 30
    assert BalTimestamp("1y").duration_to_days() == 365
    assert BalTimestamp("0d").duration_to_days() == 0
    assert BalTimestamp(1700000000).duration_to_days() == 1700000000  # unit None -> raw value


def test_bt_to_date_absolute():
    bt = BalTimestamp(1700000000)
    d = bt.to_date()
    assert isinstance(d, datetime)

    # absolute with from_date (should be ignored for absolute)
    d2 = bt.to_date(from_date=datetime(2020, 1, 1))
    assert d == d2


def test_bt_to_date_relative():
    now = datetime.now()

    # relative days from now
    bt = BalTimestamp("7d")
    d = bt.to_date()
    assert d.hour == 0 and d.minute == 0  # normalized to midnight
    assert d > now

    # reverse (subtract days)
    d_rev = bt.to_date(reverse=True)
    assert d_rev < now

    # from explicit datetime
    base = datetime(2025, 6, 1, 12, 0, 0)
    d = bt.to_date(from_date=base)
    expected = (base + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    assert d == expected

    # from int timestamp
    ts = int(base.timestamp())
    d = bt.to_date(from_date=ts)
    assert d == expected


def test_bt_to_date_years():
    bt = BalTimestamp("1y")
    d = bt.to_date()
    assert d > datetime.now()


def test_bt_to_date_overflow():
    """Huge relative durations should not crash (clamp to INT32_MAX)."""
    bt = BalTimestamp("999999999d")
    d = bt.to_date()
    # should not raise
    assert d is not None
    assert isinstance(d, datetime)


def test_bt_to_timestamp():
    bt = BalTimestamp("7d")
    ts = bt.to_timestamp()
    assert ts > time.time()
    assert isinstance(ts, float)

    bt2 = BalTimestamp(1700000000)
    assert abs(bt2.to_timestamp() - 1700000000) < 86400  # close to original


def test_bt_repr():
    assert repr(BalTimestamp("7d")) == "7d"
    r = repr(BalTimestamp(1700000000))
    assert isinstance(r, str)
    assert len(r) > 0


def test_bt_edge_values():
    # zero timestamp
    bt0 = BalTimestamp(0)
    d = bt0.to_date()
    assert d is not None

    # negative? (may depend on platform)
    try:
        bt_neg = BalTimestamp(-1)
        _ = bt_neg.to_date()
    except (OSError, ValueError, OverflowError):
        pass  # acceptable on some platforms


# ------------------------------------------------------------------ #
# BalTimestamp._safe_fromtimestamp
# ------------------------------------------------------------------ #

def test_safe_fromtimestamp_normal():
    d = BalTimestamp._safe_fromtimestamp(1700000000)
    assert isinstance(d, datetime)


def test_safe_fromtimestamp_nlocktime_max():
    """NLOCKTIME_MAX (2**32-1) must not raise even on 32-bit platforms."""
    d = BalTimestamp._safe_fromtimestamp(2**32 - 1)
    assert d is not None


def test_safe_fromtimestamp_negative():
    """Negative timestamps should not crash."""
    d = BalTimestamp._safe_fromtimestamp(-1)
    assert isinstance(d, datetime)


# ------------------------------------------------------------------ #
# BalConfig
# ------------------------------------------------------------------ #

class FakeConfig:
    """Minimal mock for Electrum config."""
    def __init__(self):
        self._store = {}
    def get(self, key, default=None):
        return self._store.get(key, default)
    def set_key(self, key, value, save=True):
        self._store[key] = value


def test_balconfig_default():
    cfg = FakeConfig()
    bc = BalConfig(cfg, "test_key", "default_val")
    assert bc.get() == "default_val"
    assert bc.get("override") == "override"
    assert bc.get(None) == "default_val"


def test_balconfig_set():
    cfg = FakeConfig()
    bc = BalConfig(cfg, "test_key", "default_val")
    bc.set("stored_val")
    assert cfg.get("test_key") == "stored_val"
    assert bc.get() == "stored_val"


# ------------------------------------------------------------------ #
# BalPlugin
# ------------------------------------------------------------------ #

def test_default_will_settings_relative():
    rel = BalPlugin.default_will_settings_relative()
    assert rel["threshold"] == "30d"
    assert rel["locktime"] == "1y"


def test_default_will_settings():
    settings = BalPlugin.default_will_settings()
    assert settings["baltx_fees"] == 100
    assert "threshold" in settings
    assert "locktime" in settings
    # threshold/locktime should be absolute timestamps
    assert isinstance(settings["threshold"], float)
    assert isinstance(settings["locktime"], float)


def test_default_will_settings_absolute():
    abs_ = BalPlugin.default_will_settings_absolute()
    assert "threshold" in abs_
    assert "locktime" in abs_
    # should be timestamps (in the future)
    today = datetime.combine(date.today(), datetime.min.time())
    assert abs_["threshold"] >= today.timestamp()
    assert abs_["locktime"] >= today.timestamp()


def test_validate_will_settings():
    # Note: passing None triggers `will_settings = []` which then fails
    # on .get(). This is a latent bug — test passing a dict directly
    result = BalPlugin.validate_will_settings(None, {"baltx_fees": 0})
    assert result["baltx_fees"] == 100

    # normal settings unchanged
    input_settings = {"baltx_fees": 50, "threshold": 1700000000, "locktime": 1800000000}
    result = BalPlugin.validate_will_settings(None, input_settings)
    assert result["baltx_fees"] == 50
    assert result["threshold"] == 1700000000


if __name__ == "__main__":
    test_bt_create_and_str()
    test_bt_duration_to_days()
    test_bt_to_date_absolute()
    test_bt_to_date_relative()
    test_bt_to_date_years()
    test_bt_to_date_overflow()
    test_bt_to_timestamp()
    test_bt_repr()
    test_bt_edge_values()
    test_safe_fromtimestamp_normal()
    test_safe_fromtimestamp_nlocktime_max()
    test_safe_fromtimestamp_negative()
    test_balconfig_default()
    test_balconfig_set()
    test_default_will_settings_relative()
    test_default_will_settings()
    test_default_will_settings_absolute()
    test_validate_will_settings()
    print(f"[OK] All {sum(1 for k in dir() if k.startswith('test_'))} plugin_base tests passed")
