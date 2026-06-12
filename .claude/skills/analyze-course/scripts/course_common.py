#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def normalize_course_id(raw: str) -> str:
    value = str(raw).strip()
    if not value.isdigit():
        raise ValueError(f"教科IDは数字で指定してください: {raw!r}")
    return f"{int(value):02d}"


def load_subjects(project_root: Path) -> dict[str, dict[str, Any]]:
    path = project_root / "config" / "subjects.json"
    if not path.is_file():
        raise ValueError("教科台帳がありません。先に /setup と /setup-course を実行してください")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("config/subjects.jsonの形式が不正です")
    return value


def resolve_subject(raw_id: str, project_root: Path) -> dict[str, Any]:
    course_id = normalize_course_id(raw_id)
    subjects = load_subjects(project_root)
    if course_id not in subjects:
        available = ", ".join(sorted(subjects)) or "なし"
        raise ValueError(f"未登録の教科IDです: {course_id}（登録済み: {available}）")

    subject = dict(subjects[course_id])
    subject["id"] = course_id
    subject.setdefault("lecture_count", 15)
    subject.setdefault("parts_per_lecture", 6)
    subject.setdefault(
        "expected_videos",
        int(subject["lecture_count"]) * int(subject["parts_per_lecture"]),
    )
    subject["project_root"] = str(project_root.resolve())
    subject["base"] = str((project_root / subject["directory"]).resolve())
    return subject


def expected_stems(subject: dict[str, Any]) -> list[str]:
    lectures = int(subject["lecture_count"])
    parts = int(subject["parts_per_lecture"])
    return [
        f"{lecture}_{part}"
        for lecture in range(1, lectures + 1)
        for part in range(1, parts + 1)
    ]


def nonempty_files(directory: Path, pattern: str) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(pattern) if path.is_file() and path.stat().st_size > 0)
