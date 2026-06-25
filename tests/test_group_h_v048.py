"""
Tests for the v0.4.8 changes (Group H).

These tests cover the small, GUI-free DECISION LOGIC introduced in v0.4.8,
without importing the Qt widgets (which need PyQt6 + an Electrum window). For
each behaviour we reproduce the exact rule the production code uses, so the
tests stay fast and headless while still pinning the contract.

Covered behaviour:

  * #7a - "executed inheritance" detection used to show a reassuring note on the
    "Checking your will" row when the wallet is empty because the inheritance was
    already executed (CONFIRMED) or is on its way (MEMPOOL). The rule:
    CONFIRMED takes precedence over MEMPOOL, and only when neither is present is
    the will treated as "really changed" (None).
  * #6 - the "at My Risk" confirmation gate for enabling ADVANCED mode. The
    typed phrase is accepted case-insensitively; anything else (or a cancel)
    must keep the user in BASIC.

Run:
    PYTHONPATH=electrum-src python3 -m pytest tests/test_group_h_v048.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))


# ------------------------------------------------------------------ #
# Mocks
# ------------------------------------------------------------------ #

class FakeWillItem:
    """Minimal will item exposing only ``get_status`` like the real WillItem."""

    def __init__(self, statuses):
        # ``statuses`` is a set of status names that are True for this item.
        self._statuses = set(statuses)

    def get_status(self, status):
        return status in self._statuses


def executed_inheritance_status(willitems):
    """GUI-free copy of ``BalDialog._executed_inheritance_status``.

    Mirrors the production rule exactly (see bal/gui/qt/dialogs.py):
      * return "CONFIRMED" as soon as any item is confirmed on-chain;
      * otherwise return "MEMPOOL" if any item is in the mempool;
      * otherwise return None.
    """
    has_mempool = False
    for witem in willitems.values():
        if witem.get_status("CONFIRMED"):
            return "CONFIRMED"
        if witem.get_status("MEMPOOL"):
            has_mempool = True
    return "MEMPOOL" if has_mempool else None


def advanced_phrase_ok(text, accepted):
    """GUI-free copy of the ADVANCED gate check (see on_user_type_change).

    Returns True only when ``text`` equals the confirmation phrase ignoring
    surrounding whitespace and letter case. ``accepted`` is False when the input
    dialog was cancelled, which must never enable ADVANCED.
    """
    if not accepted:
        return False
    return text.strip().lower() == "at my risk"


# ------------------------------------------------------------------ #
# #7a - executed-inheritance detection
# ------------------------------------------------------------------ #

def test_executed_status_confirmed_wins():
    """A confirmed transaction reports CONFIRMED even if a mempool one exists."""
    willitems = {
        "a": FakeWillItem({"MEMPOOL"}),
        "b": FakeWillItem({"CONFIRMED"}),
    }
    assert executed_inheritance_status(willitems) == "CONFIRMED"


def test_executed_status_mempool_only():
    """With only a mempool transaction the status is MEMPOOL."""
    willitems = {"a": FakeWillItem({"MEMPOOL"})}
    assert executed_inheritance_status(willitems) == "MEMPOOL"


def test_executed_status_none_when_neither():
    """No confirmed/mempool item -> None (the will really has to be rebuilt)."""
    willitems = {"a": FakeWillItem({"VALID"})}
    assert executed_inheritance_status(willitems) is None


def test_executed_status_empty():
    """No will items at all -> None."""
    assert executed_inheritance_status({}) is None


# ------------------------------------------------------------------ #
# #6 - "at My Risk" ADVANCED gate
# ------------------------------------------------------------------ #

def test_advanced_phrase_exact():
    """The exact phrase as shown in the prompt is accepted."""
    assert advanced_phrase_ok("at My Risk", True) is True


def test_advanced_phrase_case_insensitive():
    """Any capitalisation is accepted (case-insensitive)."""
    for variant in ("at my risk", "AT MY RISK", "At My Risk", "  at my risk  "):
        assert advanced_phrase_ok(variant, True) is True


def test_advanced_phrase_wrong_text():
    """A wrong phrase keeps the user in BASIC."""
    assert advanced_phrase_ok("at your risk", True) is False
    assert advanced_phrase_ok("", True) is False


def test_advanced_phrase_cancelled():
    """Cancelling the dialog (accepted=False) never enables ADVANCED."""
    assert advanced_phrase_ok("at My Risk", False) is False
