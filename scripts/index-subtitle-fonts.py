"""Index unmodified, pinned font assets; fontTools is development-only."""
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1] / "src/haizflow/assets/fonts"
FONTS = {
    "Bangers": ("Bangers-Regular.ttf", "Bangers", 400),
    "Noto Sans SC Black": ("NotoSansSC-Black.otf", "Noto Sans SC", 900),
    "Noto Sans TC Black": ("NotoSansTC-Black.otf", "Noto Sans TC", 900),
    "Noto Sans JP Black": ("NotoSansJP-Black.otf", "Noto Sans JP", 900),
    "Noto Sans KR Black": ("NotoSansKR-Black.otf", "Noto Sans KR", 900),
    "Dela Gothic One": ("DelaGothicOne-Regular.ttf", "Dela Gothic One", 400),
    "Pretendard ExtraBold": ("Pretendard-ExtraBold.otf", "Pretendard", 800),
}
entries = {}
for family, (filename, qt_family, weight) in FONTS.items():
    path = ROOT / filename
    font = TTFont(path)
    ranges = []
    for point in sorted(font.getBestCmap()):
        if ranges and point == ranges[-1][1] + 1:
            ranges[-1][1] = point
        else:
            ranges.append([point, point])
    entries[family] = dict(file=filename, qt_family=qt_family, weight=weight,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           bytes=path.stat().st_size, coverage=ranges,
                           copyright=font["name"].getDebugName(0))
(ROOT.parent / "subtitle-fonts.json").write_text(json.dumps({"version": 1, "fonts": entries},
                                                    ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
print("Indexed", len(entries), "fonts")
