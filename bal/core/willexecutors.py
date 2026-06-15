"""
bal.core.willexecutors
=======================

Client logic for talking to *will-executor* servers.

A will-executor is an optional third-party service that, for a small fee,
stores the signed inheritance transactions off-line and broadcasts them once
their locktime expires (acting as a dead-man's switch backup).

This module only contains the networking / data-shaping logic (downloading the
server list, pinging servers for their fee and address, pushing transactions,
checking whether a tx is already stored).  It is GUI-free: all user
interaction is handled by the Qt layer.
"""

import json
import time
from datetime import datetime

from aiohttp import ClientResponse
from electrum.i18n import _
from electrum.logging import get_logger
from electrum.network import Network

from .plugin_base import BalPlugin

# Per-request timeout (seconds) for interactive operations (ping / info /
# list download).  These fail fast (no retries) so a dead server does not
# block the UI.
DEFAULT_TIMEOUT = 5

# Broadcast (pushtxs) timeouts.  Broadcasting a will is important, so we keep a
# couple of quick retries to survive a transient hiccup -- but far from the old
# 10s x 10 retries + 30s sleeps (~140s) that froze the wizard on a dead server.
# Worst case per server is now ~ PUSH_TIMEOUT * (1 + PUSH_MAX_RETRIES)
# + PUSH_RETRY_SLEEP * PUSH_MAX_RETRIES = 8 * 3 + 1 * 2 = ~26s, and the wizard
# also enforces a global deadline on top of this (see push_transactions_parallel).
PUSH_TIMEOUT = 8
PUSH_MAX_RETRIES = 2
PUSH_RETRY_SLEEP = 1

# Global wall-clock deadline (seconds) for the whole parallel broadcast.  Once
# it elapses we stop waiting for the still-pending servers, mark them as
# "Timeout" and let the wizard proceed instead of appearing stuck.
PUSH_GLOBAL_DEADLINE = 30

# Check (searchtx) timeouts.  Used when the user presses "Check" to verify that
# each will-executor still holds the transaction.  Like the broadcast path, the
# old defaults (10s x 10 retries + 30s sleeps ~= 140s per server) froze the
# "checking transaction" dialog on a single dead server.  Fail fast with one
# quick retry, and cap the whole batch with a global deadline.
CHECK_TIMEOUT = 8
CHECK_MAX_RETRIES = 1
CHECK_RETRY_SLEEP = 1
CHECK_GLOBAL_DEADLINE = 30

_logger = get_logger(__name__)


chainname = BalPlugin.chainname


