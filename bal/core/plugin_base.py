"""
bal.core.plugin_base
=====================

GUI-agnostic foundation of the plugin.

It contains:
    * :class:`BalConfig`   - a thin typed wrapper around an Electrum config key
                             with a default value.
    * :class:`BalPlugin`   - the base plugin class (extends Electrum's
                             ``BasePlugin``) holding every configuration option
                             and the default "will settings".  The Qt-specific
                             ``Plugin`` subclass lives in ``bal.gui.qt.plugin``.
    * :class:`BalTimestamp`- helper to convert between relative durations
                             (``"30d"``, ``"1y"``) and absolute timestamps.

It also registers the three custom persisted dictionaries (``heirs``,
``will`` and ``will_settings``) with Electrum's JSON database so they are
serialised together with the wallet file.

This module performs **no** GUI work and imports nothing from PyQt / electrum.gui.
"""

import os
import platform
from datetime import date, datetime, timedelta

from electrum import constants, json_db
from electrum.logging import get_logger
from electrum.plugin import BasePlugin
from electrum.transaction import tx_from_any

_logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Wallet-DB registration
# --------------------------------------------------------------------------- #
# Electrum needs to know how to (de)serialise the custom dictionaries the
# plugin stores inside the wallet file.  ``register_dict`` associates a key
# name with a conversion callable applied to each value when the wallet is
# loaded.  ``will`` values run through ``get_will`` so the stored transaction
# hex is turned back into a ``Transaction`` object.
def get_will(x):
    """Deserialise a stored will entry, rebuilding its ``tx`` object."""
    try:
        x["tx"] = tx_from_any(x["tx"])
    except Exception as e:
        raise e
    return x


json_db.register_dict("heirs", tuple, None)
json_db.register_dict("will", dict, None)
json_db.register_dict("will_settings", lambda x: x, None)


class BalConfig:
    """Typed accessor for a single Electrum configuration key.

    Wraps ``config.get`` / ``config.set_key`` and supplies a default value
    when the key is missing.
    """

    def __init__(self, config, name, default):
        self.config = config
        self.name = name
        self.default = default

    def get(self, default=None):
        """Return the stored value, falling back to ``default`` then ``self.default``."""
        v = self.config.get(self.name, default)
        if v is None:
            if default is not None:
                v = default
            else:
                v = self.default
        return v

    def set(self, value, save=True):
        """Persist ``value`` for this key."""
        self.config.set_key(self.name, value, save=save)


