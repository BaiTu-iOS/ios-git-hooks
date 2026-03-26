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
| OC 格式检查 | 基于 clang-format，检查 `BT*.h/m/mm/cpp` 文件 |
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

### 修改 Swift 格式规则

编辑 `config/vswiftformatconfig`。
