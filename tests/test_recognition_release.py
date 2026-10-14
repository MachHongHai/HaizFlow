import sys
from types import ModuleType
from unittest import mock

import pytest

from hflow.pipeline import manual_tools, process_video


@pytest.mark.parametrize("owner", [manual_tools, process_video])
def test_isolated_recognition_release_does_not_import_whisperx_in_core(owner):
    with (
        mock.patch.dict(sys.modules, {"hflow.pipeline.transcribe": None}),
        mock.patch("hflow.services.external_engine.shared_external_engine_pool") as pool,
    ):
        pool.return_value.release.return_value = set()
        owner._release_recognition_runtime()
        pool.return_value.release.assert_called_once_with({"recognition", "separation", "ocr"})
        assert sys.modules["hflow.pipeline.transcribe"] is None


@pytest.mark.parametrize("owner", [manual_tools, process_video])
def test_source_warm_model_is_released_if_it_already_exists(owner):
    recognition = ModuleType("hflow.pipeline.transcribe")
    recognition.release_warm_whisperx_model = mock.Mock()
    with (
        mock.patch.dict(sys.modules, {"hflow.pipeline.transcribe": recognition}),
        mock.patch("hflow.services.external_engine.shared_external_engine_pool") as pool,
    ):
        pool.return_value.release.return_value = set()
        owner._release_recognition_runtime()
        recognition.release_warm_whisperx_model.assert_called_once_with()
