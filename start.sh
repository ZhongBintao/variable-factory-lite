#!/bin/bash
# 一键打开变量库工厂（单人版）：打开 OpenCode 后台和工厂服务，用浏览器打开。和双击桌面入口一样。
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "还没安装：先运行 ./install.sh"; exit 1; }
exec .venv/bin/python -m lite start "$@"
