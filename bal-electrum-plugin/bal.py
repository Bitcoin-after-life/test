import os
from datetime import date, datetime, timedelta
import platform
# import random
# import zipfile as zipfile_lib
from electrum import constants, json_db
from electrum.logging import get_logger
from electrum.plugin import BasePlugin
from electrum.transaction import tx_from_any

_logger = get_logger(__name__)
def get_will_settings(x):
    # print(x)
    pass


json_db.register_dict("heirs", tuple, None)
json_db.register_dict("will", dict, None)
json_db.register_dict("will_settings", lambda x: x, None)


def get_will(x):
    try:
        x["tx"] = tx_from_any(x["tx"])
    except Exception as e:
        raise e
    return x


class BalConfig:
    def __init__(self, config, name, default):
        self.config = config
        self.name = name
        self.default = default

    def get(self, default=None):
        v = self.config.get(self.name, default)
        if v is None:
            if default is not None:
                v = default
            else:
                v = self.default
        return v

    def set(self, value, save=True):
        self.config.set_key(self.name, value, save=save)


class BalPlugin(BasePlugin):
    _version=None
    __version__ = "0.2.8" #AUTOMATICALLY GENERATED DO NOT EDIT
    default_app={
            "Linux":"xdg-open",
            "Windows":"cmd /c start",
            "Darwin":"open"
    }
    chainname = constants.net.NET_NAME if constants.net.NET_NAME != "mainnet" else "bitcoin"
    def version(self):
        if not self._version:
            try:
                f = ""
                with open("{}/VERSION".format(self.plugin_dir), "r") as fi:
                    f = str(fi.read())
                self._version = f.strip()
            except Exception as e:
                _logger.error(f"failed to get version: {e}")
                self._version="unknown"
        return self._version

    SIZE = (159, 97)

    def __init__(self, parent, config, name):
        self.logger = get_logger(__name__)
        BasePlugin.__init__(self, parent, config, name)
        self.base_dir = os.path.join(config.electrum_path(), "bal")
        self.plugin_dir = os.path.split(os.path.realpath(__file__))[0]
        zipfile = "/".join(self.plugin_dir.split("/")[:-1])
        import sys

        sys.path.insert(0, zipfile)
        self.parent = parent
        self.config = config
        self.name = name

        self.ASK_BROADCAST = BalConfig(config, "bal_ask_broadcast", True)
        self.BROADCAST = BalConfig(config, "bal_broadcast", True)
        self.LOCKTIME_TIME = BalConfig(config, "bal_locktime_time", 90)
        self.LOCKTIME_BLOCKS = BalConfig(config, "bal_locktime_blocks", 144 * 90)
        self.LOCKTIMEDELTA_TIME = BalConfig(config, "bal_locktimedelta_time", 7)
        self.LOCKTIMEDELTA_BLOCKS = BalConfig(
            config, "bal_locktimedelta_blocks", 144 * 7
        )
        self.ENABLE_MULTIVERSE = BalConfig(config, "bal_enable_multiverse", False)
        self.TX_FEES = BalConfig(config, "bal_tx_fees", 100)
        self.INVALIDATE = BalConfig(config, "bal_invalidate", True)
        self.ASK_INVALIDATE = BalConfig(config, "bal_ask_invalidate", True)
        self.PREVIEW = BalConfig(config, "bal_preview", True)
        self.SAVE_TXS = BalConfig(config, "bal_save_txs", True)

        self.NO_WILLEXECUTOR = BalConfig(config, "bal_no_willexecutor", True)
        self.HIDE_REPLACED = BalConfig(config, "bal_hide_replaced", True)
        self.HIDE_INVALIDATED = BalConfig(config, "bal_hide_invalidated", True)
        self.ALLOW_REPUSH = BalConfig(config, "bal_allow_repush", True)
        self.FIRST_EXECUTION = BalConfig(config, "bal_first_execution", True)
        self.WELIST_SERVER = BalConfig(config,"bal_welist_server","https://welist.bitcoin-after.life/")
        self.EVENT_DESCRIPTION = BalConfig(config,"bal_event_description", "BAL will execution of $wallet_name\r\n heirs list:  \r\n$heirs_complete")
        self.EVENT_SUMMARY = BalConfig(config,"bal_event_summary", "BAL -Will execution of $wallet_name")
        self.WILLEXECUTORS = BalConfig(
            config,
            "bal_willexecutors",
            {
                "mainnet": {
                    "https://we.bitcoin-after.life": {
                        "base_fee": 100000,
                        "status": "New",
                        "info": "Bitcoin After Life Will Executor",
                        "address": "bc1qusymuetsz2psaqzqxv8qmzcy64d9meckj3lxxf",
                        "selected": True,
                    }
                },
                "testnet": {
                    "https://we.bitcoin-after.life": {
                        "base_fee": 100000,
                        "status": "New",
                        "info": "Bitcoin After Life Will Executor",
                        "address": "bcrt1qa5cntu4hgadw8zd3n6sq2nzjy34sxdtd9u0gp7",
                        "selected": True,
                    }
                },
                "testnet4": {
                    "https://we.bitcoin-after.life": {
                        "base_fee": 100000,
                        "status": "New",
                        "info": "Bitcoin After Life Will Executor",
                        "address": "bcrt1qa5cntu4hgadw8zd3n6sq2nzjy34sxdtd9u0gp7",
                        "selected": True,
                    }
                },
                "regtest": {
                    "https://we.bitcoin-after.life": {
                        "base_fee": 100000,
                        "status": "New",
                        "info": "Bitcoin After Life Will Executor",
                        "address": "bcrt1qa5cntu4hgadw8zd3n6sq2nzjy34sxdtd9u0gp7",
                        "selected": True,
                    }
                },
            },
        )
        self.WILL_SETTINGS = BalConfig(
            config,
            "bal_will_settings",
            BalPlugin.default_will_settings(),
        )
        self.system = platform.system()
        self.CALENDAR_APP = BalConfig(config,"bal_open_app",self.default_app.get(self.system,""))
        self._hide_invalidated = self.HIDE_INVALIDATED.get()
        self._hide_replaced = self.HIDE_REPLACED.get()

    def resource_path(self, *parts):
        return os.path.join(self.plugin_dir, *parts)

    def hide_invalidated(self):
        self._hide_invalidated = not self._hide_invalidated
        self.HIDE_INVALIDATED.set(self._hide_invalidated)

    def hide_replaced(self):
        self._hide_replaced = not self._hide_replaced
        self.HIDE_REPLACED.set(self._hide_replaced)

    def validate_will_settings(self, will_settings):
        defaults=BalPlugin.default_will_settings()
        if not will_settings:
            will_settings=[]
        if int(will_settings.get("baltx_fees", 0)) < 1:
            will_settings["baltx_fees"] = defaults['baltx_fees']
        if not will_settings.get("threshold"):
            will_settings["threshold"] = defaults['threshold']
        if not will_settings.get("locktime"):
            will_settings["locktime"] = defaults['locktime']
        return will_settings

    @staticmethod
    def default_will_settings():
        will_settings ={"baltx_fees":100}
        will_settings.update(BalPlugin.default_will_settings_absolute())
        return will_settings
    @staticmethod
    def default_will_settings_absolute():
        relative_dates=BalPlugin.default_will_settings_relative()
        today = date.today()
        dt = datetime(today.year, today.month, today.day, 0, 0, 0)
        threshold =(dt + timedelta(days=BalTimestamp(relative_dates["threshold"]).duration_to_days())).timestamp()
        locktime =(dt + timedelta(days=BalTimestamp(relative_dates["locktime"]).duration_to_days())).timestamp()
        return {"threshold": threshold, "locktime": locktime}
    @staticmethod
    def default_will_settings_relative():
        return {"threshold" : "30d", "locktime": "1y"}


