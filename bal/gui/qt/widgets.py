"""
bal.gui.qt.widgets
==================

Reusable, self-contained Qt widgets used to build the BAL tabs and dialogs.

These are "leaf" widgets: they receive the :class:`BalWindow` controller (and
any data they need) as constructor arguments at runtime, so this module does
not import ``window``/``dialogs`` and therefore introduces no import cycles.

Contents:
    * ClickableLabel, BalLineEdit, BalTextEdit, BalCheckBox - thin Qt wrappers
    * BalTxFeesWidget                                       - fee-rate editor
    * _LockTimeEditor + BalTimeEditWidget + raw/date editors - locktime editing
    * ThresholdTimeWidget / LockTimeWidget                  - threshold & locktime
    * WillSettingsWidget                                    - the settings panel
    * PercAmountEdit                                        - amount-or-percentage editor
    * WillWidget                                            - single will-tx box
"""

from .common import *
from .common import _, _logger  # underscore names are not re-exported by "import *"
from .calendar import BalCalendar


def compute_reminder_offsets(days, count):
    """Return the reminder offsets (in days BEFORE the deadline) for an .ics event.

    Group D / D1. The reminders are spread uniformly across the check-alive
    period and always fall *before* the delivery deadline, i.e. every returned
    offset is ``>= 1`` (a reminder exactly on the deadline would be useless).

    Rules:
        * ``count`` is the requested number of reminders (the settings dialog
          caps it at 5, default 3).
        * at most ONE reminder per available day: the effective number is
          ``min(count, days)``;
        * with ``days`` available days, offsets are chosen as evenly spaced
          points inside ``[1, days]`` (1 = the day before the deadline, ``days``
          = the first day of the period), de-duplicated and returned sorted
          descending (earliest reminder first).

    Args:
        days: number of whole days between check-alive and the deadline.
        count: requested number of reminders.

    Returns:
        A list of integer day-offsets (each ``>= 1``), e.g. ``[22, 15, 8]`` for
        ``days=30, count=3``. Empty if there is no room for any reminder.
    """
    # No room for any reminder (deadline today or already passed).
    if days < 1 or count < 1:
        return []

    # Never more reminders than available days (one per day at most).
    effective = min(int(count), int(days))

    # A single reminder: put it one day before the deadline.
    if effective == 1:
        return [1]

    # Spread "effective" points evenly inside [1, days]. Using i/(effective-1)
    # for i in 0..effective-1 gives fractions 0..1; map them onto [1, days].
    # This places the first reminder at the start of the period (offset ~days)
    # and the last one one day before the deadline (offset 1).
    offsets = set()
    for i in range(effective):
        frac = i / (effective - 1)  # 0.0 .. 1.0
        # offset = days at frac 0 (start), 1 at frac 1 (just before deadline).
        offset = round(days - frac * (days - 1))
        offset = max(1, min(days, offset))
        offsets.add(offset)

    # Sorted descending: earliest reminder (largest offset) first.
    return sorted(offsets, reverse=True)


class ClickableLabel(QLabel):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)



class BalTxFeesWidget(QWidget):
    valueChanged = pyqtSignal()
    current_value = None

    def __init__(self, bal_window, parent, value=None):
        super().__init__(parent)
        self.bal_window = bal_window
        layout = QHBoxLayout(self)
        self.txfee_widget = QSpinBox(self)
        self.txfee_widget.setMinimum(1)
        self.txfee_widget.setMaximum(10000)
        # Group C / C5: hovering the fee field explains what the number means.
        self.txfee_widget.setToolTip(
            _("Mining fee rate in sat/vByte used for the will transactions")
        )
        value = (
            value
            if value
            else self.bal_window.bal_plugin.WILL_SETTINGS.get()["baltx_fees"]
        )
        self.set_value(value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "baltx_fees"
        ]
        self.txfee_widget.valueChanged.connect(self.on_heir_tx_fees)
        #label = ClickableLabel("＄")
        #label.doubleClicked.connect(self.doubleclick)
        #layout.addWidget(label)
        button = HelpButton(_("mining fees expressed in sats/vbyte to be used in the Bitcoin transaction.\nHigher value ensure your transaction will be confirmed"))
        button.setText("丰")
        # Hover tooltip for the small "丰" help icon (the long explanation still
        # appears on click via the HelpButton); makes the icon self-explanatory.
        button.setToolTip(_("Miner fee, click for more information"))
        # Enlarge only the "丰" glyph on the button itself; without scoping the
        # rule to QPushButton it also enlarged the tooltip font (making it bigger
        # than the other tooltips, e.g. the calendar one). Scoping it keeps the
        # tooltip at the default size like everywhere else.
        button.setStyleSheet("QPushButton{font-size: 16px;}")
        layout.addWidget(button)
        layout.addWidget(self.txfee_widget)
        # Expose the leading icon (prefix) and the editable field so the parent
        # WillSettingsWidget can align them on a grid (see its vertical layout).
        self.prefix_widget = button
        self.field_widget = self.txfee_widget

    def doubleclick(self, event=None):
        pass

    def set_read_only(self, read_only=True):
        # Show the fee but make it non-editable (no spin arrows, no keyboard),
        # so it can only be changed from the "Build your will" wizard.
        self.txfee_widget.setReadOnly(read_only)
        self.txfee_widget.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
            if read_only
            else QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        # Light-grey background when locked, so the read-only state is visible
        # (same look as the date fields); empty stylesheet restores the
        # editable appearance used inside the wizard.
        self.txfee_widget.setStyleSheet(
            "QSpinBox{background-color:#f0f0f0;}" if read_only else ""
        )

    def get_value(self):
        return self.txfee_widget.value()

    def set_value(self, value, emit=True):
        value = int(value) if value is not None else 20
        if getattr(self, "_updating", False):
            return

        self._updating = True
        try:
            self.current_value = value
            spin = self.txfee_widget
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

        finally:
            self._updating = False

        if emit:
            spin.valueChanged.emit(value)

    def on_heir_tx_fees(self, value=None, update_all=True):
        if value != self.current_value:
            try:
                self.set_value(value)
                if update_all:
                    self.bal_window.update_setting_widgets(
                        self.get_value(), "baltx_fees", True
                    )
            except Exception as e:
                _logger.error(f"error while trying to update txfees{e}")
                log_error(e)
        else:
            pass



