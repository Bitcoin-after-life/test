import json
import time
from datetime import datetime

from aiohttp import ClientResponse
from electrum.i18n import _
from electrum.logging import get_logger
from electrum.network import Network

from .bal import BalPlugin

DEFAULT_TIMEOUT = 5
_logger = get_logger(__name__)


chainname = BalPlugin.chainname


class Willexecutors:

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
        method, url, data=None, *, timeout=10, handle_response=None, count_reply=0
    ):
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
            if count_reply < 10:
                _logger.debug(f"timeout({count_reply}) error: retry in 3 sec...")
                time.sleep(3)
                return Willexecutors.send_request(
                    method,
                    url,
                    data,
                    timeout=timeout,
                    handle_response=handle_response,
                    count_reply=count_reply + 1,
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
    def push_transactions_to_willexecutor(willexecutor):
        out = True
        try:
            _logger.debug(f"{willexecutor['url']}: {willexecutor['txs']}")
            if w := Willexecutors.send_request(
                "post",
                willexecutor["url"] + "/" + chainname + "/pushtxs",
                data=willexecutor["txs"].encode("ascii"),
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
    def get_info_task(url, willexecutor):
        w = None
        try:
            _logger.info("GETINFO_WILLEXECUTOR")
            _logger.debug(url)
            w = Willexecutors.send_request("get", url + "/" + chainname + "/info")
            if isinstance(w, dict):
                willexecutor["url"] = url
                willexecutor["status"] = 200
                willexecutor["base_fee"] = w["base_fee"]
                willexecutor["address"] = w["address"]
                willexecutor["info"] = w["info"]
            _logger.debug(f"response_data {w}")
        except Exception as e:
            _logger.error(f"error {e} contacting {url}: {w}")
            willexecutor["status"] = "KO"

        willexecutor["last_update"] = datetime.now().timestamp()
        return willexecutor

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
    def check_transaction(txid, url):
        _logger.debug(f"{url}:{txid}")
        try:
            w = Willexecutors.send_request(
                "post", url + "/searchtx", data=txid.encode("ascii")
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
