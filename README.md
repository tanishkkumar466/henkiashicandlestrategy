# Self-Updating MT5 Trading Bot Dashboard (Liquid Glass Edition)

PySide6 desktop app with a macOS-style "liquid glass" UI, MT5 connection,
and adjustable risk management. Built on the self-updating dashboard
framework from earlier.

**⚠️ MetaTrader5's Python package only works on Windows** (it talks to the
locally installed MT5 terminal). Everything else — UI, glass theme, risk
manager, config — runs and was tested on any OS; only `broker.py`'s actual
MT5 calls need Windows.

## What's new in this version

- **Full light mode**: bright white/light-blue gradient background,
  dark readable text, light glass panels. Same real-blur glass mechanism
  as before (see "Bugs found and fixed" below) — just re-tinted for
  light mode instead of dark. The intensity slider in **Settings**
  (0-100%) still controls how much glass translucency is applied
  app-wide, live, no restart needed.
- **Trading Bot page reorganized into tabs**: Login / Settings / Risk
  are now three tabs instead of one long stacked/scrolling list of
  cards. Every field, checkbox, and value is exactly the same as
  before — only the layout changed. Start/Stop controls and the
  Strategy Log stay visible below the tabs regardless of which tab is
  active.
- **No Home page** — app opens directly on Trading Bot.
- **Risk management**:
  - One master **Enable risk management** checkbox. Turn it off and the
    bot trades completely unrestricted — useful for raw demo testing.
    All risk fields grey out when disabled.
  - Concrete values instead of abstract percentages: stop loss / take
    profit in **pips**, max daily loss in **$**, max drawdown in **$**,
    max open trades as a count — these map directly to what you'd type
    into MT5 itself.
  - **Timeframe** is now a first-class dropdown (M1/M5/M15/M30/H1/H4/D1),
    passed through to `risk_manager.settings.timeframe` for `logic.py`
    to use when pulling candles.

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point, sets the app-wide font and glass theme |
| `theme.py` | `GlassTheme`: the single intensity knob (0-100) driving every panel/input/sidebar QSS |
| `dashboard.py` | Sidebar + page shell, `DashboardPage` base class with `make_glass_panel()` helper |
| `trading_page.py` | Trading Bot page: login, settings, risk management, terminal log |
| `numeric_field.py` | `NumericField`: QLineEdit-based numeric input, replaces QSpinBox (see "Bugs found and fixed" below) |
| `glass_panel.py` | `GlassPanel`: real frosted-glass widget with custom-painted backdrop blur (see "Bugs found and fixed" below) |
| `settings_page.py` | Glass intensity slider + About/update check |
| `trading_worker.py` | QThread bot loop: connect → logic → risk check → broker action |
| `broker.py` | MT5 connection wrapper (connect, orders, positions, candles) |
| `risk_manager.py` | Enable toggle, pip/dollar-based limits, timeframe setting |
| `logic.py` | **Empty — write your own buy/sell strategy here** |
| `config.py` | Saves/loads credentials + settings to `bot_config.json` |
| `updater.py` / `workers.py` / `update_window.py` | Self-update system (unchanged) |
| `version.py` | Bump before each release |

## Setup

```bash
pip install -r requirements.txt
python main.py
```

The app opens on **Trading Bot**. Fill in:

