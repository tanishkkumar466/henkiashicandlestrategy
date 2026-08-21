"""
trading_worker.py
------------------
QThread that runs the bot loop: connects to MT5, then repeatedly
calls into logic.py for a signal, checks risk_manager before acting,
and executes via broker.py. Emits log lines and status updates as
Signals so trading_page.py can display them in the terminal box
without touching threads directly.
"""

import time
import traceback

from PySide6.QtCore import QThread, Signal

import broker
import risk_manager as rm_module

try:
    import logic
except ImportError:
    logic = None


class TradingWorker(QThread):
    log_line = Signal(str)            # a line to print in the terminal
    connected = Signal(dict)          # emits account info dict on successful connect
    connection_failed = Signal(str)
    stopped = Signal()
    account_update = Signal(dict)     # periodic balance/equity refresh for the UI

    def __init__(self, login: int, password: str, server: str, path: str,
                 symbol: str, magic: int, risk_settings: "rm_module.RiskSettings",
                 poll_seconds: float = 2.0, parent=None):
        super().__init__(parent)
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.symbol = symbol
        self.magic = magic
        self.risk_settings = risk_settings
        self.poll_seconds = poll_seconds

        self._running = False
        self.broker = broker.MT5Broker()
        self.risk_manager = rm_module.RiskManager(risk_settings)
        # Seeded with symbol/magic so logic.py's generate_signal(broker,
        # risk_manager, state) can read state["symbol"] / state["magic"]
        # without needing its own copy of the running bot's settings.
        self._strategy_state = {"symbol": symbol, "magic": magic}

    def stop(self):
        """Signal the loop to exit at its next iteration."""
        self._running = False

    def run(self):
        self.log_line.emit(f"Connecting to MT5 (login={self.login}, server={self.server})...")
        try:
            account = self.broker.connect(self.login, self.password, self.server, self.path)
        except broker.BrokerError as e:
            self.log_line.emit(f"[ERROR] Connection failed: {e}")
            self.connection_failed.emit(str(e))
            return

        self.log_line.emit(
            f"Connected. Balance: {account.balance:.2f} {account.currency}  "
            f"Equity: {account.equity:.2f}  Leverage: 1:{account.leverage}"
        )
        self.connected.emit(account.__dict__)

        if not self.broker.autotrading_enabled:
            self.log_line.emit(
                "[RISK] AutoTrading is OFF in the MT5 terminal. Orders will "
                "be rejected until you click the 'Algo Trading' button in "
                "the terminal toolbar (top toolbar, or Tools > Options > "
                "Expert Advisors)."
            )

        self._running = True
        rm_status = "ENABLED" if self.risk_settings.enabled else "DISABLED (unrestricted trading)"
        self.log_line.emit(
            f"Bot started on {self.symbol} ({self.risk_settings.timeframe}), "
            f"magic={self.magic}. Risk management: {rm_status}. Watching for signals..."
        )

        while self._running:
            try:
                self._tick()
            except Exception as e:  # noqa: BLE001 - keep the loop alive, just log it
                self.log_line.emit(f"[ERROR] {e}")
                self.log_line.emit(traceback.format_exc(limit=2))

            for _ in range(int(self.poll_seconds * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

        self.broker.disconnect()
        self.log_line.emit("Bot stopped. Disconnected from MT5.")
        self.stopped.emit()

    def _tick(self):
        account = self.broker.get_account_info()
        self.risk_manager.update_account_snapshot(account.balance, account.equity)
        self.account_update.emit(account.__dict__)

        open_positions = self.broker.get_open_positions(magic=self.magic)
        allowed, reason = self.risk_manager.can_trade(len(open_positions))
        if not allowed:
            self.log_line.emit(f"[RISK] Trading blocked: {reason}")
            return

        # logic.py is empty by default — generate_signal() won't exist
        # until the user implements it. Handle that gracefully, whether
        # the file is missing entirely or just doesn't have the function yet.
        generate_signal = getattr(logic, "generate_signal", None) if logic else None
        if generate_signal is None:
            self.log_line.emit(
                "[INFO] No logic.py / generate_signal() found — "
                "nothing to do. Add a logic.py with a generate_signal() "
                "function to run your strategy."
            )
            return

        signal = generate_signal(self.broker, self.risk_manager, self._strategy_state)
        if not signal:
            return

        self._execute_signal(signal, account.balance)

    def _execute_signal(self, signal: dict, balance: float):
        action = signal.get("action")
        symbol = signal.get("symbol", self.symbol)

        if action == "close":
            ticket = signal.get("ticket")
            if ticket is None:
                self.log_line.emit("[ERROR] close signal missing 'ticket'")
                return
            result = self.broker.close_position(ticket)
            self.log_line.emit(f"Closed position {ticket}: {result}")
            return

        if action not in ("buy", "sell"):
            self.log_line.emit(f"[ERROR] Unknown signal action '{action}'")
            return

        sl_pips = signal.get("stop_loss_pips", self.risk_settings.stop_loss_pips)
        tp_pips = signal.get("take_profit_pips", self.risk_settings.take_profit_pips)

        lot = signal.get("lot")
        if lot is None:
            lot = self.risk_manager.calculate_lot_size(balance, sl_pips)

        # A signal can give an explicit price ("stop_loss"/"take_profit")
        # or a pip distance ("stop_loss_pips"/"take_profit_pips") to be
        # converted relative to the current price - explicit price wins
        # if both are present. Without this conversion, pip-based signals
        # would silently be sent with sl=0.0/tp=0.0 (no protection at
        # all), since MT5's order_send() only accepts absolute prices,
        # never pip distances.
        sl_price = signal.get("stop_loss")
        tp_price = signal.get("take_profit")

        if sl_price is None or tp_price is None:
            price_data = self.broker.get_symbol_price(symbol)
            entry_price = price_data["ask"] if action == "buy" else price_data["bid"]
            sl_offset = self.broker.pips_to_price_offset(symbol, sl_pips) if sl_pips else 0.0
            tp_offset = self.broker.pips_to_price_offset(symbol, tp_pips) if tp_pips else 0.0

            if sl_price is None:
                if sl_offset:
                    sl_price = entry_price - sl_offset if action == "buy" else entry_price + sl_offset
                else:
                    sl_price = 0.0
            if tp_price is None:
                if tp_offset:
                    tp_price = entry_price + tp_offset if action == "buy" else entry_price - tp_offset
                else:
                    tp_price = 0.0

        result = self.broker.place_order(
            symbol=symbol, action=action, lot=lot,
            sl=sl_price, tp=tp_price,
            magic=self.magic, comment=signal.get("comment", "auto"),
        )
        self.log_line.emit(
            f"[TRADE] {action.upper()} {symbol} {lot} lots -> ticket {result['ticket']} "
            f"@ {result['price']}  SL={sl_price:.5f} TP={tp_price:.5f}"
        )
