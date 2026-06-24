"""
bal.core.heirs
==============

Heir management and inheritance-transaction building.

This is the heart of the plugin's Bitcoin logic and the most delicate part of
the whole codebase, so the implementation below is kept byte-for-byte identical
to the original ``heirs.py``; only the dead commented-out imports were removed
and documentation was added.

An *heir* is stored as a small list addressed by the ``HEIR_*`` column
constants defined below.  ``Heirs`` is a ``dict`` subclass persisted inside the
wallet DB under the ``"heirs"`` key.

The ``prepare_transactions`` / ``Heirs.buildTransactions`` functions turn the
heir list plus the wallet UTXOs into a set of time-locked inheritance
transactions (optionally including a will-executor fee output).

Will-executor "heirs" are synthetic entries whose key starts with the
``w!ll3x3c"`` marker; they are skipped by most heir comparisons.
"""

import math
import random
import re
import threading
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    Tuple,
)

import dns
from dns.exception import DNSException
from electrum import (
    bitcoin,
    constants,
    dnssec,
)
from electrum.logging import Logger, get_logger
from electrum.transaction import (
    PartialTransaction,
    PartialTxInput,
    PartialTxOutput,
    TxOutpoint,
)
from electrum.util import (
    BitcoinException,
    bfh,
    read_json_file,
    to_string,
    trigger_callback,
    write_json_file,
)

from .util import Util
from .willexecutors import Willexecutors

if TYPE_CHECKING:
    from electrum.simple_config import SimpleConfig


_logger = get_logger(__name__)

# Column layout of a stored heir list.  These indices are part of the on-disk
# wallet format and are relied upon all over the codebase, so they must NEVER
# be reordered.
HEIR_ADDRESS = 0       # destination Bitcoin address
HEIR_AMOUNT = 1        # requested amount (satoshis or "<n>%")
HEIR_LOCKTIME = 2      # locktime after which the heir may claim the funds
HEIR_REAL_AMOUNT = 3   # resolved amount once percentages are computed
HEIR_DUST_AMOUNT = 4   # amount when below dust threshold (marked "DUST: ...")
TRANSACTION_LABEL = "inheritance transaction"


class AliasNotFoundException(Exception):
    pass


def reduce_outputs(in_amount, out_amount, fee, outputs):
    if in_amount < out_amount:
        for output in outputs:
            output.value = math.floor((in_amount - fee) / out_amount * output.value)


def create_op_return_script(data_hex: str) -> bytes:
    """Crea scriptpubkey OP_RETURN in bytes"""
    data = bytes.fromhex(data_hex)

    if len(data) > 80:
        raise ValueError("OP_RETURN data too big (max 80 bytes)")

    # Costruzione manuale: OP_RETURN + push data
    if len(data) <= 75:
        # Formato più comune: OP_RETURN + 1-byte length + data
        script = b'\x6a' + bytes([len(data)]) + data
    else:
        # Per dati più grandi (fino a 80) si usa OP_PUSHDATA1
        script = b'\x6a\x4c' + bytes([len(data)]) + data

    return script

