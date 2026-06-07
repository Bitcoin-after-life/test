"""
bal.gui.qt
==========

The PyQt6 graphical interface of the Bitcoin After Life plugin.

Module map (was previously one 4000-line ``qt.py``):

    common.py    - shared imports + tiny helpers (shown_cv, add_widget, ...)
    theme.py     - colour mapping for will-item statuses (was WillItem.get_color)
    calendar.py  - .ics calendar generation
    widgets.py   - reusable leaf widgets (editors, checkboxes, will box, ...)
    dialogs.py   - all dialogs (settings, wizard, build-will, detail, ...)
    lists.py     - tree views (heirs, preview, will-executors)
    window.py    - BalWindow controller (one per wallet window)
    plugin.py    - Plugin class with the Electrum @hook methods (entry point)
"""
