#!/usr/bin/env python3
"""Build an AI-friendly Markdown knowledge base from transcripts and slide OCR."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def natural_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", value)
    ]


def format_time(seconds: float) -> str:
    total = max(0, round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def normalize_ocr(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def is_similar_slide(left: str, right: str) -> bool:
    if not left or not right:
        return False
    compact_left = re.sub(r"\s+", "", left)
    compact_right = re.sub(r"\s+", "", right)
    if compact_left in compact_right or compact_right in compact_left:
        shorter = min(len(compact_left), len(compact_right))
        longer = max(len(compact_left), len(compact_right))
        return shorter / max(longer, 1) >= 0.72
    return SequenceMatcher(None, compact_left, compact_right).ratio() >= 0.82


def unique_slides(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slides: list[dict[str, Any]] = []
    for record in records:
        text = normalize_ocr(record.get("text", ""))
        if len(text) < 8:
            continue
        if slides and is_similar_slide(slides[-1]["text"], text):
            if len(text) > len(slides[-1]["text"]):
                slides[-1]["text"] = text
            continue
        slides.append(
            {
                "seconds": int(record["seconds"]),
                "timestamp": record["timestamp"],
                "text": text,
            }
        )
    return slides


def first_meaningful_line(text: str) -> str:
    for line in text.splitlines():
        clean = line.strip("・●○▶■□◆◇ \t")
        if (
            2 <= len(clean) <= 80
            and re.search(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff]", clean)
        ):
            return clean
    return "スライド"


def topic_title(text: str) -> str:
    ignored_phrases = (
        "このセクションでの問題",
        "主な内容",
        "すばやく",
        "ファイルのダウンロード",
        "http://",
        "https://",
    )
    for line in text.splitlines():
        clean = line.strip("・●○▶■□◆◇ \t")
        japanese_count = len(
            re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", clean)
        )
        if (
            2 <= len(clean) <= 80
            and japanese_count >= 2
            and not any(phrase in clean for phrase in ignored_phrases)
        ):
            return clean
    return first_meaningful_line(text)


def segment_text(segments: list[dict[str, Any]], start: float, end: float) -> str:
    selected = [
        str(segment.get("text", "")).strip()
        for segment in segments
        if float(segment.get("start", 0)) >= start
        and float(segment.get("start", 0)) < end
    ]
    return "\n\n".join(text for text in selected if text)


def write_video_section(
    handle: Any,
    stem: str,
    transcript: dict[str, Any],
    slides: list[dict[str, Any]],
) -> None:
    segments = sorted(
        transcript.get("segments", []),
        key=lambda segment: (
            float(segment.get("start", 0)),
            float(segment.get("end", 0)),
        ),
    )
    duration = max(
        (float(segment.get("end", 0)) for segment in segments),
        default=0,
    )
    handle.write(f"## 動画 {stem}\n\n")
    handle.write(
        f"- 再生時間: 約{format_time(duration)}\n"
        f"- 音声認識区間数: {len(segments)}\n"
        f"- 抽出された固有スライド数: {len(slides)}\n\n"
    )

    if slides:
        first_slide_start = float(slides[0]["seconds"])
        if first_slide_start > 0:
            opening = segment_text(segments, 0, first_slide_start)
            if opening:
                handle.write("### [00:00] 導入\n\n")
                handle.write("**講師の説明（詳細文字起こし）**\n\n")
                handle.write(opening)
                handle.write("\n\n")
        for index, slide in enumerate(slides):
            start = float(slide["seconds"])
            end = (
                float(slides[index + 1]["seconds"])
                if index + 1 < len(slides)
                else duration + 1
            )
            title = first_meaningful_line(slide["text"])
            handle.write(f"### [{format_time(start)}] {title}\n\n")
            handle.write("**スライド記載事項（OCR）**\n\n")
            handle.write("```text\n")
            handle.write(slide["text"])
            handle.write("\n```\n\n")
            explanation = segment_text(segments, start, end)
            if explanation:
                handle.write("**講師の説明（詳細文字起こし）**\n\n")
                handle.write(explanation)
                handle.write("\n\n")
    else:
        handle.write("### 講師の説明（詳細文字起こし）\n\n")
        for segment in segments:
            start = format_time(float(segment.get("start", 0)))
            text = str(segment.get("text", "")).strip()
            if text:
                handle.write(f"- **[{start}]** {text}\n")
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transcripts",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/transcripts"),
    )
    parser.add_argument(
        "--ocr",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/slide_ocr"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/マクロ経済学_授業内容_超詳細.md"),
    )
    parser.add_argument(
        "--split-output",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/notes"),
    )
    parser.add_argument(
        "--index-output",
        type=Path,
        default=Path("教科別/01_マクロ経済/output/マクロ経済学_講義トピック一覧.md"),
    )
    parser.add_argument("--subject", default="マクロ経済学")
    args = parser.parse_args()

    transcript_paths = sorted(
        args.transcripts.glob("*.json"),
        key=lambda path: natural_key(path.stem),
    )
    lectures: dict[int, list[Path]] = defaultdict(list)
    for path in transcript_paths:
        match = re.fullmatch(r"(\d+)_(\d+)", path.stem)
        if match:
            lectures[int(match.group(1))].append(path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.split_output.mkdir(parents=True, exist_ok=True)

    def write_intro(handle: Any, scope: str) -> None:
        handle.write(f"# {args.subject} 授業内容 超詳細版{scope}\n\n")
        handle.write(
            "> 他のAIへの入力、検索、試験対策資料の作成に使えるよう、"
            "スライド記載事項と講師説明を分けて可能な限り欠落なく収録した資料です。\n\n"
        )
        handle.write("## この資料の読み方\n\n")
        handle.write(
            "- 各節の `[MM:SS]` は、その動画内での開始位置です。\n"
            "- `スライド記載事項（OCR）` は画面から読み取った文字です。\n"
            "- `講師の説明` は音声認識結果です。固有名詞・数値・数式には"
            "認識誤りが残る可能性があります。\n"
            "- 税率や統計値など時点依存の情報は、講義で示された時点の情報です。\n\n"
        )

    with args.index_output.open("w", encoding="utf-8") as index_handle:
        index_handle.write(f"# {args.subject} 講義トピック一覧\n\n")
        index_handle.write(
            "全15回の詳細資料から、スライドの出現順にトピックを一覧化した索引です。"
            "他のAIへ渡す場合は、まずこの索引で対象回を決め、"
            "`notes/第NN回_超詳細.md` を添付してください。\n\n"
        )
        index_handle.write("## 他のAIへ渡す際の推奨指示\n\n")
        index_handle.write("```text\n")
        index_handle.write(
            f"添付資料は大学の{args.subject}講義の詳細記録です。\n"
            "回答は添付資料を第一の根拠とし、資料にない内容を補う場合は"
            "「補足」と明記してください。\n"
            "OCR・音声認識の誤りが疑われる固有名詞、数式、数値は、"
            "前後の文脈と一般的な専門用語・固有名詞から慎重に補正してください。\n"
            "講師が強調・反復した点、定義、因果関係、比較、数値例を"
            "省略せず整理してください。\n"
        )
        index_handle.write("```\n\n")

        for lecture_number in sorted(lectures):
            index_handle.write(f"## 第{lecture_number}回\n\n")
            for transcript_path in sorted(
                lectures[lecture_number],
                key=lambda p: natural_key(p.stem),
            ):
                ocr_path = args.ocr / f"{transcript_path.stem}.json"
                records = (
                    json.loads(ocr_path.read_text(encoding="utf-8"))
                    if ocr_path.exists()
                    else []
                )
                slides = unique_slides(records)
                index_handle.write(f"### 動画 {transcript_path.stem}\n\n")
                previous_title = ""
                for slide in slides:
                    title = topic_title(slide["text"])
                    if title == previous_title:
                        continue
                    index_handle.write(f"- [{slide['timestamp']}] {title}\n")
                    previous_title = title
                index_handle.write("\n")

    with args.output.open("w", encoding="utf-8") as handle:
        write_intro(handle, "（全15回統合）")

        for lecture_number in sorted(lectures):
            paths = sorted(lectures[lecture_number], key=lambda p: natural_key(p.stem))
            handle.write(f"# 第{lecture_number}回\n\n")
            split_path = args.split_output / f"第{lecture_number:02d}回_超詳細.md"
            with split_path.open("w", encoding="utf-8") as split_handle:
                write_intro(split_handle, f"（第{lecture_number}回）")
                for transcript_path in paths:
                    transcript = json.loads(
                        transcript_path.read_text(encoding="utf-8")
                    )
                    ocr_path = args.ocr / f"{transcript_path.stem}.json"
                    records = (
                        json.loads(ocr_path.read_text(encoding="utf-8"))
                        if ocr_path.exists()
                        else []
                    )
                    slides = unique_slides(records)
                    write_video_section(
                        handle,
                        transcript_path.stem,
                        transcript,
                        slides,
                    )
                    write_video_section(
                        split_handle,
                        transcript_path.stem,
                        transcript,
                        slides,
                    )

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
