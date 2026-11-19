# -*- coding: utf-8 -*-
"""导出：从总库里挑几个指标，导出成一个文件夹（~/变量库工厂单人版/导出/<时间>/）。

  数据/            每个有数据的指标一份 CSV（utf-8-sig，代码列按文字存，不丢前导零）
  合并数据.csv     选的指标主键一样时，按主键合成一张宽表
  指标说明.xlsx    每个指标的定义、公式（含 LaTeX 写法）、出处（论文、页码、原文摘录）、用的数据（文件名 + MD5）、放行理由、合成记录
  合成代码/        每个指标的合成代码
  说明.txt
"""
import json
import os
import time

import pandas as pd

from . import paths, store


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time() + 8 * 3600))


def _safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))[:40]


def _to_code_year(frame):
    """把一个指标的表改成 主键 = 股票代码（6 位文字）+ 年份（整数）；认不出就原样返回。"""
    oid, keys, df = frame
    if len(keys) != 2:
        return frame
    a, b = keys
    code = df[a].astype(str).str.strip().str.split(".").str[0]
    if not code.str.fullmatch(r"\d{1,6}").mean() > 0.9:
        return frame
    year = pd.to_numeric(df[b], errors="coerce")
    if not year.between(1900, 2100).mean() > 0.9:
        return frame
    out = df.drop(columns=[a, b]).copy()
    out.insert(0, "年份", year.astype("Int64"))
    out.insert(0, "股票代码", code.str.zfill(6))
    return oid, ["股票代码", "年份"], out


