"""
Focused regression/diagnostic test for the "anticipate near expiry" edge case.

Scenario reported by the plugin owner
-------------------------------------
When the user adds funds to the wallet, the plugin must rebuild the inheritance
transaction.  To make the new transaction supersede the old one, the plugin
anticipates the locktime (moves it EARLIER) by a fixed amount (1 day), so the
new tx confirms before the old one and the old one gets invalidated.

That logic is fine when the will is far from its locktime.  But if the will is
about to expire (e.g. locktime is only a few HOURS in the future), anticipating
by a full day pushes the new locktime INTO THE PAST.

This test verifies, against the real code, what value the anticipation logic
produces in that situation, and whether any guard prevents a past locktime.

It is a *diagnostic* test: it documents the current behaviour so we can decide
whether a fix is needed.  Run:

    QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src \
        python3 -m pytest tests/test_anticipate_past_locktime.py -q
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.util import Util, LOCKTIME_THRESHOLD


# ---------------------------------------------------------------------------
# 1. Pure-function level: Util.anticipate_locktime has no "now" lower bound.
# ---------------------------------------------------------------------------
def test_anticipate_locktime_can_fall_into_the_past():
    """A timestamp locktime only 10 hours away, anticipated by 1 day, lands
    ~14 hours in the PAST.  The only clamp in anticipate_locktime is `out < 1`,
    so a past-but-positive timestamp is returned unchanged."""
    now = int(time.time())
    locktime_in_10h = now + 10 * 3600  # expires in 10 hours
    assert locktime_in_10h > LOCKTIME_THRESHOLD  # it is a timestamp locktime

    anticipated = int(Util.anticipate_locktime(locktime_in_10h, days=1))

    # The anticipated locktime is earlier than the original (as intended)...
    assert anticipated < locktime_in_10h
    # ...but it is now in the PAST relative to "now":
    assert anticipated < now, (
        f"anticipated={anticipated} is not in the past relative to now={now}; "
        "the edge case may have been fixed"
    )
    # And crucially it is NOT clamped to anything sensible like `now`; it is
    # exactly original - 86400.
    assert anticipated == locktime_in_10h - 86400


def test_anticipate_locktime_far_from_expiry_stays_in_future():
    """Control case: when the will is far from expiry (e.g. 30 days away),
    anticipating by 1 day keeps the locktime safely in the future."""
    now = int(time.time())
    locktime_in_30d = now + 30 * 86400
    anticipated = int(Util.anticipate_locktime(locktime_in_30d, days=1))
    assert anticipated < locktime_in_30d
    assert anticipated > now  # still in the future -> safe


# ---------------------------------------------------------------------------
# 2. chk_locktime confirms the produced value is considered "expired".
# ---------------------------------------------------------------------------
def test_past_anticipated_locktime_is_seen_as_expired():
    """The anticipated past locktime, when fed to chk_locktime against the
    current time, is reported as NOT in the future (i.e. already expired)."""
    now = int(time.time())
    locktime_in_10h = now + 10 * 3600
    anticipated = int(Util.anticipate_locktime(locktime_in_10h, days=1))

    # chk_locktime signature is now (timestamp_to_check, locktime) (A1):
    # it returns True only if the locktime is still in the future.
    in_future = Util.chk_locktime(now, anticipated)
    assert in_future is False, (
        "the anticipated locktime is unexpectedly still in the future"
    )


# ---------------------------------------------------------------------------
# 3. Boundary scan: at what original distance does anticipation start to
#    produce a past locktime?  Documents the 24h threshold explicitly.
# ---------------------------------------------------------------------------
def test_boundary_is_exactly_24h():
    now = int(time.time())
    # Just under 24h away -> anticipated into the past.
    just_under = now + 24 * 3600 - 60
    a1 = int(Util.anticipate_locktime(just_under, days=1))
    assert a1 < now

    # Just over 24h away -> anticipated value stays (barely) in the future.
    just_over = now + 24 * 3600 + 60
    a2 = int(Util.anticipate_locktime(just_over, days=1))
    assert a2 > now


if __name__ == "__main__":
    test_anticipate_locktime_can_fall_into_the_past()
    test_anticipate_locktime_far_from_expiry_stays_in_future()
    test_past_anticipated_locktime_is_seen_as_expired()
    test_boundary_is_exactly_24h()

    # Human-readable demonstration
    now = int(time.time())
    for hours in (10, 23, 25, 48, 24 * 30):
        lt = now + hours * 3600
        a = int(Util.anticipate_locktime(lt, days=1))
        delta_h = (a - now) / 3600.0
        verdict = "PAST  <-- problem" if a < now else "future (ok)"
        print(
            f"expires in {hours:>4}h -> anticipated locktime is "
            f"{delta_h:+.1f}h from now  [{verdict}]"
        )
    print("[OK] all anticipate-past-locktime diagnostics passed")
