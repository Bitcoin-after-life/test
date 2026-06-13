"""
Regression test for the Windows year-2038 OverflowError crash.

Background
----------
On Windows ``time_t`` is 32-bit, so ``datetime.fromtimestamp(ts)`` raises
``OverflowError: Python int too large to convert to C int`` for any timestamp
past 2038 (e.g. ``NLOCKTIME_MAX = 2**32 - 1``, used as the default/sentinel
locktime).  On 64-bit Linux the same call succeeds, which is why the bug only
showed up on the user's Windows build: ``BalWindow.__init__`` ->
``create_heirs_tab`` -> ``WillSettingsWidget`` -> ``on_locktime_change`` ->
``BalTimestamp.to_date`` -> ``datetime.fromtimestamp(NLOCKTIME_MAX)`` crashed,
which aborted ``init_menubar`` / ``load_wallet`` and left the Will/Heirs tabs
and the menu entry half-built (the garbled/condensed element under the logo).

This test forces ``datetime.fromtimestamp`` to behave like the Windows 32-bit
implementation, then exercises ``BalTimestamp`` with NLOCKTIME_MAX to prove the
overflow-safe conversion no longer raises and clamps to INT32_MAX.

Run with:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
        python3 tests/windows_overflow_test.py <PLUGIN_IMPORT_NAME>
"""
import datetime as _datetime_mod
import importlib
import sys

PKG = sys.argv[1] if len(sys.argv) > 1 else "electrum.plugins.bal"

INT32_MAX = 2 ** 31 - 1
NLOCKTIME_MAX = 2 ** 32 - 1  # 4294967295, the value seen in the crash log

_real_datetime = _datetime_mod.datetime


class _WindowsLikeDatetime(_real_datetime):
    """A datetime subclass whose fromtimestamp emulates Windows' 32-bit limit."""

    @classmethod
    def fromtimestamp(cls, ts, tz=None):
        if tz is None and (ts > INT32_MAX or ts < 0):
            raise OverflowError("Python int too large to convert to C int")
        return _real_datetime.fromtimestamp(ts, tz)


def main():
    plugin_base = importlib.import_module(f"{PKG}.core.plugin_base")
    BalTimestamp = plugin_base.BalTimestamp

    # 1) Sanity: with the real (Linux 64-bit) datetime, large ts works already.
    bt = BalTimestamp(NLOCKTIME_MAX)
    d = bt.to_date()
    assert isinstance(d, _real_datetime), d
    print("[OK] BalTimestamp(NLOCKTIME_MAX).to_date() works on this platform")

    # 2) Now emulate Windows: patch datetime in the plugin_base module so that
    #    fromtimestamp raises OverflowError past 2038, exactly like Windows.
    original = plugin_base.datetime
    plugin_base.datetime = _WindowsLikeDatetime
    try:
        # 2a) Absolute sentinel timestamp (the exact crash path from the log).
        bt = BalTimestamp(NLOCKTIME_MAX)
        d = bt.to_date()  # must NOT raise OverflowError anymore
        assert d.year <= 2038, f"expected clamp to <=2038, got {d!r}"
        print("[OK] to_date(NLOCKTIME_MAX) no longer raises (clamped to INT32_MAX)")

        # 2b) to_timestamp must also be safe.
        ts = bt.to_timestamp()
        assert ts <= INT32_MAX, ts
        print("[OK] to_timestamp(NLOCKTIME_MAX) clamped & safe")

        # 2c) __str__ / __repr__ must not raise either.
        _ = str(bt)
        _ = repr(bt)
        print("[OK] str()/repr() on out-of-range timestamp are safe")

        # 2d) Relative durations that overflow when added (e.g. huge 'd').
        bt_rel = BalTimestamp(f"{10 ** 9}d")  # ~2.7M years -> overflow
        d2 = bt_rel.to_date()
        assert d2 is not None
        print("[OK] huge relative duration no longer raises")

        # 2e) Normal values are unchanged (behaviour-preserving check).
        bt_norm = BalTimestamp("90d")
        d3 = bt_norm.to_date()
        # 90 days from now, normalised to midnight
        assert d3.hour == 0 and d3.minute == 0 and d3.second == 0
        print("[OK] normal '90d' value still resolves to a midnight datetime")
    finally:
        plugin_base.datetime = original

    print(f"\n[OK] Windows overflow regression passed for package {PKG!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
