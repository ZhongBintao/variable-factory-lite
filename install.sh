#!/bin/bash
# 变量库工厂（单人版）一键安装：检查环境 → 建 Python 虚拟环境、装依赖 → 自检 → 生成示例论文和数据 → 在桌面放入口。
# 用法：在仓库文件夹里运行  ./install.sh
# 可以重复运行（更新后再跑一次也行），不会删你的论文和数据（它们在 ~/变量库工厂单人版/）。
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m✗ %s\033[0m\n' "$1"; [ -n "${2:-}" ] && printf '  怎么办：%s\n' "$2"; printf '  （更多见 docs/常见问题.md）\n'; exit 1; }

step "1/6 检查电脑"
[ "$(uname -s)" = "Darwin" ] || fail "这个工具只支持 macOS。" "换一台 Mac 运行。"
MAC="$(sw_vers -productVersion)"; MAJOR="${MAC%%.*}"
[ "$MAJOR" -ge 13 ] || fail "macOS 版本太旧（${MAC}），需要 13 或更新。" "在“系统设置 → 通用 → 软件更新”里升级。"
ok "macOS ${MAC}（$(uname -m)）"
case "$HERE" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
    printf '  \033[33m!\033[0m 仓库放在“桌面 / 文稿 / 下载”里：第一次打开时 macOS 会问“是否允许访问”，点“允许”即可。\n'
    printf '    想省掉这一步，可以把仓库挪到家目录下（如 ~/variable-factory-lite）再运行 ./install.sh。\n' ;;
esac

step "2/6 找 Python（要 3.12 或更新）"
PY=""
for c in python3.14 python3.13 python3.12 python3; do
  for d in "" /opt/homebrew/bin/ /usr/local/bin/ "$HOME/.local/bin/"; do
    p="$d$c"
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      PY="$(command -v "$p")"; break 2
    fi
  done
done
[ -n "$PY" ] || fail "没找到 Python 3.12 或更新的版本（系统自带的 3.9 太旧）。" \
  "装了 Homebrew 的话运行：brew install python@3.13 ；没有 Homebrew 就到 https://www.python.org/downloads/macos/ 下载安装包。装好后再运行 ./install.sh"
ok "$("$PY" --version)（${PY}）"

step "3/6 检查 OpenCode（AI 对话靠它）"
OC="$(command -v opencode || true)"
for p in /opt/homebrew/bin/opencode /usr/local/bin/opencode "$HOME/.opencode/bin/opencode"; do
  [ -z "$OC" ] && [ -x "$p" ] && OC="$p"
done
[ -n "$OC" ] || fail "没装 OpenCode。" "运行：brew install opencode （没有 Homebrew 见 https://opencode.ai ）。装好后再运行 ./install.sh"
OCV="$("$OC" --version 2>/dev/null | head -1 | sed -E 's/[^0-9.]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"
OCMAJ="${OCV%%.*}"; OCMIN="$(echo "$OCV" | cut -d. -f2)"
if [ -z "$OCV" ] || [ "$OCMAJ" -lt 2 ] || { [ "$OCMAJ" -eq 2 ] && [ "$OCMIN" -lt 2 ]; }; then
  fail "OpenCode 版本太旧（${OCV:-读不出版本}），需要 2.2 或更新。" "运行：brew upgrade opencode （或 opencode upgrade），再运行 ./install.sh"
fi
ok "OpenCode ${OCV}（${OC}）"
[ "$OCMAJ" -gt 2 ] && printf '  \033[33m!\033[0m 这个工具在 OpenCode 2.2.7 上测过；你的版本更新，大多能用，遇到问题见 docs/常见问题.md。\n'

step "4/6 建虚拟环境、装依赖（第一次要几分钟）"
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
  rm -rf .venv
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --disable-pip-version-check --upgrade pip
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt || \
  fail "依赖没装上（多半是网络问题）。" "检查网络后再运行 ./install.sh；公司或学校网络可能要先连 VPN。"
ok "依赖装好了（.venv/）"

step "5/6 自检"
.venv/bin/python -m pytest -q tests >/tmp/variable-factory-lite-selftest.log 2>&1 || \
  fail "自检没通过，日志在 /tmp/variable-factory-lite-selftest.log" "把日志最后几十行发给帮你安装的 AI 或作者。"
ok "自检通过"
.venv/bin/python -m lite sample-data | sed 's/^/  /'

step "6/6 在桌面放入口"
.venv/bin/python -m lite install | sed 's/^/  /'

printf '\n\033[1;32m装好了。\033[0m 双击桌面上的“变量库工厂（单人版）”打开（或在这里运行 ./start.sh）。\n'
printf '第一次打开可能要等十几秒；浏览器里左边是和 AI 的对话，右边是工厂栏。用法见 README.md。\n'
