#!/usr/bin/env python3
"""特定回だけを対象にした回別分析の共通処理。

回指定の解釈と、回ごとの完了判定（文字起こし・OCR・回別ノート・回別問題カード）を提供する。
教科解決やファイル走査は analyze-course の course_common を再利用し、二重実装を避ける。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# 兄弟スキル analyze-course の scripts へパスを通し、共通処理を再利用する。
_AC_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "analyze-course" / "scripts"
if str(_AC_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AC_SCRIPTS))

from course_common import nonempty_files, resolve_subject  # noqa: E402

# 回別の完了基準。CLAUDE.md の目安下限に合わせる。
NOTE_MIN_BYTES = 1_000
QUESTION_MIN = 20
CARD_MIN = 15

SUBPHASES = ["input", "transcription", "ocr", "note", "assessment"]


def parse_lecture_spec(spec: str, lecture_count: int) -> list[int]:
    """回指定文字列を昇順ユニークな回番号リストへ変換する。

    例: "5" / "1-5" / "1,3,5" / "1-3,8"。全角カンマ・波ダッシュも許容する。
    """
    if spec is None:
        raise ValueError("回指定がありません")
    text = str(spec).strip().replace("、", ",").replace("，", ",").replace("〜", "~")
    if not text:
        raise ValueError("回指定が空です")

    result: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        sep = "-" if "-" in token else ("~" if "~" in token else "")
        if sep:
            lo_s, _, hi_s = token.partition(sep)
            lo_s, hi_s = lo_s.strip(), hi_s.strip()
            if not lo_s.isdigit() or not hi_s.isdigit():
                raise ValueError(f"回範囲の指定が不正です: {token!r}")
            lo, hi = int(lo_s), int(hi_s)
            if lo > hi:
                lo, hi = hi, lo
            result.update(range(lo, hi + 1))
        else:
            if not token.isdigit():
                raise ValueError(f"回番号の指定が不正です: {token!r}")
            result.add(int(token))

    if not result:
        raise ValueError("有効な回番号がありません")
    out = sorted(result)
    bad = [n for n in out if n < 1 or n > lecture_count]
    if bad:
        raise ValueError(
            f"範囲外の回番号です: {', '.join(map(str, bad))}（有効範囲は1〜{lecture_count}）"
        )
    return out


def inspect_assessment(path: Path) -> dict[str, Any]:
    """回別問題カードJSONを構造検査する。data.js検査と同じ基準を回別ファイルへ適用する。"""
    if not path.is_file() or path.stat().st_size == 0:
        return {"present": False, "questions": 0, "cards": 0,
                "invalid_choices": 0, "duplicate_choices": 0, "invalid_answers": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"present": True, "parse_error": str(exc), "questions": 0, "cards": 0,
                "invalid_choices": 0, "duplicate_choices": 0, "invalid_answers": 0}

    questions = data.get("questions") if isinstance(data, dict) else None
    cards = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(cards, list):
        cards = data.get("mustKnow") if isinstance(data, dict) else None
    questions = questions if isinstance(questions, list) else []
    cards = cards if isinstance(cards, list) else []

    invalid_choices = duplicate_choices = invalid_answers = 0
    for question in questions:
        if not isinstance(question, dict):
            invalid_choices += 1
            continue
        choices = question.get("choices")
        if not isinstance(choices, list) or len(choices) != 4:
            invalid_choices += 1
            continue
        if len({str(value).strip() for value in choices}) != 4:
            duplicate_choices += 1
        answer = question.get("answer")
        if isinstance(answer, bool) or not isinstance(answer, int) or answer < 0 or answer > 3:
            invalid_answers += 1

    return {
        "present": True,
        "questions": len(questions),
        "cards": len(cards),
        "invalid_choices": invalid_choices,
        "duplicate_choices": duplicate_choices,
        "invalid_answers": invalid_answers,
    }


def validate_lecture(subject: dict[str, Any], lecture: int) -> dict[str, Any]:
    """1講義回分の回別成果物が揃っているかを判定する。"""
    base = Path(subject["base"])
    output = base / "output"
    parts = int(subject["parts_per_lecture"])
    want = [f"{lecture}_{part}" for part in range(1, parts + 1)]

    video_stems = {path.stem for path in nonempty_files(base / "videos", "*.mp4")}
    transcript_stems = {path.stem for path in nonempty_files(output / "transcripts", "*.json")}
    ocr_stems = {path.stem for path in nonempty_files(output / "slide_ocr", "*.json")}

    note = output / "notes" / f"第{lecture:02d}回_超詳細.md"
    assessment = output / "assessment" / f"第{lecture:02d}回.json"
    stats = inspect_assessment(assessment)

    missing_videos = [stem for stem in want if stem not in video_stems]
    missing_transcripts = [stem for stem in want if stem not in transcript_stems]
    missing_ocr = [stem for stem in want if stem not in ocr_stems]
    note_ok = note.is_file() and note.stat().st_size >= NOTE_MIN_BYTES
    assessment_ok = (
        stats["present"]
        and not stats.get("parse_error")
        and stats["questions"] >= QUESTION_MIN
        and stats["cards"] >= CARD_MIN
        and stats["invalid_choices"] == 0
        and stats["duplicate_choices"] == 0
        and stats["invalid_answers"] == 0
    )

    if missing_videos:
        next_subphase = "input"
    elif missing_transcripts:
        next_subphase = "transcription"
    elif missing_ocr:
        next_subphase = "ocr"
    elif not note_ok:
        next_subphase = "note"
    elif not assessment_ok:
        next_subphase = "assessment"
    else:
        next_subphase = "complete"

    blocked = bool(missing_videos)
    status = "done" if next_subphase == "complete" else ("blocked" if blocked else "pending")
    return {
        "lecture": lecture,
        "status": status,
        "next_subphase": next_subphase,
        "blocked": blocked,
        "checks": {
            "videos": not missing_videos,
            "transcripts": not missing_transcripts,
            "ocr": not missing_ocr,
            "note": note_ok,
            "assessment": assessment_ok,
        },
        "missing": {
            "videos": missing_videos,
            "transcripts": missing_transcripts,
            "ocr": missing_ocr,
            "note": not note_ok,
            "assessment": not assessment_ok,
        },
        "counts": {
            "questions": stats["questions"],
            "cards": stats["cards"],
            "invalid_choices": stats["invalid_choices"],
            "duplicate_choices": stats["duplicate_choices"],
            "invalid_answers": stats["invalid_answers"],
        },
        "paths": {"note": str(note), "assessment": str(assessment)},
    }


def validate_lectures(course_id: str, lectures: list[int], project_root: Path) -> dict[str, Any]:
    """指定された回だけをまとめて判定する。"""
    subject = resolve_subject(course_id, project_root)
    requested = sorted(dict.fromkeys(int(n) for n in lectures))
    per = [validate_lecture(subject, lecture) for lecture in requested]

    done = [item["lecture"] for item in per if item["status"] == "done"]
    pending = [item["lecture"] for item in per if item["status"] == "pending"]
    blocked = [item["lecture"] for item in per if item["status"] == "blocked"]
    if blocked:
        overall = "blocked"
    elif pending:
        overall = "incomplete"
    else:
        overall = "complete"

    return {
        "course_id": subject["id"],
        "subject": subject["name"],
        "requested_lectures": requested,
        "status": overall,
        "blocked": bool(blocked),
        "lectures_done": done,
        "lectures_pending": pending,
        "lectures_blocked": blocked,
        "per_lecture": per,
        "subject_obj": subject,
        "expected": {
            "parts_per_lecture": int(subject["parts_per_lecture"]),
            "lecture_count": int(subject["lecture_count"]),
            "questions_per_lecture_min": QUESTION_MIN,
            "cards_per_lecture_min": CARD_MIN,
        },
    }
