"""
broker.py
---------
Thin wrapper around the MetaTrader5 Python package.

The `MetaTrader5` package only works on Windows (it talks to the
locally installed MT5 terminal via DLL), so this module imports it
defensively — the rest of the app (UI, risk manager, config) will
still run and can be tested on any OS. On a Windows machine with MT5
installed, `pip install MetaTrader5` and everything below becomes live.
"""

import logging
from dataclasses import dataclass
from typing import Optional

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

log = logging.getLogger("broker")


class BrokerError(Exception):
    pass


@dataclass
class AccountInfo:
    login: int
    balance: float
    equity: float
    margin: float
    margin_free: float
    profit: float
    currency: str
    leverage: int
    server: str


@dataclass
class Position:
    ticket: int
    symbol: str
    type: str          # "buy" or "sell"
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    magic: int
    comment: str


class MT5Broker:
    """
    Wraps the MetaTrader5 package. Call connect() before anything else.
    All methods raise BrokerError with a readable message on failure,
    rather than letting raw mt5 error tuples leak into the UI layer.
    """

    def __init__(self):
        self.connected = False
        self._login: Optional[int] = None
        self.autotrading_enabled = True  # set accurately in connect(); assume True until known otherwise

    # ------------------------------------------------------------ connect

    def connect(self, login: int, password: str, server: str,
                path: str = "") -> AccountInfo:
        """
        Initializes the MT5 terminal connection and logs into the account.
        `path` is the full path to terminal64.exe, only needed if MT5
        isn't in the default install location or you run multiple terminals.
        """
        if not MT5_AVAILABLE:
            raise BrokerError(
                "MetaTrader5 package not available. This only runs on "
                "Windows with the MetaTrader5 package installed "
                "(pip install MetaTrader5) and the MT5 terminal installed."
            )

        init_kwargs = {}
        if path:
            init_kwargs["path"] = path

        ok = mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()
        if not ok:
            code, desc = mt5.last_error()
            raise BrokerError(f"MT5 initialize() failed: [{code}] {desc}")

        authorized = mt5.login(login, password=password, server=server)
        if not authorized:
            code, desc = mt5.last_error()
            mt5.shutdown()
            raise BrokerError(f"MT5 login failed: [{code}] {desc}")

        self.connected = True
        self._login = login
        log.info("Connected to MT5 account %s on %s", login, server)

        term_info = mt5.terminal_info()
        self.autotrading_enabled = bool(getattr(term_info, "trade_allowed", True)) if term_info else True
        if not self.autotrading_enabled:
            log.warning(
                "Connected, but AutoTrading is disabled in the MT5 terminal. "
                "Orders will be rejected until you click the 'Algo Trading' "
                "button in the terminal toolbar."
            )

        return self.get_account_info()

    def disconnect(self):
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
        self.connected = False
        log.info("Disconnected from MT5")

    def _require_connected(self):
        if not self.connected:
            raise BrokerError("Not connected to MT5. Call connect() first.")

    # -------------------------------------------------------------- account

    def get_account_info(self) -> AccountInfo:
        self._require_connected()
        info = mt5.account_info()
        if info is None:
            code, desc = mt5.last_error()
            raise BrokerError(f"account_info() failed: [{code}] {desc}")
        return AccountInfo(
            login=info.login, balance=info.balance, equity=info.equity,
            margin=info.margin, margin_free=info.margin_free,
            profit=info.profit, currency=info.currency,
            leverage=info.leverage, server=info.server,
        )

    # -------------------------------------------------------------- market

    def get_symbol_price(self, symbol: str):
        self._require_connected()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"No tick data for symbol '{symbol}'. Is it in Market Watch?")
        return {"bid": tick.bid, "ask": tick.ask, "time": tick.time}

    def get_symbol_info(self, symbol: str):
        self._require_connected()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise BrokerError(f"Symbol '{symbol}' not found.")
        return info

    def pip_size(self, symbol: str) -> float:
        """
        Returns the value of 1 pip in price terms for this symbol.

        NOT the same as symbol_info().point. Most brokers today quote
        with an extra fractional digit (5-digit brokers for majors like
        EURUSD at 1.09523, 3-digit for JPY pairs), where point is 1/10th
        of a real pip. Using point directly instead of pip would make
        every stop-loss/take-profit distance 10x too tight - a serious,
        silent risk-sizing error, not just a display quirk. The standard
        convention (matches every broker/EA reference for this): if
        digits is odd, 1 pip = 10 * point; if even, 1 pip = point.
        """
        info = self.get_symbol_info(symbol)
        point = info.point
        digits = info.digits
        return point * 10 if digits % 2 == 1 else point

    def pips_to_price_offset(self, symbol: str, pips: float) -> float:
        """Converts a distance in pips to a price offset for this symbol."""
        return pips * self.pip_size(symbol)

    def get_candles(self, symbol: str, timeframe: str = "M15", count: int = 200):
        """
        timeframe: one of M1, M5, M15, M30, H1, H4, D1, W1, MN1
        Returns a list of dicts: time, open, high, low, close, tick_volume

        Note: `time` is returned exactly as MT5 provides it - Unix epoch
        seconds in UTC (not local time). MT5 always stores bar/tick times
        in UTC regardless of the terminal's display timezone, so convert
        explicitly in logic.py if you need local time:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(candle["time"], tz=timezone.utc)
        """
        self._require_connected()
        tf_map = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        if timeframe not in tf_map:
            raise BrokerError(f"Unknown timeframe '{timeframe}'")

        rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, count)
        if rates is None:
            code, desc = mt5.last_error()
            raise BrokerError(f"copy_rates_from_pos failed: [{code}] {desc}")

        return [
            {"time": r["time"], "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "tick_volume": r["tick_volume"]}
            for r in rates
        ]

    # -------------------------------------------------------------- orders

    def _resolve_filling_mode(self, symbol: str):
        """
        Picks a filling mode the symbol/broker actually supports, instead
        of hardcoding one. Sending an unsupported type_filling is one of
        the most common real-world MT5 order failures (retcode 10030,
        "Unsupported filling mode") - brokers vary in which of FOK / IOC
        / RETURN they allow per symbol, so this must be checked live
        rather than assumed.
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_IOC  # fallback; place_order() will
            # have already raised if the symbol truly doesn't exist

        filling_mode = getattr(info, "filling_mode", 0)
        # filling_mode is a bitmask of SYMBOL_FILLING_FOK (1) / SYMBOL_FILLING_IOC (2)
        if filling_mode & 1:  # SYMBOL_FILLING_FOK
            return mt5.ORDER_FILLING_FOK
        if filling_mode & 2:  # SYMBOL_FILLING_IOC
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def place_order(self, symbol: str, action: str, lot: float,
                     sl: float = 0.0, tp: float = 0.0,
                     magic: int = 0, comment: str = "",
                     deviation: int = 20) -> dict:
        """
        action: "buy" or "sell"
        deviation: max acceptable slippage in points. Without this,
        brokers commonly reject orders with a "Requote" error
        (retcode 10004) if the price moves even slightly between reading
        the tick and the order arriving - 20 points is a reasonable
        default for most forex majors, tighten/widen per symbol as needed.
        Returns the order result as a dict. Raises BrokerError on failure.
        """
        self._require_connected()
        action = action.lower()
        if action not in ("buy", "sell"):
            raise BrokerError(f"Invalid action '{action}', must be 'buy' or 'sell'")

        info = self.get_symbol_info(symbol)
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                raise BrokerError(f"Could not select symbol '{symbol}' in Market Watch")

        lot = self._normalize_volume(symbol, lot)

        price_data = self.get_symbol_price(symbol)
        order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
        price = price_data["ask"] if action == "buy" else price_data["bid"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_mode(symbol),
        }

        result = mt5.order_send(request)
        if result is None:
            code, desc = mt5.last_error()
            raise BrokerError(f"order_send() returned None: [{code}] {desc}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerError(f"Order failed, retcode={result.retcode}: {result.comment}")

        log.info("Order placed: %s %s %.2f lots @ %.5f", action, symbol, lot, price)
        return {
            "ticket": result.order, "price": result.price,
            "volume": result.volume, "retcode": result.retcode,
        }

    def _normalize_volume(self, symbol: str, lot: float) -> float:
        """
        Rounds `lot` down to the nearest valid volume_step for this
        symbol and clamps to [volume_min, volume_max]. Blindly rounding
        to 2 decimal places (the previous behavior) can produce a volume
        that isn't a clean multiple of the broker's actual step - a
        well-documented cause of TRADE_RETCODE_INVALID_VOLUME (10014).
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return round(lot, 2)  # symbol lookup already validated earlier in place_order()

        step = getattr(info, "volume_step", 0.01) or 0.01
        vol_min = getattr(info, "volume_min", 0.01) or 0.01
        vol_max = getattr(info, "volume_max", 100.0) or 100.0

        import math
        steps = math.floor(lot / step + 1e-9)  # small epsilon guards float rounding
        normalized = steps * step
        normalized = max(vol_min, min(vol_max, normalized))
        # Round to avoid float noise like 0.30000000000000004
        decimals = max(0, len(str(step).split(".")[-1])) if "." in str(step) else 0
        return round(normalized, decimals)

    def close_position(self, ticket: int, deviation: int = 20) -> dict:
        self._require_connected()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise BrokerError(f"No open position with ticket {ticket}")
        pos = positions[0]

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price_data = self.get_symbol_price(pos.symbol)
        price = price_data["bid"] if close_type == mt5.ORDER_TYPE_SELL else price_data["ask"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": deviation,
            "magic": pos.magic,
            "comment": "close by bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._resolve_filling_mode(pos.symbol),
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code, desc = (mt5.last_error() if result is None else (result.retcode, result.comment))
            raise BrokerError(f"close_position() failed: [{code}] {desc}")

        log.info("Closed position %s", ticket)
        return {"ticket": ticket, "retcode": result.retcode}

    def get_open_positions(self, magic: Optional[int] = None) -> list:
        self._require_connected()
        positions = mt5.positions_get()
        if positions is None:
            return []
        result = []
        for p in positions:
            if magic is not None and p.magic != magic:
                continue
            result.append(Position(
                ticket=p.ticket, symbol=p.symbol,
                type="buy" if p.type == mt5.ORDER_TYPE_BUY else "sell",
                volume=p.volume, price_open=p.price_open,
                price_current=p.price_current, sl=p.sl, tp=p.tp,
                profit=p.profit, magic=p.magic, comment=p.comment,
            ))
        return result