class Willexecutors:

    # Expose the networking constants as class attributes so the GUI layer can
    # reference them (e.g. to show the "Xs / DEADLINEs" countdown) without
    # importing module-level names.  Single source of truth: the module
    # constants defined above.
    DEFAULT_TIMEOUT = DEFAULT_TIMEOUT
    PUSH_TIMEOUT = PUSH_TIMEOUT
    PUSH_MAX_RETRIES = PUSH_MAX_RETRIES
    PUSH_RETRY_SLEEP = PUSH_RETRY_SLEEP
    PUSH_GLOBAL_DEADLINE = PUSH_GLOBAL_DEADLINE
    CHECK_TIMEOUT = CHECK_TIMEOUT
    CHECK_MAX_RETRIES = CHECK_MAX_RETRIES
    CHECK_RETRY_SLEEP = CHECK_RETRY_SLEEP
    CHECK_GLOBAL_DEADLINE = CHECK_GLOBAL_DEADLINE

    @staticmethod
    def save(bal_plugin, willexecutors):
        _logger.debug(f"save {willexecutors},{chainname}")
        aw = bal_plugin.WILLEXECUTORS.get()
        aw[chainname] = willexecutors
        bal_plugin.WILLEXECUTORS.set(aw)
        _logger.debug(f"saved: {aw}")
        # bal_plugin.WILLEXECUTORS.set(willexecutors)

    @staticmethod
    def get_willexecutors(
        bal_plugin, update=False, bal_window=False, force=False, task=True
    ):
        willexecutors = bal_plugin.WILLEXECUTORS.get()
        willexecutors = willexecutors.get(chainname, {})
        to_del = []
        for w in willexecutors:
            if not isinstance(willexecutors[w], dict):
                to_del.append(w)
                continue
            Willexecutors.initialize_willexecutor(willexecutors[w], w)
        for w in to_del:
            _logger.error(
                "error Willexecutor to delete type:{} {}".format(
                    type(willexecutors[w]), w
                )
            )
            del willexecutors[w]
        bal = bal_plugin.WILLEXECUTORS.default.get(chainname, {})
        for bal_url, bal_executor in bal.items():
            if bal_url not in willexecutors:
                _logger.debug(f"force add {bal_url} willexecutor")
                willexecutors[bal_url] = bal_executor
        # if update:
        #    found = False
        #    for url, we in willexecutors.items():
        #        if Willexecutors.is_selected(we):
        #            found = True
        #    if found or force:
        #        if bal_plugin.PING_WILLEXECUTORS.get() or force:
        #            ping_willexecutors = True
        #            if bal_plugin.ASK_PING_WILLEXECUTORS.get() and not force:
        #                if bal_window:
        #                    ping_willexecutors = bal_window.window.question(
        #                        _(
        #                            "Contact willexecutors servers to update payment informations?"
        #                        )
        #                    )

        #            if ping_willexecutors:
        #                if task:
        #                    bal_window.ping_willexecutors(willexecutors, task)
        #                else:
        #                    bal_window.ping_willexecutors_task(willexecutors)
        w_sorted = dict(
            sorted(
                willexecutors.items(), key=lambda w: w[1].get("sort", 0), reverse=True
            )
        )
        return w_sorted

    @staticmethod
    def is_selected(willexecutor, value=None):
        if not willexecutor:
            return False
        if value is not None:
            willexecutor["selected"] = value
        try:
            return willexecutor["selected"]
        except Exception:
            willexecutor["selected"] = False
            return False

    @staticmethod
    def get_willexecutor_transactions(will, force=False):
        willexecutors = {}
        for wid, willitem in will.items():
            if willitem.get_status("VALID"):
                if willitem.get_status("COMPLETE"):
                    if not willitem.get_status("PUSHED") or force:
                        if willexecutor := willitem.we:
                            url = willexecutor["url"]
                            if willexecutor and Willexecutors.is_selected(willexecutor):
                                if url not in willexecutors:
                                    willexecutor["txs"] = ""
                                    willexecutor["txsids"] = []
                                    willexecutor["broadcast_status"] = _("Waiting...")
                                    willexecutors[url] = willexecutor
                                willexecutors[url]["txs"] += str(willitem.tx) + "\n"
                                willexecutors[url]["txsids"].append(wid)

        return willexecutors

    # def only_selected_list(willexecutors):
    #    out = {}
    #    for url, v in willexecutors.items():
    #        if Willexecutors.is_selected(url):
    #            out[url] = v

    # def push_transactions_to_willexecutors(will):
    #    willexecutors = Willexecutors.get_transactions_to_be_pushed()
    #    for url in willexecutors:
    #        willexecutor = willexecutors[url]
    #        if Willexecutors.is_selected(willexecutor):
    #            if "txs" in willexecutor:
    #                Willexecutors.push_transactions_to_willexecutor(
    #                    willexecutors[url]["txs"], url
    #                )

    @staticmethod
    def send_request(
        method, url, data=None, *, timeout=10, handle_response=None, count_reply=0,
        max_retries=10, retry_sleep=3,
    ):
        """Send an HTTP request to a will-executor server.

        ``max_retries`` / ``retry_sleep`` control the timeout-retry behaviour:

        * For *critical* operations (pushing inheritance transactions) the
          historical default of up to 10 retries with a 3s back-off is kept, so
          a transient network hiccup does not lose a transaction.
        * For *interactive* operations (ping / info / list download) callers
          should pass ``max_retries=0`` so a dead server fails fast (one short
          timeout) instead of blocking the UI for minutes.  See
          :meth:`ping_servers_parallel`.
        """
        network = Network.get_instance()
        if not network:
            raise Exception("You are offline.")
        _logger.debug(f"<-- {method} {url} {data}")
        headers = {}
        headers["user-agent"] = f"BalPlugin v:{BalPlugin.__version__}"
        headers["Content-Type"] = "text/plain"
        if not handle_response:
            handle_response = Willexecutors.handle_response
        try:
            if method == "get":
                response = Network.send_http_on_proxy(
                    method,
                    url,
                    params=data,
                    headers=headers,
                    on_finish=handle_response,
                    timeout=timeout,
                )
            elif method == "post":
                response = Network.send_http_on_proxy(
                    method,
                    url,
                    body=data,
                    headers=headers,
                    on_finish=handle_response,
                    timeout=timeout,
                )
            else:
                raise Exception(f"unexpected {method=!r}")
        except TimeoutError:
            if count_reply < max_retries:
                _logger.debug(
                    f"timeout({count_reply}) error: retry in {retry_sleep} sec..."
                )
                if retry_sleep:
                    time.sleep(retry_sleep)
                return Willexecutors.send_request(
                    method,
                    url,
                    data,
                    timeout=timeout,
                    handle_response=handle_response,
                    count_reply=count_reply + 1,
                    max_retries=max_retries,
                    retry_sleep=retry_sleep,
                )
            else:
                _logger.debug(f"Too many timeouts: {count_reply}")
        except Exception as e:
            raise e
        else:
            _logger.debug(f"--> {response}")
            return response

    @staticmethod
    def get_we_url_from_response(resp):
        url_slices = str(resp.url).split("/")
        if len(url_slices) > 2:
            url_slices = url_slices[:-2]
        return "/".join(url_slices)

    @staticmethod
    async def handle_response(resp: ClientResponse):
        r = await resp.text()
        try:

            r = json.loads(r)
            # url = Willexecutors.get_we_url_from_response(resp)
            # r["url"]= url
            # r["status"]=resp.status
        except Exception as e:
            _logger.debug(f"error handling response:{e}")
            pass
        return r

    @staticmethod
    class AlreadyPresentException(Exception):
        pass

    @staticmethod
    def push_transactions_to_willexecutor(
        willexecutor, *, timeout=PUSH_TIMEOUT, max_retries=PUSH_MAX_RETRIES,
        retry_sleep=PUSH_RETRY_SLEEP,
    ):
        # ``timeout`` / ``max_retries`` / ``retry_sleep`` are forwarded to
        # send_request so the broadcast fails fast on a dead/slow server instead
        # of hanging for ~140s (the old default was 10s timeout x 10 retries +
        # 30s of sleeps).  A small number of quick retries still protects
        # against a transient hiccup without freezing the wizard.
        out = True
        try:
            _logger.debug(f"{willexecutor['url']}: {willexecutor['txs']}")
            if w := Willexecutors.send_request(
                "post",
                willexecutor["url"] + "/" + chainname + "/pushtxs",
                data=willexecutor["txs"].encode("ascii"),
                timeout=timeout,
                max_retries=max_retries,
                retry_sleep=retry_sleep,
            ):
                willexecutor["broadcast_status"] = _("Success")
                _logger.debug(f"pushed: {w}")
                if w != "thx":
                    _logger.debug(f"error: {w}")
                    raise Exception(w)
            else:
                raise Exception("empty reply from:{willexecutor['url']}")
        except Exception as e:
            _logger.debug(f"error:{e}")
            if str(e) == "already present":
                raise Willexecutors.AlreadyPresentException()
            out = False
            willexecutor["broadcast_status"] = _("Failed")

        return out

    @staticmethod
    def ping_servers(willexecutors):
        for url, we in willexecutors.items():
            Willexecutors.get_info_task(url, we)

    @staticmethod
    def get_info_task(url, willexecutor, *, timeout=DEFAULT_TIMEOUT,
                      max_retries=0, retry_sleep=0):
        w = None
        try:
            _logger.info("GETINFO_WILLEXECUTOR")
            _logger.debug(url)
            # Fast-fail by default (max_retries=0): a dead server returns after a
            # single short timeout instead of retrying 10x with sleeps, which
            # used to freeze the UI for minutes per unreachable server.
            w = Willexecutors.send_request(
                "get", url + "/" + chainname + "/info",
                timeout=timeout, max_retries=max_retries, retry_sleep=retry_sleep,
            )
            if isinstance(w, dict):
                willexecutor["url"] = url
                willexecutor["status"] = 200
                willexecutor["base_fee"] = w["base_fee"]
                willexecutor["address"] = w["address"]
                willexecutor["info"] = w["info"]
            else:
                # No dict reply (timeout / empty) -> mark as unreachable.
                willexecutor["status"] = "KO"
            _logger.debug(f"response_data {w}")
        except Exception as e:
            _logger.error(f"error {e} contacting {url}: {w}")
            willexecutor["status"] = "KO"

        willexecutor["last_update"] = datetime.now().timestamp()
        return willexecutor

    @staticmethod
    def ping_servers_parallel(willexecutors, *, on_each=None, max_workers=8,
                              timeout=DEFAULT_TIMEOUT, on_tick=None,
                              tick_interval=1.0):
        """Ping every will-executor concurrently and report results as they
        arrive.

        Network requests run in a thread pool: each ``send_http_on_proxy`` call
        schedules its coroutine on Electrum's shared asyncio loop and blocks
        only its *own* worker thread, so the total wall-clock time is roughly
        that of the slowest server rather than the *sum* of all of them.  A
        single dead server can no longer stall the whole batch.

        Args:
            willexecutors: ``{url: we_dict}`` mapping (mutated in place with the
                ping result, exactly like the old sequential ``ping_servers``).
            on_each: optional ``callback(url, we_dict, ok: bool)`` invoked from a
                worker thread each time a server answers (or fails), so the GUI
                can update its list live.  Must be thread-safe / marshalled to
                the GUI thread by the caller.
            max_workers: maximum number of concurrent pings.
            timeout: per-request timeout in seconds (fast-fail, no retries).

            on_tick: optional ``callback()`` invoked periodically (every
                ``tick_interval`` seconds) **from the calling thread** while
                waiting for servers, so a Qt caller can refresh an elapsed-time
                counter from the same thread that drives ``on_each``.

        Returns:
            The same ``willexecutors`` mapping, updated in place.
        """
        from concurrent.futures import ThreadPoolExecutor, wait
        from concurrent.futures import FIRST_COMPLETED

        items = list(willexecutors.items())
        if not items:
            return willexecutors

        def _ping_one(url, we):
            we = Willexecutors.get_info_task(
                url, we, timeout=timeout, max_retries=0, retry_sleep=0
            )
            ok = we.get("status") == 200
            return url, we, ok

        def _fire_tick():
            if on_tick is not None:
                try:
                    on_tick()
                except Exception as cb_err:
                    _logger.error(f"ping on_tick callback error: {cb_err}")

        workers = max(1, min(max_workers, len(items)))
        # Manual pool (no ``with``) so we can poll futures in short slices and
        # drive ``on_tick`` from THIS thread between waits (reliable Qt repaint).
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bal-ping")
        futures = {pool.submit(_ping_one, url, we) for url, we in items}
        try:
            pending = set(futures)
            while pending:
                done, pending = wait(
                    pending, timeout=tick_interval, return_when=FIRST_COMPLETED
                )
                for fut in done:
                    try:
                        url, we, ok = fut.result()
                    except Exception as e:  # defensive: one server never crashes all
                        _logger.error(f"ping_servers_parallel worker error: {e}")
                        continue
                    willexecutors[url] = we
                    if on_each is not None:
                        try:
                            on_each(url, we, ok)
                        except Exception as cb_err:
                            _logger.error(f"ping on_each callback error: {cb_err}")
                # Drive the elapsed-time counter from the calling thread.
                _fire_tick()
        finally:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
        return willexecutors

    @staticmethod
    def push_transactions_parallel(willexecutors, *, on_each=None, max_workers=8,
                                   deadline=PUSH_GLOBAL_DEADLINE, on_timeout=None,
                                   on_tick=None, tick_interval=1.0):
        """Push transactions to multiple will-executors concurrently.

        Like :meth:`ping_servers_parallel` but for the ``pushtxs`` operation.
        Each server keeps a short retry behaviour
        (:meth:`push_transactions_to_willexecutor`) so a real transaction is not
        lost to a transient hiccup, but servers are contacted in parallel and
        results are reported via ``on_each(url, we_dict, ok, exc)`` as they
        complete.

        A global wall-clock ``deadline`` (seconds) caps the whole operation: if
        some servers are still pending when it elapses, we stop waiting, mark
        them via ``on_timeout(url, we_dict)`` and return, so the caller (the
        wizard) is never stuck behind one unresponsive server.  Pass
        ``deadline=None`` to wait indefinitely (old behaviour).

        ``on_tick()`` is invoked periodically (every ``tick_interval`` seconds)
        **from the calling thread** while waiting for workers.  This lets a Qt
        caller refresh an elapsed-time counter from the same thread that drives
        ``on_each`` (so its pyqtSignal repaints reliably), instead of relying on
        a separate heartbeat thread whose signal emissions are not marshalled.

        Returns ``{url: (ok, exception_or_None)}`` for the servers that
        answered in time (timed-out servers are reported via ``on_timeout``).
        """
        from concurrent.futures import ThreadPoolExecutor, wait
        from concurrent.futures import FIRST_COMPLETED

        targets = [(url, we) for url, we in willexecutors.items() if "txs" in we]
        results = {}
        if not targets:
            return results

        def _push_one(url, we):
            try:
                ok = Willexecutors.push_transactions_to_willexecutor(we)
                return url, we, ok, None
            except Willexecutors.AlreadyPresentException as ape:
                return url, we, False, ape
            except Exception as e:
                return url, we, False, e

        def _fire_tick():
            if on_tick is not None:
                try:
                    on_tick()
                except Exception as cb_err:
                    _logger.error(f"push on_tick callback error: {cb_err}")

        workers = max(1, min(max_workers, len(targets)))
        # NOTE: we do not use ``with ThreadPoolExecutor(...)`` here because its
        # __exit__ calls shutdown(wait=True), which would block on a hung worker
        # and defeat the whole point of the global deadline.  We shut the pool
        # down without waiting once the deadline elapses; the daemon worker(s)
        # stuck on a dead socket will be torn down when their request finally
        # times out (PUSH_TIMEOUT), without holding up the wizard.
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bal-push")
        fut_to_url = {pool.submit(_push_one, url, we): (url, we)
                      for url, we in targets}
        start = time.time()
        try:
            # Poll the futures in short slices so we can call ``on_tick`` from
            # THIS thread between waits.  ``wait(..., timeout=tick_interval)``
            # returns as soon as a future completes OR the slice elapses,
            # whichever comes first, so the counter advances ~once per second
            # while the parallel push runs.
            pending = set(fut_to_url.keys())
            while pending:
                if deadline is not None and (time.time() - start) >= deadline:
                    break
                slice_timeout = tick_interval
                if deadline is not None:
                    remaining = deadline - (time.time() - start)
                    slice_timeout = max(0.0, min(tick_interval, remaining))
                done, pending = wait(
                    pending, timeout=slice_timeout, return_when=FIRST_COMPLETED
                )
                for fut in done:
                    try:
                        url, we, ok, exc = fut.result()
                    except Exception as e:
                        _logger.error(
                            f"push_transactions_parallel worker error: {e}"
                        )
                        continue
                    results[url] = (ok, exc)
                    if on_each is not None:
                        try:
                            on_each(url, we, ok, exc)
                        except Exception as cb_err:
                            _logger.error(f"push on_each callback error: {cb_err}")
                # Drive the elapsed-time counter from the calling thread.
                _fire_tick()
            # Any server still pending here hit the global deadline.
            if pending:
                elapsed = time.time() - start
                _logger.warning(
                    f"push global deadline ({deadline}s) reached after "
                    f"{elapsed:.1f}s; {len(pending)} server(s) "
                    f"did not answer in time"
                )
                for fut in pending:
                    url, we = fut_to_url[fut]
                    if url in results:
                        continue
                    if on_timeout is not None:
                        try:
                            on_timeout(url, we)
                        except Exception as cb_err:
                            _logger.error(
                                f"push on_timeout callback error: {cb_err}"
                            )
        finally:
            # Do not block on still-running workers (Python 3.9+: cancel queued).
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
        return results

    @staticmethod
    def check_transactions_parallel(items, *, on_each=None, max_workers=8,
                                    deadline=CHECK_GLOBAL_DEADLINE,
                                    on_timeout=None, on_tick=None,
                                    tick_interval=1.0):
        """Check (searchtx) several will-executors concurrently.

        Same design as :meth:`push_transactions_parallel`, but for the "Check"
        operation: it verifies that each will-executor still holds its
        transaction.  ``items`` is an iterable of ``(wid, url)`` pairs (one per
        will-item that has a will-executor).

        Each server is contacted in parallel with a short fail-fast retry
        (:meth:`check_transaction`), results are reported via
        ``on_each(wid, url, result_or_None, exc)`` as they arrive, ``on_tick()``
        is called periodically from the calling thread to refresh a counter, and
        a global ``deadline`` guarantees the dialog never freezes behind one
        unresponsive server (pending servers are reported via
        ``on_timeout(wid, url)``).

        Returns ``{wid: (result_or_None, exception_or_None)}`` for the servers
        that answered in time.
        """
        from concurrent.futures import ThreadPoolExecutor, wait
        from concurrent.futures import FIRST_COMPLETED

        targets = [(wid, url) for wid, url in items if url]
        results = {}
        if not targets:
            return results

        def _check_one(wid, url):
            try:
                res = Willexecutors.check_transaction(wid, url)
                return wid, url, res, None
            except Exception as e:
                return wid, url, None, e

        def _fire_tick():
            if on_tick is not None:
                try:
                    on_tick()
                except Exception as cb_err:
                    _logger.error(f"check on_tick callback error: {cb_err}")

        workers = max(1, min(max_workers, len(targets)))
        # Manual pool (no ``with``): we must not block on a hung worker when the
        # global deadline elapses (see push_transactions_parallel for details).
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bal-check")
        fut_to_target = {pool.submit(_check_one, wid, url): (wid, url)
                         for wid, url in targets}
        start = time.time()
        try:
            pending = set(fut_to_target.keys())
            while pending:
                if deadline is not None and (time.time() - start) >= deadline:
                    break
                slice_timeout = tick_interval
                if deadline is not None:
                    remaining = deadline - (time.time() - start)
                    slice_timeout = max(0.0, min(tick_interval, remaining))
                done, pending = wait(
                    pending, timeout=slice_timeout, return_when=FIRST_COMPLETED
                )
                for fut in done:
                    try:
                        wid, url, res, exc = fut.result()
                    except Exception as e:
                        _logger.error(
                            f"check_transactions_parallel worker error: {e}"
                        )
                        continue
                    results[wid] = (res, exc)
                    if on_each is not None:
                        try:
                            on_each(wid, url, res, exc)
                        except Exception as cb_err:
                            _logger.error(f"check on_each callback error: {cb_err}")
                # Drive the elapsed-time counter from the calling thread.
                _fire_tick()
            # Any server still pending here hit the global deadline.
            if pending:
                elapsed = time.time() - start
                _logger.warning(
                    f"check global deadline ({deadline}s) reached after "
                    f"{elapsed:.1f}s; {len(pending)} server(s) "
                    f"did not answer in time"
                )
                for fut in pending:
                    wid, url = fut_to_target[fut]
                    if wid in results:
                        continue
                    if on_timeout is not None:
                        try:
                            on_timeout(wid, url)
                        except Exception as cb_err:
                            _logger.error(
                                f"check on_timeout callback error: {cb_err}"
                            )
        finally:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
        return results

    @staticmethod
    def initialize_willexecutor(willexecutor, url, status=None, old_willexecutor=None):
        old_willexecutor=old_willexecutor if old_willexecutor is not None else {}
        willexecutor["url"] = url
        if status is not None:
            willexecutor["status"] = status
        else:
            willexecutor["status"] = old_willexecutor.get("status",willexecutor.get("status","Ko"))
        willexecutor["selected"]=Willexecutors.is_selected(old_willexecutor) or willexecutor.get("selected",False)
        willexecutor["address"]=old_willexecutor.get("address",willexecutor.get("address",""))
        willexecutor["promo_code"]=old_willexecutor.get("promo_code",willexecutor.get("promo_code"))



    @staticmethod
    def download_list(old_willexecutors,welist_server):
        try:
            welist_server = welist_server if welist_server[-1] == '/' else welist_server+'/'
            willexecutors = Willexecutors.send_request(
                "get",
                f"{welist_server}data/{chainname}?page=0&limit=100",
            )
            # del willexecutors["status"]
            for w in willexecutors:
                if w not in ("status", "url"):
                    Willexecutors.initialize_willexecutor(
                        willexecutors[w], w, None, old_willexecutors.get(w,None)
                    )
            # bal_plugin.WILLEXECUTORS.set(l)
            # bal_plugin.config.set_key(bal_plugin.WILLEXECUTORS,l,save=True)
            return willexecutors

        except Exception as e:
            _logger.error(f"Failed to download willexecutors list: {e}")
            return {}

    @staticmethod
    def get_willexecutors_list_from_json():
        try:
            with open("willexecutors.json") as f:
                willexecutors = json.load(f)
                for w in willexecutors:
                    willexecutor = willexecutors[w]
                    Willexecutors.initialize_willexecutor(willexecutor, w, "New", False)
                # bal_plugin.WILLEXECUTORS.set(willexecutors)
                return willexecutors
        except Exception as e:
            _logger.error(f"error opening willexecutors json: {e}")

            return {}

    @staticmethod
    def check_transaction(txid, url, *, timeout=CHECK_TIMEOUT,
                          max_retries=CHECK_MAX_RETRIES,
                          retry_sleep=CHECK_RETRY_SLEEP):
        _logger.debug(f"{url}:{txid}")
        try:
            w = Willexecutors.send_request(
                "post", url + "/searchtx", data=txid.encode("ascii"),
                timeout=timeout, max_retries=max_retries, retry_sleep=retry_sleep,
            )
            return w
        except Exception as e:
            _logger.error(f"error contacting {url} for checking txs {e}")
            raise e

    @staticmethod
    def compute_id(willexecutor):
        return "{}-{}".format(willexecutor.get("url"), willexecutor.get("chain"))


#class WillExecutor:
#    def __init__(
#        self,
#        url,
#        base_fee,
#        chain,
#        info,
#        version,
#        status,
#        is_selected=False,
#        promo_code="",
#    ):
#        self.url = url
#        self.base_fee = base_fee
#        self.chain = chain
#        self.info = info
#        self.version = version
#        self.status = status
#        self.promo_code = promo_code
#        self.is_selected = is_selected
#        self.id = self.compute_id()
#
#    def from_dict(d):
#        return WillExecutor(
#            url=d.get("url", "http://localhost:8000"),
#            base_fee=d.get("base_fee", 1000),
#            chain=d.get("chain", chainname),
#            info=d.get("info", ""),
#            version=d.get("version", 0),
#            status=d.get("status", "Ko"),
#            is_selected=d.get("is_selected", "False"),
#            promo_code=d.get("promo_code", ""),
#        )
#
#    def to_dict(self):
#        return {
#            "url": self.url,
#            "base_fee": self.base_fee,
#            "chain": self.chain,
#            "info": self.info,
#            "version": self.version,
#            "promo_code": self.promo_code,
#        }
#
#    def compute_id(self):
#        return f"{self.url}-{self.chain}"
