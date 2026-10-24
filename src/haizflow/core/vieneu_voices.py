"""Native preset identifiers from the pinned VieNeu 3.8.3 voice bank."""

import re
import unicodedata

_HAN_TEXT = re.compile(
    r"[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\U00020000-\U0002ee5f\U0002f800-\U0002fa1f\U00030000-\U0003347f]{1,12}"
)


def han_text_notice(segments, ui_language="vi", *, imported=False):
    """Reject any Han text before model loading; do not guess a majority language."""
    examples = []
    for position, segment in enumerate(segments, 1):
        if not isinstance(segment, dict):
            continue
        match = _HAN_TEXT.search(str(segment.get("text") or ""))
        if match:
            try:
                index = max(1, int(segment.get("index", position)))
            except (TypeError, ValueError):
                index = position
            examples.append((index, match.group()))
            if len(examples) == 3:
                break
    if not examples:
        return None
    locations = "; ".join(f'{index}: “{text}”' for index, text in examples)
    if ui_language == "vi":
        title = "SRT có chứa chữ Hán" if imported else "Phụ đề có chứa chữ Hán"
        source = "Phụ đề từ SRT" if imported else "Phụ đề"
        return title, (
            f"{source} còn chữ Hán, ví dụ ở câu {locations}. "
            "Không thể tạo giọng VieNeu khi còn chữ Hán, kể cả tên riêng. "
            "VieNeu hỗ trợ tiếng Việt nhưng không hỗ trợ đọc tiếng Trung. "
            "Hãy sửa/dịch hoặc phiên âm phần chữ Hán sang tiếng Việt trong Phụ đề, hoặc chọn OmniVoice/Edge TTS. "
            + ("Chọn ngôn ngữ Tiếng Việt không tự dịch nội dung SRT." if imported else "")
        ).strip()
    title = "Imported SRT contains Han characters" if imported else "Subtitles contain Han characters"
    source = "The imported captions" if imported else "The subtitles"
    return title, (
        f"{source} contain Han characters, for example in cue {locations}. "
        "VieNeu speech generation is blocked while any Han characters remain, including in names. "
        "VieNeu supports Vietnamese but not Chinese speech. Edit/translate or transliterate these parts "
        "into Vietnamese in Subtitles, or choose OmniVoice/Edge TTS. "
        + ("Selecting Vietnamese does not translate the SRT." if imported else "")
    ).strip()


VIENEU_VOICES = (
    ("Hải Đăng", "male", "Bắc"), ("Trúc Ly", "female", "Bắc"),
    ("Thiện Minh", "male", "Bắc"), ("Mai Anh", "female", "Bắc"),
    ("Thùy Dung", "female", "Nam"), ("Thiền Tâm Đức", "male", "Bắc"),
    ("Ngọc Huyền", "female", "Bắc"), ("Quang Sơn", "male", "Trung"),
    ("Ngọc Trân", "female", "Trung"), ("Minh Đức", "male", "Bắc"),
    ("Phạm Tuyên", "male", "Bắc"), ("Thái Sơn", "male", "Nam"),
    ("Xuân Vĩnh", "male", "Bắc"), ("Thanh Bình", "male", "Bắc"),
    ("Ngọc Linh", "female", "Bắc"), ("Đoan Trang", "female", "Bắc"),
    ("Thục Đoan", "female", "Nam"), ("Minh Triết", "male", "Nam"),
    ("Mỹ Duyên", "female", "Nam"), ("Quỳnh Anh", "female", "Bắc"),
    ("Đức Trí", "male", "Nam"), ("Kim Thanh", "female", "Nam"),
    ("Adam", "male", "Nam"), ("Quốc Tuấn", "male", "Bắc"),
    ("Adam bựa", "male", "Bắc"),
)


def native_voice(voice: str) -> str:
    name = str(voice or "").removeprefix("vieneu:")
    if name not in {item[0] for item in VIENEU_VOICES}:
        raise ValueError(f"Giọng VieNeu không hợp lệ: {voice}")
    return name


def unsupported_language_notice(provider: str, language: str, ui_language: str = "vi") -> tuple[str, str] | None:
    """Chinese is unsupported; English/Vietnamese remain user-selectable."""
    if not str(provider).strip().lower().startswith("vieneu") or str(language).lower() not in {"zh", "chinese", "zh-cn", "zh-tw"}:
        return None
    if ui_language == "vi":
        label = {"zh": "tiếng Trung", "en": "tiếng Anh"}.get(language, "ngôn ngữ đã chọn")
        return "Ngôn ngữ chưa hỗ trợ", (
            f"VieNeu CPU/GPU không hỗ trợ giọng đọc {label}. "
            "Hãy chọn OmniVoice hoặc Edge TTS."
        )
    label = {"zh": "Chinese", "en": "English"}.get(language, "the selected language")
    return "Unsupported voice language", (
        f"VieNeu CPU/GPU does not support {label} speech. "
        "Choose OmniVoice or Edge TTS."
    )


def sample_voice_id(voice: str) -> str:
    """Stable ASCII asset name; preserve every native Vietnamese preset name."""
    name = native_voice(voice).replace("đ", "d").replace("Đ", "D")
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return "vieneu_" + re.sub(r"[^a-zA-Z0-9._-]+", "_", ascii_name).strip("_")


def speaker_voice(voice: str) -> str:
    """Translate identified target presets, never the default narrator choice."""
    if str(voice).startswith("vieneu:"):
        return "vieneu:" + native_voice(voice)
    code = str(voice).removeprefix("omnivoice:")
    male = code.startswith("male") or code in {"deep", "boy", "boy_bright", "elder_narrator", "storyteller"}
    return "vieneu:Hải Đăng" if male else "vieneu:Trúc Ly"
