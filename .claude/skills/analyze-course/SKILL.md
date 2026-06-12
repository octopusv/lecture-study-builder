---
name: analyze-course
description: 教科台帳に登録された任意教科の講義動画を対象に文字起こし、OCR、詳細ノート、AI再構成まとめ、4択問題、暗記カード、Webサイトを生成・監査・検証する。`/analyze-course 04`のように手動実行する。
argument-hint: "<教科ID>"
arguments:
  - course_id
disable-model-invocation: true
effort: high
hooks:
  Stop:
    - hooks:
        - type: command
          command: "python3 .claude/skills/analyze-course/scripts/stop_check.py --project-root ."
          timeout: 120
---

# 講義教材の自動生成

## 実行コンテキスト

引数から教科IDを確認し、次をBashツールで実行する。`<教科ID>` は引数の値へ置き換え、推測しない。`--session-id` には環境変数 `$CLAUDE_CODE_SESSION_ID` を必ず渡す。これでStopフックの自動継続が有効になる（状態ファイルがこのIDで作成され、Stopフックが同じIDで照合するため）。スクリプト側も同環境変数を既定値にするため省略してもよいが、明示を推奨する。

```bash
python3 .claude/skills/analyze-course/scripts/start_run.py \
  "<教科ID>" --project-root . --session-id "$CLAUDE_CODE_SESSION_ID"
```

## 手順

1. 上のJSONで対象教科と現在の `next_phase` を確認する。IDを推測しない。
2. `CLAUDE.md` と [workflow.md](references/workflow.md) を読み、対象教科だけを処理する。
3. 既存の正常な成果物を再利用し、欠損・不適合部分から再開する。動画を変更、複製、再エンコード、削除しない。
4. 長時間処理は再開可能に実行し、終了コード、ログ、成果物件数を確認する。
5. 回別内容再構成は `lecture-content-reconstructor` Sonnet、作問は `lecture-assessment-author` Sonnet、回別監査は `assessment-quality-auditor` Sonnetへ分担する。
6. 全講義回の授業まとめ統合と最終横断監査は、別起動の `course-integration-editor` Opusへ任せる。
7. UIを対象教科向けに設計し、PCと幅390pxで実動確認する。
8. 最後に次を実行し、失敗項目をすべて修正する。

```bash
python3 .claude/skills/analyze-course/scripts/validate_course.py "<教科ID>" \
  --project-root . --write-report
```

9. 機械検証が成功したら、実施内容、Sonnet・Opusの担当、問題数、カード数、監査修正数、UI確認結果を最終報告する。

Stopフックが各ターン終了時に同じ検証を行う。バックグラウンド処理（文字起こし・OCR・サブエージェント等）の実行中はブロックせず待機し、ジョブ完了の通知で再開する（毎ターンのブロックによるレート制限・トークン浪費を避けるため）。バックグラウンド処理がなく未完了の場合だけ、理由と次工程を返して作業を継続する。長時間のバックグラウンド待ちは、`run_in_background` のジョブ（処理本体や完了待ちループ）を起こし役にして、その完了通知で次工程へ進む。Claude Codeの保護機構で連続継続は最大8回なので、上限で停止した場合は同じ `/analyze-course <ID>` を再実行して続きから再開する。
