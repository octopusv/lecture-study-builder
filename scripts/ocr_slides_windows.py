#!/usr/bin/env python3
"""Windows専用: RapidOCR で抽出済みスライドフレームをOCRする。

macOS版 scripts/ocr_slides.py（Apple Vision）のローカル代替。フレーム抽出は
共通の scripts/extract_frames.py（ffmpeg, クロスプラットフォーム）で行う前提。
出力JSONのスキーマを ocr_slides.py に完全一致させ、後段を無改造で通す。
Apple Silicon Mac では ocr_slides.py を使うこと。本スクリプトはWindows以外では
実行できない（OSガードで停止）。
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from pathlib import Path


# extract_frames.py の既定抽出間隔（30秒ごと）に合わせる。
FRAME_INTERVAL_SECONDS = 30


def require_windows() -> None:
    if platform.system() != "Windows":
        print(
            "このスクリプトはWindows専用です。"
            "macOS/Apple Siliconでは scripts/ocr_slides.py を使ってください。",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2)


def natural_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.stem)
    ]


def timestamp(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def make_recognizer():
    """RapidOCRエンジンを生成し、画像パス→改行連結テキストの関数を返す。"""
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()

    def recognize(path: Path) -> str:
        result, _ = engine(str(path.resolve()))
        if not result:
            return ""
        # result は [box, text, score] のリスト。検出順（おおむね上→下）で連結する。
        return "\n".join(str(item[1]) for item in result)

    return recognize


def main() -> int:
    require_windows()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path("教科別/01_マクロ経済/output/slide_frames"),
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=Path("教科別/01_マクロ経済/output/slide_ocr"),
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    directories = sorted(
        (path for path in args.input.iterdir() if path.is_dir()),
        key=natural_key,
    )
    if args.limit is not None:
        directories = directories[: args.limit]

    recognize = make_recognizer()

    for index, directory in enumerate(directories, start=1):
        if not (directory / ".done").exists():
            continue
        output_path = args.output / f"{directory.name}.json"
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"[{index:02d}/{len(directories)}] skip {directory.name}", flush=True)
            continue

        records = []
        images = sorted(directory.glob("*.jpg"))
        for frame_index, image in enumerate(images):
            seconds = frame_index * FRAME_INTERVAL_SECONDS
            records.append(
                {
                    "frame": image.name,
                    "seconds": seconds,
                    "timestamp": timestamp(seconds),
                    "text": recognize(image),
                }
            )

        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[{index:02d}/{len(directories)}] done {directory.name}: "
            f"{len(records)} frames",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
