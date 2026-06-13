"""
bal.core.util
=============

Small, stateless helper functions shared across the whole plugin.

This module is intentionally GUI-free: it only deals with locktimes, amount
encoding/decoding, and comparing transactions / inputs / outputs / heirs.

Historical note
---------------
The original ``util.py`` also contained a set of ``print_*`` debugging helpers
(``print_var``, ``print_utxo``, ``print_prevout``) that dumped objects to
``stdout``.  Those were development-only scaffolding, never called by the
plugin logic, so they have been removed during the rewrite.  No behavioural
function has been changed: every method below is logically identical to the
original implementation.
"""

import bisect
from datetime import datetime, timedelta

from electrum.transaction import PartialTxOutput

# Bitcoin consensus rule: an nLockTime value strictly below this threshold is
# interpreted as a *block height*, otherwise it is interpreted as a *UNIX
# timestamp*.  This single constant drives most of the locktime handling below.
LOCKTIME_THRESHOLD = 500000000


class Util:
    """Namespace of static helpers (kept as a class to preserve the original
    ``Util.method(...)`` call sites used throughout the plugin)."""

    # ------------------------------------------------------------------ #
    # Locktime helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def locktime_to_str(locktime):
        """Render a locktime for display.

        If the value looks like a timestamp (``> LOCKTIME_THRESHOLD``) it is
        formatted as an ISO date string; otherwise it is returned as-is.
        """
        try:
            locktime = int(locktime)
            if locktime > LOCKTIME_THRESHOLD:
                dt = datetime.fromtimestamp(locktime).isoformat()
                return dt

        except Exception:
            pass
        return str(locktime)

    @staticmethod
    def str_to_locktime(locktime):
        """Parse a user-entered locktime string into its stored form.

        Relative values keep their suffix (``"30d"``, ``"1y"``, ``"144b"``);
        absolute ISO dates are converted to an integer UNIX timestamp.
        """
        try:
            if locktime[-1] in ("y", "d", "b"):
                return locktime
            else:
                return int(locktime)
        except Exception:
            pass
        dt_object = datetime.fromisoformat(locktime)
        timestamp = dt_object.timestamp()
        return int(timestamp)

    @staticmethod
    def parse_locktime_string(locktime, w=None):
        """Resolve a (possibly relative) locktime string into a concrete int.

        Supported forms:
            * plain int / timestamp -> returned unchanged
            * ``"<n>y"``            -> n years from now (as a timestamp)
            * ``"<n>d"``            -> n days from now (as a timestamp)
            * ``"<n>b"``            -> current block height + n (needs wallet
                                       ``w`` to read the chain height)
        """
        try:
            return int(locktime)

        except Exception:
            pass
        try:
            now = datetime.now()
            if locktime[-1] == "y":
                locktime = str(int(locktime[:-1]) * 365) + "d"
            if locktime[-1] == "d":
                return int(
                    (now + timedelta(days=int(locktime[:-1])))
                    .replace(hour=0, minute=0, second=0, microsecond=0)
                    .timestamp()
                )
            if locktime[-1] == "b":
                locktime = int(locktime[:-1])
                height = 0
                if w:
                    height = Util.get_current_height(w.network)
                locktime += int(height)
            return int(locktime)
        except Exception:
            pass
        return 0

    @staticmethod
    def int_locktime(seconds=0, minutes=0, hours=0, days=0, blocks=0):
        """Convert a human duration into seconds (blocks counted as 600s each)."""
        return int(
            seconds
            + minutes * 60
            + hours * 60 * 60
            + days * 60 * 60 * 24
            + blocks * 600
        )

    # ------------------------------------------------------------------ #
    # Amount helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def encode_amount(amount, decimal_point):
        """Convert a displayed BTC amount into integer satoshis.

        Percentage amounts (e.g. ``"50%"``) are passed through unchanged, since
        they are resolved later against the wallet balance.
        """
        if Util.is_perc(amount):
            return amount
        else:
            try:
                return int(float(amount) * pow(10, decimal_point))
            except Exception:
                return 0

    @staticmethod
    def decode_amount(amount, decimal_point):
        """Inverse of :meth:`encode_amount`: satoshis -> displayed string."""
        if Util.is_perc(amount):
            return amount
        else:
            basestr = "{{:0.{}f}}".format(decimal_point)
            try:
                return basestr.format(float(amount) / pow(10, decimal_point))
            except Exception:
                return str(amount)

    @staticmethod
    def is_perc(value):
        """True if ``value`` is a percentage string such as ``"25%"``."""
        try:
            return value[-1] == "%"
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Heir / will-executor comparison helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def cmp_array(heira, heirb):
        """Element-wise equality of two sequences (length-safe)."""
        try:
            if len(heira) != len(heirb):
                return False
            for h in range(0, len(heira)):
                if heira[h] != heirb[h]:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def cmp_heir(heira, heirb):
        """Two heirs are "the same" when address (0) and amount (1) match."""
        if heira[0] == heirb[0] and heira[1] == heirb[1]:
            return True
        return False

    @staticmethod
    def cmp_willexecutor(willexecutora, willexecutorb):
        """Compare two will-executor dicts by url / address / base_fee."""
        if willexecutora == willexecutorb:
            return True
        try:
            if (
                willexecutora["url"] == willexecutorb["url"]
                and willexecutora["address"] == willexecutorb["address"]
                and willexecutora["base_fee"] == willexecutorb["base_fee"]
            ):
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def search_heir_by_values(heirs, heir, values):
        """Return the key of the first heir in ``heirs`` matching ``heir`` on
        every column listed in ``values`` (or ``False`` if none)."""
        for h, v in heirs.items():
            found = False
            for val in values:
                if val in v and v[val] != heir[val]:
                    found = True

            if not found:
                return h
        return False

    @staticmethod
    def cmp_heir_by_values(heira, heirb, values):
        """True when two heirs agree on every column index in ``values``."""
        for v in values:
            if heira[v] != heirb[v]:
                return False
        return True

    @staticmethod
    def cmp_heirs_by_values(
        heirsa, heirsb, values, exclude_willexecutors=False, reverse=True
    ):
        """Set-equality of two heir collections, comparing only ``values``.

        When ``exclude_willexecutors`` is set, synthetic will-executor heirs
        (those whose key contains the ``w!ll3x3c"`` marker) are skipped.  The
        ``reverse`` flag makes the comparison symmetric by running it both ways.
        """
        for heira in heirsa:
            if (
                exclude_willexecutors and 'w!ll3x3c"' not in heira
            ) or not exclude_willexecutors:
                found = False
                for heirb in heirsb:
                    if Util.cmp_heir_by_values(heirsa[heira], heirsb[heirb], values):
                        found = True
                if not found:
                    return False
        if reverse:
            return Util.cmp_heirs_by_values(
                heirsb,
                heirsa,
                values,
                exclude_willexecutors=exclude_willexecutors,
                reverse=False,
            )
        else:
            return True

    @staticmethod
    def cmp_heirs(
        heirsa,
        heirsb,
        cmp_function=lambda x, y: x[0] == y[0] and x[3] == y[3],
        reverse=True,
    ):
        """Compare two heir collections using a custom ``cmp_function``.

        Will-executor entries are ignored.  As with
        :meth:`cmp_heirs_by_values`, ``reverse`` makes the relation symmetric.
        """
        try:
            for heir in heirsa:
                if 'w!ll3x3c"' not in heir:
                    if heir not in heirsb or not cmp_function(
                        heirsa[heir], heirsb[heir]
                    ):
                        if not Util.search_heir_by_values(heirsb, heirsa[heir], [0, 3]):
                            return False
            if reverse:
                return Util.cmp_heirs(heirsb, heirsa, cmp_function, False)
            else:
                return True
        except Exception as e:
            raise e

    # ------------------------------------------------------------------ #
    # Transaction input/output comparison helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def cmp_inputs(inputsa, inputsb):
        """True when both input lists reference the same set of UTXOs."""
        if len(inputsa) != len(inputsb):
            return False
        for inputa in inputsa:
            if not Util.in_utxo(inputa, inputsb):
                return False
        return True

    @staticmethod
    def cmp_outputs(outputsa, outputsb, willexecutor_output=None):
        """True when both output lists contain the same (address, value) pairs.

        The optional ``willexecutor_output`` is treated as a wildcard match so
        that the will-executor's fee output does not break the comparison.
        """
        if len(outputsa) != len(outputsb):
            return False
        for outputa in outputsa:
            if not Util.cmp_output(outputa, willexecutor_output):
                if not Util.in_output(outputa, outputsb):
                    return False
        return True

    @staticmethod
    def cmp_txs(txa, txb):
        """Two transactions are equivalent when their inputs and outputs match."""
        if not Util.cmp_inputs(txa.inputs(), txb.inputs()):
            return False
        if not Util.cmp_outputs(txa.outputs(), txb.outputs()):
            return False
        return True

    @staticmethod
    def get_value_amount(txa, txb):
        """Sum of the values of outputs that appear (same addr+value) in both
        transactions.  Returns ``False`` as soon as an output of ``txa`` shares
        neither amount nor address with any output of ``txb``."""
        outputsa = txa.outputs()
        value_amount = 0

        for outa in outputsa:
            same_amount, same_address = Util.in_output(outa, txb.outputs())
            if not (same_amount or same_address):
                return False
            if same_amount and same_address:
                value_amount += outa.value
            if same_amount:
                pass
            if same_address:
                pass

        return value_amount

    # ------------------------------------------------------------------ #
    # Locktime arithmetic
    # ------------------------------------------------------------------ #
    @staticmethod
    def chk_locktime(timestamp_to_check, block_height_to_check, locktime):
        """Return True if ``locktime`` is still in the future.

        Timestamp-style and block-height-style locktimes are compared against
        the respective "to_check" reference value.
        """
        # TODO BUG:  WHAT HAPPEN AT THRESHOLD?
        locktime = int(locktime)
        if locktime > LOCKTIME_THRESHOLD and locktime > timestamp_to_check:
            return True
        elif locktime < LOCKTIME_THRESHOLD and locktime > block_height_to_check:
            return True
        else:
            return False

    @staticmethod
    def anticipate_locktime(locktime, blocks=0, hours=0, days=0):
        """Move a locktime earlier by the given amount.

        Works on both timestamp and block-height locktimes; never returns a
        value below 1.
        """
        locktime = int(locktime)
        out = 0
        if locktime > LOCKTIME_THRESHOLD:
            seconds = blocks * 600 + hours * 3600 + days * 86400
            # On Windows datetime.fromtimestamp raises OverflowError past 2038
            # (e.g. NLOCKTIME_MAX); clamp to INT32_MAX (Electrum issue #6170).
            try:
                dt = datetime.fromtimestamp(locktime)
            except (OverflowError, OSError, ValueError):
                dt = datetime.fromtimestamp(min(locktime, 2 ** 31 - 1))
            dt -= timedelta(seconds=seconds)
            out = dt.timestamp()
        else:
            blocks -= hours * 6 + days * 144
            out = locktime + blocks

        if out < 1:
            out = 1
        return out

    @staticmethod
    def cmp_locktime(locktimea, locktimeb):
        """Compare two relative locktime strings sharing the same unit."""
        if locktimea == locktimeb:
            return 0
        strlocktimea = str(locktimea)
        strlocktimeb = str(locktimeb)
        if locktimea[-1] in "ydb":
            if locktimeb[-1] == locktimea[-1]:
                return int(strlocktimea[-1]) - int(strlocktimeb[-1])
            else:
                return int(locktimea) - (locktimeb)

    @staticmethod
    def get_lowest_valid_tx(available_utxos, will):
        """Placeholder kept from the original code (sorts the will by locktime)."""
        will = sorted(will.items(), key=lambda x: x[1]["tx"].locktime)
        for txid, willitem in will.items():
            pass

    @staticmethod
    def get_locktimes(will):
        """Return the distinct locktimes used by the transactions in ``will``."""
        locktimes = {}
        for txid, willitem in will.items():
            locktimes[willitem["tx"].locktime] = True
        return locktimes.keys()

    @staticmethod
    def get_lowest_locktimes(locktimes):
        """Split a list of locktimes into (sorted_timestamps, sorted_blocks)."""
        sorted_timestamp = []
        sorted_block = []
        for locktime in locktimes:
            locktime = Util.parse_locktime_string(locktime)
            if locktime < LOCKTIME_THRESHOLD:
                bisect.insort(sorted_block, locktime)
            else:
                bisect.insort(sorted_timestamp, locktime)

        return sorted(sorted_timestamp), sorted(sorted_block)

    @staticmethod
    def get_lowest_locktimes_from_will(will):
        """Convenience wrapper: lowest locktimes directly from a will dict."""
        return Util.get_lowest_locktimes(Util.get_locktimes(will))

    @staticmethod
    def search_willtx_per_io(will, tx):
        """Find a will entry whose tx has the same inputs/outputs as ``tx``."""
        for wid, w in will.items():
            if Util.cmp_txs(w["tx"], tx["tx"]):
                return wid, w
        return None, None

    @staticmethod
    def invalidate_will(will):
        raise Exception("not implemented")

    @staticmethod
    def get_will_spent_utxos(will):
        """Collect every input spent by any transaction in ``will``."""
        utxos = []
        for txid, willitem in will.items():
            utxos += willitem["tx"].inputs()

        return utxos

    # ------------------------------------------------------------------ #
    # UTXO helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def utxo_to_str(utxo):
        """Best-effort conversion of a UTXO / input object to its ``txid:n`` str."""
        try:
            return utxo.to_str()
        except Exception:
            pass
        try:
            return utxo.prevout.to_str()
        except Exception:
            pass
        return str(utxo)

    @staticmethod
    def cmp_utxo(utxoa, utxob):
        """True when two UTXOs refer to the same outpoint."""
        utxoa = Util.utxo_to_str(utxoa)
        utxob = Util.utxo_to_str(utxob)
        if utxoa == utxob:
            return True
        else:
            return False

    @staticmethod
    def in_utxo(utxo, utxos):
        """Membership test for a UTXO inside an iterable of UTXOs."""
        for s_u in utxos:
            if Util.cmp_utxo(s_u, utxo):
                return True
        return False

    @staticmethod
    def txid_in_utxo(txid, utxos):
        """True if any UTXO in ``utxos`` is spent from transaction ``txid``."""
        for s_u in utxos:
            if s_u.prevout.txid == txid:
                return True
        return False

    @staticmethod
    def cmp_output(outputa, outputb):
        """Two outputs are equal when both address and value match."""
        return outputa.address == outputb.address and outputa.value == outputb.value

    @staticmethod
    def in_output(output, outputs):
        """Membership test for an output inside an iterable of outputs."""
        for s_o in outputs:
            if Util.cmp_output(s_o, output):
                return True
        return False

    # check all output with the same amount if none have the same address it can be a change
    # return true true same address same amount
    # return true false same amount different address
    # return false false different amount, different address not found
    @staticmethod
    def din_output(out, outputs):
        """Detailed output lookup used to tell a change output apart.

        Returns a ``(same_amount, same_address)`` tuple:
            * ``(True, True)``  -> an output with same amount *and* address
            * ``(True, False)`` -> same amount but different address (maybe change)
            * ``(False, False)``-> no output with this amount
        """
        same_amount = []
        for s_o in outputs:
            if int(out.value) == int(s_o.value):
                same_amount.append(s_o)
                if out.address == s_o.address:
                    return True, True
                else:
                    pass

        if len(same_amount) > 0:
            return True, False
        else:
            return False, False

    @staticmethod
    def get_change_output(wallet, in_amount, out_amount, fee):
        """Build a change ``PartialTxOutput`` if the leftover exceeds dust."""
        change_amount = int(in_amount - out_amount - fee)
        if change_amount > wallet.dust_threshold():
            change_addresses = wallet.get_change_addresses_for_new_transaction()
            out = PartialTxOutput.from_address_and_value(
                change_addresses[0], change_amount
            )
            out.is_change = True
            return out

    @staticmethod
    def get_current_height(network):
        """Return a conservative current block height for locktime purposes.

        Mirrors Electrum's own anti-fee-sniping logic: if there is no network,
        the chain tip is stale, or the main server lags too far behind the
        SPV-checked height, it gives up and returns 0.
        """
        # if no network or not up to date, just set locktime to zero
        if not network:
            return 0
        chain = network.blockchain()
        if chain.is_tip_stale():
            return 0
        # figure out current block height
        chain_height = chain.height()  # learnt from all connected servers, SPV-checked
        server_height = (
            network.get_server_height()
        )  # height claimed by main server, unverified
        # note: main server might be lagging (either is slow, is malicious, or there is an SPV-invisible-hard-fork)
        #       - if it's lagging too much, it is the network's job to switch away
        if server_height < chain_height - 10:
            # the diff is suspiciously large... give up and use something non-fingerprintable
            return 0
        # discourage "fee sniping"
        height = min(chain_height, server_height)
        return height

    # ------------------------------------------------------------------ #
    # Misc helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def copy(dicto, dictfrom):
        """Shallow copy of ``dictfrom`` entries into ``dicto`` (in place)."""
        for k, v in dictfrom.items():
            dicto[k] = v

    @staticmethod
    def fix_will_settings_tx_fees(will_settings):
        """Migrate the legacy ``tx_fees`` key to ``baltx_fees`` in settings.

        Returns True when a migration was performed (caller should persist).
        """
        tx_fees = will_settings.get("tx_fees", False)
        have_to_update = False
        if tx_fees:
            will_settings["baltx_fees"] = tx_fees
            del will_settings["tx_fees"]
            have_to_update = True
        return have_to_update

    @staticmethod
    def fix_will_tx_fees(will):
        """Same legacy migration as above but applied to every will entry."""
        have_to_update = False
        for txid, willitem in will.items():
            tx_fees = willitem.get("tx_fees", False)
            if tx_fees:
                will[txid]["baltx_fees"] = tx_fees
                del will[txid]["tx_fees"]
                have_to_update = True
        return have_to_update

    @staticmethod
    def text_to_hex(text: str) -> str:
        """Convert text to a hexadecimal string (used for OP_RETURN payloads)."""
        hex_string = text.encode('utf-8').hex()
        return hex_string

    @staticmethod
    def hex_to_text(hex_string: str) -> str:
        """Convert a hexadecimal string back to text (for verification)."""
        try:
            return bytes.fromhex(hex_string).decode('utf-8')
        except Exception:
            return "Error: Invalid hex string"
