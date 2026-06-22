#!/usr/bin/env python3
"""Windows専用: faster-whisper で講義動画を文字起こしする。

macOS版 scripts/transcribe_macro.py（mlx_whisper）のローカル代替。出力先と
JSONスキーマを transcribe_macro.py に完全一致させ、後段（build_detailed_notes.py
や validate_course.py）を無改造で通す。Apple Silicon Mac では transcribe_macro.py
を使うこと。本スクリプトはWindows以外では実行できない（OSガードで停止）。

`--device auto`（既定）では搭載GPUを自動判定する。NVIDIA + CUDAランタイムが揃って
いればGPU(CUDA/float16)で実行し、揃っていなければCPUへ安全にフォールバックする。
AMD GPUは faster-whisper(CTranslate2) が非対応のためCPUで実行し、その旨を通知する。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import traceback
from pathlib import Path


DEFAULT_MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
DEFAULT_PROMPT = (
    "マクロ経済学、経済統計、国民経済計算、GDP、GNI、SNA、税制、財政、"
    "金融、物価、雇用、国際収支、経済発展についての大学講義です。"
    "専門用語、固有名詞、数式、統計値を正確に文字起こししてください。"
)


def require_windows() -> None:
    if platform.system() != "Windows":
        print(
            "このスクリプトはWindows専用です。"
            "macOS/Apple Siliconでは scripts/transcribe_macro.py を使ってください。",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2)


def natural_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.stem)
    ]


def srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_outputs(output_dir: Path, stem: str, payload: dict) -> None:
    """transcribe_macro.py の writer("all") と同じ JSON / SRT / TSV を出力する。"""
    segments = payload["segments"]
    (output_dir / f"{stem}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    srt_lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        srt_lines.append(str(i))
        srt_lines.append(f"{srt_time(seg['start'])} --> {srt_time(seg['end'])}")
        srt_lines.append(seg["text"].strip())
        srt_lines.append("")
    (output_dir / f"{stem}.srt").write_text("\n".join(srt_lines), encoding="utf-8")

    tsv_lines = ["start\tend\ttext"]
    for seg in segments:
        start_ms = int(round(seg["start"] * 1000))
        end_ms = int(round(seg["end"] * 1000))
        text = seg["text"].strip().replace("\t", " ")
        tsv_lines.append(f"{start_ms}\t{end_ms}\t{text}")
    (output_dir / f"{stem}.tsv").write_text("\n".join(tsv_lines), encoding="utf-8")


CUDA_RUNTIME_HINT = (
    "NVIDIA GPUを検出しましたが、CUDAランタイム(cuBLAS/cuDNN)を読み込めませんでした。\n"
    "  次を実行してから再試行するとGPUで動きます（.venv へ導入）:\n"
    "    .venv\\Scripts\\python -m pip install -r requirements-windows-cuda.txt\n"
    "  導入済みでもダメな場合は、NVIDIAドライバの更新も確認してください。"
)


def has_nvidia_gpu() -> bool:
    """CUDAドライバ経由でNVIDIA GPUの有無を見る（cuBLAS/cuDNN無しでもTrueになり得る）。"""
    try:
        import ctranslate2  # faster-whisper の依存に含まれる

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def has_amd_gpu() -> bool:
    """Windowsの表示アダプタ名にAMD/Radeonが含まれるかを見る（高速化可否の通知用）。"""
    if platform.system() != "Windows":
        return False
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController).Name",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return False
    names = (result.stdout or "").upper()
    return "AMD" in names or "RADEON" in names


def register_cuda_dll_dirs() -> None:
    """pip導入の nvidia-cublas-cu12 / nvidia-cudnn-cu12 のDLLをWindowsで探索可能にする。

    CTranslate2 はWindowsでこれらのDLLを自動探索しないため、site-packages 配下の
    bin ディレクトリを os.add_dll_directory で登録する。これが無いと cuBLAS/cuDNN を
    pip導入しても読み込めず、結局CPUへ落ちてしまう。
    """
    if platform.system() != "Windows" or not hasattr(os, "add_dll_directory"):
        return
    import site

    roots: list[str] = []
    roots.extend(site.getsitepackages() if hasattr(site, "getsitepackages") else [])
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        roots.append(user_site)
    for root in roots:
        for parts in (("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin")):
            dll_dir = Path(root, *parts)
            if dll_dir.is_dir():
                try:
                    os.add_dll_directory(str(dll_dir))
                except OSError:
                    pass


def resolve_device(device: str, compute_type: str) -> tuple[str, str]:
    """`auto` を実機のGPU状況へ解決し、compute_type も device に合わせて既定値を決める。"""
    if device == "auto":
        if has_nvidia_gpu():
            device = "cuda"
            print("GPU検出: NVIDIA (CUDA) を使用します。", flush=True)
        elif has_amd_gpu():
            device = "cpu"
            print(
                "GPU検出: AMD Radeon。faster-whisper(CTranslate2)はAMD GPUへ非対応のため"
                "CPUで実行します。AMDでGPU高速化したい場合は DirectML版 "
                "scripts/transcribe_windows_directml.py を使ってください"
                "（依存: requirements-windows-directml.txt）。",
                flush=True,
            )
        else:
            device = "cpu"
            print("GPU未検出: CPUで実行します。", flush=True)
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def load_model(model_name: str, device: str, compute_type: str):
    """モデルを読み込む。CUDA初期化に失敗したらCPUへフォールバックして続行する。

    戻り値は (model, 実際に使ったdevice, 実際に使ったcompute_type)。
    """
    # OSガードを通った後に重い依存を読み込む（Macにはインストールされていない）。
    from faster_whisper import WhisperModel

    if device == "cuda":
        register_cuda_dll_dirs()
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        return model, device, compute_type
    except Exception as exc:
        if device != "cuda":
            raise
        print(f"CUDA初期化に失敗しました: {exc}", file=sys.stderr, flush=True)
        print(CUDA_RUNTIME_HINT, file=sys.stderr, flush=True)
        print("CPU(int8)へフォールバックして続行します。", flush=True)
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        return model, "cpu", "int8"


def main() -> int:
    require_windows()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--videos",
        type=Path,
        default=Path("教科別/01_マクロ経済/videos"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/transcripts"),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--device",
        default="auto",
        help="auto(GPU自動判定) / cpu / cuda。autoはNVIDIA+CUDAがあればcuda、無ければcpu",
    )
    parser.add_argument(
        "--compute-type",
        default="auto",
        help="auto / int8 / float16 など。autoはcudaでfloat16、cpuでint8",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    videos = sorted(args.videos.glob("*.mp4"), key=natural_key)

    pending = [
        video
        for video in videos
        if not (
            (args.output / f"{video.stem}.json").exists()
            and (args.output / f"{video.stem}.json").stat().st_size > 0
        )
    ]
    if not pending:
        print(f"All {len(videos)} videos already transcribed.", flush=True)
        return 0

    device, compute_type = resolve_device(args.device, args.compute_type)
    print(
        f"Loading model {args.model} (device={device}, compute_type={compute_type})...",
        flush=True,
    )
    model, device, compute_type = load_model(args.model, device, compute_type)
    print(f"Model ready on device={device} (compute_type={compute_type}).", flush=True)

    failures: list[str] = []
    for index, video in enumerate(videos, start=1):
        output_json = args.output / f"{video.stem}.json"
        if output_json.exists() and output_json.stat().st_size > 0:
            print(f"[{index:02d}/{len(videos)}] skip {video.name}", flush=True)
            continue

        print(f"[{index:02d}/{len(videos)}] start {video.name}", flush=True)
        try:
            segments_iter, info = model.transcribe(
                str(video),
                language="ja",
                task="transcribe",
                temperature=0.0,
                condition_on_previous_text=True,
                initial_prompt=args.prompt,
                word_timestamps=False,
            )

            segments = []
            texts: list[str] = []
            for seg in segments_iter:
                segments.append(
                    {
                        "id": seg.id,
                        "seek": seg.seek,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                        "tokens": list(seg.tokens),
                        "temperature": seg.temperature,
                        "avg_logprob": seg.avg_logprob,
                        "compression_ratio": seg.compression_ratio,
                        "no_speech_prob": seg.no_speech_prob,
                    }
                )
                texts.append(seg.text)

            payload = {
                "text": "".join(texts),
                "language": info.language or "ja",
                "segments": segments,
            }
            write_outputs(args.output, video.stem, payload)
            print(f"[{index:02d}/{len(videos)}] done  {video.name}", flush=True)
        except Exception:
            failures.append(video.name)
            traceback.print_exc()

    if failures:
        print("Failed files:", ", ".join(failures), flush=True)
        return 1

    print(f"Completed {len(videos)} videos.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
