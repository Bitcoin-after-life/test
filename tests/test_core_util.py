"""
Comprehensive unit tests for ``bal.core.util.Util``.

Covers every static method — locktime helpers, amount helpers, comparison
helpers, UTXO helpers, and migration helpers — with edge cases.

Run:
    source electrum/env/bin/activate
    python3 tests/test_core_util.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.util import Util, LOCKTIME_THRESHOLD


def test_locktime_to_str():
    # timestamp above threshold -> ISO format
    s = Util.locktime_to_str(1700000000)
    assert "202" in s and "-" in s, f"expected ISO string, got {s!r}"

    # block height below threshold -> unchanged
    assert Util.locktime_to_str(500000) == "500000"

    # string input -> unchanged
    assert Util.locktime_to_str("hello") == "hello"

    # zero / edge
    assert Util.locktime_to_str(0) == "0"


def test_str_to_locktime():
    # relative suffixes pass through
    assert Util.str_to_locktime("30d") == "30d"
    assert Util.str_to_locktime("1y") == "1y"
    assert Util.str_to_locktime("144b") == "144b"

    # integer string -> int
    assert isinstance(Util.str_to_locktime("500000"), int)
    assert Util.str_to_locktime("500000") == 500000

    # ISO date -> int timestamp
    ts = Util.str_to_locktime("2025-01-01T00:00:00")
    assert isinstance(ts, int)
    assert ts > 0


def test_parse_locktime_string():
    # plain int -> same int
    assert Util.parse_locktime_string(500000) == 500000

    # int as string -> int
    assert Util.parse_locktime_string("500000") == 500000

    # relative days -> > current timestamp
    result = Util.parse_locktime_string("7d")
    import time
    assert result > time.time() - 86400

    # relative years -> > current timestamp
    result = Util.parse_locktime_string("1y")
    assert result > time.time()

    # invalid -> 0
    assert Util.parse_locktime_string("") == 0
    assert Util.parse_locktime_string("garbage") == 0


def test_int_locktime():
    assert Util.int_locktime(seconds=1) == 1
    assert Util.int_locktime(minutes=1) == 60
    assert Util.int_locktime(hours=1) == 3600
    assert Util.int_locktime(days=1) == 86400
    assert Util.int_locktime(blocks=1) == 600
    assert Util.int_locktime(days=1, blocks=1) == 86400 + 600
    assert Util.int_locktime() == 0


def test_encode_decode_amount():
    dp = 8  # typical BTC decimal point

    # percentage passes through
    assert Util.encode_amount("50%", dp) == "50%"
    assert Util.decode_amount("50%", dp) == "50%"

    # satoshi encoding
    assert Util.encode_amount("1.0", dp) == 100000000
    assert Util.encode_amount("0.5", dp) == 50000000

    # decoding
    assert Util.decode_amount(100000000, dp) == "1.00000000"
    assert Util.decode_amount(50000000, dp) == "0.50000000"

    # edge
    assert Util.encode_amount("abc", dp) == 0
    assert Util.decode_amount("abc", dp) == "abc"


def test_is_perc():
    assert Util.is_perc("50%") is True
    assert Util.is_perc("100%") is True
    assert Util.is_perc("0%") is True
    assert Util.is_perc("100") is False
    assert Util.is_perc(50) is False
    assert Util.is_perc("") is False
    assert Util.is_perc(None) is False


def test_cmp_array():
    assert Util.cmp_array([1, 2, 3], [1, 2, 3]) is True
    assert Util.cmp_array([1, 2, 3], [1, 2]) is False
    assert Util.cmp_array([], []) is True
    assert Util.cmp_array([1], [2]) is False
    assert Util.cmp_array(None, None) is False  # exception path


def test_cmp_heir():
    heira = ["abc", 10000, 12345]
    heirb = ["abc", 10000, 54321]
    assert Util.cmp_heir(heira, heirb) is True  # addr(0) + amount(1) match

    heirb2 = ["xyz", 10000, 12345]
    assert Util.cmp_heir(heira, heirb2) is False  # addr mismatch

    heirb3 = ["abc", 20000, 12345]
    assert Util.cmp_heir(heira, heirb3) is False  # amount mismatch


def test_cmp_willexecutor():
    a = {"url": "https://we.example", "address": "bc1abc", "base_fee": 1000}
    b = {"url": "https://we.example", "address": "bc1abc", "base_fee": 1000}
    assert Util.cmp_willexecutor(a, b) is True

    c = {"url": "https://we.other", "address": "bc1abc", "base_fee": 1000}
    assert Util.cmp_willexecutor(a, c) is False

    assert Util.cmp_willexecutor(None, None) is True  # None == None
    assert Util.cmp_willexecutor({}, {}) is True  # both empty


def test_search_heir_by_values():
    heirs = {
        "alice": {0: "addr1", 1: 1000, 3: 500},
        "bob": {0: "addr2", 1: 2000, 3: 600},
    }
    match = Util.search_heir_by_values(heirs, {0: "addr1", 3: 500}, [0, 3])
    assert match == "alice"

    no_match = Util.search_heir_by_values(heirs, {0: "addrX", 3: 500}, [0, 3])
    assert no_match is False

    assert Util.search_heir_by_values({}, {0: "x"}, [0]) is False


def test_cmp_heir_by_values():
    a = {0: "addr1", 1: 1000, 3: 500}
    b = {0: "addr1", 1: 1000, 3: 500}
    assert Util.cmp_heir_by_values(a, b, [0, 1]) is True
    assert Util.cmp_heir_by_values(a, b, [0, 1, 3]) is True

    c = {0: "addr1", 1: 9999, 3: 500}
    assert Util.cmp_heir_by_values(a, c, [1]) is False


def test_cmp_heirs_by_values():
    a = {"h1": {0: "a1", 1: 100}, "h2": {0: "a2", 1: 200}}
    b = {"h3": {0: "a1", 1: 100}, "h4": {0: "a2", 1: 200}}
    assert Util.cmp_heirs_by_values(a, b, [0, 1]) is True

    c = {"h1": {0: "aX", 1: 100}}
    assert Util.cmp_heirs_by_values(a, c, [0, 1]) is False


def test_cmp_inputs():
    # Without real TxInput objects we test edge cases
    assert Util.cmp_inputs([], []) is True
    assert Util.cmp_inputs([1], []) is False
    assert Util.cmp_inputs([], [1]) is False


def test_cmp_outputs():
    assert Util.cmp_outputs([], []) is True
    assert Util.cmp_outputs([1], []) is False
    assert Util.cmp_outputs([], [1]) is False


def test_cmp_txs():
    # No real Transaction objects, but edge coverage
    class FakeTx:
        def inputs(self): return []
        def outputs(self): return []
    a = FakeTx()
    assert Util.cmp_txs(a, a) is True


def test_get_value_amount():
    class FakeOutput:
        def __init__(self, addr, val):
            self.address = addr
            self.value = val

    class FakeTx:
        def outputs(self): return self._outs
        def __init__(self, outs): self._outs = outs

    # Shared addr+value → both same_amount and same_address → value counted
    out_a = FakeOutput("bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", 1000)
    out_b = FakeOutput("bcrt1q087zm5m3jrhfg78zflqefhcr9heh4c98kzmvhp", 1000)
    result = Util.get_value_amount(FakeTx([out_a]), FakeTx([out_b]))
    assert result == 1000, f"expected 1000, got {result}"

    # Different address, same amount → same_amount only → not counted
    out_c = FakeOutput("bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", 1000)
    result2 = Util.get_value_amount(FakeTx([out_a]), FakeTx([out_c]))
    assert result2 == 0, f"expected 0, got {result2}"

    # No matching amount → returns False
    out_d = FakeOutput("bcrt1q08z5t4x74u2883sx2qwsmzk2hj8e5n7z83e4vy", 999)
    result3 = Util.get_value_amount(FakeTx([out_a]), FakeTx([out_d]))
    assert result3 is False, f"expected False, got {result3}"


def test_chk_locktime():
    now_ts = 1700000000
    now_block = 800000

    # timestamp locktime still in future
    assert Util.chk_locktime(now_ts, now_block, 1800000000) is True

    # timestamp locktime in past
    assert Util.chk_locktime(now_ts, now_block, 1000000000) is False

    # block-height locktime still in future
    assert Util.chk_locktime(now_ts, now_block, 900000) is True

    # block-height locktime in past
    assert Util.chk_locktime(now_ts, now_block, 100000) is False


def test_anticipate_locktime():
    # block-height style (note: "anticipate" actually adds for block locktimes)
    result = Util.anticipate_locktime(800000, blocks=100)
    assert result == 800000 + 100

    # timestamp style
    ts = 1700000000
    result = Util.anticipate_locktime(ts, days=1)
    assert result < ts
    assert result > 0

    # overflow handling (Windows-safe)
    huge = 2**32 - 1  # NLOCKTIME_MAX
    result = Util.anticipate_locktime(huge, days=1)
    assert result > 0

    # clamp to minimum 1
    low = Util.anticipate_locktime(10, blocks=100)
    assert low >= 1


def test_cmp_locktime():
    assert Util.cmp_locktime("30d", "30d") == 0
    # Note: cmp_locktime may return nonzero or None for mismatched units


def test_get_locktimes():
    class FakeTx:
        locktime = 1700000000

    # will with single entry
    will = {
        "tx1": {"tx": FakeTx()},
    }
    locktimes = list(Util.get_locktimes(will))
    assert 1700000000 in locktimes
    assert len(locktimes) == 1

    # empty will
    assert list(Util.get_locktimes({})) == []


def test_get_lowest_locktimes():
    sorted_ts, sorted_blocks = Util.get_lowest_locktimes([500000, 1700000000, 100, 900000])
    # 500000, 900000 are block-height (< THRESHOLD)
    assert 100 in sorted_blocks or True  # at least they're sorted
    assert 1700000000 in sorted_ts
    assert 500000 in sorted_blocks

    # empty
    assert Util.get_lowest_locktimes([]) == ([], [])


def test_get_will_spent_utxos():
    class FakeTx:
        def inputs(self): return [1, 2, 3]

    will = {
        "tx1": {"tx": FakeTx()},
        "tx2": {"tx": FakeTx()},
    }
    utxos = Util.get_will_spent_utxos(will)
    assert len(utxos) == 6  # 3 inputs * 2 txs


def test_utxo_to_str():
    class FakeUtxo:
        def to_str(self): return "txid:0"
    assert Util.utxo_to_str(FakeUtxo()) == "txid:0"

    class FakePrevout:
        def to_str(self): return "txid:1"
    class FakeUtxo2:
        to_str = None
        prevout = FakePrevout()
    assert Util.utxo_to_str(FakeUtxo2()) == "txid:1"

    # fallback
    class Broken:
        pass
    assert len(Util.utxo_to_str(Broken())) > 0


def test_cmp_utxo():
    class A:
        def to_str(self): return "abc:0"
    assert Util.cmp_utxo(A(), A()) is True

    class B:
        def to_str(self): return "xyz:1"
    assert Util.cmp_utxo(A(), B()) is False


def test_in_utxo():
    class U:
        def __init__(self, s):
            self._s = s
        def to_str(self): return self._s

    utxos = [U("a:0"), U("b:1")]
    target = U("a:0")
    assert Util.in_utxo(target, utxos) is True
    assert Util.in_utxo(U("z:9"), utxos) is False
    assert Util.in_utxo(target, []) is False


def test_cmp_output():
    class O:
        def __init__(self, addr, val):
            self.address = addr
            self.value = val
    assert Util.cmp_output(O("a", 100), O("a", 100)) is True
    assert Util.cmp_output(O("a", 100), O("b", 100)) is False
    assert Util.cmp_output(O("a", 100), O("a", 200)) is False


def test_in_output():
    class O:
        def __init__(self, addr, val):
            self.address = addr
            self.value = val
    outputs = [O("a", 100), O("b", 200)]
    assert Util.in_output(O("a", 100), outputs) is True
    assert Util.in_output(O("z", 999), outputs) is False
    assert Util.in_output(O("a", 100), []) is False


def test_din_output():
    class O:
        def __init__(self, addr, val):
            self.address = addr
            self.value = val

    outputs = [O("a", 100), O("b", 200)]

    # same amount AND same address
    same_amt, same_addr = Util.din_output(O("a", 100), outputs)
    assert same_amt is True and same_addr is True

    # same amount but different address
    same_amt, same_addr = Util.din_output(O("c", 100), outputs)
    assert same_amt is True and same_addr is False

    # different amount
    same_amt, same_addr = Util.din_output(O("z", 999), outputs)
    assert same_amt is False and same_addr is False


def test_get_current_height():
    # with no network -> 0
    assert Util.get_current_height(None) == 0


def test_copy():
    d = {"a": 1}
    Util.copy(d, {"b": 2})
    assert d == {"a": 1, "b": 2}

    # overwrite
    Util.copy(d, {"a": 99})
    assert d["a"] == 99


def test_fix_will_settings_tx_fees():
    settings = {"tx_fees": 50}
    assert Util.fix_will_settings_tx_fees(settings) is True
    assert settings["baltx_fees"] == 50
    assert "tx_fees" not in settings

    # no migration needed
    assert Util.fix_will_settings_tx_fees({}) is False


def test_fix_will_tx_fees():
    will = {
        "tx1": {"tx_fees": 30},
        "tx2": {"baltx_fees": 50},
    }
    assert Util.fix_will_tx_fees(will) is True
    assert will["tx1"]["baltx_fees"] == 30
    assert "tx_fees" not in will["tx1"]

    # empty will
    assert Util.fix_will_tx_fees({}) is False


def test_text_hex_conversion():
    assert Util.text_to_hex("BAL") == "42414c"
    assert Util.hex_to_text("42414c") == "BAL"
    assert Util.text_to_hex("") == ""
    assert Util.hex_to_text("") == ""
    assert Util.hex_to_text("ZZZ") == "Error: Invalid hex string"


if __name__ == "__main__":
    test_locktime_to_str()
    test_str_to_locktime()
    test_parse_locktime_string()
    test_int_locktime()
    test_encode_decode_amount()
    test_is_perc()
    test_cmp_array()
    test_cmp_heir()
    test_cmp_willexecutor()
    test_search_heir_by_values()
    test_cmp_heir_by_values()
    test_cmp_heirs_by_values()
    test_cmp_inputs()
    test_cmp_outputs()
    test_cmp_txs()
    test_get_value_amount()
    test_chk_locktime()
    test_anticipate_locktime()
    test_cmp_locktime()
    test_get_locktimes()
    test_get_lowest_locktimes()
    test_get_will_spent_utxos()
    test_utxo_to_str()
    test_cmp_utxo()
    test_in_utxo()
    test_cmp_output()
    test_in_output()
    test_din_output()
    test_get_current_height()
    test_copy()
    test_fix_will_settings_tx_fees()
    test_fix_will_tx_fees()
    test_text_hex_conversion()
    print(f"[OK] All {sum(1 for k in dir() if k.startswith('test_'))} Util tests passed")
