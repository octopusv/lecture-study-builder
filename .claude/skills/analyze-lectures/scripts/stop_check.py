#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lecture_common import validate_lectures


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False))


def lectures_label(subject: str, lectures: list[int]) -> str:
    joined = "・".join(f"{int(n):02d}" for n in lectures)
    return f"{subject} 第{joined}回"


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

    state_path = args.project_root / ".claude" / "lecture-analysis-runs" / f"{session_id}.json"
    if not state_path.is_file():
        return 0

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        result = validate_lectures(
            str(state["course_id"]), list(state["lectures"]), args.project_root.resolve()
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        emit({"systemMessage": f"回別分析の継続判定に失敗しました: {exc}"})
        return 0

    label = lectures_label(result["subject"], result["requested_lectures"])

    if result["status"] == "complete":
        state_path.unlink(missing_ok=True)
        emit({"systemMessage": (
            f"{label}の回別検証が完了しました（指定回の文字起こし・OCR・回別ノート・問題/カードが揃いました）。"
            "統合まとめ・サイトは対象外です。全体を仕上げるときは /analyze-course を実行してください。"
        )})
        return 0

    if result["blocked"]:
        state_path.unlink(missing_ok=True)
        blocked = ", ".join(f"第{n:02d}回" for n in result["lectures_blocked"])
        emit({"systemMessage": (
            f"{label}は入力検証で停止しました。動画が不足している回: {blocked}。"
            "動画を配置してから同じコマンドを再実行してください。"
        )})
        return 0

    background = hook_input.get("background_tasks") or []
    if background:
        emit({"systemMessage": (
            f"{label}は未完了ですが、バックグラウンド処理が実行中です。"
            "ブロックせず待機します（ジョブ完了の通知で再開し、再検証します）。"
        )})
        return 0

    details = [
        f"第{item['lecture']:02d}回={item['next_subphase']}"
        for item in result["per_lecture"]
        if item["status"] == "pending"
    ]
    reason = (
        f"{label}の回別完成条件が未達です。未完了の回と次工程: {', '.join(details)}。"
        "既存の正常成果物は保ち、未完了の回だけを処理してください。"
        "回別問題カードは output/assessment/第NN回.json に保存します。"
        "統合まとめ・サイト・最終監査は本スキルの対象外です（後で /analyze-course が全回を統合）。"
    )
    emit({"decision": "block", "reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
