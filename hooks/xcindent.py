#!/usr/bin/env python3
# xcindent — Xcode 等价 Objective-C 重缩进器
# Source: wk-xcindent 1.0.1 (35 个真实 Xcode 26.6 oracle 用例校准)
#
# 词法驱动、逐行只改行首空白：
#   规则1  行缩进 = 花括号嵌套深度 × W（行首闭合符先回退一级）
#   规则2  未闭合 ObjC 消息的 keyword: 续行 → 右对齐关键字
#
# 只改行首空白，从不合并/拆分行、不改非空白内容。

import re
import sys


KEYWORD_COLON = re.compile(r"^([A-Za-z_]\w*)\s*:(?!:)")


class Frame:
    """一个未闭合的定界上下文。kind ∈ {'brace','paren','bracket'}。"""

    __slots__ = (
        "kind",
        "opener_indent",
        "after_open_col",
        "is_message",
        "first_colon_col",
        "is_switch",
    )

    def __init__(self, kind, opener_indent, after_open_col):
        self.kind = kind
        self.opener_indent = opener_indent
        self.after_open_col = after_open_col
        self.is_message = False
        self.first_colon_col = None
        self.is_switch = False


class Lexer:
    """跨行维护字符串、字符、行注释和块注释状态。"""

    def __init__(self):
        self.in_block_comment = False
        self.block_comment_col = None

    def line_starts_in_comment(self):
        return self.in_block_comment

    def scan(self, line):
        """扫描一行，返回结构事件与是否以反斜杠结尾。"""
        events = []
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if self.in_block_comment:
                if c == "*" and i + 1 < n and line[i + 1] == "/":
                    self.in_block_comment = False
                    self.block_comment_col = None
                    i += 2
                    continue
                i += 1
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if c == "/" and i + 1 < n and line[i + 1] == "*":
                self.in_block_comment = True
                self.block_comment_col = i
                i += 2
                continue
            if c == '"' or c == "'":
                i = self._skip_string(line, i, c)
                continue
            if c in "{([":
                events.append(("open", c, i))
            elif c in "})]":
                events.append(("close", c, i))
            elif c == ":":
                events.append(("colon", c, i))
            i += 1
        ended_bs = (not self.in_block_comment) and line.rstrip("\n").endswith("\\")
        return events, ended_bs

    @staticmethod
    def _skip_string(line, i, quote):
        n = len(line)
        i += 1
        while i < n:
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == quote:
                return i + 1
            i += 1
        return i


