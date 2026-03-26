#!/usr/bin/env python3
# Created by yuxilong on 2026/03/26
#
# iOS 禁止关键词检查器（git_hooks 版本）
# 基于 compound 语义边界匹配，支持驼峰/下划线复合词检测
#
# 用法:
#   python3 check_blocked_words.py [file1 file2 ...]       # 检查指定文件
#   python3 check_blocked_words.py --staged                 # 检查 git staged 文件
#   python3 check_blocked_words.py --all <dir>              # 检查目录下所有 iOS 源码
#   python3 check_blocked_words.py --diff-stdin             # 从 stdin 读取 git diff 输出
#   python3 check_blocked_words.py --all <dir> --skip-comments --summary

import re
import sys
import os
import subprocess
import json
from pathlib import Path

# iOS 源码文件扩展名
IOS_EXTENSIONS = {'.h', '.m', '.mm', '.swift', '.c', '.cpp', '.cc'}

# ── 关键词规则定义 ──────────────────────────────────────────────
# mode:
#   "exact"          - 精确匹配完整 token
#   "word_boundary"  - 单词边界匹配
#   "compound"       - 复合词匹配（驼峰/下划线语义边界）

BLOCKED_WORDS = [
    # ── 明确违规词（出现即违规）──
    {"word": "casino",           "mode": "word_boundary"},
    {"word": "jackpot",          "mode": "word_boundary"},
    {"word": "gamble",           "mode": "word_boundary"},
    {"word": "gambling",         "mode": "word_boundary"},
    {"word": "wager",            "mode": "word_boundary"},
    {"word": "roulette",         "mode": "word_boundary"},
    {"word": "blackjack",        "mode": "word_boundary"},
    {"word": "bingo",            "mode": "word_boundary"},
    {"word": "lottery",          "mode": "word_boundary"},
    {"word": "raffle",           "mode": "word_boundary"},
    {"word": "poker",            "mode": "word_boundary"},
    {"word": "real money",       "mode": "word_boundary"},
    {"word": "real cash",        "mode": "word_boundary"},
    {"word": "casino games",     "mode": "word_boundary"},
    {"word": "slot machines",    "mode": "word_boundary"},
    {"word": "virtual currency", "mode": "word_boundary"},
    {"word": "loot box",         "mode": "word_boundary"},
    {"word": "in-app purchase",  "mode": "word_boundary"},

    # ── 支付/金融品牌（出现即违规）──
    {"word": "paypal",           "mode": "word_boundary"},
    {"word": "alipay",           "mode": "word_boundary"},
    {"word": "stripe",           "mode": "word_boundary"},
    {"word": "adyen",            "mode": "word_boundary"},
    {"word": "razorpay",         "mode": "word_boundary"},
    {"word": "paytm",            "mode": "word_boundary"},

    # ── 短词（compound 模式：驼峰/下划线语义边界匹配）──
    {"word": "pay",              "mode": "compound"},
    {"word": "win",              "mode": "compound"},
    {"word": "game",             "mode": "compound"},
    {"word": "money",            "mode": "compound"},
    {"word": "price",            "mode": "compound"},
    {"word": "prize",            "mode": "compound"},
    {"word": "bet",              "mode": "compound"},
    {"word": "cash",             "mode": "compound"},
    {"word": "bank",             "mode": "compound"},
    {"word": "diamond",          "mode": "compound"},
    {"word": "wallet",           "mode": "compound"},
    {"word": "stake",            "mode": "compound"},

    # ── 精确匹配标识符 ──
    {"word": "lose",             "mode": "exact"},
    {"word": "match",            "mode": "exact"},
    {"word": "credits",          "mode": "exact"},
    {"word": "exchange",         "mode": "exact"},
    {"word": "anonymity",        "mode": "exact"},
    {"word": "mystery_man",      "mode": "exact"},
    {"word": "slotgame",         "mode": "exact"},

    # ── 精确匹配的复合标识符 ──
    {"word": "chat_price",       "mode": "exact"},
    {"word": "chat_money",       "mode": "exact"},
    {"word": "chatprice",        "mode": "exact"},
    {"word": "chatmoney",        "mode": "exact"},
    {"word": "video_price",      "mode": "exact"},
    {"word": "photo_price",      "mode": "exact"},
    {"word": "bigwin",           "mode": "exact"},
    {"word": "big_win",          "mode": "exact"},
    {"word": "prize_pool",       "mode": "exact"},
    {"word": "win_coin",         "mode": "exact"},
    {"word": "grand_prize",      "mode": "exact"},
    {"word": "luck_pool",        "mode": "exact"},
    {"word": "bank_id",          "mode": "exact"},
    {"word": "wx_pay",           "mode": "exact"},
    {"word": "web_pay",          "mode": "exact"},
    {"word": "pay_type",         "mode": "exact"},
    {"word": "game_id",          "mode": "exact"},
    {"word": "game_icon",        "mode": "exact"},
    {"word": "game_list",        "mode": "exact"},
    {"word": "anonymity_avatar", "mode": "exact"},
]

