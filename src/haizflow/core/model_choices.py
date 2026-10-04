"""Lightweight model/device choices shared by Core, workers and desktop UI."""

RECOGNITION_CHOICES = frozenset({"small", "small-cpu", "small-gpu", "large-v3-turbo"})


def project_recognition_choice(choice: str, app_device: str) -> str:
    """Resolve the old automatic default without replacing explicit choices."""
    if not choice or choice == "small":
        return project_model_defaults(app_device)["_speech_recognition_model"]
    return choice


def project_model_defaults(app_device: str) -> dict[str, str]:
    gpu = app_device == "gpu"
    return {
        # GPU mode is admitted only after the hardware policy's 8 GB-class
        # VRAM check. Turbo is the default; an explicit Small/CPU choice stays
        # project-local and is never overwritten on reopening a project.
        "_speech_recognition_model": "large-v3-turbo" if gpu else "small-cpu",
        "_translation_model": "full" if gpu else "q4",
        "_tts_provider": "omnivoice-gpu" if gpu else "omnivoice",
    }


def models_for_device(app_device: str, *, recognition: str, translation: str, voice: str) -> dict[str, str]:
    """Keep compatible project choices, replacing GPU-only choices in CPU mode."""
    if app_device == "cpu":
        if recognition in {"small-gpu", "large-v3-turbo"}:
            recognition = "small-cpu"
        if translation == "full":
            translation = "q4"
        if voice == "omnivoice-gpu":
            voice = "omnivoice"
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
