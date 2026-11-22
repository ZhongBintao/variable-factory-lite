# -*- coding: utf-8 -*-
"""子进程：真正执行 AI 的合成代码（lite/runner.py 调用）。结果写 status.json。"""
import json
import os
import sys
import traceback

# 审计钩子（Windows 上代替 Mac 的系统沙箱；见 lite/runner.py）：钩子一装就拆不掉，合成代码里的这些动作一律报错
_BLOCK = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.startfile", "os.fork", "os.forkpty",
          "os.kill", "os.killpg", "_winapi.CreateProcess", "socket.__new__", "socket.connect", "socket.bind", "socket.sendto",
          "socket.getaddrinfo", "urllib.Request", "http.client.connect", "ftplib.connect", "smtplib.connect",
          "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function", "ctypes.cdata", "ctypes.addressof", "ctypes.set_errno",
          "winreg.CreateKey", "winreg.OpenKey", "winreg.SetValue", "winreg.DeleteKey", "winreg.ConnectRegistry",
          "msvcrt.open_osfhandle", "_winapi.OpenProcess", "webbrowser.open", "sys.remote_exec")
_CHANGE = ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.link", "os.symlink",
           "os.utime", "shutil.rmtree", "shutil.copyfile", "shutil.copytree", "shutil.move", "shutil.chown")
_NO_IMPORT = ("ctypes", "_ctypes", "socket", "_socket", "ssl", "_ssl", "subprocess", "_winapi", "winreg", "multiprocessing")


def guard(work, secrets):
    norm = lambda p: os.path.normcase(os.path.realpath(p))      # noqa: E731
    work = norm(work)
    secrets = [norm(x) for x in secrets if x]
    devnull = {norm(os.devnull)}

    def under(p, base):
        return p == base or p.startswith(base.rstrip(os.sep) + os.sep)

    def path_of(a):
        if isinstance(a, int) or a is None:
            return None
        try:
            return norm(os.fsdecode(os.fspath(a)))
        except (TypeError, ValueError):
            return None

    def no(what):
        raise PermissionError("合成代码里不能%s（只能用 inputs 里的表算出 result）" % what)

    def hook(event, args):
        if event == "open":
            p = path_of(args[0])
            if p is None:
                return
            mode, flags = args[1] or "", args[2] or 0
            write = any(ch in str(mode) for ch in "wax+") or flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)
            if any(under(p, s) for s in secrets):
                no("读放口令和钥匙的文件夹")
            if write and not under(p, work) and p not in devnull:
                no("写临时文件夹以外的文件")
        elif event in _CHANGE:
            for a in args[:2]:
                p = path_of(a) if isinstance(a, (str, bytes, os.PathLike)) else None
                if p is not None and not under(p, work):
                    no("改动临时文件夹以外的文件")
        elif event == "import":
            if args[0] in _NO_IMPORT and args[0] not in sys.modules:
                no("用 %s（联网、开程序、调系统接口都不行）" % args[0])
        elif event.startswith(_BLOCK):
            no("联网、开别的程序或调系统底层接口（%s）" % event)

    sys.addaudithook(hook)


def main(work):
    cfg = json.load(open(os.path.join(work, "job.json"), encoding="utf-8"))
    status = {"ok": False}
    try:
        import numpy as np
        import pandas as pd
        from lite import datacheck
        inputs = {}
        for i in cfg["inputs"]:
            inputs[i["key"]] = datacheck.load_for_build(i["path"], i["need"], i["colmap"])
        g = {"inputs": inputs, "pd": pd, "np": np, "__name__": "__lite_build__"}
        if os.environ.get("LITE_GUARD"):
            guard(work, cfg.get("secrets") or [])
        try:
            exec(compile(cfg["code"], "合成代码", "exec"), g)
        except Exception:
            tb = traceback.format_exc()
            tb = tb[tb.find('File "合成代码"'):] if 'File "合成代码"' in tb else tb
            raise RuntimeError("合成代码报错：\n" + tb[-3000:])
        res = g.get("result")
        if not isinstance(res, pd.DataFrame):
            raise RuntimeError("代码跑完了，但没有得到 result（要把结果表放进变量 result，类型是 pandas.DataFrame）")
        keys, col = cfg["keys"], cfg["column"]
        miss = [k for k in keys + [col] if k not in res.columns]
        if miss:
            raise RuntimeError("result 缺这些列：%s（现有列：%s）。主键列和指标列要用 set_data_needs 里定的名字"
                               % ("、".join(miss), "、".join(map(str, res.columns))))
        if len(res) == 0:
            raise RuntimeError("result 一行都没有：检查合并、筛选条件")
        res = res.reset_index(drop=True)
        res.columns = [str(c) for c in res.columns]
        for c in res.columns:
            dt = res[c].dtype
            if pd.api.types.is_extension_array_dtype(dt) and pd.api.types.is_float_dtype(dt):
                res[c] = res[c].astype("float64")          # 可空小数（Float64）统一成普通小数，空值才不会写成 "nan"
            elif c in keys and pd.api.types.is_float_dtype(dt):
                whole = res[c].dropna()
                if len(whole) and (whole % 1 == 0).all():
                    res[c] = res[c].astype("Int64")        # 主键里的年份等整数不写成 2015.0
            elif str(res[c].dtype) == "string":
                res[c] = res[c].astype(object).where(res[c].notna(), None)
            if res[c].dtype == object:
                res[c] = res[c].where(res[c].isna(), res[c].astype(str))
        res.to_parquet(cfg["out"], index=False)
        status = {"ok": True}                              # 小结由父进程读结果文件自己算（lite/runner.py）
    except Exception as e:      # noqa
        status = {"ok": False, "error": str(e) if isinstance(e, RuntimeError) else "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc()[-2000:])}
    with open(os.path.join(work, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main(sys.argv[1])
