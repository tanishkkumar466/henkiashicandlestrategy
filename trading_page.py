"""
trading_page.py
----------------
The Trading Bot dashboard page, liquid-glass styled:
  - Login card: MT5 login/password/server + optional terminal path
  - Settings card: symbol, magic number, timeframe, lot size
  - Risk Management card: master enable/disable switch, then concrete
    values (stop loss / take profit in pips, max daily loss in $,
    max drawdown in $, max open trades, trailing stop) - all fields
    grey out when the master switch is off, since a disabled risk
    manager ignores them entirely (see risk_manager.py)
  - Start/Stop controls
  - A terminal-style log box that prints everything the bot does
"""

from PySide6.QtCore import Qt, QDateTime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QTextEdit,
    QComboBox, QFileDialog, QMessageBox, QScrollArea, QTabWidget,
)
from PySide6.QtGui import QFont, QTextCursor

import config
import risk_manager as rm_module
from trading_worker import TradingWorker
from dashboard import DashboardPage
from numeric_field import NumericField


class TerminalLog(QTextEdit):
    """A read-only, monospace, glass-dark terminal-style log box."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setReadOnly(True)
        term_font = QFont("Consolas")
        term_font.setStyleHint(QFont.Monospace)
        term_font.setPointSize(9)
        self.setFont(term_font)
        self.setStyleSheet(theme.terminal_qss())
        theme.glass_changed.connect(lambda _i: self.setStyleSheet(theme.terminal_qss()))

    def append_line(self, text: str, level: str = "info"):
        colors = {
            "info": self.theme.TEXT_SECONDARY,
            "error": self.theme.DANGER,
            "risk": self.theme.WARNING,
            "trade": self.theme.SUCCESS,
            "success": self.theme.SUCCESS,
        }
        color = colors.get(level, self.theme.TEXT_SECONDARY)
        timestamp = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.append(f'<span style="color:{self.theme.TEXT_MUTED}">[{timestamp}]</span> '
                    f'<span style="color:{color}">{text}</span>')
        self.moveCursor(QTextCursor.End)


class TradingPage(DashboardPage):
    title = "Trading Bot"

    def build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(16)

        heading = QLabel(self.title)
        heading_font = QFont("Segoe UI", 18, QFont.Bold)
        heading_font.setStyleHint(QFont.SansSerif)
        heading.setFont(heading_font)
        heading.setStyleSheet(f"color: {self.theme.TEXT_PRIMARY}; background: transparent; border: none;")
        outer.addWidget(heading)

        self.worker = None
        self._cfg = config.load_config()

        # --- tabs: Login / Settings / Risk, each holding the exact same
        # card content and fields as before, just organized into tabs
        # instead of one long stacked/scrolling list.
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._wrap_scrollable(self._build_login_card()), "Login")
        self.tabs.addTab(self._wrap_scrollable(self._build_settings_card()), "Settings")
        self.tabs.addTab(self._wrap_scrollable(self._build_risk_card()), "Risk")
        outer.addWidget(self.tabs, stretch=1)

        outer.addLayout(self._build_controls_row())

        log_label = QLabel("Strategy Log")
        log_label.setStyleSheet(self.theme.label_title_qss())
        outer.addWidget(log_label)

        self.terminal = TerminalLog(self.theme)
        self.terminal.setMinimumHeight(200)
        self.terminal.setMaximumHeight(240)
        outer.addWidget(self.terminal)

        self.terminal.append_line(
            "Ready. Fill in your MT5 credentials and click Start.", "info")

        self._apply_input_theme()
        self._apply_tab_theme()
        self.theme.glass_changed.connect(lambda _i: self._apply_tab_theme())

    def _wrap_scrollable(self, panel: QWidget) -> QWidget:
        """Puts a card panel inside its own scroll area for its tab page,
        so tall content (e.g. the Risk tab with many fields) scrolls
        independently without affecting the other tabs or the window size."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 12, 0, 12)
        v.addWidget(panel)
        v.addStretch()
        scroll.setWidget(container)
        return scroll

    def _apply_tab_theme(self):
        bg = self.theme.panel_rgba(0.55)
        border = self.theme.border_rgba()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {border};
                border-radius: 12px;
                background: transparent;
                top: -1px;
            }}
            QTabBar::tab {{
                background: {bg};
                color: {self.theme.TEXT_SECONDARY};
                border: 1px solid {border};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 22px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {self.theme.ACCENT};
                color: white;
                border: 1px solid {self.theme.ACCENT};
            }}
            QTabBar::tab:hover:!selected {{
                color: {self.theme.TEXT_PRIMARY};
            }}
        """)

    # --------------------------------------------------------- shared helpers

    def _card(self, title_text: str):
        panel = self.make_glass_panel(radius=18)
        v = QVBoxLayout(panel)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        title = QLabel(title_text)
        title.setStyleSheet(self.theme.label_title_qss())
        v.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        return panel, grid

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {self.theme.TEXT_SECONDARY}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        return lbl

    def _apply_input_theme(self):
        # NumericField is a plain QLineEdit subclass (see numeric_field.py -
        # deliberately not QSpinBox/QDoubleSpinBox, whose internal
        # up/down-button sub-controls had a confirmed text-rendering bug),
        # so styling every QLineEdit here covers it automatically.
        qss = self.theme.input_qss()
        for cls in (QLineEdit, QComboBox):
            for w in self.findChildren(cls):
                w.setStyleSheet(qss)
        for w in self.findChildren(QCheckBox):
            w.setStyleSheet(self.theme.checkbox_qss())

    def on_theme_changed(self, intensity: int):
        self._apply_input_theme()
        self._restyle_buttons()

    def _restyle_buttons(self):
        self.start_btn.setStyleSheet(self.theme.button_primary_qss())
        self.stop_btn.setStyleSheet(self.theme.button_danger_qss())

    # ------------------------------------------------------------- login card

    def _build_login_card(self):
        panel, grid = self._card("MT5 Login")

        self.login_input = QLineEdit(str(self._cfg.get("mt5_login") or ""))
        self.login_input.setPlaceholderText("MT5 account number")

        self.password_input = QLineEdit(self._cfg.get("mt5_password", ""))
        self.password_input.setPlaceholderText("MT5 password")
        self.password_input.setEchoMode(QLineEdit.Password)

        self.server_input = QLineEdit(self._cfg.get("mt5_server", ""))
        self.server_input.setPlaceholderText("e.g. ICMarkets-Demo")

        self.path_input = QLineEdit(self._cfg.get("mt5_path", ""))
        self.path_input.setPlaceholderText("Optional: path to terminal64.exe")
        browse_btn = QPushButton("Browse...")
        browse_btn.setStyleSheet(self.theme.button_ghost_qss())
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_mt5_path)

        grid.addWidget(self._label("Login"), 0, 0)
        grid.addWidget(self.login_input, 0, 1, 1, 2)
        grid.addWidget(self._label("Password"), 1, 0)
        grid.addWidget(self.password_input, 1, 1, 1, 2)
        grid.addWidget(self._label("Server"), 2, 0)
        grid.addWidget(self.server_input, 2, 1, 1, 2)
        grid.addWidget(self._label("MT5 Path"), 3, 0)
        grid.addWidget(self.path_input, 3, 1)
        grid.addWidget(browse_btn, 3, 2)

        return panel

    def _browse_mt5_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select terminal64.exe", "", "MT5 Terminal (terminal64.exe);;All Files (*)")
        if path:
            self.path_input.setText(path)

    # ---------------------------------------------------------- settings card

    def _build_settings_card(self):
        panel, grid = self._card("Bot Settings")

        self.symbol_input = QLineEdit(self._cfg.get("symbol", "EURUSD"))

        self.timeframe_input = QComboBox()
        self.timeframe_input.addItems(rm_module.TIMEFRAMES)
        current_tf = self._cfg.get("timeframe", "M15")
        if current_tf in rm_module.TIMEFRAMES:
            self.timeframe_input.setCurrentText(current_tf)

        self.magic_input = NumericField(minimum=0, maximum=999_999_999, is_int=True)
        self.magic_input.setValue(int(self._cfg.get("magic_number", 123456)))

        self.use_fixed_lot_checkbox = QCheckBox("Use fixed lot size (uncheck to size by risk %)")
        self.use_fixed_lot_checkbox.setChecked(bool(self._cfg.get("use_fixed_lot", True)))
        self.use_fixed_lot_checkbox.toggled.connect(self._on_fixed_lot_toggled)

        self.lot_size_input = NumericField(minimum=0.01, maximum=100.0, decimals=2)
        self.lot_size_input.setValue(float(self._cfg.get("lot_size", 0.10)))

        self.risk_percent_input = NumericField(minimum=0.1, maximum=100.0, decimals=1, suffix=" %")
        self.risk_percent_input.setValue(float(self._cfg.get("risk_percent", 1.0)))

        grid.addWidget(self._label("Symbol"), 0, 0)
        grid.addWidget(self.symbol_input, 0, 1)
        grid.addWidget(self._label("Timeframe"), 1, 0)
        grid.addWidget(self.timeframe_input, 1, 1)
        grid.addWidget(self._label("Magic Number"), 2, 0)
        grid.addWidget(self.magic_input, 2, 1)
        grid.addWidget(self.use_fixed_lot_checkbox, 3, 0, 1, 2)
        grid.addWidget(self._label("Lot Size"), 4, 0)
        grid.addWidget(self.lot_size_input, 4, 1)
        grid.addWidget(self._label("Risk % (if not fixed)"), 5, 0)
        grid.addWidget(self.risk_percent_input, 5, 1)

        self._on_fixed_lot_toggled(self.use_fixed_lot_checkbox.isChecked())
        return panel

    def _on_fixed_lot_toggled(self, checked: bool):
        self.lot_size_input.setEnabled(checked)
        self.risk_percent_input.setEnabled(not checked)

    # -------------------------------------------------------------- risk card

    def _build_risk_card(self):
        panel, grid = self._card("Risk Management")

        self.risk_enabled_checkbox = QCheckBox(
            "Enable risk management (disable for unrestricted demo testing)")
        self.risk_enabled_checkbox.setChecked(bool(self._cfg.get("risk_management_enabled", True)))
        self.risk_enabled_checkbox.toggled.connect(self._on_risk_enabled_toggled)
        grid.addWidget(self.risk_enabled_checkbox, 0, 0, 1, 2)

        self.sl_pips_input = NumericField(minimum=1.0, maximum=2000.0, decimals=2, suffix=" pips")
        self.sl_pips_input.setValue(float(self._cfg.get("stop_loss_pips", 20.0)))

        self.tp_pips_input = NumericField(minimum=1.0, maximum=5000.0, decimals=2, suffix=" pips")
        self.tp_pips_input.setValue(float(self._cfg.get("take_profit_pips", 40.0)))

        self.max_daily_loss_input = NumericField(minimum=1.0, maximum=1_000_000.0, decimals=2, prefix="$ ")
        self.max_daily_loss_input.setValue(float(self._cfg.get("max_daily_loss_amount", 200.0)))

        self.max_drawdown_input = NumericField(minimum=1.0, maximum=1_000_000.0, decimals=2, prefix="$ ")
        self.max_drawdown_input.setValue(float(self._cfg.get("max_drawdown_amount", 500.0)))

        self.max_open_trades_input = NumericField(minimum=1, maximum=100, is_int=True)
        self.max_open_trades_input.setValue(int(self._cfg.get("max_open_trades", 3)))

        self.trailing_stop_checkbox = QCheckBox("Enable trailing stop")
        self.trailing_stop_checkbox.setChecked(bool(self._cfg.get("use_trailing_stop", False)))
        self.trailing_stop_checkbox.toggled.connect(self._on_trailing_toggled)

        self.trailing_pips_input = NumericField(minimum=1.0, maximum=500.0, decimals=2, suffix=" pips")
        self.trailing_pips_input.setValue(float(self._cfg.get("trailing_stop_pips", 20.0)))

        rows = [
            ("Stop loss", self.sl_pips_input),
            ("Take profit", self.tp_pips_input),
            ("Max daily loss", self.max_daily_loss_input),
            ("Max drawdown lock", self.max_drawdown_input),
            ("Max open trades", self.max_open_trades_input),
        ]
        self._risk_field_rows = []
        r = 1
        for label_text, widget in rows:
            lbl = self._label(label_text)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(widget, r, 1)
            self._risk_field_rows.append((lbl, widget))
            r += 1

        grid.addWidget(self.trailing_stop_checkbox, r, 0, 1, 2)
        r += 1
        trailing_lbl = self._label("Trailing stop distance")
        grid.addWidget(trailing_lbl, r, 0)
        grid.addWidget(self.trailing_pips_input, r, 1)
        self._risk_field_rows.append((trailing_lbl, self.trailing_pips_input))

        self._on_risk_enabled_toggled(self.risk_enabled_checkbox.isChecked())
        self._on_trailing_toggled(self.trailing_stop_checkbox.isChecked())
        return panel

    def _on_risk_enabled_toggled(self, checked: bool):
        for lbl, widget in self._risk_field_rows:
            widget.setEnabled(checked)
            lbl.setEnabled(checked)
        self.trailing_stop_checkbox.setEnabled(checked)
        if checked:
            self._on_trailing_toggled(self.trailing_stop_checkbox.isChecked())

    def _on_trailing_toggled(self, checked: bool):
        self.trailing_pips_input.setEnabled(checked and self.risk_enabled_checkbox.isChecked())

    # ---------------------------------------------------------- controls row

    def _build_controls_row(self):
        row = QHBoxLayout()

        self.status_label = QLabel("● Disconnected")
        self.status_label.setStyleSheet(f"color: {self.theme.DANGER}; font-weight: 600;")
        row.addWidget(self.status_label)
        row.addStretch()

        self.start_btn = QPushButton("Start Bot")
        self.start_btn.setStyleSheet(self.theme.button_primary_qss())
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start_clicked)
        row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Bot")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self.theme.button_danger_qss())
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        row.addWidget(self.stop_btn)

        return row

    # ----------------------------------------------------------- start/stop

    def _collect_config(self) -> dict:
        return {
            "mt5_login": self.login_input.text().strip(),
            "mt5_password": self.password_input.text(),
            "mt5_server": self.server_input.text().strip(),
            "mt5_path": self.path_input.text().strip(),

            "symbol": self.symbol_input.text().strip().upper(),
            "timeframe": self.timeframe_input.currentText(),
            "magic_number": self.magic_input.value(),

            "use_fixed_lot": self.use_fixed_lot_checkbox.isChecked(),
            "lot_size": self.lot_size_input.value(),
            "risk_percent": self.risk_percent_input.value(),

            "risk_management_enabled": self.risk_enabled_checkbox.isChecked(),
            "stop_loss_pips": self.sl_pips_input.value(),
            "take_profit_pips": self.tp_pips_input.value(),
            "max_daily_loss_amount": self.max_daily_loss_input.value(),
            "max_drawdown_amount": self.max_drawdown_input.value(),
            "max_open_trades": self.max_open_trades_input.value(),
            "use_trailing_stop": self.trailing_stop_checkbox.isChecked(),
            "trailing_stop_pips": self.trailing_pips_input.value(),

            "glass_intensity": self.theme.intensity,
        }

    def _on_start_clicked(self):
        cfg = self._collect_config()

        if not cfg["mt5_login"] or not cfg["mt5_password"] or not cfg["mt5_server"]:
            QMessageBox.warning(self, "Missing info",
                                 "Login, password, and server are required.")
            return
        try:
            login_int = int(cfg["mt5_login"])
        except ValueError:
            QMessageBox.warning(self, "Invalid login", "MT5 login must be a number.")
            return

        config.save_config(cfg)

        risk_settings = rm_module.RiskSettings(
            enabled=cfg["risk_management_enabled"],
            timeframe=cfg["timeframe"],
            fixed_lot=cfg["lot_size"] if cfg["use_fixed_lot"] else None,
            risk_percent=None if cfg["use_fixed_lot"] else cfg["risk_percent"],
            stop_loss_pips=cfg["stop_loss_pips"],
            take_profit_pips=cfg["take_profit_pips"],
            max_daily_loss_amount=cfg["max_daily_loss_amount"],
            max_drawdown_amount=cfg["max_drawdown_amount"],
            max_open_trades=cfg["max_open_trades"],
            use_trailing_stop=cfg["use_trailing_stop"],
            trailing_stop_pips=cfg["trailing_stop_pips"],
        )

        self.worker = TradingWorker(
            login=login_int, password=cfg["mt5_password"], server=cfg["mt5_server"],
            path=cfg["mt5_path"], symbol=cfg["symbol"], magic=cfg["magic_number"],
            risk_settings=risk_settings,
        )
        self.worker.log_line.connect(self._on_log_line)
        self.worker.connected.connect(self._on_connected)
        self.worker.connection_failed.connect(self._on_connection_failed)
        self.worker.stopped.connect(self._on_stopped)
        self.worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("● Connecting...")
        self.status_label.setStyleSheet(f"color: {self.theme.WARNING}; font-weight: 600;")

    def _on_stop_clicked(self):
        if self.worker:
            self.terminal.append_line("Stopping bot...", "info")
            self.worker.stop()
        self.stop_btn.setEnabled(False)

    def _on_log_line(self, text: str):
        level = "info"
        if text.startswith("[ERROR]"):
            level = "error"
        elif text.startswith("[RISK]"):
            level = "risk"
        elif text.startswith("[TRADE]"):
            level = "trade"
        self.terminal.append_line(text, level)

    def _on_connected(self, account: dict):
        self.status_label.setText(f"● Connected — {account.get('login')}")
        self.status_label.setStyleSheet(f"color: {self.theme.SUCCESS}; font-weight: 600;")

    def _on_connection_failed(self, message: str):
        self.status_label.setText("● Connection failed")
        self.status_label.setStyleSheet(f"color: {self.theme.DANGER}; font-weight: 600;")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.critical(self, "MT5 Connection Failed", message)

    def _on_stopped(self):
        self.status_label.setText("● Disconnected")
        self.status_label.setStyleSheet(f"color: {self.theme.DANGER}; font-weight: 600;")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
