# BAL — Diagnosi dei problemi GUI (Fase A) → ✅ RISOLTI (Fase B)

> **STATO: tutti i bug B1-B10 sono stati CORRETTI** sul branch
> `fix/gui-window-lifecycle`. La logica di business resta **byte-identica**
> (nessuna modifica a `bal/core/*`): sono cambiati solo presentazione, parent,
> modalità, ciclo di vita e cleanup delle finestre.
>
> | ID | Stato | Fix applicato |
> |----|-------|---------------|
> | B1 | ✅ FIXED | `self.parent` → `self._bal_parent` (dialogs/lists/widgets); parent = `top_level_of(parent)` |
> | B2 | ✅ FIXED | `.show()` → `show_on_top()` / `show_modal()` con parent corretto |
> | B3 | ✅ FIXED | init a caldo: `_setup_window()` replica `load_wallet`, niente "restart Electrum" |
> | B4 | ✅ FIXED | chiave finestra stabile `_window_key()` = `id(window)` |
> | B5 | ✅ FIXED | `on_close` riscritto: niente `except:pass`, log per-step, reset stato |
> | B6 | ✅ FIXED | `BalBlockingWaitingDialog`: `processEvents()` ripristinato |
> | B7 | ✅ FIXED | `closeEvent/hideEvent`: `stop_thread()` + `super()` |
> | B8 | ✅ FIXED | `closeEvent`: `stop_thread()` (stop+wait) + `super()` |
> | B9 | ✅ FIXED | `bring_to_front()` = `raise_()` + `activateWindow()` |
> | B10| ✅ FIXED | uso di `window.tools_menu` (API ufficiale), niente ricerca per titolo `&Tools` |
>
> Helper centralizzati in `bal/gui/qt/window_utils.py`:
> `top_level_of`, `bring_to_front`, `stop_thread`, `show_modal`, `show_on_top`.
> Test di regressione: `tests/gui_fixes_test.py` (oltre a smoke + external_zip).

---

## (Storico) Diagnosi originale

Documento di sola **diagnosi**: nessuna riga di codice funzionale era stata
modificata in Fase A. Elenca i problemi grafici/di ciclo di vita riscontrati nel
codice, la loro **causa tecnica** e il **fix proposto**, con riferimenti riga.

I due sintomi che hai segnalato:
- **(S1)** Le finestre del plugin spariscono dietro la finestra di Electrum.
- **(S2)** Alcuni meccanismi funzionano solo dopo aver chiuso e "ripulito"
  Electrum.

Sono entrambi spiegati dai bug qui sotto.

---

## Riepilogo (tabella)

| ID | Gravità | Sintomo | File:riga | Causa breve |
|----|---------|---------|-----------|-------------|
| B1 | 🔴 Alta | S1 | `dialogs.py:40,69,475` | `self.parent = parent` sovrascrive il metodo `QWidget.parent()` |
| B2 | 🔴 Alta | S1 | `window.py:148,936`, `window.py:566` | dialoghi aperti con `.show()` (non-modali, senza stare in primo piano) |
| B3 | 🔴 Alta | S2 | `plugin.py:38-42` | messaggio "Please restart Electrum" = init a caldo non gestito |
| B4 | 🔴 Alta | S2 | `plugin.py:45,111` | chiave dizionario `winId` (metodo) invece di `winId()` (valore) |
| B5 | 🟠 Media | S2 | `window.py:664-677` | `on_close` con `except: pass` che nasconde errori di cleanup |
| B6 | 🟠 Media | S1/S2 | `dialogs.py:445-462` | `BalBlockingWaitingDialog` blocca il thread GUI, `processEvents` commentato |
| B7 | 🟠 Media | S2 | `dialogs.py:48-58` | `closeEvent/hideEvent` con cleanup thread commentato |
| B8 | 🟠 Media | S2 | `dialogs.py:828-830` | `closeEvent` chiama `thread.stop()` ma non `thread.wait()` né `super()` |
| B9 | 🟡 Bassa | S1 | `dialogs.py:1121-1122` | `show()+raise_()` senza `activateWindow()` né modalità |
| B10| 🟡 Bassa | — | `plugin.py:36` (init), vari | gestione finestre multiple/ multi-wallet fragile |

---

## Dettaglio dei problemi

### B1 — `self.parent = parent` rompe il sistema di finestre di Qt 🔴
**Dove:** `dialogs.py:40` (in `BalDialog.__init__`), ripetuto a `:69` e `:475`;
analoghi in altri dialoghi.

```python
self.parent = parent          # <-- PROBLEMA
super().__init__(parent)
```

**Causa:** in Qt, `parent()` è un **metodo** di `QWidget` che restituisce il
widget genitore. Assegnando un **attributo** `self.parent`, lo si maschera: da
quel punto `self.parent` non è più il metodo ma il valore salvato. Qualunque
codice (anche interno a Qt o di Electrum) che si aspetta `widget.parent()` come
metodo può comportarsi in modo imprevisto. Inoltre il `parent` passato non è
sempre la **top-level window** corretta, quindi il dialogo non viene agganciato
gerarchicamente alla finestra di Electrum e finisce **dietro** (S1).

