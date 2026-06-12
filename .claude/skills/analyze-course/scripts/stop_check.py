#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from validate_course import validate


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()

    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    session_id = str(hook_input.get("session_id", "")).strip()
    if not session_id:
        return 0

    state_path = args.project_root / ".claude" / "course-analysis-runs" / f"{session_id}.json"
    if not state_path.is_file():
        return 0

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        result = validate(str(state["course_id"]), args.project_root.resolve())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        emit({"systemMessage": f"講義分析の継続判定に失敗しました: {exc}"})
        return 0

    if result["status"] == "complete":
        state_path.unlink(missing_ok=True)
        emit({"systemMessage": f"{result['subject']}の機械検証が完了しました。"})
        return 0

    if result["blocked"]:
        state_path.unlink(missing_ok=True)
        emit({
            "systemMessage": (
                f"{result['subject']}は入力検証で停止しました。"
                f"未達: {', '.join(result['failed_checks'])}"
            )
        })
        return 0

    background = hook_input.get("background_tasks") or []
    if background:
        reason = (
            f"{result['subject']}は未完了で、バックグラウンド処理も実行中です。"
            f"次工程は {result['next_phase']}。処理を監視して完了後に再検証してください。"
        )
    else:
        reason = (
            f"{result['subject']}の完成条件が未達です。次工程: {result['next_phase']}。"
            f"未達チェック: {', '.join(result['failed_checks'])}。"
            "既存成果物を保ち、未達項目を処理してvalidate_course.pyを再実行してください。"
        )
    emit({"decision": "block", "reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
