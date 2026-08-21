"""
settings_page.py
-----------------
App settings: glass intensity slider (0-100), version info, update check.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton

from version import __version__ as CURRENT_VERSION
from update_window import open_update_window
from dashboard import DashboardPage
import config


class SettingsPage(DashboardPage):
    title = "Settings"

    def build(self):
        super().build()
        self._cfg = config.load_config()

        panel = self.make_glass_panel(radius=18)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(14)

        section_label = QLabel("Appearance")
        section_label.setStyleSheet(self.theme.label_title_qss())
        panel_layout.addWidget(section_label)

        desc = QLabel("Control how much liquid glass translucency is applied across the app.")
        desc.setStyleSheet(self.theme.label_muted_qss())
        desc.setWordWrap(True)
        panel_layout.addWidget(desc)

        slider_row = QHBoxLayout()
        self.glass_slider = QSlider(Qt.Horizontal)
        self.glass_slider.setRange(0, 100)
        self.glass_slider.setValue(int(self._cfg.get("glass_intensity", 50)))
        self.glass_slider.setStyleSheet(self.theme.slider_qss())
        self.glass_slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.glass_slider, stretch=1)

        self.glass_value_label = QLabel(f"{self.glass_slider.value()}%")
        self.glass_value_label.setFixedWidth(40)
        self.glass_value_label.setStyleSheet(
            f"color: {self.theme.TEXT_PRIMARY}; font-weight: 600; background: transparent; border: none;")
        slider_row.addWidget(self.glass_value_label)
        panel_layout.addLayout(slider_row)

        hint = QLabel("0% = solid flat panels    ·    100% = maximum glass translucency")
        hint.setStyleSheet(self.theme.label_muted_qss())
        panel_layout.addWidget(hint)

        self._layout.insertWidget(1, panel)

        # --- about / update panel ---
        about_panel = self.make_glass_panel(radius=18)
        about_layout = QVBoxLayout(about_panel)
        about_layout.setContentsMargins(22, 20, 22, 20)
        about_layout.setSpacing(10)

        about_title = QLabel("About")
        about_title.setStyleSheet(self.theme.label_title_qss())
        about_layout.addWidget(about_title)

        version_label = QLabel(f"App version: {CURRENT_VERSION}")
        version_label.setStyleSheet(self.theme.label_muted_qss())
        about_layout.addWidget(version_label)

        update_btn = QPushButton("Check for Updates...")
        update_btn.setStyleSheet(self.theme.button_ghost_qss())
        update_btn.setCursor(Qt.PointingHandCursor)
        update_btn.clicked.connect(lambda: open_update_window(self.window()))
        about_layout.addWidget(update_btn, alignment=Qt.AlignLeft)

        self._layout.insertWidget(2, about_panel)

    def _on_slider_changed(self, value: int):
        self.glass_value_label.setText(f"{value}%")
        self.theme.set_intensity(value)
        self._cfg["glass_intensity"] = value
        config.save_config(self._cfg)

    def on_theme_changed(self, intensity: int):
        # keep the slider label in sync if intensity is changed elsewhere
        if self.glass_slider.value() != intensity:
            self.glass_slider.blockSignals(True)
            self.glass_slider.setValue(intensity)
            self.glass_slider.blockSignals(False)
            self.glass_value_label.setText(f"{intensity}%")
