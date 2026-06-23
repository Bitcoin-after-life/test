# BAL — Refactoring report (for the original author)

This document lists **all** the changes made to the BAL plugin
(Bitcoin After Life) with respect to the original version `0.2.8`.

**Guiding principle:** **conservative, behaviour-preserving** refactoring
(Approach A). The business logic was kept **byte-identical** where possible;
what changed are mainly the **file layout** and the **imports**. No algorithmic
rewrite.

Verification environment: **Electrum 4.7.2** + **PyQt6** (the latest stable
release that exposes `json_db.register_dict`).

---

## 1. Structure reorganization (logic / GUI separation)

The main reported problem was that logic and graphics were mixed together, in
particular in a single `qt.py` file of **4131 lines**.

### Structure BEFORE (flat, 7 files)
```
BAL/
├── __init__.py        (empty, 0 lines)
├── bal.py             (243)  logic + plugin base
├── util.py            (533)  helpers
├── heirs.py           (791)  heirs model + tx building
├── will.py            (927)  will/WillItem model
├── willexecutors.py   (374)  will-executor networking
├── qt.py              (4131) ALL the GUI + the Plugin in a single file
└── bal_resources.py   (14)
```

### Structure AFTER (core/ vs gui/)
```
bal/
├── manifest.json            standard-compliant metadata
├── qt.py                    loading shim (re-export of Plugin)
├── __init__.py              architecture docstring + __version__
├── core/                    LOGIC with no Qt dependencies
│   ├── util.py              (was util.py)
│   ├── plugin_base.py       (was bal.py)
│   ├── heirs.py             (was heirs.py)
│   ├── will.py              (was will.py)
│   └── willexecutors.py     (was willexecutors.py)
└── gui/qt/                  PyQt6 PRESENTATION
    ├── theme.py      (59)   status → colour mapping
    ├── common.py     (155)  shared imports + GUI helpers
    ├── widgets.py    (782)  "leaf" widgets
    ├── calendar.py   (80)   BalCalendar
    ├── dialogs.py    (1127) dialog windows
    ├── lists.py      (957)  tree views (heirs/preview/executor)
    ├── window.py     (952)  per-wallet GUI controller (BalWindow)
    └── plugin.py     (273)  Plugin class (@hook Electrum → GUI)
```

The 4131-line `qt.py` file was split by **responsibility**. The **class bodies
were copied verbatim** (line by line) so as not to touch the delicate
inheritance-transaction logic.

### Map: where the 40 classes/functions of `qt.py` ended up

| Class/function (orig. line)         | New module              |
|-------------------------------------|-------------------------|
| `Plugin` (67)                       | `gui/qt/plugin.py`      |
| `shown_cv` (317)                    | `gui/qt/common.py`      |
| `BalWindow` (330)                   | `gui/qt/window.py`      |
| `add_widget` (1257)                 | `gui/qt/common.py`      |
| `ClickableLabel` (1263)             | `gui/qt/widgets.py`     |
| `BalTxFeesWidget` (1271)            | `gui/qt/widgets.py`     |
| `_LockTimeEditor` (1340)            | `gui/qt/widgets.py`     |
| `BalTimeEditWidget` (1374)          | `gui/qt/widgets.py`     |
| `TimeRawEditWidget` (1508)          | `gui/qt/widgets.py`     |
| `LockTimeRawEdit` (1527)            | `gui/qt/widgets.py`     |
| `LockTimeDateEdit` (1605)           | `gui/qt/widgets.py`     |
| `ThresholdTimeWidget` (1644)        | `gui/qt/widgets.py`     |
| `LockTimeWidget` (1664)             | `gui/qt/widgets.py`     |
| `WillSettingsWidget` (1683)         | `gui/qt/widgets.py`     |
| `PercAmountEdit` (1818)             | `gui/qt/widgets.py`     |
| `BalDialog` (1883)                  | `gui/qt/dialogs.py`     |
| `BalWizardDialog` (1913)            | `gui/qt/dialogs.py`     |
| `BalWizardWidget` (2002)            | `gui/qt/dialogs.py`     |
| `BalWizardHeirsWidget` (2068)       | `gui/qt/dialogs.py`     |
| `BalWizardWEDownloadWidget` (2103)  | `gui/qt/dialogs.py`     |
| `BalWizardWEWidget` (2190)          | `gui/qt/dialogs.py`     |
| `BalWizardLocktimeAndFeeWidget`(2207)| `gui/qt/dialogs.py`    |
| `BalWaitingDialog` (2224)           | `gui/qt/dialogs.py`     |
| `BalBlockingWaitingDialog` (2285)   | `gui/qt/dialogs.py`     |
| `BalLineEdit` (2304)                | `gui/qt/widgets.py`     |
| `BalTextEdit` (2312)                | `gui/qt/widgets.py`     |
| `BalCheckBox` (2320)                | `gui/qt/widgets.py`     |
| `BalBuildWillDialog` (2335)         | `gui/qt/dialogs.py`     |
| `HeirListWidget` (2858)             | `gui/qt/lists.py`       |
| `PreviewList` (3059)                | `gui/qt/lists.py`       |
| `WillDetailDialog` (3445)           | `gui/qt/dialogs.py`     |
| `WillWidget` (3545)                 | `gui/qt/widgets.py`     |
| `WillExecutorListWidget` (3637)     | `gui/qt/lists.py`       |
| `WillExecutorWidget` (3873)         | `gui/qt/lists.py`       |
| `WillExecutorDialog` (3982)         | `gui/qt/dialogs.py`     |
| `CheckAliveError` (4018)            | `gui/qt/common.py`      |
| `log_error` (4028)                  | `gui/qt/common.py`      |
| `export_meta_gui` (4043)            | `gui/qt/common.py`      |
| `BalCalendar` (4066)                | `gui/qt/calendar.py`    |

