#!/usr/bin/env python3
"""Extract lecture slide frames every N seconds with ffmpeg.

Produces, for each video ``<stem>.mp4`` under ``--videos``, a directory
``<output>/<stem>/`` filled with zero-padded ``00001.jpg`` frames sampled at a
fixed interval, then writes an empty ``.done`` marker so re-runs skip finished
videos. The naming and 30s default match ``ocr_slides.py`` (which labels frame
index ``i`` as ``i * interval`` seconds).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import traceback
from pathlib import Path


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
        default=Path("教科別/01_マクロ経済/output/slide_frames"),
    )
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--quality", default="3", help="ffmpeg -q:v value")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    videos = sorted(args.videos.glob("*.mp4"), key=natural_key)
    failures: list[str] = []

    for index, video in enumerate(videos, start=1):
        out_dir = args.output / video.stem
        if (out_dir / ".done").exists():
            print(f"[{index:02d}/{len(videos)}] skip {video.name}", flush=True)
            continue

        # Remove any partial leftovers so frame numbering stays consistent.
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"[{index:02d}/{len(videos)}] start {video.name}", flush=True)
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(video),
                    "-vf",
                    f"fps=1/{args.interval}",
                    "-q:v",
                    str(args.quality),
                    str(out_dir / "%05d.jpg"),
                ],
                check=True,
            )
            frame_count = len(list(out_dir.glob("*.jpg")))
            if frame_count == 0:
                raise RuntimeError("no frames produced")
            (out_dir / ".done").touch()
            print(
                f"[{index:02d}/{len(videos)}] done  {video.name}: {frame_count} frames",
                flush=True,
            )
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
