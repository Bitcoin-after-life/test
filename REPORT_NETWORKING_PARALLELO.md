# Report tecnico — Networking parallelo (anti-freeze Will-Executor)

**Destinatario:** programmatore esterno / manutentore del plugin
**Autore:** refactoring AI (lavoro su GitHub `Bitcoin-after-life/test`)
**Data:** 2026-06-15
**Branch:** `feature/networking-parallelo`
**Repository Gitea privato `kaibot/bal-plugin-ai`: NON modificato** (per richiesta esplicita).

---

## 1. Problema

Quando il plugin contatta i server Will-Executor (invio transazioni, ping/aggiornamento
eredità, download lista), lo fa **in sequenza**. Se un server non risponde, il thread
resta bloccato sui timeout di connessione e, peggio, sui **retry**:

- `send_request` riprovava fino a **10 volte** con `time.sleep(3)` ad ogni timeout
  → circa **130 secondi per ogni server irraggiungibile**, sommati uno dopo l'altro.

Conseguenze:
- Con pochi server già si avverte; con **20 server** diventa ingestibile.
- L'utente vede "Rimani in attesa — Non risponde" senza capire cosa succede.
- Un singolo server morto blocca l'intera operazione.

---

## 2. Soluzione (in sintesi)

1. **Parallelismo** con `ThreadPoolExecutor`: i server vengono contattati
   contemporaneamente. Il tempo totale ≈ server **più lento**, non la **somma**.
2. **Fast-fail** per le operazioni interattive (ping/info/download): niente retry-storm,
   un solo timeout breve e il server viene marcato "KO".
3. **Feedback live**: callback `on_each(...)` che aggiorna la finestra di attesa
   server-per-server, in modo thread-safe.
4. **Push transazioni**: parallelo, ma mantiene i retry per ogni singolo server
   (una transazione reale non deve andare persa per un hiccup transitorio).

### Perché è thread-safe
`Network.send_http_on_proxy()` usa `asyncio.run_coroutine_threadsafe(coro, loop)` e poi
`coro.result()`: ogni chiamata schedula la propria coroutine sullo stesso loop asyncio
condiviso di Electrum e blocca **solo il proprio worker thread**. Più chiamate
concorrenti sono quindi sicure → `ThreadPoolExecutor` dà vero parallelismo.

Gli aggiornamenti UI passano per `BalWaitingDialog.update()` che emette un
`pyqtSignal` → marshalling automatico sul thread GUI. I callback dai worker thread
possono quindi aggiornare il dialog in sicurezza.

---

## 3. File modificati (tutto su GitHub `Bitcoin-after-life/test`, branch `feature/networking-parallelo`)

### 3.1 `bal/core/willexecutors.py`

**`send_request(...)`** — aggiunti due parametri keyword-only:
```python
def send_request(method, url, data=None, *, timeout=10, handle_response=None,
                 count_reply=0, max_retries=10, retry_sleep=3):
```
- `max_retries` / `retry_sleep` controllano i retry sui timeout.
- **Default invariato** (`10` / `3s`) → il push critico mantiene il comportamento storico.
- Le operazioni interattive passano `max_retries=0` → fast-fail.

**`get_info_task(...)`** — fast-fail di default:
```python
def get_info_task(url, willexecutor, *, timeout=DEFAULT_TIMEOUT,
                  max_retries=0, retry_sleep=0):
```
- Se la risposta non è un `dict` (timeout/vuoto) → `status="KO"`.

**NUOVO `ping_servers_parallel(willexecutors, *, on_each=None, max_workers=8, timeout=DEFAULT_TIMEOUT)`**
- `ThreadPoolExecutor` + `as_completed`; un worker per server (`_ping_one`).
- Muta `willexecutors` in place (come il vecchio `ping_servers`).
- Invoca `on_each(url, we, ok)` man mano che arrivano i risultati.
- Un worker che esplode non blocca gli altri (try/except difensivo).

**NUOVO `push_transactions_parallel(willexecutors, *, on_each=None, max_workers=8)`**
- Push in parallelo solo verso le voci con chiave `"txs"`.
- Ogni server mantiene i propri retry (`push_transactions_to_willexecutor`).
- `on_each(url, we, ok, exc)`; raccoglie `AlreadyPresentException` separatamente.
- Ritorna `{url: (ok, exc)}`.

