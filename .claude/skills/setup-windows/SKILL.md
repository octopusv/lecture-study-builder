---
name: setup-windows
description: Windows環境向けの初回セットアップを行う。macOS専用のApple Vision OCR・mlx_whisperの代わりに、faster-whisper（音声認識）とRapidOCR（スライドOCR）を完全ローカルで準備・検証する。ffmpeg/uv/nodeはwingetで導入し、Python環境・Whisper(CT2)モデル・空の教科作業領域・python3エイリアスを整える。ユーザーが`/setup-windows`を実行したときに使用する。
disable-model-invocation: true
effort: high
---

# 初回セットアップ（Windows）

このSkillはWindows専用である。macOS/Apple Siliconでは代わりに `/setup` を使うこと。
標準構成（Apple Vision＋mlx_whisper）はMac専用のため、Windowsではローカル代替として
faster-whisper と RapidOCR を使う（いずれもローカル処理・追加課金なし・外部送信なし）。

## 前提

- Windows 10/11。`python`（python.org または Microsoft Store 版）が利用可能であること。
  セットアップ最初のコマンドは `python3` ではなく `python` で起動する（`python3`
  エイリアスはこのSkillが後で作成する）。
- システム依存の自動導入には winget（『アプリ インストーラー』）を使う。

## 実行手順

1. 最初にBashツール/ターミナルで次を実行し、現在の状態を取得する。

```bat
python .claude/skills/setup-windows/scripts/setup_project_windows.py --project-root . --check
```

2. 出力JSONを確認する。`supported_platform` が偽（＝Windows以外）なら理由を示して停止する。
3. `winget` が無い場合は、Microsoft Store の『アプリ インストーラー』導入をユーザーへ案内する。非公式スクリプトは使わない。
4. `ffmpeg`、`uv`、`node`、`npm` が不足している場合は、wingetで不足分だけ導入することを説明し、実行許可を求める。
5. 音声認識モデル（faster-whisper用のCT2版 large-v3-turbo, 数GB）が未取得なら、ダウンロードが発生することを伝えて許可を求める。
6. `--install-system` は winget での導入に加えて、`python3` エイリアス（`python` へ転送する `python3.cmd`）を作成し、そのフォルダをユーザーPATHへ追加する。これはユーザー環境変数の変更なので、実行前に許可を求める。許可を得たら次を実行する。

```bat
python .claude/skills/setup-windows/scripts/setup_project_windows.py --project-root . --apply --install-system --download-model
```

7. セットアップ中に失敗した工程だけを修正・再実行する。正常な環境やモデルは再作成しない。
8. ルートの `index.html` が存在しなかった場合だけ、既存setup skillの `assets/index.html` から汎用初期ページが生成される。`index.html` はGit管理外のローカル生成物。既存の `index.html` は絶対に上書きしない。
9. PATH変更を反映するため、**新しいターミナルを開いてから**最終チェックを実行し、`portal_index.exists: true` と `ready: true` を確認する。

```bat
python3 .claude/skills/setup-windows/scripts/setup_project_windows.py --project-root . --check --strict
```

10. 教科が未登録なら、`/setup-course 01 教科名` で追加できることを案内する。登録済み教科があれば作業フォルダも不足分だけ復元される。

## 解析時の注意（Windows）

- 文字起こしは `scripts/transcribe_macro.py` ではなく **`scripts/transcribe_windows.py`**（faster-whisper）を使う。
- スライドOCRは `scripts/ocr_slides.py` ではなく **`scripts/ocr_slides_windows.py`**（RapidOCR）を使う。フレーム抽出は共通の `scripts/extract_frames.py`（ffmpeg）をそのまま使う。
- 上記2スクリプトはOSガードを持ち、Windows以外では即停止する。
- GPU高速化: `transcribe_windows.py` は `--device auto` で搭載GPUを自動判定し、NVIDIA+CUDAがあればGPU(cuda/float16)、無ければCPUで実行する。faster-whisper(CTranslate2)はAMD GPU非対応のためAMD機はCPU動作になる。`--apply` 時、**NVIDIA GPUを検出した場合だけ** `requirements-windows-cuda.txt`（cuBLAS/cuDNN）を `.venv` へ自動導入する（AMD/CPUのみの環境では導入しない）。導入済みなら再実行時はスキップ。
- `/analyze-course` `/analyze-lectures` のStopフックは `python3` を叩くため、手順6で作る `python3` エイリアスが必要。エイリアス作成後は新しいシェルで有効になる。
- 音声認識モデルは既定で `deepdml/faster-whisper-large-v3-turbo-ct2`。別のCT2モデルを使う場合は `transcribe_windows.py` と `setup_project_windows.py` の `MODEL_REPO` を合わせて変更する。

## 安全条件

- 既存ファイルを削除・上書きしない。既存のルート `index.html` も上書きしない。
- 既存の `setup` skill、`analyze-course`/`analyze-lectures` skill、既存 `scripts/*.py`（macOS版）は変更しない。
- 動画をダウンロード、移動、複製しない。
- `.gitignore`、Git履歴、リモート設定は変更しない。
- winget導入・モデル取得・PATH変更などシステム・環境変数の変更は、実行前にユーザー承認を得る。
- ローカル教科台帳は `config/subjects.json` を基準とする。存在しなければ空の台帳を生成する。
