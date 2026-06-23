# BAL — Diagnosis of the GUI problems (Phase A) → ✅ RESOLVED (Phase B)

> **STATUS: all bugs B1-B10 have been FIXED** and merged into `main`
> (PR #2, squash `dd6f677`). The business logic remains **byte-identical**
> (no changes to `bal/core/*`): only the presentation, parent, modality,
> lifecycle and cleanup of the windows changed.
>
> | ID | Status | Applied fix |
> |----|--------|-------------|
> | B1 | ✅ FIXED | `self.parent` → `self._bal_parent` (dialogs/lists/widgets); parent = `top_level_of(parent)` |
> | B2 | ✅ FIXED | `.show()` → `show_on_top()` / `show_modal()` with the correct parent |
> | B3 | ✅ FIXED | hot init: `_setup_window()` replicates `load_wallet`, no more "restart Electrum" |
> | B4 | ✅ FIXED | stable window key `_window_key()` = `id(window)` |
> | B5 | ✅ FIXED | `on_close` rewritten: no `except:pass`, per-step logging, state reset |
> | B6 | ✅ FIXED | `BalBlockingWaitingDialog`: `processEvents()` restored |
> | B7 | ✅ FIXED | `closeEvent/hideEvent`: `stop_thread()` + `super()` |
> | B8 | ✅ FIXED | `closeEvent`: `stop_thread()` (stop+wait) + `super()` |
> | B9 | ✅ FIXED | `bring_to_front()` = `raise_()` + `activateWindow()` |
> | B10| ✅ FIXED | use of `window.tools_menu` (official API), no lookup by the `&Tools` title |
>
> Helpers centralized in `bal/gui/qt/window_utils.py`:
> `top_level_of`, `bring_to_front`, `stop_thread`, `show_modal`, `show_on_top`.
> Regression test: `tests/gui_fixes_test.py` (in addition to smoke + external_zip).

---

## (Historical) Original diagnosis

A **diagnosis-only** document: no line of functional code had been modified in
Phase A. It lists the graphical/lifecycle problems found in the code, their
**technical cause** and the **proposed fix**, with line references.

The two symptoms you reported:
- **(S1)** The plugin windows disappear behind the Electrum window.
- **(S2)** Some mechanisms work only after closing and "cleaning up"
  Electrum.

Both are explained by the bugs below.

---

## Summary (table)

| ID | Severity | Symptom | File:line | Short cause |
|----|----------|---------|-----------|-------------|
| B1 | 🔴 High | S1 | `dialogs.py:40,69,475` | `self.parent = parent` overrides the `QWidget.parent()` method |
| B2 | 🔴 High | S1 | `window.py:148,936`, `window.py:566` | dialogs opened with `.show()` (non-modal, not staying in the foreground) |
| B3 | 🔴 High | S2 | `plugin.py:38-42` | "Please restart Electrum" message = unhandled hot init |
| B4 | 🔴 High | S2 | `plugin.py:45,111` | dictionary key `winId` (method) instead of `winId()` (value) |
| B5 | 🟠 Medium | S2 | `window.py:664-677` | `on_close` with `except: pass` that hides cleanup errors |
| B6 | 🟠 Medium | S1/S2 | `dialogs.py:445-462` | `BalBlockingWaitingDialog` blocks the GUI thread, `processEvents` commented out |
| B7 | 🟠 Medium | S2 | `dialogs.py:48-58` | `closeEvent/hideEvent` with the thread cleanup commented out |
| B8 | 🟠 Medium | S2 | `dialogs.py:828-830` | `closeEvent` calls `thread.stop()` but not `thread.wait()` nor `super()` |
| B9 | 🟡 Low | S1 | `dialogs.py:1121-1122` | `show()+raise_()` without `activateWindow()` nor modality |
| B10| 🟡 Low | — | `plugin.py:36` (init), various | fragile multiple-window / multi-wallet handling |

---

## Detail of the problems

### B1 — `self.parent = parent` breaks Qt's window system 🔴
**Where:** `dialogs.py:40` (in `BalDialog.__init__`), repeated at `:69` and `:475`;
similar in other dialogs.

```python
self.parent = parent          # <-- PROBLEM
super().__init__(parent)
```

**Cause:** in Qt, `parent()` is a **method** of `QWidget` that returns the
parent widget. By assigning an **attribute** `self.parent`, you mask it: from
that point on `self.parent` is no longer the method but the saved value. Any
code (even inside Qt or Electrum) that expects `widget.parent()` as a method
may behave unexpectedly. In addition, the `parent` that is passed is not always
the correct **top-level window**, so the dialog is not attached hierarchically
to the Electrum window and ends up **behind** it (S1).

**Proposed fix:**
- Do not override `parent`: rename the attribute (e.g. `self._bal_parent`).
- Always pass as `parent` Electrum's **top-level window**
  (`window.top_level_window()`), so the dialog stays in the foreground relative
  to it.

---

### B2 — Dialogs opened with `.show()` instead of modally 🔴
**Where:**
- `window.py:148` `show_willexecutor_dialog` → `self.willexecutor_dialog.show()`
- `window.py:936` `preview_modal_dialog` → `self.dw.show()` (the name says
  "modal" but it uses `show()`!)
- `window.py:566` `show_transaction_real` → `d.show()`

**Cause:** `show()` opens a **non-modal, independent** window: if the `parent`
is not set correctly (see B1), the window does not stay above Electrum and
"disappears behind it" (S1). The inconsistency is noticeable: elsewhere `.exec()`
is used correctly (e.g. `init_wizard` at `window.py:144`, `settings_dialog` at
`plugin.py:254`), which is modal and stays in the foreground.

**Proposed fix:**
- For the dialogs that must stay in the foreground: use `exec()` (modal) **or**
  `show()` + correct parent + `setWindowModality(Qt.WindowModal)` +
  `raise_()` + `activateWindow()`.
- Keep the same logic of "what the dialog does" (no change of functional
  behaviour, only z-order/modality).

---

### B3 — "Please restart Electrum to activate the BAL plugin" 🔴
**Where:** `plugin.py:38-42` (`init_qt` hook).

```python
if wallet:
    window.show_warning(_("Please restart Electrum to activate the BAL plugin"), ...)
    return
```

**Cause:** when the plugin is **enabled hot** (wallet already open), the
`init_qt` hook gives up and asks for a restart instead of initializing the tabs
and menus on the already-loaded wallet. It is **the direct cause of symptom
S2**: "you have to close/restart Electrum for it to work".

**Proposed fix:**
- In `init_qt`, if there is already an open wallet, run the same initialization
  that normally happens in `load_wallet` (create `BalWindow`, tabs, menu, load
  the will) **without** requiring a restart.
- Symmetrically, handle `close_wallet` properly to tear down the tabs/menu, so
  that re-enabling/reloading does not leave dirty state.

---

### B4 — Dictionary key `winId` (method) instead of `winId()` 🔴
**Where:** `plugin.py:45` (write) and `plugin.py:111` (read).

```python
self.bal_windows[top_level_window.winId] = w   # writes with the *function* winId
...
w = self.bal_windows.get(window.winId, None)   # reads with the *function* winId
```

**Cause:** `winId` without parentheses is the **bound method**, not the window
identifier. Used as a key it "works by accident" because the same window object
produces the same bound method; but it is fragile and semantically wrong: with
more windows/wallets or after reopening, the matching can break, creating
duplicate `BalWindow` objects or failing to find the right one → inconsistent
state (contributes to S2).

**Proposed fix:**
- Use a stable, correct key, e.g. `int(window.winId())` or `id(window)`,
  **consistently** both when writing and when reading.

---

### B5 — `on_close` swallows all errors 🟠
**Where:** `window.py:664-677`.

```python
def on_close(self):
    try:
        if not self.disable_plugin:
            close_window = BalBuildWillDialog(self)
            close_window.build_will_task()
            self.save_willitems()
            self.heirs_tab.close()
            ...
    except Exception:
        pass            # <-- hides any cleanup error
```

**Cause:** if any of these operations fails, the exception is silenced:
tabs/menu are not removed, the state (`willitems`, `heirs`, tabs) stays in
memory and "dirty" until Electrum is restarted (S2).

**Proposed fix:**
- Do not silence it: log the error with `_logger`.
- Make the cleanup **robust and idempotent** (each step in a separate
  try/except with logging), so a partial failure does not block the other
  steps.
- Explicitly reset the state (`willitems={}`, references to tabs/menu set to
  `None`) at the end of `on_close`.

---

### B6 — `BalBlockingWaitingDialog` blocks the GUI thread 🟠
**Where:** `dialogs.py:445-462`.

```python
self.show()
# QCoreApplication.processEvents()   # <-- commented out
# QCoreApplication.processEvents()
try:
    task()        # runs the task ON the GUI thread -> "frozen" window
finally:
    self.accept()
```

**Cause:** after `show()` the GUI is not given time to paint itself
(`processEvents` is commented out) and then `task()` is run **blocking** the
interface thread. Result: the "Please wait" window can appear empty, fail to
repaint, and the app seems stuck (contributes to S1/the perception of a
freeze).

**Proposed fix:**
- Either run the task in a `TaskThread` (as `BalWaitingDialog` already does),
- or, if it must stay blocking, restore a `processEvents()` after `show()` so
  the window is painted before the task.

---

### B7 — `closeEvent`/`hideEvent` with the thread cleanup commented out 🟠
**Where:** `dialogs.py:48-58` (`BalDialog`).

```python
def closeEvent(self, event):
    self._stopping = True
    #if self.thread:
    #    self.thread.stop()      # <-- disabled
    super().closeEvent(event)
```

**Cause:** when the dialog closes, any active threads are **not** stopped. They
keep running in the background, can write to already-destroyed widgets or hold
resources/connections → erratic behaviour until a restart (S2).

**Proposed fix:**
- Safely restore stopping the threads: `if self.thread:
  self.thread.stop(); self.thread.wait()` with a guard on `None`.

---

### B8 — `BalBuildWillDialog.closeEvent` incomplete 🟠
**Where:** `dialogs.py:828-830`.

```python
def closeEvent(self, event):
    self._stopping = True
    self.thread.stop()
    # missing self.thread.wait() and missing super().closeEvent(event)
```

**Cause:** `stop()` signals the stop but does not wait for the thread to finish
(`wait()`), and `super().closeEvent(event)` is not called: the close event is
not propagated correctly. Possible orphan threads and windows that do not close
cleanly.

**Proposed fix:**
- `self.thread.stop(); self.thread.wait(); super().closeEvent(event)` with a
  guard on `self.thread is None`.

---

### B9 — `show()+raise_()` without `activateWindow()`/modality 🟡
**Where:** `dialogs.py:1121-1122` (e.g. `WillExecutorDialog`/detail).

```python
self.show()
self.raise_()
# missing self.activateWindow(); no modality set
```

**Cause:** `raise_()` raises the window in the stack but on some window
managers (including Windows) without `activateWindow()` it does not receive
focus and may still end up behind. Without modality, the user can go back to the
main window leaving the dialog hidden.

**Proposed fix:**
- Add `self.activateWindow()` after `raise_()`, and consider
  `setWindowModality(Qt.WindowModal)` where it makes sense.

---

### B10 — Fragile multiple-window / multi-wallet handling 🟡
**Where:** `plugin.py:30-62` (`init_qt`), `get_window` (`plugin.py:109-115`).

**Cause:** the `bal_windows` map and the menu attachment rely on assumptions
(B4) and on iterating the menubar's children by name (`"&Tools"`), which is
sensitive to **localization** (you use `Locale: Italian_Italy`!). If the menu
is not named exactly `&Tools` in the current language, the attachment can fail
silently.

**Proposed fix:**
- Use the official `window.tools_menu` API (already used in `init_menubar`,
  `plugin.py:79`) instead of looking up the menu by its translated title.
- Unify the creation/lookup of `BalWindow` on a stable key (B4).

---

## Proposed correction strategy (for Phase B/C)

In order to **not change the operating logic** and reduce the risks, I propose
to introduce a **single centralized point** for window management (a small
helper, e.g. `gui/qt/window_utils.py`) with functions such as:

- `show_modal(dialog)` → sets the correct parent, modality, `exec()`.
- `show_on_top(dialog)` → `show()` + `raise_()` + `activateWindow()` for the
  few cases that must stay non-modal.

And then replace the scattered `.show()`/`.exec()` calls with these functions.
Advantages:
- the **business logic stays intact** (what the dialog does does not change);
- only the "how" it is shown/closed is touched;
- easier to test and to review (small, localized diff).

### Recommended order
1. **B3 + B4** (hot init + window key): fix the root of S2.
2. **B1 + B2 + B9** (parent/modality/z-order): fix S1.
3. **B5 + B7 + B8** (robust cleanup + threads): close the remaining S2 issues.
4. **B6 + B10** (waiting dialog + localized menus): polish.

---

## What is needed from you for Phase B/C
- Confirmation that I may modify the **GUI behaviour** (parent, modality,
  cleanup, hot init) while keeping the business logic unchanged.
- Testing on **Electrum portable Windows** after each group of fixes, with a
  description/screenshot of what happens (opening dialogs, hot enabling,
  closing the wallet).

> Note: bugs B1–B10 exist **identically in the original** — this refactor
> preserved them faithfully (that was the goal of the previous phase). Phase B/C
> fixes them.
