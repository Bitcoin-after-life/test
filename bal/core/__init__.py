"""
bal.core
========

Pure business-logic layer of the Bitcoin After Life (BAL) Electrum plugin.

Everything in this sub-package MUST stay completely free of any GUI / Qt
imports.  The rule of thumb is:

    * ``bal.core``      -> "what the plugin does" (inheritance rules, building
                           and validating transactions, talking to
                           will-executor servers, persistence helpers).
    * ``bal.gui``       -> "how it looks" (Qt widgets, dialogs, list views).

Keeping the two apart is the main motivation behind this rewrite: the original
code mixed transaction-building logic and presentation inside a single
4000-line ``qt.py`` module, which made the delicate Bitcoin logic hard to audit.

No behaviour is changed with respect to the original plugin; the code has only
been reorganised and documented.
"""
