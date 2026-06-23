"""
Tests for Group C (settings-dialog enhancements).

Covered behaviour:

  * C2 - the persisted ``EDITABLE_DATES`` configuration key exists, defaults to
    OFF, and can be toggled and read back. This is the flag that makes the
    delivery-time / check-alive date fields editable outside the wizard.
  * C4b - the "Reset" logic restores each of the six dialog settings to its
    factory default. The factory default is taken from ``BalConfig.default``
    (the third argument used when the config was created), so the dialog's
    Reset button has a single source of truth and never hard-codes values.

The Qt widgets are not imported (they need PyQt6 + an Electrum window). Instead
we reproduce the small, GUI-free decision logic with the same lightweight
``FakeConfig`` used by the Group B tests, which keeps the tests fast and
headless while still verifying the real contract.

Run:
    PYTHONPATH=electrum-src python3 -m pytest tests/test_group_c_settings.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from bal.core.plugin_base import BalConfig


# ------------------------------------------------------------------ #
# Mocks
# ------------------------------------------------------------------ #

class FakeConfig:
    """Minimal mock for Electrum's config object (key/value store)."""

    def __init__(self):
        self._store = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set_key(self, key, value, save=True):
        self._store[key] = value


# ------------------------------------------------------------------ #
# C2 - EDITABLE_DATES config
# ------------------------------------------------------------------ #

def test_editable_dates_defaults_off():
    """C2: the editable-dates flag defaults to OFF (dates display-only)."""
    cfg = FakeConfig()
    editable = BalConfig(cfg, "bal_editable_dates", False)
    assert editable.get() is False


def test_editable_dates_can_be_enabled():
    """C2: turning the flag ON is persisted and read back as True."""
    cfg = FakeConfig()
    editable = BalConfig(cfg, "bal_editable_dates", False)
    editable.set(True)
    # Re-read through a fresh accessor to prove it is persisted in the config.
    assert BalConfig(cfg, "bal_editable_dates", False).get() is True


# ------------------------------------------------------------------ #
# C4b - Reset to defaults
# ------------------------------------------------------------------ #

def _reset_to_defaults(configs):
    """Reproduce the dialog's Reset logic: set each config back to its default.

    This mirrors ``on_reset_defaults`` in ``bal.gui.qt.plugin`` (which also
    refreshes the Qt widgets). Here we only verify the persistence side: every
    config is reset to ``BalConfig.default``.
    """
    for cfg in configs:
        cfg.set(cfg.default)


def test_reset_restores_all_dialog_settings():
    """C4b: Reset restores every dialog setting to its factory default.

    The dialog exposes seven settings: the original six plus the Group C
    "Editable dates" checkbox, which the Reset button must also restore (this
    was a follow-up fix after the first test round).
    """
    cfg = FakeConfig()

    # The settings exposed by the dialog, with their real defaults.
    hide_replaced = BalConfig(cfg, "bal_hide_replaced", True)
    hide_invalidated = BalConfig(cfg, "bal_hide_invalidated", True)
    auto_sign = BalConfig(cfg, "bal_auto_sign", True)
    editable_dates = BalConfig(cfg, "bal_editable_dates", False)
    calendar_app = BalConfig(cfg, "bal_open_app", "xdg-open")
    event_summary = BalConfig(
        cfg, "bal_event_summary", "BAL -Will execution of $wallet_name"
    )
    event_description = BalConfig(
        cfg,
        "bal_event_description",
        "BAL will execution of $wallet_name\r\n heirs list:  \r\n$heirs_complete",
    )
    settings = [
        hide_replaced,
        hide_invalidated,
        auto_sign,
        editable_dates,
        calendar_app,
        event_summary,
        event_description,
    ]

    # Mutate every setting away from its default.
    hide_replaced.set(False)
    hide_invalidated.set(False)
    auto_sign.set(False)
    editable_dates.set(True)
    calendar_app.set("/custom/app")
    event_summary.set("custom summary")
    event_description.set("custom description")

    # Sanity: the values really changed.
    assert hide_replaced.get() is False
    assert editable_dates.get() is True
    assert calendar_app.get() == "/custom/app"

    # Reset and verify each one is back to its declared default.
    _reset_to_defaults(settings)
    for s in settings:
        assert s.get() == s.default
    # In particular the "Editable dates" flag is back OFF.
    assert editable_dates.get() is False


def test_reset_does_not_touch_unrelated_settings():
    """C4b: Reset only changes the listed settings, nothing else.

    A will / will-executor style key that is NOT part of the dialog list must
    keep its value after a reset of the six dialog settings.
    """
    cfg = FakeConfig()
    unrelated = BalConfig(cfg, "bal_will_settings", {"x": 1})
    unrelated.set({"custom": "value"})

    dialog_settings = [
        BalConfig(cfg, "bal_hide_replaced", True),
        BalConfig(cfg, "bal_auto_sign", True),
    ]
    for s in dialog_settings:
        s.set(False)

    _reset_to_defaults(dialog_settings)

    # The unrelated key is untouched by the dialog reset.
    assert unrelated.get() == {"custom": "value"}