---

## 2. Removals (dead / debug code) — behaviour unchanged

All the following removals were verified as **unused** or **purely debug**, so
they do not alter the plugin's behaviour.

1. **`util.py` → `core/util.py`**: removed three debug helpers used only for
   console printing:
   - `print_var()`   (orig. line 439)
   - `print_utxo()`  (orig. line 474)
   - `print_prevout()` (orig. line 486)

2. **`bal.py` → `core/plugin_base.py`**: removed the **empty stub** function
   `get_will_settings(x)` (orig. lines 12-14):
   ```python
   def get_will_settings(x):
       # print(x)
       pass
   ```
   ⚠️ Verified: **it was not referenced by any `register_dict`** — the three
   `register_dict` calls use `tuple`, `dict`, `lambda x: x`. So it was dead
   code. The **used** function `get_will(x)` was kept identical.

3. **`will.py` (`WillItem`) → moved to `gui/qt/theme.py`**: the method
   `WillItem.get_color()` (orig. line 852) returned hexadecimal colours —
   it is **presentation** logic, not domain logic. It was moved out of the
   model and turned into the function `status_color(will_item)` in
   `gui/qt/theme.py`. **Verified byte-identical** across all status
   combinations (same `get_status(...)` chain, same colour codes).

---

## 3. Import changes (required by the new structure)

The imports were updated from "flat" to "package" style. Examples:

| Before                             | After                                 |
|------------------------------------|---------------------------------------|
| `from .bal import BalPlugin`       | `from .plugin_base import BalPlugin`   (in willexecutors) |
| `from .util import Util`           | `from .util import Util`               (unchanged, now inside core/) |
| (in qt.py) `from .bal import ...`  | the GUI modules import from `...core.X`  |

- Added `from .common import _, _logger` in the GUI modules, because `import *`
  does **not** export names starting with an underscore.
- Added 3 "lazy" imports (inside the functions) in `dialogs.py` to break the
  `dialogs ↔ lists` cycle (lists imports `BalBuildWillDialog` from dialogs).

The **internal logic of the methods** was not touched: `prepare_transactions()`,
`buildTransactions()`, etc. are verbatim.

---

## 4. Electrum-standard packaging

`manifest.json` made compliant with https://plugins.electrum.org/developers.html :

| Field            | Before             | After                         |
|------------------|--------------------|-------------------------------|
| `name`           | `"BAL"`            | `"bal"` (lowercase = dir name) |
| `version`        | (absent, was only in the description) | `"0.2.8"`     |
| `description`    | with HTML `<br>`   | clean text                    |
| `licence`        | (absent)           | `"MIT"`                       |
| `fullname`/`author`/`available_for`/`icon` | present | unchanged        |

- `__init__.py` (was **empty**): now contains the architecture docstring and
  `__version__ = "0.2.8"`.
- Brought into the package: `LICENSE`, `VERSION`, `README.md`, `bal_resources.py`,
  and the `wallet_util/` folder (unchanged).

---

## 5. BUG FIX: loading as an external plugin (.zip)

During testing on **Electrum 4.7.2 portable for Windows**, two real problems
emerged when loading the plugin as an **external plugin from .zip**:

