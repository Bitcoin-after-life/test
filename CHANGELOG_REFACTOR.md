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

---

## 9. CORREZIONI GUI — finestre e ciclo di vita (B1-B10)

Dopo il refactoring di struttura sono stati corretti **dieci difetti grafici e
di ciclo di vita** delle finestre, già presenti nel codice originale. La logica
di business è rimasta **byte-identica** (nessuna modifica a `bal/core/*`): sono
cambiati solo **presentazione, parent, modalità, z-order, ciclo di vita e
cleanup** delle finestre Qt.

Sintomi segnalati dall'utente, ora risolti:
- **(S1)** le finestre del plugin sparivano dietro la finestra di Electrum;
- **(S2)** alcuni meccanismi funzionavano solo dopo aver chiuso e riavviato
  Electrum.

| ID  | Problema (presente nell'originale)                                   | Correzione applicata |
|-----|----------------------------------------------------------------------|----------------------|
| B1  | `self.parent = parent` sovrascriveva il metodo `parent()` di Qt, rompendo la gerarchia delle finestre | rinominato in `self._bal_parent` (in `dialogs.py`, `lists.py`, `widgets.py`); il parent reale passa da `top_level_of(parent)` |
| B2  | dialoghi aperti con `.show()` non modale → finivano sotto la finestra principale | sostituiti con `show_on_top()` / `show_modal()` e parent corretto |
| B3  | messaggio "Please restart Electrum to activate the BAL plugin": il plugin si attivava solo dopo riavvio | inizializzazione **a caldo** con `_setup_window()` che replica `load_wallet` — niente più riavvio |
| B4  | chiave del dizionario finestre usava il **metodo** `winId` invece del valore | chiave stabile `_window_key()` basata su `id(window)` |
| B5  | `on_close` ingoiava tutti gli errori con `except: pass` | riscritto: niente `except:pass`, log per ogni passo, reset pulito dello stato |
| B6  | `BalBlockingWaitingDialog` bloccava il thread della GUI (`processEvents` commentato) | ripristinato `processEvents()` → GUI reattiva durante l'attesa |
| B7  | `closeEvent`/`hideEvent` con cleanup del thread commentato | gestione esplicita di `closeEvent`/`hideEvent` + chiamata a `super()` |
| B8  | `closeEvent` incompleto in alcuni dialog | gestione uniforme dello stato di chiusura |
| B9  | `show()+raise_()` senza `activateWindow()` né modalità → finestra non in primo piano | `bring_to_front()` = `raise_()` + `activateWindow()` |
| B10 | gestione multi-wallet / multi-finestra fragile; menu cercato per titolo `&Tools` | uso dell'API ufficiale `window.tools_menu` |

### Nuovo modulo: `gui/qt/window_utils.py` (119 righe)

Gli helper per la gestione delle finestre sono stati **centralizzati** in un
unico modulo, così la stessa logica non viene duplicata nei vari dialog:

- `top_level_of(widget)` — risale alla finestra di primo livello corretta da
  usare come parent;
- `bring_to_front(window)` — `raise_()` + `activateWindow()` per portare in
  primo piano;
- `stop_thread(thread)` — stop+wait sicuro di un `TaskThread`;
- `show_modal(dialog)` — apertura modale corretta (`exec()`);
- `show_on_top(window)` — apertura non modale ma sopra le altre finestre.

`gui/qt/common.py` importa questi helper e li rende disponibili al resto della
GUI.

---

## 10. CORREZIONE BUG: download lista will-executor

Dopo l'installazione del pacchetto con le correzioni GUI, l'utente ha
segnalato che il comando **"download list"** dei will-executor non scaricava
più la lista.

### Indagine

Il codice di rete (`core/willexecutors.py`: `send_request`, `handle_response`,
`download_list`, `initialize_willexecutor`) è stato confrontato riga per riga
con l'originale Gitea ed è risultato **byte-identico** (l'unica differenza è il
parametro aggiuntivo `welist_server` in `download_list`, retro-compatibile).

