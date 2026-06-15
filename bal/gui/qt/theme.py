"""
bal.gui.qt.theme
================

Pure presentation helpers for the Qt layer.

This is where colours and other look-and-feel decisions live, kept apart from
the core inheritance logic.  In particular it hosts :func:`status_color`, which
used to be ``WillItem.get_color()`` inside ``will.py``.

The status flags themselves are computed by the core layer
(:class:`bal.core.will.WillItem`); this module only translates a will item's
status into a colour for the transaction list / detail views.
"""

# Status -> hex colour.  The first matching status (checked in priority order)
# wins.  These are exactly the colours the original ``WillItem.get_color`` used,
# so the GUI looks identical after the refactor.
#
# The order matters: e.g. an INVALIDATED tx must show orange even if it also
# carries other flags, so INVALIDATED is checked before everything else.
_STATUS_COLOR_PRIORITY = (
    ("INVALIDATED", "#f87838"),  # orange  - tx can no longer be mined
    ("REPLACED", "#ff97e9"),     # pink    - superseded by another tx
    ("CONFIRMED", "#bfbfbf"),    # grey    - already mined
    ("PENDING", "#ffce30"),      # yellow  - in mempool, waiting
)

# Default colour used when no status in the priority list matches.
_DEFAULT_COLOR = "#ffffff"


def status_color(will_item) -> str:
    """Return the display colour (``"#rrggbb"``) for a :class:`WillItem`.

    This is a faithful, behaviour-preserving port of the old
    ``WillItem.get_color()`` method.  The slightly irregular handling of the
    push/check states (which is not a simple priority list) is reproduced
    exactly as in the original code.
    """
    # First, the simple priority-ordered statuses.
    for status, color in _STATUS_COLOR_PRIORITY:
        if will_item.get_status(status):
            return color

    # The remaining states need the original branching because of the
    # CHECK_FAIL / CHECKED interaction.
    if will_item.get_status("CHECK_FAIL") and not will_item.get_status("CHECKED"):
        return "#e83845"  # red - server check failed
    elif will_item.get_status("CHECKED"):
        return "#8afa6c"  # green - server confirmed it stored the tx
    elif will_item.get_status("PUSH_FAIL"):
        return "#e83845"  # red - failed to push to will-executor
    elif will_item.get_status("PUSHED"):
        return "#73f3c8"  # teal - pushed to will-executor
    elif will_item.get_status("COMPLETE"):
        return "#2bc8ed"  # blue - signed
    else:
        return _DEFAULT_COLOR


def server_status_text(will_item) -> str:
    """Return a short, human-readable label describing the state of a will
    item on the will-executor servers (the online inheritance backup).

    This is shown in the dedicated "Server" column of the transaction list so
    the user always knows whether each inheritance transaction is actually
    stored on the will-executor servers, regardless of the row colour.
    """
    from electrum.i18n import _

    if will_item.get_status("CHECK_FAIL") and not will_item.get_status("CHECKED"):
        return _("Not on server")
    if will_item.get_status("CHECKED"):
        return _("Confirmed on server")
    if will_item.get_status("PUSH_FAIL"):
        return _("Send failed")
    if will_item.get_status("PUSHED"):
        return _("Sent (not checked)")
    if will_item.get_status("COMPLETE"):
        return _("Signed (not sent)")
    return _("Not sent")


def server_status_tooltip(will_item) -> str:
    """Return a detailed tooltip for the "Server" column, including the
    will-executor URL (if any) and the current server state."""
    from electrum.i18n import _

    url = None
    we = getattr(will_item, "we", None)
    if we:
        url = we.get("url")
    state = server_status_text(will_item)
    if url:
        return "{}: {}\n{}".format(_("Will-Executor"), url, state)
    return "{}\n{}".format(_("No will-executor"), state)