class BalTimestamp:
    value = None
    unit = None
    def __init__(self,value):
        str_value = str(value)
        if str_value and str_value[-1].lower() in ("y","d"):
            self.value = int(str_value[:-1])
            self.unit = str_value[-1]
        else:
            try:
                self.value = int(value)
            except Exception as _e:
                self.value=1
            self.unit = None

    def duration_to_days(self):
        return self.value*365 if self.unit=='y' else self.value

    def to_date(self,from_date=None,reverse=False):
        if self.unit is None:
            return datetime.fromtimestamp(self.value)
        else:
            if from_date is None:
                from_date = datetime.now()
            if isinstance(from_date, (int, float)):
                from_date = datetime.fromtimestamp(from_date)
            reverse = 1 if not reverse else -1
            return (from_date + (reverse * timedelta(days = self.duration_to_days()))).replace(hour=0,minute=0,second=0,microsecond=0)

    def to_timestamp(self,from_date=None,reverse=False):
        return self.to_date(from_date,reverse).timestamp()

    def __str__(self):
        if self.unit is None:
            return datetime.fromtimestamp(self.value).isoformat()
        else:
            return f"{self.value}{self.unit}"

    def __repr__(self):
        if self.unit is None:
            return datetime.fromtimestamp(self.value).to_date().timestamp()
        else:
            return f"{self.value}{self.unit}"
