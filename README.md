# BAL — Bitcoin After Life (Electrum plugin)

Free and decentralized **Bitcoin inheritance** support for the
[Electrum](https://electrum.org) wallet. Build time-locked "will" transactions
that transfer your funds to your heirs if you stop refreshing them
(dead-man's switch), optionally relayed by will-executor servers.

This repository contains a **behavior-preserving refactor** of the original
plugin. The logic was kept byte-identical wherever possible; only the file
layout was reorganized to cleanly separate **business logic** from the
**PyQt GUI**.

## Repository layout

```
bal/                     the installable Electrum plugin package
├── manifest.json        plugin metadata (Electrum reads this)
├── qt.py                Qt entry-point shim (re-exports Plugin)
├── core/                GUI-free logic (importable without Qt)
│   ├── util.py
│   ├── plugin_base.py
│   ├── heirs.py
│   ├── will.py
│   └── willexecutors.py
├── gui/qt/              PyQt6 presentation layer
│   ├── theme.py         status → color mapping
│   ├── common.py        shared imports / helpers
│   ├── widgets.py       leaf widgets
│   ├── calendar.py      calendar widget
│   ├── dialogs.py       dialog windows
│   ├── lists.py         tree/list views
│   ├── window.py        per-wallet GUI controller
│   └── plugin.py        Plugin (Electrum @hooks → GUI)
├── icons/  wallet_util/  LICENSE  VERSION  README.md
build_zip.py             builds a clean, zipimport-friendly distribution zip
tests/                   smoke + external-zip regression tests
```

## Requirements

- **Electrum 4.7.2** — the last stable release exposing `json_db.register_dict`,
  which this plugin relies on. Newer versions removed it.
- **PyQt6** (bundled with the Electrum desktop GUI).

## Installation

### Build the distribution archive

```bash
python3 build_zip.py
# -> bal-electrum-plugin.zip  (prints size + SHA-256 for integrity checks)
```

The builder writes a `zipimport`-friendly archive (files only, standard
DEFLATE, deterministic order) to avoid loader errors seen on some Electrum
portable builds.

### Install as an external plugin (zip)

1. Electrum → **Tools → Plugins** → install from file → pick the built zip.
2. Enable **Bitcoin After Life** and restart Electrum.
3. (Recommended) verify the downloaded zip's SHA-256 matches the value printed
   by `build_zip.py`.

### Install as an internal plugin

Copy the `bal/` directory into your Electrum installation's
`electrum/plugins/` directory, so that `electrum/plugins/bal/manifest.json`
exists, then enable it from **Tools → Plugins**.

## Inheritance safety: anticipate / postpone

A will transaction is signed with a **fixed, immutable locktime** and then
optionally sent to will-executor servers, which are economically incentivised
to broadcast it (they collect fees). Because the locktime is baked into the
signed transaction, simply changing the delivery time later is **not enough**:
the old, already-signed transaction keeps living on the will-executors.

The plugin handles the two cases as follows (triggered when you press
**Tools → Prepare**):

* **Anticipate** (new delivery time *earlier* than the signed locktime): the
  will is treated as expired and you are asked to **invalidate** the old
  transaction on-chain, then rebuild.
* **Postpone** (new delivery time *later* than the signed locktime) on a will
  that was already **signed and/or pushed**: the previously committed coins
  must be invalidated on-chain **first**, otherwise a will-executor could
  broadcast the old (earlier-locktime) transaction and execute the inheritance
  *too early*. The plugin detects this by comparing the requested locktime with
  the locktime **frozen inside the signed transaction** (`tx.locktime`), and
  asks you to sign and broadcast an invalidation transaction. After it is
  broadcast, press **Prepare** again to rebuild, re-sign and re-send the new
  (postponed) inheritance. Postponing a will that was *never* signed/sent just
  rebuilds it (no on-chain fee).

## Transaction list: the "Server" column

The will transaction list shows a dedicated **Server** column so you always
know whether each inheritance transaction is actually stored on the
will-executor servers, independently of the row colour:

| Label | Meaning |
| --- | --- |
| `Confirmed on server` | the will-executor confirmed it stored the transaction |
| `Sent (not checked)` | pushed to the will-executor, not yet re-checked |
| `Send failed` / `Not on server` | push failed or the server no longer has it |
| `Signed (not sent)` | signed locally, not sent to any will-executor |
| `Not sent` | not signed/sent yet |

Hovering the cell shows a tooltip with the will-executor URL and the current
state.

## Testing

```bash
# imports + behavior
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/smoke_test.py electrum.plugins.bal

# external-zip loading regression
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/external_zip_test.py bal-electrum-plugin.zip
```

## ⚠️ Safety

This plugin builds real Bitcoin inheritance transactions with time-locks. Test
on **testnet** or a fund-less wallet first, and review the generated
transactions before broadcasting.

## License

MIT — see [`bal/LICENSE`](bal/LICENSE).
