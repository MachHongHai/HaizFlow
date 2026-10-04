"""Read-only cold CPU/CUDA comparison; optionally use real source speech."""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

from haizflow.pipeline.speaker_identity import _cluster, _features, model_root, verify_model
from haizflow.pipeline.speaker_runtime import SpeakerSession
from haizflow.utils.ffmpeg import _binary


def benchmark_session(model, device):
    if device == "cpu":
        return SpeakerSession(model)
    # GPU support is diagnostic only; the application ships the CPU runtime.
    import onnxruntime as ort
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("Benchmark requires an isolated onnxruntime-gpu environment.")
    ort.preload_dlls()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    session = ort.InferenceSession(str(model), sess_options=options, providers=[
        ("CUDAExecutionProvider", {"device_id": 0, "gpu_mem_limit": 512 * 1024 ** 2,
          "arena_extend_strategy": "kSameAsRequested", "cudnn_conv_algo_search": "HEURISTIC",
          "cudnn_conv_use_max_workspace": "0"}), "CPUExecutionProvider"])
    if "CUDAExecutionProvider" not in session.get_providers():
        raise RuntimeError("CUDA backend failed; refusing to benchmark a CPU fallback as GPU.")
    session.disable_fallback()
    class GpuSession:
        device = "gpu"
        def run(self, features):
            return session.run(None, {"feats": features})
    return GpuSession()


def inputs(count, audio="", segment_file=""):
    if audio:
        segments = json.loads(Path(segment_file).read_text(encoding="utf-8"))
        samples = []
        decoded = subprocess.run([_binary("ffmpeg"), "-v", "error", "-i", audio, "-vn", "-ac", "1", "-ar", "16000",
                                  "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], capture_output=True, check=True,
                                 timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with wave.open(io.BytesIO(decoded.stdout), "rb") as stream:
            for segment in segments[:count]:
                start = max(0, int(segment["start"] * 16000))
                end = min(stream.getnframes(), int(segment["end"] * 16000), start + 128000)
                if end - start < 8000:
                    continue
                stream.setpos(start)
                signal = np.frombuffer(stream.readframes(end - start), dtype="<i2").astype(np.float32)
                if np.sqrt(np.mean(signal ** 2)) >= 20:
                    samples.append(_features(signal)[None, :, :])
        if not samples:
            raise ValueError("No voiced segments in input.")
        return samples
    rng = np.random.default_rng(876)
    samples = []
    for index in range(count):
        duration = (0.7, 1.2, 2.0, 3.0, 5.0, 8.0)[index % 6]
        t = np.arange(int(duration * 16000)) / 16000
        pitch = (105, 145, 195, 240)[index % 4]
        signal = sum(1000 / harmonic * np.sin(2 * np.pi * pitch * harmonic * t)
                   for harmonic in range(1, 7))
        signal += rng.normal(0, 30, len(t))
        samples.append(_features(signal)[None, :, :])
    return samples


def worker(device, count, audio="", segment_file=""):
    samples = inputs(count, audio, segment_file)
    started = time.monotonic()
    session = benchmark_session(verify_model(model_root()), device)
    loaded = time.monotonic() - started
    timings, embeddings = [], []
    for sample in samples:
        started = time.monotonic()
        vector = np.asarray(session.run(sample)[0], dtype=np.float32).reshape(-1)
        timings.append(time.monotonic() - started)
        vector /= max(float(np.linalg.norm(vector)), 1e-8)
        embeddings.append(vector.tolist())
    print(json.dumps(dict(actual=session.device, segments=len(samples), load_seconds=loaded, inference_seconds=sum(timings),
                          total_seconds=loaded + sum(timings), embeddings=embeddings)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=("cpu", "gpu"))
    parser.add_argument("--segments", type=int, default=30)
    parser.add_argument("--audio", default="")
    parser.add_argument("--segment-file", default="")
    parser.add_argument("--trials", type=int, default=1)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.segments, args.audio, args.segment_file)
        return
    for trial in range(args.trials):
        result, vectors = {}, {}
        for device in (("cpu", "gpu") if trial % 2 == 0 else ("gpu", "cpu")):
            command = [sys.executable, __file__, "--worker", device, "--segments", str(args.segments)]
            if args.audio:
                command.extend(["--audio", args.audio, "--segment-file", args.segment_file])
            child = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if child.returncode:
                raise RuntimeError(f"{device} benchmark failed: {child.stderr[-1500:]}")
            record = json.loads(child.stdout.strip().splitlines()[-1])
            vectors[device] = np.asarray(record.pop("embeddings"), dtype=np.float32)
            result[device] = record
        result["trial"] = trial + 1
        result["input"] = "real speech" if args.audio else "synthetic"
        result["minimum_embedding_cosine"] = float(np.min(np.sum(vectors["cpu"] * vectors["gpu"], axis=1)))
        result["same_clusters"] = _cluster(vectors["cpu"]) == _cluster(vectors["gpu"])
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
