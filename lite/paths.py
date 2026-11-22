# -*- coding: utf-8 -*-
"""单人版的东西放在哪。

默认放在 ~/变量库工厂单人版/（家目录下，不在“桌面”“文稿”里：那两个文件夹可能开着 iCloud 同步，
论文和数据不该被同步到网盘）。测试、试用可以用环境变量 LITE_HOME 换地方。

~/变量库工厂单人版/
  工作区/     OpenCode 的项目文件夹（接好工厂工具的 opencode.jsonc、给 AI 的说明 AGENTS.md）；对话都开在这里
  库/         数据库 lite.db、论文 PDF、上传的数据、合成记录、入库的变量
  导出/       每次导出一个子文件夹
  示例数据/   合成的练习数据（python -m lite sample-data 生成，数值是虚构的）
  设置/       钥匙、进程号（只本人可读）
  日志/
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("LITE_PORT") or 8797)
# 公开版（只有单人版的仓库）：没有旧库的登记卡和数据文件，旧库只带变量名、定义、公式（lite/oldlib_defs.json）
PUBLIC = not os.path.isdir(os.path.join(REPO, "warehouse"))
WINDOWS = os.name == "nt"
# Windows：工厂服务在后台跑、没有窗口，它再叫起的命令（opencode、git、合成代码）也不许弹黑框
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def home():
    return os.path.abspath(os.path.expanduser(os.environ.get("LITE_HOME") or "~/变量库工厂单人版"))


def sub(*parts):
    return os.path.join(home(), *parts)


def lib(*parts):
    return sub("库", *parts)


def workspace():
    return sub("工作区")


def exports():
    return sub("导出")


def cfg(*parts):
    return sub("设置", *parts)


def logs(*parts):
    return sub("日志", *parts)


def python():
    """跑工厂用的 Python（仓库的 .venv；没有就用当前这个）。"""
    v = os.path.join(REPO, ".venv", "Scripts", "python.exe") if WINDOWS else os.path.join(REPO, ".venv", "bin", "python")
    return v if os.path.exists(v) else sys.executable


def py_cmd(*args):
    """用工厂的 Python 跑：Windows 上加 -X utf8（中文一律按 UTF-8 读写，不跟系统的 GBK）。"""
    return [python()] + (["-X", "utf8"] if WINDOWS else []) + list(args)


def ensure():
    for d in (lib(), lib("papers"), lib("data"), lib("builds"), lib("variables"), workspace(), exports(), logs()):
        os.makedirs(d, exist_ok=True)
    os.makedirs(cfg(), mode=0o700, exist_ok=True)
