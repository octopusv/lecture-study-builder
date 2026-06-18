#!/usr/bin/env python3
"""Windows専用の初回セットアップ。

macOS版 .claude/skills/setup/scripts/setup_project.py を手本に、OS依存部分だけを
差し替えたローカル代替。音声認識は faster-whisper、OCRは RapidOCR を使い、いずれも
完全ローカル・追加課金なしで動かす。システム依存は Homebrew ではなく winget で導入する。
教科台帳生成・作業フォルダ復元・index.html テンプレート生成のクロスプラットフォーム部分は
mac版と同じ思想で実装している。本スクリプトはWindows以外では --apply できない。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# winget のパッケージID。npm は node 同梱。
SYSTEM_WINGET = {
    "ffmpeg": "Gyan.FFmpeg",
    "uv": "astral-sh.uv",
    "node": "OpenJS.NodeJS",
}
# ready 判定に必要な実コマンド（winget 自体は導入器なので必須に含めない）。
REQUIRED_COMMANDS = ("ffmpeg", "uv", "node", "npm")
REQUIRED_PYTHON_PACKAGES = ("faster_whisper", "rapidocr_onnxruntime", "huggingface_hub")
COURSE_DIRECTORIES = (
    "videos",
    "output",
    "output/transcripts",
    "output/slide_frames",
    "output/slide_ocr",
    "output/notes",
    "output/summary_sections",
    "output/quiz_src",
    "output/assessment",
    "output/validation",
    "site",
)
MODEL_REPO = "deepdml/faster-whisper-large-v3-turbo-ct2"
REQUIREMENTS_NAME = "requirements-windows.txt"
# 既存 setup skill の汎用初期ページテンプレートをそのまま流用する（無改造）。
PORTAL_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "setup" / "assets" / "index.html"
)
SHIM_DIR = Path.home() / ".zen-shims"


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def venv_python(project_root: Path) -> Path:
    return project_root / ".venv" / "Scripts" / "python.exe"


def model_cache_dir_name() -> str:
    return "models--" + MODEL_REPO.replace("/", "--")


def model_cache_path() -> Path:
    explicit = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser() / model_cache_dir_name()
    hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
    return hf_home.expanduser() / "hub" / model_cache_dir_name()


def model_cached() -> bool:
    snapshots = model_cache_path() / "snapshots"
    return snapshots.is_dir() and any(
        path.is_file() and path.stat().st_size > 0 for path in snapshots.rglob("*")
    )


def ensure_registry(project_root: Path) -> Path:
    path = project_root / "config" / "subjects.json"
    if path.is_file():
        return path
    example = project_root / "config" / "subjects.example.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = example.read_text(encoding="utf-8") if example.is_file() else "{}\n"
    path.write_text(content, encoding="utf-8")
    return path


def ensure_portal_index(project_root: Path) -> Path:
    path = project_root / "index.html"
    if path.exists():
        return path
    if not PORTAL_TEMPLATE.is_file():
        raise RuntimeError(f"汎用初期ページのテンプレートがありません: {PORTAL_TEMPLATE}")
    shutil.copyfile(PORTAL_TEMPLATE, path)
    return path


def load_subjects(project_root: Path) -> dict[str, dict[str, Any]]:
    path = project_root / "config" / "subjects.json"
    if not path.is_file():
        raise RuntimeError(f"ローカル教科台帳がありません: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("config/subjects.jsonの形式が不正です")
    return value


def python_packages(python: Path) -> dict[str, bool]:
    if not python.is_file():
        return {name: False for name in REQUIRED_PYTHON_PACKAGES}
    code = (
        "import importlib.util,json;"
        f"mods={REQUIRED_PYTHON_PACKAGES!r};"
        "print(json.dumps({m: importlib.util.find_spec(m) is not None for m in mods}))"
    )
    completed = subprocess.run([str(python), "-c", code], capture_output=True, text=True)
    try:
        return json.loads(completed.stdout) if completed.returncode == 0 else {
            name: False for name in REQUIRED_PYTHON_PACKAGES
        }
    except json.JSONDecodeError:
        return {name: False for name in REQUIRED_PYTHON_PACKAGES}


def inspect(project_root: Path) -> dict[str, Any]:
    supported = platform.system() == "Windows"
    commands = {
        name: bool(shutil.which(name))
        for name in ("winget", "ffmpeg", "uv", "node", "npm")
    }
    python = venv_python(project_root)
    packages = python_packages(python)
    registry_path = project_root / "config" / "subjects.json"
    portal_path = project_root / "index.html"
    requirements_ok = (project_root / REQUIREMENTS_NAME).is_file()

    try:
        subjects = load_subjects(project_root)
        registry_ok, registry_error = True, None
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        subjects, registry_ok, registry_error = {}, False, str(exc)

    course_state: dict[str, Any] = {}
    for course_id, subject in subjects.items():
        base = project_root / subject.get("directory", "")
        missing = [name for name in COURSE_DIRECTORIES if not (base / name).is_dir()]
        course_state[course_id] = {
            "name": subject.get("name", ""),
            "directory": subject.get("directory", ""),
            "exists": base.is_dir(),
            "missing_directories": missing,
        }

    npm_required = (project_root / "package-lock.json").is_file()
    node_modules_ok = not npm_required or (project_root / "node_modules").is_dir()
    course_root_ok = (project_root / "教科別").is_dir()
    python3_alias = bool(shutil.which("python3"))
    ready = bool(
        supported
        and registry_ok
        and requirements_ok
        and all(commands[name] for name in REQUIRED_COMMANDS)
        and python.is_file()
        and all(packages.values())
        and model_cached()
        and node_modules_ok
        and course_root_ok
        and portal_path.is_file()
        and all(not item["missing_directories"] for item in course_state.values())
    )
    return {
        "ready": ready,
        "supported_platform": supported,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "version": platform.version(),
        },
        "commands": commands,
        "venv_exists": python.is_file(),
        "python_packages": packages,
        "requirements_file": requirements_ok,
        "whisper_model": {
            "repo": MODEL_REPO,
            "cached": model_cached(),
            "cache_path": str(model_cache_path()),
        },
        "node_modules": node_modules_ok,
        "python3_alias": python3_alias,
        "course_root": course_root_ok,
        "portal_index": {
            "path": str(portal_path),
            "exists": portal_path.is_file(),
        },
        "subject_registry": {
            "path": str(registry_path),
            "valid": registry_ok,
            "error": registry_error,
            "count": len(subjects),
        },
        "courses": course_state,
    }


def ensure_system_dependencies() -> None:
    winget = shutil.which("winget")
    if not winget:
        raise RuntimeError(
            "wingetがありません。Microsoft Store の『アプリ インストーラー』を導入するか、"
            "ffmpeg・uv・node を手動でインストールして再実行してください"
        )
    for command, package_id in SYSTEM_WINGET.items():
        if not shutil.which(command):
            run([
                winget, "install", "--id", package_id, "-e",
                "--source", "winget",
                "--accept-package-agreements", "--accept-source-agreements",
            ])
    if not shutil.which("npm"):
        run([
            winget, "install", "--id", SYSTEM_WINGET["node"], "-e",
            "--source", "winget",
            "--accept-package-agreements", "--accept-source-agreements",
        ])


def ensure_python3_shim() -> None:
    """analyze-course/analyze-lectures のStopフックが叩く `python3` を解決させる。

    既存skillを改造しない代わりに、`python` へ転送する python3.cmd を作り、その
    ディレクトリをユーザーPATHへ追加する（PATH変更はユーザーごとの環境変数のみ）。
    反映には新しいシェルの起動が必要。
    """
    SHIM_DIR.mkdir(parents=True, exist_ok=True)
    shim = SHIM_DIR / "python3.cmd"
    shim.write_text("@echo off\r\npython %*\r\n", encoding="utf-8")

    ps = (
        f"$d='{SHIM_DIR}';"
        "$p=[Environment]::GetEnvironmentVariable('Path','User');"
        "if($p -eq $null){$p=''};"
        "if(($p -split ';') -notcontains $d){"
        "[Environment]::SetEnvironmentVariable('Path',($p.TrimEnd(';')+';'+$d),'User')}"
    )
    run(["powershell", "-NoProfile", "-Command", ps])


def ensure_course_directories(project_root: Path) -> None:
    (project_root / "教科別").mkdir(parents=True, exist_ok=True)
    for subject in load_subjects(project_root).values():
        base = project_root / subject["directory"]
        for relative in COURSE_DIRECTORIES:
            (base / relative).mkdir(parents=True, exist_ok=True)


def ensure_python_environment(project_root: Path) -> None:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uvがありません")
    python = venv_python(project_root)
    if not python.is_file():
        run([uv, "venv", "--python", "3.12", ".venv"], cwd=project_root)
    requirements = project_root / REQUIREMENTS_NAME
    if not requirements.is_file():
        raise RuntimeError(f"依存定義がありません: {requirements}")
    run([uv, "pip", "install", "--python", str(python), "-r", str(requirements)], cwd=project_root)


def ensure_node_environment(project_root: Path) -> None:
    if not (project_root / "package-lock.json").is_file():
        return
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npmがありません")
    if not (project_root / "node_modules").is_dir():
        run([npm, "ci"], cwd=project_root)


def ensure_model(project_root: Path) -> None:
    if model_cached():
        return
    python = venv_python(project_root)
    code = (
        "from huggingface_hub import snapshot_download;"
        f"snapshot_download(repo_id={MODEL_REPO!r})"
    )
    run([str(python), "-c", code], cwd=project_root)


def apply_setup(project_root: Path, install_system: bool, download_model: bool) -> None:
    if platform.system() != "Windows":
        raise RuntimeError(
            "このWindows用セットアップはWindows専用です。"
            "macOS/Apple Siliconでは /setup（setup_project.py）を使ってください"
        )
    ensure_portal_index(project_root)
    ensure_registry(project_root)
    ensure_course_directories(project_root)
    if install_system:
        ensure_system_dependencies()
    ensure_python_environment(project_root)
    ensure_node_environment(project_root)
    if install_system:
        ensure_python3_shim()
    if download_model:
        ensure_model(project_root)


def summarize(state: dict[str, Any], applied: bool) -> None:
    bar = "─" * 52
    lines = [bar]
    head = "✅ セットアップ完了: 準備OK" if state["ready"] else "⚠️  セットアップ未完了"
    mode = "（適用後の状態）" if applied else "（チェック結果）"
    lines.append(f"{head} {mode}  ready={str(state['ready']).lower()}")

    plat = state["platform"]
    lines.append(
        f"  プラットフォーム : {plat['system']}/{plat['machine']} "
        + ("対応" if state["supported_platform"] else "非対応(Windows専用)")
    )

    missing_cmds = [name for name in REQUIRED_COMMANDS if not state["commands"].get(name)]
    lines.append("  コマンド         : " + ("全導入済み" if not missing_cmds else "未導入 " + ", ".join(missing_cmds)))

    missing_pkgs = [name for name, ok in state["python_packages"].items() if not ok]
    if not state["venv_exists"]:
        py_status = ".venv なし"
    elif missing_pkgs:
        py_status = ".venv あり / 不足 " + ", ".join(missing_pkgs)
    else:
        py_status = ".venv あり / 必須パッケージ充足"
    lines.append("  Python環境       : " + py_status)

    lines.append("  音声認識モデル   : " + ("キャッシュ済み" if state["whisper_model"]["cached"] else "未取得"))
    lines.append("  python3エイリアス: " + ("有効" if state["python3_alias"] else "未設定(新しいシェルで反映)"))
    lines.append("  ポータル         : index.html " + ("存在" if state["portal_index"]["exists"] else "なし"))

    reg = state["subject_registry"]
    lines.append(f"  教科台帳         : {reg['count']}教科登録" + ("" if reg["valid"] else " (台帳エラー)"))

    courses = state["courses"]
    total_missing = sum(len(c["missing_directories"]) for c in courses.values())
    with_missing = [cid for cid, c in courses.items() if c["missing_directories"]]
    folder_line = f"  作業フォルダ     : 不足 {total_missing} 件"
    if with_missing:
        folder_line += " (教科 " + ", ".join(with_missing) + ")"
    lines.append(folder_line)

    if not state["supported_platform"]:
        lines.append("  → このSkillはWindows専用です。macOS/Apple Siliconでは /setup を使ってください")
    elif not state["ready"]:
        lines.append("  → 次のアクション : --apply --install-system --download-model を実行")

    lines.append(bar)
    print("\n".join(lines), file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--install-system", action="store_true")
    parser.add_argument("--download-model", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    if args.apply:
        try:
            apply_setup(root, args.install_system, args.download_model)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            print(f"⚠️  セットアップ適用中にエラー: {exc}", file=sys.stderr, flush=True)
            return 2
    state = inspect(root)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    summarize(state, applied=args.apply)
    return 1 if args.strict and not state["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
