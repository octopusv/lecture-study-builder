#!/usr/bin/env python3
"""Assemble data.js / expanded-data.js from per-lecture quiz source JSON.

Each ``<src>/第NN回.json`` holds one lecture:
    {id, title, summary, mustKnow:[[term,detail]...], expanded:[[term,detail]...],
     questions:[[importance,type,basis,title,answer,video,seconds]...]}
This merges them (lecture-number order) into the two data files the site loads,
mirroring app.js' concept-dedup so the validation matches what the page builds.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def norm_key(text: str) -> str:
    return re.sub(r"\s", "", str(text)).lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--title", default="情報社会論 試験対策")
    parser.add_argument("--generated-from", default="全15回・90動画")
    args = parser.parse_args()

    files = sorted(
        args.src.glob("第*.json"),
        key=lambda p: int(re.search(r"\d+", p.stem).group()),
    )
    if not files:
        print("no source files found", file=sys.stderr)
        return 1

    lectures = []
    expanded = {}
    warnings = []
    total_concepts = 0
    total_questions_est = 0

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        lid = int(d["id"])
        must = d["mustKnow"]
        exp = d.get("expanded", [])
        qs = d["questions"]

        # Mirror app.js mergeConcepts(): keep first occurrence by normalized term.
        seen = set()
        merged_details = []
        for term, detail in [*[(t[0], t[1]) for t in must], *[(t[0], t[1]) for t in exp]]:
            key = norm_key(term)
            if key in seen:
                continue
            seen.add(key)
            merged_details.append(detail)
        concepts = len(merged_details)

        # Duplicate details would make a detail-question's 4 choices collapse.
        detail_counts = {}
        for det in merged_details:
            detail_counts[norm_key(det)] = detail_counts.get(norm_key(det), 0) + 1
        if any(v > 1 for v in detail_counts.values()):
            warnings.append(f"第{lid}回: concept説明文に重複あり")
        if concepts < 4:
            warnings.append(f"第{lid}回: concepts {concepts} < 4 (4択生成不可)")
        if len(qs) < 4:
            warnings.append(f"第{lid}回: questions {len(qs)} < 4 (4択生成不可)")
        answers = [q[4] for q in qs]
        if len({norm_key(a) for a in answers}) < len(answers):
            warnings.append(f"第{lid}回: question正解文に重複あり")

        norm_qs = []
        for q in qs:
            importance, qtype, basis, title, answer, video, seconds = q
            norm_qs.append(
                [importance, qtype, basis, title, answer, str(video), int(seconds)]
            )

        lectures.append({
            "id": lid,
            "title": d["title"],
            "summary": d["summary"],
            "mustKnow": [[t[0], t[1]] for t in must],
            "questions": norm_qs,
        })
        expanded[lid] = [[t[0], t[1]] for t in exp]

        total_concepts += concepts
        total_questions_est += concepts * 2 + len(qs)

    data = {
        "meta": {
            "title": args.title,
            "generatedFrom": args.generated_from,
            "note": (
                "「講義内の明示問題」はスライドで実際に提示された問いです。"
                "その他は講義のまとめ・定義・反復から出題可能性を推定しています。"
            ),
        },
        "lectures": lectures,
    }

    args.site.mkdir(parents=True, exist_ok=True)
    (args.site / "data.js").write_text(
        "window.EXAM_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    (args.site / "expanded-data.js").write_text(
        "window.EXPANDED_TERMS = "
        + json.dumps(expanded, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )

    print(f"回数: {len(lectures)}")
    print(f"知識項目(concepts)合計: {total_concepts}")
    print(f"推定4択問題数: {total_questions_est}")
    print(f"推定暗記カード数: {total_questions_est}")
    if warnings:
        print("--- 警告 ---")
        for warning in warnings:
            print(" -", warning)
    else:
        print("検証: 警告なし")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
