#!/usr/bin/env python3
"""Run Apple Vision OCR over the sampled lecture slide frames."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from Foundation import NSURL
from Vision import (
    VNImageRequestHandler,
    VNRecognizeTextRequest,
    VNRequestTextRecognitionLevelAccurate,
)


def natural_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.stem)
    ]


def recognize(path: Path) -> str:
    url = NSURL.fileURLWithPath_(str(path.resolve()))
    request = VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["ja-JP", "en-US"])
    request.setUsesLanguageCorrection_(True)
    handler = VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise RuntimeError(error)

    lines: list[str] = []
    for observation in request.results() or []:
        candidates = observation.topCandidates_(1)
        if candidates:
            lines.append(str(candidates[0].string()))
    return "\n".join(lines)


def timestamp(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def main() -> int:
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
            seconds = frame_index * 30
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