**Fix proposto:**
- Non sovrascrivere `parent`: rinominare l'attributo (es. `self._bal_parent`).
- Passare sempre come `parent` la **top-level window** di Electrum
  (`window.top_level_window()`), così il dialogo resta in primo piano rispetto
  ad essa.

---

### B2 — Dialoghi aperti con `.show()` invece che modali 🔴
**Dove:**
- `window.py:148` `show_willexecutor_dialog` → `self.willexecutor_dialog.show()`
- `window.py:936` `preview_modal_dialog` → `self.dw.show()` (il nome dice
  "modal" ma usa `show()`!)
- `window.py:566` `show_transaction_real` → `d.show()`

**Causa:** `show()` apre una finestra **non-modale e indipendente**: se il
`parent` non è impostato correttamente (vedi B1), la finestra non resta sopra
Electrum e ci "sparisce dietro" (S1). Si nota l'incoerenza: altrove si usa
correttamente `.exec()` (es. `init_wizard` a `window.py:144`, `settings_dialog`
a `plugin.py:254`), che è modale e resta in primo piano.

**Fix proposto:**
- Per i dialoghi che devono restare in primo piano: usare `exec()` (modale) **o**
  `show()` + parent corretto + `setWindowModality(Qt.WindowModal)` +
  `raise_()` + `activateWindow()`.
- Mantenere la stessa logica di "cosa fa il dialogo" (nessun cambio di
  comportamento funzionale, solo z-order/modalità).

---

### B3 — "Please restart Electrum to activate the BAL plugin" 🔴
**Dove:** `plugin.py:38-42` (hook `init_qt`).

```python
if wallet:
    window.show_warning(_("Please restart Electrum to activate the BAL plugin"), ...)
    return
```

**Causa:** quando il plugin viene **abilitato a caldo** (wallet già aperto),
l'hook `init_qt` si arrende e chiede il riavvio invece di inizializzare le tab
e i menu sul wallet già caricato. È **la causa diretta del sintomo S2**: "devi
chiudere/riavviare Electrum perché funzioni".

**Fix proposto:**
- In `init_qt`, se c'è già un wallet aperto, eseguire la stessa inizializzazione
  che normalmente avviene in `load_wallet` (creare `BalWindow`, tab, menu,
  caricare il will) **senza** richiedere il riavvio.
- Simmetricamente, gestire bene `close_wallet` per smontare tab/menu, così
  ri-abilitare/ricaricare non lascia stato sporco.

---

### B4 — Chiave del dizionario `winId` (metodo) invece di `winId()` 🔴
**Dove:** `plugin.py:45` (scrittura) e `plugin.py:111` (lettura).

```python
self.bal_windows[top_level_window.winId] = w   # scrive con la *funzione* winId
...
w = self.bal_windows.get(window.winId, None)   # legge con la *funzione* winId
```

**Causa:** `winId` senza parentesi è il **metodo legato** (bound method), non
l'identificatore della finestra. Usato come chiave "funziona per caso" perché
lo stesso oggetto-finestra produce lo stesso bound method; ma è fragile e
semanticamente errato: con più finestre/wallet o dopo riaperture la
corrispondenza può saltare, creando `BalWindow` duplicati o non trovando quello
giusto → stato incoerente (contribuisce a S2).

**Fix proposto:**
- Usare una chiave stabile e corretta, es. `int(window.winId())` oppure
  `id(window)`, in modo **coerente** sia in scrittura sia in lettura.

---

### B5 — `on_close` ingoia tutti gli errori 🟠
**Dove:** `window.py:664-677`.

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
        pass            # <-- nasconde qualsiasi errore di cleanup
```

**Causa:** se una qualsiasi di queste operazioni fallisce, l'eccezione viene
silenziata: tab/menu non vengono rimossi, lo stato (`willitems`, `heirs`, tab)
resta in memoria e "sporco" finché non si riavvia Electrum (S2).

**Fix proposto:**
- Non silenziare: loggare l'errore con `_logger`.
- Rendere il cleanup **robusto e idempotente** (ogni passo in un try/except
  separato con log), così un fallimento parziale non blocca gli altri passi.
- Azzerare esplicitamente lo stato (`willitems={}`, riferimenti a tab/menu a
  `None`) a fine `on_close`.

---

### B6 — `BalBlockingWaitingDialog` blocca il thread della GUI 🟠
**Dove:** `dialogs.py:445-462`.

```python
self.show()
# QCoreApplication.processEvents()   # <-- commentato
# QCoreApplication.processEvents()
try:
    task()        # esegue il task SUL thread GUI -> finestra "congelata"
finally:
    self.accept()
