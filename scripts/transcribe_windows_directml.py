#!/usr/bin/env python3
"""Windows + DirectML(AMD/Intel/NVIDIAのDX12 GPU) 向けの文字起こし。

faster-whisper(CTranslate2) は AMD GPU を使えないため、AMD等のDX12対応GPUでGPU高速化
したい場合のローカル代替。onnxruntime-directml + optimum + transformers で ONNX 版
Whisper を DirectML(DmlExecutionProvider) 上で実行する。出力先とJSONスキーマは
transcribe_macro.py / transcribe_windows.py に一致させ、後段(build_detailed_notes.py /
validate_course.py)を無改造で通す。

- NVIDIA機なら transcribe_windows.py(CUDA) の方が速い。本スクリプトはAMD等のための経路。
- 初回は openai/whisper-large-v3-turbo を ONNX へ自動エクスポートしてキャッシュする
  （数分かかる。2回目以降はキャッシュを再利用）。
- DirectML(チャンク処理)では initial_prompt を既定で使わない（チャンク処理と相性が悪い）。
- 依存は requirements-windows-directml.txt。Windows以外では実行できない(OSガードで停止)。
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import traceback
from pathlib import Path


DEFAULT_MODEL = "openai/whisper-large-v3-turbo"
# エクスポート済みONNXのキャッシュ先（ユーザーホーム配下、モデルごと）。
DEFAULT_EXPORT_ROOT = Path.home() / ".cache" / "whisper-onnx-directml"
CHUNK_LENGTH_S = 30
STRIDE_LENGTH_S = 5


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
    """transcribe_macro.py / transcribe_windows.py と同じ JSON / SRT / TSV を出力する。"""
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


def is_exported(export_dir: Path) -> bool:
    """optimum がエクスポートしたONNX一式が揃っているか（encoder + decoder）。"""
    if not export_dir.is_dir():
        return False
    has_encoder = any(export_dir.glob("encoder_model*.onnx"))
    has_decoder = any(export_dir.glob("decoder_model*.onnx"))
    return has_encoder and has_decoder


def resolve_provider(prefer_dml: bool) -> str:
    """DirectMLが使えれば DmlExecutionProvider、無ければ CPUExecutionProvider。"""
    import onnxruntime as ort

    available = ort.get_available_providers()
    if prefer_dml and "DmlExecutionProvider" in available:
        return "DmlExecutionProvider"
    if prefer_dml:
        print(
            "警告: DmlExecutionProvider が見つかりません。CPUで実行します。"
            "GPUを使うには onnxruntime-directml を導入してください"
            "（pip install -r requirements-windows-directml.txt）。",
            file=sys.stderr,
            flush=True,
        )
    return "CPUExecutionProvider"


def load_pipeline(model_id: str, export_dir: Path, provider: str):
    """ONNX版WhisperをDirectMLで動かすASRパイプラインを返す。

    初回は model_id を ONNX へエクスポートして export_dir にキャッシュする。
    """
    import onnxruntime as ort
    from optimum.onnxruntime import ORTModelForSpeechSeq2Seq
    from transformers import AutoProcessor, pipeline

    if not is_exported(export_dir):
        print(
            f"ONNXモデルを書き出します（初回のみ、数分かかります）: {model_id} -> {export_dir}",
            flush=True,
        )
        exported = ORTModelForSpeechSeq2Seq.from_pretrained(model_id, export=True)
        export_dir.mkdir(parents=True, exist_ok=True)
        exported.save_pretrained(export_dir)
        AutoProcessor.from_pretrained(model_id).save_pretrained(export_dir)

    model = ORTModelForSpeechSeq2Seq.from_pretrained(
        export_dir, provider=provider, use_io_binding=False
    )
    processor = AutoProcessor.from_pretrained(export_dir)
    active = getattr(model, "providers", None)
    print(
        f"ORT providers: available={ort.get_available_providers()} active={active}",
        flush=True,
    )

    asr = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        chunk_length_s=CHUNK_LENGTH_S,
        stride_length_s=STRIDE_LENGTH_S,
        return_timestamps=True,
    )
    return asr


def chunks_to_segments(chunks: list[dict], full_text: str) -> list[dict]:
    """HFパイプラインの chunks を transcribe_macro 互換の segments へ変換する。"""
    segments: list[dict] = []
    for index, chunk in enumerate(chunks):
        timestamp = chunk.get("timestamp") or (None, None)
        raw_start, raw_end = timestamp[0], timestamp[1]
        start = float(raw_start) if raw_start is not None else (
            segments[-1]["end"] if segments else 0.0
        )
        end = float(raw_end) if raw_end is not None else start
        segments.append(
            {
                "id": index,
                "seek": 0,
                "start": start,
                "end": end,
                "text": chunk.get("text", ""),
                "tokens": [],
                "temperature": 0.0,
                "avg_logprob": 0.0,
                "compression_ratio": 0.0,
                "no_speech_prob": 0.0,
            }
        )
    if not segments and full_text:
        # タイムスタンプが取れなかった場合は全体を1区間にする。
        segments.append(
            {
                "id": 0,
                "seek": 0,
                "start": 0.0,
                "end": 0.0,
                "text": full_text,
                "tokens": [],
                "temperature": 0.0,
                "avg_logprob": 0.0,
                "compression_ratio": 0.0,
                "no_speech_prob": 0.0,
            }
        )
    return segments


def transcribe_one(asr, video: Path) -> dict:
    result = asr(
        str(video),
        generate_kwargs={"language": "japanese", "task": "transcribe"},
        return_timestamps=True,
    )
    full_text = result.get("text", "") if isinstance(result, dict) else ""
    chunks = result.get("chunks") or [] if isinstance(result, dict) else []
    segments = chunks_to_segments(chunks, full_text)
    return {"text": full_text, "language": "ja", "segments": segments}


def main() -> int:
    require_windows()

    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=Path, default=Path("教科別/01_マクロ経済/videos"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/transcripts"),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="ONNXエクスポートのキャッシュ先。未指定なら ~/.cache/whisper-onnx-directml/<model>",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="auto(DirectML優先) / dml / cpu",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="モデル読み込みとprovider、1秒の無音推論だけ確認して終了する",
    )
    args = parser.parse_args()

    export_dir = args.export_dir or (
        DEFAULT_EXPORT_ROOT / re.sub(r"[^A-Za-z0-9._-]", "_", args.model)
    )
    prefer_dml = args.device in ("auto", "dml")
    provider = "CPUExecutionProvider" if args.device == "cpu" else resolve_provider(prefer_dml)

    if args.selftest:
        import numpy as np

        print(f"selftest: model={args.model} provider(target)={provider}", flush=True)
        asr = load_pipeline(args.model, export_dir, provider)
        out = asr(np.zeros(16000, dtype="float32"), return_timestamps=True)
        text = out.get("text", "") if isinstance(out, dict) else ""
        print(f"selftest OK: provider={provider} 1秒無音のtext={text!r}", flush=True)
        return 0

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

    print(
        f"Loading model {args.model} (provider target={provider})...",
        flush=True,
    )
    asr = load_pipeline(args.model, export_dir, provider)

    failures: list[str] = []
    for index, video in enumerate(videos, start=1):
        output_json = args.output / f"{video.stem}.json"
        if output_json.exists() and output_json.stat().st_size > 0:
            print(f"[{index:02d}/{len(videos)}] skip {video.name}", flush=True)
            continue

        print(f"[{index:02d}/{len(videos)}] start {video.name}", flush=True)
        try:
            payload = transcribe_one(asr, video)
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
