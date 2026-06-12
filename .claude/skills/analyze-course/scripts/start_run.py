#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from course_common import resolve_subject
from validate_course import validate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("course_id")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    try:
        subject = resolve_subject(args.course_id, project_root)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2

    run_dir = project_root / ".claude" / "course-analysis-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / f"{args.session_id}.json"
    state = {
        "session_id": args.session_id,
        "course_id": subject["id"],
        "subject": subject["name"],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = validate(subject["id"], project_root)
    context = {
        "course": subject,
        "current_status": result["status"],
        "next_phase": result["next_phase"],
        "failed_checks": result["failed_checks"],
        "state_file": str(state_path),
    }
    print(json.dumps(context, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
