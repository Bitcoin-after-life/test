"""
Group E - Mock tests built around a fake wallet named "giovanna7".

These tests exercise the four behaviour areas requested for Group E using a
single, self-contained fake wallet (``giovanna7``). No real Electrum wallet
file is needed: everything is driven by lightweight mocks/stubs, exactly like
the other ``test_group_*`` and ``test_core_*`` suites.

The four sections are:

* E1 - calendar / .ics:  reminder-offset distribution, separate-VEVENT shape,
  description escaping and temporary .ics file creation.
* E2 - inheritance / states:  WillItem status transitions and heir-change
  detection for giovanna7's inheritance.
* E3 - connectivity:  parallel pinging of giovanna7's will-executor servers
  (concurrency, per-server callback, write-back of results).
* E4 - will-executor:  selection flag and the filtering rule that decides which
  transactions are pushed to a will-executor.

Run:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src \
        python3 -m pytest tests/test_group_e_mock_giovanna7.py -q
"""

import copy
import os
import sys
import time

# Make the plugin package importable when run directly (tests/ is one level
# below the repo root that contains the ``bal`` package).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.will import WillItem, Will, HeirNotFoundException
from bal.core.heirs import Heirs
from bal.core.willexecutors import Willexecutors
from bal.gui.qt.calendar import BalCalendar
from bal.gui.qt.widgets import compute_reminder_offsets


# A valid serialized Bitcoin transaction hex (1 input + 1 P2PKH output,
# version 2).  Reused from test_core_will.py so WillItem can parse a real tx.
_VALID_TX_HEX = (
    "01000000012a5c9a94fcde98f5581cd00162c60a13936ceb75389ea65b"
    "f38633b424eb4031000000006c493046022100a82bbc57a0136751e543"
    "3f41cf000b3f1a99c6744775e76ec764fb78c54ee100022100f9e80b7d"
    "e89de861dc6fb0c1429d5da72c2b6b2ee2406bc9bfb1beedd729d98501"
    "2102e61d176da16edd1d258a200ad9759ef63adf8e14cd97f53227bae3"
    "5cdb84d2f6ffffffff0140420f00000000001976a914230ac37834073a"
    "42146f11ef8414ae929feaafc388ac00000000"
)


# ------------------------------------------------------------------ #
# The fake "giovanna7" wallet
# ------------------------------------------------------------------ #

class FakeDB:
    """Minimal stand-in for an Electrum wallet database (a dict with
    get/put), used so the Heirs model can read/write the "heirs" key."""

    def __init__(self, data=None):
        """Store the initial key/value mapping (empty by default)."""
        self._data = data or {}

    def get(self, key, default=None):
        """Return the stored value for ``key`` or ``default`` if missing."""
        return self._data.get(key, default)

    def put(self, key, value):
        """Store ``value`` under ``key``."""
        self._data[key] = value


class GiovannaWallet:
    """A fake wallet named "giovanna7".

    It mimics just enough of an Electrum wallet for the Group E tests:

    * ``str(wallet)`` returns the wallet name ("giovanna7"), which is what the
      plugin uses to build calendar UIDs and labels.
    * ``db`` is a :class:`FakeDB` pre-loaded with two heirs so the Heirs model
      can be constructed without a live wallet.
    """

    #: Wallet name, exposed via ``str(wallet)``.
    NAME = "giovanna7"

    def __init__(self, heirs=None):
        """Build the wallet with an optional custom heirs mapping.

        Args:
            heirs: optional ``{name: [address, amount, locktime]}`` mapping.
                Defaults to two heirs (alice, bob).
        """
        if heirs is None:
            heirs = {
                "alice": ["addr_alice", "50%", "30d"],
                "bob": ["addr_bob", "10000", "90d"],
            }
        self.db = FakeDB({"heirs": heirs})

    def __str__(self):
        """Return the wallet name so it can be used in labels/UIDs."""
        return self.NAME


def make_giovanna_wallet(heirs=None):
    """Factory returning a fresh "giovanna7" fake wallet for each test."""
    return GiovannaWallet(heirs=heirs)


def _make_willitem(**overrides):
    """Create a WillItem for giovanna7 from a minimal, valid dict.

    The status block is reset to the clean defaults so each test starts from a
    deterministic state (VALID=True, everything else False).
    """
    d = {
        "tx": _VALID_TX_HEX,
        "heirs": {"alice": ["addr_alice", 5000, "30d"]},
        "willexecutor": None,
        "status": "",
        "description": "",
        "time": 0,
        "change": "",
        "baltx_fees": 100,
    }
    d.update(overrides)
    item = WillItem(d)
    item.STATUS = copy.deepcopy(WillItem.STATUS_DEFAULT)
    return item


