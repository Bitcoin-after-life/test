#!env/bin/python3
import getpass
import json
import os
import sys

from electrum.storage import WalletStorage
from electrum.util import MyEncoder

default_fees = 100


def fix_will_settings_tx_fees(json_wallet):
    tx_fees = json_wallet.get("will_settings", {}).get("tx_fees", False)
    have_to_update = False
    if tx_fees:
        json_wallet["will_settings"]["baltx_fees"] = tx_fees
        del json_wallet["will_settings"]["tx_fees"]
        have_to_update = True
    for txid, willitem in json_wallet["will"].items():
        tx_fees = willitem.get("tx_fees", False)
        if tx_fees:
            json_wallet["will"][txid]["baltx_fees"] = tx_fees
            del json_wallet["will"][txid]["tx_fees"]
            have_to_update = True
    return have_to_update


def uninstall_bal(json_wallet):
    if "will_settings" in json_wallet:
        del json_wallet["will_settings"]
    if "will" in json_wallet:
        del json_wallet["will"]
    if "heirs" in json_wallet:
        del json_wallet["heirs"]
    return True


def save(json_wallet, storage):
    human_readable = not storage.is_encrypted()
    storage.write(
        json.dumps(
            json_wallet,
            indent=4 if human_readable else None,
            sort_keys=bool(human_readable),
            cls=MyEncoder,
        )
    )


def read_wallet(path, password=False):
    storage = WalletStorage(path)
    if storage.is_encrypted():
        if not password:
            password = getpass.getpass("Enter wallet password: ", stream=None)
        storage.decrypt(password)
    data = storage.read()
    json_wallet = json.loads("[" + data + "]")[0]
    return json_wallet, storage


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: ./bal_wallet_utils <command> <wallet path>")
        print("available commands: uninstall, fix")
        exit(1)
    if not os.path.exists(sys.argv[2]):
        print("Error: wallet not found")
        exit(1)
    command = sys.argv[1]
    path = sys.argv[2]
    json_wallet, storage = read_wallet(path)
    have_to_save = False
    if command == "fix":
        have_to_save = fix_will_settings_tx_fees(json_wallet)
    if command == "uninstall":
        have_to_save = uninstall_bal(json_wallet)
    if have_to_save:
        save(json_wallet, storage)
    else:
        print("nothing to do")