class BalPlugin(BasePlugin):
    """Base plugin: holds configuration and default inheritance settings.

    The GUI layer subclasses this in ``bal.gui.qt.plugin.Plugin`` and adds the
    Electrum ``@hook`` methods.  Keeping the configuration here means the CLI
    layer (or unit tests) can use the plugin logic without importing Qt.
    """

    _version = None
    __version__ = "0.3.6"  # AUTOMATICALLY GENERATED DO NOT EDIT

    # Command used to open an .ics calendar file, per operating system.
    default_app = {
        "Linux": "xdg-open",
        "Windows": "cmd /c start",
        "Darwin": "open",
    }

    # Human-readable chain name ("bitcoin", "testnet", "regtest", ...).
    chainname = (
        constants.net.NET_NAME if constants.net.NET_NAME != "mainnet" else "bitcoin"
    )

    # Default geometry hint for some dialogs (kept from the original code).
    SIZE = (159, 97)

    def version(self):
        """Return the plugin version, read once from the ``VERSION`` file."""
        if not self._version:
            try:
                f = ""
                with open("{}/VERSION".format(self.plugin_dir), "r") as fi:
                    f = str(fi.read())
                self._version = f.strip()
            except Exception as e:
                _logger.error(f"failed to get version: {e}")
                self._version = "unknown"
        return self._version

    def __init__(self, parent, config, name):
        self.logger = get_logger(__name__)
        BasePlugin.__init__(self, parent, config, name)

        # Base directory for plugin data inside the Electrum data dir.
        self.base_dir = os.path.join(config.electrum_path(), "bal")
        self.plugin_dir = os.path.split(os.path.realpath(__file__))[0]

        # Make the plugin importable when loaded from a zip (legacy behaviour:
        # the parent directory of this file is added to ``sys.path``).
        zipfile = "/".join(self.plugin_dir.split("/")[:-1])
        import sys

        sys.path.insert(0, zipfile)

        self.parent = parent
        self.config = config
        self.name = name

        # ---------------------------------------------------------------- #
        # Configuration options (all persisted via Electrum's config).
        # ---------------------------------------------------------------- #
        self.ASK_BROADCAST = BalConfig(config, "bal_ask_broadcast", True)
        self.BROADCAST = BalConfig(config, "bal_broadcast", True)
        self.LOCKTIME_TIME = BalConfig(config, "bal_locktime_time", 90)
        # NOTE (A1): block-height locktimes were removed; the plugin now uses
        # only timestamp-based locktimes. LOCKTIME_BLOCKS is therefore no longer
        # read anywhere in the code. It is kept here (dormant) on purpose, to
        # avoid touching a persisted config key ("bal_locktime_blocks") that may
        # already exist in some users' saved settings.
        self.LOCKTIME_BLOCKS = BalConfig(config, "bal_locktime_blocks", 144 * 90)
        self.LOCKTIMEDELTA_TIME = BalConfig(config, "bal_locktimedelta_time", 7)
        # NOTE (A1): same as LOCKTIME_BLOCKS above - block-height locktimes were
        # removed, so LOCKTIMEDELTA_BLOCKS is no longer read anywhere. It is kept
        # here (dormant) on purpose, to avoid touching the persisted config key
        # "bal_locktimedelta_blocks" that may already exist in saved settings.
        self.LOCKTIMEDELTA_BLOCKS = BalConfig(
            config, "bal_locktimedelta_blocks", 144 * 7
        )
        self.ENABLE_MULTIVERSE = BalConfig(config, "bal_enable_multiverse", False)
        self.TX_FEES = BalConfig(config, "bal_tx_fees", 100)
        self.INVALIDATE = BalConfig(config, "bal_invalidate", True)
        self.ASK_INVALIDATE = BalConfig(config, "bal_ask_invalidate", True)
        self.PREVIEW = BalConfig(config, "bal_preview", True)
        self.SAVE_TXS = BalConfig(config, "bal_save_txs", True)

        # AUTO_SIGN (Group B / B2): when enabled, pressing "Check" will, after
        # querying the will-executor servers, automatically sign the will
        # transactions and broadcast them to their will-executors, without the
        # user having to invoke "Sign" and "Broadcast" separately. The wallet
        # password is requested only when the wallet is actually encrypted
        # (handled by BalWindow.get_wallet_password). Default ON.
        self.AUTO_SIGN = BalConfig(config, "bal_auto_sign", True)

        # EDITABLE_DATES (Group C / C2): when enabled, the delivery-time and
        # check-alive date fields are editable everywhere (toolbar / Heirs tab),
        # not only inside the "Build your will" wizard. Default OFF, so the dates
        # stay display-only outside the wizard unless the user opts in.
        self.EDITABLE_DATES = BalConfig(config, "bal_editable_dates", False)

        # NUM_REMINDERS (Group D / D1): how many reminder alarms (VALARM) the
        # exported .ics calendar event should contain. The reminders are spread
        # uniformly across the check-alive period and always fall BEFORE the
        # delivery deadline. Default 3; the settings dialog caps it at 5 and the
        # alarm builder additionally limits it to at most one alarm per available
        # day.
        self.NUM_REMINDERS = BalConfig(config, "bal_num_reminders", 3)

        self.NO_WILLEXECUTOR = BalConfig(config, "bal_no_willexecutor", True)
        self.HIDE_REPLACED = BalConfig(config, "bal_hide_replaced", True)
        self.HIDE_INVALIDATED = BalConfig(config, "bal_hide_invalidated", True)
        self.ALLOW_REPUSH = BalConfig(config, "bal_allow_repush", True)
        self.FIRST_EXECUTION = BalConfig(config, "bal_first_execution", True)
        self.WELIST_SERVER = BalConfig(
            config, "bal_welist_server", "https://welist.bitcoin-after.life/"
        )
        self.EVENT_DESCRIPTION = BalConfig(
            config,
            "bal_event_description",
            "BAL will execution of $wallet_name\r\n heirs list:  \r\n$heirs_complete",
        )
        self.EVENT_SUMMARY = BalConfig(
            config, "bal_event_summary", "BAL -Will execution of $wallet_name"
        )

        # Default will-executor servers, keyed by network.
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
        self.CALENDAR_APP = BalConfig(
            config, "bal_open_app", self.default_app.get(self.system, "")
        )

        # Cached toggles used by the GUI list filters.
        self._hide_invalidated = self.HIDE_INVALIDATED.get()
        self._hide_replaced = self.HIDE_REPLACED.get()

    def resource_path(self, *parts):
        """Absolute path to a file bundled inside the plugin directory."""
        return os.path.join(self.plugin_dir, *parts)

    def sync_hide_filters(self):
        """Re-read the "hide" filter flags from the persisted config.

        The cached ``_hide_invalidated`` / ``_hide_replaced`` flags are used by
        the GUI list to decide which rows to skip.  They can be changed from two
        different places:

        * the list toolbar buttons, which call :meth:`hide_invalidated` /
          :meth:`hide_replaced` (a toggle that updates both the cache and the
          config), and
        * the Settings dialog checkboxes, which write the config directly
          (``BalConfig.set``) without touching the cached flags.

        In the second case the cache and the config would drift apart and the
        transaction list would keep filtering with the *old* value, so the
        toggled rows never appear/disappear until Electrum is restarted.
        Re-syncing the cache from the config here (called by ``update_all``)
        keeps every code path coherent regardless of where the change came
        from.
        """
        self._hide_invalidated = self.HIDE_INVALIDATED.get()
        self._hide_replaced = self.HIDE_REPLACED.get()

    def hide_invalidated(self):
        """Toggle (and persist) the "hide invalidated transactions" filter."""
        self._hide_invalidated = not self._hide_invalidated
        self.HIDE_INVALIDATED.set(self._hide_invalidated)

    def hide_replaced(self):
        """Toggle (and persist) the "hide replaced transactions" filter."""
        self._hide_replaced = not self._hide_replaced
        self.HIDE_REPLACED.set(self._hide_replaced)

    def validate_will_settings(self, will_settings):
        """Fill in any missing will-setting with its default value."""
        defaults = BalPlugin.default_will_settings()
        if not will_settings:
            will_settings = []
        if int(will_settings.get("baltx_fees", 0)) < 1:
            will_settings["baltx_fees"] = defaults['baltx_fees']
        if not will_settings.get("threshold"):
            will_settings["threshold"] = defaults['threshold']
        if not will_settings.get("locktime"):
            will_settings["locktime"] = defaults['locktime']
        return will_settings

    @staticmethod
    def default_will_settings():
        """Default will settings: a fee rate plus absolute threshold/locktime."""
        will_settings = {"baltx_fees": 100}
        will_settings.update(BalPlugin.default_will_settings_absolute())
        return will_settings

    @staticmethod
    def default_will_settings_absolute():
        """Convert the default relative dates into absolute timestamps (from today)."""
        relative_dates = BalPlugin.default_will_settings_relative()
        today = date.today()
        dt = datetime(today.year, today.month, today.day, 0, 0, 0)
        threshold = (
            dt + timedelta(days=BalTimestamp(relative_dates["threshold"]).duration_to_days())
        ).timestamp()
        locktime = (
            dt + timedelta(days=BalTimestamp(relative_dates["locktime"]).duration_to_days())
        ).timestamp()
        return {"threshold": threshold, "locktime": locktime}

    @staticmethod
    def default_will_settings_relative():
        """Default relative dates: 30 days threshold, 1 year locktime."""
        return {"threshold": "30d", "locktime": "1y"}


