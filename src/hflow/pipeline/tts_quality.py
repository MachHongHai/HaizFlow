"""Lightweight safeguards for very short local utterances; no model imports."""
import re
import unicodedata

SHORT_PHRASE_VERSION = "omnivoice-short-phrase-v5-legacy-generation-zero-fade"
NUMBER_SPEECH_VERSION = "omnivoice-vi-numbers-v3-legacy-native-text"
VOICE_AUDIO_VERSION = "omnivoice-clean-level-v4-zero-fade-speaker-peer-median"
OMNIVOICE_FADE_DURATION = 0.0

_VI_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")


class SpeechQualityError(RuntimeError):
    """An otherwise decodable waveform is not safe to publish as speech."""


def _vi_triplet(value: int, full: bool = False) -> str:
    hundreds, rest = divmod(value, 100)
    tens, ones = divmod(rest, 10)
    words = []
    if hundreds or full:
        words += [_VI_DIGITS[hundreds], "trăm"]
    if tens >= 2:
        words += [_VI_DIGITS[tens], "mươi"]
    elif tens == 1:
        words.append("mười")
    elif ones and (hundreds or full):
        words.append("lẻ")
    if ones:
        words.append("mốt" if ones == 1 and tens >= 2 else "lăm" if ones == 5 and tens else _VI_DIGITS[ones])
    return " ".join(words)


