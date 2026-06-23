# HANDOFF — BAL Electrum Plugin (Bitcoin After Life)

> **Purpose of this file:** allow ANY new chat / AI model to resume this project
> WITHOUT losing context. If you are a new assistant, READ THIS FILE FIRST,
> then read `CHANGELOG.md` and `.agent_memory_tasks.md`.
>
> **Chat language is Italian, but ALL output (code, comments, UI text, docs,
> CHANGELOG, commit messages) MUST be in ENGLISH.** The user is NOT a programmer.

---

## 1. MANDATORY STANDING RULES (apply to EVERY task, never skip)

- **R1 — LANGUAGE:** Italian is ONLY for chatting. ALL deliverables in ENGLISH
  (code, docstrings, comments, UI strings, docs, CHANGELOG, commit messages).
- **R2 — DOCUMENTED CODE:** every method/class needs a docstring + explanatory
  comments. When a non-obvious design choice is made, explain WHY in a comment.
- **R3 — NEVER INVENT:** if anything is missing or unclear, STOP and ask the user
  clear, simple questions (he is not a programmer). Be "100% sure" before acting.
- **R4 — HUMAN CHECKPOINT:** before writing/modifying code, show the PLAN and WAIT
  for the user's explicit "OK".
- **METHOD per task:** DISCOVER → PLAN (wait OK) → EXECUTE → VERIFY → ITERATE
  (max 8 attempts, then declare "UNRESOLVED").
- **LOG:** a single `CHANGELOG.md` in English, one numbered entry per task.
- **ZIP-FIRST:** always deliver a test ZIP for the user to try BEFORE committing
  plugin code. Commit ONLY after explicit user confirmation.
- Always run `ruff` + the official test suite before committing/reporting/zipping.

---

## 2. PROJECT OVERVIEW

- Electrum **4.7.2** Qt (PyQt6) inheritance plugin.
- External zip plugin id: `electrum_external_plugins.bal`.
- **zipimport caches the plugin → the user MUST fully restart Electrum after
  installing a new ZIP** (always remind him).
- Repo: `Bitcoin-after-life/test` (GitHub). Working branch: `genspark_ai_developer`.
- Main code lives under `bal/`. Tests under `tests/`. Electrum source vendored in
  `electrum-src/` (read-only reference).

### Version files (keep ALL FOUR in sync on every release)
- `bal/manifest.json`  → `"version"`
- `bal/__init__.py`    → `__version__`
- `bal/core/plugin_base.py` → `__version__ = "..."  # AUTOMATICALLY GENERATED DO NOT EDIT`
- `bal/VERSION`
- **Current released version: 0.3.9**

---

## 3. BUILD / TEST / RELEASE COMMANDS

### Build the ZIP (clear caches first)
```bash
cd /home/user/webapp
find bal -name "__pycache__" -type d -exec rm -rf {} + ; find bal -name "*.pyc" -delete
python3 build_zip.py bal-electrum-plugin-vX.Y.Z.zip   # builds 37 files
```

### Run the full test suite (must stay GREEN: 239 passed)
```bash
cd /home/user/webapp
QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src python3 -m pytest \
  tests/test_core_*.py tests/test_gui_*.py \
  tests/test_anticipate_past_locktime.py tests/test_anticipate_manual_locktime.py \
  tests/test_group_b_auto_sign.py tests/test_group_c_settings.py \
  tests/test_group_d_alarms.py tests/test_group_e_mock_giovanna7.py -q
```

### Ruff (only PRE-EXISTING noise is acceptable)
```bash
cd /home/user/webapp && ruff check bal/<changed files>
```
Pre-existing warnings that are NOT your fault and can be ignored:
- `F401/F403/F405` star-import noise (`from .common import *`).
- `F841` at: `will.py:151`, `dialogs.py:615` (`except NoHeirsException as e`),
  `lists.py:185`, `lists.py:272`.
- `E501` long lines in several pre-existing spots.

### Git / PR / Release workflow
- `setup_github_environment` first. If `git push` fails with
  "Invalid username or token", CALL `setup_github_environment` AGAIN, then retry.
- Token for API calls:
  `TOKEN=$(sed -n 's#https://\([^:]*\):\([^@]*\)@.*#\2#p' ~/.git-credentials | head -1)`
