"""Load only caption fonts actually needed by a Qt fallback/selection preview."""
from functools import lru_cache

from PySide6.QtGui import QFontDatabase, QGuiApplication

from haizflow.core.subtitle_fonts import bundled_font_path, font_catalog, subtitle_font_for_text


@lru_cache(maxsize=7)
def _register(family):
    path = bundled_font_path(family)
    if path is None or QFontDatabase.addApplicationFont(str(path)) < 0:
        raise RuntimeError(f"Cannot load bundled subtitle font: {family}")


def qt_subtitle_font(text="", language=""):
    family = subtitle_font_for_text(text, language)
    if QGuiApplication.instance() is not None:
        _register(family)
    spec = font_catalog()[family]
    from haizflow.pipeline.render import _ass_font_em_scale

    return {"family": spec["qt_family"], "weight": spec["weight"],
            "scale": _ass_font_em_scale(str(bundled_font_path(family)))}