class _LockTimeEditor:
    min_allowed_value = NLOCKTIME_MIN
    max_allowed_value = NLOCKTIME_MAX
    alarm = None

    def get_value(self) -> Optional[int]:
        raise NotImplementedError()

    def set_value(self, x: Any, force=True) -> None:
        raise NotImplementedError()

    @classmethod
    def is_acceptable_locktime(cls, x: Any) -> bool:
        if not x:  # e.g. empty string
            return True
        try:
            x = int(x)
        except Exception as _e:
            return False
        return cls.min_allowed_value <= x <= cls.max_allowed_value

    @staticmethod
    def get_max_allowed_timestamp() -> int:
        ts = NLOCKTIME_MAX
        # Test if this value is within the valid timestamp limits (which is platform-dependent).
        # see #6170
        try:
            datetime.fromtimestamp(ts)
        except (OSError, OverflowError):
            ts = 2**31 - 1  # INT32_MAX
            datetime.fromtimestamp(ts)  # test if raises
        return ts



class BalTimeEditWidget(QWidget, _LockTimeEditor):
    valueEdited = pyqtSignal()
    _setting_locktime = False
    current_value = None
    current_index = None
    default_value = None

    help_text = (
        "if you choose Raw, you can insert various options based on suffix:\n"
        + " - d: number of days after current day(ex: 1d means tomorrow)\n"
        + " - y: number of years after currrent day(ex: 1y means one year from today)\n"
    )
    label_text = None
    tooltip_text = None
    base_field = None

    def __init__(self, bal_window, parent, default_locktime=None):
        super().__init__(parent)
        self.bal_window = bal_window

        hbox = QHBoxLayout()
        self.setLayout(hbox)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        self.setMinimumWidth(40 * char_width_in_lineedit())
        self.locktime_raw_e = TimeRawEditWidget(self, time_edit=self)
        self.locktime_date_e = LockTimeDateEdit(self, time_edit=self)
        self.editors = [self.locktime_raw_e, self.locktime_date_e]
        self.combo = QComboBox()
        options = [_("Raw"), _("Date")]
        self.option_index_to_editor_map = {
            0: self.locktime_raw_e,
            1: self.locktime_date_e,
        }
        self.combo.addItems(options)
        default_index = 0
        if not default_locktime:
            default_locktime = self.bal_window.bal_plugin.WILL_SETTINGS.get()[self.base_field]
        try:
            int(default_locktime)
            default_index = 1
        except Exception:
            default_index = 0
        #hbox.addWidget(QLabel(self.label_text))
        help_button=HelpButton(self.help_text)
        help_button.setText(self.label_text)
        # Show a short label (e.g. "Delivery time" / "Check Alive") when the
        # user hovers the icon, so the emoji button is self-explanatory.
        if self.tooltip_text:
            help_button.setToolTip(_(self.tooltip_text))
        #help_button.setStyleSheet("font-size: 155555);
        hbox.addWidget(help_button)
        # Expose the leading icon (prefix) so the parent WillSettingsWidget can
        # align all rows on a common left edge (see its vertical layout).
        self.prefix_widget = help_button
        self.combo.currentIndexChanged.connect(self.on_current_index_changed)

        for w in self.editors:
            w.setVisible(False)
            w.setEnabled(False)

        self.editor = self.option_index_to_editor_map[default_index]
        self.editor.setVisible(True)
        self.editor.setEnabled(True)
        self.set_index(default_index)
        #self.on_current_index_changed(default_index)
        self.set_value(default_locktime)
        self.current_value=default_locktime
        hbox.addWidget(self.combo)
        for w in self.editors:
            hbox.addWidget(w)

        hbox.addStretch(1)
        # spssscer_widget = QWidget()
        # spacer_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # hbox.addWidget(spacer_widget)
        self.valueEdited.connect(lambda: self.update_will_settings(True))
        self.locktime_raw_e.editingFinished.connect(self.valueEdited.emit)
        self.locktime_date_e.dateTimeChanged.connect(self.valueEdited.emit)
        #self.combo.currentIndexChanged.connect(self.valueEdited.emit)

    def update_will_settings(
        self,
        update_all=False,
        update_will_dialog=False,
        update_heirs_dialog=False,
    ):
        self.bal_window.update_setting_widgets(
            self.get_value(),
            self.base_field,
            update_all,
            update_will_dialog,
            update_heirs_dialog,
        )

    def on_current_index_changed(self, i):
        self.current_index = i
        for w in self.editors:
            w.setVisible(False)
            w.setEnabled(False)
        # prev_locktime = self.editor.get_value()
        self.editor = self.option_index_to_editor_map[i]
        if i==0:
            self.editor.set_value(self.bal_window.bal_plugin.default_will_settings_relative()[self.base_field])
        else:
            self.editor.set_value(self.bal_window.bal_plugin.default_will_settings_absolute()[self.base_field])
        self.valueEdited.emit()
        # if self.editor.is_acceptable_locktime(prev_locktime):
        #    self.editor.set_value(prev_locktime, force=False)
        self.editor.setVisible(True)
        self.editor.setEnabled(True)
        self.bal_window.update_combo_setting_widgets(i, self.base_field,True)

    def get_value(self) -> Optional[str]:
        val = self.editor.get_value()
        #return self.current_value
        return val

    def set_index(self, index):
        if self.current_index != index:
            self.combo.setCurrentIndex(index)
            #self.on_current_index_changed(index, force)

    def set_value(
        self,
        x: Any,
        force=None,
        update_all=False,
        update_will_dialog=False,
        update_heirs_dialog=False,
    ) -> None:
        if not x:
            if self.current_index == 0:
                x = self.bal_window.bal_plugin.default_will_settings_relative()[self.base_field]
            elif self.current_index == 1:
                x = self.bal_window.bal_plugin.default_will_settings_absolute()[self.base_field]
        if x != self.get_value():
            self.editor.set_value(x)
            self.current_value = x
            self.bal_window.update_setting_widgets(x, self.base_field)

    def set_read_only(self, read_only=True):
        """Show the value but make it non-editable.

        Used everywhere except the "Build your will" wizard, where the date is
        the only place the user is allowed to change it. The Raw/Date combo is
        disabled and both editors become read-only with no spin buttons.
        """
        self.combo.setEnabled(not read_only)
        for w in self.editors:
            w.set_read_only(read_only)