def _vi_integer(digits: str) -> str:
    if len(digits) > 1 and digits.startswith("0"):
        return " ".join(_VI_DIGITS[int(d)] for d in digits)
    value = int(digits)
    if value == 0:
        return _VI_DIGITS[0]
    groups = []
    while value:
        value, group = divmod(value, 1000)
        groups.append(group)
    words = []
    for index in range(len(groups) - 1, -1, -1):
        if not groups[index]:
            continue
        words.append(_vi_triplet(groups[index], full=bool(words) and groups[index] < 100))
        if index % 3:
            words.append(("", "nghìn", "triệu")[index % 3])
        if index >= 3:
            words.extend(["tỷ"] * (index // 3))
    return " ".join(words)


def spoken_text_for_omnivoice(text: str, language: str) -> str:
    """Expand unambiguous Vietnamese numbers only at the synthesis boundary.

    Subtitles/reference transcripts remain unchanged. Do not reinterpret dates,
    versions, times or embedded identifiers. No online normalization/dependency.
    """
    text = unicodedata.normalize("NFC", str(text or ""))
    if str(language or "").lower() not in {"vi", "vietnamese"}:
        return text

    def expand(match):
        token = match.group()
        prefix = "âm " if token.startswith("-") else ""
        token = token.lstrip("+-")
        integer, _, fraction = token.partition(",")
        digits = integer.replace(".", "")
        if len(digits) > 15 or len(fraction) > 8:
            return match.group()
        result = prefix + _vi_integer(digits)
        if fraction:
            result += " phẩy " + " ".join(_VI_DIGITS[int(d)] for d in fraction)
        if match.start() == 0:
            result = result[0].upper() + result[1:]
        return result

    # A final sentence dot is allowed, but not a dot followed by another digit.
    return re.sub(r"(?<![\w./:,+\-])[-+]?\d+(?:\.\d{3})*(?:,\d+)?(?![\w/:,+\-]|\.\d)", expand, text)


def uses_spoken_number_normalization(text: str, language: str) -> bool:
    return spoken_text_for_omnivoice(text, language) != unicodedata.normalize("NFC", str(text or ""))


def voice_text_policy_versions(text: str, language: str) -> tuple[str, ...]:
    versions = (VOICE_AUDIO_VERSION,)
    if short_phrase_units(text, language):
        versions += (SHORT_PHRASE_VERSION,)
    if uses_spoken_number_normalization(text, language):
        versions += (NUMBER_SPEECH_VERSION,)
    return versions


def short_phrase_units(text: str, language: str) -> int:
    text = unicodedata.normalize("NFC", str(text or ""))
    # Numbers/abbreviations may expand to many spoken syllables. Do not apply
    # a short written-token duration to them while SDK normalization is off.
    if any(character.isdigit() for character in text):
        return 0
    if str(language or "").lower() in {"zh", "chinese"}:
        count = len(re.findall(r"[\u3400-\u9fff]", text))
        return count if 0 < count <= 6 else 0
    if str(language or "").lower() not in {"vi", "vietnamese", "en", "english"}:
        return 0
    words = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", text)
    if any(len(word) > 12 for word in words):
        return 0
    if str(language or "").lower() in {"en", "english"}:
        count = sum(max(1, len(re.findall(r"[aeiouy]+", word.lower()))
                        - int(word.lower().endswith("e") and not word.lower().endswith("le"))) for word in words)
    else:
        count = len(words)
    return count if 0 < count <= 4 else 0


def short_phrase_generation_options(text: str, language: str) -> dict:
    count = short_phrase_units(text, language)
    if not count and not uses_spoken_number_normalization(text, language):
        return {}
    # Do not fit generation to the source slot: the mixer fits full speech
    # afterwards. The SDK's 100 ms edge fades can erase short final consonants.
    # Arbitrary fixed token budgets can collapse the decoder into DC/tones.
    # Preserve the SDK's reference-calibrated duration; only protect the edges.
    return {"fade_duration": OMNIVOICE_FADE_DURATION}


def active_speech_rms(waveform, sample_rate: int) -> float:
    """Measure voiced energy without letting pauses or codec DC set the gain."""
    import numpy as np

    wave = np.asarray(waveform, dtype=np.float32).reshape(-1)
    size = max(1, round(sample_rate * .04))
    frames = wave[:len(wave) // size * size].reshape(-1, size)
    if not len(frames):
        return 0.0
    centered = frames - frames.mean(axis=1, keepdims=True)
    rms = np.sqrt(np.mean(centered ** 2, axis=1))
    active = rms[rms > max(.001, float(rms.max()) * .08)]
    return float(np.sqrt(np.mean(active ** 2))) if len(active) else 0.0


def match_quiet_speech_level(waveform, sample_rate: int, reference_level: float, *, tolerance_db: float = 3.0):
    """Raise clearly quiet generated speech to its own reference, safely.

    One constant gain, no limiter/pumping, time stretch, clipping or new model.
    Do not flatten normal sentence dynamics or amplify near-silent artifacts.
    Validation must run first: no gain is applied to an invalid artifact.
    """
    import numpy as np

    wave = np.asarray(waveform, dtype=np.float32).reshape(-1)
    level = active_speech_rms(wave, sample_rate)
    if not .005 <= level < reference_level / (10 ** (tolerance_db / 20)) or not .005 <= reference_level <= .3:
        return wave
    peak = float(np.max(np.abs(wave))) if len(wave) else 0.0
    gain = min(reference_level / level, 10 ** (9 / 20), 10 ** (-1 / 20) / max(peak, 1e-20))
    return (wave * gain).astype(np.float32) if gain > 1 else wave


def peer_speech_target(levels) -> float:
    """Robust same-speaker target, never a loudest sentence/peak target."""
    import numpy as np
    values = np.asarray(levels,dtype=np.float32)
    values = values[np.isfinite(values) & (values >= .005) & (values <= .3)]
    return float(np.median(values)) if len(values) >= 3 else 0.0


def is_level_reference_text(text: str, language: str) -> bool:
    """Learn from ordinary dialogue, not shouts, numbers or tiny reactions."""
    return (bool(str(text).strip()) and not any(c.isdigit() for c in text)
            and not any(c in text for c in '!！') and not short_phrase_units(text,language))


def validate_speech_waveform(waveform, sample_rate: int) -> None:
    """Reject clear codec collapse (DC/pure sustained tone), not voice timbre.

    Deliberately conservative; this is not a transcript/content verifier. Run on
    decoded speech before MP3/cache publication; FFT cost is tiny vs inference.
    """
    import numpy as np

    wave = np.asarray(waveform, dtype=np.float32).reshape(-1)
    size = max(1, round(sample_rate * .04))
    frames = wave[:len(wave) // size * size].reshape(-1, size)
    if not len(frames):
        raise SpeechQualityError("OmniVoice speech audio is empty.")
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    active = frames[rms > max(.001, float(rms.max()) * .08)]
    if len(active) < 3:
        raise SpeechQualityError("OmniVoice speech audio is silent.")
    power = abs(np.fft.rfft(active * np.hanning(size))) ** 2
    probability = power / np.maximum(power.sum(axis=1, keepdims=True), 1e-20)
    entropy = -(probability * np.log(np.maximum(probability, 1e-20))).sum(axis=1) / np.log(power.shape[1])
    peak_hz = power.argmax(axis=1) * sample_rate / size
    # Use actual DC energy, not the lowest FFT bins: a legitimate deep male
    # fundamental around 50-75 Hz must not be mistaken for codec DC collapse.
    dc = np.mean(active, axis=1) ** 2 / np.maximum(np.mean(active ** 2, axis=1), 1e-20) > .75
    tonal = (entropy < .23) & (peak_hz >= 700)
    if float(np.mean(dc)) >= .80 or (float(np.mean(tonal)) >= .60 and float(np.mean(entropy < .23)) >= .85):
        raise SpeechQualityError("OmniVoice returned a tone/DC artifact instead of speech.")
    # A clip may contain valid words AFTER two codec beeps. Whole-clip RMS/ASR
    # misses this. Detect repeated, nearly pure, same-frequency tone bursts in
    # the first second; a normal harmonic vowel is not a narrow-band beep.
    all_power = abs(np.fft.rfft(frames * np.hanning(size))) ** 2
    all_probability = all_power / np.maximum(all_power.sum(axis=1, keepdims=True), 1e-20)
    peaks = all_power.argmax(axis=1)
    frequencies = peaks * sample_rate / size
    narrow = np.array([row[max(0, peak - 2):peak + 3].sum()
                       for row, peak in zip(all_probability, peaks)])
    ridge = np.array([row[max(0, peak - 3):peak + 4].sum()
                      for row, peak in zip(all_probability, peaks)])
    # Codec tones may have sidebands/harmonics and coexist with perfectly valid
    # words. Detect a stationary, dominant high ridge over >=320ms anywhere,
    # not just low-entropy whole files or repeated pure beeps in the prefix.
    for start in range(max(0, len(frames) - 7)):
        window = slice(start, start + 8)
        if (np.all((frequencies[window] >= 1000) & (frequencies[window] <= 4000))
                and np.ptp(frequencies[window]) <= 50
                and np.all(ridge[window] > .45)
                and np.all(rms[window] > max(.005, float(rms.max()) * .10))):
            raise SpeechQualityError("OmniVoice returned a sustained high-frequency tone, not speech.")
    beep_frames = np.flatnonzero((narrow > .90) & (frequencies >= 400) & (frequencies <= 4000)
                                & (rms > max(.005, float(rms.max()) * .10))
                                & (np.arange(len(frames)) * .04 < 1.0))
    if len(beep_frames) >= 3:
        bursts = np.split(beep_frames, np.flatnonzero(np.diff(beep_frames) > 1) + 1)
        if len(bursts) >= 2 and np.ptp(frequencies[beep_frames]) <= 100:
            raise SpeechQualityError("OmniVoice returned repeated beep artifacts before speech.")


def validate_short_phrase_audio(waveform, text: str, language: str, sample_rate: int) -> None:
    """Reject clear under-generation before encoding/publishing a cached clip.

    This is an acoustic safety floor, NOT an ASR/content correctness guarantee.
    """
    count = short_phrase_units(text, language)
    if not count:
        return
    import numpy as np

    wave = np.asarray(waveform).reshape(-1)
    frame_size = max(1, int(sample_rate * .01))
    samples = wave[:len(wave) // frame_size * frame_size]
    rms = np.sqrt(np.mean(samples.reshape(-1, frame_size) ** 2, axis=1)) if len(samples) else np.asarray([])
    audible = np.flatnonzero(rms > max(.001, float(rms.max()) * .06)) if len(rms) else []
    span = (audible[-1] - audible[0] + 1) * .01 if len(audible) else 0
    # A clearly spoken two-syllable reaction can legitimately last ~240ms.
    # Reject gross under-generation, not natural fast dialogue. Completeness
    # is not inferred from duration alone (see the phoneme/real-ASR fixtures).
    if span < .08 + .08 * count:
        raise SpeechQualityError(f"Short utterance audio is incomplete ({span:.2f}s): {text}")
