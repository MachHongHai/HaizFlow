"""Small, offline catalog for the app's supported Edge output languages."""

EDGE_VOICES = {
    "vi": (("vi-VN-HoaiMyNeural", "Hoài My · Nữ", "Hoai My · Female"),
           ("vi-VN-NamMinhNeural", "Nam Minh · Nam", "Nam Minh · Male")),
    "en": (("en-US-JennyNeural", "Jenny · Nữ", "Jenny · Female"),
           ("en-US-GuyNeural", "Guy · Nam", "Guy · Male")),
    "zh": (("zh-CN-XiaoxiaoNeural", "Xiaoxiao · Nữ", "Xiaoxiao · Female"),
           ("zh-CN-YunxiNeural", "Yunxi · Nam", "Yunxi · Male")),
}


def edge_voice(voice: str, language: str) -> str:
    choices = EDGE_VOICES.get(str(language or "").lower())
    if not choices:
        raise ValueError("Edge TTS chưa hỗ trợ ngôn ngữ đích này trong HFlow.")
    if voice not in {item[0] for item in choices}:
        raise ValueError("Chọn giọng Edge TTS phù hợp với ngôn ngữ đích.")
    return voice