class TimeRawEditWidget(QWidget):
    editingFinished = pyqtSignal()

    def is_acceptable_locktime(self, value):
        return True

    def __init__(self, parent, time_edit=None):
        super().__init__(parent)
        self.editor = LockTimeRawEdit(parent, time_edit)
        self.label = QLabel("")
        # Group C / C3: this trailing label shows the ABSOLUTE date computed
        # from the RAW value (e.g. "30d" -> "2027-06-23"), so it needs room for a
        # full "YYYY-MM-DD" string (~10 characters). Only the input box itself
        # (LockTimeRawEdit) is narrowed; shrinking this label was a mistake that
        # truncated the computed date.
        self.label.setFixedWidth(10 * char_width_in_lineedit())
        self.layout = QHBoxLayout(self)
        self.layout.addWidget(self.editor)
        self.layout.addWidget(self.label)
        self.editor.editingFinished.connect(self.editingFinished.emit)
        self.get_value = self.editor.get_value
        self.set_value = self.editor.set_value

    def set_read_only(self, read_only=True):
        self.editor.setReadOnly(read_only)
        # Match the Date editor: grey background when locked so the read-only
        # state is visible; empty stylesheet restores the editable look.
        self.editor.setStyleSheet(
            "QLineEdit{background-color:#f0f0f0;}" if read_only else ""
        )