# ── compound 模式白名单 ──────────────────────────────────────────
COMPOUND_WHITELIST = {
    # pay
    "payload", "payloadmessage", "btpayloadmessage", "btpayloaddecoder",
    "btpayloadroot", "decodedpayload", "btdecodedpayload",
    "repay", "display", "displayed", "displaying",
    # win
    "window", "windows", "darwin", "uiwindow", "nswindow",
    "winding", "rewind", "nswindowcontroller",
    # game
    "gamepad", "gamecontroller", "gkgame",
    # bet
    "beta", "alphabet", "alphabetical", "between",
    # cash
    "cache", "cached", "caching", "nscache", "nsurlcache",
    "broadcast", "broadcasting",
    # bank
    "bankrupt", "bankruptcy",
    # match
    "matching", "matched", "matcher", "nspredicate",
    # stake
    "mistake", "mistaken",
    # lose
    "close", "closed", "closing", "closedenumsupportknown",
    "enclose", "enclosed",
}


def build_pattern(word: str, mode: str) -> re.Pattern:
    """根据匹配模式构建正则表达式"""
    escaped = re.escape(word)

    if mode == "exact":
        return re.compile(
            r'(?<![a-zA-Z0-9_])' + escaped + r'(?![a-zA-Z0-9_])',
            re.IGNORECASE)

    elif mode == "word_boundary":
        return re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)

    elif mode == "compound":
        return re.compile(
            r'[a-zA-Z_]*' + escaped + r'[a-zA-Z_]*',
            re.IGNORECASE)

    raise ValueError(f"Unknown mode: {mode}")


def is_whitelisted(full_token: str) -> bool:
    """检查完整 token 是否在白名单中"""
    return full_token.lower() in COMPOUND_WHITELIST


def is_compound_match(full_token: str, keyword: str) -> bool:
    """判断 compound 模式下，token 是否真正包含关键词作为语义组件

    规则：
    - 关键词独立出现 → 违规
    - 驼峰组件（payCoins, chatMoney）→ 违规
    - 下划线组件（pay_type, chat_money）→ 违规
    - 全大写组件（PAY_TYPE）→ 违规
    - 纯子串（payload, display, window）→ 放行
    """
    token_lower = full_token.lower()
    kw_lower = keyword.lower()

    if is_whitelisted(token_lower):
        return False

    if token_lower == kw_lower:
        return True

    idx = token_lower.find(kw_lower)
    if idx == -1:
        return False

    kw_end = idx + len(kw_lower)

    # 检查左边界
    left_ok = False
    if idx == 0:
        left_ok = True
    else:
        prev_char = full_token[idx - 1]
        if prev_char == '_':
            left_ok = True
        elif prev_char.islower() and full_token[idx].isupper():
            left_ok = True
        elif prev_char.isupper() and full_token[idx].isupper():
            left_ok = True

    if not left_ok:
        return False

    # 检查右边界
    right_ok = False
    if kw_end == len(full_token):
        right_ok = True
    else:
        next_char = full_token[kw_end]
        if next_char == '_':
            right_ok = True
        elif next_char.isupper():
            right_ok = True
        elif full_token[kw_end - 1].isupper() and next_char.islower():
            right_ok = False

    return right_ok


