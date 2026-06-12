---
name: analyze-lectures
description: 教科台帳に登録された教科の「特定の講義回だけ」を対象に、文字起こし、OCR、回別ノート、回別の4択問題・暗記カードを生成・監査する。生成物は正規パスへ保存され、後で /analyze-course を回すと済んだ回は自動でスキップされる。`/analyze-lectures 04 1-5` のように手動実行する。
argument-hint: "<教科ID> <回指定>"
arguments:
  - course_id
  - lectures
disable-model-invocation: true
effort: high
hooks:
  Stop:
    - hooks:
        - type: command
          command: "python3 .claude/skills/analyze-lectures/scripts/stop_check.py --project-root ."
          timeout: 120
---

# 特定回だけの講義分析

指定した講義回だけを対象に、回別成果物（文字起こし・OCR・回別ノート・回別の4択問題と暗記カード）を生成する。これらは `/analyze-course` と同じ正規パスへ保存するため、後で教科全体を分析するときに、ここで仕上げた回は自動的にスキップされる。

このスキルは回別成果物までを担当する。**統合まとめ（授業内容まとめ超詳細版）、Webサイト、最終横断監査は本スキルの対象外**で、教科全体を仕上げるときに `/analyze-course <教科ID>` が全回をまとめて統合・構築する。

## 実行コンテキスト

引数から教科IDと回指定を確認し、次をBashツールで実行する。`<教科ID>` と `<回指定>` は引数の値へ置き換え、推測しない。`--session-id` には環境変数 `$CLAUDE_CODE_SESSION_ID` を必ず渡す。これでStopフックの自動継続が有効になる（状態ファイルがこのIDで作成され、Stopフックが同じIDで照合するため）。

回指定は単一回・範囲・カンマ区切り・混在を許容する。例: `5` / `1-5` / `1,3,5` / `1-3,8`。

```bash
python3 .claude/skills/analyze-lectures/scripts/start_run.py \
  "<教科ID>" "<回指定>" --project-root . --session-id "$CLAUDE_CODE_SESSION_ID"
```

出力の `lectures_to_process` が今回処理すべき回、`lectures_to_skip` が既に完成していてスキップする回、`lectures_blocked` が動画不足で進めない回である。`per_lecture` に各回の `next_subphase`（input→transcription→ocr→note→assessment）が入る。

## 手順

1. 上のJSONで対象教科と、処理対象 `lectures_to_process` を確認する。IDも回も推測しない。
2. `CLAUDE.md` と [analyze-course のワークフロー](../analyze-course/references/workflow.md) の品質基準・モデル分担を読む。工程の中身（文字起こし・OCR・回別ノート・作問の作法）はそこに従う。
3. `lectures_to_skip` の回は触らない。`lectures_to_process` の回だけを、各回の `next_subphase` から再開する。既存の正常な成果物は再利用し、欠損・空ファイルだけ再処理する。動画は変更・複製・再エンコード・削除しない。
4. 各回について次を順に満たす。すべて正規パスへ書き、回番号で命名する。
   - **文字起こし**: `.venv` と `scripts/transcribe_macro.py`、`mlx_whisper` を再利用し、その回の各動画について空でない `output/transcripts/<回>_<パート>.json` を作る。
   - **OCR**: `scripts/extract_frames.py` と `scripts/ocr_slides.py`（Apple Vision OCR）を再利用し、`output/slide_ocr/<回>_<パート>.json` を作る。
   - **回別ノート**: `lecture-content-reconstructor` Sonnetを1回1エージェントで起動し、`output/notes/第NN回_超詳細.md` を作る。複数回を1エージェントへまとめて読ませない。
   - **回別の問題・カード**: `lecture-assessment-author` Sonnetを1回1エージェントで起動し、その回の詳細ノートを根拠に4択問題・暗記カードを執筆して `output/assessment/第NN回.json` に保存する。スキーマは既存教科に合わせ、`{ "id", "title", "summary", "questions": [{ "q", "choices"(4個・重複なし), "answer"(0-3), "explanation", "importance", "type", "video", "seconds", "source" }], "cards": [...] }` とする。問題は各回20〜30問、カードは各回15〜25枚を目安とし、水増しはしない。
5. 作問後は必ず別起動の `assessment-quality-auditor` Sonnetを1回単位で起動し、正解の一意性、誤答の妥当性、講義との整合、重複、網羅性を監査・修正する。同じエージェントの自己採点で完了しない。
6. サブエージェントの成果はそのまま採用せず、主担当が正確性・重複・欠損・選択肢品質・ファイル整合を最終確認して統合する。
7. 1回の詳細ノートが極端に大きい、コンテキスト残量警告が出る、出力が途中で切れる場合は、その回を動画1〜3と4〜6などの節へ分割して別エージェントへ割り当て、別の統合担当が重複を除いてまとめる。
8. 独立した回・工程は積極的に並列化する。各サブエージェントの担当回と出力先を明確にし、同じファイルを同時編集させない。

統合まとめ・サイト・最終横断監査・ポータル更新・公開版生成はここでは行わない。これらは教科全体を対象にする `/analyze-course` の担当である。

## 完了確認

最後に次を実行し、指定回の `status` が `complete` になることを確認する。`pending` の回が残る場合は、その回の `next_subphase` を処理してから再実行する。

```bash
python3 .claude/skills/analyze-lectures/scripts/validate_lectures.py \
  "<教科ID>" "<回指定>" --project-root .
```

確認できたら、処理した回、スキップした回、Sonnet担当（再構成・作問・監査）、各回の問題数・カード数・監査修正数を日本語で最終報告する。「この教科全体を仕上げるには `/analyze-course <教科ID>` を実行する」ことも伝える。

Stopフックが各ターン終了時に同じ回別検証を行う。バックグラウンド処理（文字起こし・OCR・サブエージェント等）の実行中はブロックせず待機し、ジョブ完了の通知で再開する。バックグラウンド処理がなく未完了の場合だけ、未完了の回と次工程を返して作業を継続する。Claude Codeの保護機構で連続継続は最大8回なので、上限で停止した場合は同じ `/analyze-lectures <教科ID> <回指定>` を再実行して続きから再開する。
