"""
main.py
-------
Entry point. Wires up the Dashboard with your pages and starts the
Qt event loop. Also the file relaunched by updater.py after an
update installs, so keep "python main.py" working from this folder.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from dashboard import Dashboard
from trading_page import TradingPage
from settings_page import SettingsPage
from theme import GlassTheme
import config


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Use a cross-platform safe font stack as the app default. Qt falls
    # back automatically per-platform (Segoe UI on Windows, San Francisco/
    # Helvetica Neue on macOS, DejaVu/Noto on Linux) when the family name
    # isn't found, so this keeps text rendering crisp everywhere without
    # hand-picking a font per OS.
    default_font = QFont("Segoe UI")
    default_font.setStyleHint(QFont.SansSerif)
    app.setFont(default_font)

    cfg = config.load_config()
    theme = GlassTheme(intensity=int(cfg.get("glass_intensity", 50)))

    window = Dashboard(app_title="MT5 Bot", theme=theme)
    window.add_page("Trading Bot", TradingPage)
    window.add_page("Settings", SettingsPage)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
