"""Bounded safetensors reads without Windows copy-on-write file mappings."""

import json
import math
import struct
from pathlib import Path


class TensorSlice:
    def __init__(self, reader, name):
        self.reader = reader
        self.name = name

    def get_shape(self):
        return self.reader.header[self.name]["shape"]

    def get_dtype(self):
        return self.reader.header[self.name]["dtype"]

    def __getitem__(self, index):
        return self.reader.get_tensor(self.name)[index]


class BufferedCheckpoint:
    """The safe_open subset used by Transformers for a local, verified model.

    Only a single tensor is materialized on the host at a time. All shapes,
    offsets and file coverage are validated before any tensor is allocated.
    No pickle, executable metadata or persistent converted copy is involved.
    """

    def __init__(self, filename, framework="pt", device="cpu"):
        import torch

        if framework != "pt":
            raise ValueError("The bounded checkpoint reader only supports PyTorch")
        self.path = Path(filename)
        self.device = f"cuda:{device}" if isinstance(device, int) else device
        self.dtypes = {
            "F64": torch.float64, "F32": torch.float32, "F16": torch.float16,
            "BF16": torch.bfloat16, "I64": torch.int64, "I32": torch.int32,
            "I16": torch.int16, "I8": torch.int8, "U8": torch.uint8,
            "BOOL": torch.bool,
        }
        size = self.path.stat().st_size
        with self.path.open("rb") as stream:
            prefix = stream.read(8)
            if len(prefix) != 8:
                raise ValueError("Truncated safetensors header")
            length = struct.unpack("<Q", prefix)[0]
            if length > min(100_000_000, size - 8):
                raise ValueError("Invalid safetensors header length")
            self.header = json.loads(stream.read(length))
        if not isinstance(self.header, dict):
            raise ValueError("Invalid safetensors header")
        self.offset = length + 8
        self.meta = self.header.pop("__metadata__", None)
        if self.meta is not None and (
            not isinstance(self.meta, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.meta.items())
        ):
            raise ValueError("Invalid safetensors metadata")
        ranges = []
        for name, spec in self.header.items():
            if not isinstance(spec, dict):
                raise ValueError(f"Invalid tensor metadata: {name}")
            shape, offsets, dtype = spec.get("shape"), spec.get("data_offsets"), spec.get("dtype")
            if (dtype not in self.dtypes or not isinstance(shape, list)
                    or any(type(n) is not int or n < 0 for n in shape)
                    or not isinstance(offsets, list) or len(offsets) != 2
                    or any(type(n) is not int or n < 0 for n in offsets)):
                raise ValueError(f"Invalid tensor metadata: {name}")
            start, end = offsets
            expected = math.prod(shape) * torch.empty((), dtype=self.dtypes[dtype]).element_size()
            if end - start != expected:
                raise ValueError(f"Invalid tensor length: {name}")
            ranges.append((start, end))
        end = 0
        for start, stop in sorted(ranges):
            if start != end:
                raise ValueError("Overlapping or incomplete safetensors data")
            end = stop
        if self.offset + end != size:
            raise ValueError("Truncated or trailing safetensors data")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def keys(self):
        return list(self.header)

    def metadata(self):
        return self.meta

    def get_slice(self, name):
        return TensorSlice(self, name)

    def get_tensor(self, name):
        import torch

        spec = self.header[name]
        start, end = spec["data_offsets"]
        if start == end:
            return torch.empty(spec["shape"], dtype=self.dtypes[spec["dtype"]], device=self.device)
        data = bytearray(end - start)
        with self.path.open("rb") as stream:
            stream.seek(self.offset + start)
            if stream.readinto(data) != len(data):
                raise ValueError(f"Truncated tensor: {name}")
        return torch.frombuffer(data, dtype=self.dtypes[spec["dtype"]]).reshape(spec["shape"]).to(self.device)
