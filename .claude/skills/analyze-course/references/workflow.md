# 講義分析ワークフロー

## 基本方針

- 対象は `start_run.py` が返した1教科だけとする。
- `CLAUDE.md` の品質基準、公開・非公開分離、モデル分担を優先する。
- 各工程の前後で `validate_course.py` を実行し、`next_phase` を更新する。
- 既存の正常な成果物を上書きしない。欠損、空ファイル、不合格項目だけを再処理する。
- 同じ出力ファイルを複数エージェントに同時編集させない。

## 工程

### 1. input

- `config/subjects.json` の `lecture_count`、`parts_per_lecture`、`expected_videos` に対応する動画が揃っていることを確認する。
- 命名、重複、欠損、空ファイルを検査する。
- 入力不備は推測で補わず、停止して具体的に報告する。

### 2. transcription

- `.venv`、`scripts/transcribe_macro.py`、`mlx_whisper` を再利用・汎用化する。
- 各動画について空でないJSONを保存する。
- 既存の正常なJSONはスキップし、失敗動画だけ再実行する。

### 3. ocr

- `scripts/extract_frames.py` と `scripts/ocr_slides.py` を再利用する。
- Apple Vision OCRを用い、各動画について空でないJSONを保存する。
- フレームはOCR確認後に削除可能だが、動画は削除しない。

### 4. notes

- 教科台帳の `parts_per_lecture` 本を各回ごとに統合し、`output/notes/第01回_超詳細.md` から最終講義回まで作る。
- OCR記載と講師説明を区別し、動画番号と時刻を保持する。
- 全講義回を連結した参照用 `<教科名>_講義全記録.md` を作る。
- `lecture-content-reconstructor` Sonnetを1回単位で起動し、回別の再構成原稿を競合しない個別ファイルへ出力する。

### 5. synthesis

- `course-integration-editor` Opusを起動し、Sonnetの回別再構成原稿を主入力として `<教科名>_授業内容まとめ_超詳細.md` を執筆する。
- 全記録の単純結合は禁止する。
- 統合執筆とは別起動のOpusで、重複、矛盾、欠落、OCR誤認、試験重要度を監査する。
- `output/validation/opus_cross_audit.md` に監査対象、修正内容、残る不確実性を記録する。

### 6. assessment

- 回別の問題・カードは `output/assessment/第NN回.json` を唯一の回別保存先とし、`site/data.js` はそこから組み立てる。
- 既に正常な `output/assessment/第NN回.json` がある回（`/analyze-lectures` で先行生成した回など）はスキップし、欠損・不正な回だけを作問する。
- 各回を `lecture-assessment-author` Sonnetへ分担する。
- 4択は各回20〜30問を目安とし、全体件数は講義回数に応じて決める。
- カードは各回15〜25枚を目安とし、全体件数は講義回数に応じて決め、、特に密度が高い回だけ30枚程度まで許容する。
- `assessment-quality-auditor` Sonnetを別起動し、回別に根拠、一意性、誤答品質、重複、網羅性を監査・修正する。
- `course-integration-editor` Opusをさらに別起動し、全講義回横断の重複、偏り、出題漏れ、試験重要度を監査する。
- 件数が目安外でも講義密度上妥当な場合は、Opusが `output/validation/count_exceptions.json` に理由を記録する。

例:

```json
{
  "approved_by_opus": true,
  "question_reason": "講義密度に基づく具体的理由",
  "card_reason": "講義密度に基づく具体的理由"
}
```

### 7. site

- `site/index.html`、`styles.css`、`app.js`、`data.js` を完成させる。
- 検索、講義回・重要度絞り込み、40問程度のページ分割、ランダム、未回答、即時採点、解説、双方向カード、進捗保存を実装する。
- 対象教科に固有の洗練されたUIにする。
- PCと幅390pxで主要操作とコンソールを確認する。
- ルート `index.html` がなければ、先に `/setup` と同じ汎用初期ページ生成処理を実行する。
- 既存ホームの見出し、デザイン、他教科カードを維持し、対象カードの実数、状態、リンクだけを更新する。
- 他教科のカード、リンク、集計値を壊さない。

### 8. final

- `output/validation/final_report.md` に全検証結果を記録する。
- `validate_course.py --write-report` が成功するまで修正する。
- 公開版を作る場合は、`CLAUDE.md` の許可リスト方式と非公開資料除外を守る。