- **MT5 Login**: login, password, server, optional terminal path
- **Bot Settings**: symbol, timeframe, magic number, fixed lot or risk %
- **Risk Management**:
  - Master **Enable risk management** switch — off means unrestricted
    trading (no daily loss cap, no drawdown lock, no open-trade limit)
  - Stop loss / take profit in pips
  - Max daily loss in $ (bot stops trading for the day once equity has
    dropped this much from the day's starting balance)
  - Max drawdown lock in $ (if equity falls this far from its peak,
    trading locks until you manually call `reset_drawdown_lock()`)
  - Max open trades
  - Optional trailing stop, distance in pips

Go to **Settings** to adjust the glass intensity slider — drag it and
every panel across the app re-styles immediately.

## Writing your strategy

`logic.py` is empty — that part is yours. One function:

```python
def generate_signal(broker, risk_manager, state: dict) -> dict | None:
    # broker.get_symbol_price("EURUSD") -> {"bid":.., "ask":.., "time":..}
    # broker.get_candles("EURUSD", timeframe=risk_manager.settings.timeframe, count=200)
    # risk_manager.can_trade(open_trade_count) -> (bool, reason)

    return {
        "action": "buy",            # "buy" | "sell" | "close"
        "symbol": "EURUSD",
        "stop_loss_pips": 20,       # used for risk-based lot sizing
        "stop_loss": 1.0950,        # actual SL price (optional)
        "take_profit": 1.1050,      # optional
        "comment": "my strategy",
    }
```

If `logic.py` has no `generate_signal()` (or is missing entirely), the bot
connects and runs its loop but logs "no strategy defined" instead of
crashing.

## What was tested (no real MT5 account needed)

- `risk_manager.py`: enable/disable master switch, fixed vs. risk-%
  lot sizing, $ daily loss block, $ drawdown lock + persistence + reset,
  daily counter reset on a new day, timeframe list — all passing
- `config.py`: save/load round-trip with all new fields
- `broker.py`: graceful, readable error when MT5 isn't installed
- Full UI: glass theme renders, slider changes propagate live to every
  open panel, risk-management checkbox correctly greys out/re-enables
  every dependent field, timeframe dropdown populated correctly
- Full bot loop: risk-management-disabled mode confirmed to bypass
  max_open_trades even with 5 phantom open positions against a limit
  of 1 — proving the "unrestricted demo" mode works as intended
- Full trading pipeline with a mock strategy: `logic.py` signal →
  `risk_manager` lot sizing → `broker.place_order()` — correct lot
  math end to end

### Bugs found and fixed

**Max daily loss check was silently dead.** It compared against a
`realized_pnl` counter that nothing in the app ever updated, so it never
triggered no matter how much money was actually lost. Fixed by having
`update_account_snapshot()` track daily loss as (start-of-day balance −
current equity) instead — the same way MT5 itself typically reports
daily loss, and it now works automatically from the account snapshots
the bot already pulls every tick. Re-verified with a full regression
pass plus a test that specifically reproduces the original bug.

**Numeric input fields rendered garbled text.** Confirmed on a real
macOS build (not just in testing): "Magic Number", "Stop loss", "Max
daily loss" and similar fields showed corrupted, overlapping glyphs
instead of readable numbers. Root cause: `QSpinBox`/`QDoubleSpinBox`'s
internal up/down-button sub-controls have a geometry bug in this app's
combination of styling and layout - their internal text sub-control
geometry doesn't get laid out correctly, which visually corrupts the
displayed number even though the underlying value is always correct.
Fixed by replacing every `QSpinBox`/`QDoubleSpinBox` with `NumericField`
(`numeric_field.py`), a small `QLineEdit`-based widget with the same
`.value()`/`.setValue()` interface plus prefix/suffix support (" pips",
"$ "), validated with `QIntValidator`/`QDoubleValidator`. This sidesteps
the buggy sub-control machinery entirely. Re-verified visually (screenshot
confirms every field now reads correctly) and functionally (all checkbox
enable/disable interactions, config save/load, and the full trading
pipeline re-tested and passing).

One visible trade-off: `NumericField` has no up/down arrow buttons -
type the value directly and click away (or press Tab/Enter) to commit
it. Values are still clamped to their min/max range and invalid input
falls back to the field's minimum rather than crashing.

**Panels didn't actually look like glass - just flat dark rectangles.**
Confirmed on a real macOS build. Root cause: Qt's `background-color:
rgba(...)` QSS only blends against the app's *own* painted background,
never against the OS desktop or anything with real depth - it's just a
translucent color wash, not backdrop blur. No amount of alpha tuning
fixes that, because Qt has no CSS-style `backdrop-filter` concept at the
widget level. Fixed properly with `glass_panel.py`'s `GlassPanel`: the
window renders its own background gradient plus a few soft accent glows
into an offscreen `QPixmap`, blurs it with `QGraphicsBlurEffect`, and
every `GlassPanel` custom-paints the cropped, blurred slice that sits
directly behind it as its own background, with a tint and border on
top. This produces genuine visible blur/glow bleeding through each
panel rather than a flat tint, and it's confirmed to change meaningfully
live as the intensity slider moves (low intensity ~ solid flat panels,
high intensity ~ strong colorful blur visible through every card). The
backdrop buffer regenerates on window resize and on every intensity
change.

## What still needs a real Windows + MT5 environment

- Actual `broker.connect()` login against a real/demo account
- Actual order placement, fills, position closing
- Live tick loop behavior over time
- Visual confirmation of the glass UI on a real display (not offscreen)

## MT5-specific issues found and fixed

These were researched against documented MT5 API behavior and real
trader bug reports (this sandbox can't run the actual MetaTrader5
package, so these were verified by mocking `mt5.*` calls to simulate
realistic broker responses, not by connecting to a live account):

**Hardcoded `type_filling=ORDER_FILLING_IOC` would reject orders on
many brokers.** Brokers support different combinations of FOK/IOC/RETURN
fill policies per symbol - sending an unsupported one is one of the most
commonly reported MT5 Python failures (`retcode=10030`, "Unsupported
filling mode"). Fixed with `_resolve_filling_mode()`, which reads the
symbol's actual supported modes via `symbol_info().filling_mode` and
picks one that's actually valid, instead of assuming IOC works
everywhere. Used by both `place_order()` and `close_position()`.

**Missing `deviation` (max slippage) parameter.** Every real-world
example of `order_send()` includes `deviation` - without it, orders are
commonly rejected with `retcode=10004` ("Requote") if price moves even
slightly between reading the tick and the order arriving. Added
`deviation: int = 20` to both `place_order()` and `close_position()`
(20 points is a reasonable default for most forex majors).

**Lot size only rounded to 2 decimals, ignoring broker volume
constraints.** `risk_manager.calculate_lot_size()`'s `round(x, 2)` can
produce a volume that isn't a valid multiple of the broker's actual
`volume_step` (which varies by symbol - often 0.01, but sometimes 0.1
for indices/crypto), and doesn't respect `volume_min`/`volume_max`. This
is explicitly called out across multiple sources as the standard cause
of `retcode=10014` ("Invalid volume"). Fixed with `_normalize_volume()`
in `broker.py`, which reads the symbol's real constraints and floors to
the nearest valid step, then clamps to min/max - applied automatically
inside `place_order()` before every order is sent.

**No visibility into "AutoTrading disabled" state.** If the MT5
terminal's Algo Trading button is off, every order silently fails with
a generic rejection that doesn't explain why. `connect()` now checks
`terminal_info().trade_allowed` and `trading_worker.py` logs an explicit,
actionable warning ("AutoTrading is OFF... click the Algo Trading
button") right after connecting, instead of leaving the user to guess
why every order fails.

**Orders were being sent with SL=0.0 and TP=0.0 every single time -
no stop loss or take profit protection at all.** This was the most
serious issue found. `logic.py` signals only ever set
`stop_loss_pips`/`take_profit_pips` (pip distances), but
`trading_worker.py` was reading `signal.get("stop_loss", 0.0)` - a
different, price-based key that no signal ever populated - so every
order silently went out completely unprotected. Fixed two ways:
  - `broker.py` gained `pip_size()` and `pips_to_price_offset()`,
    which correctly convert a pip distance to a real price offset.
    This isn't just `pips * point` - most brokers today quote with an
    extra fractional digit (5-digit majors, 3-digit JPY pairs), where
    1 pip = 10 * point, not 1 * point. Using point directly would have
    made every stop-loss 10x too tight on most modern brokers. Fixed
    to check `symbol_info().digits` and apply the correct multiplier,
    tested against both 5-digit/3-digit (modern) and 4-digit/2-digit
    (legacy) broker conventions.
  - `trading_worker.py`'s `_execute_signal()` now converts
    `stop_loss_pips`/`take_profit_pips` into real prices (relative to
    current ask/bid, correctly inverted for buy vs sell) before calling
    `place_order()`, and logs the resulting SL/TP prices in the
    Strategy Log so you can see exactly what protection every trade
    got. An explicit `stop_loss`/`take_profit` price in a signal still
    takes priority over the pip conversion if both are present.

All fixes were unit tested against mocked realistic broker responses
(varying `filling_mode` bitmasks, `volume_step` values, `trade_allowed`
states, `digits`/`point` combinations across both digit conventions,
buy vs sell SL/TP direction) - not connected to a live account, since
that's not possible from this environment. Test the demo account
carefully yourself before scaling up, and watch the Strategy Log's
`SL=... TP=...` output on your first few trades to confirm the numbers
look right for your broker/symbol.

## Self-update system

Unchanged — bump `version.py`, zip your `.py` files, attach to a GitHub
Release tagged `vX.Y.Z`. Set `GITHUB_OWNER` / `GITHUB_REPO` at the top of
`updater.py`.