# ================================================================== #
# E1 - calendar / .ics
# ================================================================== #

def test_e1_giovanna_wallet_name():
    """The fake wallet identifies itself as "giovanna7" (used in .ics UIDs)."""
    wallet = make_giovanna_wallet()
    assert str(wallet) == "giovanna7"


def test_e1_reminder_offsets_long_period():
    """Over a 30-day period, 3 reminders are spread out and all fall before
    the deadline (offset >= 1 day)."""
    offsets = compute_reminder_offsets(30, 3)
    assert offsets == [30, 16, 1]
    assert all(o >= 1 for o in offsets)
    # Sorted descending: furthest-from-deadline reminder first.
    assert offsets == sorted(offsets, reverse=True)


def test_e1_reminder_offsets_capped_one_per_day():
    """If the period is shorter than the requested count, at most one reminder
    per day is produced (no duplicate same-day alarms)."""
    offsets = compute_reminder_offsets(2, 3)
    assert offsets == [2, 1]
    assert len(offsets) == len(set(offsets))


def test_e1_reminder_offsets_no_room():
    """A zero-day (or shorter) period yields no reminders at all."""
    assert compute_reminder_offsets(0, 3) == []


def test_e1_reminder_offsets_single():
    """A single reminder fires exactly one day before the deadline."""
    assert compute_reminder_offsets(10, 1) == [1]


def test_e1_build_separate_events_for_giovanna():
    """Build the SEPARATE reminder VEVENTs for giovanna7 the same way
    open_or_save_calendar does (one VEVENT per offset, each on its own date)
    and verify their shape.

    We replicate the pure part of WillSettingsWidget.open_or_save_calendar here
    so the test stays GUI-free (no Qt widget construction), while still
    asserting the exact iCalendar structure the plugin emits: N distinct events,
    unique UIDs, "(reminder N/total)" summaries, and the last event placed one
    day before the locktime.
    """
    from datetime import datetime, timedelta, timezone

    # 30-day period -> offsets [30, 16, 1] (the last one = 1 day before deadline).
    locktime = datetime(2026, 7, 23, 9, 0, 0, tzinfo=timezone.utc)
    offsets = compute_reminder_offsets(30, 3)
    total = len(offsets)
    wallet = "giovanna7"
    summary_base = f"BAL - Will execution of {wallet}"

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for idx, offset in enumerate(offsets, start=1):
        event_dt = BalCalendar.format_time(locktime - timedelta(days=offset))
        summary = BalCalendar.ical_escape(f"{summary_base} (reminder {idx}/{total})")
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:bal-{wallet}-{offset}d",
            f"DTSTART:{event_dt}",
            f"DTEND:{event_dt}",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")

    # One separate VEVENT per reminder offset (no VALARM blocks any more).
    assert lines.count("BEGIN:VEVENT") == len(offsets)
    assert lines.count("END:VEVENT") == len(offsets)
    assert "BEGIN:VALARM" not in lines
    # UIDs are unique per event so calendars do not merge them.
    uids = [ln for ln in lines if ln.startswith("UID:")]
    assert len(uids) == len(set(uids)) == len(offsets)
    # Summaries are numbered to tell the events apart.
    assert any("(reminder 1/3)" in ln for ln in lines)
    assert any("(reminder 3/3)" in ln for ln in lines)
    # The LAST event (offset 1) sits one day before the locktime.
    last_dt = BalCalendar.format_time(locktime - timedelta(days=1))
    assert f"DTSTART:{last_dt}" in lines


def test_e1_event_description_escaping():
    """Special iCalendar characters in giovanna7's event text are escaped so
    the .ics file stays valid."""
    raw = "Wallet giovanna7; heirs: alice, bob"
    escaped = BalCalendar.ical_escape(raw)
    assert "\\;" in escaped       # semicolon escaped
    assert "\\," in escaped       # comma escaped
    assert "giovanna7" in escaped


def test_e1_write_temp_ics_for_giovanna():
    """A minimal VCALENDAR for giovanna7 can be written to a real temp .ics
    file and read back byte-for-byte."""
    content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:bal-giovanna7\r\n"
        "SUMMARY:BAL will reminder\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    path = BalCalendar.write_temp_ics(content)
    try:
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == content.encode("utf-8")
    finally:
        os.unlink(path)


