"""Lightweight model/device choices shared by Core, workers and desktop UI."""

RECOGNITION_CHOICES = frozenset({"small", "small-cpu", "small-gpu", "large-v3-turbo"})
_FOUR_GB_GPU_LIMIT_BYTES = 5 * 1024**3
_LEGACY_AUTO_FULL_VRAM_BYTES = 12 * 1024**3


def project_recognition_choice(choice: str, app_device: str, *, total_vram_bytes: int | None = None) -> str:
    """Resolve the old automatic default without replacing explicit choices."""
    if not choice or choice == "small":
        return project_model_defaults(app_device, total_vram_bytes=total_vram_bytes)["_speech_recognition_model"]
    return choice


def project_model_defaults(app_device: str, *, total_vram_bytes: int | None = None,
                           target_language: str = "vi") -> dict[str, str]:
    gpu = app_device == "gpu"
    small_gpu = gpu and total_vram_bytes is not None and total_vram_bytes < _FOUR_GB_GPU_LIMIT_BYTES
    return {
        # Keep the established defaults on larger GPUs. On a 4 GB card,
        # Whisper Small and voice synthesis run sequentially on CUDA; translation
        # uses its smaller CPU pack so the full GPU weights never overlap.
        "_speech_recognition_model": "small-gpu" if small_gpu else "large-v3-turbo" if gpu else "small-cpu",
        "_translation_model": "q4" if small_gpu or not gpu else "full",
        "_tts_provider": (("vieneu-gpu" if gpu else "vieneu") if target_language == "vi"
                          else "omnivoice-gpu" if gpu else "omnivoice"),
    }


def default_tts_voice(provider: str) -> str:
    return "vieneu:Hải Đăng" if str(provider).startswith("vieneu") else "omnivoice:female"


def project_translation_choice(choice: str, app_device: str, *, total_vram_bytes: int | None = None) -> str:
    """Resolve saved pre-picker 'auto' to one of the two visible local models."""
    if str(choice or "auto").lower() != "auto":
        return choice
    return "full" if app_device == "gpu" and isinstance(total_vram_bytes, int) \
        and total_vram_bytes >= _LEGACY_AUTO_FULL_VRAM_BYTES else "q4"


def heavy_gpu_choice_blocked(app_device: str, capabilities, *, recognition: str = "", translation: str = "") -> bool:
    return bool(app_device == "gpu" and capabilities is not None
                and getattr(capabilities, "gpu_supported", False)
                and not getattr(capabilities, "heavy_gpu_models_supported", False)
                and (recognition == "large-v3-turbo" or translation == "full"))


def models_for_device(app_device: str, *, recognition: str, translation: str, voice: str,
                      total_vram_bytes: int | None = None) -> dict[str, str]:
    """Keep compatible project choices, replacing GPU-only choices in CPU mode."""
    translation = project_translation_choice(translation, app_device, total_vram_bytes=total_vram_bytes)
    if app_device == "cpu":
        if recognition in {"small-gpu", "large-v3-turbo"}:
            recognition = "small-cpu"
        if translation == "full":
            translation = "q4"
        if voice == "omnivoice-gpu":
            voice = "omnivoice"
        elif voice == "vieneu-gpu":
            voice = "vieneu"
    return {"speech_recognition_model": recognition, "translation_model": translation, "tts_provider": voice}


def recognition_context(choice: str, app_device: str) -> dict[str, str]:
    choice = str(choice or "small").lower()
    device = "gpu" if app_device == "gpu" else "cpu"
    if choice not in RECOGNITION_CHOICES:
        raise ValueError(f"Unsupported recognition model: {choice}")
    if choice == "small-cpu":
        device = "cpu"
    elif choice in {"small-gpu", "large-v3-turbo"}:
        if device != "gpu":
            raise ValueError("Đang dùng chế độ CPU. Chọn model CPU hoặc chuyển sang GPU trong Cài đặt → Chung.")
    return {"model": "large-v3-turbo" if choice == "large-v3-turbo" else "small", "device": device}


def gpu_choice_blocked(app_device: str, *, recognition="small", translation="auto", voice="omnivoice") -> bool:
    return app_device != "gpu" and (
        recognition in {"small-gpu", "large-v3-turbo"}
        or translation == "full" or str(voice).endswith("-gpu")
    )