def prepare_transactions(locktimes, available_utxos, fees, wallet):
    available_utxos = sorted(
        available_utxos,
        key=lambda x: "{}:{}:{}".format(
            x.value_sats(), x.prevout.txid, x.prevout.out_idx
        ),
    )
    # total_used_utxos = []
    txsout = {}
    locktime, _ = Util.get_lowest_locktimes(locktimes)
    if not locktime:
        _logger.info("prepare transactions, no locktime")
        return
    locktime = locktime[0]

    heirs = locktimes[locktime]
    true = True
    while true:
        true = False
        fee = fees.get(locktime, 0)
        out_amount = fee
        description = ""
        outputs = []
        paid_heirs = {}
        for name, heir in heirs.items():
            if len(heir) > HEIR_REAL_AMOUNT and "DUST" not in str(
                heir[HEIR_REAL_AMOUNT]
            ):
                try:
                    real_amount = heir[HEIR_REAL_AMOUNT]
                    outputs.append(
                        PartialTxOutput.from_address_and_value(
                            heir[HEIR_ADDRESS], real_amount
                        )
                    )
                    out_amount += real_amount
                    description += f"{name}\n"
                except BitcoinException as e:
                    _logger.info("exception decoding output {} - {}".format(type(e), e))
                    heir[HEIR_REAL_AMOUNT] = e

                except Exception as e:
                    heir[HEIR_REAL_AMOUNT] = e
                    _logger.error(f"error preparing transactions: {e}")
                    pass
            paid_heirs[name] = heir

        in_amount = 0.0
        used_utxos = []
        try:
            while utxo := available_utxos.pop():
                value = utxo.value_sats()
                in_amount += value
                used_utxos.append(utxo)
                if in_amount >= out_amount:
                    break

        except IndexError as e:
            _logger.error(
                f"error preparing transactions index error {e} {in_amount}, {out_amount}"
            )
            pass
        if int(in_amount) < int(out_amount):
            _logger.error(
                "error preparing transactions in_amount < out_amount ({} < {})      "
            )
            continue
        heirsvalue = out_amount
        change = get_change_output(wallet, in_amount, out_amount, fee)
        if change:
            outputs.append(change)
        for i in range(0, 100):
            random.shuffle(outputs)

        #op_return_text = "Hello Bal!"

        ## Convert text to hex
        #op_return_hex = op_return_text.encode('utf-8').hex()
        #op_return_script = create_op_return_script(op_return_hex)
        #outputs.append(PartialTxOutput(value=0, scriptpubkey=op_return_script))
        tx = PartialTransaction.from_io(
            used_utxos,
            outputs,
            locktime=Util.parse_locktime_string(locktime, wallet),
            version=2,
        )
        if len(description) > 0:
            tx.description = description[:-1]
        else:
            tx.description = ""
        tx.heirsvalue = heirsvalue
        tx.set_rbf(True)
        tx.remove_signatures()
        txid = tx.txid()
        if txid is None:
            raise Exception(f"txid is none: {tx}")

        tx.heirs = paid_heirs
        tx.my_locktime = locktime
        txsout[txid] = tx

        if change:
            change_idx = tx.get_output_idxs_from_address(change.address)
            prevout = TxOutpoint(txid=bfh(tx.txid()), out_idx=change_idx.pop())
            txin = PartialTxInput(prevout=prevout)
            txin._trusted_value_sats = change.value
            txin.script_descriptor = change.script_descriptor
            txin.is_mine = True
            txin._TxInput__address = change.address
            txin._TxInput__scriptpubkey = change.scriptpubkey
            txin._TxInput__value_sats = change.value
            txin.utxo = tx
            available_utxos.append(txin)
        txsout[txid].available_utxos = available_utxos[:]
    return txsout


def get_utxos_from_inputs(tx_inputs, tx, utxos):
    for tx_input in tx_inputs:
        prevoutstr = tx_input.prevout.to_str()
        utxos[prevoutstr] = utxos.get(prevoutstr, {"input": tx_input, "txs": []})
        utxos[prevoutstr]["txs"].append(tx)
    return utxos


# TODO calculate de minimum inputs to be invalidated
def invalidate_inheritance_transactions(wallet):
    # listids = []
    utxos = {}
    dtxs = {}
    for k, v in wallet.get_all_labels().items():
        tx = None
        if TRANSACTION_LABEL == v:
            tx = wallet.adb.get_transaction(k)
        if tx:
            dtxs[tx.txid()] = tx
            get_utxos_from_inputs(tx.inputs(), tx, utxos)

    for key, utxo in utxos.items():
        txid = key.split(":")[0]
        if txid in dtxs:
            for tx in utxo["txs"]:
                txid = tx.txid()
                del dtxs[txid]

    utxos = {}
    for txid, tx in dtxs.items():
        get_utxos_from_inputs(tx.inputs(), tx, utxos)

    utxos = sorted(utxos.items(), key=lambda item: len(item[1]))

    remaining = {}
    invalidated = []
    for key, value in utxos:
        for tx in value["txs"]:
            txid = tx.txid()
            if txid not in invalidated:
                invalidated.append(tx.txid())
                remaining[key] = value


