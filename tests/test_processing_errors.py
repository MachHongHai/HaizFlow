import pytest

from haizflow.core.processing_errors import describe_failure


@pytest.mark.parametrize("error", [
    "CUDA failed with error out of memory",
    "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 1.2 GiB",
    "CUDNN_STATUS_ALLOC_FAILED", "CUBLAS_STATUS_ALLOC_FAILED",
])
def test_gpu_memory_errors_have_explicit_name(error):
    result = describe_failure(error)
    assert result["code"] == "gpu_out_of_memory"
    assert "Hết bộ nhớ GPU" in result["title"]
    assert "CUDA out of memory" in result["message"]


@pytest.mark.parametrize("error", [
    MemoryError(), "std::bad_alloc", "[WinError 1455] The paging file is too small",
    "DefaultCPUAllocator: can't allocate memory", "Unable to allocate array",
])
def test_system_memory_is_distinct_from_gpu_memory(error):
    result = describe_failure(error)
    assert result["code"] == "system_out_of_memory"
    assert "RAM" in result["message"]


def test_logged_cudnn_execution_failure_is_not_assumed_to_be_oom():
    result = describe_failure("cuDNN error: CUDNN_STATUS_EXECUTION_FAILED_CUBLAS")
    assert result["code"] == "gpu_execution_error"
    assert "CUDNN_STATUS_EXECUTION_FAILED_CUBLAS" in result["title"]
    assert "Chưa xác định là hết bộ nhớ" in result["message"]


def test_unknown_errors_keep_technical_context_with_bounded_text():
    result = describe_failure("Missing model file " + "x" * 300)
    assert result["code"] == "processing_error"
    assert "Missing model file" in result["message"]
    assert len(result["message"]) < 280


def test_english_ui_does_not_mix_languages():
    result = describe_failure("CUDA out of memory", "en")
    assert result["title"] == "GPU out of memory (CUDA)"
    assert "Close other GPU applications" in result["message"]
