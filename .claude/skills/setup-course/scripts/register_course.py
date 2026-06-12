#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


COURSE_DIRECTORIES = (
    "videos",
    "output",
    "output/transcripts",
    "output/slide_frames",
    "output/slide_ocr",
    "output/notes",
    "output/summary_sections",
    "output/quiz_src",
    "output/assessment",
    "output/validation",
    "site",
)


def normalize_id(raw: str) -> str:
    value = raw.strip()
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("教科IDは1以上の整数で指定してください")
    return f"{int(value):02d}"


def normalize_name(raw: str) -> str:
    value = re.sub(r"\s+", " ", raw.strip())
    if not value:
        raise ValueError("教科名が空です")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("教科名にパス区切りは使用できません")
    if any(ord(char) < 32 for char in value):
        raise ValueError("教科名に制御文字は使用できません")
    return value


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("config/subjects.jsonの形式が不正です")
    return value


def write_registry(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {key: registry[key] for key in sorted(registry, key=lambda item: int(item))}
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_directories(base: Path) -> list[str]:
    created: list[str] = []
    for relative in COURSE_DIRECTORIES:
        target = base / relative
        if not target.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            created.append(relative)
    return created


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id")
    parser.add_argument("course_name")
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()

    try:
        course_id = normalize_id(args.course_id)
        course_name = normalize_name(args.course_name)
        project_root = args.project_root.resolve()
        registry_path = project_root / "config" / "subjects.json"
        registry = load_registry(registry_path)

        existing = registry.get(course_id)
        if existing and existing.get("name") != course_name:
            raise ValueError(
                f"教科ID {course_id} は {existing.get('name')!r} として登録済みです"
            )

        directory = f"教科別/{course_id}_{course_name}"
        entry = existing or {
            "name": course_name,
            "directory": directory,
            "output_prefix": course_name,
            "lecture_count": 15,
            "parts_per_lecture": 6,
            "expected_videos": 90,
        }
        registry[course_id] = entry
        write_registry(registry_path, registry)
        created = ensure_directories(project_root / entry["directory"])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"created": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps({
        "created": True,
        "course": {"id": course_id, **entry},
        "created_directories": created,
        "next_command": f"/analyze-course {course_id}",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
