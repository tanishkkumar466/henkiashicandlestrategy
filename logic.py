"""
logic.py
--------
"Algo advance" strategy, converted from Pine Script v6.

Original Pine logic:
    - Builds Heikin Ashi candles on a fixed 60-minute timeframe
      (independent of the chart's own timeframe), via request.security()
    - ha_dif2 = HA_open - HA_close
        > 0  -> ha_diff2 = 1 -> RED candle   -> shortCondition -> short signal
        < 0  -> ha_diff2 = 2 -> GREEN candle -> longCondition  -> long signal
      (traced exactly from the Pine script's ternary chain - easy to get
      backwards since "green/bullish" doesn't intuitively map to
      ha_open < ha_close at a glance, so this was double-checked line by
      line against the original ha_diff2 / longCondition / shortCondition
      definitions rather than assumed)
    - On a long signal: close any open Short, then open a Long
    - On a short signal: close any open Long, then open a Short
    - No explicit SL/TP in the Pine script itself - risk is meant to be
      handled externally (that's exactly what this app's Risk Management
      tab does: stop_loss_pips / take_profit_pips get applied when the
      order is placed, see the return value below)

Porting notes (things that don't map 1:1 and needed a judgment call):
    - The original used lookahead = barmerge.lookahead_on, which Pine
      itself flags as unsafe/repainting (it can peek at an HTF candle
      before it has actually closed). That's fine in a backtest but
      wrong for a live bot - it would mean acting on a signal that can
      still change. This port ONLY ever reads fully closed HTF candles,
      which is the correct, non-repainting way to run this live. This
      is a deliberate improvement, not a bug.
    - Heikin Ashi is recursive (each HA candle depends on the previous
      HA candle), so this pulls a run of recent candles on the selected
      timeframe and computes the HA series across all of them, not just
      the last one - using only the single latest candle would seed the
      recursion incorrectly and give a wrong HA_open.
    - The original hardcoded res2 = "60" (H1), independent of the
      chart's own timeframe. This port instead uses whatever timeframe
      is selected in the app's Bot Settings tab (risk_manager.settings.
      timeframe) - set it there, no code edit needed. Pick whichever
      timeframe you want the Heikin Ashi candles built from.
    - "Close previous before new entry" is implemented as: on a flip,
      close every open position for this symbol+magic in the opposite
      direction, then return a fresh entry signal. trading_worker.py
      places one order per generate_signal() call, so a flip takes two
      ticks to fully execute (close on this tick, open on the next) -
      see _manage_flip() below for exactly how that's sequenced.
"""

HA_LOOKBACK_CANDLES = 50      # how many candles to pull to seed the HA recursion


def _compute_heikin_ashi_series(candles: list) -> list:
    """
    candles: list of dicts from broker.get_candles(), oldest first, each
    with open/high/low/close (as returned by broker.py).

    Returns a list of dicts [{"ha_open":.., "ha_close":.., "ha_high":..,
    "ha_low":..}, ...] in the same order, one per input candle.

    Standard Heikin Ashi formula:
        HA_close = (open + high + low + close) / 4
        HA_open  = (previous HA_open + previous HA_close) / 2
                   (first candle seeds with (open + close) / 2)
        HA_high  = max(high, HA_open, HA_close)
        HA_low   = min(low, HA_open, HA_close)
    """
    ha_series = []
    prev_ha_open = None
    prev_ha_close = None

    for c in candles:
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
        ha_close = (o + h + l + cl) / 4.0

        if prev_ha_open is None:
            ha_open = (o + cl) / 2.0
        else:
            ha_open = (prev_ha_open + prev_ha_close) / 2.0

        ha_high = max(h, ha_open, ha_close)
        ha_low = min(l, ha_open, ha_close)

        ha_series.append({
            "ha_open": ha_open, "ha_close": ha_close,
            "ha_high": ha_high, "ha_low": ha_low,
        })
        prev_ha_open, prev_ha_close = ha_open, ha_close

    return ha_series


