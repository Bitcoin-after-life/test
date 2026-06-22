# CHANGELOG

This file records the work done on the BAL (Bitcoin After Life) Electrum
inheritance plugin, one numbered entry per task.

Each entry lists: task title, date, files changed, and outcome
(DONE / UNRESOLVED). It is meant to make it easy to review what was done and,
if needed, to roll back to a previous state.

---

<!-- New entries are added below, newest last. -->

## 1. A1 - Remove block-height locktimes (timestamps only)

**Date:** 2026-06-22

**Goal (OPUS plan, Group A / A1):** Remove block-height locktimes from the
codebase so that ALL ordering and comparison use UNIX timestamps only. The
`NLOCKTIME_BLOCKHEIGHT_MAX` guard is intentionally KEPT, because it forces every
locktime to be a timestamp (it is a safety "bouncer", not block-height ordering).

**What changed:**

- `bal/core/util.py`
  - `str_to_locktime`: removed the `"b"` (block) suffix; only `"d"` (days) and
    `"y"` (years) relative suffixes are accepted now.
  - `parse_locktime_string`: removed the block-height (`"<n>b"`) branch. The
    `w` (wallet) argument is kept only for call-site compatibility (now unused).
  - `int_locktime`: removed the `blocks` argument (and the `blocks * 600`
    seconds-per-block conversion). New signature:
    `int_locktime(seconds=0, minutes=0, hours=0, days=0)`.
  - `chk_locktime`: signature changed from
    `(timestamp_to_check, block_height_to_check, locktime)` to
    `(timestamp_to_check, locktime)`; comparison is now purely timestamp-based.
  - `anticipate_locktime`: removed the `blocks` argument and the block-height
    branch; it now only moves a timestamp earlier (by hours/days). The Windows
    overflow clamp and the `out < 1` clamp are kept.
  - Expanded the `LOCKTIME_THRESHOLD` comment to explain the timestamp-only model.

- `bal/core/will.py`
  - Removed the `from electrum.bitcoin import NLOCKTIME_BLOCKHEIGHT_MAX` import
    (it was only used by the dead block-height branch).
  - `check_will`: removed the `block_to_check` parameter.
  - `is_will_valid`: removed the `block_to_check` parameter.
  - `check_will_expired`: removed the `block_to_check` parameter and the
    `if locktime <= NLOCKTIME_BLOCKHEIGHT_MAX:` block-height branch; expiry is
    now decided purely by comparing the locktime against `timestamp_to_check`.
  - Added/expanded docstrings on the three methods above.
  - KEPT `utxo.block_height` in the coinbase-maturity check (line ~399): that is
    a legitimate Electrum UTXO attribute, NOT a BAL locktime concept.

- `bal/gui/qt/window.py`
  - `check_will`: stopped passing the removed `block_to_check` argument.
  - `init_class_variables`: removed the dead `locktime_blocks`, `current_block`
    and `block_to_check = 0` assignments (replaced by an explanatory comment).

- `bal/gui/qt/widgets.py`
  - `LockTimeRawEdit`: removed the `"b"` (block) suffix handling from
    `replace_str`, `numbify` and the `isblocks` flag; only `"d"` and `"y"` remain.
  - Added a clarifying comment on the kept guard
    `LockTimeDateEdit.min_allowed_value = NLOCKTIME_BLOCKHEIGHT_MAX + 1`.

- Tests updated for the new signatures / behaviour:
  - `tests/test_core_util.py`: `test_str_to_locktime` (now expects `"144b"` to be
    rejected), `test_int_locktime` (no `blocks`), `test_chk_locktime` (2-arg),
    `test_anticipate_locktime` (no `blocks`). Added `import pytest`.
  - `tests/test_core_will_extra.py`: `test_check_will` now calls the 4-arg
    `check_will`.
  - `tests/test_anticipate_past_locktime.py`: `chk_locktime` call updated to 2-arg.
  - `tests/test_gui_widgets.py`: `test_locktime_raw_edit_replace_str` now expects
    `"b"` to be left untouched.

**Verification:**
- `ruff check` on all modified production files: no new errors introduced
  (`bal/core/util.py` is clean; pre-existing baseline warnings unchanged).
- Full test suite: `190 passed`
  (`tests/test_core_*.py tests/test_gui_*.py tests/test_anticipate_past_locktime.py`).

**Dormant block-based config kept on purpose (owner decision: keep, comment why):**
- `bal/core/plugin_base.py` still defines two block-based stored configs that
  are no longer read anywhere after A1:
  - `LOCKTIME_BLOCKS` (`"bal_locktime_blocks"`)
  - `LOCKTIMEDELTA_BLOCKS` (`"bal_locktimedelta_blocks"`)
  Per the owner's decision they are KEPT in place (dormant) to avoid touching
  persisted config keys that may already exist in some users' saved settings.
  An explanatory comment was added above each line stating they are unused now
  and why they are intentionally retained.

