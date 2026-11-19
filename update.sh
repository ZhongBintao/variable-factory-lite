#!/bin/bash
# 更新到新版：拉取最新代码 → 重新安装（依赖、自检、桌面入口）→ 关掉旧的工厂服务（下次打开就是新版）。
# 你的论文和数据在 ~/变量库工厂单人版/，更新不会动它们。
set -euo pipefail
cd "$(dirname "$0")"
if [ -n "$(git status --porcelain -- . ':!.venv' 2>/dev/null)" ]; then
  echo "仓库里有你改过的文件，先不更新（免得覆盖）。改动列表："; git status --short; exit 1
fi
OLD="$(git describe --tags --always 2>/dev/null || true)"
git pull --ff-only --tags
NEW="$(git describe --tags --always 2>/dev/null || true)"
[ -x .venv/bin/python ] && .venv/bin/python -m lite stop >/dev/null 2>&1 || true
./install.sh
echo "已从 ${OLD:-旧版} 更新到 ${NEW:-新版}。双击桌面入口打开新版。"
