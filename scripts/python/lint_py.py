#!/usr/bin/env python3
"""Python lint 统一入口脚本。

对仓库内全部 *.py 文件执行两项检查（CLAUDE.md 代码风格约定）：
  1. ruff format --check：代码格式检查
  2. ruff check：lint 规则检查

用法：
  python3 scripts/python/lint_py.py          # 检查全部 .py 文件
  python3 scripts/python/lint_py.py fix      # 自动修复（ruff format + ruff check --fix）
"""

import shutil
import subprocess
import sys
from pathlib import Path

# ---- 常量 ----

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

# 排除目录
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".eggs"}


# ==================================================================
# 1. 文件收集
# ==================================================================


def collect_py_files(repo_root: Path) -> list[Path]:
    """收集仓库内全部 .py 文件（排除 .git、node_modules 等）。"""
    files: list[Path] = []
    for py in sorted(repo_root.rglob("*.py")):
        parts = set(py.relative_to(repo_root).parts)
        if parts & EXCLUDE_DIRS:
            continue
        files.append(py)
    return files


# ==================================================================
# 2. ruff
# ==================================================================


def find_ruff_cmd(repo_root: Path) -> str | None:
    """查找 ruff：优先项目 venv，其次 PATH 全局。"""
    venv_bin = repo_root / ".venv" / "bin" / "ruff"
    if venv_bin.exists():
        return str(venv_bin)
    return shutil.which("ruff")


def run_ruff_format(cmd: str, files: list[Path], fix: bool) -> int:
    """执行 ruff format 检查，返回 exit code。"""
    args = [cmd, "format"]
    if not fix:
        args.append("--check")
    args.extend(str(f) for f in files)

    result = subprocess.run(args, capture_output=False)
    return result.returncode


def run_ruff_check(cmd: str, files: list[Path], fix: bool) -> int:
    """执行 ruff check，返回 exit code。"""
    args = [cmd, "check"]
    if fix:
        args.append("--fix")
    args.extend(str(f) for f in files)

    result = subprocess.run(args, capture_output=False)
    return result.returncode


# ==================================================================
# 主流程
# ==================================================================


def main() -> int:
    fix = len(sys.argv) > 1 and sys.argv[1] == "fix"

    py_files = collect_py_files(REPO_ROOT)
    if not py_files:
        print("[INFO] 未找到任何 .py 文件")
        return 0

    print(f"=== Python Lint === ({len(py_files)} 个文件)\n", flush=True)

    exit_code = 0

    # ---- 查找 ruff ----
    ruff_cmd = find_ruff_cmd(REPO_ROOT)
    if not ruff_cmd:
        print("  [FAIL] ruff 未安装")
        print("         运行 ./scripts/setup.sh --auto 安装")
        return 1

    # ---- 1. ruff format ----
    print("--- ruff format ---", flush=True)
    rc = run_ruff_format(ruff_cmd, py_files, fix=fix)
    if rc != 0:
        exit_code = 1
    print()

    # ---- 2. ruff check ----
    print("--- ruff check ---", flush=True)
    rc = run_ruff_check(ruff_cmd, py_files, fix=fix)
    if rc != 0:
        exit_code = 1
    print()

    # ---- 汇总 ----
    if exit_code == 0:
        print("=== 全部检查通过 ===")
    else:
        print("=== 存在未通过项 ===")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