# ================================================================== #
# E2 - inheritance / states
# ================================================================== #

def test_e2_giovanna_heirs_loaded():
    """giovanna7's two default heirs are read from the wallet db."""
    wallet = make_giovanna_wallet()
    heirs = Heirs(wallet)
    assert "alice" in heirs
    assert "bob" in heirs
    assert len(heirs) == 2


def test_e2_giovanna_add_remove_heir():
    """Adding and removing an heir updates both the model and the wallet db."""
    wallet = make_giovanna_wallet()
    heirs = Heirs(wallet)

    heirs["charlie"] = ["addr_charlie", "20000", "30d"]
    assert "charlie" in heirs
    assert "charlie" in wallet.db.get("heirs", {})

    removed = heirs.pop("alice")
    assert removed is not None
    assert "alice" not in heirs


def test_e2_willitem_default_and_complete():
    """A fresh will-item for giovanna7 starts VALID-but-not-COMPLETE; marking
    it COMPLETE flips only that flag."""
    item = _make_willitem()
    assert item.get_status("VALID") is True
    assert item.get_status("COMPLETE") is False

    assert item.set_status("COMPLETE", True) is True
    assert item.get_status("COMPLETE") is True
    # Re-setting the same value is a no-op (returns None).
    assert item.set_status("COMPLETE", True) is None


def test_e2_invalidated_clears_valid():
    """Invalidating giovanna7's will clears its VALID flag."""
    item = _make_willitem()
    item.set_status("INVALIDATED", True)
    assert item.get_status("INVALIDATED") is True
    assert item.get_status("VALID") is False


def test_e2_pushed_clears_push_fail():
    """A successful push clears any previous PUSH_FAIL state."""
    item = _make_willitem()
    item.set_status("PUSH_FAIL", True)
    assert item.get_status("PUSH_FAIL") is True

    item.set_status("PUSHED", True)
    assert item.get_status("PUSHED") is True
    assert item.get_status("PUSH_FAIL") is False


def test_e2_only_valid_filters_invalidated():
    """Will.only_valid keeps only the still-valid items of giovanna7's will."""
    good = _make_willitem()
    bad = _make_willitem()
    bad.set_status("INVALIDATED", True)
    will = {"good": good, "bad": bad}

    valid = list(Will.only_valid(will))
    assert "good" in valid
    assert "bad" not in valid


def test_e2_heir_change_triggers_rebuild():
    """If giovanna7 removes an heir after signing, the mismatch between the
    frozen will and the current heirs must raise HeirNotFoundException so the
    inheritance is rebuilt."""
    lt = 1900000000
    will_heirs = {
        "alice": ["addr_alice", 5000, str(lt)],
        "bob": ["addr_bob", 3000, str(lt)],
    }
    current_heirs = {"alice": ["addr_alice", 5000, str(lt)]}  # bob removed

    item = WillItem(
        {
            "tx": _VALID_TX_HEX,
            "heirs": copy.deepcopy(will_heirs),
            "willexecutor": None,
            "status": "",
            "description": "",
            "time": 0,
            "change": "",
            "baltx_fees": 100,
        }
    )
    item.STATUS = copy.deepcopy(WillItem.STATUS_DEFAULT)
    item.tx.locktime = lt
    will = {"willid_1": item}

    raised = False
    try:
        Will.check_willexecutors_and_heirs(will, current_heirs, {}, False, 0, 100)
    except HeirNotFoundException:
        raised = True
    assert raised, "removing an heir must raise HeirNotFoundException"


# ================================================================== #
# E3 - connectivity
# ================================================================== #

# Each simulated will-executor server takes this long to "answer".
_SLOW = 0.3
# Number of simulated servers for giovanna7.
_N = 6


