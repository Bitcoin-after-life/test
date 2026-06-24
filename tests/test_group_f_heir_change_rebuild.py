"""
Tests for Group F (heir-change full rebuild, "Option A").

Context (bugs E/F/K): when an heir was deleted/changed and the rebuilt
inheritance transaction happened to keep the SAME txid, ``Will.update_will``
used to REUSE the old (already signed/COMPLETE) WillItem, copying only the new
heirs onto it. The downstream ``have_to_sign`` check then saw the item as
COMPLETE and reported "Nothing to do", so the new will was never signed or
broadcast.

The fix reuses the old item ONLY when the real heirs are identical. These tests
pin the behaviour of the helper ``Will._same_heirs`` that drives that decision.

Run:
    source electrum/env/bin/activate
    python3 tests/test_group_f_heir_change_rebuild.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.will import Will


# Heir entry layout (see heirs.py): [0]=address, [1]=amount, [2]=locktime.
# Extra trailing fields (e.g. real/dust amount) must NOT affect equality.
def _heir(address, amount, locktime, *extra):
    return [address, amount, locktime, *extra]


def test_same_heirs_identical():
    """Identical real heirs -> True (old signed item may be reused)."""
    a = {"alice": _heir("bc1qalice", "50%", "2026-12-01")}
    b = {"alice": _heir("bc1qalice", "50%", "2026-12-01")}
    assert Will._same_heirs(a, b) is True


def test_same_heirs_ignores_extra_fields():
    """Derived/extra fields (real amount, dust flag) do not break equality."""
    a = {"alice": _heir("bc1qalice", "50%", "2026-12-01", 12345, "DUST")}
    b = {"alice": _heir("bc1qalice", "50%", "2026-12-01")}
    assert Will._same_heirs(a, b) is True


def test_same_heirs_deleted_heir():
    """Deleting one of two heirs -> changed -> False (must rebuild/re-sign)."""
    old = {
        "alice": _heir("bc1qalice", "50%", "2026-12-01"),
        "bob": _heir("bc1qbob", "50%", "2026-12-01"),
    }
    new = {
        # bob removed; alice is auto-scaled to 100% by the plugin.
        "alice": _heir("bc1qalice", "100%", "2026-12-01"),
    }
    assert Will._same_heirs(old, new) is False


def test_same_heirs_added_heir():
    """Adding a heir -> changed -> False."""
    old = {"alice": _heir("bc1qalice", "100%", "2026-12-01")}
    new = {
        "alice": _heir("bc1qalice", "50%", "2026-12-01"),
        "carol": _heir("bc1qcarol", "50%", "2026-12-01"),
    }
    assert Will._same_heirs(old, new) is False


def test_same_heirs_changed_amount():
    """Same heir name but different amount -> changed -> False."""
    old = {"alice": _heir("bc1qalice", "50%", "2026-12-01")}
    new = {"alice": _heir("bc1qalice", "70%", "2026-12-01")}
    assert Will._same_heirs(old, new) is False


def test_same_heirs_changed_address():
    """Same heir name but different destination address -> False."""
    old = {"alice": _heir("bc1qalice", "50%", "2026-12-01")}
    new = {"alice": _heir("bc1qOTHER", "50%", "2026-12-01")}
    assert Will._same_heirs(old, new) is False


def test_same_heirs_changed_locktime():
    """Same heir but different delivery locktime -> False."""
    old = {"alice": _heir("bc1qalice", "50%", "2026-12-01")}
    new = {"alice": _heir("bc1qalice", "50%", "2027-06-01")}
    assert Will._same_heirs(old, new) is False


def test_same_heirs_ignores_willexecutor_pseudo_heirs():
    """Reserved 'w!ll3x3c\"' pseudo-heirs are bookkeeping, not real heirs.

    A difference only in the pseudo-heir entries must NOT be reported as a heir
    change (the will-executor is refreshed separately in update_will).
    """
    old = {
        "alice": _heir("bc1qalice", "100%", "2026-12-01"),
        'w!ll3x3c"server1': _heir("bc1qwe1", "0", "0"),
    }
    new = {
        "alice": _heir("bc1qalice", "100%", "2026-12-01"),
        'w!ll3x3c"server2': _heir("bc1qwe2", "0", "0"),
    }
    assert Will._same_heirs(old, new) is True


def test_same_heirs_empty():
    """Two empty heir maps are equal; None is treated as empty."""
    assert Will._same_heirs({}, {}) is True
    assert Will._same_heirs(None, {}) is True
    assert Will._same_heirs(None, None) is True


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
