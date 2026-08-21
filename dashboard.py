"""
dashboard.py
------------
Reusable PySide6 dashboard shell, "liquid glass" style: a translucent
sidebar over a dark gradient background, driving a QStackedWidget
content area of glass-panel pages.

Real backdrop blur: Qt has no CSS-style backdrop-filter, so this window
renders its own background gradient (plus a few soft accent glows) into
an offscreen QPixmap, blurs a copy of it with QGraphicsBlurEffect, and
stores the result on self._blurred_backdrop. Every GlassPanel (see
glass_panel.py) reads that pixmap and paints the cropped, blurred slice
that sits directly behind it - producing genuine frosted-glass panels
that show a blurred version of the app's own background through them,
not just a flat translucent color. The buffer regenerates on resize and
whenever the intensity slider changes (since blur radius scales with it).

No Home page - the app opens straight into the first registered page
(Trading Bot).
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsBlurEffect,
)
from PySide6.QtGui import (
    QFont, QAction, QPixmap, QPainter, QLinearGradient, QColor, QRadialGradient,
)

from version import __version__ as CURRENT_VERSION
from update_window import open_update_window
from theme import GlassTheme
from glass_panel import GlassPanel


class DashboardPage(QWidget):
    """
    Base class for a page shown in the dashboard's content area.
    Subclasses get self.theme (a GlassTheme) available in build(), and
    should override on_theme_changed() if they have custom glass panels
    that need re-styling when the intensity slider moves.
    """

    title = "Untitled Page"

    def __init__(self, theme: GlassTheme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        self.build()
        self.theme.glass_changed.connect(self.on_theme_changed)

    def build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(self.title)
        heading_font = QFont("Segoe UI", 18, QFont.Bold)
        heading_font.setStyleHint(QFont.SansSerif)
        heading.setFont(heading_font)
        heading.setStyleSheet(f"color: {self.theme.TEXT_PRIMARY}; background: transparent; border: none;")
        layout.addWidget(heading, alignment=Qt.AlignLeft)
        layout.addStretch()
        self._layout = layout

    def on_theme_changed(self, intensity: int):
        """Override in subclasses to re-apply glass QSS to custom panels."""
        pass

    def make_glass_panel(self, radius: int = 16) -> QWidget:
        """Returns a real frosted-glass panel (see glass_panel.py)."""
        return GlassPanel(self.theme, radius=radius)


class Dashboard(QMainWindow):
    """
    Main application window: glass sidebar + glass content area.
    Register pages via `self.add_page(name, PageClass)`.
    """

    def __init__(self, app_title="My App", theme: GlassTheme = None):
        super().__init__()
        self.theme = theme or GlassTheme(intensity=50)
        self._app_title = app_title
        self.setWindowTitle(f"{app_title}  v{CURRENT_VERSION}")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        self._page_classes = {}
        self._page_instances = {}
        self._blurred_backdrop = QPixmap()

        self._build_menu()
        self._build_layout()
        self.theme.glass_changed.connect(self._on_theme_changed)
        self._apply_theme(self.theme.intensity)

    # --------------------------------------------------------------- menu

    def _build_menu(self):
        menubar = self.menuBar()
        app_menu = menubar.addMenu("App")

        check_action = QAction("Check for Updates...", self)
        check_action.triggered.connect(lambda: open_update_window(self))
        app_menu.addAction(check_action)

        app_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        app_menu.addAction(exit_action)

    # ------------------------------------------------------------- layout

    def _build_layout(self):
        central = QWidget()
        central.setObjectName("GlassRoot")
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- sidebar ---
        self.sidebar = QWidget()
        self.sidebar.setAttribute(Qt.WA_StyledBackground, True)
        self.sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 22, 0, 16)
        sidebar_layout.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(20, 0, 20, 0)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {self.theme.ACCENT}; font-size: 14px;")
        brand_row.addWidget(dot)
        app_label = QLabel(self._app_title)
        app_label.setStyleSheet(
            f"color: {self.theme.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; margin-left: 6px;")
        brand_row.addWidget(app_label)
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addSpacing(26)

        self.nav_list = QListWidget()
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        sidebar_layout.addWidget(self.nav_list, stretch=1)

        version_label = QLabel(f"v{CURRENT_VERSION}")
        version_label.setStyleSheet(f"color: {self.theme.TEXT_MUTED}; font-size: 9px; padding: 0 20px;")
        sidebar_layout.addWidget(version_label)
        sidebar_layout.addSpacing(6)

        self.update_btn = QLabel("⟳  Check for Updates...")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setStyleSheet(
            f"color: {self.theme.TEXT_SECONDARY}; font-size: 10px; padding: 8px 20px;")
        self.update_btn.mousePressEvent = lambda e: open_update_window(self)
        sidebar_layout.addWidget(self.update_btn)

        root_layout.addWidget(self.sidebar)

        # --- content area ---
        self.content_stack = QStackedWidget()
        self.content_stack.setAttribute(Qt.WA_StyledBackground, True)
        root_layout.addWidget(self.content_stack, stretch=1)

    def _apply_theme(self, _intensity: int):
        self.centralWidget().setStyleSheet(self.theme.app_background_qss())
        self.sidebar.setStyleSheet(self.theme.sidebar_qss())
        self.nav_list.setStyleSheet(self.theme.nav_list_qss())
        self.content_stack.setStyleSheet("background: transparent; border: none;")
        self._rebuild_backdrop()

    def _on_theme_changed(self, intensity: int):
        self._apply_theme(intensity)

    # ---------------------------------------------------- backdrop buffer

    def _rebuild_backdrop(self):
        """
        Renders the window's own background gradient (+ soft accent
        glows, for visual interest to actually blur) into a QPixmap,
        then blurs it. GlassPanel widgets crop their own region out of
        self._blurred_backdrop in their paintEvent().
        """
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            return

        # 1) Paint the flat background gradient + glow accents at full res.
        base = QPixmap(size)
        base.fill(Qt.transparent)
        painter = QPainter(base)
        painter.setRenderHint(QPainter.Antialiasing)

        grad = QLinearGradient(0, 0, size.width() * 0.4, size.height())
        grad.setColorAt(0.0, QColor(self.theme.BG_TOP))
        grad.setColorAt(1.0, QColor(self.theme.BG_BOTTOM))
        painter.fillRect(base.rect(), grad)

        # A couple of soft accent glows give the blur something to work
        # with visually - without any texture behind it, a blurred flat
        # gradient just looks like... a flat gradient. Tuned lighter here
        # since they sit on a light background, not a dark one.
        glow1 = QRadialGradient(size.width() * 0.8, size.height() * 0.1, size.width() * 0.55)
        glow1.setColorAt(0.0, QColor(120, 160, 255, 130))
        glow1.setColorAt(1.0, QColor(120, 160, 255, 0))
        painter.fillRect(base.rect(), glow1)

        glow2 = QRadialGradient(size.width() * 0.1, size.height() * 0.9, size.width() * 0.5)
        glow2.setColorAt(0.0, QColor(180, 140, 255, 110))
        glow2.setColorAt(1.0, QColor(180, 140, 255, 0))
        painter.fillRect(base.rect(), glow2)

        glow3 = QRadialGradient(size.width() * 0.5, size.height() * 0.5, size.width() * 0.35)
        glow3.setColorAt(0.0, QColor(255, 255, 255, 90))
        glow3.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(base.rect(), glow3)
        painter.end()

        # 2) Blur it via a QGraphicsScene round-trip (the standard way to
        # apply a QGraphicsEffect to a QPixmap rather than a live widget).
        blur_px = self.theme.blur_radius()
        if blur_px <= 0:
            self._blurred_backdrop = base
        else:
            scene = QGraphicsScene()
            item = QGraphicsPixmapItem(base)
            effect = QGraphicsBlurEffect()
            effect.setBlurRadius(blur_px)
            item.setGraphicsEffect(effect)
            scene.addItem(item)

            result = QPixmap(size)
            result.fill(Qt.transparent)
            result_painter = QPainter(result)
            result_painter.setRenderHint(QPainter.Antialiasing)
            scene.render(result_painter, QRectF(base.rect()), QRectF(base.rect()))
            result_painter.end()
            self._blurred_backdrop = result

        # Repaint every glass panel now that the backdrop changed.
        for panel in self.findChildren(GlassPanel):
            panel.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_backdrop()

    # ----------------------------------------------------------- page API

    def add_page(self, name: str, page_class):
        """Register a page class under `name`, add sidebar entry, instantiate it."""
        self._page_classes[name] = page_class
        instance = page_class(self.theme)
        self._page_instances[name] = instance
        self.content_stack.addWidget(instance)

        item = QListWidgetItem(name)
        self.nav_list.addItem(item)

        if self.nav_list.count() == 1:
            self.nav_list.setCurrentRow(0)

    def show_page(self, name: str):
        if name not in self._page_instances:
            raise ValueError(f"No page registered under '{name}'")
        for i in range(self.nav_list.count()):
            if self.nav_list.item(i).text() == name:
                self.nav_list.setCurrentRow(i)
                return

    def _on_nav_changed(self, row: int):
        if row < 0:
            return
        name = self.nav_list.item(row).text()
        self.content_stack.setCurrentWidget(self._page_instances[name])

