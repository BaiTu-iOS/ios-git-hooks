#!/bin/sh
# iOS Git Hooks 安装/更新脚本
# 用法: curl -fsSL https://raw.githubusercontent.com/BaiTu-iOS/ios-git-hooks/main/install.sh | sh

set -e

REPO_URL="https://github.com/BaiTu-iOS/ios-git-hooks.git"
INSTALL_DIR="$HOME/.local/bin/git_hooks"
HOOKS_DIR="$INSTALL_DIR/hooks"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { printf "${GREEN}[✓]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[!]${NC} %s\n" "$1"; }
error() { printf "${RED}[✗]${NC} %s\n" "$1"; }

# ── 检查依赖 ──
check_dependencies() {
    missing=""

    if ! command -v git >/dev/null 2>&1; then
        missing="$missing git"
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        missing="$missing python3"
    fi

    if [ -n "$missing" ]; then
        error "缺少必要依赖:$missing"
        echo "请先安装后重试"
        exit 1
    fi
}

# ── 安装/更新 ──
install_hooks() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        # 更新模式
        info "检测到已有安装，正在更新..."
        cd "$INSTALL_DIR"
        git pull --ff-only origin main 2>/dev/null || {
            warn "git pull 失败，尝试强制更新..."
            git fetch origin main
            git reset --hard origin/main
        }
    elif [ -d "$INSTALL_DIR" ]; then
        # 存在旧目录但非 git 仓库 → 备份后重新 clone
        BACKUP_DIR="${INSTALL_DIR}.backup.$(date +%Y%m%d%H%M%S)"
        warn "检测到旧版目录（非 git 仓库），备份到 $BACKUP_DIR"
        mv "$INSTALL_DIR" "$BACKUP_DIR"
        info "正在克隆仓库..."
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        # 全新安装
        info "正在克隆仓库..."
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
}

# ── 设置权限 ──
set_permissions() {
    chmod +x "$HOOKS_DIR"/* 2>/dev/null || true
}

# ── 配置 git hooks 路径 ──
configure_git() {
    git config --global core.hooksPath "$HOOKS_DIR"
    info "已设置 git core.hooksPath → $HOOKS_DIR"
}

# ── 显示结果 ──
show_result() {
    VERSION=""
    if [ -f "$INSTALL_DIR/.version" ]; then
        VERSION=$(cat "$INSTALL_DIR/.version")
    fi

    echo ""
    echo "========================================="
    info "iOS Git Hooks 安装完成！"
    if [ -n "$VERSION" ]; then
        info "版本: $VERSION"
    fi
    echo "========================================="
    echo ""
    echo "功能包含："
    echo "  • Objective-C 代码格式检查（clang-format → Xcode 等价缩进）"
    echo "  • Swift 代码格式检查（swiftformat）"
    echo "  • 敏感词检查（compound 语义匹配）"
    echo ""
    echo "更新命令（同一条命令）："
    echo "  curl -fsSL https://raw.githubusercontent.com/BaiTu-iOS/ios-git-hooks/main/install.sh | sh"
    echo ""
    echo "卸载命令："
    echo "  git config --global --unset core.hooksPath && rm -rf $INSTALL_DIR"
    echo ""
}

# ── 主流程 ──
main() {
    echo "iOS Git Hooks 安装器"
    echo ""

    check_dependencies
    install_hooks
    set_permissions
    configure_git
    show_result
}

main
