# HANDOFF — BAL (Bitcoin After Life) Electrum plugin

> Purpose: let ANY future AI assistant (Claude or another model, more advanced
> or cheaper) resume work on this project with full context, without having to
> re-discover the codebase. Read this file FIRST, then `CHANGELOG.md` and
> `.agent_memory_tasks.md`.

---

## 0. TL;DR — what this project is

- **Product:** BAL ("Bitcoin After Life") — an inheritance plugin for the
  **Electrum 4.7.2** Bitcoin wallet (Qt / **PyQt6**).
- **Form:** external **ZIP plugin** (not bundled in Electrum). The user
  installs the ZIP from Electrum's plugin manager.
- **What it does:** lets a wallet owner pre-build, sign and (later) broadcast
  Bitcoin transactions that pay one or more **heirs** after a chosen **date**
  (a future UNIX-timestamp `nLockTime`). Optional **will-executors** (remote
  services) can be paid a fee to broadcast the inheritance when due. The owner
  periodically proves they are alive ("check-alive"); if the deadline passes,
  the inheritance becomes spendable.
- **Current version:** see `bal/VERSION` (last shipped: **0.4.7**).

---

## 1. MANDATORY working rules (the owner set these — always follow them)

These are non-negotiable. They come from the owner directly.

- **R1 — LANGUAGE.** The CHAT language with the owner is **Italian**. But ALL
  *output* — source code, comments, docstrings, UI strings, docs, `CHANGELOG.md`,
  commit messages, this handoff — must be in **ENGLISH**.
- **R2 — DOCUMENTED CODE.** Every method/class gets a docstring + explanatory
  comments. Always explain *WHY* for any non-obvious decision.
- **R3 — NEVER INVENT.** If something is missing or unclear, STOP and ask the
  owner clear, simple questions. **The owner is NOT a programmer** — explain in
  plain language, avoid jargon. Be "100% sure" before acting.
- **R4 — HUMAN CHECKPOINT.** Before writing/modifying code, present the PLAN
  and WAIT for an explicit "OK" from the owner.
- **METHOD:** DISCOVER → PLAN (wait for OK) → EXECUTE → VERIFY → ITERATE
  (max ~8 attempts per problem, then step back and ask).
- **LOG:** keep a single `CHANGELOG.md`, in English, **one numbered entry per
  task** (newest entry appended at the END of the file).
- **ZIP-FIRST.** Deliver a test ZIP and let the owner test it BEFORE committing.
  **Commit ONLY after the owner explicitly confirms the ZIP works.**
- **ALWAYS** run `ruff` + the official test suite before committing / reporting
  / zipping.
- **CREDIT-SAVING (important).** The owner is low on funds. Minimize token /
  credit usage: report brief summaries (do NOT paste whole modified code
  blocks back), and batch work into a single ZIP/test cycle where possible.

---

## 2. Repository layout (what lives where)

```
bal/                         <- the plugin package (this is what ships in the ZIP)
  __init__.py                <- __version__ (one of 4 version files)
  VERSION                    <- plain-text version (one of 4 version files)
  manifest.json              <- plugin manifest, "version" field (one of 4)
  core/
    plugin_base.py           <- __version__ "AUTOMATICALLY GENERATED" (one of 4)
    heirs.py                 <- HEIRS + transaction building (prepare_lists,
                                prepare_transactions, buildTransactions). CORE LOGIC.
    will.py                  <- Will/WillItem, validation (check_amounts, check_will),
                                exceptions (AmountException, WillExpiredException, ...).
    willexecutors.py         <- remote will-executor services handling.
    util.py                  <- locktime parsing/most helpers (timestamps only).
  gui/qt/
    common.py                <- shared imports; every gui module does
                                `from .common import *`. Add new shared imports HERE.
    dialogs.py               <- the big build/sign/broadcast dialog
                                (BalBuildWillDialog, task_phase1/2), wizard glue.
    widgets.py               <- WillSettingsWidget + wizard widgets/labels.
    window.py                <- BalWalletWindow (build_will, check_will, get_transactions).
    lists.py, calendar.py, theme.py, window_utils.py, ...
tests/                       <- pytest suite (see run command below).
electrum-src/                <- a copy of Electrum source, used ONLY for tests
                                (PYTHONPATH=electrum-src). NOT shipped in the ZIP.
build_zip.py                 <- builds the shippable ZIP (37 files).
CHANGELOG.md                 <- numbered task log (English).
.agent_memory_tasks.md       <- terse internal memory notes per task batch.
HANDOFF.md                   <- this file.
```

