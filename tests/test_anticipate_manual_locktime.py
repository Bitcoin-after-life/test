"""
Diagnostic tests for A3 - "Move date earlier (anticipate)" handled manually.

These tests describe what the core decision function
``Will.check_willexecutors_and_heirs`` does TODAY when the user manually sets a
SMALLER locktime for an heir (case "A" agreed with the owner):

  * Case A1: the new locktime is smaller than the frozen tx.locktime but STILL
    in the future (e.g. from "90 days" to "30 days"). Per the owner's decision
    (D2 = A1) this must lead to a plain REBUILD with the new locktime and must
    NEVER invalidate on-chain, even if the tx was already signed/sent.

  * Case A2: the new locktime is in the PAST relative to the check date. This is
    a genuinely expired will and is handled by ``check_will_expired`` ->
    WillExpiredException -> on-chain invalidation. This behaviour is correct and
    is kept (D3 only fixes the documentation for case A1).

These are permanent regression tests. The A3 analysis confirmed the core logic
is ALREADY correct: case A1 raises a rebuild signal (a NotCompleteWillException
subclass, in practice HeirNotFoundException) and never WillExpiredException, so
no on-chain invalidation happens for an anticipate to a future date. The A3 work
itself only fixed the documentation (the table wrongly claimed "anticipate ->
always invalidate"); these tests guard that the behaviour stays correct.

Run:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src python3 -m pytest \
        tests/test_anticipate_manual_locktime.py -q
"""

import sys
import os
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

import pytest  # noqa: E402

from bal.core.will import (  # noqa: E402
    WillItem,
    Will,
    NotCompleteWillException,
    WillExpiredException,
)

# A valid serialized tx (1 input + 1 output, version 2).
_VALID_TX_HEX = (
    "01000000012a5c9a94fcde98f5581cd00162c60a13936ceb75389ea65b"
    "f38633b424eb4031000000006c493046022100a82bbc57a0136751e543"
    "3f41cf000b3f1a99c6744775e76ec764fb78c54ee100022100f9e80b7d"
    "e89de861dc6fb0c1429d5da72c2b6b2ee2406bc9bfb1beedd729d98501"
    "2102e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae3"
    "5cdb84d2f6ffffffff0140420f00000000001976a914230ac37834073a"
    "42146f11ef8414ae929feaafc388ac00000000"
)

TX_FEES = 100


def _make_will_item(heirs, tx_locktime, status_complete=False):
    """Build a WillItem whose stored heirs == ``heirs`` and whose tx.locktime
    is forced to ``tx_locktime`` (the value frozen inside the signed tx).

    Args:
        heirs: The heirs dict stored in the will item.
        tx_locktime: The locktime to force into the (pretend) signed tx.
        status_complete: If True, mark the item as already signed (COMPLETE).

    Returns:
        A configured WillItem.
    """
    d = {
        "tx": _VALID_TX_HEX,
        "heirs": copy.deepcopy(heirs),
        "willexecutor": None,
        "status": "",
        "description": "",
        "time": 0,
        "change": "",
        "baltx_fees": TX_FEES,
    }
    item = WillItem(d, _id="willid_1")
    item.STATUS = copy.deepcopy(WillItem.STATUS_DEFAULT)
    item.tx.locktime = tx_locktime
    if status_complete:
        item.set_status("COMPLETE", True)
    return item


def _check(will_heirs, current_heirs, tx_locktime,
           status_complete=False, check_date=0):
    """Run check_willexecutors_and_heirs and return the raised exception type
    (or None if it returned coherent).

    Args:
        will_heirs: Heirs stored in the will item.
        current_heirs: The (possibly edited) current heirs dict.
        tx_locktime: The frozen tx.locktime.
        status_complete: Whether the will tx is already signed.
        check_date: The reference check date (timestamp).

    Returns:
        The exception class raised, or None if the will stayed coherent.
    """
    item = _make_will_item(will_heirs, tx_locktime, status_complete)
    will = {"willid_1": item}
    try:
        Will.check_willexecutors_and_heirs(
            will, current_heirs, {}, False, check_date, TX_FEES,
        )
        return None
    except Exception as e:  # noqa: BLE001 - we want the type for the diagnosis
        return type(e)


# A locktime far in the future (year ~2030) so it is never "in the past".
_FUTURE = 1900000000
# An even later future locktime (postpone target).
_LATER = 2000000000
# A smaller-but-still-future locktime (anticipate target, case A1).
_SMALLER_FUTURE = 1800000000


# --------------------------------------------------------------------------- #
# Case A1: smaller locktime, still in the future.
# Owner decision D2 = A1: must REBUILD with the new locktime, NEVER invalidate.
# --------------------------------------------------------------------------- #

def test_a1_anticipate_unsigned_triggers_rebuild_not_invalidate():
    """Anticipate (smaller, future locktime) on an UNSIGNED will must signal a
    rebuild (a NotCompleteWillException subclass) and must NOT raise
    WillExpiredException (which would invalidate on-chain)."""
    will_heirs = {"alice": ["addr_alice", 5000, str(_FUTURE)]}
    current_heirs = {"alice": ["addr_alice", 5000, str(_SMALLER_FUTURE)]}
    raised = _check(will_heirs, current_heirs, tx_locktime=_FUTURE,
                    status_complete=False, check_date=0)
    # Must NOT be an expiry/invalidation.
    assert raised is not WillExpiredException
    # Must be a rebuild signal (HeirChange / HeirNotFound, both subclasses of
    # NotCompleteWillException).
    assert raised is not None and issubclass(raised, NotCompleteWillException)


def test_a1_anticipate_signed_triggers_rebuild_not_invalidate():
    """Anticipate (smaller, future locktime) on a SIGNED will must STILL signal
    a rebuild and must NOT invalidate on-chain (owner decision D2 = A1)."""
    will_heirs = {"alice": ["addr_alice", 5000, str(_FUTURE)]}
    current_heirs = {"alice": ["addr_alice", 5000, str(_SMALLER_FUTURE)]}
    raised = _check(will_heirs, current_heirs, tx_locktime=_FUTURE,
                    status_complete=True, check_date=0)
    assert raised is not WillExpiredException
    assert raised is not None and issubclass(raised, NotCompleteWillException)


# --------------------------------------------------------------------------- #
# Case A2: smaller locktime that lands in the PAST -> genuine expiry.
# This is handled by check_will_expired (separate from check_willexecutors_and_heirs)
# and is intentionally NOT changed by A3.
# --------------------------------------------------------------------------- #

def test_a2_past_locktime_is_genuinely_expired():
    """A locktime in the PAST (relative to the check date) is a genuine expiry
    handled by check_will_expired -> WillExpiredException. This is kept."""
    item = _make_will_item(
        {"alice": ["addr_alice", 5000, str(1000)]}, tx_locktime=1000,
    )
    item.set_status("VALID", True)
    will = {"willid_1": item}
    all_inputs = Will.get_all_inputs(will, only_valid=True)
    min_lt = Will.get_all_inputs_min_locktime(all_inputs)
    # check_date well after the tx locktime -> expired.
    with pytest.raises(WillExpiredException):
        Will.check_will_expired(min_lt, timestamp_to_check=_FUTURE)


if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All A3 anticipate diagnostic tests passed")
