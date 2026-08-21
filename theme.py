"""
theme.py
--------
"Liquid glass" theme engine for the whole app - light mode.

Qt has no native backdrop-blur, so the glass look is built by
dashboard.py rendering the window's own background into an offscreen
buffer, blurring it, and having every GlassPanel (glass_panel.py) paint
the cropped, blurred slice that sits behind it. This file only supplies
the palette and alpha/blur math that drives that effect - see
glass_panel.py for the actual paint logic.

The single knob that controls glass strength is `GlassTheme.intensity`
(0-100):
  - 0   = fully opaque flat light panels (glass effect off)
  - 50  = default, moderate translucency
  - 100 = maximum translucency / most "glassy"
"""

from PySide6.QtCore import QObject, Signal


class GlassTheme(QObject):
    """
    Central theme object. Create ONE instance and pass it down to every
    page/widget that needs glass styling, so they all stay in sync.
    """

    glass_changed = Signal(int)  # emits new intensity (0-100)

    # Base palette - light, bright, airy (full light mode)
    BG_TOP = "#eef2fb"
    BG_BOTTOM = "#dbe4f5"
    ACCENT = "#3b6fe0"
    ACCENT_SOFT = "#5c86e8"
    TEXT_PRIMARY = "#1a2233"
    TEXT_SECONDARY = "#51617a"
    TEXT_MUTED = "#8492a8"
    SUCCESS = "#1fa864"
    DANGER = "#e0405a"
    WARNING = "#d98a1c"

    # Backdrop-blur glow tint (panel fill drawn over the blurred backdrop)
    PANEL_TINT_RGB = (255, 255, 255)  # white tint, light mode
    BORDER_RGB = (30, 41, 66)          # dark border, reads on light bg

    def __init__(self, intensity: int = 50, parent=None):
        super().__init__(parent)
        self._intensity = max(0, min(100, intensity))

    @property
    def intensity(self) -> int:
        return self._intensity

    def set_intensity(self, value: int):
        self._intensity = max(0, min(100, value))
        self.glass_changed.emit(self._intensity)

    # ------------------------------------------------------------ real glass

    def blur_radius(self) -> int:
        """
        How strongly the backdrop is blurred behind glass panels.
        Higher intensity = more blur = more "frosted" look, capped at a
        sensible max so it doesn't turn into pure mush.
        """
        return int(4 + (self._intensity / 100) * 36)  # 4px .. 40px

    def panel_tint_alpha(self) -> int:
        """
        0-255 alpha for the light tint painted over the blurred backdrop.
        At intensity 0: nearly opaque (glass "off", reads as a flat panel).
        At intensity 100: much more of the blurred backdrop shows through.
        """
        return int(225 - (self._intensity / 100) * 165)  # 225 .. 60

    def border_alpha(self) -> int:
        """0-255 alpha for panel borders, brightens slightly with intensity."""
        return int(30 + (self._intensity / 100) * 50)  # 30 .. 80

    # ------------------------------------------------------------ helpers

    def _alpha(self, base_alpha_at_100: float) -> float:
        """Scale an alpha value by the current intensity (0-100)."""
        return base_alpha_at_100 * (self._intensity / 100)

    def panel_rgba(self, base_alpha_at_100: float = 0.55) -> str:
        """
        Light-tinted glass fill for QSS-styled elements (sidebar, inputs).
        At intensity 0: nearly opaque white panel (glass effect "off").
        At intensity 100: more translucent, letting more of whatever's
        beneath show through.
        """
        opacity = 0.96 - (self._intensity / 100) * (0.96 - base_alpha_at_100)
        return f"rgba(255, 255, 255, {opacity:.3f})"

    def border_rgba(self) -> str:
        """Border darkens slightly as glass intensity increases (light mode)."""
        a = 0.08 + (self._intensity / 100) * 0.14
        return f"rgba(30, 41, 66, {a:.3f})"

    # ------------------------------------------------------------ QSS

    def app_background_qss(self) -> str:
        """Full-window gradient background, the base the glass sits on."""
        return f"""
            QMainWindow, #GlassRoot {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0.4, y2:1,
                    stop:0 {self.BG_TOP}, stop:1 {self.BG_BOTTOM}
                );
            }}
        """

    def panel_qss(self, radius: int = 16, alpha: float = 0.14) -> str:
        """A glass card/panel: translucent fill, soft border, rounded corners."""
        bg = self.panel_rgba(alpha)
        border = self.border_rgba()
        return f"""
            background-color: {bg};
            border: 1px solid {border};
            border-radius: {radius}px;
        """

    def sidebar_qss(self) -> str:
        opacity = 0.97 - (self._intensity / 100) * (0.97 - 0.55)
        return f"""
            background-color: rgba(255, 255, 255, {opacity:.3f});
            border-right: 1px solid {self.border_rgba()};
        """

    def input_qss(self) -> str:
        bg = self.panel_rgba(0.55)
        border = self.border_rgba()
        return f"""
            QLineEdit, QComboBox {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 7px 10px;
                color: {self.TEXT_PRIMARY};
                selection-background-color: {self.ACCENT};
                selection-color: white;
            }}
            QLineEdit::placeholder {{
                color: {self.TEXT_MUTED};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {self.ACCENT_SOFT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #ffffff;
                color: {self.TEXT_PRIMARY};
                selection-background-color: {self.ACCENT};
                selection-color: white;
                border: 1px solid {self.border_rgba()};
                outline: none;
            }}
        """

    def label_title_qss(self) -> str:
        return (f"color: {self.TEXT_PRIMARY}; font-size: 15px; font-weight: 600; "
                f"background: transparent; border: none;")

    def label_muted_qss(self) -> str:
        return (f"color: {self.TEXT_SECONDARY}; font-size: 11px; "
                f"background: transparent; border: none;")

    def button_primary_qss(self) -> str:
        return f"""
            QPushButton {{
                background-color: {self.ACCENT};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 9px 20px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {self.ACCENT_SOFT}; }}
            QPushButton:disabled {{ background-color: rgba(30,41,66,0.15); color: {self.TEXT_MUTED}; }}
        """

    def button_danger_qss(self) -> str:
        return f"""
            QPushButton {{
                background-color: {self.DANGER};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 9px 20px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: #ea5c73; }}
            QPushButton:disabled {{ background-color: rgba(30,41,66,0.15); color: {self.TEXT_MUTED}; }}
        """

    def button_ghost_qss(self) -> str:
        return f"""
            QPushButton {{
                background-color: {self.panel_rgba(0.08)};
                color: {self.TEXT_PRIMARY};
                border: 1px solid {self.border_rgba()};
                border-radius: 8px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background-color: {self.panel_rgba(0.16)}; }}
        """

    def checkbox_qss(self) -> str:
        return f"""
            QCheckBox {{ color: {self.TEXT_PRIMARY}; spacing: 8px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border-radius: 4px;
                border: 1px solid {self.border_rgba()};
                background: {self.panel_rgba(0.08)};
            }}
            QCheckBox::indicator:checked {{
                background: {self.ACCENT};
                border: 1px solid {self.ACCENT};
            }}
        """

    def nav_list_qss(self) -> str:
        return f"""
            QListWidget {{
                background: transparent;
                border: none;
                color: {self.TEXT_SECONDARY};
                font-size: 12px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 11px 18px;
                margin: 2px 10px;
                border-radius: 8px;
            }}
            QListWidget::item:selected {{
                background: {self.panel_rgba(0.18)};
                color: {self.TEXT_PRIMARY};
            }}
            QListWidget::item:hover:!selected {{
                background: {self.panel_rgba(0.08)};
            }}
        """

    def terminal_qss(self) -> str:
        """
        Deliberately kept dark even in light mode - terminal/log views
        conventionally stay dark for readability regardless of the app's
        overall theme (matches VS Code, Xcode console, etc).
        """
        return f"""
            QTextEdit {{
                background-color: rgba(20, 26, 38, 0.92);
                color: #d7dee8;
                border: 1px solid {self.border_rgba()};
                border-radius: 10px;
                padding: 10px;
            }}
        """

    def slider_qss(self) -> str:
        return f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: rgba(30,41,66,0.15);
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {self.ACCENT};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: white;
                border: 1px solid rgba(30,41,66,0.25);
                width: 16px; height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
        """
