# BalPlugin
Bitcoin After Life Electrum Plugin

Free and decentralized Bitcoin inheritance support for Electrum: build
time-locked "will" transactions that transfer your funds to your heirs if you
stop refreshing them (dead-man's switch), optionally relayed by will-executor
servers.

## Key behaviours

- **Anticipate / postpone safety**: changing the delivery time of an
  already-signed will is handled safely. Postponing a signed/sent will first
  asks you to invalidate the old transaction on-chain (so a will-executor can
  never broadcast the earlier-locktime transaction and execute the inheritance
  too early), then lets you rebuild and re-send the new one via
  **Tools → Prepare**.
- **"Server" column**: the will transaction list shows whether each transaction
  is actually stored on the will-executor servers
  (`Confirmed on server`, `Sent (not checked)`, `Send failed`,
  `Not on server`, `Signed (not sent)`, `Not sent`), with a tooltip showing the
  will-executor URL.

See the top-level [`README.md`](../README.md) for installation and testing.
