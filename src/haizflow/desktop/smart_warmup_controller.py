"""Predictive, low-priority model warm-up that never owns the UI thread."""

from __future__ import annotations

import heapq
import queue
import threading
import time
from dataclasses import dataclass, field

from haizflow.core.hardware import available_memory_bytes, runtime_profile
from haizflow.services.external_engine import close_shared_external_engine_pool, shared_external_engine_pool


@dataclass(order=True)
class _WarmRequest:
    priority: int
    sequence: int
    capability: str = field(compare=False)
    context: dict = field(compare=False, default_factory=dict)


class SmartWarmupController:
    """Keep likely next models resident while foreground work stays dominant."""

    def __init__(self, host, resource_manager):
        self._host = host
        self._resource_manager = resource_manager
        self._condition = threading.Condition()
        self._requests: list[_WarmRequest] = []
        self._sequence = 0
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._started = False
        self._suspended = False
        self._resident: set[str] = set()
        self._resident_since: dict[str, float] = {}
        self._resident_contexts: dict[str, dict] = {}
        self._events: queue.Queue[dict] = queue.Queue()
        self._active_capability = ""
        self._active_context: dict = {}
        self._external_engines = shared_external_engine_pool(resource_manager)

    def _renew_external_pool(self) -> None:
        self._external_engines = shared_external_engine_pool(self._resource_manager)

    @property
    def resident(self) -> tuple[str, ...]:
        with self._condition:
            return tuple(sorted(self._resident))

    def start(self) -> None:
        if self._started or self._stopping or not bool(getattr(self._host, "_keep_models_warm", True)):
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, name="haizflow-smart-warmup", daemon=True)
        self._thread.start()
        self.request_startup_prediction()

    def request_startup_prediction(self) -> None:
        device = str(getattr(self._host, "_settings_processing_device", "cpu") or "cpu")
        model = str(getattr(self._host, "_speech_recognition_model", "small") or "small")
        # Recognition is the first expensive action in both automatic and
        # manual translation flows. Translation follows at a lower priority.
        self.request("recognition", {"device": device, "model": model}, priority=30)
        self.request("translation", {"device": device}, priority=40)

    def request_project_prediction(self) -> None:
        video = self._host._selected_video()
        if video is None:
            return
        context = {
            "device": str(getattr(self._host, "_settings_processing_device", "cpu") or "cpu"),
            "model": str(getattr(video, "speech_recognition_model", "small") or "small"),
            "source_language": str(getattr(video, "source_language", "auto") or "auto"),
            "language": str(getattr(video, "target_language", "") or ""),
            "provider": str(getattr(video, "tts_provider", "omnivoice") or "omnivoice"),
        }
        last_tool = str(getattr(video, "manual_target_tool", "") or "")
        predicted = {
            "translation": ("recognition", "translation"),
            "voice": ("voice",),
            "source": ("separation",),
            "image": ("ocr",),
        }.get(last_tool, ("recognition", "translation"))
        for offset, capability in enumerate(predicted):
            self.request(capability, context, priority=10 + offset)

    def request(self, capability: str, context: dict | None = None, *, priority: int = 20) -> None:
        if self._stopping or self._suspended or not bool(getattr(self._host, "_keep_models_warm", True)):
            return
        capability = str(capability or "").strip().lower()
        if capability not in {"recognition", "translation", "voice", "separation", "ocr"}:
            return
        context = dict(context or {})
        with self._condition:
            self._sequence += 1
            self._requests = [request for request in self._requests if request.capability != capability]
            heapq.heapify(self._requests)
            heapq.heappush(self._requests, _WarmRequest(int(priority), self._sequence, capability, context))
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            request = None
            with self._condition:
                if not self._requests and not self._stopping:
                    self._condition.wait(timeout=1.0)
                if self._stopping:
                    return
                if self._requests:
                    request = heapq.heappop(self._requests)
            if request is None:
                self._expire_idle_residents()
                continue
            while self._host._processing_queue.has_work and not self._stopping:
                time.sleep(0.1)
            if self._stopping:
                return
            missing = self._resource_manager.missing_packs(request.capability, request.context)
            if missing:
                self._events.put(
                    {
                        "state": "missing",
                        "capability": request.capability,
                        "detail": "Thiếu gói tài nguyên",
                        "missing": missing,
                    }
                )
                continue
            try:
                with self._condition:
                    self._active_capability = request.capability
                    self._active_context = dict(request.context)
                self._events.put(
                    {
                        "state": "warming",
                        "capability": request.capability,
                        "detail": self._warming_label(request.capability),
                    }
                )
                self._enforce_resident_budget(request.capability)
                self._warm(request.capability, request.context)
                with self._condition:
                    self._resident.add(request.capability)
                    self._resident_since[request.capability] = time.monotonic()
                    self._resident_contexts[request.capability] = dict(request.context)
                self._events.put(
                    {
                        "state": "ready",
                        "capability": request.capability,
                        "detail": self._ready_label(request.capability),
                    }
                )
            except Exception as exc:
                self._events.put(
                    {
                        "state": "failed",
                        "capability": request.capability,
                        "detail": str(exc),
                    }
                )
            finally:
                with self._condition:
                    self._active_capability = ""
                    self._active_context = {}
                    self._condition.notify_all()

    @staticmethod
    def _warming_label(capability: str) -> str:
        return {
            "recognition": "Đang chuẩn bị Whisper",
            "translation": "Đang chuẩn bị HY-MT2",
            "voice": "Đang chuẩn bị OmniVoice",
            "separation": "Đang chuẩn bị Demucs",
            "ocr": "Đang chuẩn bị OCR",
        }[capability]

    @staticmethod
    def _ready_label(capability: str) -> str:
        return {
            "recognition": "Whisper đã sẵn sàng",
            "translation": "HY-MT2 đã sẵn sàng",
            "voice": "OmniVoice đã sẵn sàng",
            "separation": "Demucs đã sẵn sàng",
            "ocr": "OCR đã sẵn sàng",
        }[capability]

    def _enforce_resident_budget(self, next_capability: str) -> None:
        profile = runtime_profile()
        total_ram_gib = profile.total_ram_gib or 16
        total_vram_gib = profile.total_vram_gib
        constrained = total_ram_gib < 24 or (profile.cuda_available and total_vram_gib < 12)
        if not constrained:
            return
        if next_capability == "recognition" and "translation" in self._resident:
            self._release_now("memory-pressure", {"translation"})
        elif next_capability == "translation" and "recognition" in self._resident:
            self._release_now("memory-pressure", {"recognition"})

    def _idle_timeout(self, capability: str) -> float | None:
        video = self._host._selected_video()
        selected_tool = str(getattr(video, "manual_target_tool", "") or "") if video is not None else ""
        if capability == "voice":
            return 300.0 if selected_tool == "voice" else 90.0
        if capability == "translation":
            profile = runtime_profile()
            if profile.total_ram_gib >= 24 and selected_tool in {"translation", "recognition"}:
                return None
            return 300.0
        if capability == "recognition":
            return 300.0
        return 90.0

    def _expire_idle_residents(self) -> None:
        if self._host._processing_queue.has_work:
            return
        profile = runtime_profile()
        available = available_memory_bytes()
        total = int(profile.total_ram_bytes or 0)
        if self._resident and available and (
            available < 3 * 1024**3 or (total > 0 and available / total < 0.15)
        ):
            self._release_now("memory-pressure")
            return
        now = time.monotonic()
        with self._condition:
            expired = {
                capability
                for capability, loaded_at in self._resident_since.items()
                if (timeout := self._idle_timeout(capability)) is not None and now - loaded_at >= timeout
            }
        if expired:
            self._release_now("idle", expired)

    def _warm(self, capability: str, context: dict) -> None:
        # Frozen Core never imports Torch/ONNX. Installed packs are warmed by
        # their versioned engine process; source/legacy bundled runtimes retain
        # the direct path for development and migration.
        # Translation and OmniVoice already expose persistent Core-side
        # clients whose commands resolve to the external engine. Warm those
        # exact servers so the foreground request reuses the loaded model.
        if capability == "translation":
            from haizflow.services.translation import warm_hymt2_worker

            warm_hymt2_worker()
            return
        if capability == "voice":
            from haizflow.pipeline.omnivoice_tts import warm_runtime

            warm_runtime(str(context.get("language") or "vi"))
            return
        if self._external_engines.warm(capability, context):
            return
        if capability == "recognition":
            from haizflow.pipeline.transcribe import warm_whisperx_model

            requested = str(context.get("model") or "small")
            model = "large-v3-turbo" if requested in {"large-v3-turbo", "turbo"} else "small"
            warm_whisperx_model(model)
        elif capability == "separation":
            # Importing inside this worker initializes the installed engine and
            # keeps the UI process free of Torch startup work.
            import haizflow.pipeline.audio_separation  # noqa: F401, PLC0415
        elif capability == "ocr":
            import haizflow.pipeline.subtitle_ocr  # noqa: F401, PLC0415

    def _release_now(self, reason: str = "idle", capabilities: set[str] | None = None) -> None:
        with self._condition:
            residents = set(self._resident if capabilities is None else self._resident.intersection(capabilities))
            self._resident.difference_update(residents)
            for capability in residents:
                self._resident_since.pop(capability, None)
                self._resident_contexts.pop(capability, None)
        if not residents:
            return
        external_residents = self._external_engines.release(residents)
        bundled_residents = residents.difference(external_residents)
        if "translation" in bundled_residents:
            from haizflow.services.translation import shutdown_hymt2_worker

            shutdown_hymt2_worker()
        if "recognition" in bundled_residents:
            from haizflow.pipeline.transcribe import release_warm_whisperx_model

            release_warm_whisperx_model()
        if "voice" in bundled_residents:
            from haizflow.pipeline.omnivoice_tts import clear_runtime

            clear_runtime()
        self._events.put(
            {
                "state": "released",
                "capability": "",
                "detail": "Đã giải phóng model để giảm bộ nhớ",
                "reason": reason,
            }
        )

    def release(self, reason: str = "idle", capabilities: set[str] | None = None) -> None:
        """Release without ever blocking Settings or navigation."""
        threading.Thread(
            target=self._release_now,
            args=(str(reason or "idle"), capabilities),
            name="haizflow-warmup-release",
            daemon=True,
        ).start()

    def pack_in_use(self, pack_id: str) -> bool:
        """Return whether speculative warm-up currently owns this pack."""

        with self._condition:
            contexts = dict(self._resident_contexts)
            if self._active_capability:
                contexts[self._active_capability] = dict(self._active_context)
        return any(
            str(pack_id) in self._resource_manager.required_packs(capability, context)
            for capability, context in contexts.items()
        )

    def close_idle_pack(self, pack_id: str) -> None:
        """Close a resident-free engine process before deleting its files."""

        self._external_engines.close_pack(str(pack_id))

    def _preempt_active_warm(self, capability: str) -> bool:
        """Stop a speculative load without waiting for its inference lock."""

        if self._external_engines.preempt(capability):
            return True
        if capability == "translation":
            from haizflow.services.translation import shutdown_hymt2_worker

            shutdown_hymt2_worker()
            return True
        if capability == "voice":
            from haizflow.pipeline.omnivoice_tts import clear_runtime

            clear_runtime()
            return True
        return False

    def foreground_work_requested(self, required_capabilities: set[str] | None = None) -> None:
        """Keep useful residents and discard only work predicted for another tool."""
        required = {str(item) for item in (required_capabilities or set()) if item}
        with self._condition:
            self._requests.clear()
            active = self._active_capability
            wrong_residents = self._resident.difference(required)
            for capability in self._resident.intersection(required):
                self._resident_since[capability] = time.monotonic()
        # Releasing a model that the foreground command is about to use would
        # erase the latency benefit of warm-up. Only speculative residents are
        # retired. An in-flight warm for the same capability is allowed to
        # finish and the foreground operation reuses it.
        if wrong_residents:
            self.release("foreground", wrong_residents)
        if active and active not in required:
            # External engines can be terminated immediately even while their
            # synchronous warm RPC is running. Bundled development runtimes
            # finish their current import/load and are released afterwards.
            if not self._preempt_active_warm(active):
                self.release("foreground", {active})

    def suspend_for_storage_move(self) -> None:
        """Quiesce warm workers before resource files move to another drive."""
        with self._condition:
            self._suspended = True
            self._requests.clear()
            active = self._active_capability
        # An external speculative load is safe to terminate immediately. Do
        # this before waiting so moving resources never appears frozen for the
        # whole 30-second safety timeout.
        if active:
            self._preempt_active_warm(active)
        with self._condition:
            deadline = time.monotonic() + 30.0
            while self._active_capability and time.monotonic() < deadline:
                self._condition.wait(timeout=0.25)
            if self._active_capability:
                raise RuntimeError("Không thể dừng model đang chuẩn bị; chưa chuyển vị trí tài nguyên.")
        self._release_now("storage-move")
        close_shared_external_engine_pool()

    def quiesce_for_device_switch(self, timeout_seconds: float = 5.0) -> None:
        """Stop speculative work before selecting another compute engine."""

        with self._condition:
            self._requests.clear()
            active = self._active_capability
        if active:
            self._preempt_active_warm(active)
        deadline = time.monotonic() + max(0.5, float(timeout_seconds))
        with self._condition:
            while self._active_capability and time.monotonic() < deadline:
                self._condition.wait(timeout=0.1)
            if self._active_capability:
                raise RuntimeError("Model đang được sử dụng; chưa thể đổi bộ xử lý.")
        self._release_now("device-switch")
        close_shared_external_engine_pool()
        self._renew_external_pool()

    def resume_after_storage_move(self) -> None:
        self._renew_external_pool()
        with self._condition:
            self._suspended = False
        if bool(getattr(self._host, "_keep_models_warm", True)) and not self._stopping:
            self.request_project_prediction()

    def drain_events(self) -> None:
        changed = False
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            changed = True
            self._host._warmup_state = event["state"]
            self._host._warmup_capability = event["capability"]
            self._host._warmup_detail = event["detail"]
            if event["state"] in {"warming", "ready", "released"}:
                self._host._status_message = event["detail"]
                self._host.statusMessageChanged.emit()
        if changed:
            self._host.warmupChanged.emit()

    def stop(self) -> None:
        self._stopping = True
        with self._condition:
            self._requests.clear()
            self._condition.notify_all()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._release_now("shutdown")
        close_shared_external_engine_pool()
