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

    print(f"\n[OK] parallel networking test passed for package {PKG!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
