# BAL — Resoconto del refactoring (per l'autore originale)

Questo documento elenca **tutte** le modifiche apportate al plugin BAL
(Bitcoin After Life) rispetto alla versione originale `0.2.8`.

**Principio guida:** refactoring **conservativo e a comportamento invariato**
(Approccio A). La logica di business è stata mantenuta **byte-identica** dove
possibile; sono cambiati soprattutto la **disposizione dei file** e gli
**import**. Nessuna riscrittura algoritmica.

Ambiente di verifica: **Electrum 4.7.2** + **PyQt6** (l'ultima release stabile
che espone `json_db.register_dict`).

---

## 1. Riorganizzazione della struttura (separazione logica / GUI)

Il problema principale segnalato era che la logica e la grafica erano
mescolate, in particolare in un unico file `qt.py` da **4131 righe**.

### Struttura PRIMA (flat, 7 file)
```
BAL/
├── __init__.py        (vuoto, 0 righe)
├── bal.py             (243)  logica + plugin base
├── util.py            (533)  helper
├── heirs.py           (791)  modello eredi + costruzione tx
├── will.py            (927)  modello will/WillItem
├── willexecutors.py   (374)  networking will-executor
├── qt.py              (4131) TUTTA la GUI + il Plugin in un solo file
└── bal_resources.py   (14)
```

### Struttura DOPO (core/ vs gui/)
```
bal/
├── manifest.json            metadati conformi allo standard
├── qt.py                    shim di caricamento (re-export di Plugin)
├── __init__.py              docstring di architettura + __version__
├── core/                    LOGICA senza dipendenze Qt
│   ├── util.py              (ex util.py)
│   ├── plugin_base.py       (ex bal.py)
│   ├── heirs.py             (ex heirs.py)
│   ├── will.py              (ex will.py)
│   └── willexecutors.py     (ex willexecutors.py)
└── gui/qt/                  PRESENTAZIONE PyQt6
    ├── theme.py      (59)   mappatura stato → colore
    ├── common.py     (155)  import condivisi + helper GUI
    ├── widgets.py    (782)  widget "foglia"
    ├── calendar.py   (80)   BalCalendar
    ├── dialogs.py    (1127) finestre di dialogo
    ├── lists.py      (957)  viste ad albero (eredi/preview/executor)
    ├── window.py     (952)  controller GUI per-wallet (BalWindow)
    └── plugin.py     (273)  classe Plugin (@hook Electrum → GUI)
```

Il file `qt.py` da 4131 righe è stato suddiviso per **responsabilità**. I
**corpi delle classi sono stati copiati verbatim** (riga per riga) per non
toccare la logica delicata delle transazioni di eredità.

### Mappa: dove sono finite le 40 classi/funzioni di `qt.py`

| Classe/funzione (riga orig.)        | Nuovo modulo            |
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

## 2. Rimozioni (codice morto / debug) — comportamento invariato

Tutte le rimozioni seguenti sono state verificate come **non utilizzate** o
**puramente di debug**, quindi non alterano il comportamento del plugin.

1. **`util.py` → `core/util.py`**: rimossi tre helper di debug usati solo per
   stampe a console:
   - `print_var()`   (orig. riga 439)
   - `print_utxo()`  (orig. riga 474)
   - `print_prevout()` (orig. riga 486)

2. **`bal.py` → `core/plugin_base.py`**: rimossa la funzione **stub vuota**
   `get_will_settings(x)` (orig. righe 12-14):
   ```python
   def get_will_settings(x):
       # print(x)
       pass
   ```
   ⚠️ Verificato: **non era riferita da nessun `register_dict`** — i tre
   `register_dict` usano `tuple`, `dict`, `lambda x: x`. Quindi era codice
   morto. La funzione **usata** `get_will(x)` è stata mantenuta identica.

3. **`will.py` (`WillItem`) → spostato in `gui/qt/theme.py`**: il metodo
   `WillItem.get_color()` (orig. riga 852) restituiva colori esadecimali —
   è logica di **presentazione**, non di dominio. È stato spostato fuori dal
   modello e trasformato nella funzione `status_color(will_item)` in
   `gui/qt/theme.py`. **Verificato byte-identico** su tutte le combinazioni di
   stato (stessa catena di `get_status(...)`, stessi codici colore).

---

## 3. Cambi di import (necessari per la nuova struttura)

Gli import sono stati aggiornati da "flat" a "a package". Esempi:

| Prima                              | Dopo                                  |
|------------------------------------|---------------------------------------|
| `from .bal import BalPlugin`       | `from .plugin_base import BalPlugin`   (in willexecutors) |
| `from .util import Util`           | `from .util import Util`               (invariato, ora dentro core/) |
| (in qt.py) `from .bal import ...`  | i moduli GUI importano da `...core.X`  |

