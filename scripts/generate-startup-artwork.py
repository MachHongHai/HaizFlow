"""Render the code-native startup background and clipped existing brand mark.

Rendering happens at build time. The native startup window reads a BMP without
importing Qt, Pillow or model dependencies; localized text stays native/live.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "src/haizflow/desktop/assets/branding"


def render(*, preview: Path | None = None) -> None:
    application = QGuiApplication.instance() or QGuiApplication([])
    # The offscreen Qt platform does not automatically enumerate Windows fonts.
    # Use installed fonts only for preview; never copy Microsoft fonts into assets.
    for name in ("SegUIVar.ttf", "segoeui.ttf", "seguisb.ttf"):
        installed_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if installed_font.is_file():
            QFontDatabase.addApplicationFont(str(installed_font))
    image = QImage(1200, 676, QImage.Format.Format_RGB32)
    image.fill(QColor("#100c09"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer = QSvgRenderer(str(BRANDING / "startup-background.svg"))
    if not renderer.isValid():
        raise ValueError("Startup background SVG is invalid.")
    renderer.render(painter)
    logo_rectangle = QRectF(502, 142, 196, 196)
    clip = QPainterPath()
    clip.addRoundedRect(logo_rectangle, 38, 38)
    painter.save()
    painter.setClipPath(clip)
    logo = QImage(str(BRANDING / "haizflow-mark.png"))
    # The supplied mark has an opaque margin outside its rounded tile. Crop
    # the source tile and clip its corners while composing, not by editing it.
    painter.drawImage(logo_rectangle, logo, QRectF(96, 92, 1062, 1068))
    painter.restore()
    outline = QLinearGradient(502, 142, 698, 338)
    outline.setColorAt(0, QColor("#7e5745"))
    outline.setColorAt(.5, QColor("#ffd5a1"))
    outline.setColorAt(1, QColor("#78451f"))
    painter.setPen(QPen(outline, 1.6))
    painter.drawPath(clip)
    painter.end()
    if not image.save(str(BRANDING / "startup-splash.bmp"), "BMP"):
        raise ValueError("Could not save the native startup background.")
    if preview is not None:
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Segoe UI Variable")
        font.setPixelSize(80)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        widths = [painter.fontMetrics().horizontalAdvance(part) for part in ("Haiz", "Flow")]
        x = (image.width() - sum(widths)) / 2
        for part, width, color in zip(("Haiz", "Flow"), widths, ("#f6f4ef", "#ffb65d")):
            painter.setPen(QColor(color))
            painter.drawText(QRectF(x, 348, width, 100), part)
            x += width
        font.setPixelSize(32)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor("#ded2c4"))
        from PySide6.QtCore import Qt
        painter.drawText(QRectF(40, 443, 1120, 65), Qt.AlignmentFlag.AlignCenter, "Đang khởi động…")
        gradient = QLinearGradient(337, 0, 586, 0)
        gradient.setColorAt(0, QColor("#ff6c26"))
        gradient.setColorAt(1, QColor("#ffe0a0"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(337, 521, 249, 9), 4.5, 4.5)
        painter.end()
        preview.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(preview))
    # Keep the QGuiApplication wrapper alive until painting is complete.
    del application


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path)
    render(preview=parser.parse_args().preview)
