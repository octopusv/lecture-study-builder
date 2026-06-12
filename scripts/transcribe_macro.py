#!/usr/bin/env python3
"""Transcribe all macroeconomics lecture videos with MLX Whisper."""

from __future__ import annotations

import argparse
import re
import traceback
from pathlib import Path

from mlx_whisper import transcribe
from mlx_whisper.writers import get_writer


DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_PROMPT = (
    "マクロ経済学、経済統計、国民経済計算、GDP、GNI、SNA、税制、財政、"
    "金融、物価、雇用、国際収支、経済発展についての大学講義です。"
    "専門用語、固有名詞、数式、統計値を正確に文字起こししてください。"
)


def natural_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.stem)
    ]


def main() -> int:
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
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    videos = sorted(args.videos.glob("*.mp4"), key=natural_key)
    writer = get_writer("all", str(args.output))
    failures: list[str] = []

    for index, video in enumerate(videos, start=1):
        output_json = args.output / f"{video.stem}.json"
        if output_json.exists() and output_json.stat().st_size > 0:
            print(f"[{index:02d}/{len(videos)}] skip {video.name}", flush=True)
            continue

        print(f"[{index:02d}/{len(videos)}] start {video.name}", flush=True)
        try:
            result = transcribe(
                str(video),
                path_or_hf_repo=args.model,
                language="ja",
                task="transcribe",
                verbose=False,
                temperature=0.0,
                condition_on_previous_text=True,
                initial_prompt=args.prompt,
                word_timestamps=False,
            )
            writer(result, video.stem)
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
