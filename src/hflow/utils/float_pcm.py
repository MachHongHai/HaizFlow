"""Bounded little-endian mono float PCM reader for the lightweight Core."""
from pathlib import Path


class FloatPcmReader:
    def __init__(self,path,samplerate=16000):
        self.path = Path(path)
        self.samplerate = samplerate
        size = self.path.stat().st_size
        if size % 4:
            raise ValueError('Incomplete float PCM frame.')
        self.frames = size//4
        self._file = None

    def __enter__(self):
        self._file = self.path.open('rb')
        return self

    def __exit__(self,*_exc):
        self._file.close()

    def seek(self,frame):
        self._file.seek(max(0,int(frame))*4)

    def read(self,frames,dtype='float32'):
        import numpy as np
        return np.frombuffer(self._file.read(max(0,int(frames))*4),dtype='<f4').astype(dtype,copy=False)
