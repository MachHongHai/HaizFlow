"""Native preset identifiers from the pinned VieNeu 3.8.3 voice bank."""

import re
import unicodedata

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
