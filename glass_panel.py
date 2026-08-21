"""
glass_panel.py
---------------
A genuine frosted-glass panel widget for PySide6.

Qt's QSS `background-color: rgba(...)` only blends against the app's own
painted background - it can NEVER show a blurred version of what's behind
it, because Qt has no backdrop-filter/backdrop-blur concept at the widget
level (unlike CSS or native macOS NSVisualEffectView). A flat rgba() panel
just looks like a dark rectangle with a tint, which is not "liquid glass"
no matter how the alpha is tuned - confirmed by testing.

GlassPanel instead does what browsers and native toolkits actually do
under the hood to fake backdrop blur: it grabs a snapshot of what's
directly behind the panel (the app's own background gradient/content,
rendered once into an offscreen buffer), blurs that snapshot with
QGraphicsBlurEffect, and paints the blurred result as the panel's own
background in paintEvent(). This produces real, visible blur of the
content behind the panel - not just a translucent color wash - which is
what actually reads as "glass" to the eye.

Usage: GlassPanel reads window()._blurred_backdrop, a QPixmap the
Dashboard window regenerates whenever it resizes or the theme's
intensity changes (see dashboard.py's _rebuild_background_buffer()).
"""

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class GlassPanel(QWidget):
    """
    A widget that paints itself as frosted glass: a blurred crop of the
    app's background buffer, tinted and bordered. Automatically repaints
    when intensity changes (connected to theme.glass_changed) or when
    the window regenerates its background buffer (e.g. on resize).
    """

    def __init__(self, theme, radius: int = 16, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.radius = radius
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        theme.glass_changed.connect(lambda _i: self.update())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), self.radius, self.radius)
        painter.setClipPath(path)

        # 1) Paint the blurred backdrop crop, if the window has one ready.
        window = self.window()
        backdrop = getattr(window, "_blurred_backdrop", None)
        if backdrop is not None and not backdrop.isNull():
            global_top_left = self.mapTo(window, QPoint(0, 0))
            source_rect = QRect(global_top_left, rect.size())
            painter.drawPixmap(rect, backdrop, source_rect)

        # 2) Tint overlay - lightens the blurred backdrop based on
        # intensity, so it still reads as a distinct "panel" rather than
        # a plain window-shaped cutout, and stays legible under any
        # background content. Color pulled from theme.PANEL_TINT_RGB so
        # this works for both light and dark palettes without editing
        # this file.
        tint_alpha = self.theme.panel_tint_alpha()
        tint_r, tint_g, tint_b = self.theme.PANEL_TINT_RGB
        painter.fillPath(path, QColor(tint_r, tint_g, tint_b, tint_alpha))

        # 3) Border
        painter.setClipping(False)
        border_r, border_g, border_b = self.theme.BORDER_RGB
        pen = QPen(QColor(border_r, border_g, border_b, self.theme.border_alpha()))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), self.radius, self.radius)