def is_comment_line(line: str) -> bool:
    """判断是否为注释行"""
    stripped = line.strip()
    return (stripped.startswith('//')
            or stripped.startswith('*')
            or stripped.startswith('/*'))


def check_line(line: str, line_num: int, filepath: str,
               skip_comments: bool = False) -> list:
    """检查单行代码是否包含禁止关键词"""
    violations = []
    is_comment = is_comment_line(line)

    if skip_comments and is_comment:
        return violations

    for rule in BLOCKED_WORDS:
        word = rule["word"]
        mode = rule["mode"]
        pattern = build_pattern(word, mode)

        for m in pattern.finditer(line):
            matched_text = m.group()

            if mode == "compound":
                if not is_compound_match(matched_text, word):
                    continue

            if is_whitelisted(matched_text):
                continue

            violations.append({
                "file": filepath,
                "line": line_num,
                "keyword": word,
                "matched": matched_text,
                "mode": mode,
                "context": line.rstrip(),
                "is_comment": is_comment,
            })

    return violations


def check_file(filepath: str, skip_comments: bool = False) -> list:
    """检查单个文件"""
    violations = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                violations.extend(
                    check_line(line, line_num, filepath,
                               skip_comments=skip_comments))
    except (IOError, OSError) as e:
        print(f"警告: 无法读取 {filepath}: {e}", file=sys.stderr)
    return violations


def check_diff_stdin(skip_comments: bool = False) -> list:
    """从 stdin 读取 git diff -U0 输出，只检查新增行

    解析格式：
    +++ b/path/to/file  → 提取文件路径
    @@ -x,y +N,M @@    → 提取新增行起始行号
    +content            → 检查新增行内容
    """
    violations = []
    current_file = ""
    current_line_num = 0

    for raw_line in sys.stdin:
        line = raw_line.rstrip('\n')

        # 提取文件路径
        if line.startswith('+++ '):
            # +++ b/path/to/file 或 +++ path/to/file
            path = line[4:]
            if path.startswith('b/'):
                path = path[2:]
            current_file = path
            continue

        # 提取行号
        if line.startswith('@@'):
            # @@ -x,y +N,M @@ 或 @@ -x +N @@
            m = re.search(r'\+(\d+)', line)
            if m:
                current_line_num = int(m.group(1))
            continue

        # 跳过删除行和 --- 行
        if line.startswith('---') or line.startswith('-'):
            continue

        # 检查新增行
        if line.startswith('+'):
            content = line[1:]  # 去掉 diff 的 + 前缀
            if current_file:
                violations.extend(
                    check_line(content, current_line_num, current_file,
                               skip_comments=skip_comments))
            current_line_num += 1
            continue

        # 上下文行（无 +/- 前缀）：递增行号但不检查
        if not line.startswith('\\'):  # 跳过 "\ No newline at end of file"
            current_line_num += 1

    return violations


