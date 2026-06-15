# Technical report — Parallel networking (Will-Executor anti-freeze) + UI feedback

**Audience:** external programmer / plugin maintainer
**Author:** AI refactoring work (on GitHub `Bitcoin-after-life/test`)
**Date:** 2026-06-15
**Branch:** `feature/networking-parallelo` (Pull Request #4)
**Private Gitea repo `kaibot/bal-plugin-ai`: NOT modified** (per explicit request; cloned read-only only to run the official tests).

---

## 1. Problem

When the plugin contacts the Will-Executor servers (pushing transactions,
pinging/refreshing the inheritance, downloading the list, and **checking**
transactions), it used to do it **sequentially**. If a server did not answer,
the thread stayed blocked on the connection timeouts and, worse, on the
**retries**:

- `send_request` retried up to **10 times** with `time.sleep(3)` on every
  timeout → roughly **~140 seconds per unreachable server**, summed one after
  another.

Consequences:
- Noticeable already with a few servers; with **20 servers** it became
  unusable.
- The user saw "Stay waiting — Not responding" with no idea what was happening.
- A single dead server blocked the whole operation.

---

## 2. Solution (overview)

1. **Parallelism** with `ThreadPoolExecutor`: servers are contacted
   concurrently. Total time ≈ the **slowest** server, not the **sum**.
2. **Fast-fail** for interactive operations (ping/info/download): no retry
   storm, a single short timeout and the server is marked "KO".
3. **Aggressive timeouts + global deadline** for push/check: a short per-server
   retry budget is kept (a real transaction must survive a transient hiccup),
   but a wall-clock **global deadline** caps the whole batch so a dialog never
   freezes behind one unresponsive server.
4. **Live feedback + reliable elapsed-time counter**: `on_each(...)` updates the
   dialog as results arrive, and `on_tick()` refreshes an elapsed-time counter
   (`Xs / DEADLINEs`) so the user always knows progress and the maximum wait.

### Why it is thread-safe
`Network.send_http_on_proxy()` uses `asyncio.run_coroutine_threadsafe(coro,
loop)` and then `coro.result()`: every call schedules its own coroutine on
Electrum's shared asyncio loop and blocks **only its own worker thread**.
Multiple concurrent calls are therefore safe → `ThreadPoolExecutor` gives true
parallelism.

UI updates go through `BalWaitingDialog.update()` / the dialog's `pyqtSignal`,
which marshals to the GUI thread automatically. Callbacks from worker threads
can therefore update the dialog safely.

### Why the counter is driven from the calling thread (important)
An earlier attempt refreshed the elapsed-time counter from a separate raw
`threading.Thread` heartbeat that emitted the `pyqtSignal`. That proved
**unreliable**: a `pyqtSignal` emitted from a raw (non-Qt) Python thread inside
the wizard's `TaskThread` was not reliably marshalled and the dialog never
repainted — the counter was invisible.

The fix: the parallel helpers accept an **`on_tick` callback that is invoked
periodically from the CALLING thread** (the same thread that already drives
`on_each` and successfully repaints). The helpers poll the futures in short
slices (`concurrent.futures.wait(..., timeout=tick_interval)`) and call
`on_tick()` between waits. No heartbeat thread is used anymore.

---

## 3. Modified files (all on GitHub `Bitcoin-after-life/test`, branch `feature/networking-parallelo`)

### 3.1 `bal/core/willexecutors.py`

**Networking constants** (module level, also exposed as `Willexecutors` class
attributes for a single source of truth in the GUI):
```python
DEFAULT_TIMEOUT = 5            # interactive ops (ping/info/list)

PUSH_TIMEOUT = 8               # broadcast (pushtxs)
PUSH_MAX_RETRIES = 2
PUSH_RETRY_SLEEP = 1
PUSH_GLOBAL_DEADLINE = 30      # wall-clock cap for the whole parallel push

CHECK_TIMEOUT = 8              # check (searchtx)
CHECK_MAX_RETRIES = 1
CHECK_RETRY_SLEEP = 1
CHECK_GLOBAL_DEADLINE = 30     # wall-clock cap for the whole parallel check
```
Worst case per server is now ~26s (push) / ~17s (check) instead of ~140s, and
the global deadline guarantees the dialog proceeds within 30s regardless.

**`send_request(...)`** — keyword-only retry controls:
```python
def send_request(method, url, data=None, *, timeout=10, handle_response=None,
                 count_reply=0, max_retries=10, retry_sleep=3):
```
- Defaults unchanged → callers that need the historical behaviour are
  unaffected.
- Interactive callers pass `max_retries=0` → fast-fail.

**`get_info_task(...)`** — fast-fail by default (`max_retries=0`); a
timeout/empty response yields `status="KO"`.

**`check_transaction(...)`** — now accepts `timeout`/`max_retries`/`retry_sleep`
(defaults from the `CHECK_*` constants) and forwards them to `send_request`,
replacing the old ~140s default storm.

**NEW `ping_servers_parallel(willexecutors, *, on_each=None, max_workers=8,
timeout=DEFAULT_TIMEOUT, on_tick=None, tick_interval=1.0)`**
- `ThreadPoolExecutor`; polls futures in slices and calls `on_tick()` from the
  calling thread; mutates `willexecutors` in place; invokes
  `on_each(url, we, ok)` as results arrive; a worker exception never blocks the
  others (defensive try/except).

**NEW `push_transactions_parallel(willexecutors, *, on_each=None, max_workers=8,
deadline=PUSH_GLOBAL_DEADLINE, on_timeout=None, on_tick=None,
tick_interval=1.0)`**
- Parallel push only to entries that have a `"txs"` key; each server keeps its
  short retry budget.
- `on_each(url, we, ok, exc)` per server; `on_timeout(url, we)` for servers
  still pending when the global deadline elapses; `on_tick()` for the counter.
- Manual pool (no `with`) so `shutdown(wait=False, cancel_futures=True)` does
  not block on a hung worker once the deadline is reached.
- Returns `{url: (ok, exc)}` for the servers that answered in time.

**NEW `check_transactions_parallel(items, *, on_each=None, max_workers=8,
deadline=CHECK_GLOBAL_DEADLINE, on_timeout=None, on_tick=None,
tick_interval=1.0)`**
- Same design as the push helper but for the **Check** (searchtx) operation.
- `items` is an iterable of `(wid, url)` pairs; `_check_one` calls
  `check_transaction`.
- `on_each(wid, url, result_or_None, exc)`, `on_timeout(wid, url)`, `on_tick()`.
- Returns `{wid: (result_or_None, exc)}`.

### 3.2 `bal/gui/qt/window.py`

- **`ping_willexecutors_task(self, wes)`** rewritten on `ping_servers_parallel`
  with live feedback and a counter `Ping Will-Executors: 2/3 (3s / 30s)` driven
  by `on_tick` from the calling thread.
- **`push_transactions_to_willexecutors(self, force=False)`** rewritten on
  `push_transactions_parallel`; `on_each` does thread-safe book-keeping + UI
  update; "already present" servers are verified afterwards (original check
  logic intact).
- **`check_transactions_task(self, will)`** rewritten on
  `check_transactions_parallel`; shows `Checking transactions: 2/5 (4s / 30s)`,
  reusing the original `set_check_willexecutor(...)` per-item logic inside
  `on_each` (and `set_check_willexecutor(None)` on `on_timeout`).
- **`fetch_will_executors_list(...)`** fast-fail download
  (`timeout=10, max_retries=1, retry_sleep=1`); the download dialog shows
  `Downloading will-executors list... (Xs / 45s)`.

### 3.3 `bal/gui/qt/dialogs.py`

- **`BalBuildWillDialog.loop_push`** (the "Building Will" wizard broadcast step)
  rewritten on `push_transactions_parallel` with the `on_tick` counter
  `Broadcasting 2/3 (5s / 30s)`. The previous raw heartbeat thread was removed.

### 3.4 `bal/gui/qt/plugin.py` — status-bar icon (restored)

`create_status_bar` re-adds the BAL `StatusBarButton` (bottom-right of the
Electrum status bar). It shows that the plugin is installed and opens the plugin
settings on click; it also de-duplicates the button per window. (Comments in
English.)

### 3.5 `bal/gui/qt/lists.py` and `bal/gui/qt/widgets.py` — GUI usability

- **Tooltips** (hover) on the Will toolbar icons, all in English:
  Wizard (`Wizard - Build your will`), Delivery time (truck), Check Alive
  (siren), Calendar, Check (refresh).
- **Toolbar order** changed to:
  `Wizard | Delivery time | Check Alive | Calendar | Check`; layout margins
  tightened so everything fits the Will window.

### 3.6 `bal/core/util.py` — BUGFIX (pre-existing regression)

In `get_value_amount` (line 324) `Util.in_output(...)` (returns `bool`) had been
used instead of `Util.din_output(...)` (returns the tuple
`(same_amount, same_address)`), causing:
```
TypeError: cannot unpack non-iterable bool object
```
**Fixed** by restoring `din_output`. Found by running the official Gitea tests
(`tests/test_core_util.py::test_get_value_amount`).

---

## 4. Verification (ruff + official tests)

### 4.1 ruff (lint / PEP8)
- `ruff check` on the new code: **no new issues** introduced. The `F403/F405/
  F401` warnings come from the original `from .common import *` pattern;
  per-file counts are identical between HEAD and the working tree.
- The new parallel functions add **0 `E501`** (line-length) issues; in
  `window.py` the count actually decreased after the rewrite.
- `ruff check tests/parallel_ping_test.py` → no new issues.

### 4.2 Official tests from the Gitea repo `kaibot/bal-plugin-ai/tests`
Run against the refactored code (with all the networking + UI changes):

| Suite | Result |
|-------|--------|
| `test_core_*` + `test_gui_*` (pytest) | **182 passed** |
| `smoke_test.py` | OK |
| `external_zip_test.py` | OK |
| `windows_overflow_test.py` | OK |
| `gui_fixes_test.py` | OK |
| `parallel_ping_test.py` (new) | OK — parallel ping/push/check ~`0.50s` for 8 servers (sequential would be ~`4.00s`); global deadline enforced; `on_tick` fired from the calling thread; static checks that the dialogs use the parallel helpers + the `Xs / Ns` counter |

Commands (as per README):
```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 -m pytest tests/ -q
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/smoke_test.py electrum.plugins.bal
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/external_zip_test.py bal-electrum-plugin.zip
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/parallel_ping_test.py bal
```

---

## 5. Integration notes / risks

- **No change to the server protocol**: only the *how* (parallel) and the
  *when* (retries/deadline) of the calls changed, not the payloads.
- **Push transactions**: per-server retries are intentionally kept so a real
  transaction is not lost to a transient hiccup; only ping/info/download use
  fast-fail. The global deadline marks unanswered servers as failed (`on_timeout`)
  so the user can retry later.
- **`max_workers=8`** is conservative; with many servers (e.g. 20) it can be
  raised, but 8 workers already collapse the total time to the slowest server.
- **Thread/UI**: all UI updates from workers go through `pyqtSignal`-based
  dialog updates; the periodic counter is driven by `on_tick` from the calling
  thread. Do **not** reintroduce a raw heartbeat thread emitting signals — it
  does not repaint reliably.
- **Compatibility**: signatures are backward compatible (new parameters are
  keyword-only with defaults that preserve the old behaviour).

---

## 6. How to test

1. Install `bal-electrum-plugin.zip` (Tools → Plugins → install from file).
   Fully close and reopen Electrum to avoid the cached zip import.
2. Configure several Will-Executors, including **at least one unreachable**.
3. Run push / ping / Check: each dialog shows per-server status plus a counter
   `N/total (Xs / 30s)` and **no longer freezes** on the dead server — within
   the global deadline the operation reports the dead server and proceeds.

The SHA-256 of the zip is printed by `build_zip.py` at the end of the build
(use it to verify integrity).
