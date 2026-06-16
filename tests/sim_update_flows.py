"""
Real-world simulation of the inheritance update flows.

This script does NOT touch the GUI.  It drives the core decision function
``Will.check_willexecutors_and_heirs`` (the one that decides whether a will is
still coherent or must be rebuilt) through the scenarios the user reported:

  1. delivery date moved forward (postpone)            -> must NOT stay "coherent"
  2. an heir is added                                   -> must trigger rebuild
  3. an heir is removed                                 -> must trigger rebuild
  4. a single heir percentage / amount is changed       -> must trigger rebuild
  5. nothing changed                                    -> stays coherent

For each scenario we report which exception (if any) is raised, because that is
exactly what the GUI relies on to decide whether to rebuild the inheritance
transactions.  If the function returns True (coherent) when something DID
change, the GUI will (correctly) show no update -- which is the symptom the
user described.

Run:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src python3 tests/sim_update_flows.py
"""

import sys
import os
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.will import (
    WillItem, Will,
    NotCompleteWillException, HeirNotFoundException, NoHeirsException,
    TxFeesChangedException, WillExpiredException,
)
from bal.core.util import Util

# A valid serialized tx (1 input + 1 output, version 2). Its nLockTime is 0.
_VALID_TX_HEX = (
    "01000000012a5c9a94fcde98f5581cd00162c60a13936ceb75389ea65b"
    "f38633b424eb4031000000006c493046022100a82bbc57a0136751e543"
    "3f41cf000b3f1a99c6744775e76ec764fb78c54ee100022100f9e80b7d"
    "e89de861dc6fb0c1429d5da72c2b6b2ee2406bc9bfb1beedd729d98501"
    "2102e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae3"
    "5cdb84d2f6ffffffff0140420f00000000001976a914230ac37834073a"
    "42146f11ef8414ae929feaafc388ac00000000"
)

# A locktime far in the past (so the frozen tx.locktime is a fixed integer we
# control via monkey-patching below).  We will override w.tx.locktime per test.
TX_FEES = 100


def _make_will_item(heirs, tx_locktime, status_complete=False):
    """Build a WillItem whose stored heirs == ``heirs`` and whose tx.locktime
    is forced to ``tx_locktime`` (the value frozen in the signed Bitcoin tx)."""
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
    # Force the locktime frozen "inside" the signed tx.
    item.tx.locktime = tx_locktime
    if status_complete:
        item.set_status("COMPLETE", True)
    return item


def _run(label, will_heirs, current_heirs, tx_locktime,
         status_complete=False, check_date=0):
    """Run check_willexecutors_and_heirs and report the outcome."""
    item = _make_will_item(will_heirs, tx_locktime, status_complete)
    will = {"willid_1": item}
    outcome = None
    try:
        result = Will.check_willexecutors_and_heirs(
            will,
            current_heirs,           # the (possibly edited) heirs dict
            {},                      # willexecutors
            False,                   # self_willexecutor
            check_date,              # check_date (timestamp)
            TX_FEES,                 # tx_fees
        )
        outcome = f"coherent (returned {result})"
    except HeirNotFoundException as e:
        outcome = f"HeirNotFoundException: {e}"
    except NoHeirsException as e:
        outcome = f"NoHeirsException: {e}"
    except TxFeesChangedException as e:
        outcome = f"TxFeesChangedException: {e}"
    except WillExpiredException as e:
        outcome = f"WillExpiredException: {e}"
    except NotCompleteWillException as e:
        outcome = f"{type(e).__name__}: {e}"
    except Exception as e:
        outcome = f"!! UNEXPECTED {type(e).__name__}: {e}"
    print(f"[{label}]")
    print(f"    -> {outcome}")
    return outcome


def main():
    # locktime string "0d" -> Util.parse_locktime_string returns a timestamp
    # ~ now.  We use explicit integer timestamps to keep things deterministic.
    base_lt = 1900000000          # frozen tx.locktime (year ~2030)
    later_lt = "2000000000"       # a later locktime string (postpone)
    same_lt = str(base_lt)

    # Scenario 0: nothing changed -> should be coherent.
    heirs = {"alice": ["addr_alice", 5000, same_lt]}
    _run("0. nothing changed",
         will_heirs=heirs, current_heirs=copy.deepcopy(heirs),
         tx_locktime=base_lt, check_date=0)

    # Scenario 1: delivery date moved forward (postpone), will NOT yet signed.
    heirs_will = {"alice": ["addr_alice", 5000, same_lt]}
    heirs_now = {"alice": ["addr_alice", 5000, later_lt]}
    _run("1. date postponed (unsigned will)",
         will_heirs=heirs_will, current_heirs=heirs_now,
         tx_locktime=base_lt, check_date=0)

    # Scenario 1b: postpone on a SIGNED will (status COMPLETE).
    _run("1b. date postponed (SIGNED will)",
         will_heirs=heirs_will, current_heirs=heirs_now,
         tx_locktime=base_lt, status_complete=True, check_date=0)

    # Scenario 2: an heir is ADDED.
    heirs_will = {"alice": ["addr_alice", 5000, same_lt]}
    heirs_now = {
        "alice": ["addr_alice", 5000, same_lt],
        "bob": ["addr_bob", 3000, same_lt],
    }
    _run("2. heir added (bob)",
         will_heirs=heirs_will, current_heirs=heirs_now,
         tx_locktime=base_lt, check_date=0)

    # Scenario 3: an heir is REMOVED.
    heirs_will = {
        "alice": ["addr_alice", 5000, same_lt],
        "bob": ["addr_bob", 3000, same_lt],
    }
    heirs_now = {"alice": ["addr_alice", 5000, same_lt]}
    _run("3. heir removed (bob)",
         will_heirs=heirs_will, current_heirs=heirs_now,
         tx_locktime=base_lt, check_date=0)

    # Scenario 4: a single heir AMOUNT/percentage changed.
    heirs_will = {"alice": ["addr_alice", 5000, same_lt]}
    heirs_now = {"alice": ["addr_alice", 9999, same_lt]}
    _run("4. heir amount changed (5000 -> 9999)",
         will_heirs=heirs_will, current_heirs=heirs_now,
         tx_locktime=base_lt, check_date=0)

    # Scenario 5: heir ADDRESS changed.
    heirs_will = {"alice": ["addr_alice", 5000, same_lt]}
    heirs_now = {"alice": ["addr_NEW", 5000, same_lt]}
    _run("5. heir address changed",
         will_heirs=heirs_will, current_heirs=heirs_now,
         tx_locktime=base_lt, check_date=0)

    print("\n[done] simulation finished")


if __name__ == "__main__":
    main()