class LockTimeRawEdit(QLineEdit, _LockTimeEditor):
    def __init__(self, parent=None, time_edit=None):
        QLineEdit.__init__(self, parent)
        # Group C / C3: narrow the RAW input to roughly a third of its former
        # width. The accepted values are short relative durations such as "30d"
        # or "1y", so a handful of characters is plenty while still leaving room
        # for larger day counts (e.g. "3650d").
        self.setFixedWidth(6 * char_width_in_lineedit())
        self.textChanged.connect(self.numbify)
        self.isdays = False
        self.isyears = False
        self.time_edit = time_edit

    @staticmethod
    def replace_str(text):
        """Strip the relative-time suffixes (d/y) from the text.

        Only days ("d") and years ("y") are supported. The block-height
        suffix ("b") was removed (A1): locktimes are always timestamps now.
        """
        return str(text).replace("d", "").replace("y", "")

    def checkbdy(self, s, pos, appendix):
        try:
            charpos = pos - 1
            charpos = max(0, charpos)
            charpos = min(len(s) - 1, charpos)
            if appendix == s[charpos]:
                s = self.replace_str(s) + appendix
                pos = charpos
        except Exception:
            pass
        return pos, s

    def numbify(self):
        # Only digits plus the day ("d") and year ("y") suffixes are accepted.
        # The block-height suffix ("b") was removed (A1): locktimes are always
        # UNIX timestamps now, so block-relative input is no longer allowed.
        text = self.text().strip()
        chars = "0123456789dy"
        pos = self.cursorPosition()
        pos = len("".join([i for i in text[:pos] if i in chars]))
        s = "".join([i for i in text if i in chars])
        self.isdays = False
        self.isyears = False

        pos, s = self.checkbdy(s, pos, "d")
        pos, s = self.checkbdy(s, pos, "y")

        if "d" in s:
            self.isdays = True
        if "y" in s:
            self.isyears = True

        if self.isdays:
            s = self.replace_str(s) + "d"
        if self.isyears:
            s = self.replace_str(s) + "y"
        self.blockSignals(True)
        self.setText(s)
        self.blockSignals(False)
        # self.set_value(s, force=False)
        self.current_value = s
        # setText sets Modified to False.  Instead we want to remember
        # if updates were because of user modification.
        self.setModified(self.hasFocus())
        self.setCursorPosition(pos)

    def get_value(self) -> Optional[str]:
        try:
            return str(self.text())
        except Exception:
            return None

    def set_value(self, x: Any, force=True) -> None:
        if x != self.get_value():
            self.blockSignals(True)
            self.setText(str(x))
            self.blockSignals(False)
            self.numbify()



class LockTimeDateEdit(QDateTimeEdit, _LockTimeEditor):
    # GUARD (kept on purpose, A1): NLOCKTIME_BLOCKHEIGHT_MAX is the highest value
    # Bitcoin interprets as a *block height*. By forcing the minimum to one above
    # it, every locktime entered here is guaranteed to be a UNIX *timestamp*,
    # never a block height. This is NOT block-height ordering; it is the
    # "bouncer" that prevents block-height values from ever being used again.
    min_allowed_value = NLOCKTIME_BLOCKHEIGHT_MAX + 1
    max_allowed_value = _LockTimeEditor.get_max_allowed_timestamp()

    def __init__(self, parent=None, time_edit=None):
        QDateTimeEdit.__init__(self, parent)
        self.setMinimumDateTime(datetime.fromtimestamp(self.min_allowed_value))
        self.setMaximumDateTime(datetime.fromtimestamp(self.max_allowed_value))
        #self.setDateTime(QDateTime.currentDateTime())
        self.time_edit = time_edit

    def set_read_only(self, read_only=True):
        # Read-only display: keyboard editing disabled and the up/down spin
        # arrows removed, so the date can only be changed from the wizard.
        self.setReadOnly(read_only)
        self.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
            if read_only
            else QAbstractSpinBox.ButtonSymbols.UpDownArrows
        )
        # A read-only QDateTimeEdit keeps a white background by default, which
        # does not visually signal that it is locked.  Paint it light grey (like
        # the disabled combo/fee fields next to it) so the user sees at a glance
        # that the date is not editable here; an empty stylesheet restores the
        # default look when the field is made editable again (in the wizard).
        self.setStyleSheet(
            "QDateTimeEdit{background-color:#f0f0f0;}" if read_only else ""
        )

    def get_value(self) -> Optional[int]:
        #dt = self.dateTime().toPyDateTime()
        #locktime = int(time.mktime(dt.timetuple()))
        #p#
        #dt = dt_edit.dateTime()
        ## QDateTimets = dt.toSecsSinceEpoch()

        dt = self.dateTime()
        _ts = dt.toSecsSinceEpoch()

        return _ts


    def set_value(self, x: Any, force=False) -> None:
        if not self.is_acceptable_locktime(x):
            self.setDateTime(QDateTime.currentDateTime())
            return
        try:
            x = int(x)
        except Exception as e:
            x = QDateTime.currentDateTime().timestamp()
        finally:
            # Use the overflow-safe converter: on Windows datetime.fromtimestamp
            # raises OverflowError for timestamps past 2038 (e.g. NLOCKTIME_MAX).
            _dt = BalTimestamp._safe_fromtimestamp(x)
            #if self.alarm != dt:
            self.setDateTime(_dt)
            self.alarm = _dt



class ThresholdTimeWidget(BalTimeEditWidget):
    # rich_text=True is used by the HelpButton, so HTML tags (<b>, <br>) render.
    help_text = (
        "<b>CHECK ALIVE</b><br><br>"
        "Check to ask for invalidation.<br><br>"
        "When less then this time is missing, ask to invalidate.<br>"
        "If you fail to invalidate during this time, your transactions will be delivered to your heirs.<br><br>"
        "if you choose Raw, you can insert various options based on suffix:<br>"
        " - d: number of days after current day(ex: 1d means tomorrow)<br>"
        " - y: number of years after currrent day(ex: 1y means one year from today)<br>"
    )
    label_text = "🚨"
    #label_text = "Check Alive"
    tooltip_text = "Check Alive"
    base_field = "threshold"

    def __init__(self, bal_window, parent, init_value=None):
        if init_value is None:
            init_value = bal_window.bal_plugin.WILL_SETTINGS.get()["threshold"]
        super().__init__(bal_window, parent, init_value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "threshold"
        ]



