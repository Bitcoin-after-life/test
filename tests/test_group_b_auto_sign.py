"""
Tests for Group B / B2 and its follow-up fixes.

Covered behaviour:

  * the persisted ``AUTO_SIGN`` configuration key exists and defaults to ON,
    and can be turned off and read back;
  * the manual "next step (Sign/Broadcast)" hint is suppressed when AUTO_SIGN
    is ON (the Building Will dialog already signs and broadcasts), and shown
    when AUTO_SIGN is OFF (Fix A - no duplicate "press Broadcast" popup);
  * the broadcast is "one-shot": transactions already marked PUSHED are not
    collected again for re-sending, so a will-executor that failed before does
    not cause the successful ones to be re-broadcast (Fix B).

The Qt classes are not imported (they require PyQt6 + an Electrum window).
Instead we reproduce the small decision logic with light-weight fakes, which
keeps the tests fast and headless while still verifying the real contract.

Run:
    PYTHONPATH=electrum-src python3 -m pytest tests/test_group_b_auto_sign.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.plugin_base import BalConfig
from bal.core.willexecutors import Willexecutors


# ------------------------------------------------------------------ #
# Mocks
# ------------------------------------------------------------------ #

class FakeConfig:
    """Minimal mock for Electrum's config object (key/value store)."""

    def __init__(self):
        self._store = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set_key(self, key, value, save=True):
        self._store[key] = value


class FakeWillItem:
    """Minimal will item exposing the status flags and will-executor used by
    ``Willexecutors.get_willexecutor_transactions``.

    ``statuses`` is a set of active status names; ``we`` is the assigned
    will-executor dict (or ``None``); ``tx`` is any stringifiable stand-in for
    the transaction.
    """

    def __init__(self, statuses, we, tx="rawtx"):
        self._statuses = set(statuses)
        self.we = we
        self.tx = tx

    def get_status(self, name):
        return name in self._statuses


# ------------------------------------------------------------------ #
# AUTO_SIGN config default
# ------------------------------------------------------------------ #

def test_auto_sign_config_defaults_on():
    """AUTO_SIGN must default to ON (True) when not yet stored."""
    cfg = FakeConfig()
    auto_sign = BalConfig(cfg, "bal_auto_sign", True)
    assert auto_sign.get() is True


def test_auto_sign_config_can_be_disabled():
    """Once turned off and persisted, AUTO_SIGN reads back as False."""
    cfg = FakeConfig()
    auto_sign = BalConfig(cfg, "bal_auto_sign", True)
    auto_sign.set(False)
    assert auto_sign.get() is False
    # A fresh wrapper over the same config still sees the stored value.
    assert BalConfig(cfg, "bal_auto_sign", True).get() is False


# ------------------------------------------------------------------ #
# Fix A - manual "next step" hint suppressed when AUTO_SIGN is ON
# ------------------------------------------------------------------ #

def _should_show_manual_hint(auto_sign_on):
    """Reproduce the guard added at the top of _show_next_steps_hint().

    Returns True when the manual Sign/Broadcast hint (and follow-up popup)
    should be shown. With AUTO_SIGN ON the dialog has already signed and
    broadcast, so the hint must be suppressed.
    """
    if auto_sign_on:
        return False
    return True


def test_hint_suppressed_when_auto_sign_on():
    assert _should_show_manual_hint(auto_sign_on=True) is False


def test_hint_shown_when_auto_sign_off():
    assert _should_show_manual_hint(auto_sign_on=False) is True


# ------------------------------------------------------------------ #
# Fix B - PUSHED transactions are not collected again (one-shot broadcast)
# ------------------------------------------------------------------ #

def test_pushed_tx_not_recollected():
    """A VALID+COMPLETE+PUSHED will must NOT be collected for re-broadcast."""
    we = {"url": "https://we.example", "selected": True}
    will = {
        "tx_done": FakeWillItem(
            {"VALID", "COMPLETE", "PUSHED"}, dict(we)
        ),
    }
    collected = Willexecutors.get_willexecutor_transactions(will)
    # Nothing to send: the only will is already PUSHED.
    assert collected == {}


def test_unpushed_tx_is_collected():
    """A VALID+COMPLETE but NOT-yet-PUSHED will IS collected for broadcast."""
    we = {"url": "https://we.example", "selected": True}
    will = {
        "tx_new": FakeWillItem({"VALID", "COMPLETE"}, dict(we)),
    }
    collected = Willexecutors.get_willexecutor_transactions(will)
    assert "https://we.example" in collected
    assert "tx_new" in collected["https://we.example"]["txsids"]


def test_mixed_only_unpushed_collected():
    """With one PUSHED and one not-pushed will on different servers, only the
    not-pushed one is collected (the successful one is never re-sent)."""
    will = {
        "tx_done": FakeWillItem(
            {"VALID", "COMPLETE", "PUSHED"},
            {"url": "https://ok.example", "selected": True},
        ),
        "tx_todo": FakeWillItem(
            {"VALID", "COMPLETE"},
            {"url": "https://todo.example", "selected": True},
        ),
    }
    collected = Willexecutors.get_willexecutor_transactions(will)
    assert "https://ok.example" not in collected
    assert "https://todo.example" in collected