def print_transaction(heirs, tx, locktimes, tx_fees):
    jtx = tx.to_json()
    print(f"TX: {tx.txid()}\t-\tLocktime: {jtx['locktime']}")
    print("---")
    for inp in jtx["inputs"]:
        print(f"{inp['address']}: {inp['value_sats']}")
    print("---")
    for out in jtx["outputs"]:
        heirname = ""
        for key in heirs.keys():
            heir = heirs[key]
            if heir[HEIR_ADDRESS] == out["address"] and str(heir[HEIR_LOCKTIME]) == str(
                jtx["locktime"]
            ):
                heirname = key
        print(f"{heirname}\t{out['address']}: {out['value_sats']}")

    print()
    size = tx.estimated_size()
    print(
        "fee: {}\texpected: {}\tsize: {}".format(
            tx.input_value() - tx.output_value(), size * tx_fees, size
        )
    )

    print()
    try:
        print(tx.serialize_to_network())
    except Exception:
        print("impossible to serialize")
    print()


def get_change_output(wallet, in_amount, out_amount, fee):
    change_amount = int(in_amount - out_amount - fee)
    if change_amount > wallet.dust_threshold():
        change_addresses = wallet.get_change_addresses_for_new_transaction()
        out = PartialTxOutput.from_address_and_value(change_addresses[0], change_amount)
        out.is_change = True
        return out


