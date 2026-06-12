#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from lecture_common import parse_lecture_spec, resolve_subject, validate_lectures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id")
    parser.add_argument("lectures", help="回指定。例: 5 / 1-5 / 1,3,5 / 1-3,8")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    args = parser.parse_args()

    if not args.session_id:
        print(json.dumps(
            {"error": "セッションIDがありません。--session-id か環境変数 CLAUDE_CODE_SESSION_ID を指定してください"},
            ensure_ascii=False,
        ))
        return 2

    project_root = args.project_root.resolve()
    try:
        subject = resolve_subject(args.course_id, project_root)
        lectures = parse_lecture_spec(args.lectures, int(subject["lecture_count"]))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    run_dir = project_root / ".claude" / "lecture-analysis-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / f"{args.session_id}.json"
    state = {
        "session_id": args.session_id,
        "course_id": subject["id"],
        "subject": subject["name"],
        "lectures": lectures,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = validate_lectures(subject["id"], lectures, project_root)
    context = {
        "course": {
            key: subject[key]
            for key in (
                "id", "name", "directory", "output_prefix",
                "lecture_count", "parts_per_lecture", "expected_videos", "base",
            )
        },
        "requested_lectures": lectures,
        "lectures_to_skip": result["lectures_done"],
        "lectures_to_process": result["lectures_pending"],
        "lectures_blocked": result["lectures_blocked"],
        "status": result["status"],
        "per_lecture": result["per_lecture"],
        "assessment_dir": str(Path(subject["base"]) / "output" / "assessment"),
        "out_of_scope": ["synthesis", "site", "final"],
        "state_file": str(state_path),
    }
    print(json.dumps(context, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