class BalTimestamp:
    """Parse and convert relative durations / absolute timestamps.

    A value may be:
        * ``"<n>y"`` -> ``n`` years (unit ``"y"``)
        * ``"<n>d"`` -> ``n`` days  (unit ``"d"``)
        * an integer -> an absolute UNIX timestamp (``unit is None``)
    """

    value = None
    unit = None

    def __init__(self, value):
        str_value = str(value)
        if str_value and str_value[-1].lower() in ("y", "d"):
            self.value = int(str_value[:-1])
            self.unit = str_value[-1]
        else:
            try:
                self.value = int(value)
            except Exception as _e:
                self.value = 1
            self.unit = None

    def duration_to_days(self):
        """Return the duration expressed in days (years are ``*365``)."""
        return self.value * 365 if self.unit == 'y' else self.value

    @staticmethod
    def _safe_fromtimestamp(ts):
        """``datetime.fromtimestamp`` that never raises ``OverflowError``.

        On Windows ``time_t`` is 32-bit, so ``datetime.fromtimestamp`` raises
        ``OverflowError: Python int too large to convert to C int`` for any
        timestamp past the year-2038 limit (e.g. ``NLOCKTIME_MAX = 2**32 - 1``,
        used as the default/sentinel locktime).  On 64-bit Linux the same call
        succeeds, which is why this only crashed on the user's Windows build.

        We clamp out-of-range timestamps to INT32_MAX, mirroring Electrum's own
        ``get_max_allowed_timestamp`` workaround (see Electrum issue #6170).
        """
        INT32_MAX = 2 ** 31 - 1
        try:
            return datetime.fromtimestamp(ts)
        except (OSError, OverflowError, ValueError):
            try:
                return datetime.fromtimestamp(min(int(ts), INT32_MAX))
            except (OSError, OverflowError, ValueError):
                return datetime.fromtimestamp(INT32_MAX)

    def to_date(self, from_date=None, reverse=False):
        """Resolve to a ``datetime``.

        For absolute values the stored timestamp is returned; for relative ones
        the duration is added to (or, if ``reverse``, subtracted from)
        ``from_date`` (defaulting to *now*), normalised to midnight.
        """
        if self.unit is None:
            return self._safe_fromtimestamp(self.value)
        else:
            if from_date is None:
                from_date = datetime.now()
            if isinstance(from_date, (int, float)):
                from_date = self._safe_fromtimestamp(from_date)
            reverse = 1 if not reverse else -1
            try:
                return (
                    from_date + (reverse * timedelta(days=self.duration_to_days()))
                ).replace(hour=0, minute=0, second=0, microsecond=0)
            except (OverflowError, OSError, ValueError):
                # Duration overflowed datetime's range; clamp to INT32_MAX.
                return self._safe_fromtimestamp(2 ** 31 - 1).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

    def to_timestamp(self, from_date=None, reverse=False):
        """Same as :meth:`to_date` but returns a UNIX timestamp."""
        return self.to_date(from_date, reverse).timestamp()

    def __str__(self):
        if self.unit is None:
            return self._safe_fromtimestamp(self.value).isoformat()
        else:
            return f"{self.value}{self.unit}"

    def __repr__(self):
        if self.unit is None:
            return self._safe_fromtimestamp(self.value).isoformat()
        else:
            return f"{self.value}{self.unit}"
