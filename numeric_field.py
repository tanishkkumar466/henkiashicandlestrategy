"""
numeric_field.py
-----------------
A QLineEdit-based drop-in replacement for QSpinBox/QDoubleSpinBox.

Why this exists: QSpinBox/QDoubleSpinBox's internal up/down-button
sub-controls have a confirmed rendering bug in this app - their internal
QLineEdit sub-control geometry can end up corrupted when many spinboxes
are styled and shown together (reproduced both on a real macOS build and
in automated testing), which visually garbles the displayed numbers.
Every attempted CSS/timing fix for the spinbox sub-control geometry was
tested and failed to resolve it reliably, so this sidesteps the problem
entirely by not using QAbstractSpinBox at all: NumericField wraps a
plain QLineEdit with a validator, which has none of that sub-control
machinery and renders reliably.

Provides the same interface trading_page.py needs from a spinbox:
value(), setValue(), setEnabled(), setStyleSheet(), plus optional
suffix/prefix text (e.g. " pips", "$ ") matching the old spinbox look.
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QLineEdit


class NumericField(QLineEdit):
    """A validated numeric text field behaving like a spinbox for our purposes."""

    valueChanged = Signal(float)

    def __init__(self, minimum=0.0, maximum=1_000_000.0, decimals=2,
                 suffix="", prefix="", is_int=False, parent=None):
        super().__init__(parent)
        self._decimals = 0 if is_int else decimals
        self._suffix = suffix
        self._prefix = prefix
        self._is_int = is_int
        self._min = minimum
        self._max = maximum

        if is_int:
            validator = QIntValidator(int(minimum), int(maximum), self)
        else:
            validator = QDoubleValidator(minimum, maximum, decimals, self)
            validator.setNotation(QDoubleValidator.StandardNotation)
        self.setValidator(validator)

        self.editingFinished.connect(self._on_editing_finished)
        self.setValue(minimum)

    def _format(self, value) -> str:
        if self._is_int:
            text = str(int(value))
        else:
            text = f"{value:.{self._decimals}f}"
        return f"{self._prefix}{text}{self._suffix}"

    def _parse(self, text: str) -> float:
        raw = text.strip()
        if self._prefix and raw.startswith(self._prefix):
            raw = raw[len(self._prefix):]
        if self._suffix and raw.endswith(self._suffix):
            raw = raw[: -len(self._suffix)]
        raw = raw.strip()
        try:
            return float(raw) if raw else self._min
        except ValueError:
            return self._min

    def _on_editing_finished(self):
        value = self._parse(self.text())
        value = max(self._min, min(self._max, value))
        self.setValue(value)

    def value(self):
        v = self._parse(self.text())
        return int(v) if self._is_int else v

    def setValue(self, value):
        value = max(self._min, min(self._max, value))
        self.setText(self._format(value))
        self.valueChanged.emit(float(value))

    def setRange(self, minimum, maximum):
        self._min, self._max = minimum, maximum
        if self._is_int:
            self.setValidator(QIntValidator(int(minimum), int(maximum), self))
        else:
            v = QDoubleValidator(minimum, maximum, self._decimals, self)
            v.setNotation(QDoubleValidator.StandardNotation)
            self.setValidator(v)

    def setSuffix(self, suffix: str):
        current = self.value()
        self._suffix = suffix
        self.setValue(current)

    def setPrefix(self, prefix: str):
        current = self.value()
        self._prefix = prefix
        self.setValue(current)

    def setSingleStep(self, step):
        pass  # kept for API compatibility with QDoubleSpinBox callers; no-op here

    def setDecimals(self, decimals: int):
        self._decimals = decimals
