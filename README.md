# 大学授業 自動まとめポータル

大学の授業動画を入力するだけで、**文字起こし・スライドOCR・詳細ノート・統合まとめ・4択問題・暗記カード・教科別の学習Webサイト**までを自動生成する Claude Code 向けワークスペースです。

特定の大学・学部・教科に依存しません。任意の教科を登録して使え、元動画やOCR全文などの私的データは Git 管理外として扱います。

---

## 主な機能

-  **音声認識** — `mlx_whisper`（`large-v3-turbo`）による日本語文字起こし
-  **スライドOCR** — `ffmpeg` でフレーム抽出し、macOS 標準の Apple Vision で認識
-  **講義ノート** — 回別の超詳細ノートと、全回を読み解いて再構成した統合まとめ
-  **試験対策** — 講義内容に基づく4択問題と双方向の暗記カード
-  **学習サイト** — 検索・絞り込み・採点・解説・進捗保存に対応した教科別サイト＋教科一覧ポータル
-  **再開可能** — 中断しても、未完了の工程だけを自動で検出して続きから再開
-  **特定回だけ先行分析** — `/analyze-lectures` で指定した講義回だけを先に処理。続けて全体を回すと、済んだ回は自動でスキップ

---

## 動作環境

| 項目 | 要件 |
|------|------|
| プラットフォーム | Apple Silicon 搭載 Mac |
| 実行環境 | Claude Code |
| パッケージ管理 | Homebrew（`ffmpeg` / `uv` / `node`） |
| Python | `uv` が管理する仮想環境（`.venv`） |

> `/setup` が不足分のみを導入・検証します（Homebrew 本体だけは安全のため自動導入せず、未導入時は公式インストーラーを案内します）。

---

## クイックスタート

```text
/setup                     # 環境構築・検証（ffmpeg, uv, node, .venv, Whisperモデル）
/setup-course 01 教科名     # 教科を登録し、作業フォルダを作成
```

作成された `教科別/01_教科名/videos/` に授業動画（既定は `1_1.mp4`〜`15_6.mp4`）を配置し、解析を開始します。

```text
/analyze-course 01         # 文字起こし→OCR→ノート→まとめ→問題→サイトまで生成
```

`/analyze-course` は既存の正常な成果物を再利用し、欠損・未完了の工程から再開します。完了条件を満たすまで Stop フックが自動で作業を継続します（連続継続の上限に達したら同じコマンドを再実行）。

### 特定の回だけ先に分析する

教科全体ではなく、一部の講義回だけを先に仕上げたいときは `/analyze-lectures` を使います。

```text
/analyze-lectures 01 1-5     # 第1〜5回だけを処理（5 / 1-5 / 1,3,5 / 1-3,8 を指定可）
```

指定した回の**文字起こし・OCR・回別ノート・4択問題・暗記カード**を、`/analyze-course` と同じ場所（`output/transcripts/`・`output/notes/`・`output/assessment/第NN回.json` など）に生成して止まります。統合まとめ・サイト・最終横断監査は対象外です。

あとで `/analyze-course 01` を実行すると、ここで仕上げた回は**自動的にスキップ**され、残りの回と全体の統合（まとめ・サイト・横断監査）だけが処理されます。`/analyze-lectures` 自身も、未完了の回が揃うまで Stop フックが自動継続します。

---

## ディレクトリ構成

```text
.
├── CLAUDE.md              # 処理方針・品質基準・公開分離ルール（最重要ドキュメント）
├── config/
│   ├── subjects.example.json   # 公開テンプレート用の空台帳
│   └── subjects.json           # ローカル教科台帳（Git管理外）
├── scripts/              # 共通処理（教科に依存しない汎用スクリプト）
│   ├── transcribe_macro.py     # 音声認識
│   ├── extract_frames.py       # フレーム抽出
│   ├── ocr_slides.py           # Apple Vision OCR
│   ├── build_detailed_notes.py # 詳細ノート生成
│   ├── build_assessment_data.py# 問題・カードのサイトデータ化
│   └── build_site_data.py      # サイトデータ生成
├── .claude/skills/       # /setup・/setup-course・/analyze-course・/analyze-lectures
├── portal.css            # ポータル共通スタイル
├── index.html            # 教科一覧ポータル（ローカル生成・Git管理外）
└── 教科別/               # 教科ごとの動画と成果物（Git管理外）
```

---

## 処理パイプライン

`/analyze-course` は、教科台帳を基準に次の工程を順に進めます。各工程は再実行可能で、正常な成果物はスキップされます。

| 工程 | 内容 | 主な出力 |
|------|------|----------|
| 1. 文字起こし | 日本語音声認識（temperature 0・教科別 initial_prompt） | `output/transcripts/*.json` |
| 2. スライドOCR | 30秒ごとにフレーム抽出 → Apple Vision で日英認識 | `output/slide_ocr/*.json` |
| 3. 回別ノート | 回ごとの超詳細ノートを生成 | `output/notes/第NN回_超詳細.md` |
| 4. 統合まとめ | 全回を読み解いて再構成した学習用解説書・トピック一覧・全記録 | `output/<教科>_授業内容まとめ_超詳細.md` ほか |
| 5. 問題・カード | 回別に作問 → 品質監査 → 横断監査 | `output/assessment/*.json` |
| 6. サイト | 教科に合わせた学習サイトを構築 | `site/`（`index.html` / `app.js` / `styles.css` / `data.js`） |
| 7. ポータル更新 | ルート `index.html` の該当教科カードを実数で更新 | `index.html` |

### 品質を担保する仕組み

問題・暗記カード・まとめは、単語リストからの機械生成では完了とせず、専用のサブエージェントが講義内容を実際に読んで執筆・監査します。

- `lecture-content-reconstructor`（Sonnet） — 回別の詳細再構成
- `lecture-assessment-author`（Sonnet） — 問題・選択肢・解説・暗記カードの執筆
- `assessment-quality-auditor`（Sonnet） — 講義MDと照合した回別の品質監査
- `course-integration-editor`（Opus） — 全回横断の統合編集と最終監査

最後に `validate_course.py` が、動画・文字起こし・OCR・ノート・問題数・カード数・選択肢の妥当性などを機械検証します。

---

## データの扱い

私的データはリポジトリに含めません（`.gitignore` 済み）。

- `教科別/`（動画・文字起こし・OCR全文・生成途中の成果物）
- `config/subjects.json`（ローカル教科台帳）
- `index.html` / `PROGRESS_*.md` / `GOAL_*.txt`
- `.venv/` / `node_modules/` / `.claude/course-analysis-runs/` / `.claude/lecture-analysis-runs/`

公開テンプレートには空の `config/subjects.example.json` のみを含めます。

### 公開する場合の3層分離

クラウド公開時は、ワークスペースをそのまま配置せず、必ず生成物を分離します。

1. **公開版** — 許可リスト方式で、公開可能な問題・カード・要点のみを生成
2. **非公開クラウド版** — Cloudflare Access の認証下でのみ閲覧できる詳細学習サイト
3. **ローカル完全版** — 動画・OCR・文字起こし・超詳細MDを含む（`127.0.0.1` のみで配信）

詳しい分離ルールと公開前検査は `CLAUDE.md` を参照してください。

---

## 参考

処理方針、作問・暗記カードの作成手順、Webサイトの品質基準、検証と完了条件、公開版/非公開版の分離方法は、すべて **[`CLAUDE.md`](./CLAUDE.md)** に定義しています。
