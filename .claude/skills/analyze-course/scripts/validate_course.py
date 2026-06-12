#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from course_common import expected_stems, nonempty_files, resolve_subject


def file_ok(path: Path, minimum: int = 1) -> bool:
    return path.is_file() and path.stat().st_size >= minimum


def same_content(left: Path, right: Path) -> bool:
    if not left.is_file() or not right.is_file() or left.stat().st_size != right.stat().st_size:
        return False
    digest = lambda path: hashlib.sha256(path.read_bytes()).digest()
    return digest(left) == digest(right)


def inspect_site_data(path: Path) -> dict[str, Any]:
    node = shutil.which("node")
    script = Path(__file__).with_name("inspect_site_data.js")
    if not node or not path.is_file():
        return {"parsed": False, "error": "nodeまたはsite/data.jsがありません"}
    completed = subprocess.run(
        [node, str(script), str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"parsed": False, "error": completed.stderr.strip() or "site/data.jsを解析できません"}


def load_count_exceptions(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def validate(course_id: str, project_root: Path) -> dict[str, Any]:
    subject = resolve_subject(course_id, project_root)
    base = Path(subject["base"])
    output = base / "output"
    site = base / "site"
    validation_dir = output / "validation"
    prefix = subject["output_prefix"]
    lecture_count = int(subject["lecture_count"])
    expected_video_count = int(subject["expected_videos"])
    expected = set(expected_stems(subject))

    videos = nonempty_files(base / "videos", "*.mp4")
    transcripts = nonempty_files(output / "transcripts", "*.json")
    ocr = nonempty_files(output / "slide_ocr", "*.json")
    notes = nonempty_files(output / "notes", "第*_超詳細.md")
    video_stems = {path.stem for path in videos}
    transcript_stems = {path.stem for path in transcripts}
    ocr_stems = {path.stem for path in ocr}

    archive = output / f"{prefix}_講義全記録.md"
    summary = output / f"{prefix}_授業内容まとめ_超詳細.md"
    topics = output / f"{prefix}_講義トピック一覧.md"
    readme = output / "README.md"
    opus_audit = validation_dir / "opus_cross_audit.md"
    final_report = validation_dir / "final_report.md"
    exceptions = load_count_exceptions(validation_dir / "count_exceptions.json")
    site_stats = inspect_site_data(site / "data.js")

    q_count = int(site_stats.get("questions", 0) or 0)
    c_count = int(site_stats.get("cards", 0) or 0)
    q_min, q_max = 20 * lecture_count, 30 * lecture_count
    c_min, c_max = 15 * lecture_count, 25 * lecture_count
    q_exception = bool(
        exceptions.get("approved_by_opus")
        and len(str(exceptions.get("question_reason", "")).strip()) >= 20
    )
    c_exception = bool(
        exceptions.get("approved_by_opus")
        and len(str(exceptions.get("card_reason", "")).strip()) >= 20
    )

    portal = project_root / "index.html"
    portal_text = portal.read_text(encoding="utf-8", errors="ignore") if portal.is_file() else ""
    expected_link = f"{subject['directory']}/site/index.html"

    checks: dict[str, bool] = {
        "course_directory": base.is_dir(),
        "videos_expected_named": len(videos) == expected_video_count and video_stems == expected,
        "transcripts_expected": len(transcripts) == expected_video_count and transcript_stems == expected,
        "ocr_expected": len(ocr) == expected_video_count and ocr_stems == expected,
        "notes_expected": len(notes) == lecture_count,
        "lecture_archive": file_ok(archive, max(5_000, lecture_count * 1_000)),
        "ai_summary": file_ok(summary, max(20_000, lecture_count * 3_000)),
        "archive_summary_distinct": file_ok(archive) and file_ok(summary) and not same_content(archive, summary),
        "topics": file_ok(topics, max(1_000, lecture_count * 100)),
        "readme": file_ok(readme, 300),
        "site_files": all(file_ok(site / name, 100) for name in ("index.html", "styles.css", "app.js", "data.js")),
        "site_data_parsed": bool(site_stats.get("parsed")),
        "lectures_expected": int(site_stats.get("lectures", 0) or 0) == lecture_count,
        "questions_target": q_min <= q_count <= q_max or q_exception,
        "cards_target": c_min <= c_count <= c_max or c_exception,
        "four_unique_choices": (
            bool(site_stats.get("parsed"))
            and int(site_stats.get("invalid_choices", 0) or 0) == 0
            and int(site_stats.get("duplicate_choices", 0) or 0) == 0
        ),
        "valid_answers": bool(site_stats.get("parsed")) and int(site_stats.get("invalid_answers", 0) or 0) == 0,
        "opus_cross_audit": file_ok(opus_audit, 1_000),
        "final_report": file_ok(final_report, 1_000),
        "portal_link": expected_link in portal_text,
    }

    phase_checks = [
        ("input", ["course_directory", "videos_expected_named"]),
        ("transcription", ["transcripts_expected"]),
        ("ocr", ["ocr_expected"]),
        ("notes", ["notes_expected", "lecture_archive", "topics", "readme"]),
        ("synthesis", ["ai_summary", "archive_summary_distinct"]),
        (
            "assessment",
            ["site_data_parsed", "lectures_expected", "questions_target", "cards_target", "four_unique_choices", "valid_answers"],
        ),
        ("site", ["site_files", "portal_link"]),
        ("final", ["opus_cross_audit", "final_report"]),
    ]
    next_phase = "complete"
    for phase, names in phase_checks:
        if not all(checks[name] for name in names):
            next_phase = phase
            break

    failed = [name for name, passed in checks.items() if not passed]
    blocked = not checks["course_directory"] or not checks["videos_expected_named"]
    return {
        "course_id": subject["id"],
        "subject": subject["name"],
        "status": "complete" if not failed else ("blocked" if blocked else "incomplete"),
        "next_phase": next_phase,
        "blocked": blocked,
        "checks": checks,
        "failed_checks": failed,
        "expected": {
            "lectures": lecture_count,
            "parts_per_lecture": int(subject["parts_per_lecture"]),
            "videos": expected_video_count,
            "questions": [q_min, q_max],
            "cards": [c_min, c_max],
        },
        "counts": {
            "videos": len(videos),
            "transcripts": len(transcripts),
            "ocr": len(ocr),
            "notes": len(notes),
            "lectures": int(site_stats.get("lectures", 0) or 0),
            "questions": q_count,
            "cards": c_count,
            "invalid_choices": int(site_stats.get("invalid_choices", 0) or 0),
            "duplicate_choices": int(site_stats.get("duplicate_choices", 0) or 0),
            "invalid_answers": int(site_stats.get("invalid_answers", 0) or 0),
        },
        "paths": {
            "base": str(base),
            "archive": str(archive),
            "summary": str(summary),
            "validation": str(validation_dir),
        },
        "site_data_error": site_stats.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    try:
        result = validate(args.course_id, args.project_root.resolve())
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.write_report:
        validation_dir = Path(result["paths"]["validation"])
        validation_dir.mkdir(parents=True, exist_ok=True)
        (validation_dir / "machine_validation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{result['course_id']}] {result['subject']}: {result['status']}")
        print(f"next_phase: {result['next_phase']}")
        for key, value in result["counts"].items():
            print(f"{key}: {value}")
        if result["failed_checks"]:
            print("failed:")
            for name in result["failed_checks"]:
                print(f"- {name}")

    return 0 if result["status"] == "complete" else (2 if result["blocked"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
