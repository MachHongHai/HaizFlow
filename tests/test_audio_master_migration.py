import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from haizflow.pipeline import process_video


def test_normal_demucs_stem_is_not_treated_as_a_legacy_master():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "temp").mkdir()
        source = root / "temp" / "audio.wav"
        stem = root / "no_vocals.wav"
        for path, rate in ((source, 48000), (stem, 44100)):
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(rate)
                audio.writeframes(b"\0" * 400)
        video = SimpleNamespace(enable_audio_separation=True, video_id="v", files={"background_audio": str(stem)})
        with (
            mock.patch.object(process_video, "extract_audio") as extract,
            mock.patch.object(process_video, "separate_audio") as separate,
            mock.patch.object(process_video, "_resolve_audio_mix", return_value=(str(stem), 60)),
        ):
            assert process_video._prepare_audio_mix(video, None, str(root), str(stem)) == (str(stem), 60)
        extract.assert_not_called()
        separate.assert_not_called()
