#!/usr/bin/env python3
"""Assemble data.js from per-lecture authored assessment JSON and validate.

Each ``<src>/第NN回.json`` is WRITTEN by the lecture-assessment-author agent
(and fixed by assessment-quality-auditor) with explicitly authored questions:
    {
      "id": N, "title": "...", "summary": "...",
      "questions": [
        {"q","choices":[4],"answer":<0-3>,"explanation","importance","type",
         "video","seconds","source"} ...
      ],
      "cards": [
        {"front","back","importance","video","seconds","source"} ...
      ]
    }
This validates every question (exactly 4 distinct choices, valid answer index)
and emits site/data.js as a self-contained window.EXAM_DATA.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s", "", str(text)).lower()


# 監査・執筆エージェントの出力で日英が混在した type を英語キーへ正規化する。
# site/app.js の typeLabels が英語キー→日本語表示の変換を持つ。
TYPE_MAP = {
    "定義": "definition", "分類": "classification", "比較": "comparison",
    "説明": "explanation", "因果": "cause", "影響": "effect", "事例": "case",
    "具体例": "case", "論点": "issue", "条件": "issue", "前提": "issue",
    "制度・法": "law", "制度": "law", "人物": "person",
    "人物と著作": "person", "人物と理論": "person", "人物と業績": "person",
    "学派": "school", "経緯": "history", "歴史": "history", "事実": "history",
    "手法": "method", "応用": "application", "適用": "application",
    "総合": "synthesis", "読解": "reading", "課題": "issue", "批判": "critique",
    "計算": "calculation", "並べ替え": "order", "順序": "order",
    "正誤": "judgement", "誤り指摘": "judgement", "年代": "chronology",
    "概念": "concept",
}

# importance を high / medium の2値へ正規化する。日英・数値・別表記が混在しても吸収する。
IMPORTANCE_MAP = {
    "high": "high", "高": "high", "高い": "high", "最重要": "high",
    "★★★": "high", "3": "high",
    "medium": "medium", "中": "medium", "重要": "medium",
    "普通": "medium", "標準": "medium",
    "2": "medium", "low": "medium", "低": "medium", "低い": "medium", "1": "medium",
}


def norm_type(value: str) -> str:
    v = str(value or "").strip()
    return TYPE_MAP.get(v, v)


def norm_importance(value) -> str:
    v = str(value).strip()
    return IMPORTANCE_MAP.get(v, "medium")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--title", default="情報社会論 試験対策")
    parser.add_argument("--generated-from", default="全15回・90動画")
    parser.add_argument(
        "--eras-json",
        type=Path,
        help="任意。{'eras':[{label,lectures,blurb}], 'lectureEra':{'1':label,...}} 形式。"
        "指定すると各回に era、トップレベルに eras を付与する（経済言説史の時代フィルタ用）。",
    )
    args = parser.parse_args()

    eras_meta = []
    lecture_era = {}
    if args.eras_json and args.eras_json.exists():
        ej = json.loads(args.eras_json.read_text(encoding="utf-8"))
        eras_meta = ej.get("eras", [])
        lecture_era = {str(k): v for k, v in ej.get("lectureEra", {}).items()}

    files = sorted(
        args.src.glob("第*.json"),
        key=lambda p: int(re.search(r"\d+", p.stem).group()),
    )
    if not files:
        print("no source files found", file=sys.stderr)
        return 1

    lectures = []
    errors = []
    total_q = 0
    total_c = 0

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        lid = int(d["id"])
        questions = d.get("questions", [])
        cards = d.get("cards", [])

        clean_q = []
        for i, q in enumerate(questions):
            choices = q.get("choices", [])
            answer = q.get("answer")
            where = f"第{lid}回 Q{i}"
            if len(choices) != 4:
                errors.append(f"{where}: 選択肢が{len(choices)}個")
                continue
            if len({norm(c) for c in choices}) != 4:
                errors.append(f"{where}: 選択肢重複")
                continue
            if not isinstance(answer, int) or not (0 <= answer <= 3):
                errors.append(f"{where}: 正解index無効({answer})")
                continue
            if not str(q.get("q", "")).strip() or not str(q.get("explanation", "")).strip():
                errors.append(f"{where}: 問題文/解説が空")
                continue
            item = {
                "id": f"q-{lid}-{i}",
                "q": q["q"],
                "choices": choices,
                "answer": answer,
                "explanation": q["explanation"],
                "importance": norm_importance(q.get("importance", "medium")),
                "type": norm_type(q.get("type", "")),
                "video": q.get("video", ""),
                "seconds": int(q.get("seconds", 0) or 0),
                "source": q.get("source", ""),
            }
            tags = [str(t).strip() for t in (q.get("tags") or []) if str(t).strip()]
            if tags:
                item["tags"] = tags
            clean_q.append(item)

        clean_c = []
        for i, c in enumerate(cards):
            if not str(c.get("front", "")).strip() or not str(c.get("back", "")).strip():
                errors.append(f"第{lid}回 C{i}: カード表裏が空")
                continue
            card = {
                "id": f"c-{lid}-{i}",
                "front": c["front"],
                "back": c["back"],
                "importance": norm_importance(c.get("importance", "medium")),
                "video": c.get("video", ""),
                "seconds": int(c.get("seconds", 0) or 0),
                "source": c.get("source", ""),
            }
            ctags = [str(t).strip() for t in (c.get("tags") or []) if str(t).strip()]
            if ctags:
                card["tags"] = ctags
            clean_c.append(card)

        lecture = {
            "id": lid,
            "title": d["title"],
            "summary": d["summary"],
            "questions": clean_q,
            "cards": clean_c,
        }
        era = lecture_era.get(str(lid)) or d.get("era")
        if era:
            lecture["era"] = era
        lectures.append(lecture)
        total_q += len(clean_q)
        total_c += len(clean_c)

    data = {
        "meta": {
            "title": args.title,
            "generatedFrom": args.generated_from,
            "note": "全問が講義の詳細ノートを根拠に執筆・監査されています。",
        },
        "lectures": lectures,
    }
    if eras_meta:
        data["eras"] = eras_meta
    args.site.mkdir(parents=True, exist_ok=True)
    (args.site / "data.js").write_text(
        "window.EXAM_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )

    print(f"回数: {len(lectures)}")
    for l in lectures:
        print(f"  第{l['id']:2d}回 {l['title']}: 問題{len(l['questions'])} / カード{len(l['cards'])}")
    print(f"4択問題 合計: {total_q}")
    print(f"暗記カード 合計: {total_c}")
    if errors:
        print(f"--- 検証エラー {len(errors)}件 ---")
        for e in errors[:40]:
            print(" -", e)
        return 1
    print("検証: 全問4択・重複なし・正解index有効 (エラー0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
