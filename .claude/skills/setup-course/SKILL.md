---
name: setup-course
description: 任意の教科IDと教科名を教科台帳へ登録し、`教科別/`配下に動画・出力・サイト用の作業フォルダを作る。`/setup-course 01 心理学`のように新しい教科を追加するときに使用する。
argument-hint: "<教科ID> <教科名>"
arguments:
  - course_id
  - course_name
disable-model-invocation: true
model: sonnet
effort: high
---

# 教科追加

次を実行する。

!`python3 "${CLAUDE_SKILL_DIR}/scripts/register_course.py" "$course_id" "$course_name" --project-root "${CLAUDE_PROJECT_DIR}"`

## 完了確認

1. JSONの `created` と `course` を確認する。
2. `config/subjects.json` に教科ID、教科名、ディレクトリ、講義回数、各回の動画本数が登録されていることを確認する。
3. 対象教科の `videos/`、`output/`、`site/` と出力用サブディレクトリが存在することを確認する。
4. 動画は自動取得しない。利用者へ `videos/` に配置するよう案内する。
5. 標準の動画構成は15回×各6本、命名は `1_1.mp4` から `15_6.mp4`。異なる構成の場合は `config/subjects.json` の `lecture_count`、`parts_per_lecture`、`expected_videos` を変更する。
6. 配置後は `/analyze-course <教科ID>` で分析を開始できる。

## 安全条件

- 同じIDが異なる教科名で登録済みなら上書きせず停止する。
- 既存の教科ファイルや動画を削除・移動しない。
- 教科名にパス区切りや制御文字を許可しない。