def _latest_closed_ha_direction(broker, symbol: str, timeframe: str) -> str:
    """
    Returns "green" (ha_open < ha_close, i.e. ha_dif2 < 0 -> ha_diff2==2
    in the Pine script -> longCondition) or "red" (ha_open > ha_close,
    ha_dif2 > 0 -> ha_diff2==1 -> shortCondition) for the most recently
    CLOSED Heikin Ashi candle on the given timeframe, or "flat" if
    they're exactly equal (Pine's ha_diff2==3 -> na, no signal).

    timeframe: whatever's selected in the Bot Settings tab's Timeframe
    dropdown (M1/M5/M15/M30/H1/H4/D1) - this is your control, matching
    the Pine script's res2 which you could likewise change. The original
    script had this hardcoded to "60" (H1); this port makes it whatever
    you pick in the UI instead.

    broker.get_candles() with count=N returns the N most recent candles
    including the still-forming current one as the last element, so we
    drop that last element to only ever act on fully closed candles
    (see the "Porting notes" docstring above on lookahead_on).
    """
    candles = broker.get_candles(symbol, timeframe=timeframe, count=HA_LOOKBACK_CANDLES)
    if len(candles) < 3:
        return "flat"  # not enough data yet to compute a meaningful HA series

    closed_candles = candles[:-1]  # drop the still-forming current candle
    ha_series = _compute_heikin_ashi_series(closed_candles)
    latest = ha_series[-1]

    ha_dif2 = latest["ha_open"] - latest["ha_close"]
    if ha_dif2 < 0:
        return "green"
    elif ha_dif2 > 0:
        return "red"
    return "flat"


def _open_positions_by_side(broker, risk_manager, symbol: str, magic: int):
    """Splits this symbol+magic's open positions into (longs, shorts) lists."""
    positions = broker.get_open_positions(magic=magic)
    longs = [p for p in positions if p.symbol == symbol and p.type == "buy"]
    shorts = [p for p in positions if p.symbol == symbol and p.type == "sell"]
    return longs, shorts


def _manage_flip(broker, risk_manager, state: dict, symbol: str, magic: int,
                  direction: str) -> dict | None:
    """
    Mirrors the Pine script's "strategy.close() then strategy.entry()"
    for one direction. Since trading_worker.py sends one order per
    generate_signal() call, a flip is handled over up to two ticks:
      tick 1: if the opposite side is open, close it and return (no
               entry yet - closing and opening in the same tick would
               send two orders from one signal dict, which the worker
               doesn't support)
      tick 2: once the opposite side is confirmed flat, open the new
               position

    state["last_ha_direction"] tracks the last direction we've already
    acted on, so we only do this once per genuine flip - not on every
    tick while already positioned correctly, matching Pine's
    bar-close-triggered behavior instead of re-firing continuously.
    """
    longs, shorts = _open_positions_by_side(broker, risk_manager, symbol, magic)

    if direction == "green":  # long signal
        if shorts:
            return {"action": "close", "ticket": shorts[0].ticket}
        if not longs:
            state["last_ha_direction"] = "green"
            return {
                "action": "buy",
                "symbol": symbol,
                "stop_loss_pips": risk_manager.settings.stop_loss_pips,
                "take_profit_pips": risk_manager.settings.take_profit_pips,
                "comment": "Algo advance - long",
            }
    elif direction == "red":  # short signal
        if longs:
            return {"action": "close", "ticket": longs[0].ticket}
        if not shorts:
            state["last_ha_direction"] = "red"
            return {
                "action": "sell",
                "symbol": symbol,
                "stop_loss_pips": risk_manager.settings.stop_loss_pips,
                "take_profit_pips": risk_manager.settings.take_profit_pips,
                "comment": "Algo advance - short",
            }

    state["last_ha_direction"] = direction
    return None


def generate_signal(broker, risk_manager, state: dict) -> dict | None:
    """
    Called every poll by trading_worker.py. symbol/magic come from the
    running bot's configured Symbol / Magic Number (Bot Settings tab),
    seeded into state["symbol"] / state["magic"] by trading_worker.py's
    __init__ before the loop starts (see trading_worker.py's
    self._strategy_state = {"symbol": symbol, "magic": magic}).

    Timeframe comes from risk_manager.settings.timeframe - whatever's
    selected in the Bot Settings tab's Timeframe dropdown. Change it
    there, no code edit needed.
    """
    symbol = state.get("symbol")
    magic = state.get("magic", 0)
    if symbol is None:
        return None  # shouldn't happen once trading_worker.py seeds state, but stay safe

    timeframe = risk_manager.settings.timeframe

    direction = _latest_closed_ha_direction(broker, symbol, timeframe)
    if direction == "flat":
        return None

    last_seen = state.get("last_ha_direction")
    longs, shorts = _open_positions_by_side(broker, risk_manager, symbol, magic)
    already_correctly_positioned = (
        (direction == "green" and longs and not shorts) or
        (direction == "red" and shorts and not longs)
    )

    if direction == last_seen and already_correctly_positioned:
        return None  # no change since last time we acted - nothing to do

    return _manage_flip(broker, risk_manager, state, symbol, magic, direction)
