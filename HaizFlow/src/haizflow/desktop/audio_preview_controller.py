"""Asynchronous short audio-mix previews for the dubbing setup."""

from __future__ import annotations

import os
import subprocess
import threading
import uuid
from pathlib import Path

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS, RUNTIME_DATA_DIR
from haizflow.pipeline.tts import (
    _run_coroutine,
    preprocess_text_for_tts,
    resolve_tts_provider,
    tts_segment_with_retry,
)
from haizflow.services import video_store
from haizflow.utils.ffmpeg import _binary


class AudioPreviewController:
    """Prepare synchronized, disposable preview tracks without changing checkpoints."""

    _DURATION_SECONDS = 20
    _PREVIEW_TEXT_BY_LANGUAGE = {
        "vi": (
            "Đây là bản nghe thử để bạn cảm nhận giọng đọc trong bản lồng tiếng hoàn chỉnh. "
            "Hãy chú ý cách phát âm, nhịp nói, khoảng nghỉ và độ rõ của từng câu. "
            "Trong lúc đó, âm thanh gốc và nhạc nền vẫn phát phía dưới để bạn điều chỉnh mức âm lượng "
            "một cách tự nhiên, cân bằng và dễ nghe cho toàn bộ video."
        ),
        "zh": "这是一个配音试听，用来感受完整混音中的语音效果。请留意发音、语速、停顿和清晰度，同时原始声音和背景音乐会在下方播放。调整各个音量，直到声音自然、平衡、舒适，并且适合整段视频。",
        "hi": "यह एक डबिंग पूर्वावलोकन है, जिससे आप पूरे मिश्रण में आवाज़ को सुन सकते हैं। उच्चारण, गति, विराम और स्पष्टता पर ध्यान दें, जबकि मूल ध्वनि और पृष्ठभूमि संगीत साथ में चलते रहें। सभी स्तरों को समायोजित करें ताकि आवाज़ स्वाभाविक, संतुलित और पूरे वीडियो के लिए सहज लगे।",
        "es": "Esta es una vista previa del doblaje para escuchar la voz dentro de la mezcla completa. Presta atención a la pronunciación, el ritmo, las pausas y la claridad mientras el sonido original y la música de fondo siguen sonando. Ajusta cada nivel hasta que la voz resulte natural, equilibrada y cómoda durante todo el video.",
        "fr": "Voici un aperçu du doublage pour entendre la voix dans le mixage complet. Écoutez la prononciation, le rythme, les pauses et la clarté pendant que le son d'origine et la musique de fond restent présents. Ajustez chaque niveau afin que la voix paraisse naturelle, équilibrée et agréable tout au long de la vidéo.",
        "ar": "هذه معاينة للدبلجة للاستماع إلى الصوت داخل المزيج الكامل. انتبه إلى النطق والسرعة والتوقفات والوضوح بينما يستمر الصوت الأصلي والموسيقى الخلفية في التشغيل. اضبط المستويات حتى يبدو الصوت طبيعياً ومتوازناً ومريحاً طوال الفيديو.",
        "pt": "Esta é uma prévia da dublagem para ouvir a voz dentro da mixagem completa. Observe a pronúncia, o ritmo, as pausas e a clareza enquanto o áudio original e a música de fundo continuam tocando. Ajuste cada nível até que a voz pareça natural, equilibrada e confortável durante todo o vídeo.",
        "ru": "Это предварительное прослушивание дубляжа, чтобы оценить голос в полном миксе. Обратите внимание на произношение, темп, паузы и разборчивость, пока исходный звук и фоновая музыка продолжают играть. Настройте уровни так, чтобы голос звучал естественно, сбалансированно и комфортно на протяжении всего видео.",
        "id": "Ini adalah pratinjau sulih suara untuk mendengarkan suara dalam campuran lengkap. Perhatikan pelafalan, tempo, jeda, dan kejernihan saat audio asli serta musik latar tetap diputar. Sesuaikan setiap tingkat agar suara terdengar alami, seimbang, dan nyaman sepanjang video.",
        "de": "Dies ist eine Vorschau der Synchronisation, damit Sie die Stimme in der vollständigen Mischung hören können. Achten Sie auf Aussprache, Tempo, Pausen und Klarheit, während Originalton und Hintergrundmusik weiterlaufen. Passen Sie alle Pegel an, bis die Stimme über das gesamte Video natürlich, ausgewogen und angenehm klingt.",
        "ja": "これは完成したミックスの中で吹き替え音声を確認するためのプレビューです。元の音声と背景音楽が流れる間に、発音、話す速さ、間の取り方、聞き取りやすさを確認してください。各音量を調整し、動画全体で自然でバランスのよい聞きやすい声に仕上げます。",
        "ko": "이것은 완성된 믹스에서 더빙 음성을 들어 보기 위한 미리 보기입니다. 원본 소리와 배경 음악이 함께 재생되는 동안 발음, 말의 속도, 쉼과 선명도를 확인하세요. 각 음량을 조절하여 영상 전체에서 목소리가 자연스럽고 균형 잡히며 편안하게 들리도록 만드세요.",
        "it": "Questa è un'anteprima del doppiaggio per ascoltare la voce nel mix completo. Presta attenzione alla pronuncia, al ritmo, alle pause e alla chiarezza mentre l'audio originale e la musica di sottofondo continuano a suonare. Regola ogni livello finché la voce non risulta naturale, equilibrata e piacevole per tutto il video.",
        "th": "นี่คือตัวอย่างเสียงพากย์เพื่อฟังเสียงพูดในมิกซ์ที่สมบูรณ์ โปรดสังเกตการออกเสียง จังหวะ การเว้นวรรค และความชัดเจน ขณะที่เสียงต้นฉบับและเพลงพื้นหลังยังเล่นอยู่ ปรับระดับเสียงแต่ละส่วนจนเสียงพูดเป็นธรรมชาติ สมดุล และฟังสบายตลอดทั้งวิดีโอ",
        "fil": "Ito ay preview ng dubbing upang marinig ang boses sa kumpletong mix. Pakinggan ang pagbigkas, bilis, paghinto at linaw habang tumutugtog ang orihinal na audio at background music. Ayusin ang bawat antas upang maging natural, balanse at komportable ang boses sa buong video.",
        "en": (
            "Use this extended preview to hear how the dubbed voice sounds in a complete mix. "
            "Notice the pronunciation, pace, pauses, and clarity while the original audio and "
            "background music play underneath. Adjust each level until the voice remains natural, "
            "clear, balanced, and comfortable to hear from the beginning to the end of your finished video."
        ),
    }

    def __init__(self, host):
        self._host = host
        self._thread: threading.Thread | None = None
        self._token = ""

    def invalidate(self) -> None:
        """Discard an unfinished preview when its project context changes."""
        self._token = uuid.uuid4().hex
        host = self._host
        host._audio_preview_source = ""
        host._audio_preview_original_source = ""
        host._audio_preview_background_music_source = ""
        host._audio_preview_state = "idle"
        host.audioPreviewChanged.emit()

    def start(
        self,
        *,
        video_id: str | None = None,
        enable_audio_separation: bool | None = None,
        background_music_path: str | None = None,
        original_volume: int | None = None,
        background_music_volume: int | None = None,
        tts_volume: int | None = None,
        voice: str | None = None,
        provider: str | None = None,
        target_language: str | None = None,
    ) -> bool:
        """Build a preview from persisted settings or an unsaved editor draft."""
        if self._thread and self._thread.is_alive():
            return False
        host = self._host
        selected_video_id = video_id if video_id is not None else getattr(host, "_selected_video_id", None)
        video = video_store.get_video(selected_video_id) if selected_video_id else None
        files = dict((video.files if video else {}) or {})
        use_audio_separation = (
            bool(getattr(host, "_enable_audio_separation", False))
            if enable_audio_separation is None else bool(enable_audio_separation)
        )
        source_path = (
            str(files.get("background_audio") or "")
            if video and use_audio_separation and os.path.isfile(str(files.get("background_audio") or ""))
            else str(files.get("video_input") or getattr(host, "_video_path", "") or "")
        )
        if not os.path.isfile(source_path):
            host._status_message = "Choose an input video before previewing the audio mix."
            host.statusMessageChanged.emit()
            return False

        token = uuid.uuid4().hex
        self._token = token
        host._audio_preview_state = "preparing"
        host.audioPreviewChanged.emit()
        effective_target_language = (
            str(target_language or "en")
            if target_language is not None
            else str(getattr(host, "_target_language", "en") or "en")
        )
        snapshot = {
            "token": token,
            "source_path": source_path,
            "background_music_path": str(
                getattr(host, "_background_music_path", "") if background_music_path is None else background_music_path
            ),
            "original_volume": int(
                getattr(host, "_original_volume", 60) if original_volume is None else original_volume
            ),
            "background_music_volume": int(
                getattr(host, "_background_music_volume", 30)
                if background_music_volume is None else background_music_volume
            ),
            "tts_volume": int(getattr(host, "_tts_volume", 100) if tts_volume is None else tts_volume),
            "voice": str(getattr(host, "_tts_voice", "") if voice is None else voice),
            "provider": str(
                getattr(host, "_tts_provider", "vieneu") if provider is None else provider
            ),
            "target_language": effective_target_language,
            "directory": video_store.get_video_dir(video.video_id) if video else str(RUNTIME_DATA_DIR),
        }
        self._thread = threading.Thread(
            target=self._build_preview,
            args=(snapshot,),
            name="haizflow-audio-preview",
            daemon=True,
        )
        self._thread.start()
        return True

    def _build_preview(self, snapshot: dict) -> None:
        token = snapshot["token"]
        preview_dir = Path(snapshot["directory"]) / "temp" / "audio_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        voice_path = preview_dir / f"voice-{token}.mp3"
        source_output_path = preview_dir / f"source-{token}.m4a"
        music_output_path = preview_dir / f"music-{token}.m4a"
        try:
            preview_text = self._preview_text(snapshot["target_language"])
            effective_provider = resolve_tts_provider(
                snapshot["provider"], snapshot["target_language"]
            )
            if effective_provider == "vieneu":
                from haizflow.pipeline.vieneu_tts import synthesize_to_mp3

                synthesize_to_mp3(
                    preprocess_text_for_tts(preview_text),
                    snapshot["voice"],
                    str(voice_path),
                    f"audio-preview-{token}",
                )
            else:
                _run_coroutine(
                    tts_segment_with_retry(
                        preview_text,
                        snapshot["voice"],
                        str(voice_path),
                        retries=2,
                    )
                )
            self._encode_track(snapshot["source_path"], source_output_path)
            music_path = ""
            if snapshot["background_music_path"] and os.path.isfile(snapshot["background_music_path"]):
                self._encode_track(snapshot["background_music_path"], music_output_path, loop=True)
                music_path = str(music_output_path)
            self._remove_stale_preview_files(preview_dir, {voice_path, source_output_path, music_output_path})
            self._host._audio_preview_events.put(
                ("ready", token, {
                    "source": str(source_output_path),
                    "voice": str(voice_path),
                    "music": music_path,
                })
            )
        except Exception as exc:
            self._host._audio_preview_events.put(("error", token, str(exc)))

    @classmethod
    def _preview_text(cls, target_language: str) -> str:
        return cls._PREVIEW_TEXT_BY_LANGUAGE.get(str(target_language or "").lower(), cls._PREVIEW_TEXT_BY_LANGUAGE["en"])

    @staticmethod
    def _remove_stale_preview_files(preview_dir: Path, keep_paths: set[Path]) -> None:
        """Keep one preview generation; all files here are controller-owned temporaries."""
        retained = {path.resolve() for path in keep_paths}
        for prefix in ("voice-", "source-", "music-"):
            for candidate in preview_dir.glob(f"{prefix}*"):
                if candidate.resolve() in retained or not candidate.is_file():
                    continue
                try:
                    candidate.unlink()
                except OSError:
                    pass

    def _encode_track(self, input_path: str, output_path: Path, *, loop: bool = False) -> None:
        command = [_binary("ffmpeg"), "-y", "-v", "error"]
        if loop:
            command.extend(["-stream_loop", "-1"])
        command.extend([
            "-i", input_path,
            "-t", str(self._DURATION_SECONDS),
            "-vn", "-map", "0:a:0?",
            "-ac", "2", "-ar", "44100", "-c:a", "aac", str(output_path),
        ])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=MEDIA_PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 0:
            detail = (result.stderr or "FFmpeg could not prepare an audio preview track.").strip()
            raise RuntimeError(detail[:400])

    def drain_events(self) -> None:
        host = self._host
        while True:
            try:
                kind, token, value = host._audio_preview_events.get_nowait()
            except Exception:
                return
            if token != self._token:
                continue
            if kind == "ready":
                host._audio_preview_source = Path(value["voice"]).resolve().as_uri()
                host._audio_preview_original_source = Path(value["source"]).resolve().as_uri()
                host._audio_preview_background_music_source = (
                    Path(value["music"]).resolve().as_uri() if value["music"] else ""
                )
                host._audio_preview_state = "ready"
                host._status_message = "Audio mix preview is ready."
            else:
                host._audio_preview_state = "failed"
                host._status_message = f"Could not prepare audio preview: {value}"
            host.statusMessageChanged.emit()
            host.audioPreviewChanged.emit()
