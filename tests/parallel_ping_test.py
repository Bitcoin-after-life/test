"""
Regression / behaviour test for the parallel will-executor networking.

Before this change, pinging / pushing to will-executor servers was done in a
sequential loop where every unreachable server blocked the whole batch for the
full timeout (plus up to 10 retries with 3s sleeps).  With N servers the total
wall-clock time was the *sum* of every server's time, so a couple of dead
servers froze the GUI ("Non risponde") for minutes.

This test patches Willexecutors.get_info_task / push_transactions_to_willexecutor
with slow stubs and asserts that:
  * ping_servers_parallel contacts servers concurrently (total time ~= the
    slowest server, NOT the sum), and
  * the on_each callback is invoked once per server with the right ok flag,
  * push_transactions_parallel behaves the same way.

Run with:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
        python3 tests/parallel_ping_test.py <PLUGIN_IMPORT_NAME>
"""
import importlib
import sys
import threading
import time

PKG = sys.argv[1] if len(sys.argv) > 1 else "electrum.plugins.bal"

SLOW = 0.5  # seconds each simulated server takes to answer
N = 8       # number of servers


def main():
    we_mod = importlib.import_module(f"{PKG}.core.willexecutors")
    W = we_mod.Willexecutors

    # ---- 1) ping_servers_parallel: time ~= slowest, not sum ----
    def slow_get_info(url, we, **kwargs):
        time.sleep(SLOW)
        # half the servers "fail"
        if "dead" in url:
            we["status"] = "KO"
        else:
            we["status"] = 200
        return we

    orig_get_info = W.get_info_task
    W.get_info_task = staticmethod(slow_get_info)
    try:
        wes = {}
        for i in range(N):
            kind = "dead" if i % 2 else "ok"
            wes[f"https://{kind}-{i}.example"] = {}

        seen = []

        def on_each(url, we, ok):
            seen.append((url, ok))

        start = time.time()
        W.ping_servers_parallel(wes, on_each=on_each, max_workers=N)
        elapsed = time.time() - start

        # Sequential would take ~ N * SLOW.  Parallel must be far less.
        sequential = N * SLOW
        assert elapsed < sequential * 0.6, (
            f"not parallel: {elapsed:.2f}s vs sequential {sequential:.2f}s")
        print(f"[OK] ping parallel: {elapsed:.2f}s for {N} servers "
              f"(sequential would be ~{sequential:.2f}s)")

        # callback fired once per server, with correct ok flags
        assert len(seen) == N, seen
        for url, ok in seen:
            assert ok == ("ok" in url), (url, ok)
        print("[OK] on_each fired once per server with correct ok flag")

        # results written back into the mapping
        for url, we in wes.items():
            if "ok" in url:
                assert we["status"] == 200, (url, we)
            else:
                assert we["status"] == "KO", (url, we)
        print("[OK] ping results written back into the willexecutors mapping")
    finally:
        W.get_info_task = orig_get_info

    # ---- 2) push_transactions_parallel: time ~= slowest, not sum ----
    def slow_push(we, **kwargs):
        time.sleep(SLOW)
        return "fail" not in we["url"]

    orig_push = W.push_transactions_to_willexecutor
    W.push_transactions_to_willexecutor = staticmethod(slow_push)
    try:
        wes = {}
        for i in range(N):
            kind = "fail" if i % 2 else "good"
            wes[f"https://{kind}-{i}.example"] = {
                "url": f"https://{kind}-{i}.example",
                "txs": "deadbeef",
                "txsids": [f"id{i}"],
            }

        pushed = []

        def on_each_push(url, we, ok, exc):
            pushed.append((url, ok))

        start = time.time()
        results = W.push_transactions_parallel(wes, on_each=on_each_push,
                                               max_workers=N)
        elapsed = time.time() - start

        sequential = N * SLOW
        assert elapsed < sequential * 0.6, (
            f"push not parallel: {elapsed:.2f}s vs {sequential:.2f}s")
        print(f"[OK] push parallel: {elapsed:.2f}s for {N} servers "
              f"(sequential would be ~{sequential:.2f}s)")

        assert len(results) == N, results
        for url, (ok, exc) in results.items():
            assert ok == ("good" in url), (url, ok)
        print("[OK] push results correct for every server")
    finally:
        W.push_transactions_to_willexecutor = orig_push

    # ---- 2b) global deadline: a hung server must not block past `deadline` ----
    def hanging_push(we, **kwargs):
        # Simulate a server that never answers within the test window.
        time.sleep(10)
        return True

    orig_push2 = W.push_transactions_to_willexecutor
    W.push_transactions_to_willexecutor = staticmethod(hanging_push)
    try:
        wes = {
            "https://fast.example": {
                "url": "https://fast.example", "txs": "x", "txsids": ["a"],
            },
            "https://hang.example": {
                "url": "https://hang.example", "txs": "y", "txsids": ["b"],
            },
        }
        # fast one answers quickly, hang one never does within the deadline
        def fast_or_hang(we, **kwargs):
            if "fast" in we["url"]:
                return True
            time.sleep(10)
            return True
        W.push_transactions_to_willexecutor = staticmethod(fast_or_hang)

        timed_out = []

        def on_timeout(url, we):
            timed_out.append(url)

        start = time.time()
        W.push_transactions_parallel(
            wes, max_workers=2, deadline=1.0, on_timeout=on_timeout
        )
        elapsed = time.time() - start
        assert elapsed < 3.0, f"deadline not enforced: waited {elapsed:.1f}s"
        assert "https://hang.example" in timed_out, timed_out
        print(f"[OK] global deadline enforced: returned in {elapsed:.1f}s, "
              f"hung server reported via on_timeout")
    finally:
        W.push_transactions_to_willexecutor = orig_push2

    # ---- 2c) on_tick is fired periodically from the CALLING thread ----
    # The elapsed-time counter is driven by an on_tick callback called from the
    # thread that invokes push_transactions_parallel (the same thread that drives
    # on_each), so its pyqtSignal repaints reliably.  Assert the callback runs
    # roughly once per tick_interval while the push is in flight, and that it
    # runs on the calling thread (not on a worker/heartbeat thread).
    def slow_push2(we, **kwargs):
        time.sleep(SLOW * 6)  # ~3s, long enough for several ticks
        return True

    orig_push3 = W.push_transactions_to_willexecutor
    W.push_transactions_to_willexecutor = staticmethod(slow_push2)
    try:
        wes = {
            "https://tick.example": {
                "url": "https://tick.example", "txs": "x", "txsids": ["a"],
            },
        }
        ticks = []
        caller_thread = threading.current_thread()
        tick_threads = set()

        def on_tick():
            ticks.append(time.time())
            tick_threads.add(threading.current_thread())

        W.push_transactions_parallel(
            wes, max_workers=1, on_tick=on_tick, tick_interval=0.5
        )
        # ~3s push with 0.5s ticks => at least a few ticks.
        assert len(ticks) >= 3, f"on_tick fired too few times: {len(ticks)}"
        assert tick_threads == {caller_thread}, (
            "on_tick must run on the calling thread, got "
            f"{[t.name for t in tick_threads]}"
        )
        print(f"[OK] on_tick fired {len(ticks)} times from the calling thread")
    finally:
        W.push_transactions_to_willexecutor = orig_push3

    # ---- 2d) check_transactions_parallel: parallel + deadline + on_tick ----
    # Pressing "Check" verifies each will-executor still holds its tx.  This used
    # to be a sequential loop with default (~140s) timeouts, freezing the
    # "checking transaction" dialog on a dead server.  It must now run in
    # parallel, enforce a global deadline, and drive an on_tick counter from the
    # calling thread.
    def slow_check(txid, url, **kwargs):
        time.sleep(SLOW)
        return {"tx": "ok"} if "good" in url else None

    orig_check = W.check_transaction
    W.check_transaction = staticmethod(slow_check)
    try:
        targets = []
        for i in range(N):
            kind = "good" if i % 2 else "bad"
            targets.append((f"id{i}", f"https://{kind}-{i}.example"))

        checked = []

        def on_each_check(wid, url, res, exc):
            checked.append((wid, res))

        start = time.time()
        results = W.check_transactions_parallel(
            targets, on_each=on_each_check, max_workers=N
        )
        elapsed = time.time() - start
        sequential = N * SLOW
        assert elapsed < sequential * 0.6, (
            f"check not parallel: {elapsed:.2f}s vs {sequential:.2f}s")
        assert len(results) == N, results
        print(f"[OK] check parallel: {elapsed:.2f}s for {N} servers "
              f"(sequential would be ~{sequential:.2f}s)")
    finally:
        W.check_transaction = orig_check

    # 2d-bis) global deadline + on_tick from the calling thread
    def hanging_check(txid, url, **kwargs):
        if "fast" in url:
            return {"tx": "ok"}
        time.sleep(10)
        return {"tx": "ok"}

    orig_check2 = W.check_transaction
    W.check_transaction = staticmethod(hanging_check)
    try:
        targets = [
            ("idf", "https://fast.example"),
            ("idh", "https://hang.example"),
        ]
        timed_out = []
        ticks = []
        caller_thread = threading.current_thread()
        tick_threads = set()

        def on_timeout_check(wid, url):
            timed_out.append(wid)

        def on_tick_check():
            ticks.append(time.time())
            tick_threads.add(threading.current_thread())

        start = time.time()
        W.check_transactions_parallel(
            targets, max_workers=2, deadline=2.0,
            on_timeout=on_timeout_check, on_tick=on_tick_check,
            tick_interval=0.5,
        )
        elapsed = time.time() - start
        assert elapsed < 4.0, f"check deadline not enforced: {elapsed:.1f}s"
        assert "idh" in timed_out, timed_out
        assert len(ticks) >= 2, f"check on_tick fired too few times: {len(ticks)}"
        assert tick_threads == {caller_thread}, (
            "check on_tick must run on the calling thread")
        print(f"[OK] check global deadline enforced ({elapsed:.1f}s), on_tick "
              f"fired {len(ticks)}x from the calling thread")
    finally:
        W.check_transaction = orig_check2

    # ---- 3) the wizard's loop_push must use the parallel helper ----
    # The "Building Will" wizard broadcasts via BalBuildWillDialog.loop_push.
    # It previously looped over servers sequentially (one
    # push_transactions_to_willexecutor call at a time), which is exactly the
    # slow path the user saw at "Broadcasting your will to executors".  Make
    # sure it now delegates to push_transactions_parallel.
    import inspect
    dialogs_mod = importlib.import_module(f"{PKG}.gui.qt.dialogs")
    loop_push_src = inspect.getsource(dialogs_mod.BalBuildWillDialog.loop_push)
    code = "\n".join(
        line for line in loop_push_src.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "push_transactions_parallel" in code, (
        "wizard loop_push must use push_transactions_parallel (parallel push)")
    assert "for url, willexecutor in willexecutors.items()" not in code, (
        "wizard loop_push must not push to servers in a sequential loop")
    print("[OK] wizard loop_push uses push_transactions_parallel (not sequential)")

    # The wizard counter must be driven via on_tick from the calling thread, NOT
    # via a separate heartbeat thread (whose pyqtSignal emissions never
    # repainted the dialog -> the counter was invisible during "Broadcasting").
    assert "on_tick" in code, (
        "wizard loop_push must drive the counter via on_tick (calling thread)")
    assert "threading.Thread" not in code, (
        "wizard loop_push must not use a heartbeat thread for the counter "
        "(its pyqtSignal emissions are not marshalled / never repaint)")
    print("[OK] wizard loop_push drives the counter via on_tick (no heartbeat "
          "thread)")

    # The counter must show the maximum wait too ("Xs / DEADLINEs"), so the user
    # knows when the wizard will give up waiting, not just an open-ended number.
    assert "PUSH_GLOBAL_DEADLINE" in code, (
        "wizard counter must reference the global deadline so it can show "
        "'Xs / DEADLINEs'")
    assert "{}s / {}s" in code or "s / {}s" in code, (
        "wizard counter must render the elapsed time AND the deadline "
        "(e.g. '3s / 30s')")
    print("[OK] wizard counter shows elapsed time AND the max deadline "
          "(Xs / 30s)")

    # ---- 4) the "Check" dialog must use check_transactions_parallel ----
    # Pressing "Check" runs BalWindow.check_transactions_task.  It used to loop
    # over will-items sequentially calling check_transaction (default ~140s
    # timeouts), freezing the "checking transaction" dialog.  It must now use the
    # parallel helper and show the elapsed-time counter.
    window_mod = importlib.import_module(f"{PKG}.gui.qt.window")
    check_src = inspect.getsource(window_mod.BalWindow.check_transactions_task)
    check_code = "\n".join(
        line for line in check_src.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "check_transactions_parallel" in check_code, (
        "check_transactions_task must use check_transactions_parallel")
    assert "on_tick" in check_code, (
        "check dialog must drive its counter via on_tick (calling thread)")
    assert "{}s / {}s" in check_code, (
        "check dialog counter must render elapsed time AND the deadline")
    print("[OK] check_transactions_task uses check_transactions_parallel "
          "with on_tick counter (Xs / 30s)")

    print(f"\n[OK] parallel networking test passed for package {PKG!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