- Repo for API: `Bitcoin-after-life/test`.
- Releases published so far: v0.3.6, v0.3.7, v0.3.8, **v0.3.9 (latest)**.
- Attach the ZIP as a release asset via the uploads API.

---

## 4. CURRENT STATE (as of v0.3.9, COMMITTED + RELEASED)

v0.3.9 is merged to `main` (PR #11) and released with the ZIP attached.
sha256 of the released ZIP: `cd52b6f5e6276fb707ea4bf477a00bd0469dfd88960282fb74c219ee0f5f4292`.

What shipped in v0.3.9 (TASK A/B/C/D + regression fix A3):
- **A** clearer "Will expired" message: shortened will id (8+8 chars via
  `Will._short_will_id`) + readable UTC date (`Will._format_locktime`) instead of
  raw UNIX timestamp; shown ORANGE (warning) not RED (error) in the wizard.
- **A2** message split on two lines via `<br>` (rendered as HTML by `msg_warning`).
- **B** History labels (text only): inheritance tx → `BAL Inheritance transaction`;
  invalidate tx → `BAL Invalidate transaction`. Colours = Electrum defaults
  (Electrum colours outgoing tx descriptions red by itself, history_list.py:193-196).
- **C** "No will-executor TX" checkbox in plugin Settings (`plugin.py`), bound to
  existing `NO_WILLEXECUTOR` config (default ON, line plugin_base.py:193), with help
  text "Create a will that does not require a Will-executor; it can be saved, for
  example, on a USB stick, and a copy can be given to the heirs." Included in reset.
- **D** wizard button "Create your will" → "Build Your Will" (lists.py:473).
- **A3 regression fix:** adding an heir to an expired will via the wizard no longer
  failed to invalidate. Implemented a `"invalidate_classic"` signal returned from
  `task_phase1` and handled in `on_success_phase1` (dialogs.py) that closes the
  wizard and shows a popup telling the user to use `Tools → Invalidate`.
  **NOTE: this popup text is about to be CHANGED — see the pending task below.**

---

## 5. PENDING TASK (NOT STARTED) — UNIFY THE INVALIDATE PROCEDURE

### Problem the user reported
There are currently TWO different "invalidate" procedures, and the user wants ONE
identical behaviour for BOTH the **CHECK button** and the **WIZARD**.

- **PROCEDURE 1 "classic/manual"** = `window.py::invalidate_will` (line ~695):
  waiting dialog → "please sign and broadcast" popup → CLASSIC Electrum tx window
  (Sign/Broadcast buttons) → **SETS** history label "BAL Invalidate transaction"
  (line ~704). Used by: Tools→Invalidate menu (lists.py:468→571), a dialog button
  (dialogs.py:1356), the on-close/postpone paths (window.py:539,576,614).
  **This window opens correctly IN FRONT** (user confirmed) because nothing else
  is closing at the same time.
- **PROCEDURE 2 "automatic"** = `dialogs.py::invalidate_task` (line ~902):
  password prompt inside the wizard → sign + auto-broadcast
  (`loop_broadcast_invalidating`, line ~729) → **does NOT set the history label**.
  Used by the CHECK button and the FIRST `WillExpiredException` handler in
  `task_phase1` (dialogs.py:594 → `return None, Will.invalidate_will` at ~598,
  which makes `on_success_phase1` see `have_to_sign is None` → password prompt).

### CHECK button flow (important)
`lists.py:545 check()` → `BalBuildWillDialog(...).build_will_task()` →
`task_phase1` → `on_success_phase1`. **It is the SAME engine as the wizard.**

### FINAL REQUIREMENT (user-approved, OPTION A refined)
Make CHECK and WIZARD behave IDENTICALLY for an expired will:
1. First show a **WARNING popup** (REMOVE the old "use the top-right menu
   Tools → Invalidate" wording).
2. Then **AUTOMATICALLY open the CLASSIC Electrum sign window** (PROCEDURE 1,
   `window.py::invalidate_will`) so the label is set and the user can Sign + Broadcast.
3. Sequence: warning popup → user clicks OK → classic sign window opens BY ITSELF,
   IN FRONT.

### APPROVED WARNING POPUP TEXT (verbatim, English per R1)
```
Your will has expired and must be invalidated before it can be rebuilt.
A transaction window will now open:
please SIGN and then BROADCAST it to invalidate your old will.
After the invalidation is confirmed, press the Check button to finish the will.
```
(The user wrote "SIGN and then  BROADCAST" with a double space — normalize to a
single space unless he objects.)

### Implementation approach (agreed in principle; still needs final PLAN + OK)
- Route the expired cases (FIRST handler at ~594, the `invalidate_classic` block,
  and therefore the CHECK button) through ONE shared helper that:
  (a) closes the CHECK/wizard dialog FIRST,
  (b) shows the warning popup,
  (c) then calls `self.bal_window.invalidate_will()` (PROCEDURE 1) LAST, so the
      classic window is the last thing opened and stays in front.
- Drop the use of PROCEDURE 2 (`invalidate_task`) for the expired case.
- **KNOWN RISK / why this is delicate:** earlier attempts to auto-open the classic
  window *while the wizard was closing* put it BEHIND the main wallet window on the
  user's machine (Windows focus/stacking). The fix is to make sure NOTHING closes
  AFTER the classic window opens (close the dialog first, open the tx window last).
  `Tools → Invalidate` works perfectly precisely because no other window is closing.
- The user has hinted he may add MORE requirements before this is implemented, so
  CONFIRM the full scope before coding.

### Status: WAITING. Do NOT code yet. Build full PLAN → wait OK (R4) → zip-first.

---

## 6. KEY FILE / LINE REFERENCES (verify line numbers, they drift)

- `bal/core/will.py`
  - `check_will()` order (line ~561): `check_invalidated` → `check_will_expired`
    (raises `WillExpiredException`) → `search_rai` (raises `HeirNotFoundException`).
  - `invalidate_will()` static (line ~394) builds the invalidation PartialTransaction.
  - `_short_will_id` / `_format_locktime` helpers + the expired message (with `<br>`).
- `bal/gui/qt/dialogs.py`
  - `BalBuildWillDialog` is the CHECK + wizard engine.
  - `build_will_task()` (~530) starts `task_phase1`.
  - `task_phase1()` (~542): first `check_will()`; first `WillExpiredException`
    handler (~594) → `return None, Will.invalidate_will(...)`; `NotCompleteWill`/
    `HeirNotFound` → `have_to_build`; inner `check_will()`; inner `WillExpiredException`
    (~659) → currently returns `"invalidate_classic", None`.
  - `on_success_phase1()` (~924): unpacks `(have_to_sign, tx)`. If
    `have_to_sign == "invalidate_classic"` → shows popup. If `have_to_sign is None`
    → password prompt "Invalidate your old will" → `invalidate_task` (PROCEDURE 2).
  - `invalidate_task()` (~902) + `loop_broadcast_invalidating()` (~729): PROCEDURE 2.
  - `QTimer` is available via `from .common import *` (defined in common.py:53).
- `bal/gui/qt/window.py`
  - `invalidate_will()` (~695): PROCEDURE 1 (the "good" one). Sets label at ~704.
  - `show_transaction_real()` (~656) uses `show_on_top(d, modal_to_window=False)`.
  - on-close/postpone expired handling at ~539, ~576, ~614.
- `bal/gui/qt/lists.py`
  - `check()` (~545): the CHECK button. `invalidate_will()` (~571). Menu actions
    "Check"/"Invalidate" at ~467/468. Wizard button "Build Your Will" at ~473.
- `bal/gui/qt/plugin.py`: settings dialog; "No will-executor TX" checkbox + reset.
- `bal/gui/qt/window_utils.py`: `show_on_top` (~100), `bring_to_front` (~52),
  `show_modal` (~86).
- `bal/gui/qt/common.py`: `add_widget` helper (~98); imports `QTimer`, `Qt`, etc.

---

## 7. HOW TO RESUME IN A NEW CHAT (any model)

Tell the new assistant:
> "Read `/home/user/webapp/HANDOFF.md`, then `CHANGELOG.md` and
> `.agent_memory_tasks.md`. Follow rules R1–R4 and zip-first. The next task is the
> 'unify invalidate procedure' task in HANDOFF.md section 5 — present the PLAN and
> wait for my OK before coding."

Everything needed (rules, state, pending task, build/test commands, file map) is in
this file. The real work is safe in Git (PR #11, release v0.3.9) and in CHANGELOG.md.
