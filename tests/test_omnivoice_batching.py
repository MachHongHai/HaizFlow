"""Bounded batching, ordered checkpoints and isolated-worker memory ownership."""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from haizflow.pipeline import omnivoice_tts as voice
from haizflow.core.memory import MemorySnapshot


class FakeCudaOom(RuntimeError):
    pass


def fake_torch():
    return SimpleNamespace(
        Tensor=type("Tensor", (), {}), OutOfMemoryError=FakeCudaOom,
        float16="fp16", float32="fp32", set_num_threads=Mock(), set_num_interop_threads=Mock(),
        manual_seed=Mock(), inference_mode=contextlib.nullcontext,
        cuda=SimpleNamespace(is_available=lambda: True, manual_seed_all=Mock(), empty_cache=Mock(),
                             mem_get_info=lambda: (4 * 1024**3, 8 * 1024**3),
                             memory_reserved=lambda: 2 * 1024**3, memory_allocated=lambda: 2 * 1024**3),
        backends=SimpleNamespace(cuda=SimpleNamespace(matmul=SimpleNamespace()), cudnn=SimpleNamespace()),
    )


class OmniVoiceBatchTests(unittest.TestCase):
    def test_reference_codec_always_encodes_in_inference_mode(self):
        events = []

        @contextlib.contextmanager
        def inference():
            events.append("enter")
            yield
            events.append("exit")

        def encode(**kwargs):
            self.assertEqual(events, ["enter"])
            self.assertEqual(kwargs, {"ref_audio": "voice.wav", "ref_text": "Sample"})
            return "discrete tokens"

        result = voice._encode_voice_reference(SimpleNamespace(create_voice_clone_prompt=encode),
                                               SimpleNamespace(inference_mode=inference), "voice.wav", "Sample")
        self.assertEqual(result, "discrete tokens")
        self.assertEqual(events, ["enter", "exit"])

    def test_grouping_preserves_order_voice_and_reference(self):
        items = [{"text": "A short sentence.", "voice": "male"},
                 {"text": "Another sentence.", "voice": "male"},
                 {"text": "Another sentence.", "voice": "female"}]
        self.assertEqual(voice._next_synthesis_batch(items, 0, 4), items[:2])
        items[1]["reference_path"] = "other.wav"
        self.assertEqual(voice._next_synthesis_batch(items, 0, 4), items[:1])
        items[1].pop("reference_path")
        items[1]["text"] = "x" * 170
        self.assertEqual(voice._next_synthesis_batch(items, 0, 4), items[:1])

    def test_batch_headroom_counts_reclaimable_blocks_but_keeps_reserve(self):
        torch = fake_torch()
        self.assertEqual(voice._gpu_batch_ceiling(torch, "cuda:0"), 2)
        torch.cuda.mem_get_info = lambda: (512 * 1024**2, 8 * 1024**3)
        self.assertEqual(voice._gpu_batch_ceiling(torch, "cuda:0"), 1)
        torch.cuda.memory_reserved = lambda: 4 * 1024**3
        self.assertEqual(voice._gpu_batch_ceiling(torch, "cuda:0"), 2)
        self.assertEqual(voice._gpu_batch_ceiling(torch, "cpu"), 1)

    def test_cuda_oom_retries_smaller_batch_without_reordering(self):
        torch = fake_torch()
        items = [{"text": str(index)} for index in range(4)]
        calls = []

        def generate(batch):
            calls.append(len(batch))
            if len(batch) > 1:
                raise FakeCudaOom("CUDA out of memory")
            return ["audio"]

        outputs, batch, retries = voice._generate_bounded_batch(generate, items, torch, "cuda:0")
        self.assertEqual(calls, [4, 2, 1])
        self.assertEqual(outputs, ["audio"])
        self.assertEqual(batch, items[:1])
        self.assertEqual(retries, 2)
        self.assertEqual(torch.cuda.empty_cache.call_count, 2)

    def test_adaptation_uses_pairs_only_for_measured_throughput_gain(self):
        profile = {"single": [], "paired": [], "trials": 0}
        self.assertEqual([voice._adaptive_batch_size(profile, 2) for _ in range(4)], [1, 2, 1, 2])
        profile.update(single=[1.0, 1.05], paired=[1.0, 1.01])
        self.assertEqual(voice._adaptive_batch_size(profile, 2), 1)
        profile["paired"] = [0.7, 0.8]
        self.assertEqual(voice._adaptive_batch_size(profile, 2), 2)
        self.assertEqual(voice._adaptive_batch_size(profile, 1), 1)

    def test_preview_and_full_quality_never_share_throughput_profiles(self):
        runtime = {}
        item = {"text": "Short sentence"}
        preview = voice._adaptive_batch_profile(runtime, "cuda:0", "vi", item, 8)
        full = voice._adaptive_batch_profile(runtime, "cuda:0", "vi", item, 32)
        self.assertIsNot(preview, full)
        self.assertIs(full, voice._adaptive_batch_profile(runtime, "cuda:0", "vi", item, 32))

    def test_other_failures_and_single_item_oom_are_not_hidden(self):
        torch = fake_torch()
        for error, items in ((RuntimeError("invalid text"), [1, 2]),
                             (RuntimeError("CUDA error: illegal memory access"), [1, 2]),
                             (FakeCudaOom("CUDA out of memory"), [1])):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    voice._generate_bounded_batch(Mock(side_effect=error), items, torch, "cuda:0")
        torch.cuda.empty_cache.assert_not_called()

    def test_release_request_keeps_modules_but_no_model_or_prompt(self):
        torch = fake_torch()
        modules = (Mock(), Mock(), torch, Mock())
        clear_layers = Mock()
        codec = SimpleNamespace(_get_conv1d_layers=SimpleNamespace(cache_clear=clear_layers))
        runtime = {"modules": modules, "model": SimpleNamespace(audio_tokenizer=codec), "model_key": ("model", "cuda:0"),
                   "clone_prompt_cache": {"reference": Mock()}, "preset_prompt_cache": {"voice": Mock()}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps({"operation": "release_model"}), encoding="utf-8")
            self.assertEqual(voice._worker_main(str(path), runtime), 0)
        self.assertEqual(runtime, {"modules": modules})
        clear_layers.assert_called_once()
        torch.cuda.empty_cache.assert_called_once()

    def test_parent_reuses_imports_only_after_verified_release_with_ram_headroom(self):
        cases = [(True, 8 * 1024**2, 5 * 1024**3, 32, 12, True),
                 (True, 128 * 1024**2, 5 * 1024**3, 32, 12, False),
                 (True, 8 * 1024**2, 2 * 1024**3, 32, 12, False),
                 (True, 8 * 1024**2, 5 * 1024**3, 16, 12, False),
                 (True, 8 * 1024**2, 5 * 1024**3, 32, 2, False),
                 (True, 8 * 1024**2, 5 * 1024**3, 32, None, False),
                 (False, 0, 5 * 1024**3, 32, 12, False)]
        for released, resident, ram, total, commit, expected in cases:
            with self.subTest(released=released, resident=resident, ram=ram), tempfile.TemporaryDirectory() as directory:
                process = SimpleNamespace(poll=lambda: None, stdin=SimpleNamespace(write=Mock(), flush=Mock()))

                def respond(line):
                    request = json.loads(Path(line.strip()).read_text(encoding="utf-8"))
                    self.assertEqual(request["operation"], "release_model")
                    Path(request["response_path"]).write_text(json.dumps({"return_code": 0, "model_released": released,
                                                                          "resident_cuda_bytes": resident}), encoding="utf-8")

                process.stdin.write.side_effect = respond
                with patch.object(voice, "TMP_DIR", directory), \
                     patch.object(voice, "_PERSISTENT_WORKER_PROCESS", process), \
                     patch.object(voice, "_cancel_idle_shutdown"), \
                     patch.object(voice, "_schedule_idle_shutdown") as idle, \
                     patch.object(voice, "_stop_persistent_worker_unlocked") as stop, \
                     patch("haizflow.core.memory.memory_snapshot", return_value=MemorySnapshot(
                         usable_bytes=total * 1024**3, available_bytes=ram,
                         process_commit_available_bytes=None if commit is None else commit * 1024**3,
                     )):
                    self.assertEqual(voice.release_model_memory(), expected)
                self.assertEqual(idle.call_count, int(expected))
                self.assertEqual(stop.call_count, int(not expected))

    def test_worker_outputs_every_item_in_order_and_reports_batch_progress(self):
        for device, oom in (("cuda:0", False), ("cuda:0", True), ("cpu", False)):
            with self.subTest(device=device, oom=oom), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                torch = fake_torch()
                writes, statuses, sizes = [], [], []

                def generate(**kwargs):
                    texts = kwargs["text"] if isinstance(kwargs["text"], list) else [kwargs["text"]]
                    sizes.append(len(texts))
                    if oom and len(texts) > 1:
                        raise FakeCudaOom("CUDA out of memory")
                    return [np.full(480, float(text.split()[0]), dtype=np.float32) for text in texts]

                model = SimpleNamespace(generate=generate, sampling_rate=24000)
                sf = SimpleNamespace(write=lambda path, audio, rate, **kw: writes.append((Path(path).name, audio[0], rate)))
                runtime = {"modules": (np, sf, torch, Mock()), "model": model, "model_key": ("model", device)}
                items = [{"text": f"{index} a short sentence", "voice": "omnivoice:male", "wav_path": str(root / f"{index}.wav")}
                         for index in range(1, 6)]
                request = {"site_packages": directory, "model_root": "model", "device": device, "language": "vi",
                           "items": items, "status_path": str(root / "status.json"), "speaker_mode": "multiple",
                           "cpu_threads": 4}
                path = root / "request.json"
                path.write_text(json.dumps(request), encoding="utf-8")
                with patch.object(voice, "_write_status_file", side_effect=lambda _path, payload: statuses.append(payload)):
                    self.assertEqual(voice._worker_main(str(path), runtime), 0)
                self.assertEqual([entry[0] for entry in writes], [f"{index}.wav" for index in range(1, 6)])
                self.assertEqual([entry[1] for entry in writes], list(range(1, 6)))
                self.assertTrue(all(entry[2] == 24000 for entry in writes))
                self.assertEqual(statuses[-1]["completed"], 5)
                if device == "cpu":
                    self.assertEqual(sizes, [1] * 5)
                    self.assertEqual([call.args[0] for call in torch.set_num_threads.call_args_list], [1, 4])
                elif oom:
                    self.assertEqual(sizes, [1, 2, 1, 1, 1, 1])
                    self.assertEqual(statuses[-1]["batch_retries"], 1)
                else:
                    self.assertEqual(sizes, [1, 2, 1, 1])
                if device.startswith("cuda"):
                    torch.set_num_threads.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