def get_staged_files() -> list:
    """获取 git staged 的 iOS 源码文件"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            capture_output=True, text=True, check=True
        )
        files = []
        for f in result.stdout.strip().split('\n'):
            if f and Path(f).suffix in IOS_EXTENSIONS:
                files.append(f)
        return files
    except subprocess.CalledProcessError:
        return []


def get_all_ios_files(root: str = '.') -> list:
    """递归获取所有 iOS 源码文件"""
    files = []
    for dirpath, _, filenames in os.walk(root):
        if any(skip in dirpath for skip in
               ['/Pods/', '/build/', '/.git/', '/DerivedData/']):
            continue
        for fname in filenames:
            if Path(fname).suffix in IOS_EXTENSIONS:
                files.append(os.path.join(dirpath, fname))
    return files


def format_violations(violations: list) -> str:
    """格式化输出违规信息"""
    if not violations:
        return "✅ 未发现禁止关键词\n"

    by_file = {}
    for v in violations:
        by_file.setdefault(v['file'], []).append(v)

    lines = []
    lines.append(f"❌ 发现 {len(violations)} 处禁止关键词命中\n")

    for filepath, file_violations in by_file.items():
        lines.append(f"📄 {filepath}")
        for v in file_violations:
            comment_tag = " [注释]" if v['is_comment'] else ""
            lines.append(
                f"  L{v['line']:>4d} | 关键词 '{v['keyword']}' → "
                f"匹配 '{v['matched']}'{comment_tag}"
            )
            lines.append(f"       | {v['context'][:120]}")
        lines.append("")

    return '\n'.join(lines)


def format_summary(violations: list) -> str:
    """汇总表格格式输出"""
    if not violations:
        return "✅ 未发现禁止关键词\n"

    keyword_stats = {}
    for v in violations:
        kw = v['keyword']
        if kw not in keyword_stats:
            keyword_stats[kw] = {'count': 0, 'files': set()}
        keyword_stats[kw]['count'] += 1
        keyword_stats[kw]['files'].add(v['file'])

    total_keywords = len(keyword_stats)
    total_hits = sum(s['count'] for s in keyword_stats.values())

    lines = []
    lines.append(
        f"敏感词检查汇总：{total_keywords} 个敏感词，共 {total_hits} 处命中\n")
    lines.append("| 敏感词 | 命中数 | 涉及文件数 |")
    lines.append("|--------|--------|-----------|")
    for kw, stats in sorted(keyword_stats.items(),
                            key=lambda x: -x[1]['count']):
        lines.append(
            f"| {kw} | {stats['count']} | {len(stats['files'])} |")
    lines.append("")
    return '\n'.join(lines)


def format_json(violations: list) -> str:
    """JSON 格式输出"""
    return json.dumps(violations, ensure_ascii=False, indent=2)


def parse_args(argv: list) -> dict:
    """解析命令行参数"""
    opts = {
        'json': False,
        'staged': False,
        'all': False,
        'all_root': '.',
        'skip_comments': False,
        'summary': False,
        'diff_stdin': False,
        'files': [],
    }

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--json':
            opts['json'] = True
        elif arg == '--staged':
            opts['staged'] = True
        elif arg == '--diff-stdin':
            opts['diff_stdin'] = True
        elif arg == '--all':
            opts['all'] = True
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                opts['all_root'] = argv[i + 1]
                i += 1
        elif arg == '--skip-comments':
            opts['skip_comments'] = True
        elif arg == '--summary':
            opts['summary'] = True
        elif os.path.isfile(arg):
            opts['files'].append(arg)
        i += 1

    return opts


def main():
    opts = parse_args(sys.argv[1:])

    if opts['diff_stdin']:
        # 从 stdin 读取 git diff 输出
        all_violations = check_diff_stdin(
            skip_comments=opts['skip_comments'])
    elif opts['staged']:
        files = get_staged_files()
        if not files:
            print("没有 staged 的 iOS 源码文件")
            sys.exit(0)
        all_violations = []
        for f in files:
            all_violations.extend(
                check_file(f, skip_comments=opts['skip_comments']))
    elif opts['all']:
        files = get_all_ios_files(opts['all_root'])
        if not files:
            print("未找到 iOS 源码文件")
            sys.exit(0)
        all_violations = []
        for f in files:
            all_violations.extend(
                check_file(f, skip_comments=opts['skip_comments']))
    elif opts['files']:
        all_violations = []
        for f in opts['files']:
            all_violations.extend(
                check_file(f, skip_comments=opts['skip_comments']))
    else:
        print("用法:")
        print("  python3 check_blocked_words.py file1.m file2.h ...")
        print("  python3 check_blocked_words.py --staged")
        print("  python3 check_blocked_words.py --diff-stdin")
        print("  python3 check_blocked_words.py --all [root_dir]")
        print("  python3 check_blocked_words.py --all <dir> "
              "--skip-comments --summary")
        sys.exit(0)

    if opts['json']:
        print(format_json(all_violations))
    elif opts['summary']:
        print(format_summary(all_violations))
    else:
        print(format_violations(all_violations))

    sys.exit(1 if all_violations else 0)


if __name__ == '__main__':
    main()