**`DEFAULT_TIMEOUT = 5`** (costante a livello di modulo).

### 3.2 `bal/gui/qt/window.py`

- **`ping_willexecutors_task(self, wes)`** riscritto su `ping_servers_parallel(...)`
  con feedback live (set `pinged`/`failed`, `get_title()` mostra "Ok"/"Ko"/"waiting...").
- **`push_transactions_to_willexecutors(self, force=False)`** riscritto su
  `push_transactions_parallel(...)`. `on_each` fa book-keeping + update UI thread-safe;
  i server "already present" sono raccolti in `already_present[]` e il loro
  `check_transaction` viene eseguito dopo, nel task thread (logica di check originale intatta).
- **`fetch_will_executors_list(...)`** download fast-fail:
  `send_request("get", url, timeout=10, max_retries=1, retry_sleep=1)`.

### 3.3 `bal/core/util.py` — BUGFIX (regressione pre-esistente)

In `get_value_amount` (riga 324) era stato erroneamente usato `Util.in_output(...)`
(ritorna `bool`) al posto di `Util.din_output(...)` (ritorna la tupla
`(same_amount, same_address)`), causando:
```
TypeError: cannot unpack non-iterable bool object
```
**Corretto** ripristinando `din_output`. Bug scoperto eseguendo i test ufficiali del
repo Gitea (`tests/test_core_util.py::test_get_value_amount`).

---

## 4. Verifica (ruff + test ufficiali)

### 4.1 ruff (lint / PEP8)
- `ruff check` sul codice nuovo: **nessun nuovo problema** introdotto
  (i `F403/F405/F401` presenti derivano dal pattern `from .common import *`
  dell'originale; conteggio identico HEAD vs working tree: 121 = 121).
- Le funzioni parallele nuove rispettano il limite di 88 caratteri (0 `E501`).
- `ruff check tests/parallel_ping_test.py` → **All checks passed**.

### 4.2 Test ufficiali del repo Gitea `kaibot/bal-plugin-ai/tests`
Eseguiti contro il codice refactorizzato (con le modifiche networking):

| Suite | Esito |
|-------|-------|
| `test_core_*` (pytest) | **117 passed** |
| `test_gui_*` (pytest) | **65 passed** |
| `smoke_test.py` | OK |
| `external_zip_test.py` | OK |
| `windows_overflow_test.py` | OK |
| `gui_fixes_test.py` | OK |
| `parallel_ping_test.py` (nuovo) | OK — `0.50s` per 8 server (sequenziale ~`4.00s`) |

Comandi (come da README):
```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 -m pytest tests/ -q
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/smoke_test.py electrum.plugins.bal
QT_QPA_PLATFORM=offscreen PYTHONPATH=<electrum-src> \
    python3 tests/external_zip_test.py bal-electrum-plugin.zip
```

---

## 5. Note di integrazione / rischi

- **Nessuna modifica al protocollo server**: solo il *come* (parallelo) e il *quando*
  (retry) delle chiamate cambia, non i payload.
- **Push transazioni**: i retry per-server sono mantenuti apposta, per non perdere
  una transazione reale per un hiccup. Solo il ping/info/download usa fast-fail.
- **`max_workers=8`** è prudente; con molti server (es. 20) si può alzare, ma 8
  worker già abbattono il tempo totale al server più lento.
- **Thread/UI**: tutti gli aggiornamenti UI dai worker passano per
  `BalWaitingDialog.update()` (pyqtSignal) → safe. Non toccare quel canale.
- **Compatibilità**: firme retro-compatibili (i nuovi parametri sono keyword-only
  con default che preservano il vecchio comportamento).

---

## 6. Come provare

1. Installare lo zip `bal-electrum-plugin.zip` (Tools → Plugins → install from file).
2. Configurare più Will-Executor, includendone **almeno uno irraggiungibile**.
3. Lanciare invio transazioni / ping: il dialog mostra lo stato server-per-server
   e **non resta più bloccato** sul server morto.

SHA-256 dello zip stampato da `build_zip.py` a fine build (verificare l'integrità).