---

## 3. How to build, test and lint

Run everything from `/home/user/webapp`.

**Full test suite (expected: 258 passed as of v0.4.7):**
```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=electrum-src python3 -m pytest \
  tests/test_core_*.py tests/test_gui_*.py \
  tests/test_anticipate_past_locktime.py tests/test_anticipate_manual_locktime.py \
  tests/test_group_b_auto_sign.py tests/test_group_c_settings.py \
  tests/test_group_d_alarms.py tests/test_group_e_mock_giovanna7.py \
  tests/test_group_f_heir_change_rebuild.py tests/test_group_g_basic_calendar.py -q
```

**Lint (only NEW errors matter; ignore pre-existing noise):**
```bash
ruff check <files> | grep -oE "^[^ ]+\.py:[0-9]+:[0-9]+: [A-Z][0-9]+" \
  | grep -vE "F401|F403|F405|F841"
```
Pre-existing, KNOWN-OK ruff noise: `F401/F403/F405` (star-imports via
`from .common import *`) and 2× `F841` (an unused `e` in two `except` blocks).
Do NOT "fix" these unless asked — they are intentional / out of scope.

**Build the ZIP (always clear caches first so zipimport doesn't ship stale .pyc):**
```bash
find bal -name "__pycache__" -type d -exec rm -rf {} + ; find bal -name "*.pyc" -delete
python3 build_zip.py bal-electrum-plugin-vX.Y.Z.zip      # produces 37 files
```

**Bump version — there are FOUR files, keep them in sync:**
```
bal/core/plugin_base.py   ->  __version__ = "X.Y.Z"  # AUTOMATICALLY GENERATED DO NOT EDIT
bal/__init__.py           ->  __version__ = "X.Y.Z"
bal/VERSION               ->  X.Y.Z
bal/manifest.json         ->  "version": "X.Y.Z",
```

**IMPORTANT for the owner when testing:** after installing a ZIP, the owner
must **fully restart Electrum** (not just reload the plugin) — Electrum's
`zipimport` caches modules, so a partial reload runs stale code.

---

## 4. Key technical knowledge (hard-won — saves you hours)

- **Locktimes are UNIX timestamps only.** Block-height locktimes were removed
  (CHANGELOG #1). Ordering/expiry compare timestamps.
- **`heirs.py` data shape.** An heir is a list indexed by constants
  (`heirs.py` top): `HEIR_ADDRESS=0`, `HEIR_AMOUNT=1` (sats or `"<n>%"`),
  `HEIR_LOCKTIME=2`, `HEIR_REAL_AMOUNT=3` (resolved sats, or the string
  `"DUST: <n>"` when below the dust limit), `HEIR_DUST_AMOUNT=4` (raw dust sats).
- **Will-executor pseudo-heirs.** Internally, each selected will-executor is
  injected as a fake "heir" whose NAME starts with the reserved marker
  `w!ll3x3c"` (i.e. `'w!ll3x3c"' + url + '"' + str(locktime)`). Its amount is
  the executor `base_fee` (always non-dust). When you count/iterate "real"
  heirs you MUST skip names starting with `w!ll3x3c"`.
- **Transaction-building pipeline:**
  `window.build_will()` → `Heirs.get_transactions()` (recursive over locktimes)
  → `Heirs.buildTransactions()` → `Heirs.prepare_lists()` (builds the
  `locktimes` dict for ALL future locktimes, resolves amounts, marks dust)
  and `prepare_transactions()` (builds ONE tx for the LOWEST locktime only;
  the recursion handles the others via leftover `available_utxos`).
- **DUST logic (v0.4.7 — verify before touching):**
  - The "all heirs are dust" guard lives at the END of `prepare_lists`
    (NOT in `prepare_transactions`). Reason: `prepare_transactions` only sees
    the single lowest locktime, so a guard there would FALSE-POSITIVE block a
    will whose later locktimes still have valid heirs. `prepare_lists` is the
    only place that sees ALL heirs across ALL locktimes with their final dust
    state (fixed AND percentage).
  - Guard: count real heirs (skip `w!ll3x3c"`); if there are real heirs but
    NONE has a valid (non-`"DUST"`) `HEIR_REAL_AMOUNT`, raise
    `HeirAmountIsDustException` (defined in `heirs.py`). A mix of dust + valid
    heirs keeps building normally.
  - **Critical nuance:** with FIXED amounts and a LARGE balance, leftover funds
    are REDISTRIBUTED (`normalize_perc(..., real=True)`), so small fixed
    amounts end up with a VALID `HEIR_REAL_AMOUNT` (not dust). The real
    all-dust case is **small balance + percentage heirs** (matches the owner's
    log: shares of 214 / 316 / 3 sat). Tests reproduce this with
    `prepare_lists(800, 100, wallet)` and `"40%"/"60%"` heirs.
  - The exception is NOT a `WillExecutorFeeException`, so it skips that handler
    in `buildTransactions` and propagates cleanly to the GUI.
  - GUI: `dialogs.py task_phase1` has a dedicated `except
    HeirAmountIsDustException` BEFORE the generic `except Exception`. It shows a
    RED message and stops (`return False, None`) — no signing/checking, no
    empty will in the list. `HeirAmountIsDustException` is imported in
    `common.py` and re-exported via `from .common import *`.
- **`broadcast_transaction` returns `None`** (Electrum `network.py`). To get a
  txid, use `tx.txid()` — do NOT rely on the broadcast return value
  (this was the root cause of the missing "BAL Invalidate transaction" label,
  CHANGELOG #21 / v0.4.5).
- **Qt label truncation gotcha (CHANGELOG #22).** A `QLabel` added with
  `alignment=Qt.AlignmentFlag.AlignLeft` is NOT stretched by Qt, so word-wrap
  computes on a narrow sizeHint and the text gets truncated. Fix: drop the
  alignment flag, add `setSizePolicy(Expanding, Minimum)` + `setMinimumWidth`.
  With `setWordWrap(True)`, an explicit `\n` in the text forces a line break.
- **`BalBuildWillDialog` report area.** Messages are accumulated as HTML in
  `self.labels` and joined by `msg_update` (`"<br><br>".join(...)`, `\n`→`<br>`).
  The report is inside a `QScrollArea` (v0.4.7: `setMinimumHeight(500)`,
  `setMaximumHeight(700)`); the Close button sits BELOW the scroll area so it
  stays reachable.

---

## 5. Git / delivery workflow

- **Branch:** work on `genspark_ai_developer`. Open PRs into `main`.
- **Commit policy:** ZIP-FIRST — build a test ZIP, let the owner confirm it
  works, THEN commit. (This differs from "commit after every change"; the owner
  explicitly prefers ZIP-first because they manually test each build.)
- Before opening/updating a PR: `git fetch origin main`, rebase, resolve
  conflicts preferring remote `main` unless a local change is essential,
  squash local commits into ONE comprehensive commit, push (force if needed),
  then create/update the PR and SHARE the PR URL with the owner.
- The previous PR for this line of work is **PR #13** on the repo.
- Deliverable ZIPs are uploaded with the file-wrapper tool and the URL is given
  to the owner. (Latest: v0.4.7.)

---

## 6. Version history (short — full detail in CHANGELOG.md)

- **v0.4.5** — fix invalidation loop; add "BAL Invalidate transaction" label on
  the automatic path (root cause: `broadcast_transaction` returns None → use
  `tx.txid()`); fix wizard text truncation.
- **v0.4.6** — DUST one-line-per-heir report; heirs on one line; scrollable
  report area; wizard final check (`on_next_we` now calls
  `check_transactions`); wizard truncation fix (remove AlignLeft); anticipated-
  date notice styling.
- **v0.4.7** — report area opens 500px tall (max 700); heirs reverted to ONE
  per line (green/bold); explicit `\n` line breaks in two wizard texts
  (after "(or backup)" and after "miner fees"); **ALL-DUST guard** in
  `prepare_lists` that blocks (clear RED message) only when EVERY heir is dust;
  3 new tests pinning the dust behaviour. 258 tests pass.

---

## 7. How to resume (checklist for the next AI)

1. Read this file, then `CHANGELOG.md` (last entries) and `.agent_memory_tasks.md`.
2. Confirm the environment: `git status`, current branch, `bal/VERSION`.
3. Run the full test suite (Section 3) — expect all green (258 as of v0.4.7).
4. Talk to the owner in **Italian**, write everything else in **English**.
5. For any change: present a PLAN, wait for "OK" (R4), then implement, test,
   build a ZIP, let the owner test, and only commit after explicit confirmation.
6. Keep credit usage low: summarize, don't paste big code blocks; batch work.