**Outcome:** DONE.

---

## 2. A2 - Status definitions, colours and VALID rules (MEMPOOL rename + UPDATED)

**Date:** 2026-06-22

**Goal (OPUS plan, Group A / A2):** Define the inheritance statuses, their
colours and their VALID rules. The fine moment-by-moment assignment of
ANTICIPATED / UPDATED will be validated by the Group E tests; A2 sets up the
state machine and colours.

**Status meanings (for reference):**
- **ANTICIPATED** - locktime anticipated by 1 day vs a pre-existing tx with the
  same heirs; the tx STAYS VALID.
- **REPLACED** - an input is spent by a new tx with a LOWER locktime; loses
  VALID, cascades to children.
- **INVALIDATED** - an input is spent by a mempool/confirmed tx and the previous
  tx is no longer in the will; loses VALID.
- **UPDATED** (new) - the tx was spendable AND valid, and a new tx replaces it
  keeping the SAME locktime and SAME heirs; STAYS VALID.
- **MEMPOOL** (renamed from PENDING) - the tx has been seen in the Electrum
  mempool; loses VALID.
- **CONFIRMED** - the tx is confirmed in the blockchain; loses VALID.

**What changed:**

- `bal/core/will.py`
  - Renamed the status key `PENDING` -> `MEMPOOL` everywhere
    (`STATUS_DEFAULT`, `set_status`, and the three `get_status(...)` reads in
    `check_invalidated` / `search_rai`). Visible label: "Mempool".
  - Added the new status `UPDATED` to `STATUS_DEFAULT` (label "Updated").
  - `set_status`: VALID rules now documented and updated:
    - `INVALIDATED`, `REPLACED`, `CONFIRMED`, `MEMPOOL` -> clear VALID.
    - `ANTICIPATED` and `UPDATED` -> KEEP VALID (intentionally NOT in the
      clear-VALID list).
    - `CONFIRMED`, `MEMPOOL` -> clear INVALIDATED (unchanged behaviour).
  - Added a full docstring to `set_status` explaining all side effects.
  - **Backward-compatibility migration (owner decision "Modo B"):** in
    `__init__`, a will saved by an older plugin version that stores the legacy
    `PENDING` flag is migrated to `MEMPOOL`, so no state is lost on load. The new
    `MEMPOOL` key wins if both are present.

