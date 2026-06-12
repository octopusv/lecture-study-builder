---
name: setup
description: Gitからcloneした講義分析プロジェクトの初回セットアップを行う。教科データが存在しない状態から、macOS依存、Python環境、Node依存、Whisperモデル、空の教科作業領域を準備・検証する。ユーザーが`/setup`を実行したときに使用する。
disable-model-invocation: true
effort: high
---

# 初回セットアップ

## 実行手順

1. 最初にBashツールで次を実行し、現在の状態を取得する。

```bash
python3 .claude/skills/setup/scripts/setup_project.py \
  --project-root . \
  --check
```

2. 出力されたJSONを確認する。`supported_platform` が偽なら理由を示して停止する。音声認識とOCRの標準構成はApple Silicon Mac向けである。
3. Homebrewがない場合は、公式インストーラーを実行する許可をユーザーへ求める。非公式スクリプトは使用しない。
4. `ffmpeg`、`uv`、`node`、`npm` が不足している場合は、セットアップPythonがHomebrewで不足分だけ導入することを説明し、実行許可を求める。
5. Whisperモデルが未取得なら、数GBのダウンロードが発生することを伝えて許可を求める。
6. 次をBashツールで実行する。

```bash
python3 .claude/skills/setup/scripts/setup_project.py \
  --project-root . \
  --apply \
  --install-system \
  --download-model
```

7. セットアップ中に失敗した工程だけを修正・再実行する。正常な環境やモデルは再作成しない。
8. ルートの `index.html` が存在しなかった場合だけ、`assets/index.html` から公開タイトル「大学授業 自動まとめポータル」の汎用初期ページが生成される。既存の `index.html` は個人用ホームを含めて絶対に上書きしない。
9. 最後に次をBashツールで実行し、`portal_index.exists: true` と `ready: true` を確認する。

```bash
python3 .claude/skills/setup/scripts/setup_project.py \
  --project-root . \
  --check \
  --strict
```

10. 教科が未登録なら、`/setup-course 01 教科名`で追加できることを案内する。登録済み教科があれば、その作業フォルダも不足分だけ復元される。

## 安全条件

- 既存ファイルを削除・上書きしない。
- 既存のルート `index.html` を上書きしない。再実行時も内容を変更しない。
- 動画をダウンロード、移動、複製しない。
- `.gitignore`、Git履歴、リモート設定は変更しない。
- Homebrewやモデル取得などネットワーク・システム変更は、実行前にユーザー承認を得る。
- ローカル教科台帳は `config/subjects.json` を基準とする。存在しなければ空の台帳を生成する。