def export(ids):
    ids = [i for i in dict.fromkeys(ids or []) if i]
    if not ids:
        raise store.LiteError("一个都没选", "在变量库里勾选要导出的指标")
    out = os.path.join(paths.exports(), _stamp())
    os.makedirs(os.path.join(out, "数据"), exist_ok=True)
    os.makedirs(os.path.join(out, "合成代码"), exist_ok=True)
    rows, frames, skipped = [], [], []
    with store.ro() as c:
        for oid in ids:
            if oid.startswith("gv"):
                o = store._must(c, "oldlib", oid, "旧库变量")
                srcs = o["sources"] or []
                rows.append({"编号": oid, "名称": o["name"], "英文名": o["name_en"], "列名": oid, "状态": "旧库" if not paths.PUBLIC else "内置定义",
                             "定义": o["definition"] or "；".join(m.get("label", "") for m in o["meanings"] or []), "公式": o["formula"] or "", "公式（LaTeX）": "", "符号（LaTeX）": "", "单位": o["unit"],
                             "数据形状": o["shape"], "主键": "firm_id + fyear",
                             "论文": "；".join(sorted({s.get("paper_id") or "" for s in srcs})), "论文题目": "", "页码": "",
                             "原文摘录": " ｜ ".join("%s：%s（%s）" % (s.get("paper_id"), s.get("quote"), s.get("location")) for s in srcs[:5]),
                             "所需数据": "", "用的数据文件（MD5）": "", "放行理由": "", "合成记录": "", "入库时间": ""})
                if o["data"] and os.path.isfile(o["data"]):
                    df = pd.read_parquet(o["data"])
                    df.to_csv(os.path.join(out, "数据", "%s.csv" % oid), index=False, encoding="utf-8-sig")
                    keys = [k for k in ("firm_id", "fyear") if k in df.columns]
                    frames.append((oid, keys, df))
                else:
                    skipped.append("%s（%s只带了定义）" % (oid, "内置定义" if paths.PUBLIC else "旧库"))
                continue
            ind = store._must(c, "indicators", oid, "指标")
            v = store._ind_view(c, ind, full=True)
            p = store._one(c, "SELECT * FROM papers WHERE id = ?", ind["paper"])
            r = v["run_info"] or {}
            files = "；".join("%s（%s）" % (i["file"], i["md5"]) for i in (r.get("inputs") or []))
            rows.append({"编号": oid, "名称": ind["name"], "英文名": ind["name_en"], "列名": ind["column"], "状态": ind["state"],
                         "定义": ind["definition"], "公式": ind["formula"], "公式（LaTeX）": ind["formula_tex"] or "",
                         "符号（LaTeX）": ind["symbol_tex"] or "", "单位": ind["unit"], "数据形状": ind["shape"],
                         "主键": " + ".join(ind["keys"] or []), "论文": ind["paper"], "论文题目": p["title"] if p else "",
                         "页码": "PDF 第 %s 页" % ind["page"], "原文摘录": ind["quote"],
                         "所需数据": "；".join("%s：%s" % (n["name"], n["what"]) for n in ind["needs"] or []),
                         "用的数据文件（MD5）": files, "放行理由": "；".join("%s：%s" % (o["file"], o["reason"]) for o in v["overrides"]),
                         "合成记录": r.get("id", ""), "入库时间": ind["admitted"]})
            if ind["state"] == "已入库" and r.get("code"):
                with open(os.path.join(out, "合成代码", "%s_%s.py" % (oid, _safe(ind["column"]))), "w", encoding="utf-8") as f:
                    f.write("# %s %s（%s）\n# 出处：%s《%s》PDF 第 %s 页\n# 用的数据：%s\n# 合成记录 %s，代码里的 inputs 是工厂按所需数据读好的表\n\n%s\n"
                            % (oid, ind["name"], ind["column"], ind["paper"], p["title"] if p else "", ind["page"], files, r.get("id"), r["code"]))
                path = paths.lib("variables", oid + ".parquet")
                df = pd.read_parquet(path)
                df.to_csv(os.path.join(out, "数据", "%s_%s.csv" % (oid, _safe(ind["column"]))), index=False, encoding="utf-8-sig")
                frames.append((oid, list(ind["keys"] or []), df))
            else:
                skipped.append("%s（%s，只有定义）" % (oid, ind["state"]))
    defs = pd.DataFrame(rows)
    defs.to_excel(os.path.join(out, "指标说明.xlsx"), index=False)
    defs.to_csv(os.path.join(out, "指标说明.csv"), index=False, encoding="utf-8-sig")
    merged = None
    if len(frames) >= 2 and len({tuple(k) for _, k, _ in frames}) > 1:
        frames = [_to_code_year(f) for f in frames]          # 旧库 firm_id + fyear、新指标 股票代码 + 年份：统一成 股票代码 + 年份
    if len(frames) >= 2 and len({tuple(k) for _, k, _ in frames}) == 1 and frames[0][1]:
        keys = frames[0][1]
        for oid, _, df in frames:
            df = df.drop_duplicates(subset=keys)
            vals = [c for c in df.columns if c not in keys]
            df = df[keys + vals].rename(columns={c: c if c not in (merged.columns if merged is not None else []) else "%s_%s" % (c, oid) for c in vals})
            merged = df if merged is None else merged.merge(df, on=keys, how="outer")
        merged.to_csv(os.path.join(out, "合并数据.csv"), index=False, encoding="utf-8-sig")
    note = ["变量库工厂（单人版）导出 · %s（北京时间）" % store.now(), "",
            "指标：%s" % "、".join(ids),
            "数据/：每个有数据的指标一份 CSV" + ("；合并数据.csv：按主键（%s）合成的宽表" % " + ".join(frames[0][1]) if merged is not None else ""),
            "指标说明.xlsx：定义、公式、出处（论文、页码、原文摘录）、用的数据（文件名 + MD5）、放行理由、合成记录",
            "合成代码/：每个指标的合成代码"]
    if skipped:
        note += ["", "只有定义、没有数据的：%s" % "、".join(skipped)]
    if len(frames) >= 2 and merged is None:
        note += ["", "选的指标主键不一样，没有合成宽表，请分别用 数据/ 里的文件"]
    with open(os.path.join(out, "说明.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(note) + "\n")
    with store.tx() as c:
        store.log(c, "导出", "导出", "导出 %d 个指标到 %s" % (len(ids), out))
    return {"folder": out, "n": len(ids), "with_data": len(frames), "merged": merged is not None, "skipped": skipped}
