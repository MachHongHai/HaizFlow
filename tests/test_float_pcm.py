import numpy as np
import pytest
from hflow.utils.float_pcm import FloatPcmReader


def test_float_reader_preserves_overshoots_and_supports_frame_seeks(tmp_path):
    path = tmp_path/'audio.pcm'
    samples = np.array([0,1.31,-1.25,.02],dtype='<f4')
    path.write_bytes(samples.tobytes())
    with FloatPcmReader(path) as reader:
        assert reader.frames == 4
        np.testing.assert_array_equal(reader.read(2),samples[:2])
        reader.seek(2)
        np.testing.assert_array_equal(reader.read(5),samples[2:])
        assert reader.read(1).size == 0
    assert reader._file.closed


def test_float_reader_rejects_truncated_sample(tmp_path):
    path = tmp_path/'audio.pcm'
    path.write_bytes(b'123')
    with pytest.raises(ValueError,match='Incomplete'):
        FloatPcmReader(path)