### Bug 5a — `ModuleNotFoundError: No module named 'electrum_external_plugins'`
- **Cause:** Electrum loads external plugins from zip under the synthetic
  package `electrum_external_plugins.bal`, and runs **only** the package
  `__init__` and the `qt` module. It does not register the synthetic root
  package nor the nested sub-packages (`gui`, `gui.qt`). A simple
  `from .gui.qt.plugin import Plugin` fails when walking up to the missing
  parents.
- **Fix:** `qt.py` is now a resilient shim that (1) detects its own package
  name at runtime (`__package__`), (2) rebuilds in `sys.modules` any missing
  parent packages, (3) imports `Plugin` with `importlib.import_module`. It
  works **both** as an internal plugin (`electrum.plugins.bal`) **and** as an
  external one (`electrum_external_plugins.bal`).

### Bug 5b — `zlib.error: Error -5 ... incomplete or truncated stream`
- **Cause:** some Electrum portable builds on Windows fail to decompress with
  `zipimport` archives that contain **directory entries** or non-standard
  compression.
- **Fix:** added `build_zip.py`, which generates a "zipimport-friendly"
  archive: files only (no directory entries), standard DEFLATE, deterministic
  ordering (reproducible SHA-256), excluding `__pycache__`/`*.pyc`. It also
  prints the SHA-256 hash to verify the integrity of the download.

---

## 6. Tests added

- `tests/smoke_test.py` — checks imports + basic behaviour
  (`BalTimestamp`, `Util` helpers, `HEIR_*` constants, `WillItem` states,
  `Plugin` hooks).
- `tests/external_zip_test.py` — **faithfully** reproduces Electrum's loading
  sequence for an external plugin from zip (regression test for Bug 5a/5b).

All tests pass under Electrum 4.7.2 + PyQt6.

---

## 7. Summary: what did NOT change

- The transaction-building logic (`heirs.py`, `will.py`).
- The values and types of `json_db.register_dict(...)`.
- The status colour codes (only moved to `theme.py`).
- The algorithm of all the GUI classes (copied verbatim).
- The format of the data saved in the wallet.

## 8. Notes / recommendations

- The plugin **requires Electrum 4.7.2**: `json_db.register_dict` was
  **removed** in later versions (master), where it should be replaced with
  `stored_dict.register_name`. Consider an update if you want to support a
  more recent Electrum.
- Before release, an **end-to-end test in a real Electrum session** is
  recommended (preferably on testnet), in addition to the smoke tests.

---

## 9. GUI FIXES — windows and lifecycle (B1-B10)

After the structural refactoring, **ten graphical and lifecycle defects** of
the windows were fixed, all already present in the original code. The business
logic remained **byte-identical** (no changes to `bal/core/*`): only the
**presentation, parent, modality, z-order, lifecycle and cleanup** of the Qt
windows changed.

Symptoms reported by the user, now resolved:
- **(S1)** the plugin windows disappeared behind the Electrum window;
- **(S2)** some mechanisms worked only after closing and restarting Electrum.

| ID  | Problem (present in the original)                                    | Applied fix |
|-----|----------------------------------------------------------------------|----------------------|
| B1  | `self.parent = parent` overrode Qt's `parent()` method, breaking the window hierarchy | renamed to `self._bal_parent` (in `dialogs.py`, `lists.py`, `widgets.py`); the real parent comes from `top_level_of(parent)` |
| B2  | dialogs opened with non-modal `.show()` → ended up under the main window | replaced with `show_on_top()` / `show_modal()` and the correct parent |
| B3  | message "Please restart Electrum to activate the BAL plugin": the plugin activated only after a restart | **hot** initialization with `_setup_window()` that replicates `load_wallet` — no more restart |
| B4  | the windows-dictionary key used the `winId` **method** instead of its value | stable `_window_key()` key based on `id(window)` |
| B5  | `on_close` swallowed all errors with `except: pass` | rewritten: no `except:pass`, logging at every step, clean state reset |
| B6  | `BalBlockingWaitingDialog` blocked the GUI thread (`processEvents` commented out) | restored `processEvents()` → responsive GUI during the wait |
| B7  | `closeEvent`/`hideEvent` with the thread cleanup commented out | explicit handling of `closeEvent`/`hideEvent` + call to `super()` |
| B8  | incomplete `closeEvent` in some dialogs | uniform handling of the closing state |
| B9  | `show()+raise_()` without `activateWindow()` nor modality → window not in the foreground | `bring_to_front()` = `raise_()` + `activateWindow()` |
| B10 | fragile multi-wallet / multi-window handling; menu looked up by the `&Tools` title | use of the official `window.tools_menu` API |