class LockTimeWidget(BalTimeEditWidget):
    # rich_text=True is used by the HelpButton, so HTML tags (<b>, <br>) render.
    help_text = (
        "<b>DELIVERY TIME</b><br><br>"
        "Set Locktime for transactions.<br>"
        "Any time is needed transaction will be anticipated by 1day<br><br>"
        "if you choose Raw, you can insert various options based on suffix:<br>"
        " - d: number of days after current day(ex: 1d means tomorrow)<br>"
        " - y: number of years after currrent day(ex: 1y means one year from today)<br>"
    )
    label_text = "🚛"
    #label_text = "Locktime"
    tooltip_text = "Delivery time"
    base_field = "locktime"

    def __init__(self, bal_window, parent, init_value=None):
        if init_value is None:
            init_value = bal_window.bal_plugin.WILL_SETTINGS.get()["locktime"]
        super().__init__(bal_window, parent, init_value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "locktime"
        ]



class WillSettingsWidget(QWidget):

    def __init__(self, bal_window: "BalWindow", parent, layout_type="h",
                 read_only=True):
        self.widgets = {}
        QWidget.__init__(self, parent)
        self.bal_window = bal_window
        # When read_only=True (toolbars, Heirs tab) the delivery time, check
        # alive and fee fields are display-only; they can only be edited from
        # the "Build your will" wizard, which passes read_only=False.
        self.read_only = read_only
        box = QHBoxLayout(self) if layout_type == "h" else QVBoxLayout(self)

        self.calendar_button = QPushButton()
        self.calendar_button.setIcon(
            read_QIcon_from_bytes(
                self.bal_window.bal_plugin.read_file("icons/calendar.png")
            )
        )
        # Tooltip so the icon is self-explanatory when hovered (Group C / C5).
        self.calendar_button.setToolTip(
            _("Export reminder dates to your calendar (.ics)")
        )
        self.calendar_button.clicked.connect(self.open_or_save_calendar)
        self.widgets["locktime"] = LockTimeWidget(bal_window, self)
        self.widgets["threshold"] = ThresholdTimeWidget(bal_window, self)
        self.widgets["locktime"].valueEdited.connect(self.on_locktime_change)
        self.widgets["threshold"].valueEdited.connect(self.on_locktime_change)
        # self.widgets['baltx_fees'].valueChange.connect(self.bal_window.update_setting_widgets)
        self.on_locktime_change()
        self.widgets["baltx_fees"] = BalTxFeesWidget(bal_window, self)
        if not hasattr(bal_window, "txfee_widgets"):
            bal_window.txfee_widgets = []

        w = self.widgets["baltx_fees"]
        if w not in bal_window.txfee_widgets:
            bal_window.txfee_widgets.append(w)
        if layout_type == "h":
            box.addWidget(self.widgets["locktime"])
            box.addWidget(self.widgets["threshold"])
            box.addWidget(self.calendar_button)
            box.addWidget(self.widgets["baltx_fees"])
        else:
            # Vertical layout (the "Build your will" wizard): make every row the
            # same width and left aligned so they all fit in one tidy block,
            # instead of letting the calendar button and the fee field stretch to
            # the dialog's right edge (which made them far wider than the date
            # rows above).
            #
            # IMPORTANT: the leading icons keep their ORIGINAL size.  The icons
            # are HelpButtons, which already pin themselves to a fixed width
            # (2.2 * char_width_in_lineedit()); we must NOT widen them, otherwise
            # they look oversized compared with the original toolbar layout.  We
            # only need to (1) align the calendar row's left edge with the icons'
            # original width and (2) cap every row to the date-row width.
            locktime_w = self.widgets["locktime"]
            threshold_w = self.widgets["threshold"]
            fees_w = self.widgets["baltx_fees"]

            # Original icon width (HelpButton's own fixed width); used only to
            # offset the calendar button so its field starts under the others.
            icon_w = locktime_w.prefix_widget.sizeHint().width()

            # Common row width = natural width of the date rows (the reference).
            row_w = max(
                locktime_w.sizeHint().width(),
                threshold_w.sizeHint().width(),
            )
            for w in (locktime_w, threshold_w, fees_w):
                w.setFixedWidth(row_w)

            # The calendar row has no prefix icon: wrap it so it starts with an
            # empty spacer of the icon width (calendar field aligned with the
            # date/fee fields) and cap it to the same total width as the rows
            # above, so it no longer stretches to the dialog's right edge.
            calendar_row = QWidget(self)
            calendar_box = QHBoxLayout(calendar_row)
            calendar_box.setContentsMargins(0, 0, 0, 0)
            calendar_box.setSpacing(0)
            calendar_spacer = QWidget()
            calendar_spacer.setFixedWidth(icon_w)
            calendar_box.addWidget(calendar_spacer)
            calendar_box.addWidget(self.calendar_button)
            calendar_row.setFixedWidth(row_w)

            box.addWidget(locktime_w, alignment=Qt.AlignmentFlag.AlignLeft)
            box.addWidget(threshold_w, alignment=Qt.AlignmentFlag.AlignLeft)
            box.addWidget(calendar_row, alignment=Qt.AlignmentFlag.AlignLeft)
            box.addWidget(fees_w, alignment=Qt.AlignmentFlag.AlignLeft)

        # Group C / C2: apply the current "Editable dates" setting to the date
        # fields. Done once at creation here, and re-applied later by
        # apply_editable_dates() whenever the setting changes (called from
        # BalWindow.update_all()), so toggling the checkbox takes effect
        # immediately, exactly like the "Hide Invalidated" filter does.
        self.apply_editable_dates()

    def apply_editable_dates(self):
        """Re-read the EDITABLE_DATES setting and lock/unlock the editable fields.

        Outside the "Build your will" wizard (``read_only=True``) the
        delivery-time, check-alive dates AND the mining fee are display-only by
        default. When the user ticks "Editable dates" in the settings, all three
        fields (locktime, threshold and fee) become editable here too; when it
        is unticked they all go back to read-only. The fee follows exactly the
        same rule as the dates (it used to stay always read-only, but the user
        asked for the fee to be editable together with the dates).

        This is safe to call repeatedly: it only adjusts the read-only state of
        the already-created sub-widgets, it does not rebuild anything. It is the
        per-update hook that lets the settings checkbox take effect without
        having to recreate the toolbar / re-open the window.
        """
        # Inside the wizard the dates are always editable; nothing to do.
        if not self.read_only:
            return

        editable_dates = False
        try:
            editable_dates = self.bal_window.bal_plugin.EDITABLE_DATES.get()
        except Exception:
            # If the setting cannot be read, fall back to the safe default
            # (dates remain read-only outside the wizard).
            editable_dates = False

        self.widgets["locktime"].set_read_only(not editable_dates)
        self.widgets["threshold"].set_read_only(not editable_dates)
        # The fee now follows the very same "Editable dates" rule as the dates:
        # editable outside the wizard only when the setting is ticked.
        self.widgets["baltx_fees"].set_read_only(not editable_dates)

    def create_alarms(self, alarm_start, alarm_end):
        """Build the VALARM reminder blocks for the .ics event (Group D / D1).

        The number of reminders is read from the NUM_REMINDERS setting (default
        3, capped at 5 by the settings dialog). They are spread uniformly across
        the check-alive period and always fall before the delivery deadline; if
        the period is shorter than the requested number, at most one reminder
        per day is produced (see compute_reminder_offsets).

        Args:
            alarm_start: the check-alive datetime (start of the period).
            alarm_end: the delivery-time / locktime datetime (the deadline).

        Returns:
            A list of .ics text lines (possibly empty) describing the VALARMs.
        """
        days = (alarm_end - alarm_start).days

        # How many reminders the user asked for (default 3 if unreadable).
        try:
            count = int(self.bal_window.bal_plugin.NUM_REMINDERS.get())
        except Exception:
            count = 3

        offsets = compute_reminder_offsets(days, count)

        # Reminder text shown by the calendar app when each alarm fires.
        description = _(
            "BAL reminder: check in before your will is delivered to your heirs."
        )

        lines = []
        for offset in offsets:
            lines.extend(
                [
                    "BEGIN:VALARM",
                    # Fire "offset" days before the event end (the deadline).
                    f"TRIGGER;RELATED=END:-P{offset}D",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{BalCalendar.ical_escape(description)}",
                    "END:VALARM",
                ]
            )
        return lines

    def open_or_save_calendar(self):
        now = BalCalendar.format_time(datetime.now())

        locktime = self.widgets["locktime"].alarm
        threshold = self.widgets["threshold"].alarm
        alarm_end = BalCalendar.format_time(locktime)
        alarm_start = BalCalendar.format_time(threshold)

        heirs_details = "\r\n".join(f" {heir} - {self.bal_window.heirs[heir][0]}, {self.bal_window.heirs[heir][1]}" for heir in self.bal_window.heirs)
        event_description = BalCalendar.ical_escape(
                f"{self.bal_window.bal_plugin.EVENT_DESCRIPTION.get()}".replace("$wallet_name",str(self.bal_window.wallet)).replace("$heirs_complete",heirs_details)
        )
        #event_description =f"{event_description}{heirs_details}"
        uid = f"bal-{str(self.bal_window.wallet)}"
        summary = BalCalendar.ical_escape(
            f"{self.bal_window.bal_plugin.EVENT_SUMMARY.get()}".replace("$wallet_name",str(self.bal_window.wallet))
        )
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:-//Bitcoin After Life//Electrum Plugin/{BalPlugin.__version__}",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{alarm_end}",
            f"DTEND:{alarm_end}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{event_description}",
        ]
        lines.extend(self.create_alarms(threshold, locktime))
        lines.extend([
            "END:VEVENT",
            "END:VCALENDAR",
        ])

        lines = [s.rstrip("\r\n") for s in lines]
        ics_content = "\r\n".join(lines) + "\r\n"
        # Keep the generated .ics in a temp file; it is copied to the path the
        # user picks below.
        self.temp_path = BalCalendar.write_temp_ics(ics_content)

        # Group D / D1b: always ask the user WHERE to save the .ics file (the
        # plugin no longer tries to open it with a calendar app). The save
        # dialog opens on the user's Desktop by default, with an .ics filter and
        # a sensible default filename.
        desktop = BalCalendar.desktop_dir()
        default_path = os.path.join(desktop, "will_event.ics")
        target = getSaveFileName(
            parent=self.bal_window.window,
            title=_("Save calendar reminder (.ics)"),
            # An absolute filename makes getSaveFileName ignore its remembered
            # IO_DIRECTORY and open on the Desktop instead.
            filename=default_path,
            filter="iCalendar (*.ics);;All files (*)",
            default_extension="ics",
            config=self.bal_window.window.config,
        )
        if not target:
            # User cancelled the save dialog: nothing to do.
            return
        try:
            self.save_ics_to(target)
        except Exception as save_err:
            _logger.error(f"saving .ics failed: {save_err}")
            self.bal_window.show_warning(
                _("Could not save the calendar file: {}").format(save_err)
            )
            return
        self.bal_window.show_message(
            _("Calendar file saved to:\n{}").format(target)
        )

    def save_ics_to(self, target):
        """Copy the generated .ics from the temp file to ``target`` (Group D / D1b).

        Overwrites the destination if it already exists. Used by
        open_or_save_calendar after the user picks a save location.

        Args:
            target: absolute destination path chosen by the user.

        Returns:
            The destination path.
        """
        _logger.debug(f"save_ics_to {self.temp_path} -> {target}")
        with open(self.temp_path, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
        return target

    def on_locktime_change(self):
        locktime = self.widgets["locktime"].get_value()
        threshold = self.widgets["threshold"].get_value()
        locktime = BalTimestamp(locktime)
        threshold = BalTimestamp(threshold)

        min_locktime = min(
                Will.get_min_locktime(self.bal_window.willitems, NLOCKTIME_MAX),
                locktime.to_timestamp(),
        )
        td = threshold.to_date(min_locktime, True)
        self.widgets["threshold"].alarm=td
        self.bal_window.will_settings["real_threshold"]=td.timestamp()
        try:
            self.widgets["threshold"].editor.label.setText(td.strftime("%Y-%m-%d"))
        except Exception as _e:
            pass

        td = locktime.to_date()
        alarm = BalTimestamp(min_locktime).to_date()
        self.widgets["locktime"].alarm=alarm
        self.bal_window.will_settings["real_locktime"]=td.timestamp()
        try:
            self.widgets["locktime"].editor.label.setText(td.strftime("%Y-%m-%d"))
        except Exception as _e:
            pass



class PercAmountEdit(BTCAmountEdit):
    def __init__(self, decimal_point, is_int=False, parent=None, *, max_amount=None):
        super().__init__(decimal_point, is_int, parent, max_amount=max_amount)

    def numbify(self):
        text = self.text().strip()
        if text == "!":
            self.shortcut.emit()
            return
        pos = self.cursorPosition()
        chars = "0123456789%"
        chars += DECIMAL_POINT

        s = "".join([i for i in text if i in chars])

        if "%" in s:
            self.is_perc = True
            s = s.replace("%", "")
        else:
            self.is_perc = False

        if DECIMAL_POINT in s:
            p = s.find(DECIMAL_POINT)
            s = s.replace(DECIMAL_POINT, "")
            s = s[:p] + DECIMAL_POINT + s[p : p + 8]
        if self.is_perc:
            s += "%"

        self.setText(s)
        self.setModified(self.hasFocus())
        self.setCursorPosition(pos)

    def _get_amount_from_text(self, text: str) -> Union[None, Decimal, int]:
        try:
            text = text.replace(DECIMAL_POINT, ".")
            text = text.replace("%", "")
            return (Decimal)(text)
        except Exception:
            return None

    def _get_text_from_amount(self, amount):
        out = super()._get_text_from_amount(amount)
        if self.is_perc:
            out += "%"
        return out

    def paintEvent(self, event):
        QLineEdit.paintEvent(self, event)
        if self.base_unit:
            panel = QStyleOptionFrame()
            self.initStyleOption(panel)
            textRect = self.style().subElementRect(
                QStyle.SubElement.SE_LineEditContents, panel, self
            )
            textRect.adjust(2, 0, -10, 0)
            painter = QPainter(self)
            painter.setPen(ColorScheme.GRAY.as_color())
            if len(self.text()) == 0:
                painter.drawText(
                    textRect,
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    self.base_unit() + " or perc value",
                )



class BalLineEdit(QLineEdit):
    def __init__(self,variable):
        QLineEdit.__init__(self)
        self.setText(variable.get())
        def on_edit():
            variable.set(self.text())
        self.editingFinished.connect(on_edit)


class BalTextEdit(QTextEdit):
    def __init__(self,variable):
        QTextEdit.__init__(self)
        self.setPlainText(variable.get())
        def on_edit():
            variable.set(self.toPlainText())
        self.textChanged.connect(on_edit)


class BalCheckBox(QCheckBox):
    def __init__(self, variable, on_click=None):
        QCheckBox.__init__(self)
        self.setChecked(variable.get())
        self.on_click = on_click

        def on_check(v):
            variable.set(v == 2)
            #variable.get()
            if self.on_click:
                self.on_click()

        self.stateChanged.connect(on_check)


class BalSpinBox(QSpinBox):
    """Integer spin box bound to a BalConfig value (Group D / D1).

    Mirrors BalCheckBox / BalLineEdit: it shows the persisted value on creation
    and writes the new value back to the config whenever the user changes it.

    Args:
        variable: the BalConfig accessor to read from / write to.
        minimum: smallest selectable value (default 1).
        maximum: largest selectable value (default 5, used by "Number of
            reminders").
        on_change: optional callback invoked after the value is persisted.
    """

    def __init__(self, variable, minimum=1, maximum=5, on_change=None):
        QSpinBox.__init__(self)
        self.setMinimum(minimum)
        self.setMaximum(maximum)
        # Coerce the stored value to int and clamp it into the allowed range,
        # so a stale/invalid config value can never push the spin box out of
        # bounds.
        try:
            current = int(variable.get())
        except Exception:
            current = minimum
        current = max(minimum, min(maximum, current))
        self.setValue(current)
        self.on_change = on_change

        def on_value_changed(v):
            variable.set(int(v))
            if self.on_change:
                self.on_change()

        self.valueChanged.connect(on_value_changed)



class WillWidget(QWidget):
    def __init__(self, father=None, parent=None):
        super().__init__()
        vlayout = QVBoxLayout()
        self.setLayout(vlayout)
        self.will = parent.bal_window.willitems
        self._bal_parent = parent
        for w in self.will:
            if (
                self.will[w].get_status("REPLACED")
                and self._bal_parent.bal_window.bal_plugin._hide_replaced
            ):
                continue
            if (
                self.will[w].get_status("INVALIDATED")
                and self._bal_parent.bal_window.bal_plugin._hide_invalidated
            ):
                continue
            f = self.will[w].father
            if father == f:
                qwidget = QWidget()
                # childWidget = QWidget()
                hlayout = QHBoxLayout(qwidget)
                qwidget.setLayout(hlayout)
                vlayout.addWidget(qwidget)
                detailw = QWidget()
                detaillayout = QVBoxLayout()
                detailw.setLayout(detaillayout)

                willpushbutton = QPushButton(w)

                willpushbutton.clicked.connect(
                    partial(self._bal_parent.bal_window.show_transaction, txid=w)
                )
                detaillayout.addWidget(willpushbutton)
                locktime = str(BalTimestamp(self.will[w].tx.locktime))
                creation = str(BalTimestamp(self.will[w].time))

                def qlabel(title, value):
                    label = "<b>" + _(str(title)) + f":</b>\t{str(value)}"
                    return QLabel(label)

                detaillayout.addWidget(qlabel("Locktime", locktime))
                detaillayout.addWidget(qlabel("Creation Time", creation))
                try:
                    total_fees = (
                        self.will[w].tx.input_value() - self.will[w].tx.output_value()
                    )
                except Exception:
                    total_fees = -1
                decoded_fees = total_fees
                fee_per_byte = round(total_fees / self.will[w].tx.estimated_size(), 3)
                fees_str = str(decoded_fees) + " (" + str(fee_per_byte) + " sats/vbyte)"
                detaillayout.addWidget(qlabel("Transaction fees:", fees_str))
                detaillayout.addWidget(qlabel("Status:", self.will[w].status))
                detaillayout.addWidget(QLabel(""))
                detaillayout.addWidget(QLabel("<b>Heirs:</b>"))
                for heir in self.will[w].heirs:
                    if 'w!ll3x3c"' not in heir:
                        decoded_amount = Util.decode_amount(
                            self.will[w].heirs[heir][3], self._bal_parent.decimal_point
                        )
                        detaillayout.addWidget(
                            qlabel(
                                heir, f"{decoded_amount} {self._bal_parent.base_unit_name}"
                            )
                        )
                if self.will[w].we:
                    detaillayout.addWidget(QLabel(""))
                    detaillayout.addWidget(QLabel(_("<b>Willexecutor:</b:")))
                    decoded_amount = Util.decode_amount(
                        self.will[w].we["base_fee"], self._bal_parent.decimal_point
                    )

                    detaillayout.addWidget(
                        qlabel(
                            self.will[w].we["url"],
                            f"{decoded_amount} {self._bal_parent.base_unit_name}",
                        )
                    )
                detaillayout.addStretch()
                pal = QPalette()
                pal.setColor(
                    QPalette.ColorRole.Window, QColor(status_color(self.will[w]))
                )
                detailw.setAutoFillBackground(True)
                detailw.setPalette(pal)

                hlayout.addWidget(detailw)
                hlayout.addWidget(WillWidget(w, parent=parent))