def test_e3_ping_servers_parallel():
    """giovanna7's will-executor servers are pinged concurrently.

    We stub ``get_info_task`` with a slow function: half the servers "fail".
    The test asserts that (a) total time is far below the sequential sum
    (proving concurrency), (b) the per-server ``on_each`` callback fires once
    with the correct ok flag, and (c) results are written back into the
    mapping.
    """

    def slow_get_info(url, we, **kwargs):
        """Stub: sleep, then mark the server ok/KO based on its url."""
        time.sleep(_SLOW)
        we["status"] = "KO" if "dead" in url else 200
        return we

    original = Willexecutors.get_info_task
    Willexecutors.get_info_task = staticmethod(slow_get_info)
    try:
        wes = {}
        for i in range(_N):
            kind = "dead" if i % 2 else "ok"
            wes[f"https://{kind}-{i}.giovanna7.example"] = {}

        seen = []

        def on_each(url, we, ok):
            """Record each server's url and ok flag as it answers."""
            seen.append((url, ok))

        start = time.time()
        Willexecutors.ping_servers_parallel(wes, on_each=on_each, max_workers=_N)
        elapsed = time.time() - start

        # Parallel must be far faster than running every server in sequence.
        sequential = _N * _SLOW
        assert elapsed < sequential * 0.6, (
            f"not parallel: {elapsed:.2f}s vs sequential {sequential:.2f}s"
        )

        # The callback fired once per server with the right ok flag.
        assert len(seen) == _N
        for url, ok in seen:
            assert ok == ("ok" in url), (url, ok)

        # Ping results were written back into giovanna7's server mapping.
        for url, we in wes.items():
            assert we["status"] == (200 if "ok" in url else "KO"), (url, we)
    finally:
        Willexecutors.get_info_task = original


def test_e3_ping_empty_mapping():
    """Pinging an empty server mapping is a safe no-op (returns the mapping)."""
    result = Willexecutors.ping_servers_parallel({})
    assert result == {}


# ================================================================== #
# E4 - will-executor
# ================================================================== #

def test_e4_is_selected_default_false():
    """A brand-new will-executor for giovanna7 is not selected by default, and
    is_selected initialises the flag to False."""
    we = {"url": "https://we.giovanna7.example"}
    assert Willexecutors.is_selected(we) is False
    assert we["selected"] is False


def test_e4_is_selected_set_value():
    """is_selected can both set and read the selection flag."""
    we = {"url": "https://we.giovanna7.example"}
    assert Willexecutors.is_selected(we, True) is True
    assert we["selected"] is True
    assert Willexecutors.is_selected(we) is True


def test_e4_get_transactions_only_valid_complete_selected():
    """Only a VALID + COMPLETE + not-yet-PUSHED will whose will-executor is
    *selected* contributes a transaction to be pushed.

    This is the core filtering rule of get_willexecutor_transactions, verified
    here against giovanna7's will.
    """
    url = "https://we.giovanna7.example"

    # 1) The good one: valid, complete, not pushed, selected -> included.
    good = _make_willitem()
    good.set_status("COMPLETE", True)
    good.we = {"url": url, "selected": True}

    # 2) Not complete -> excluded.
    not_complete = _make_willitem()
    not_complete.we = {"url": url, "selected": True}

    # 3) Complete but already pushed -> excluded (unless force).
    pushed = _make_willitem()
    pushed.set_status("COMPLETE", True)
    pushed.set_status("PUSHED", True)
    pushed.we = {"url": url, "selected": True}

    # 4) Complete, not pushed, but will-executor NOT selected -> excluded.
    not_selected = _make_willitem()
    not_selected.set_status("COMPLETE", True)
    not_selected.we = {"url": url, "selected": False}

    will = {
        "good": good,
        "not_complete": not_complete,
        "pushed": pushed,
        "not_selected": not_selected,
    }

    result = Willexecutors.get_willexecutor_transactions(will)

    # Exactly one server entry, carrying only the "good" will-item's tx id.
    assert url in result
    assert result[url]["txsids"] == ["good"]


def test_e4_get_transactions_force_includes_pushed():
    """With ``force=True``, an already-PUSHED will is re-included so giovanna7
    can re-broadcast it (the "Rebroadcast" button path)."""
    url = "https://we.giovanna7.example"

    pushed = _make_willitem()
    pushed.set_status("COMPLETE", True)
    pushed.set_status("PUSHED", True)
    pushed.we = {"url": url, "selected": True}

    will = {"pushed": pushed}

    result = Willexecutors.get_willexecutor_transactions(will, force=True)
    assert url in result
    assert result[url]["txsids"] == ["pushed"]


def test_e4_compute_id():
    """compute_id builds a stable identifier from url + chain."""
    we = {"url": "https://we.giovanna7.example", "chain": "bitcoin"}
    assert Willexecutors.compute_id(we) == "https://we.giovanna7.example-bitcoin"


# ------------------------------------------------------------------ #
# Main (allows running the file directly, like the other suites)
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    for name in sorted(dir()):
        if name.startswith("test_"):
            globals()[name]()
            print(f"  [OK] {name}")
    print("[OK] All Group E (giovanna7) tests passed")
