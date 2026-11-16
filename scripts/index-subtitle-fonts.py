"""Index unmodified, pinned font assets; fontTools is development-only."""
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1] / "src/haizflow/assets/fonts"
FONTS = {
    "Archivo Black": ("ArchivoBlack-Regular.ttf", "Archivo Black", 900),
    "Barlow": ("Barlow-Bold.ttf", "Barlow", 700),
    "Fira Sans": ("FiraSans-Bold.ttf", "Fira Sans", 700),
    "Saira Condensed": ("SairaCondensed-Bold.ttf", "Saira Condensed", 700),
    "Chakra Petch": ("ChakraPetch-Bold.ttf", "Chakra Petch", 700),
    "Kanit": ("Kanit-SemiBold.ttf", "Kanit", 600),
    "Sarabun": ("Sarabun-Bold.ttf", "Sarabun", 700),
    "Bungee": ("Bungee-Regular.ttf", "Bungee", 400),
    "Pacifico": ("Pacifico-Regular.ttf", "Pacifico", 400),
    "Patrick Hand": ("PatrickHand-Regular.ttf", "Patrick Hand", 400),
    "Amatic SC": ("AmaticSC-Bold.ttf", "Amatic SC", 700),
    "Itim": ("Itim-Regular.ttf", "Itim", 400),
    "Noto Serif SC Bold": ("NotoSerifSC-Bold.otf", "Noto Serif SC", 700),
    "Noto Serif TC Bold": ("NotoSerifTC-Bold.otf", "Noto Serif TC", 700),
    "Noto Serif JP Bold": ("NotoSerifJP-Bold.otf", "Noto Serif JP", 700),
    "Noto Serif KR Bold": ("NotoSerifKR-Bold.otf", "Noto Serif KR", 700),
    "Bangers": ("Bangers-Regular.ttf", "Bangers", 400),
    "Be Vietnam Pro": ("BeVietnamPro-Bold.ttf", "Be Vietnam Pro", 700),
    "Anton": ("Anton-Regular.ttf", "Anton", 400),
    "Barlow Condensed": ("BarlowCondensed-SemiBold.ttf", "Barlow Condensed", 600),
    "Lato": ("Lato-Bold.ttf", "Lato", 700),
    "Lobster": ("Lobster-Regular.ttf", "Lobster", 400),
    "Bree Serif": ("BreeSerif-Regular.ttf", "Bree Serif", 400),
    "Maitree": ("Maitree-Bold.ttf", "Maitree", 700),
    "Judson": ("Judson-Bold.ttf", "Judson", 700),
    "Noto Sans SC Black": ("NotoSansSC-Black.otf", "Noto Sans SC", 900),
    "Noto Sans TC Black": ("NotoSansTC-Black.otf", "Noto Sans TC", 900),
    "Noto Sans JP Black": ("NotoSansJP-Black.otf", "Noto Sans JP", 900),
    "Noto Sans KR Black": ("NotoSansKR-Black.otf", "Noto Sans KR", 900),
    "Dela Gothic One": ("DelaGothicOne-Regular.ttf", "Dela Gothic One", 400),
    "Pretendard ExtraBold": ("Pretendard-ExtraBold.otf", "Pretendard", 800),
    "Black Han Sans": ("BlackHanSans-Regular.ttf", "Black Han Sans", 400),
    "Jua": ("Jua-Regular.ttf", "Jua", 400),
    "Do Hyeon": ("DoHyeon-Regular.ttf", "Do Hyeon", 400),
    "Gowun Dodum": ("GowunDodum-Regular.ttf", "Gowun Dodum", 400),
    "Gowun Batang": ("GowunBatang-Bold.ttf", "Gowun Batang", 700),
    "Sunflower": ("Sunflower-Bold.ttf", "Sunflower", 700),
    "Gugi": ("Gugi-Regular.ttf", "Gugi", 400),
    "Gaegu": ("Gaegu-Bold.ttf", "Gaegu", 700),
    "Zen Maru Gothic": ("ZenMaruGothic-Black.ttf", "Zen Maru Gothic", 900),
    "Zen Kaku Gothic New": ("ZenKakuGothicNew-Black.ttf", "Zen Kaku Gothic New", 900),
    "Yusei Magic": ("YuseiMagic-Regular.ttf", "Yusei Magic", 400),
    "Reggae One": ("ReggaeOne-Regular.ttf", "Reggae One", 400),
    "Klee One": ("KleeOne-SemiBold.ttf", "Klee One", 600),
    "Hachi Maru Pop": ("HachiMaruPop-Regular.ttf", "Hachi Maru Pop", 400),
    "RocknRoll One": ("RocknRollOne-Regular.ttf", "RocknRoll One", 400),
    "ZCOOL KuaiLe": ("ZCOOLKuaiLe-Regular.ttf", "ZCOOL KuaiLe", 400),
    "Zhi Mang Xing": ("ZhiMangXing-Regular.ttf", "Zhi Mang Xing", 400),
    "Ma Shan Zheng": ("MaShanZheng-Regular.ttf", "Ma Shan Zheng", 400),
    "ZCOOL QingKe HuangYou": ("ZCOOLQingKeHuangYou-Regular.ttf", "ZCOOL QingKe HuangYou", 400),
    "Iansui": ("Iansui-Regular.ttf", "Iansui", 400),
    "LXGW WenKai TC": ("LXGWWenKaiTC-Bold.ttf", "LXGW WenKai TC", 700),
    "Huninn": ("Huninn-Regular.ttf", "Huninn", 400),
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
                           ass_family=(font["name"].getName(1, 3, 1, 1033).toUnicode()
                                       if font["name"].getName(1, 3, 1, 1033)
                                       else font["name"].getDebugName(1)),
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           bytes=path.stat().st_size, coverage=ranges,
                           copyright=font["name"].getDebugName(0))
(ROOT.parent / "subtitle-fonts.json").write_text(json.dumps({"version": 1, "fonts": entries},
                                                    ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
print("Indexed", len(entries), "fonts")