```

**Causa:** dopo `show()` non si dà alla GUI il tempo di disegnarsi
(`processEvents` è commentato) e poi si esegue `task()` **bloccando** il thread
dell'interfaccia. Risultato: la finestra "Please wait" può apparire vuota,
non ridisegnarsi, e l'app sembra bloccata (contribuisce a S1/percezione di
freeze).

**Fix proposto:**
- O eseguire il task in un `TaskThread` (come fa già `BalWaitingDialog`),
- oppure, se deve restare bloccante, ripristinare un `processEvents()` dopo
  `show()` per far disegnare la finestra prima del task.

---

### B7 — `closeEvent`/`hideEvent` con cleanup thread commentato 🟠
**Dove:** `dialogs.py:48-58` (`BalDialog`).

```python
def closeEvent(self, event):
    self._stopping = True
    #if self.thread:
    #    self.thread.stop()      # <-- disattivato
    super().closeEvent(event)
```

**Causa:** alla chiusura del dialogo i thread eventualmente attivi **non**
vengono fermati. Restano in esecuzione in background, possono scrivere su widget
già distrutti o tenere risorse/connessioni → comportamenti erratici finché non
si riavvia (S2).

**Fix proposto:**
- Ripristinare in modo sicuro lo stop dei thread: `if self.thread:
  self.thread.stop(); self.thread.wait()` con guardia su `None`.

---

### B8 — `BalBuildWillDialog.closeEvent` incompleto 🟠
**Dove:** `dialogs.py:828-830`.

```python
def closeEvent(self, event):
    self._stopping = True
    self.thread.stop()
    # manca self.thread.wait() e manca super().closeEvent(event)
```

**Causa:** `stop()` segnala lo stop ma non attende la fine del thread
(`wait()`), e non viene chiamato `super().closeEvent(event)`: l'evento di
chiusura non è propagato correttamente. Possibili thread orfani e finestre che
non si chiudono pulite.

**Fix proposto:**
- `self.thread.stop(); self.thread.wait(); super().closeEvent(event)` con
  guardia su `self.thread is None`.

---

### B9 — `show()+raise_()` senza `activateWindow()`/modalità 🟡
**Dove:** `dialogs.py:1121-1122` (es. `WillExecutorDialog`/dettaglio).

```python
self.show()
self.raise_()
# manca self.activateWindow(); nessuna modalità impostata
```

**Causa:** `raise_()` alza la finestra nello stack ma su alcuni window manager
(incluso Windows) senza `activateWindow()` non riceve il focus e può comunque
finire dietro. Senza modalità, l'utente può tornare alla finestra principale
lasciando il dialogo nascosto.

**Fix proposto:**
- Aggiungere `self.activateWindow()` dopo `raise_()`, e valutare
  `setWindowModality(Qt.WindowModal)` dove ha senso.

---

### B10 — Gestione finestre multiple / multi-wallet fragile 🟡
**Dove:** `plugin.py:30-62` (`init_qt`), `get_window` (`plugin.py:109-115`).

**Causa:** la mappa `bal_windows` e l'aggancio ai menu si basano su assunzioni
(B4) e sull'iterazione dei figli del menubar per nome (`"&Tools"`), che è
sensibile alla **localizzazione** (tu usi `Locale: Italian_Italy`!). Se il menu
non si chiama esattamente `&Tools` nella lingua corrente, l'aggancio può
fallire silenziosamente.

**Fix proposto:**
- Usare l'API ufficiale `window.tools_menu` (già usata in `init_menubar`,
  `plugin.py:79`) invece di cercare il menu per titolo tradotto.
- Unificare la creazione/lookup di `BalWindow` su una chiave stabile (B4).

---

## Strategia di correzione proposta (per la Fase B/C)

Per **non cambiare la logica di funzionamento** e ridurre i rischi, propongo di
introdurre un **unico punto centralizzato** di gestione finestre (un piccolo
helper, es. `gui/qt/window_utils.py`) con funzioni tipo:

- `show_modal(dialog)` → imposta parent corretto, modalità, `exec()`.
- `show_on_top(dialog)` → `show()` + `raise_()` + `activateWindow()` per i
  pochi casi che devono restare non-modali.

E poi sostituire i `.show()`/`.exec()` sparsi con queste funzioni. Vantaggi:
- la **logica di business resta intatta** (cosa fa il dialogo non cambia);
- si tocca **solo** il "come" viene mostrato/chiuso;
- più facile da testare e da revisionare (diff piccolo e localizzato).

### Ordine consigliato
1. **B3 + B4** (init a caldo + chiave finestre): risolvono la radice di S2.
2. **B1 + B2 + B9** (parent/modalità/z-order): risolvono S1.
3. **B5 + B7 + B8** (cleanup robusto + thread): chiudono i residui di S2.
4. **B6 + B10** (waiting dialog + menu localizzati): rifiniture.

---

## Cosa serve da te per la Fase B/C
- Conferma che posso modificare il **comportamento della GUI** (parent,
  modalità, cleanup, init a caldo) mantenendo invariata la logica di business.
- Test su **Electrum portable Windows** dopo ogni gruppo di fix, con descrizione
  /screenshot di cosa succede (apertura dialoghi, abilitazione a caldo,
  chiusura wallet).

> Nota: i bug B1–B10 esistono **identici nell'originale** — questo refactor li
> ha preservati fedelmente (era l'obiettivo della fase precedente). La Fase B/C
> li corregge.
