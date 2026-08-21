"""
risk_manager.py
----------------
Position sizing and trading-permission logic, independent of MT5 so
it's testable on its own.

v2 changes:
  - `enabled` flag: when False, can_trade() always allows and
    calculate_lot_size() just returns the fixed lot untouched. Lets you
    run raw on a demo account with zero risk interference while testing.
  - Real concrete values instead of pure percentages: stop loss / take
    profit in pips, max daily loss in account currency ($), max
    drawdown in account currency ($) - these map directly to what you'd
    type into MT5 itself, rather than abstract percentages.
  - Timeframe is now a first-class setting (used by logic.py to know
    which candles to pull), one of: M1, M5, M15, M30, H1, H4, D1.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


@dataclass
class RiskSettings:
    enabled: bool = True                    # master on/off switch for all risk checks

    timeframe: str = "M15"                  # candle timeframe logic.py should trade on

    fixed_lot: Optional[float] = 0.10       # if set, overrides risk-based sizing
    risk_percent: Optional[float] = None    # if set (and fixed_lot is None), size by % risk

    stop_loss_pips: float = 20.0
    take_profit_pips: float = 40.0

    max_daily_loss_amount: float = 200.0    # in account currency, e.g. $200
    max_drawdown_amount: float = 500.0      # in account currency, e.g. $500
    max_open_trades: int = 3

    use_trailing_stop: bool = False
    trailing_stop_pips: float = 20.0


@dataclass
class _DailyState:
    day: date = field(default_factory=date.today)
    start_balance: float = 0.0
    realized_pnl: float = 0.0


class RiskManager:
    def __init__(self, settings: RiskSettings):
        self.settings = settings
        self._peak_equity: Optional[float] = None
        self._last_equity: Optional[float] = None
        self._daily = _DailyState()
        self._drawdown_locked = False
        self._lock_reason = ""

    # ------------------------------------------------------------- update

    def update_account_snapshot(self, balance: float, equity: float):
        """
        Call this regularly (e.g. every tick) with fresh account figures.

        Tracks today's loss as (start_of_day_balance - current_equity),
        which reflects both realized and floating P&L - the same way
        MT5 itself typically reports daily loss. This means the daily
        loss check works automatically from account snapshots alone;
        record_realized_pnl() is an optional extra for strategies that
        want to track realized-only P&L on top of this.
        """
        today = date.today()
        if self._daily.day != today:
            self._daily = _DailyState(day=today, start_balance=balance, realized_pnl=0.0)
        elif self._daily.start_balance == 0.0:
            self._daily.start_balance = balance

        self._last_equity = equity

        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

        if not self.settings.enabled:
            return

        if self._peak_equity:
            drawdown_amount = self._peak_equity - equity
            if drawdown_amount >= self.settings.max_drawdown_amount and not self._drawdown_locked:
                self._drawdown_locked = True
                self._lock_reason = (
                    f"Max drawdown reached: ${drawdown_amount:.2f} "
                    f"(limit ${self.settings.max_drawdown_amount:.2f})"
                )

    def record_realized_pnl(self, amount: float):
        """
        Optional: call this when a trade closes to additionally track
        realized-only P&L (available via status_summary()). Not required
        for the max daily loss check itself - that's driven by
        update_account_snapshot()'s equity-vs-start-of-day comparison,
        so it works correctly even if this is never called.
        """
        self._daily.realized_pnl += amount

    # ------------------------------------------------------------- checks

    def can_trade(self, current_open_trades: int) -> tuple[bool, str]:
        """
        Returns (allowed, reason). reason is empty if allowed=True,
        otherwise explains why trading is currently blocked.

        When settings.enabled is False, this always returns (True, "")
        so the bot trades unrestricted - useful for demo testing.
        """
        if not self.settings.enabled:
            return True, ""

        if self._drawdown_locked:
            return False, self._lock_reason

        if current_open_trades >= self.settings.max_open_trades:
            return False, (
                f"Max open trades reached ({current_open_trades}/"
                f"{self.settings.max_open_trades})"
            )

        daily_loss = self._daily.start_balance - self._last_equity if self._last_equity is not None else 0.0
        if daily_loss >= self.settings.max_daily_loss_amount:
            return False, (
                f"Max daily loss reached: ${daily_loss:.2f} "
                f"(limit ${self.settings.max_daily_loss_amount:.2f})"
            )

        return True, ""

    def reset_drawdown_lock(self):
        """Manual override to resume trading after a drawdown lock (use with care)."""
        self._drawdown_locked = False
        self._lock_reason = ""
        self._peak_equity = None

    # ------------------------------------------------------------- sizing

    def calculate_lot_size(self, balance: float, stop_loss_pips: Optional[float] = None,
                            pip_value_per_lot: float = 10.0) -> float:
        """
        If risk management is disabled, or a fixed lot is set, just
        returns that fixed lot untouched. Otherwise sizes by risk_percent:

            lot = (balance * risk%) / (stop_loss_pips * pip_value_per_lot)
        """
        if not self.settings.enabled or self.settings.risk_percent is None:
            return round(self.settings.fixed_lot or 0.01, 2)

        sl_pips = stop_loss_pips or self.settings.stop_loss_pips
        if sl_pips <= 0:
            raise ValueError("stop_loss_pips must be > 0 to size a position by risk")

        risk_amount = balance * (self.settings.risk_percent / 100)
        raw_lot = risk_amount / (sl_pips * pip_value_per_lot)
        return max(0.01, round(raw_lot, 2))

    # ------------------------------------------------------------- status

    def status_summary(self) -> dict:
        daily_loss = None
        if self._last_equity is not None:
            daily_loss = round(self._daily.start_balance - self._last_equity, 2)
        return {
            "enabled": self.settings.enabled,
            "drawdown_locked": self._drawdown_locked,
            "lock_reason": self._lock_reason,
            "daily_realized_pnl": round(self._daily.realized_pnl, 2),
            "daily_loss_from_equity": daily_loss,
            "peak_equity": self._peak_equity,
        }
