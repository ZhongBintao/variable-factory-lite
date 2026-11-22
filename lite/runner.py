# -*- coding: utf-8 -*-
"""跑 AI 写的合成代码：在单独的子进程里跑（限时），跑完核对结果的样子，再算小结。

代码里能直接用：
  inputs   {所需数据的 key: 表(pandas.DataFrame)}；所需的列已改成 AI 定的列名并按类型转好
           （code/text 是文字，保留前导零；number、year 是数；date 是日期），文件里别的列原样带着（文字）
  pd, np   pandas、numpy
要做的：把结果放进变量 result（pandas.DataFrame），含主键列（keys）和指标列（column），一行一个主键。
print 的内容会记进日志。不要读写别的文件、不要联网。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from . import paths

TIMEOUT = 300


# AI 写的代码只能算数：在 macOS 自带的沙箱（sandbox-exec）里跑——不能联网、不能执行或让系统打开别的程序（系统服务一律不让连）、
# 除了自己的临时文件夹哪儿都不能写（工厂的库、你的文件都改不了），也读不到放口令和钥匙的地方。
# 环境变量只给最少的几项（不带 LITE_HOME 等），代码就算 import 工厂自己的模块，也碰不到库。
# Windows 没有这种系统沙箱：改由子进程自己装“审计钩子”拦（见 lite/_child.py 的 guard）——不能联网、不能开别的程序、
# 不能调系统底层接口（ctypes）、除了自己的临时文件夹哪儿都不能写、读不到放口令和钥匙的地方。比 Mac 的沙箱弱，防的是 AI 写错，不是防黑客。
PROFILE = """(version 1)
(allow default)
(deny network*)
(deny process-exec*)
(allow process-exec* (literal (param "PY")) (literal (param "PYREAL")) (subpath (param "PYHOME")))
(deny file-write*)
(allow file-write* (subpath (param "WORK")) (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr") (literal "/dev/dtracehelper"))
(deny lsopen)
(deny appleevent-send)
(deny mach-lookup)
(deny file-read* (subpath (param "SECRET1")) (subpath (param "SECRET2")) (subpath (param "SECRET3")) (subpath (param "SECRET4")) (subpath (param "SECRET5")))
"""


def sandboxed(cmd, work):
    exe = shutil.which("sandbox-exec") or ("/usr/bin/sandbox-exec" if os.path.exists("/usr/bin/sandbox-exec") else None)
    if not exe:
        return cmd                      # 不是 Mac：由子进程自己拦（secret_dirs 交给它，见 run）
    secrets = secret_dirs()[:5]
    args = [exe, "-p", PROFILE, "-D", "WORK=" + os.path.realpath(work), "-D", "PY=" + cmd[0], "-D", "PYREAL=" + os.path.realpath(cmd[0]),
            "-D", "PYHOME=" + os.path.realpath(sys.base_prefix)]
    for i, sp in enumerate(secrets, 1):
        args += ["-D", "SECRET%d=%s" % (i, os.path.realpath(sp))]
    return args + cmd


def secret_dirs():
    """合成代码不许读的地方：放口令、钥匙、OpenCode 登录信息的文件夹。前 5 个给 Mac 沙箱。"""
    home = os.path.expanduser("~")
    d = [os.path.join(home, ".config"), os.path.join(home, ".ssh"), os.path.join(home, "Library", "Keychains"),
         os.path.realpath(paths.cfg()), os.path.join(home, ".local", "share", "opencode")]
    if paths.WINDOWS:
        d += [os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"),
              os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), "opencode"),
              os.path.join(home, ".git-credentials"), os.path.join(home, ".aws"), os.path.join(home, ".azure")]
    return d


def clean_env(work):
    env = {"PATH": "/usr/bin:/bin", "HOME": work, "TMPDIR": work, "PYTHONPATH": paths.REPO, "PYTHONIOENCODING": "utf-8",
           "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg", "LANG": "en_US.UTF-8", "LITE_SANDBOX": "1"}
    if paths.WINDOWS:
        root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
        env.update({"PATH": os.pathsep.join([os.path.dirname(os.path.realpath(sys.executable)), sys.base_prefix,
                                              os.path.join(root, "System32"), root]),
                    "SYSTEMROOT": root, "WINDIR": root, "TEMP": work, "TMP": work, "USERPROFILE": work,
                    "PYTHONUTF8": "1", "LITE_GUARD": "1"})
    return env


def run(code, inputs, keys, column, timeout=TIMEOUT):
    """返回 {ok, error, log, summary, tmp_out}。"""
    work = tempfile.mkdtemp(prefix="lite-build-")
    cfg = {"code": code, "keys": keys, "column": column, "out": os.path.join(work, "result.parquet"),
           "inputs": [{"key": i["key"], "path": i["path"], "need": i["need"], "colmap": i.get("colmap") or {}} for i in inputs],
           "secrets": secret_dirs()}
    with open(os.path.join(work, "job.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    try:
        p = subprocess.run(sandboxed(paths.py_cmd("-m", "lite._child", work), work), cwd=work, env=clean_env(work),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=paths.NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "合成代码跑了 %d 秒还没完，停掉了。检查有没有死循环，或数据太大要换更快的写法" % timeout, "log": ""}
    try:
        with open(os.path.join(work, "status.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {"ok": False, "error": "合成代码没跑完就退出了：\n" + (p.stderr or "")[-3000:]}
    st["log"] = ((p.stdout or "")[-4000:] + ("\n" + p.stderr[-2000:] if p.stderr and not st.get("ok") else "")).strip()
    if st.get("ok"):
        # 小结由工厂自己（沙箱外）读结果文件算，不用子进程报的：合成代码改不了它
        try:
            import pandas as pd
            from . import summary
            res = pd.read_parquet(cfg["out"])
            miss = [k for k in list(keys) + [column] if k not in res.columns]
            if miss or len(res) == 0:
                raise ValueError("结果文件缺列 %s 或没有行" % "、".join(miss))
            st["summary"] = json.loads(json.dumps(summary.summarize(res, keys, column), default=str))
            st["tmp_out"] = cfg["out"]
        except Exception as e:      # noqa
            st = {"ok": False, "error": "合成结果读不出来：%s" % e, "log": st.get("log", "")}
    return st


def build(indicator, code, note=""):
    """合成一个指标：取齐数据 → 跑代码 → 记下来。返回 (合成记录编号, 结果)。"""
    from . import store
    if not (code or "").strip():
        raise store.LiteError("code 是空的", "写一段 Python：用 inputs 里的表算出 result")
    ind, inputs = store.build_inputs(indicator)
    if not ind["column"] or not ind["keys"]:
        raise store.LiteError("%s 还没定结果的列名和主键" % indicator, "先用 set_data_needs 给出 column 和 keys")
    res = run(code, inputs, ind["keys"], ind["column"])
    rid = store.record_run(indicator, code, note, res, inputs)
    return rid, res


if __name__ == "__main__":
    print(__doc__, file=sys.stderr)
