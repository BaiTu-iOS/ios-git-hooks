# iOS Git Hooks

团队统一的 Git pre-commit 钩子，自动检查代码格式和敏感词。

## 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/BaiTu-iOS/ios-git-hooks/main/install.sh | sh
```

同一条命令也用于**更新**。

## 功能

| 检查项 | 说明 |
|--------|------|
| OC 格式检查 | `clang-format → xcindent` 组合校验，仅检查 `BT*.h/m/mm/cpp` 改动行；缩进对齐 Xcode Ctrl+I |
| Swift 格式检查 | 基于 swiftformat，检查暂存的 `.swift` 文件 |
| 敏感词检查 | compound 语义匹配，支持驼峰/下划线复合词边界识别 |

### 敏感词匹配示例

| 关键词 | 命中 | 不命中 |
|--------|------|--------|
| `pay` | `payType`, `pay_type`, `wx_pay` | `payload`, `display`, `repay` |
| `win` | `winCoin`, `win_coin`, `bigwin` | `window`, `darwin` |
| `money` | `moneyType`, `money_amount` | — |
| `bet` | `betAmount` | `beta`, `alphabet` |

## 依赖

- git 2.9+（支持 `core.hooksPath`）
- python3
- clang-format（通过 Xcode 自带 `xcrun --find clang-format`）
- [swiftformat](https://github.com/nicklockwood/SwiftFormat)（需自行安装: `brew install swiftformat`）

## 卸载

```bash
git config --global --unset core.hooksPath && rm -rf ~/.local/bin/git_hooks
```

## 维护

### 添加/修改敏感词

编辑 `hooks/check_blocked_words.py` 中的 `BLOCKED_WORDS` 列表。

### 添加白名单

编辑 `hooks/check_blocked_words.py` 中的 `COMPOUND_WHITELIST`。

### 修改 OC 格式规则

编辑 `config/clang-format-config`。

OC 门禁先让 clang-format 处理空格、大括号和指针位置，再由内置
`hooks/xcindent.py` 对同一批改动行做缩进收尾。后者只改行首空白，
用于解决尾随消息 block body 被 clang-format 推到参数列深缩进的问题。
内置引擎同步自 `wk-xcindent 1.0.1`，已通过 35 个真实 Xcode 26.6
oracle golden 用例校准。

检查过程完全在内存中完成，只输出建议 diff，不会直接修改工作区文件。

### 修改 Swift 格式规则

编辑 `config/vswiftformatconfig`。

### 运行回归

```bash
python3 -m unittest discover -s tests -v
```
