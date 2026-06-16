<p align="center">
  <img src="./manual/images/logo.png" alt="BitcoinAfter.Life logo" width="110" />
</p>

<h1 align="center">BAL — Bitcoin After Life · Documentation</h1>

Documentation for the **BAL** open‑source Electrum plugin for Bitcoin digital
inheritance. Everything here is plain Markdown + images (and optional styled
HTML), so it renders directly on GitHub and via GitHub Pages — **no PDF needed**.

## Contents

| Document | Markdown (GitHub) | Styled HTML |
|---|---|---|
| **User Manual (revB)** — full plugin manual with screenshots | [`manual/README.md`](./manual/README.md) | [`manual/manual.html`](./manual/manual.html) |
| **Inheritance Options Guide** — every change (date earlier/later, add/remove heir, change %, fees, executors) + decision flow chart + transaction states & server effects | [`inheritance-options.md`](./inheritance-options.md) | [`inheritance-options.html`](./inheritance-options.html) |

## Quick links

- 📖 **New to BAL?** Start with the [User Manual](./manual/README.md).
- 🔁 **Changing a will?** See the [Inheritance Options Guide](./inheritance-options.md)
  to know exactly what happens (and whether it costs an on‑chain fee).

## Viewing the HTML versions

- On GitHub Pages: enable Pages for this repository (Settings → Pages → deploy
  from branch, folder `/docs`), then open
  `https://<owner>.github.io/<repo>/manual/manual.html`.
- Offline: download the `docs/` folder and open the `.html` files in any browser
  (the styled manual works fully offline; the inheritance‑options page loads
  Mermaid from a CDN for the live diagram, and also ships a static SVG fallback).

---

*The manual is the GitHub‑friendly edition of the official BAL PDF
([bal_plugin_manual](https://bitcoin-after.life/gitea/bitcoinafterlife/bal_plugin_manual)).*