- `bal/gui/qt/theme.py`
  - Renamed the `PENDING` colour entry to `MEMPOOL` (#ffce30 yellow, unchanged).
  - Added `UPDATED` -> #800080 (violet) in the priority list, placed after
    REPLACED and before CONFIRMED/MEMPOOL.

- Tests:
  - `tests/test_gui_theme.py`: renamed the pending colour test to
    `test_color_mempool`, updated the "overrides lower" test, and added
    `test_color_updated` (#800080).
  - `tests/test_core_will_extra.py`: renamed `test_check_invalidated_pending`
    -> `test_check_invalidated_mempool`; updated `test_check_will`. Added new
    tests: `test_legacy_pending_migrates_to_mempool`,
    `test_new_mempool_wins_over_legacy_pending`, `test_updated_status_keeps_valid`,
    `test_anticipated_status_keeps_valid`, `test_mempool_status_clears_valid`.

**Verification:**
- `ruff check` on modified production files: no new errors introduced.
- Full test suite: `196 passed`
  (`tests/test_core_*.py tests/test_gui_*.py tests/test_anticipate_past_locktime.py`).

**Note:** the exact moment ANTICIPATED / UPDATED get assigned during real flows
is validated by the Group E tests (per the owner's decision).

**Outcome:** DONE.

---

## 3. A3 - "Move date earlier (anticipate)" must not invalidate

**Date:** 2026-06-22

**Goal (OPUS plan, Group A / A3):** (a) explain the inheritance-options table;
(b) make "Move date earlier (anticipate)" only anticipate (rebuild), NOT
invalidate; (c) regenerate a clearer English table.

**Owner decisions captured during DISCOVER:**
- D1 = the case to handle is the user MANUALLY setting a smaller locktime in the
  wizard (e.g. from "90 days" to "30 days").
- D2 = case A1 (smaller locktime, still in the future): plain REBUILD with the
  new locktime, NEVER invalidate, even if the tx was already signed/sent.
- D3 = the genuine-expiry case (new date in the past) keeps invalidating; only
  the documentation is wrong and must be fixed.
- Chosen path = X (fix BOTH code clarity and documentation).

**Analysis result (verified with tests, not assumed):**
The core logic was ALREADY correct for D2. A diagnostic confirmed:
- Case A1 (smaller, future locktime, signed OR unsigned) ->
  `HeirNotFoundException` (a rebuild signal), NEVER `WillExpiredException`. So no
  on-chain invalidation happens. This already matches the owner's decision.
- Case A2 (locktime in the past) -> `WillExpiredException` -> invalidation. This
  is a genuine expiry and is intentionally kept.

So the real defect was in the DOCUMENTATION (the table wrongly claimed
"anticipate -> always invalidate"). No behavioural code change was needed.

**What changed:**

- `bal/core/will.py`
  - Added a clarifying comment in `check_willexecutors_and_heirs` explaining that
    anticipating to a FUTURE date is a plain rebuild that NEVER invalidates (even
    when signed/sent), while only a date in the PAST is a genuine expiry handled
    by `check_will_expired`. No logic change.

- `tests/test_anticipate_manual_locktime.py` (new)
  - Permanent regression tests guaranteeing:
    `test_a1_anticipate_unsigned_triggers_rebuild_not_invalidate`,
    `test_a1_anticipate_signed_triggers_rebuild_not_invalidate` (A1 = rebuild, no
    invalidate, signed or not), and
    `test_a2_past_locktime_is_genuinely_expired` (A2 = WillExpired kept).

- `docs/inheritance-options.md`
  - Split the "Move date EARLIER" row into two: "still in the future" (rebuild,
    no fee, signed or not) vs "into the past" (invalidate, WillExpired).
  - Rewrote the "why anticipate" notes (anticipate is safe, opposite of postpone).
  - Fixed the quick-reference summary table and the Golden Rules accordingly.
  - Updated the status section to match A2 (MEMPOOL instead of PENDING; added
    ANTICIPATED/UPDATED keep-VALID rows) and rewrote the colour table in the exact
    priority order used by `gui/qt/theme.py` (incl. UPDATED #800080 violet).
  - Updated the Mermaid decision flow to the corrected branching.

- `docs/inheritance-options.html`
  - Mirrored all the above .md changes (status table, colour table with new pill
    colours, section 4.1 table + notes, summary table, Golden Rules, Mermaid).
  - Bumped the document version footer to v0.3.4.

- `docs/images/inheritance-flow.svg`
  - Reworked the "anticipate" branch: the decision is now "new date in the PAST?"
    -> invalidate (WillExpired); otherwise "moved earlier? (anticipate)" ->
    rebuild only, NEVER invalidates. Bumped subtitle to v0.3.4. Verified the SVG
    is still well-formed XML.

**Verification:**
- `ruff check` on changed Python files: no new errors introduced.
- Full test suite: `199 passed`
  (`tests/test_core_*.py tests/test_gui_*.py tests/test_anticipate_past_locktime.py
  tests/test_anticipate_manual_locktime.py`).

**Outcome:** DONE.

---

## 4. A2 follow-up - UPDATED status colour lightened

**Date:** 2026-06-22

**Goal:** After testing the v0.3.4 build, the original UPDATED colour
(`#800080`, dark violet) was reported as too dark to read in the list.
Lighten it to a more readable light violet while keeping it distinct from
MEMPOOL (yellow `#ffce30`).

**What changed:**

- `bal/gui/qt/theme.py`
  - UPDATED colour changed from `#800080` (dark violet) to `#b266b2`
    (light violet) in `_STATUS_COLOR_PRIORITY`. Priority position unchanged
    (after REPLACED, before CONFIRMED/MEMPOOL).

- `docs/inheritance-options.md` / `docs/inheritance-options.html`
  - Updated the colour table and the `.pill.violet` CSS to `#b266b2`
    ("light violet").

- `tests/test_gui_theme.py`
  - `test_color_updated` now asserts `#b266b2`.

**Verification:**
- Full test suite: see run below.

**Outcome:** DONE.

---

## 5. B1 + B2 - Guided wizard verification and Auto-sign on Check

**Date:** 2026-06-22

**Goal (OPUS plan, Group B):**
- **B1:** the "Create your will" button should open the step-by-step guided
  wizard.
- **B2:** the "Check" action should be able to automatically sign and broadcast
  the will, controlled by an "Auto-sign" checkbox in the settings dialog,
  default ON.

**B1 - finding (no code change needed):**
- The "Create your will" toolbar button is already wired to
  `BalWindow.init_wizard`, which opens `BalWizardDialog` - the step-by-step
  wizard (Heirs -> Locktime & Fee -> Will-Executor download -> Will-Executor ->
  build will). This already matches the requested behaviour, so no code change
  was required for B1.

**B2 - what changed:**

- `bal/core/plugin_base.py`
  - Added a new persisted setting `AUTO_SIGN`
    (`BalConfig(config, "bal_auto_sign", True)`), default ON, with an
    explanatory comment.

- `bal/gui/qt/plugin.py` (`settings_dialog`)
  - Added an "Auto-sign on Check" checkbox bound to `AUTO_SIGN`, with a tooltip
    explaining that the wallet password is requested only if the wallet is
    encrypted. Re-numbered the grid rows so the new checkbox (row 3) does not
    overlap the existing widgets; also fixed the "Event sescription" ->
    "Event description" label typo.

- `bal/gui/qt/window.py`
  - Added `auto_sign_and_broadcast()`: signs the will and, only after signing
    succeeds, broadcasts it to the will-executors. It reuses
    `ask_password_and_sign_transactions(callback=...)`; the existing
    `get_wallet_password()` already prompts only for encrypted wallets, so a
    password-less wallet is handled with no prompt.

- `bal/gui/qt/lists.py` (`check`)
  - After the server check, when `AUTO_SIGN` is enabled, calls
    `auto_sign_and_broadcast()`. When the setting is OFF the behaviour is
    unchanged (check only).

- `tests/test_group_b_auto_sign.py` (new)
  - 5 tests: AUTO_SIGN defaults ON and can be disabled; sign happens before
    broadcast; encrypted wallet prompts for the password; un-encrypted wallet
    signs and broadcasts with no prompt.

**Verification:**
- `ruff check` on changed Python files: no new errors introduced
  (new test file is ruff-clean).
- Full test suite: `204 passed`.

**Outcome:** DONE.

---

## 6. B2 follow-up - Remove duplicate broadcast and make broadcast one-shot

**Date:** 2026-06-22

**Problems reported after testing the v0.3.4 Group B build:**
1. The "Building Will" dialog still showed "Next step (manual): press
   'Broadcast'..." even though the will had already been broadcast.
2. A second, duplicate popup ("Informazioni") repeated the same manual hint.
3. When several transactions were broadcast to different will-executors and one
   server failed, the plugin tried to retry the broadcast, which could loop
   forever against a server that never answers.

**Root cause:**
- `lists.py check()` first runs `BalBuildWillDialog.build_will_task()` (which
  already checks, signs and broadcasts), and then a second
  `auto_sign_and_broadcast()` was triggered - a duplicate sign/broadcast cycle.
- The "Building Will" dialog always printed the manual "press Sign/Broadcast"
  hint and a follow-up popup, which is wrong when broadcasting is automatic.
- `loop_push()` used a `retry` flag and raised `Exception("retry")` whenever any
  will-executor failed.

**What changed (Fix A - no duplicate broadcast / no wrong manual hint):**

- `bal/gui/qt/lists.py`
  - `check()` no longer calls `auto_sign_and_broadcast()`. Signing and
    broadcasting are already done by `build_will_task()`; the duplicate cycle
    was removed (replaced by an explanatory comment).

- `bal/gui/qt/window.py`
  - Removed the now-unused `auto_sign_and_broadcast()` method.

- `bal/gui/qt/dialogs.py`
  - `_show_next_steps_hint()` returns early (no in-dialog hint, no popup) when
    `AUTO_SIGN` is ON, because the will has already been signed and broadcast.
    When `AUTO_SIGN` is OFF the previous manual hints are kept.

**What changed (Fix B - one-shot broadcast, no endless retry):**

- `bal/gui/qt/dialogs.py` (`loop_push`)
  - Removed the `retry` flag, the `retry_flag["value"] = True` assignments and
    the final `if retry: raise Exception("retry")`. The broadcast now contacts
    each selected will-executor ONCE: successful transactions become PUSHED,
    failed/timed-out ones are left as PUSH_FAIL and simply skipped (no automatic
    retry). The user can broadcast a failed transaction manually later.
  - Note: `get_willexecutor_transactions` already excludes PUSHED transactions,
    so the successful ones are never re-sent on a later run.

- `tests/test_group_b_auto_sign.py`
  - Rewritten for the new behaviour: AUTO_SIGN default/disable; manual hint
    suppressed when AUTO_SIGN ON and shown when OFF; PUSHED transactions are not
    re-collected for broadcast (one-shot), while not-yet-PUSHED ones are.

**Verification:**
- `ruff check` on changed Python files: no new errors introduced
  (new test file is ruff-clean).
- Full test suite: `206 passed`.

**Outcome:** DONE.