Durante l'indagine sono comunque emersi e stati corretti **due difetti reali**
introdotti dalle correzioni GUI, che potevano "perdere" il risultato del
download:

1. **`BalDialog.closeEvent`/`hideEvent` fermavano il `TaskThread`.** In Electrum
   `TaskThread.on_done` esegue `cb_done` (cioè `self.accept`, che **chiude** il
   dialog) **prima** di `cb_result` (cioè `on_success`, che **aggiorna** la
   lista). Fermare il thread alla chiusura del dialog **scartava** quindi il
   risultato appena scaricato. → I due metodi sono stati riportati a **non**
   fermare il thread (con commento esplicativo nel codice).
2. **`BalWaitingDialog.exe()` usava una modalità sbagliata** (`show_modal` /
   `WindowModal`). → Ripristinato l'originale `self.exec()`, aggiungendo prima
   `bring_to_front(self)` per garantire il primo piano.

Inoltre i percorsi del **pulsante** e del **wizard** (che prima scaricavano in
modi diversi e con messaggi diversi) sono stati **unificati** in un unico
helper `fetch_will_executors_list`, eseguito dentro il worker del `TaskThread`.

### Causa vera del mancato download: ambientale, NON del plugin

Una probe di controllo con `urllib` che **bypassava completamente Electrum**
falliva ugualmente con `WinError 10054` ("connection forcibly closed by remote
host"): segno che la **rete/ISP dell'utente resettava la connessione HTTPS**
verso `welist.bitcoin-after.life`. La conferma definitiva: **attivando una VPN
il download è andato a buon fine.**

L'originale "sembrava" funzionare perché spedisce comunque un will-executor di
**default già incorporato** (`https://we.bitcoin-after.life`), quindi la lista
non risultava mai del tutto vuota anche senza un download riuscito.

### Pulizia finale (scelta dall'utente — "Opzione 1")

- **Finestra di attesa non bloccante** mantenuta (`BalWaitingDialog`), così la
  GUI non si congela durante il download.
- **Fallback dell'URL**: prima l'URL configurato (`WELIST_SERVER`), poi quello
  hardcoded `https://welist.bitcoin-after.life/`.
- **Diagnostica dettagliata spostata nei soli log** (rimossa la probe `urllib`
  dall'interfaccia).
- **Messaggio d'errore semplice per l'utente, in inglese** (`DOWNLOAD_FAILED_MESSAGE`):

  > *"Could not download the will-executors list. This is usually caused by
  > your internet connection or a firewall, not by the plugin. Please check
  > your connection (a VPN often helps) and try again."*

### File toccati (solo presentazione/GUI, logica invariata)

- `gui/qt/window.py` — helper condiviso `fetch_will_executors_list`,
  `download_list` con `TaskThread` + `BalWaitingDialog`, costante
  `DOWNLOAD_FAILED_MESSAGE`.
- `gui/qt/lists.py` — `WillExecutorWidget.download_list` instradato sul
  percorso condiviso con `on_success` che aggiorna/salva la lista.
- `gui/qt/dialogs.py` — `BalDialog.closeEvent`/`hideEvent` **non** fermano più
  il thread; `BalWaitingDialog.exe()` torna a `self.exec()` + `bring_to_front`.
- `tests/gui_fixes_test.py` — asserzione di **regressione**: verifica che
  `closeEvent`/`hideEvent` **non** contengano `stop_thread` (per non
  reintrodurre il bug che scartava il download).

---

## 11. Confronto strutturale finale (originale Gitea → refactor)

Conteggio file `.py` (escluse cartelle generate):

| Originale (Gitea)            | righe | →  | Refactor (`bal/`)                         | righe |
|------------------------------|------:|----|-------------------------------------------|------:|
| `__init__.py`                |     1 | →  | `__init__.py`                             |    37 |
| `bal.py`                     |   161 | →  | `core/plugin_base.py`                     |   351 |
| `util.py`                    |  1051 | →  | `core/util.py`                            |   614 |
| `heirs.py`                   |   792 | →  | `core/heirs.py`                           |   806 |
| `will.py`                    |   903 | →  | `core/will.py`                            |   938 |
| `willexecutors.py`           |   547 | →  | `core/willexecutors.py`                   |   390 |
| `qt.py` (monolite GUI)       |  3777 | →  | suddiviso in `gui/qt/*` (vedi sotto)      |     — |
| `bal_resources.py`           |    14 | →  | `bal_resources.py`                        |    14 |
| `wallet_util/*.py`           |   275 | →  | `wallet_util/*.py` (invariati)            |   280 |

Suddivisione del vecchio `qt.py` (3777 righe) nei moduli GUI:

| Modulo refactor             | righe | Contenuto |
|-----------------------------|------:|-----------|
| `gui/qt/plugin.py`          |   303 | classe `Plugin` (`@hook` Electrum → GUI) |
| `gui/qt/window.py`          |  1048 | `BalWindow` (controller per-wallet) |
| `gui/qt/dialogs.py`         |  1155 | finestre di dialogo + wizard |
| `gui/qt/lists.py`           |   964 | viste ad albero (eredi/preview/executor) |
| `gui/qt/widgets.py`         |   782 | widget "foglia" |
| `gui/qt/common.py`          |   157 | import condivisi + helper |
| `gui/qt/window_utils.py`    |   119 | helper finestre (NUOVO — vedi §9) |
| `gui/qt/calendar.py`        |    80 | `BalCalendar` |
| `gui/qt/theme.py`           |    59 | mappatura stato → colore |
| `gui/qt/__init__.py`        |    17 | init package GUI |

> Le differenze nei conteggi di righe rispetto all'originale derivano da:
> riformattazione/commenti, separazione degli import per modulo, e spostamento
> di funzioni tra `util.py`/`bal.py` e i nuovi moduli. **Gli algoritmi non sono
> stati modificati.**

---

## 12. Cronologia delle modifiche su GitHub

- **`4198a51`** — import iniziale del refactor strutturale (v0.2.8): separazione
  `core/` (logica) vs `gui/qt/` (presentazione), packaging conforme, fix
  caricamento zip esterno, smoke test (sezioni §1-§8).
- **`d56fa36`** — questo changelog del refactoring (in italiano).
- **`4806997`** — `DIAGNOSI_GUI.md`: diagnosi dei bug GUI di z-order e ciclo di
  vita (Fase A).
- **`dd6f677`** (PR **#2**, squash) — correzioni GUI **B1-B10** + fix download
  lista will-executor + `window_utils.py` + test di regressione (sezioni §9-§10).
- **PR #3** — fix **OverflowError su Windows (anno 2038)** che rompeva le schede
  Will/Heirs e la voce di menu (sezione §13).

---

## 13. CORREZIONE BUG: OverflowError su Windows (limite anno 2038)

### Sintomo (Windows 11)
Dopo aver **riavviato Electrum** o **cambiato wallet**, le schede **Will** e
**Heirs** sparivano e compariva una **voce di menu condensata/illeggibile**
(icona + testo sovrapposti) sotto il logo di Electrum, accanto a *Portafogli*.
Su Linux il problema non si manifestava.

### Causa vera (dal log di Electrum dell'utente)
```
OverflowError: Python int too large to convert to C int
  window.py __init__ -> create_heirs_tab -> WillSettingsWidget
  -> on_locktime_change -> BalTimestamp.to_date
  -> datetime.fromtimestamp(NLOCKTIME_MAX)
```

- `NLOCKTIME_MAX = 2**32 - 1 = 4294967295` viene usato come locktime di
  **default/sentinella**.
- Su **Windows** `time_t` è a **32 bit**, quindi `datetime.fromtimestamp(ts)`
  solleva **`OverflowError`** per qualsiasi timestamp oltre il **2038**.
- Su **Linux 64-bit** la stessa chiamata **funziona**: ecco perché il bug si
  vedeva solo su Windows e i test su Linux non lo intercettavano.
- L'eccezione interrompeva `BalWindow.__init__` durante `init_menubar` /
  `load_wallet`, lasciando le schede Will/Heirs e la voce di menu **a metà
  costruzione** → l'elemento grafico condensato/illeggibile sotto il logo.

> Nota: i due primi tentativi di correzione (status-bar no-op e idempotenza di
> `init_menubar_tools`) **non** centravano la causa; sono stati comunque
> mantenuti perché innocui e leggermente migliorativi, ma il vero colpevole era
> questo crash a monte.

### Fix (comportamento invariato per tutti i valori normali)
- **`BalTimestamp._safe_fromtimestamp()`**: `datetime.fromtimestamp` con
  **clamp a INT32_MAX** (anno 2038) in caso di `OverflowError`/`OSError`/
  `ValueError`, **esattamente** come la funzione `get_max_allowed_timestamp()`
  dell'originale (workaround per Electrum issue **#6170**).
- Usato in `to_date` / `to_timestamp` / `__str__` / `__repr__` di
  `BalTimestamp`.
- `gui/qt/widgets.py` (`set_value`): usa il converter sicuro.
- `core/util.py` (`timestamp_minus`): stessa protezione inline con clamp a
  INT32_MAX.

I valori entro il 2038 (date assolute normali, durate relative come `90d`/`5y`)
producono **lo stesso identico risultato** di prima.

### Test
- `tests/windows_overflow_test.py` riproduce il limite 32-bit di Windows
  (monkeypatch di `datetime.fromtimestamp`) e dimostra che **senza** il fix si
  ottiene lo **stesso** `OverflowError` del log, mentre **con** il fix passa.
  Verificato anche che il test **fallisce** senza il fix.

Confermato dall'utente: **"si ora funziona"**.

## 14. NUOVA FUNZIONE: invalidazione automatica al posticipo dell'eredità

### Problema
Una transazione di eredità viene firmata con un **locktime fisso e immutabile**
e inviata ai will-executor, che sono economicamente incentivati a trasmetterla
(incassano le fee). Se l'utente, dopo aver firmato/inviato, **posticipa** la
data di consegna (es. di un anno), la **vecchia** transazione gia firmata resta
valida sui server dei will-executor. Poiche ha il locktime piu basso, un
will-executor potrebbe trasmetterla appena scade, eseguendo l'eredita **in
anticipo** rispetto alla nuova volonta dell'utente. La versione precedente
**non gestiva** questo caso: il posticipo non produceva alcuna azione.

### Soluzione (Strategia B — invalidazione esplicita on-chain)
Al posticipo di un'eredita **gia firmata e/o inviata** (stato `COMPLETE` o
`PUSHED`), il plugin chiede di **invalidare on-chain** i fondi prima di
ricostruire la nuova eredita. L'invalidazione spende gli stessi UTXO verso un
nuovo indirizzo di change con `locktime = altezza corrente` (RBF), quindi e
trasmettibile subito: una volta confermata, la vecchia transazione pre-firmata
diventa **definitivamente inutilizzabile**, vincendo la corsa contro qualunque
will-executor.

### Dettagli tecnici
- **`core/will.py`**:
  - nuova eccezione `WillPostponedException` (sottoclasse di
    `NotCompleteWillException`);
  - `check_willexecutors_and_heirs`: il confronto del locktime non usa piu
    l'entry dell'erede memorizzata (`their[2]`), che viene aggiornata in memoria
    insieme al nuovo valore al momento del posticipo e quindi risulterebbe
    sempre uguale. Ora confronta il locktime richiesto con **`w.tx.locktime`**,
    cioe il locktime **congelato** nella transazione firmata (immutabile, e
    quello che i will-executor possiedono). Tre casi: invariato → coerente;
    nuovo > tx su will firmato/inviato → `WillPostponedException`; nuovo > tx su
    will mai inviato → semplice ricostruzione (nessuna fee on-chain).
- **`gui/qt/dialogs.py`** (`BalBuildWillDialog.task_phase1`, il percorso reale
  usato da **Tools → Prepare**): aggiunto il ramo `except WillPostponedException`
  **prima** di `NotCompleteWillException`; si comporta come il caso "will
  scaduto" e ritorna `(None, tx)` per innescare firma + broadcast
  dell'invalidazione. L'utente preme di nuovo **Prepare** per ricostruire,
  rifirmare e reinviare la nuova eredita (due passi espliciti, per maggior
  controllo).
- **`gui/qt/window.py`** (`build_inheritance_transaction`): aggiunto lo stesso
  ramo per completezza del percorso alternativo, con messaggio esplicativo.
- **`gui/qt/common.py`**: `WillPostponedException` esportato.

### NUOVA COLONNA "Server" nella lista transazioni
Per dare all'utente visibilita costante sullo stato online delle proprie
transazioni di eredita, e stata aggiunta una colonna dedicata **"Server"** in
`PreviewList` (`gui/qt/lists.py`), con etichetta sempre leggibile
(`Confirmed on server`, `Sent (not checked)`, `Send failed`, `Not on server`,
`Signed (not sent)`, `Not sent`) e **tooltip** con URL del will-executor e
stato. Le funzioni `server_status_text()` e `server_status_tooltip()` sono in
`gui/qt/theme.py` e riusano gli stessi flag di stato gia esistenti.

### Test
- I 182 test ufficiali continuano a passare; smoke test ed external-zip test
  OK; `ruff` senza nuove segnalazioni reali.
- Verificato sui dati reali del log dell'utente: il posticipo di un'eredita
  firmata ora rileva correttamente la condizione e avvia l'invalidazione.

Confermato dall'utente: **"mi pare che funziona"**.

## 15. TENTATIVO E REVERT: fix doppia invalidazione al posticipo (v0.3.1 -> v0.3.2)

### v0.3.1 (RITIRATA)
Per risolvere la doppia firma dell'invalidazione al posticipo, era stato
introdotto `Will.mark_invalidated_by_tx()`, chiamato in
`loop_broadcast_invalidating` dopo il broadcast dell'invalidazione, per marcare
`INVALIDATED` le will che spendevano gli stessi UTXO della tx di invalidazione
e persistere lo stato con `save_willitems`.

### Perche e stata ritirata
La modifica ha introdotto una regressione grave segnalata dall'utente:
**la lista eredita mostrava ancora le vecchie eredita e l'aggiornamento di
eredi/date risultava incoerente**.

Causa: `loop_broadcast_invalidating` e il punto di broadcast usato per **TUTTI**
i tipi di invalidazione (posticipo, CheckAlive, will scaduto/anticipato), non
solo per il posticipo. Inoltre il metodo marcava e **persisteva** lo stato
`INVALIDATED` su tutte le will item che condividevano gli UTXO del wallet
(tipicamente tutte). Queste will item invalidate restavano poi in memoria e su
disco, inquinando la ricostruzione di eredi/date e lasciando vecchie voci nella
lista.

### v0.3.2 (questa versione): REVERT completo
- Rimosso `Will.mark_invalidated_by_tx()` da `core/will.py`.
- Rimossa la chiamata in `gui/qt/dialogs.py` (`loop_broadcast_invalidating`):
  il metodo torna **identico** alla v0.3.0.
- Rimossi i due test relativi; mantenuto solo l'assert di gerarchia su
  `WillPostponedException` (corretto e indipendente).
- `core/will.py` e `gui/qt/dialogs.py` sono ora **byte-identici** alla v0.3.0
  funzionante (verificato con `git diff a394cde`).

Il bug della doppia invalidazione al posticipo resta quindi **aperto** e andra
riaffrontato in modo piu mirato (senza toccare il percorso di broadcast comune e
senza persistere stati su will che condividono gli UTXO), previa conferma
dell'utente. La priorita era ripristinare il comportamento corretto di
lista/eredi/date.

## 16. Aggiornamenti mancati, Check/Close coerenti, e rifinitura UI (v0.3.2)

### FIX 1 - Rimozione di un erede rilevata su Check / chiusura Electrum
`core/will.py` (`check_willexecutors_and_heirs`): prima il plugin
rilevava solo l'**aggiunta** di un erede (raise `HeirNotFoundException` quando un
erede corrente non era piu nella will). Mancava il caso inverso: la
**rimozione** di un erede. Aggiunto il ramo `else` che lancia
`HeirNotFoundException` anche quando la will porta ancora un erede che non e piu
presente nel set di eredi corrente. Cosi la ricostruzione dell'eredita scatta su
**Check** e alla **chiusura di Electrum** (entrambi usano lo stesso percorso
`BalBuildWillDialog.build_will_task()`), come deciso dall'utente: nessun
aggiornamento automatico dopo la modifica, solo manuale con Check / alla
chiusura.

### FIX 2 - Check interroga i server anche per le will gia inviate
`core/will.py` (nuovo `Will.needs_server_check(w)`) e
`gui/qt/lists.py` (`PreviewList.check`): prima il Check interrogava i server solo
per le will in stato `PUSHED`. Le will gia inviate ma rimaste su "New / Not sent"
non venivano ricontrollate ("nothing to do"). Ora `needs_server_check` include
ogni will **VALID** con un will-executor e **non ancora CHECKED**, anche se non
in stato `PUSHED`. Stesso controllo usato sia dal pulsante Check sia da
`on_close`.

### FIX 3 - Hide invalidated/replaced da finestra Impostazioni aggiornava la lista
`core/plugin_base.py` (nuovo `sync_hide_filters()`) e
`gui/qt/window.py` (`update_all`): le checkbox "Hide Replaced" / "Hide
Invalidated" nella finestra Impostazioni scrivono direttamente la config
(`BalConfig.set`) senza toccare i flag in cache `_hide_invalidated` /
`_hide_replaced` usati dalla lista per filtrare. Risultato: la lista continuava
a filtrare col valore vecchio finche non si riavviava Electrum. Ora
`update_all()` chiama `sync_hide_filters()` che ri-legge i flag dalla config,
quindi qualunque sorgente del cambiamento (toolbar o finestra Impostazioni)
aggiorna subito la lista.

### Rifinitura UI - Risultati in grassetto nel dialog "Building Will"
`gui/qt/dialogs.py` (`BalBuildWillDialog`): i **risultati** mostrati a destra di
ogni riga di stato (es. `Ok`, `Ko`, `Nothing to do`, `Skipped`, `Wait`,
`Timeout`) sono ora resi in **grassetto**, mantenendo i loro colori
(verde/rosso/giallo). Le etichette di stato a sinistra restano in peso normale.
Modifica centralizzata negli helper `msg_ok`, `msg_error`, `msg_warning`,
`msg_set_status`, piu le righe dei will-executor (push e check) che ora mostrano
`Ok/Ko` e `True/False` in grassetto + colore (verde/rosso).

### Test
- 186 test ufficiali passano; smoke test, external-zip test e simulazione dei
  flussi di aggiornamento (`tests/sim_update_flows.py`) OK; `ruff` senza nuove
  segnalazioni reali (solo falsi positivi pre-esistenti da star-import).
- Aggiunti test in `tests/test_core_will.py`:
  `test_check_heirs_unchanged_is_coherent`,
  `test_check_heir_removed_triggers_rebuild`,
  `test_check_heir_added_triggers_rebuild`, `test_needs_server_check`.

Confermato dall'utente sui dati reali: dopo Sign -> Broadcast -> Check le
transazioni gia inviate sono tornate verdi ("confirmed on server"); la lista
torna pulita; il grassetto e l'aggiornamento delle hide-flag funzionano.
