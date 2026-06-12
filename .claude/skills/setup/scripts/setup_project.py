#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


SYSTEM_FORMULAE = {"ffmpeg": "ffmpeg", "uv": "uv", "node": "node"}
REQUIRED_PYTHON_PACKAGES = ("mlx_whisper", "Foundation", "Vision", "huggingface_hub")
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
MODEL_REPO = "mlx-community/whisper-large-v3-turbo"
PORTAL_TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "index.html"


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


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


def model_cache_path() -> Path:
    explicit = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser() / "models--mlx-community--whisper-large-v3-turbo"
    hf_home = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
    return hf_home.expanduser() / "hub" / "models--mlx-community--whisper-large-v3-turbo"


def model_cached() -> bool:
    snapshots = model_cache_path() / "snapshots"
    return snapshots.is_dir() and any(
        path.is_file() and path.stat().st_size > 0 for path in snapshots.rglob("*")
    )


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
    supported = platform.system() == "Darwin" and platform.machine() == "arm64"
    commands = {name: bool(shutil.which(name)) for name in ("brew", "ffmpeg", "uv", "node", "npm")}
    venv_python = project_root / ".venv" / "bin" / "python"
    packages = python_packages(venv_python)
    registry_path = project_root / "config" / "subjects.json"
    portal_path = project_root / "index.html"

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
    ready = bool(
        supported
        and registry_ok
        and (project_root / "requirements-macos.txt").is_file()
        and all(commands.values())
        and venv_python.is_file()
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
            "version": platform.mac_ver()[0],
        },
        "commands": commands,
        "venv_exists": venv_python.is_file(),
        "python_packages": packages,
        "requirements_file": (project_root / "requirements-macos.txt").is_file(),
        "whisper_model": {
            "repo": MODEL_REPO,
            "cached": model_cached(),
            "cache_path": str(model_cache_path()),
        },
        "node_modules": node_modules_ok,
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
    brew = shutil.which("brew")
    if not brew:
        raise RuntimeError("Homebrewがありません。公式インストーラーで導入後に再実行してください")
    for command, formula in SYSTEM_FORMULAE.items():
        if not shutil.which(command):
            run([brew, "install", formula])
    if not shutil.which("npm"):
        run([brew, "install", "node"])


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
    python = project_root / ".venv" / "bin" / "python"
    if not python.is_file():
        run([uv, "venv", "--python", "3.12", ".venv"], cwd=project_root)
    requirements = project_root / "requirements-macos.txt"
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
    python = project_root / ".venv" / "bin" / "python"
    code = (
        "from huggingface_hub import snapshot_download;"
        f"snapshot_download(repo_id={MODEL_REPO!r})"
    )
    run([str(python), "-c", code], cwd=project_root)


def apply_setup(project_root: Path, install_system: bool, download_model: bool) -> None:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("現在の標準音声認識・OCR構成はApple Silicon Mac専用です")
    ensure_portal_index(project_root)
    ensure_registry(project_root)
    ensure_course_directories(project_root)
    if install_system:
        ensure_system_dependencies()
    ensure_python_environment(project_root)
    ensure_node_environment(project_root)
    if download_model:
        ensure_model(project_root)


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
            return 2
    state = inspect(root)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 1 if args.strict and not state["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