### New module: `gui/qt/window_utils.py` (119 lines)

The window-management helpers were **centralized** in a single module, so that
the same logic is not duplicated across the various dialogs:

- `top_level_of(widget)` — walks up to the correct top-level window to use as
  parent;
- `bring_to_front(window)` — `raise_()` + `activateWindow()` to bring to the
  foreground;
- `stop_thread(thread)` — safe stop+wait of a `TaskThread`;
- `show_modal(dialog)` — correct modal opening (`exec()`);
- `show_on_top(window)` — non-modal opening but above the other windows.

`gui/qt/common.py` imports these helpers and makes them available to the rest
of the GUI.

---

## 10. BUG FIX: will-executor list download

After installing the package with the GUI fixes, the user reported that the
will-executor **"download list"** command no longer downloaded the list.

### Investigation

The network code (`core/willexecutors.py`: `send_request`, `handle_response`,
`download_list`, `initialize_willexecutor`) was compared line by line with the
original Gitea version and turned out to be **byte-identical** (the only
difference is the extra `welist_server` parameter in `download_list`, which is
backward-compatible).

During the investigation, **two real defects** introduced by the GUI fixes were
nevertheless found and corrected, which could "lose" the download result:

1. **`BalDialog.closeEvent`/`hideEvent` stopped the `TaskThread`.** In Electrum,
   `TaskThread.on_done` runs `cb_done` (i.e. `self.accept`, which **closes** the
   dialog) **before** `cb_result` (i.e. `on_success`, which **updates** the
   list). Stopping the thread when the dialog closed therefore **discarded** the
   result that had just been downloaded. → The two methods were restored so they
   do **not** stop the thread (with an explanatory comment in the code).
2. **`BalWaitingDialog.exe()` used the wrong modality** (`show_modal` /
   `WindowModal`). → Restored the original `self.exec()`, first adding
   `bring_to_front(self)` to guarantee the foreground.

In addition, the **button** and **wizard** paths (which previously downloaded
in different ways and with different messages) were **unified** into a single
helper `fetch_will_executors_list`, run inside the `TaskThread` worker.

### Real cause of the failed download: environmental, NOT the plugin

A control probe with `urllib` that **completely bypassed Electrum** also failed
with `WinError 10054` ("connection forcibly closed by remote host"): a sign
that the **user's network/ISP was resetting the HTTPS connection** to
`welist.bitcoin-after.life`. The definitive confirmation: **with a VPN enabled
the download succeeded.**

The original "seemed" to work because it ships anyway a **built-in default**
will-executor (`https://we.bitcoin-after.life`), so the list never appeared
completely empty even without a successful download.

### Final cleanup (chosen by the user — "Option 1")

- **Non-blocking waiting window** kept (`BalWaitingDialog`), so the GUI does
  not freeze during the download.
- **URL fallback**: first the configured URL (`WELIST_SERVER`), then the
  hardcoded `https://welist.bitcoin-after.life/`.
- **Detailed diagnostics moved to the logs only** (removed the `urllib` probe
  from the interface).
- **Simple error message for the user, in English** (`DOWNLOAD_FAILED_MESSAGE`):

  > *"Could not download the will-executors list. This is usually caused by
  > your internet connection or a firewall, not by the plugin. Please check
  > your connection (a VPN often helps) and try again."*

### Files touched (presentation/GUI only, logic unchanged)

- `gui/qt/window.py` — shared helper `fetch_will_executors_list`,
  `download_list` with `TaskThread` + `BalWaitingDialog`, constant
  `DOWNLOAD_FAILED_MESSAGE`.
- `gui/qt/lists.py` — `WillExecutorWidget.download_list` routed onto the shared
  path with an `on_success` that updates/saves the list.
- `gui/qt/dialogs.py` — `BalDialog.closeEvent`/`hideEvent` no longer stop the
  thread; `BalWaitingDialog.exe()` goes back to `self.exec()` + `bring_to_front`.
- `tests/gui_fixes_test.py` — **regression** assertion: verifies that
  `closeEvent`/`hideEvent` do **not** contain `stop_thread` (so as not to
  reintroduce the bug that discarded the download).

---

## 11. Final structural comparison (original Gitea → refactor)

`.py` file count (excluding generated folders):

