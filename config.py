"""
config.py
---------
Loads/saves MT5 login credentials and bot settings to a local JSON
file next to the app, so the user doesn't have to retype everything
each run.

NOTE: this stores the MT5 password in plain text on disk. That's fine
for a local desktop trading tool the user controls, but don't ship this
config file anywhere shared (git repo, cloud sync folder others can read).
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_config.json")

DEFAULTS = {
    "mt5_login": "",
    "mt5_password": "",
    "mt5_server": "",
    "mt5_path": "",

    "symbol": "EURUSD",
    "magic_number": 123456,
    "timeframe": "M15",

    "use_fixed_lot": True,
    "lot_size": 0.10,
    "risk_percent": 1.0,

    "risk_management_enabled": True,
    "stop_loss_pips": 20.0,
    "take_profit_pips": 40.0,
    "max_daily_loss_amount": 200.0,
    "max_drawdown_amount": 500.0,
    "max_open_trades": 3,
    "use_trailing_stop": False,
    "trailing_stop_pips": 20.0,

    "glass_intensity": 50,
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
