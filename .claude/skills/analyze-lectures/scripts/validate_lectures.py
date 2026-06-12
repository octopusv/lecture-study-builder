#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lecture_common import parse_lecture_spec, resolve_subject, validate_lectures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id")
    parser.add_argument("lectures", help="回指定。例: 5 / 1-5 / 1,3,5 / 1-3,8")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    try:
        subject = resolve_subject(args.course_id, project_root)
        lectures = parse_lecture_spec(args.lectures, int(subject["lecture_count"]))
        result = validate_lectures(subject["id"], lectures, project_root)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{result['course_id']}] {result['subject']}: {result['status']}")
        print(f"対象回: {', '.join(map(str, result['requested_lectures']))}")
        print(f"完了(スキップ): {', '.join(map(str, result['lectures_done'])) or 'なし'}")
        print(f"未完了: {', '.join(map(str, result['lectures_pending'])) or 'なし'}")
        print(f"動画不足: {', '.join(map(str, result['lectures_blocked'])) or 'なし'}")
        for item in result["per_lecture"]:
            counts = item["counts"]
            print(
                f"- 第{item['lecture']:02d}回: {item['status']} "
                f"(次工程={item['next_subphase']}, "
                f"問題={counts['questions']}, カード={counts['cards']})"
            )

    return 0 if result["status"] == "complete" else (2 if result["blocked"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