- Aggiunti `from .common import _, _logger` nei moduli GUI, perché `import *`
  **non** esporta i nomi che iniziano con underscore.
- Aggiunti 3 import "lazy" (dentro le funzioni) in `dialogs.py` per spezzare il
  ciclo `dialogs ↔ lists` (lists importa `BalBuildWillDialog` da dialogs).

La **logica interna dei metodi** non è stata toccata: `prepare_transactions()`,
`buildTransactions()` ecc. sono verbatim.

---

## 4. Packaging conforme allo standard Electrum

`manifest.json` reso conforme a https://plugins.electrum.org/developers.html :

| Campo            | Prima              | Dopo                          |
|------------------|--------------------|-------------------------------|
| `name`           | `"BAL"`            | `"bal"` (minuscolo = nome dir) |
| `version`        | (assente, era solo nella description) | `"0.2.8"`     |
| `description`    | con `<br>` HTML    | testo pulito                  |
| `licence`        | (assente)          | `"MIT"`                       |
| `fullname`/`author`/`available_for`/`icon` | presenti | invariati        |

- `__init__.py` (era **vuoto**): ora contiene la docstring di architettura e
  `__version__ = "0.2.8"`.
- Portati nel package: `LICENSE`, `VERSION`, `README.md`, `bal_resources.py`,
  e la cartella `wallet_util/` (invariata).

---

## 5. CORREZIONE BUG: caricamento come plugin esterno (.zip)

Durante i test su **Electrum 4.7.2 portable per Windows** sono emersi due
problemi reali nel caricare il plugin come **plugin esterno da .zip**:

### Bug 5a — `ModuleNotFoundError: No module named 'electrum_external_plugins'`
- **Causa:** Electrum carica i plugin esterni da zip sotto il package sintetico
  `electrum_external_plugins.bal`, ed esegue **solo** l'`__init__` del package e
  il modulo `qt`. Non registra il package radice sintetico né i sotto-package
  annidati (`gui`, `gui.qt`). Un semplice `from .gui.qt.plugin import Plugin`
  fallisce risalendo ai parent mancanti.
- **Fix:** `qt.py` ora è uno shim resiliente che (1) rileva a runtime il proprio
  nome di package (`__package__`), (2) ricostruisce in `sys.modules` gli
  eventuali package padre mancanti, (3) importa `Plugin` con
  `importlib.import_module`. Funziona **sia** come plugin interno
  (`electrum.plugins.bal`) **sia** esterno (`electrum_external_plugins.bal`).

### Bug 5b — `zlib.error: Error -5 ... incomplete or truncated stream`
- **Causa:** alcune build portable di Electrum su Windows non riescono a
  decomprimere con `zipimport` archivi che contengono **voci di directory** o
  compressione non standard.
- **Fix:** aggiunto `build_zip.py`, che genera un archivio "zipimport-friendly":
  solo file (nessuna voce di directory), DEFLATE standard, ordine deterministico
  (SHA-256 riproducibile), escludendo `__pycache__`/`*.pyc`. Stampa anche
  l'hash SHA-256 per verificare l'integrità del download.

---

## 6. Test aggiunti

- `tests/smoke_test.py` — verifica import + comportamento di base
  (`BalTimestamp`, helper di `Util`, costanti `HEIR_*`, stati di `WillItem`,
  hook del `Plugin`).
- `tests/external_zip_test.py` — riproduce **fedelmente** la sequenza di
  caricamento di un plugin esterno da zip di Electrum (regressione per il
  Bug 5a/5b).

Tutti i test passano sotto Electrum 4.7.2 + PyQt6.

---

## 7. Riepilogo: cosa NON è cambiato

- La logica di costruzione delle transazioni (`heirs.py`, `will.py`).
- I valori e i tipi di `json_db.register_dict(...)`.
- I codici colore degli stati (solo spostati in `theme.py`).
- L'algoritmo di tutte le classi GUI (copiate verbatim).
- Il formato dei dati salvati nel wallet.

## 8. Note / raccomandazioni

- Il plugin **richiede Electrum 4.7.2**: `json_db.register_dict` è stato
  **rimosso** nelle versioni successive (master), dove andrebbe sostituito con
  `stored_dict.register_name`. Valutare un adeguamento se si vuole supportare
  Electrum più recente.
- Prima del rilascio è consigliata una prova **end-to-end in una sessione
  Electrum reale** (preferibilmente su testnet), oltre agli smoke test.