| Original (Gitea)             | lines | →  | Refactor (`bal/`)                         | lines |
|------------------------------|------:|----|-------------------------------------------|------:|
| `__init__.py`                |     1 | →  | `__init__.py`                             |    37 |
| `bal.py`                     |   161 | →  | `core/plugin_base.py`                     |   351 |
| `util.py`                    |  1051 | →  | `core/util.py`                            |   614 |
| `heirs.py`                   |   792 | →  | `core/heirs.py`                           |   806 |
| `will.py`                    |   903 | →  | `core/will.py`                            |   938 |
| `willexecutors.py`           |   547 | →  | `core/willexecutors.py`                   |   390 |
| `qt.py` (GUI monolith)       |  3777 | →  | split into `gui/qt/*` (see below)         |     — |
| `bal_resources.py`           |    14 | →  | `bal_resources.py`                        |    14 |
| `wallet_util/*.py`           |   275 | →  | `wallet_util/*.py` (unchanged)            |   280 |

Split of the old `qt.py` (3777 lines) into the GUI modules:

| Refactor module             | lines | Content |
|-----------------------------|------:|-----------|
| `gui/qt/plugin.py`          |   303 | `Plugin` class (`@hook` Electrum → GUI) |
| `gui/qt/window.py`          |  1048 | `BalWindow` (per-wallet controller) |
| `gui/qt/dialogs.py`         |  1155 | dialog windows + wizard |
| `gui/qt/lists.py`           |   964 | tree views (heirs/preview/executor) |
| `gui/qt/widgets.py`         |   782 | "leaf" widgets |
| `gui/qt/common.py`          |   157 | shared imports + helpers |
| `gui/qt/window_utils.py`    |   119 | window helpers (NEW — see §9) |
| `gui/qt/calendar.py`        |    80 | `BalCalendar` |
| `gui/qt/theme.py`           |    59 | status → colour mapping |
| `gui/qt/__init__.py`        |    17 | GUI package init |

> The differences in the line counts compared to the original come from:
> reformatting/comments, separation of imports per module, and the movement
> of functions between `util.py`/`bal.py` and the new modules. **The algorithms
> were not modified.**

---

## 12. Change history on GitHub

- **`4198a51`** — initial import of the structural refactor (v0.2.8):
  separation of `core/` (logic) vs `gui/qt/` (presentation), compliant
  packaging, external-zip load fix, smoke test (sections §1-§8).
- **`d56fa36`** — this refactoring changelog (in Italian).
- **`4806997`** — `GUI_DIAGNOSIS.md` (originally `DIAGNOSI_GUI.md`): diagnosis
  of the z-order and lifecycle GUI bugs (Phase A).
