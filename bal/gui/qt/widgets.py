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
        button.setStyleSheet("font-size: 16px;")
        layout.addWidget(button)
        layout.addWidget(self.txfee_widget)

    def doubleclick(self, event=None):
        pass
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
        #help_button.setStyleSheet("font-size: 155555);
        hbox.addWidget(help_button)
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



class TimeRawEditWidget(QWidget):
    editingFinished = pyqtSignal()

    def is_acceptable_locktime(self, value):
        return True

    def __init__(self, parent, time_edit=None):
        super().__init__(parent)
        self.editor = LockTimeRawEdit(parent, time_edit)
        self.label = QLabel("")
        self.label.setFixedWidth(10 * char_width_in_lineedit())
        self.layout = QHBoxLayout(self)
        self.layout.addWidget(self.editor)
        self.layout.addWidget(self.label)
        self.editor.editingFinished.connect(self.editingFinished.emit)
        self.get_value = self.editor.get_value
        self.set_value = self.editor.set_value



class LockTimeRawEdit(QLineEdit, _LockTimeEditor):
    def __init__(self, parent=None, time_edit=None):
        QLineEdit.__init__(self, parent)
        self.setFixedWidth(12 * char_width_in_lineedit())
        self.textChanged.connect(self.numbify)
        self.isdays = False
        self.isyears = False
        self.isblocks = False
        self.time_edit = time_edit

    @staticmethod
    def replace_str(text):
        return str(text).replace("d", "").replace("y", "").replace("b", "")

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
        text = self.text().strip()
        # chars = '0123456789bdy' removed the option to choose locktime by block
        chars = "0123456789dy"
        pos = self.cursorPosition()
        pos = len("".join([i for i in text[:pos] if i in chars]))
        s = "".join([i for i in text if i in chars])
        self.isdays = False
        self.isyears = False
        self.isblocks = False

        pos, s = self.checkbdy(s, pos, "d")
        pos, s = self.checkbdy(s, pos, "y")
        pos, s = self.checkbdy(s, pos, "b")

        if "d" in s:
            self.isdays = True
        if "y" in s:
            self.isyears = True
        if "b" in s:
            self.isblocks = True

        if self.isdays:
            s = self.replace_str(s) + "d"
        if self.isyears:
            s = self.replace_str(s) + "y"
        if self.isblocks:
            s = self.replace_str(s) + "b"
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
    min_allowed_value = NLOCKTIME_BLOCKHEIGHT_MAX + 1
    max_allowed_value = _LockTimeEditor.get_max_allowed_timestamp()

    def __init__(self, parent=None, time_edit=None):
        QDateTimeEdit.__init__(self, parent)
        self.setMinimumDateTime(datetime.fromtimestamp(self.min_allowed_value))
        self.setMaximumDateTime(datetime.fromtimestamp(self.max_allowed_value))
        #self.setDateTime(QDateTime.currentDateTime())
        self.time_edit = time_edit

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
            _dt = datetime.fromtimestamp(x)
            #if self.alarm != dt:
            self.setDateTime(_dt)
            self.alarm = _dt



class ThresholdTimeWidget(BalTimeEditWidget):
    help_text = (
        "Check to ask for invalidation.\n\n"
        "When less then this time is missing, ask to invalidate.\n"
        "If you fail to invalidate during this time, your transactions will be delivered to your heirs.\n\n"
        f"{BalTimeEditWidget.help_text}"
    )
    label_text = "🚨"
    #label_text = "Check Alive"
    base_field = "threshold"

    def __init__(self, bal_window, parent, init_value=None):
        if init_value is None:
            init_value = bal_window.bal_plugin.WILL_SETTINGS.get()["threshold"]
        super().__init__(bal_window, parent, init_value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "threshold"
        ]



class LockTimeWidget(BalTimeEditWidget):
    help_text = (
        "Set Locktime for transactions.\n"
        "Any time is needed transaction will be anticipated by 1day\n"
        f"{BalTimeEditWidget.help_text}"
    )
    label_text = "🚛"
    #label_text = "Locktime"
    base_field = "locktime"

    def __init__(self, bal_window, parent, init_value=None):
        if init_value is None:
            init_value = bal_window.bal_plugin.WILL_SETTINGS.get()["locktime"]
        super().__init__(bal_window, parent, init_value)
        self.default_value = self.bal_window.bal_plugin.default_will_settings()[
            "locktime"
        ]



class WillSettingsWidget(QWidget):

    def __init__(self, bal_window: "BalWindow", parent, layout_type="h"):
        self.widgets = {}
        QWidget.__init__(self, parent)
        self.bal_window = bal_window
        box = QHBoxLayout(self) if layout_type == "h" else QVBoxLayout(self)

        self.calendar_button = QPushButton()
        self.calendar_button.setIcon(
            read_QIcon_from_bytes(
                self.bal_window.bal_plugin.read_file("icons/calendar.png")
            )
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
        box.addWidget(self.widgets["locktime"])
        box.addWidget(self.widgets["threshold"])
        box.addWidget(self.calendar_button)
        box.addWidget(self.widgets["baltx_fees"])

    def create_alarms(self, alarm_start, alarm_end):
        days = (alarm_end - alarm_start).days+1
        lines = []
        for i in range(1, days):
            lines.extend(
                [
                    "BEGIN:VALARM",
                    f"TRIGGER;RELATED=END:-P{i}D",
                    "ACTION:DISPLAY",
                    # f"DESCRIPTION:{self.bal_window.bal_plugin.ALARM_DESCRIPTION.get()}",
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
        days_difference = (locktime - threshold).days

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
        self.temp_path = BalCalendar.write_temp_ics(ics_content)
        opened = BalCalendar.open_with_default_app(
            self.bal_window.bal_plugin.CALENDAR_APP.get(), self.temp_path
        )
        if opened:
            _logger.info(f"File opened with default app: {self.temp_path}")
        else:
            export_meta_gui(
                self.bal_window.window, f"will_event.ics",self.save_to_cwd

            )


    def save_to_cwd(self,filename="event.ics"):
        target = os.path.abspath(filename)
        # se il file esiste, sovrascrive
        _logger.debug(f"save_to_cwd {self.temp_path},{filename}")
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



class WillWidget(QWidget):
    def __init__(self, father=None, parent=None):
        super().__init__()
        vlayout = QVBoxLayout()
        self.setLayout(vlayout)
        self.will = parent.bal_window.willitems
        self.parent = parent
        for w in self.will:
            if (
                self.will[w].get_status("REPLACED")
                and self.parent.bal_window.bal_plugin._hide_replaced
            ):
                continue
            if (
                self.will[w].get_status("INVALIDATED")
                and self.parent.bal_window.bal_plugin._hide_invalidated
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
                    partial(self.parent.bal_window.show_transaction, txid=w)
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
                            self.will[w].heirs[heir][3], self.parent.decimal_point
                        )
                        detaillayout.addWidget(
                            qlabel(
                                heir, f"{decoded_amount} {self.parent.base_unit_name}"
                            )
                        )
                if self.will[w].we:
                    detaillayout.addWidget(QLabel(""))
                    detaillayout.addWidget(QLabel(_("<b>Willexecutor:</b:")))
                    decoded_amount = Util.decode_amount(
                        self.will[w].we["base_fee"], self.parent.decimal_point
                    )

                    detaillayout.addWidget(
                        qlabel(
                            self.will[w].we["url"],
                            f"{decoded_amount} {self.parent.base_unit_name}",
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


