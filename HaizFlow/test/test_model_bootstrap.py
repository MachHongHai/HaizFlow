import hashlib
import io
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.desktop.runtime_device_controller import RuntimeDeviceController
from haizflow.services import model_bootstrap


class _Response:
    def __init__(self, payload: bytes, url: str):
        self._stream = io.BytesIO(payload)
        self._url = url
        self.status = 200
        self.headers = {"Content-Length": str(len(payload))}

    def read(self, size=-1):
        return self._stream.read(size)

    def geturl(self):
        return self._url

    def getcode(self):
        return self.status

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class ModelBootstrapTests(unittest.TestCase):
    def test_plan_downloads_only_the_selected_translation_backend(self):
        cpu_paths = {asset.relative_path for asset in model_bootstrap.required_assets("cpu")}
        gpu_paths = {asset.relative_path for asset in model_bootstrap.required_assets("gpu")}

        self.assertTrue(any(path.endswith(".gguf") for path in cpu_paths))
        self.assertFalse(any(path.endswith(".safetensors") for path in cpu_paths))
        self.assertTrue(any(path.endswith(".safetensors") for path in gpu_paths))
        self.assertFalse(any(path.endswith(".gguf") for path in gpu_paths))
        self.assertTrue(any(path.startswith("whisper/") for path in cpu_paths))
        self.assertTrue(any(path.startswith("demucs/") for path in gpu_paths))
        self.assertTrue(any(path.startswith("vieneu/v3-turbo/") for path in cpu_paths))
        self.assertTrue(any(path.startswith("vieneu/codec/") for path in gpu_paths))
        self.assertTrue(any(path.endswith("vieneu-3.2.5-py3-none-any.whl") for path in cpu_paths))
        self.assertEqual(
            {path for path in cpu_paths if path.startswith("subtitle-ocr/")},
            {
                "subtitle-ocr/subtitle-det.onnx",
                "subtitle-ocr/subtitle-rec.onnx",
                "subtitle-ocr/subtitle-cls.onnx",
            },
        )
        self.assertEqual(
            sum(path.startswith("alignment/") for path in cpu_paths),
            len(model_bootstrap.ALIGNMENT_MODELS),
        )

    def test_install_is_atomic_reports_progress_and_reuses_verified_file(self):
        payload = b"verified model payload"
        asset = model_bootstrap.ModelAsset(
            component="test",
            label="Test model",
            url="https://huggingface.co/test/model.bin",
            relative_path="test/model.bin",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        progress = []
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            model_bootstrap, "required_assets", return_value=(asset,)
        ), patch.object(
            model_bootstrap, "_verify_installed_components"
        ), patch.object(
            model_bootstrap.shutil,
            "disk_usage",
            return_value=type("Usage", (), {"free": model_bootstrap.DOWNLOAD_HEADROOM_BYTES * 2})(),
        ), patch.object(
            model_bootstrap.urllib.request,
            "urlopen",
            return_value=_Response(payload, asset.url),
        ) as urlopen:
            root = Path(temp_dir)
            model_bootstrap.install_required_models(root, "cpu", progress=progress.append)
            destination = root / asset.relative_path
            self.assertEqual(destination.read_bytes(), payload)
            self.assertFalse(destination.with_name(destination.name + ".part").exists())
            self.assertEqual(progress[-1].state, "ready")
            self.assertEqual(progress[-1].completed_bytes, len(payload))

            progress.clear()
            model_bootstrap.install_required_models(root, "cpu", progress=progress.append)
            self.assertEqual(urlopen.call_count, 1)
            self.assertEqual(progress[-1].state, "ready")

    def test_cancel_stops_before_network_and_leaves_no_partial_file(self):
        payload = b"model"
        asset = model_bootstrap.ModelAsset(
            component="test",
            label="Test model",
            url="https://huggingface.co/test/model.bin",
            relative_path="test/model.bin",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        cancelled = threading.Event()
        cancelled.set()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            model_bootstrap, "required_assets", return_value=(asset,)
        ), patch.object(model_bootstrap.urllib.request, "urlopen") as urlopen:
            with self.assertRaises(model_bootstrap.ModelBootstrapCancelled):
                model_bootstrap.install_required_models(
                    Path(temp_dir),
                    "cpu",
                    progress=lambda _value: None,
                    cancel_event=cancelled,
                )
            urlopen.assert_not_called()
            self.assertFalse((Path(temp_dir) / "test" / "model.bin.part").exists())

    def test_paused_partial_is_preserved_and_resumed(self):
        payload = b"resumable model payload"
        offset = 10
        asset = model_bootstrap.ModelAsset(
            component="test",
            label="Test model",
            url="https://huggingface.co/test/model.bin",
            relative_path="test/model.bin",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        response = _Response(payload[offset:], asset.url)
        response.status = 206
        progress = []
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            model_bootstrap, "required_assets", return_value=(asset,)
        ), patch.object(
            model_bootstrap, "_verify_installed_components"
        ), patch.object(
            model_bootstrap.shutil,
            "disk_usage",
            return_value=type("Usage", (), {"free": model_bootstrap.DOWNLOAD_HEADROOM_BYTES * 2})(),
        ), patch.object(
            model_bootstrap.urllib.request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            root = Path(temp_dir)
            partial = root / "test" / "model.bin.part"
            partial.parent.mkdir(parents=True)
            partial.write_bytes(payload[:offset])

            model_bootstrap.install_required_models(root, "cpu", progress=progress.append)

            request = urlopen.call_args.args[0]
            self.assertEqual(request.headers["Range"], f"bytes={offset}-")
            self.assertEqual((root / asset.relative_path).read_bytes(), payload)
            self.assertFalse(partial.exists())

    def test_complete_verified_partial_is_promoted_without_network(self):
        payload = b"complete model payload"
        asset = model_bootstrap.ModelAsset(
            component="test",
            label="Test model",
            url="https://huggingface.co/test/model.bin",
            relative_path="test/model.bin",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            model_bootstrap, "required_assets", return_value=(asset,)
        ), patch.object(
            model_bootstrap, "_verify_installed_components"
        ), patch.object(
            model_bootstrap.urllib.request,
            "urlopen",
        ) as urlopen:
            root = Path(temp_dir)
            partial = root / "test" / "model.bin.part"
            partial.parent.mkdir(parents=True)
            partial.write_bytes(payload)

            model_bootstrap.install_required_models(
                root,
                "cpu",
                progress=lambda _value: None,
            )

            urlopen.assert_not_called()
            self.assertEqual((root / asset.relative_path).read_bytes(), payload)
            self.assertFalse(partial.exists())

    def test_unapproved_download_redirect_is_rejected(self):
        asset = model_bootstrap.ModelAsset(
            component="test",
            label="Test model",
            url="https://huggingface.co/test/model.bin",
            relative_path="test/model.bin",
            size=5,
            sha256="0" * 64,
        )
        with patch.object(
            model_bootstrap.urllib.request,
            "urlopen",
            return_value=_Response(b"model", "https://example.test/model.bin"),
        ):
            with self.assertRaisesRegex(model_bootstrap.ModelBootstrapError, "unapproved host"):
                model_bootstrap._open_download(asset, 0)

    def test_modelscope_ocr_source_is_approved(self):
        self.assertTrue(model_bootstrap._approved_download_url(
            "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx"
        ))

    def test_completed_install_skips_setup_ui_and_only_warms_models(self):
        class _Host:
            def __init__(self):
                self._model_setup_target_device = ""
                self._runtime_probe_error = ""
                self._runtime_state = "warming"
                self._model_setup_events = queue.Queue()
                self._initial_model_warmup_done = threading.Event()
                self.warmed = False

            def _warm_models(self):
                self.warmed = True
                self._runtime_state = "ready"

        host = _Host()
        controller = RuntimeDeviceController(host)
        with patch(
            "haizflow.desktop.runtime_device_controller.processing_device_preference",
            return_value="cpu",
        ), patch(
            "haizflow.desktop.runtime_device_controller.models_ready",
            return_value=True,
        ), patch(
            "haizflow.desktop.runtime_device_controller.probe_runtime",
            return_value=type("Probe", (), {"ok": True, "message": "ready"})(),
        ), patch.object(
            controller, "_install_models"
        ) as install, patch.object(
            controller, "_queue_model_setup"
        ) as setup_event:
            controller._warm_models_at_startup()

        install.assert_not_called()
        setup_event.assert_not_called()
        self.assertTrue(host.warmed)
        self.assertTrue(host._initial_model_warmup_done.is_set())


if __name__ == "__main__":
    unittest.main()