def _json_safe(value, _path="heirs", _depth=0):
    """Return a JSON-serializable deep copy of *value*.

    The wallet DB persists the heirs dict via ``json_db.put``, which calls
    ``copy.deepcopy`` on the value.  If any nested element is a live runtime
    object (e.g. one holding a ``threading.RLock``), deepcopy raises
    ``TypeError: cannot pickle '_thread.RLock' object`` and the whole
    "Build will" task fails.

    To make persistence robust we coerce the structure to plain
    JSON-compatible types (dict / list / str / int / float / bool / None).
    Anything else is converted to ``str(value)`` and logged with its path so
    the offending field can be identified, instead of crashing the task.
    """
    # Primitive JSON scalars are kept as-is.
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {
            str(k): _json_safe(v, "{}[{!r}]".format(_path, k), _depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _json_safe(v, "{}[{}]".format(_path, i), _depth + 1)
            for i, v in enumerate(value)
        ]
    # Unexpected runtime object: do not let it reach deepcopy.  Log where it
    # was found so the real source can be fixed, then store a safe string.
    _logger.error(
        "heirs.save: non-serializable value at {} (type={}); coercing to str. "
        "value={!r}".format(_path, type(value).__name__, value)
    )
    return str(value)


class Heirs(dict, Logger):

    def __init__(self, wallet):
        Logger.__init__(self)
        self.db = wallet.db
        self.wallet = wallet
        d = self.db.get("heirs", {})
        try:
            self.update(d)
        except Exception:
            return

    def invalidate_transactions(self, wallet):
        invalidate_inheritance_transactions(wallet)

    def save(self):
        # Sanitise the heirs mapping before handing it to the wallet DB: this
        # guarantees only JSON-serializable values are stored and prevents the
        # "cannot pickle '_thread.RLock' object" failure that aborted the
        # Build-will task when a runtime object slipped into an heir value.
        self.db.put("heirs", _json_safe(dict(self)))

    def import_file(self, path):
        data = read_json_file(path)
        data = Heirs._validate(data)
        self.update(data)
        self.save()

    def export_file(self, path):
        write_json_file(path, self)

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        self.save()

    def pop(self, key):
        if key in self.keys():
            res = dict.pop(self, key)
            self.save()
            return res

    def get_locktimes(self, from_locktime, a=False):
        locktimes = {}
        for key in self.keys():
            locktime = Util.parse_locktime_string(self[key][HEIR_LOCKTIME])
            if locktime > from_locktime and not a or locktime <= from_locktime and a:
                locktimes[int(locktime)] = None
        return list(locktimes.keys())

    def check_locktime(self):
        return False

    def normalize_perc(
        self, heir_list, total_balance, relative_balance, wallet, real=False
    ):
        amount = 0
        for key, v in heir_list.items():
            try:
                column = HEIR_AMOUNT
                if real:
                    column = HEIR_REAL_AMOUNT
                if "DUST" in str(v[column]):
                    column = HEIR_DUST_AMOUNT
                value = int(
                    math.floor(
                        total_balance
                        / relative_balance
                        * self.amount_to_float(v[column])
                    )
                )
                if value > wallet.dust_threshold():
                    heir_list[key].insert(HEIR_REAL_AMOUNT, value)
                    amount += value
                else:
                    heir_list[key].insert(HEIR_REAL_AMOUNT, f"DUST: {value}")
                    heir_list[key].insert(HEIR_DUST_AMOUNT, value)
                    _logger.info(f"{key}, {value} is dust will be ignored")

            except Exception as e:
                raise e
        return amount

    def amount_to_float(self, amount):
        try:
            return float(amount)
        except Exception:
            try:
                return float(amount[:-1])
            except Exception:
                return 0.0

    def fixed_percent_lists_amount(self, from_locktime, dust_threshold, reverse=False):
        fixed_heirs = {}
        fixed_amount = 0.0
        percent_heirs = {}
        percent_amount = 0.0
        fixed_amount_with_dust = 0.0
        for key in self.keys():
            try:
                cmp = (
                    Util.parse_locktime_string(self[key][HEIR_LOCKTIME]) - from_locktime
                )
                if cmp <= 0:
                    _logger.debug(
                        "cmp < 0 {} {} {} {}".format(
                            cmp, key, self[key][HEIR_LOCKTIME], from_locktime
                        )
                    )
                    continue
                if Util.is_perc(self[key][HEIR_AMOUNT]):
                    percent_amount += float(self[key][HEIR_AMOUNT][:-1])
                    percent_heirs[key] = list(self[key])
                else:
                    heir_amount = int(math.floor(float(self[key][HEIR_AMOUNT])))
                    fixed_amount_with_dust += heir_amount
                    fixed_heirs[key] = list(self[key])
                    if heir_amount > dust_threshold:
                        fixed_amount += heir_amount
                        fixed_heirs[key].insert(HEIR_REAL_AMOUNT, heir_amount)
                    else:
                        fixed_heirs[key] = list(self[key])
                        fixed_heirs[key].insert(
                            HEIR_REAL_AMOUNT, f"DUST: {heir_amount}"
                        )
                        fixed_heirs[key].insert(HEIR_DUST_AMOUNT, heir_amount)
            except Exception as e:
                _logger.error(e)
        return (
            fixed_heirs,
            fixed_amount,
            percent_heirs,
            percent_amount,
            fixed_amount_with_dust,
        )

    def prepare_lists(
        self, balance, total_fees, wallet, willexecutor=False, from_locktime=0
    ):
        if balance<total_fees or balance < wallet.dust_threshold():
            raise BalanceTooLowException(balance,wallet.dust_threshold(),total_fees)
        willexecutors_amount = 0
        willexecutors = {}
        heir_list = {}
        onlyfixed = False
        newbalance = balance - total_fees
        locktimes = self.get_locktimes(from_locktime)
        if willexecutor:
            for locktime in locktimes:
                if int(Util.int_locktime(locktime)) > int(from_locktime):
                    try:
                        base_fee = int(willexecutor["base_fee"])
                        willexecutors_amount += base_fee
                        h = [None] * 4
                        h[HEIR_AMOUNT] = base_fee
                        h[HEIR_REAL_AMOUNT] = base_fee
                        h[HEIR_LOCKTIME] = locktime
                        h[HEIR_ADDRESS] = willexecutor["address"]
                        willexecutors[
                            'w!ll3x3c"' + willexecutor["url"] + '"' + str(locktime)
                        ] = h
                    except Exception:
                        return [], False
                else:
                    _logger.error(
                        f"heir excluded from will locktime({locktime}){Util.int_locktime(locktime)}<minimum{from_locktime}"
                    ),
            heir_list.update(willexecutors)
            newbalance -= willexecutors_amount
            if newbalance < 0:
                raise WillExecutorFeeException(willexecutor)
        (
            fixed_heirs,
            fixed_amount,
            percent_heirs,
            percent_amount,
            fixed_amount_with_dust,
        ) = self.fixed_percent_lists_amount(from_locktime, wallet.dust_threshold())
        if fixed_amount > newbalance:
            fixed_amount = self.normalize_perc(
                fixed_heirs, newbalance, fixed_amount, wallet
            )
            onlyfixed = True

        heir_list.update(fixed_heirs)

        newbalance -= fixed_amount
        if newbalance > 0:
            perc_amount = self.normalize_perc(
                percent_heirs, newbalance, percent_amount, wallet
            )
            newbalance -= perc_amount
            heir_list.update(percent_heirs)
        if newbalance > 0:
            newbalance += fixed_amount
            fixed_amount = self.normalize_perc(
                fixed_heirs, newbalance, fixed_amount_with_dust, wallet, real=True
            )
            newbalance -= fixed_amount
            heir_list.update(fixed_heirs)

        heir_list = sorted(
            heir_list.items(),
            key=lambda item: Util.parse_locktime_string(item[1][HEIR_LOCKTIME], wallet),
        )

        locktimes = {}
        for key, value in heir_list:
            locktime = Util.parse_locktime_string(value[HEIR_LOCKTIME])
            if locktime not in locktimes:
                locktimes[locktime] = {key: value}
            else:
                locktimes[locktime][key] = value

        # ALL-DUST GUARD (owner request, see CHANGELOG / log analysis).
        #
        # WHY HERE: ``locktimes`` now contains EVERY heir across EVERY locktime,
        # with their final resolved amount already computed and dust-marked
        # ("DUST: <n>" in HEIR_REAL_AMOUNT) by fixed_percent_lists_amount /
        # normalize_perc above. This is the only place where we can reliably
        # tell whether *all* heirs are dust, for BOTH fixed and percentage
        # heirs and across all dates. ``prepare_transactions`` only sees the
        # single lowest locktime, so checking there would wrongly block a will
        # whose later locktimes still have valid heirs (false positive).
        #
        # WHAT: count the REAL heirs (excluding the internal will-executor
        # pseudo-heirs, whose names start with the reserved ``w!ll3x3c"``
        # marker) and how many of them have a valid, non-dust amount. If there
        # are real heirs but NONE of them is payable, the inheritance would pay
        # nobody (only the change + the will-executor fee). Previously such an
        # "empty" will was still built, signed, checked and listed; we now
        # refuse it and raise HeirAmountIsDustException so the GUI can show a
        # clear message and stop. A mix of dust + valid heirs keeps building
        # normally with the valid ones (unchanged behaviour).
        real_heirs = 0
        valid_real_heirs = 0
        for heirs_at_locktime in locktimes.values():
            for name, heir in heirs_at_locktime.items():
                if str(name).startswith('w!ll3x3c"'):
                    continue
                real_heirs += 1
                if len(heir) > HEIR_REAL_AMOUNT and "DUST" not in str(
                    heir[HEIR_REAL_AMOUNT]
                ):
                    valid_real_heirs += 1
        if real_heirs > 0 and valid_real_heirs == 0:
            raise HeirAmountIsDustException(
                "All heirs' shares are below the dust limit"
            )

        return locktimes, onlyfixed

    def is_perc(self, key):
        return Util.is_perc(self[key][HEIR_AMOUNT])

    def buildTransactions(
        self, bal_plugin, wallet, tx_fees=None, utxos=None, from_locktime=0
    ):
        Heirs._validate(self)
        if len(self) <= 0:
            _logger.info("while building transactions there was no heirs")
            return
        balance = 0.0
        len_utxo_set = 0
        available_utxos = []
        if not utxos:
            utxos = wallet.get_utxos()
        willexecutors = Willexecutors.get_willexecutors(bal_plugin) or {}
        self.decimal_point = bal_plugin.get_decimal_point()
        no_willexecutors = bal_plugin.NO_WILLEXECUTOR.get()
        for utxo in utxos:
            if utxo.value_sats() > 0 * tx_fees:
                balance += utxo.value_sats()
                len_utxo_set += 1
                available_utxos.append(utxo)
        if len_utxo_set == 0:
            _logger.info("no usable utxos")
            return
        j = -2
        willexecutorsitems = list(willexecutors.items())
        willexecutorslen = len(willexecutorsitems)
        alltxs = {}
        while True:
            j += 1
            if j >= willexecutorslen:
                break
            elif 0 <= j:
                url, willexecutor = willexecutorsitems[j]
                if not Willexecutors.is_selected(willexecutor) or willexecutor["base_fee"] < wallet.dust_threshold():
                    continue
                else:
                    willexecutor["url"] = url
            elif j == -1:
                if not no_willexecutors:
                    continue
                url = willexecutor = False
            else:
                break
            fees = {}
            i = 0
            while i < 10:
                txs = {}
                redo = False
                i += 1
                total_fees = 0
                for fee in fees:
                    total_fees += int(fees[fee])
                # newbalance = balance
                try:
                    locktimes, onlyfixed = self.prepare_lists(
                        balance, total_fees, wallet, willexecutor, from_locktime
                    )
                except WillExecutorFeeException:
                    i = 10
                    continue
                if locktimes:
                    try:
                        txs = prepare_transactions(
                            locktimes, available_utxos[:], fees, wallet
                        )
                        if not txs:
                            return {}
                    except Exception as e:
                        _logger.error(
                            f"build transactions: error preparing transactions: {e}"
                        )
                        try:
                            if "w!ll3x3c" in e.heirname:
                                Willexecutors.is_selected(
                                    e.heirname[len("w!ll3x3c") :], False
                                )
                                break
                        except Exception:
                            raise e
                    total_fees = 0
                    total_fees_real = 0
                    total_in = 0
                    for txid, tx in txs.items():
                        tx.willexecutor = willexecutor
                        fee = tx.estimated_size() * tx_fees
                        txs[txid].tx_fees = tx_fees
                        total_fees += fee
                        total_fees_real += tx.get_fee()
                        total_in += tx.input_value()
                        rfee = tx.input_value() - tx.output_value()
                        if rfee < fee or rfee > fee + wallet.dust_threshold():
                            redo = True
                        # oldfees = fees.get(tx.my_locktime, 0)
                        fees[tx.my_locktime] = fee

                    if balance - total_in > wallet.dust_threshold():
                        redo = True
                    if not redo:
                        break
                    if i >= 10:
                        break
                else:
                    _logger.info(
                        f"no locktimes for willexecutor {willexecutor} skipped"
                    )
                    break
            alltxs.update(txs)

        return alltxs

    def get_transactions(
        self, bal_plugin, wallet, tx_fees, utxos=None, from_locktime=0
    ):
        txs = self.buildTransactions(bal_plugin, wallet, tx_fees, utxos, from_locktime)
        if txs:
            temp_txs = {}
            for txid in txs:
                if txs[txid].available_utxos:
                    temp_txs.update(
                        self.get_transactions(
                            bal_plugin,
                            wallet,
                            tx_fees,
                            txs[txid].available_utxos,
                            txs[txid].locktime,
                        )
                    )
            txs.update(temp_txs)
        return txs

    def resolve(self, k):
        if bitcoin.is_address(k):
            return {"address": k, "type": "address"}
        if k in self.keys():
            _type, addr = self[k]
            if _type == "address":
                return {"address": addr, "type": "heir"}
        if openalias := self.resolve_openalias(k):
            return openalias
        raise AliasNotFoundException("Invalid Bitcoin address or alias", k)

    @classmethod
    def resolve_openalias(cls, url: str) -> Dict[str, Any]:
        out = cls._resolve_openalias(url)
        if out:
            address, name, validated = out
            return {
                "address": address,
                "name": name,
                "type": "openalias",
                "validated": validated,
            }
        return {}

    def by_name(self, name):
        for k in self.keys():
            _type, addr = self[k]
            if addr.casefold() == name.casefold():
                return {"name": addr, "type": _type, "address": k}
        return None

    def fetch_openalias(self, config: "SimpleConfig"):
        self.alias_info = None
        alias = config.OPENALIAS_ID
        if alias:
            alias = str(alias)

            def f():
                self.alias_info = self._resolve_openalias(alias)
                trigger_callback("alias_received")

            t = threading.Thread(target=f)
            t.daemon = True
            t.start()

    @classmethod
    def _resolve_openalias(cls, url: str) -> Optional[Tuple[str, str, bool]]:
        # support email-style addresses, per the OA standard
        url = url.replace("@", ".")
        try:
            records, validated = dnssec.query(url, dns.rdatatype.TXT)
        except DNSException as e:
            _logger.info(f"Error resolving openalias: {repr(e)}")
            return None
        prefix = "btc"
        for record in records:
            string = to_string(record.strings[0], "utf8")
            if string.startswith("oa1:" + prefix):
                address = cls.find_regex(string, r"recipient_address=([A-Za-z0-9]+)")
                name = cls.find_regex(string, r"recipient_name=([^;]+)")
                if not name:
                    name = address
                if not address:
                    continue
                return address, name, validated

    @staticmethod
    def find_regex(haystack, needle):
        regex = re.compile(needle)
        try:
            return regex.search(haystack).groups()[0]
        except AttributeError:
            return None

    def validate_address(address):
        if not bitcoin.is_address(address, net=constants.net):
            raise NotAnAddress(f"not an address,{address}")
        return address

    def validate_amount(amount):
        try:
            famount = float(amount[:-1]) if Util.is_perc(amount) else float(amount)
            if famount <= 0.00000001:
                raise AmountNotValid(f"amount have to be positive {famount} < 0")
        except Exception as e:
            raise AmountNotValid(f"amount not properly formatted, {e}")
        return amount

    def validate_locktime(locktime, timestamp_to_check=False):
        try:
            if timestamp_to_check:
                if Util.parse_locktime_string(locktime, None) < timestamp_to_check:
                    raise HeirExpiredException()
        except Exception as e:
            raise LocktimeNotValid(f"locktime string not properly formatted, {e}")
        return locktime

    def validate_heir(k, v, timestamp_to_check=False):
        address = Heirs.validate_address(v[HEIR_ADDRESS])
        amount = Heirs.validate_amount(v[HEIR_AMOUNT])
        locktime = Heirs.validate_locktime(v[HEIR_LOCKTIME], timestamp_to_check)
        return (address, amount, locktime)

    def _validate(data, timestamp_to_check=False):

        for k, v in list(data.items()):
            if k == "heirs":
                return Heirs._validate(v, timestamp_to_check)
            try:
                Heirs.validate_heir(k, v, timestamp_to_check)
            except Exception as e:
                _logger.info(f"exception heir removed {e}")
                data.pop(k)
        return data


class NotAnAddress(ValueError):
    pass


class AmountNotValid(ValueError):
    pass


class LocktimeNotValid(ValueError):
    pass


class HeirExpiredException(LocktimeNotValid):
    pass


class HeirAmountIsDustException(Exception):
    pass


class NoHeirsException(Exception):
    pass


class WillExecutorFeeException(Exception):
    def __init__(self, willexecutor):
        self.willexecutor = willexecutor

    def __str__(self):
        return "WillExecutorFeeException: {} fee:{}".format(
            self.willexecutor["url"], self.willexecutor["base_fee"]
        )
class BalanceTooLowException(Exception):
    def __init__(self,balance, dust_threshold, fees):
        self.balance=balance
        self.dust_threshold = dust_threshold
        self.fees = fees
    def __str__(self):
        return f"Balance too low, balance: {self.balance}, dust threshold: {self.dust_threshold}, fees: {self.fees}"
