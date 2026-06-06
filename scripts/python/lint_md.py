#!/usr/bin/env python3
"""Markdown lint 统一入口脚本。

对仓库内全部 *.md 文件执行两项检查：
  1. markdownlint-cli2：标准 Markdown 规则（行宽 120，代码块 / 表格除外）
  2. 中英文 / 中文数字交界处空格检查（代码块、行内代码、URL 除外）

用法：
  python3 scripts/python/lint_md.py          # 检查全部 .md 文件
  python3 scripts/python/lint_md.py fix      # 自动修复可修复的问题
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---- 常量 ----

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

# CJK 统一表意文字（基本区 + 扩展 A）
CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
ASCII_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


# ==================================================================
# 1. 文件收集
# ==================================================================


def collect_md_files(repo_root: Path) -> list[Path]:
    """收集仓库内全部 .md 文件（排除 .git、node_modules、.venv 等）。"""
    exclude_dirs = {".git", "node_modules", ".venv", "venv"}
    files: list[Path] = []
    for md in sorted(repo_root.rglob("*.md")):
        parts = set(md.relative_to(repo_root).parts)
        if parts & exclude_dirs:
            continue
        files.append(md)
    return files


# ==================================================================
# 2. markdownlint-cli2
# ==================================================================


def find_markdownlint_cmd(repo_root: Path) -> str | None:
    """查找 markdownlint-cli2：优先项目级安装，其次全局。"""
    node_modules_bin = repo_root / "node_modules" / ".bin" / "markdownlint-cli2"
    if node_modules_bin.exists():
        return str(node_modules_bin)
    return shutil.which("markdownlint-cli2")


def run_markdownlint(
    cmd: str,
    files: list[Path],
    fix: bool,
) -> int:
    """执行 markdownlint-cli2，返回 exit code。"""
    args = [cmd]
    if fix:
        args.append("--fix")
    args.extend(str(f) for f in files)

    result = subprocess.run(args, capture_output=False)
    return result.returncode


# ==================================================================
# 3. 中英文 / 中文数字空格检查
# ==================================================================


def _strip_non_text(markdown: str) -> str:
    """移除不需要检查的部分：行内代码、链接 / 图片 URL。"""
    result = re.sub(r"`[^`]*`", "", markdown)
    result = re.sub(r"\]\([^)]*\)", "]", result)
    return result


def _check_line_spacing(text: str) -> list[tuple[int, str]]:
    """在纯文本行中检查 CJK-ASCII 交界处是否缺少空格。"""
    issues: list[tuple[int, str]] = []
    chars = list(text)
    for i in range(len(chars) - 1):
        c1, c2 = chars[i], chars[i + 1]
        hit = (CJK_RE.match(c1) and ASCII_ALNUM_RE.match(c2)) or (
            ASCII_ALNUM_RE.match(c1) and CJK_RE.match(c2)
        )
        if hit:
            start = max(0, i - 5)
            end = min(len(chars), i + 7)
            snippet = "".join(chars[start:end])
            issues.append((i + 1, snippet))
    return issues


def check_cjk_spacing(filepath: Path) -> list[tuple[int, int, str]]:
    """检查单个文件的 CJK 空格。返回 [(line_no, col, snippet), ...]。"""
    lines = filepath.read_text(encoding="utf-8").splitlines()
    issues: list[tuple[int, int, str]] = []
    in_fenced_block = False

    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()

        # fenced code block
        if FENCE_RE.match(stripped):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue

        # indented code block
        if raw_line.startswith("    ") or raw_line.startswith("\t"):
            continue

        # 空行 / HTML 注释
        if not stripped or stripped.startswith("<!--"):
            continue

        text = _strip_non_text(stripped)
        for col, snippet in _check_line_spacing(text):
            issues.append((lineno, col, snippet))

    return issues


def run_cjk_check(files: list[Path]) -> int:
    """对全部文件执行 CJK 空格检查，返回 exit code。"""
    has_errors = False
    for filepath in files:
        issues = check_cjk_spacing(filepath)
        if issues:
            has_errors = True
            for lineno, col, snippet in issues:
                print(f"  {filepath}:{lineno}:{col}: 缺少空格 -> ...{snippet}...")

    if has_errors:
        print("  [FAIL] 存在中英文 / 中文数字交界处缺少空格的问题")
        return 1

    print("  [OK] 中英文 / 中文数字空格检查通过")
    return 0


# ==================================================================
# 主流程
# ==================================================================


def main() -> int:
    fix = len(sys.argv) > 1 and sys.argv[1] == "fix"

    md_files = collect_md_files(REPO_ROOT)
    if not md_files:
        print("[INFO] 未找到任何 .md 文件")
        return 0

    print(f"=== Markdown Lint === ({len(md_files)} 个文件)\n", flush=True)

    exit_code = 0

    # ---- 1. markdownlint-cli2 ----
    print("--- markdownlint-cli2 ---", flush=True)
    mdlint_cmd = find_markdownlint_cmd(REPO_ROOT)
    if mdlint_cmd:
        rc = run_markdownlint(mdlint_cmd, md_files, fix=fix)
        if rc != 0:
            exit_code = 1
    else:
        print("  [WARN] markdownlint-cli2 未安装，跳过标准规则检查")
        print("         运行 ./scripts/setup.sh --auto 安装")
    print()

    # ---- 2. CJK 空格检查 ----
    print("--- 中英文空格检查 ---", flush=True)
    if run_cjk_check(md_files) != 0:
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