- **`dd6f677`** (PR **#2**, squash) — GUI fixes **B1-B10** + will-executor list
  download fix + `window_utils.py` + regression test (sections §9-§10).
- **PR #3** — fix for the **OverflowError on Windows (year 2038)** that broke
  the Will/Heirs tabs and the menu entry (section §13).

---

## 13. BUG FIX: OverflowError on Windows (year-2038 limit)

### Symptom (Windows 11)
After **restarting Electrum** or **switching wallet**, the **Will** and
**Heirs** tabs disappeared and a **condensed/illegible menu entry**
(overlapping icon + text) appeared under the Electrum logo, next to *Wallets*.
On Linux the problem did not occur.

### Real cause (from the user's Electrum log)
```
OverflowError: Python int too large to convert to C int
  window.py __init__ -> create_heirs_tab -> WillSettingsWidget
  -> on_locktime_change -> BalTimestamp.to_date
  -> datetime.fromtimestamp(NLOCKTIME_MAX)
```

- `NLOCKTIME_MAX = 2**32 - 1 = 4294967295` is used as the
  **default/sentinel** locktime.
- On **Windows** `time_t` is **32-bit**, so `datetime.fromtimestamp(ts)`
  raises **`OverflowError`** for any timestamp beyond **2038**.
- On **64-bit Linux** the same call **works**: that is why the bug was visible
  only on Windows and the Linux tests did not catch it.
- The exception interrupted `BalWindow.__init__` during `init_menubar` /
  `load_wallet`, leaving the Will/Heirs tabs and the menu entry **half-built**
  → the condensed/illegible graphical element under the logo.

> Note: the first two correction attempts (a no-op status bar and the
> idempotency of `init_menubar_tools`) did **not** hit the cause; they were
> kept anyway because they are harmless and slightly improving, but the real
> culprit was this upstream crash.

### Fix (behaviour unchanged for all normal values)
- **`BalTimestamp._safe_fromtimestamp()`**: `datetime.fromtimestamp` with
  a **clamp to INT32_MAX** (year 2038) on `OverflowError`/`OSError`/
  `ValueError`, **exactly** like the original's `get_max_allowed_timestamp()`
  function (workaround for Electrum issue **#6170**).
- Used in `to_date` / `to_timestamp` / `__str__` / `__repr__` of
  `BalTimestamp`.
- `gui/qt/widgets.py` (`set_value`): uses the safe converter.
- `core/util.py` (`timestamp_minus`): same inline protection with a clamp to
  INT32_MAX.

Values within 2038 (normal absolute dates, relative durations such as
`90d`/`5y`) produce **exactly the same result** as before.

### Test
- `tests/windows_overflow_test.py` reproduces the Windows 32-bit limit
  (monkeypatch of `datetime.fromtimestamp`) and proves that **without** the fix
  you get the **same** `OverflowError` as in the log, while **with** the fix it
  passes. It was also verified that the test **fails** without the fix.

Confirmed by the user: **"yes, it works now"**.

## 14. NEW FEATURE: automatic invalidation when postponing the inheritance

### Problem
An inheritance transaction is signed with a **fixed, immutable locktime** and
sent to the will-executors, who are economically incentivized to broadcast it
(they collect the fees). If the user, after signing/sending, **postpones** the
delivery date (e.g. by one year), the **old** already-signed transaction
remains valid on the will-executors' servers. Since it has the lower locktime,
a will-executor could broadcast it as soon as it expires, executing the
inheritance **earlier** than the user's new intent. The previous version did
**not handle** this case: postponing produced no action at all.

### Solution (Strategy B — explicit on-chain invalidation)
When postponing an inheritance that is **already signed and/or sent** (state
`COMPLETE` or `PUSHED`), the plugin asks to **invalidate the funds on-chain**
before rebuilding the new inheritance. The invalidation spends the same UTXOs
to a new change address with `locktime = current height` (RBF), so it is
broadcastable immediately: once confirmed, the old pre-signed transaction
becomes **permanently unusable**, winning the race against any will-executor.

### Technical details
- **`core/will.py`**:
  - new exception `WillPostponedException` (subclass of
    `NotCompleteWillException`);
  - `check_willexecutors_and_heirs`: the locktime comparison no longer uses the
    stored heir entry (`their[2]`), which is updated in memory together with the
    new value at the moment of postponement and would therefore always look
    equal. It now compares the requested locktime with **`w.tx.locktime`**, i.e.
    the locktime **frozen** in the signed transaction (immutable, and the one
    the will-executors hold). Three cases: unchanged → coherent; new > tx on a
    signed/sent will → `WillPostponedException`; new > tx on a will never sent
    → simple rebuild (no on-chain fee).
- **`gui/qt/dialogs.py`** (`BalBuildWillDialog.task_phase1`, the real path used
  by **Tools → Prepare**): added the `except WillPostponedException` branch
  **before** `NotCompleteWillException`; it behaves like the "expired will"
  case and returns `(None, tx)` to trigger signing + broadcasting of the
  invalidation. The user presses **Prepare** again to rebuild, re-sign and
  re-send the new inheritance (two explicit steps, for greater control).
- **`gui/qt/window.py`** (`build_inheritance_transaction`): added the same
  branch for completeness of the alternative path, with an explanatory message.
- **`gui/qt/common.py`**: `WillPostponedException` exported.

### NEW "Server" COLUMN in the transactions list
To give the user constant visibility on the online status of their inheritance
transactions, a dedicated **"Server"** column was added in `PreviewList`
(`gui/qt/lists.py`), with an always-readable label (`Confirmed on server`,
`Sent (not checked)`, `Send failed`, `Not on server`, `Signed (not sent)`,
`Not sent`) and a **tooltip** with the will-executor URL and status. The
functions `server_status_text()` and `server_status_tooltip()` are in
`gui/qt/theme.py` and reuse the same already-existing status flags.

### Test
- The 182 official tests keep passing; smoke test and external-zip test OK;
  `ruff` with no new real warnings.
- Verified against the real data from the user's log: postponing a signed
  inheritance now correctly detects the condition and starts the invalidation.

Confirmed by the user: **"it seems to work"**.

## 15. ATTEMPT AND REVERT: fix for double invalidation on postpone (v0.3.1 -> v0.3.2)

### v0.3.1 (WITHDRAWN)
To solve the double signing of the invalidation on postpone,
`Will.mark_invalidated_by_tx()` had been introduced, called in
`loop_broadcast_invalidating` after broadcasting the invalidation, to mark as
`INVALIDATED` the wills that spent the same UTXOs as the invalidation tx and to
persist the state with `save_willitems`.

### Why it was withdrawn
The change introduced a serious regression reported by the user:
**the inheritance list still showed the old inheritances and the update of
heirs/dates was inconsistent**.

Cause: `loop_broadcast_invalidating` is the broadcast point used for **ALL**
types of invalidation (postpone, CheckAlive, expired/anticipated will), not
only for postpone. In addition, the method marked and **persisted** the
`INVALIDATED` state on all the will items that shared the wallet's UTXOs
(typically all of them). These invalidated will items then stayed in memory and
on disk, polluting the rebuild of heirs/dates and leaving old entries in the
list.

### v0.3.2 (this version): full REVERT
- Removed `Will.mark_invalidated_by_tx()` from `core/will.py`.
- Removed the call in `gui/qt/dialogs.py` (`loop_broadcast_invalidating`): the
  method goes back to being **identical** to v0.3.0.
- Removed the two related tests; kept only the hierarchy assertion on
  `WillPostponedException` (correct and independent).
- `core/will.py` and `gui/qt/dialogs.py` are now **byte-identical** to the
  working v0.3.0 (verified with `git diff a394cde`).

The double-invalidation-on-postpone bug therefore remains **open** and will
have to be tackled in a more targeted way (without touching the common
broadcast path and without persisting states on wills that share the UTXOs),
subject to the user's confirmation. The priority was to restore the correct
behaviour of the list/heirs/dates.

## 16. Missed updates, consistent Check/Close, and UI polish (v0.3.2)

### FIX 1 - Removal of an heir detected on Check / Electrum close
`core/will.py` (`check_willexecutors_and_heirs`): previously the plugin
detected only the **addition** of an heir (raising `HeirNotFoundException` when
a current heir was no longer in the will). The opposite case was missing: the
**removal** of an heir. Added the `else` branch that raises
`HeirNotFoundException` also when the will still carries an heir that is no
longer present in the current heir set. This way the inheritance rebuild is
triggered on **Check** and on **Electrum close** (both use the same
`BalBuildWillDialog.build_will_task()` path), as decided by the user: no
automatic update after the change, only a manual one via Check / on close.

### FIX 2 - Check also queries the servers for already-sent wills
`core/will.py` (new `Will.needs_server_check(w)`) and `gui/qt/lists.py`
(`PreviewList.check`): previously Check queried the servers only for wills in
the `PUSHED` state. Wills already sent but left at "New / Not sent" were not
re-checked ("nothing to do"). Now `needs_server_check` includes every **VALID**
will with a will-executor that is **not yet CHECKED**, even if not in the
`PUSHED` state. The same check is used both by the Check button and by
`on_close`.

### FIX 3 - Hide invalidated/replaced from the Settings window updated the list
`core/plugin_base.py` (new `sync_hide_filters()`) and `gui/qt/window.py`
(`update_all`): the "Hide Replaced" / "Hide Invalidated" checkboxes in the
Settings window write the config directly (`BalConfig.set`) without touching the
cached flags `_hide_invalidated` / `_hide_replaced` that the list uses to
filter. Result: the list kept filtering with the old value until Electrum was
restarted. Now `update_all()` calls `sync_hide_filters()`, which re-reads the
flags from the config, so whatever the source of the change (toolbar or
Settings window) the list updates immediately.

### UI polish - Bold results in the "Building Will" dialog
`gui/qt/dialogs.py` (`BalBuildWillDialog`): the **results** shown to the right
of each status line (e.g. `Ok`, `Ko`, `Nothing to do`, `Skipped`, `Wait`,
`Timeout`) are now rendered in **bold**, keeping their colours
(green/red/yellow). The status labels on the left stay in normal weight. The
change is centralized in the helpers `msg_ok`, `msg_error`, `msg_warning`,
`msg_set_status`, plus the will-executor lines (push and check) that now show
`Ok/Ko` and `True/False` in bold + colour (green/red).

### Test
- 186 official tests pass; smoke test, external-zip test and the update-flow
  simulation (`tests/sim_update_flows.py`) OK; `ruff` with no new real warnings
  (only pre-existing false positives from star-imports).
- Added tests in `tests/test_core_will.py`:
  `test_check_heirs_unchanged_is_coherent`,
  `test_check_heir_removed_triggers_rebuild`,
  `test_check_heir_added_triggers_rebuild`, `test_needs_server_check`.

Confirmed by the user against real data: after Sign -> Broadcast -> Check the
already-sent transactions turned green again ("confirmed on server"); the list
goes back clean; the bold rendering and the hide-flag update work.

## 17. UI polish and bug fix — signed-tx colour, wizard, Building Will dialog (v0.3.3)

This session groups several behaviour-invariant UI refinements plus one colour
bug fix.  All comments and code remain in English; only the chat with the
author was in Italian.

### FIX — Signed-but-not-sent transaction shown RED instead of blue
`core/will.py` (`needs_server_check`): a previous-session change (section 16,
"FIX 2") had removed the `PUSHED` requirement from `needs_server_check`, so a
will that was *signed but never broadcast* was still server-queried.  The query
returned CHECK_FAIL, and because `status_color()` checks CHECK_FAIL (red,
`#e83845`) before COMPLETE (blue, `#2bc8ed`), the row turned red.  Restored the
original Gitea `check()` condition by adding back `and w.get_status("PUSHED")`,
so only already-broadcast wills are server-checked.  A signed-but-not-sent will
now stays blue (COMPLETE) as in the original.
- `tests/test_core_will.py` (`test_needs_server_check`): a freshly-built item
  (VALID, not PUSHED) now correctly expects `False`.

### Wizard "Will Settings" — equal-width, left-aligned rows
`gui/qt/widgets.py` (`WillSettingsWidget`, vertical layout): the calendar button
and the fee field used to stretch to the dialog's right edge, far wider than the
date rows.  Now every row is capped to the widest date-row width (`row_w`) and
left-aligned, so they form a tidy column.  The leading icons keep their original
`HelpButton` width (`icon_w` is used only as a spacer in front of the calendar,
never to widen the icons themselves).

### Wizard button — icon + text
`gui/qt/lists.py` (`create_toolbar`): the "build your will" toolbar button is now
more inviting: a 28×28 wizard icon plus a bold `"Create your will"` caption,
`setMinimumHeight(40)`.  `gui/qt/common.py` gained `QSize` in the QtCore import.

### Building Will dialog — clearer final report + manual Close
`gui/qt/dialogs.py` (`BalBuildWillDialog`):
- The closing summary line is no longer a bare "Ok": it now has an explicit
  left-side label, `"All done: Ok"`, like the other result rows.
- A blank separator row is inserted above "All done" so the overall outcome is
  visually detached from the per-step rows.
- The four `"checking variables"` status strings are capitalised to
  `"Checking variables"` to match the rows below; the redundant trailing colon
  on the final one was dropped (`msg_set_status` already adds `":\t"`).
- The final auto-closing countdown (`self.wait(5)`) was replaced by an explicit
  right-aligned **"Close"** button (`_add_close_button` / `_on_close_clicked`).
  The dialog now stays open until the user dismisses it, so the full report can
  be read at leisure.  The intermediate technical pauses (`wait(10)`, `wait(5)`,
  `wait(3)`) are kept.  Closing still shows the persistent "next steps"
  (Sign / Broadcast) popup when `self._next_steps_hint` is set.

### Preview helpers (dev-only, not shipped logic)
`tests/preview_wizard_settings_align.py`, `tests/preview_wizard_button.py`,
`tests/preview_building_will_close_btn.py`: small offscreen scripts used to
render before/after mock-ups for visual approval.

### Test
- 186 official tests pass; smoke test, external-zip test OK.
- `ruff` reports only the pre-existing baseline false positives (F401/F403/F405
  star-import re-exports, one F841, one F541) — no new issues.
- Version bumped to **0.3.3** (`bal/VERSION`, `bal/__init__.py`,
  `bal/manifest.json`).

## 18. Documentation site (docs/) — no behaviour change

Added a `docs/` tree that renders directly on GitHub and GitHub Pages (no PDF):

- `docs/inheritance-options.md` + `.html`: a code‑accurate **Inheritance Options
  Guide** covering every change a user can make (date earlier/later, add/remove
  heir, change percentages, fees, will‑executors), each transaction status flag
  and its colour, and what happens on the will‑executor servers. Includes a
  decision **flow chart** (GitHub‑native Mermaid block in the `.md`, plus a
  static SVG fallback `docs/images/inheritance-flow.svg`, plus a live Mermaid
  render in the `.html`). Behaviour is derived directly from
  `core/will.py::is_will_valid` / `check_willexecutors_and_heirs` and
  `gui/qt/window.py::build_inheritance_transaction`.
- `docs/manual/README.md` + `manual.html` + `images/`: the official **BAL User
  Manual (revB)** converted from the upstream Gitea PDF into GitHub‑friendly
  Markdown/HTML with the original screenshots re‑rendered at high resolution
  (`docs/manual/images/fig*.png`, `logo.png`).
- `docs/README.md`: documentation index linking both documents.

No plugin code changed; 186 tests still pass.
