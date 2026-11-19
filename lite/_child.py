# -*- coding: utf-8 -*-
"""子进程：真正执行 AI 的合成代码（lite/runner.py 调用）。结果写 status.json。"""
import json
import os
import sys
import traceback


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
