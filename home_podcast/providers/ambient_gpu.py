"""Pinned offline Small-SFX CUDA renderer, promoted from the 3080 audition.

Importing this module loads no numerical stack or model. The existing isolated
runtime supplies the official sampler, text encoder, tokenizer and decoder.
There is no download path and CUDA execution is verified, not inferred.
"""
from __future__ import annotations

from collections import Counter
import gc
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

BACKEND = "onnxruntime_cuda_fp16_diffusion_litert_cpu_text_and_decode"
MODEL_REVISION = "08b17423649b5714b22eab20f96bf00751f2358a"
SOURCE_REVISION = "77e0398c26f7d22d801ec1bb036307e8b231f741"


def verify_runtime(runtime: Path):
    from home_podcast.ambient_mastering import sha
    receipt = json.loads((runtime / "runtime-gpu-receipt.json").read_text(encoding="utf-8"))
    if receipt.get("revision") != MODEL_REVISION or not receipt.get("runtime_ready"):
        raise ValueError("Expected the pinned, already installed ambient GPU runtime")
    for item in receipt["files"]:
        path = (runtime / item["runtime_path"]).resolve()
        if not path.is_relative_to(runtime.resolve()) or sha(path) != item["sha256"]:
            raise ValueError("Ambient runtime file missing or changed")
    commit = subprocess.run(["git", "-C", str(runtime / "vendor/stable-audio-3"),
                             "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if commit != SOURCE_REVISION:
        raise ValueError("Ambient sampler source revision changed")
    return {"model_revision": MODEL_REVISION, "source_revision": SOURCE_REVISION,
            "files_verified": len(receipt["files"]), "network_calls": 0}


class StableAudio3CUDARenderer:
    def __init__(self, *, project_root: Path, runtime: Path, profile_prefix: Path):
        import numpy as np
        dlls = project_root / ".venv-qwen/Lib/site-packages/torch/lib"
        self.dll_handle = os.add_dll_directory(str(dlls)) if os.name == "nt" else None
        os.environ["PATH"] = str(dlls) + os.pathsep + os.environ.get("PATH", "")
        for name in ("HF_HUB_OFFLINE", "HF_HUB_DISABLE_IMPLICIT_TOKEN", "HF_HUB_DISABLE_TELEMETRY"):
            os.environ[name] = "1"
        import onnxruntime as ort
        ort.preload_dlls(directory=str(dlls))
        vendor = runtime / "vendor/stable-audio-3/optimized/tflite"
        sys.path.insert(0, str(vendor))
        sys.path.insert(0, str(vendor / "scripts"))
        from models.defs import tflite_pipeline as pipeline
        from rung_decoder import RungDecoder
        self.np, self.pipeline = np, pipeline
        self.tokenizer = pipeline.Tokenizer()
        self.text_model = pipeline.T5GemmaTFLite(vendor / "models/tflite/t5gemma/encoder_fp16.tflite", threads=8)
        self.decoder = RungDecoder(vendor / "models/tflite/same-s/dec_w8a8.tflite", threads=8, trim=16)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.log_severity_level = 3
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_prefix)
        self.session = ort.InferenceSession(str(runtime / "models/onnx/sa3-sm-sfx/dit_fp16.onnx"),
                                            sess_options=options, providers=[("CUDAExecutionProvider", {
                                                "device_id": 0, "gpu_mem_limit": 10 * 2**30,
                                                "arena_extend_strategy": "kSameAsRequested"})])
        if self.session.get_providers()[0] != "CUDAExecutionProvider":
            raise RuntimeError("CUDA unavailable; refusing silent CPU generation")
        self.session.disable_fallback()
        self.version = ort.__version__

    def generate(self, *, prompt, negative_prompt, seconds, seed, cfg=1.5, steps=8):
        np, p = self.np, self.pipeline
        if (not 1 <= seconds <= 120 or steps != 8 or not 1 <= cfg <= 3
                or type(seed) is not int or not 0 <= seed < 2**32):
            raise ValueError("Invalid bounded Small-SFX settings")
        if max(len(self.tokenizer.sp.Encode(text)) for text in (prompt, negative_prompt)) > 256:
            raise ValueError("Ambient prompt would be truncated")
        started = time.perf_counter()
        ids, mask = self.tokenizer(prompt)
        hidden = self.text_model(ids, mask)
        negative_ids, negative_mask = self.tokenizer(negative_prompt)
        negative_hidden = self.text_model(negative_ids, negative_mask) if cfg != 1 else None
        length = max(1, math.ceil(seconds * 44100 / 4096))
        shared = {"seconds_total": np.array([seconds], np.float32),
                  "local_add_cond": np.zeros((1, 257, length), np.float32)}
        diffusion_seconds, forwards = 0.0, 0

        def forward(x, t, unused_cross=None, unused_global=None):
            nonlocal diffusion_seconds, forwards
            feeds = {**shared, "x": x.astype(np.float32), "t": np.array([t], np.float32),
                     "t5_hidden": hidden, "t5_mask": mask.astype(np.float32)}
            before = time.perf_counter()
            vc = self.session.run(None, feeds)[0]
            forwards += 1
            if cfg == 1:
                result = vc
            else:
                feeds.update(t5_hidden=negative_hidden, t5_mask=negative_mask.astype(np.float32))
                vu = self.session.run(None, feeds)[0]
                forwards += 1
                cond, uncond = x - np.float32(t) * vc, x - np.float32(t) * vu
                diff = cond - uncond
                norm = np.sqrt((cond * cond).sum(axis=(-2, -1), keepdims=True))
                unit = cond / np.maximum(norm, 1e-8)
                orthogonal = diff - (diff * unit).sum(axis=(-2, -1), keepdims=True) * unit
                guided = cond + np.float32(cfg - 1) * orthogonal
                result = (x - guided) / np.float32(t)
            diffusion_seconds += time.perf_counter() - before
            if not np.isfinite(result).all():
                raise ValueError("Non-finite CUDA diffusion output")
            return result.astype(np.float32)

        noise, step_noise = p.make_noise(length, steps, seed)
        latents = p.sample(forward, noise, step_noise, p.build_pingpong_schedule(steps), None, None)
        if length % 2:
            latents = np.concatenate([latents, latents[:, :, -1:]], axis=2)
        decode_start = time.perf_counter()
        audio = self.decoder.decode(latents)[0, :, :round(seconds * 44100)].T
        if not np.isfinite(audio).all() or np.max(np.abs(audio)) > 20:
            raise ValueError("Invalid decoded ambient audio")
        return audio, {"backend": BACKEND, "onnxruntime": self.version,
                       "diffusion_gpu_seconds": round(diffusion_seconds, 3),
                       "cpu_decode_seconds": round(time.perf_counter() - decode_start, 3),
                       "wall_seconds": round(time.perf_counter() - started, 3),
                       "diffusion_forwards": forwards, "model_seconds": seconds,
                       "sample_rate": 44100, "channels": 2, "speech_models_loaded": 0,
                       "generation_network_calls": 0, "paid_calls": 0}

    def close(self):
        profile = Path(self.session.end_profiling())
        events = json.loads(profile.read_text(encoding="utf-8"))
        providers = Counter(e.get("args", {}).get("provider") for e in events if e.get("args", {}).get("provider"))
        cuda_matrix = sum(e.get("args", {}).get("provider") == "CUDAExecutionProvider"
                          and e.get("args", {}).get("op_name") in {"MatMul", "Gemm", "FusedMatMul"}
                          for e in events)
        self.session = self.text_model = self.decoder = None
        gc.collect()
        if self.dll_handle:
            self.dll_handle.close()
        if not cuda_matrix:
            raise RuntimeError("No CUDA matrix execution verified")
        return {"execution_profile": str(profile), "provider_operation_counts": dict(providers),
                "verified_cuda_matrix_operations": cuda_matrix, "models_unloaded": True}