class Reindenter:
    def __init__(self, width=4, indent_case=True, indent_preproc=False):
        self.W = width
        self.indent_case = indent_case
        self.indent_preproc = indent_preproc

    def reindent(self, text, ranges=None):
        """重缩进全文，或仅重写 1-based 闭区间 ranges 内的行首空白。"""
        lex = Lexer()
        stack = []
        out = []
        cont_from_backslash = False
        in_preproc = False
        prev_backslash = False
        method = {"active": False, "colon": None}

        for lineno, raw in enumerate(text.split("\n"), start=1):
            raw = raw.rstrip("\n")
            content = raw.strip()
            apply_ln = ranges is None or self._in_ranges(lineno, ranges)
            starts_in_comment = lex.line_starts_in_comment()

            if content == "":
                out.append("" if apply_ln else raw)
                lex.scan(raw)
                continue

            if starts_in_comment:
                col = lex.block_comment_col
                ind = (col + 1) if col is not None else 0
                emit = (" " * ind + content) if apply_ln else raw
                out.append(emit)
                lex.scan(emit)
                continue

            if content[0] == "#" or (in_preproc and prev_backslash):
                ind = self._brace_depth(stack) * self.W if self.indent_preproc else 0
                emit = (" " * ind + content) if apply_ln else raw
                out.append(emit)
                lex.scan(emit)
                in_preproc = True
                prev_backslash = content.rstrip().endswith("\\")
                if not prev_backslash:
                    in_preproc = False
                cont_from_backslash = False
                continue
            in_preproc = False

            if (
                not method["active"]
                and self._inner_brace(stack) is None
                and re.match(r"^[-+]\s*\(", content)
            ):
                method["active"] = True
                method["colon"] = None

            if apply_ln:
                indent = self._indent_for(content, stack, cont_from_backslash, method)
                emit = " " * indent + content
            else:
                emit = raw
                indent = len(raw) - len(raw.lstrip())
            out.append(emit)

            events, ended_bs = lex.scan(emit)
            self._apply_events(events, stack, indent, emit)
            cont_from_backslash = ended_bs

            if method["active"]:
                if method["colon"] is None:
                    first_colon = next(
                        (col for kind, _char, col in events if kind == "colon"), None
                    )
                    if first_colon is not None:
                        method["colon"] = first_colon
                if any(
                    kind == "open" and char == "{" for kind, char, _col in events
                ) or content.rstrip().endswith(";"):
                    method["active"] = False
                    method["colon"] = None

        return "\n".join(out)

    @staticmethod
    def _in_ranges(lineno, ranges):
        for start, end in ranges:
            if start <= lineno <= end:
                return True
        return False

    def _brace_depth(self, stack):
        return sum(1 for frame in stack if frame.kind == "brace")

    def _indent_for(self, content, stack, cont_bs, method):
        first_char = content[0]
        top = stack[-1] if stack else None

        if first_char in "})]":
            for frame in reversed(stack):
                if (frame.kind, first_char) in (
                    ("brace", "}"),
                    ("paren", ")"),
                    ("bracket", "]"),
                ):
                    if frame.kind == "brace":
                        return (self._brace_depth(stack) - 1) * self.W
                    return frame.opener_indent
            return 0

        if method["active"] and method["colon"] is not None:
            match = KEYWORD_COLON.match(content)
            if match:
                return max(0, method["colon"] - len(match.group(1)))

        if first_char == "{" or content.startswith("@{"):
            return self._brace_depth(stack) * self.W

        if (
            (top is None or top.kind == "brace")
            and re.match(r"^[A-Za-z_]\w*\s*:(?!:)", content)
            and not re.match(r"^(case\b|default\b)", content)
        ):
            return 0

        if top and top.kind == "bracket" and top.is_message:
            match = KEYWORD_COLON.match(content)
            if match and top.first_colon_col is not None:
                return max(0, top.first_colon_col - len(match.group(1)))
            if top.after_open_col is not None:
                return top.after_open_col
            return top.opener_indent + self.W

        if top and top.kind == "bracket":
            if top.after_open_col is not None:
                return top.after_open_col
            return top.opener_indent + self.W

        if top and top.kind == "paren":
            if top.after_open_col is not None:
                return top.after_open_col
            return top.opener_indent + self.W

        base = self._brace_depth(stack) * self.W
        brace_frame = self._inner_brace(stack)

        if re.match(r"^(case\b|default\b\s*:)", content):
            if brace_frame is not None:
                brace_frame.is_switch = True
            return base

        if self.indent_case and brace_frame is not None and brace_frame.is_switch:
            base += self.W
        if cont_bs:
            base += self.W
        return base

    @staticmethod
    def _inner_brace(stack):
        for frame in reversed(stack):
            if frame.kind == "brace":
                return frame
        return None

    def _apply_events(self, events, stack, line_indent, line):
        for kind, char, col in events:
            if kind == "open":
                frame_kind = {
                    "{": "brace",
                    "(": "paren",
                    "[": "bracket",
                }[char]
                rest = line[col + 1 :]
                after = (
                    col + 1 + (len(rest) - len(rest.lstrip())) if rest.strip() else None
                )
                stack.append(Frame(frame_kind, line_indent, after))
            elif kind == "close":
                wanted = {"}": "brace", ")": "paren", "]": "bracket"}[char]
                while stack and stack[-1].kind != wanted:
                    stack.pop()
                if stack:
                    stack.pop()
            elif kind == "colon":
                for frame in reversed(stack):
                    if frame.kind == "bracket":
                        if frame.first_colon_col is None:
                            frame.first_colon_col = col
                            frame.is_message = True
                        break
                    if frame.kind in ("brace", "paren"):
                        break


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog="xcindent", description="Xcode 等价 ObjC 重缩进"
    )
    parser.add_argument("file", nargs="?", help="输入文件；缺省读 stdin")
    parser.add_argument("-w", "--width", type=int, default=4, help="缩进宽度（默认 4）")
    parser.add_argument("-i", "--in-place", action="store_true", help="原地写回文件")
    parser.add_argument("--no-indent-case", action="store_true", help="case 标签不缩进")
    parser.add_argument(
        "--lines",
        action="append",
        metavar="START:END",
        help="仅重缩进指定 1-based 行区间（可重复）",
    )
    args = parser.parse_args(argv)

    ranges = None
    if args.lines:
        ranges = []
        for spec in args.lines:
            start, _, end = spec.partition(":")
            end = end or start
            ranges.append((int(start), int(end)))

    if args.file:
        with open(args.file, encoding="utf-8") as input_file:
            text = input_file.read()
    else:
        text = sys.stdin.read()

    result = Reindenter(width=args.width, indent_case=not args.no_indent_case).reindent(
        text, ranges=ranges
    )
    if args.in_place and args.file:
        with open(args.file, "w", encoding="utf-8") as output_file:
            output_file.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
