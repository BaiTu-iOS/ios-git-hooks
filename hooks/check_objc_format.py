#!/usr/bin/env python3
"""检查 HEAD 以来改动的 BT* ObjC/C++ 行是否符合组合格式化管线。"""

import argparse
import difflib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from xcindent import Reindenter


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SOURCE_NAME = re.compile(r"^BT.*\.(?:cpp|h|m|mm)$")


def run(command, cwd, check=True, input_bytes=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "命令执行失败: {}".format(command[0]))
    return result


def repository_root():
    result = run(["git", "rev-parse", "--show-toplevel"], os.getcwd())
    return Path(os.fsdecode(result.stdout).strip()).resolve()


def base_tree(repo):
    result = run(
        ["git", "rev-parse", "--verify", "HEAD^{tree}"],
        str(repo),
        check=False,
    )
    if result.returncode == 0:
        return os.fsdecode(result.stdout).strip()
    return EMPTY_TREE


def changed_sources(repo, base):
    result = run(
        ["git", "diff", "--name-status", "-z", "--find-renames", base, "--"],
        str(repo),
    )
    fields = result.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()

    sources = []
    index = 0
    while index < len(fields):
        status = os.fsdecode(fields[index])
        index += 1
        kind = status[:1]
        if kind in ("R", "C"):
            if index + 1 >= len(fields):
                raise RuntimeError("无法解析 git rename/copy 输出")
            old_path = os.fsdecode(fields[index])
            new_path = os.fsdecode(fields[index + 1])
            index += 2
        else:
            if index >= len(fields):
                raise RuntimeError("无法解析 git diff 输出")
            old_path = new_path = os.fsdecode(fields[index])
            index += 1

        if kind == "D" or not SOURCE_NAME.match(Path(new_path).name):
            continue
        sources.append((old_path, new_path, kind))
    return sources


def blob_at(repo, base, path, kind):
    if kind == "A" or base == EMPTY_TREE:
        return b""
    result = run(
        ["git", "show", "{}:{}".format(base, path)],
        str(repo),
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    return b""


def changed_ranges(before_text, after_text, cwd=None):
    """用 git diff -U0 返回 after_text 中发生变化的 1-based 闭区间。"""
    if before_text == after_text:
        return []

    with tempfile.TemporaryDirectory(prefix="objc-format-") as directory:
        before_path = Path(directory) / "before"
        after_path = Path(directory) / "after"
        before_path.write_text(before_text, encoding="utf-8")
        after_path.write_text(after_text, encoding="utf-8")
        result = run(
            [
                "git",
                "diff",
                "--no-index",
                "--no-ext-diff",
                "--text",
                "--unified=0",
                "--no-color",
                "--",
                str(before_path),
                str(after_path),
            ],
            cwd or os.getcwd(),
            check=False,
        )
    if result.returncode not in (0, 1):
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or "git diff 无法计算格式化区间")

    ranges = []
    hunk = re.compile(rb"^@@ -[0-9]+(?:,[0-9]+)? \+([0-9]+)(?:,([0-9]+))? @@")
    for line in result.stdout.splitlines():
        match = hunk.match(line)
        if not match:
            continue
        start = int(match.group(1))
        length = int(match.group(2) or b"1")
        if length == 0:
            continue
        end = start + length - 1
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def clang_format(clang_binary, style, filename, content, ranges, repo):
    command = [
        clang_binary,
        "-style=file:{}".format(style),
        "-assume-filename={}".format(filename),
    ]
    command.extend("-lines={}:{}".format(start, end) for start, end in ranges)
    result = run(command, str(repo), check=False, input_bytes=content)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "{}: clang-format 执行失败{}".format(
                filename, ": " + message if message else ""
            )
        )
    return result.stdout


def format_source(clang_binary, style, filename, baseline, current, repo):
    try:
        baseline_text = baseline.decode("utf-8")
        current_text = current.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("{} 不是 UTF-8 源文件: {}".format(filename, error))

    initial_ranges = changed_ranges(baseline_text, current_text, str(repo))
    if not initial_ranges:
        return current_text

    clang_bytes = clang_format(
        clang_binary,
        style,
        str(repo / filename),
        current,
        initial_ranges,
        repo,
    )
    try:
        clang_text = clang_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError(
            "{}: clang-format 输出不是 UTF-8: {}".format(filename, error)
        )

    # clang-format 的 Allman 大括号规则可能增删行，因此必须基于其输出
    # 重新计算区间，不能复用格式化前的行号。
    xcindent_ranges = changed_ranges(baseline_text, clang_text, str(repo))
    if not xcindent_ranges:
        return clang_text
    return Reindenter(width=4).reindent(clang_text, ranges=xcindent_ranges)


def patch_for(filename, current, expected):
    lines = difflib.unified_diff(
        current.splitlines(),
        expected.splitlines(),
        fromfile="a/{}".format(filename),
        tofile="b/{}".format(filename),
        n=1,
        lineterm="",
    )
    return "\n".join(lines) + "\n"


def write_report(output_path, patches):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(patches), encoding="utf-8")


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--clang-format", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        repo = repository_root()
        base = base_tree(repo)
        patches = []

        for old_path, new_path, kind in changed_sources(repo, base):
            worktree_path = repo / new_path
            if not worktree_path.is_file():
                continue
            baseline = blob_at(repo, base, old_path, kind)
            current = worktree_path.read_bytes()
            expected = format_source(
                args.clang_format,
                args.style,
                new_path,
                baseline,
                current,
                repo,
            )
            current_text = current.decode("utf-8")
            if expected != current_text:
                patches.append(patch_for(new_path, current_text, expected))

        write_report(args.output, patches)
        if not patches:
            print("✅ Objective-C代码校验通过！")
            print("")
            return 0

        print("❌ Objective-C代码格式校验不通过，建议修改：")
        print("".join(patches), end="")
        print("详情见: {}".format(args.output))
        return 1
    except (OSError, RuntimeError) as error:
        print("❌ Objective-C代码格式校验执行失败: {}".format(error))
        return 2


if __name__ == "__main__":
    sys.exit(main())
