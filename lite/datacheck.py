# -*- coding: utf-8 -*-
"""读人上传的数据文件，按 AI 列的“所需数据”校验。

所需数据（一份）的写法：
  {"key": "assets", "name": "年末总资产", "what": "每家公司每年年末的总资产（合并报表）",
   "columns": [{"name": "股票代码", "type": "code", "aliases": ["Stkcd", "证券代码"], "hint": "6 位，如 000001"},
               {"name": "年份", "type": "year", "aliases": ["Accper", "会计年度"]},
               {"name": "总资产", "type": "number", "aliases": ["A001000000", "资产总计"], "unit": "元"}],
   "unique": ["股票代码", "年份"],           # 可不写：这几列合起来不该重复
   "years": "2008-2020"}                    # 可不写：要覆盖的年份
列的类型：code（代码，按文字读，保留前导零）、year（年份，也认 2015-12-31 这种日期）、date（日期）、number（数）、text（文字）。

文件里的列名对不上时：先按别名认（不分大小写、不管空格下划线），还认不出就算“缺列”；
人可以在工厂栏里把“缺的列”对应到文件里的某一列（colmap），对应完重新校验。
校验结果：{"ok": 过没过, "problems": [挡住的原因…], "warnings": [不挡的提醒…], "info": {行数、列、前几行…}}
"""
import os
import re

import pandas as pd

TYPES = {"code": "代码", "year": "年份", "date": "日期", "number": "数", "text": "文字"}
READABLE = (".csv", ".txt", ".xlsx", ".xlsm", ".parquet", ".dta")
MIN_OK = 0.95       # 一列里能按类型读懂的比例低于这个就挡住
MAX_MISSING = 0.5   # 一列空着的比例高于这个就挡住


def norm(s):
    return re.sub(r"[\s_\-（）()\[\]]+", "", str(s)).lower()


def read(path, nrows=None):
    """把文件读成全是文字的表（不丢前导零）。读不了抛 ValueError（中文说明）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        raise ValueError("这是旧版 Excel（.xls），读不了：用 Excel 打开，另存为 .xlsx 或 .csv 再上传")
    if ext not in READABLE:
        raise ValueError("这种文件（%s）读不了：请上传 .csv、.xlsx、.parquet 或 .dta" % (ext or "没有扩展名"))
    try:
        if ext in (".csv", ".txt"):
            last = None
            for enc in ("utf-8-sig", "gb18030"):
                try:
                    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], nrows=nrows, encoding=enc,
                                       sep=None, engine="python")
                except UnicodeDecodeError as e:
                    last = e
            raise ValueError("文件的文字编码认不出（试了 UTF-8 和 GBK）：%s" % last)
        if ext in (".xlsx", ".xlsm"):
            return pd.read_excel(path, dtype=str, nrows=nrows)
        if ext == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_stata(path)
        df = df.head(nrows) if nrows else df
        return df.astype("string").astype(object).where(df.notna(), None)
    except ValueError:
        raise
    except Exception as e:      # noqa
        raise ValueError("文件打不开：%s: %s" % (type(e).__name__, str(e)[:200]))


def match_columns(df_cols, spec_cols, colmap=None):
    """所需的每一列 → 文件里的哪一列。返回 {所需列名: 文件列名或 None}。"""
    colmap = colmap or {}
    by_norm = {}
    for c in df_cols:
        by_norm.setdefault(norm(c), c)
    out = {}
    for sc in spec_cols:
        name = sc["name"]
        got = None
        if colmap.get(name) in df_cols:
            got = colmap[name]
        else:
            for cand in [name] + list(sc.get("aliases") or []):
                if norm(cand) in by_norm:
                    got = by_norm[norm(cand)]
                    break
        out[name] = got
    return out


def to_year(s):
    """一列文字 → 年份（数）。认 2015、2015.0、2015-12-31、2015/12/31、20151231。"""
    s = s.astype("string").str.strip()
    y = pd.to_numeric(s, errors="coerce")
    y = y.where((y % 1 == 0) & (y >= 1900) & (y <= 2100))
    m = y.isna() & s.notna()
    if m.any():
        d = pd.to_datetime(s[m].str.replace(r"^(\d{4})(\d{2})(\d{2})$", r"\1-\2-\3", regex=True), errors="coerce")
        y[m] = d.dt.year
    return y


# 这些写法都当“空”：Excel 的错误值（#N/A、#DIV/0! …）、各种“没有”
BLANKS = {"", "nan", "NaN", "NAN", "NULL", "null", "None", "none", "NA", "N/A", "n/a", "#N/A", "#N/A N/A", "#NA", "#DIV/0!",
          "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#NULL!", "-", "--", "—", "."}


def blank_out(series):
    s = series.astype("string").str.strip()
    return s.mask(s.isin(BLANKS))


def convert(series, typ):
    """按类型转换；返回 (转换后的列, 能读懂的比例 —— 只算不空的格子)。"""
    s = blank_out(series)
    filled = s.notna()
    n = int(filled.sum())
    if typ == "number":
        v = pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce").astype("float64")
    elif typ == "year":
        v = to_year(s).astype("float64").round().astype("Int64")    # 年份是整数（可空），导出不会写成 2015.0
    elif typ == "date":
        v = pd.to_datetime(s, errors="coerce")
    else:
        return s, 1.0
    good = int((v.notna() & filled).sum())
    return v, (good / n if n else 1.0)


def year_range(text):
    m = re.fullmatch(r"\s*(\d{4})\s*[-~～—至到]\s*(\d{4})\s*", str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def check(path, need, colmap=None):
    """校验一份文件。"""
    problems, warnings, info = [], [], {}
    try:
        df = read(path)
    except ValueError as e:
        return {"ok": False, "problems": [str(e)], "warnings": [], "info": {}, "mapping": {}}
    df.columns = [str(c).strip() for c in df.columns]
    info["rows"] = int(len(df))
    info["columns"] = list(df.columns)[:200]
    info["preview"] = df.head(5).fillna("").astype(str).values.tolist()
    if len(df) == 0:
        problems.append("文件里没有数据行")
    spec = need.get("columns") or []
    mapping = match_columns(list(df.columns), spec, colmap)
    missing = [c["name"] for c in spec if not mapping.get(c["name"]) and c.get("required", True)]
    if missing:
        problems.append("缺少这些列：%s。文件里的列是：%s。可以在下面把缺的列对应到文件里的某一列，或改好文件重新上传"
                        % ("、".join(missing), "、".join(list(df.columns)[:30]) + ("…" if len(df.columns) > 30 else "")))
    conv = {}
    for c in spec:
        col = mapping.get(c["name"])
        if not col or len(df) == 0:
            continue
        typ = c.get("type") or "text"
        v, ratio = convert(df[col], typ)
        conv[c["name"]] = v
        b = blank_out(df[col])
        miss = float(b.isna().mean()) if len(df) else 0.0
        odd = int((b.isna() & df[col].notna()).sum())
        if odd:
            ex = df[col][b.isna() & df[col].notna()].astype(str).str.strip()
            ex = ex[ex != ""].head(1).tolist()
            if ex:
                warnings.append("“%s”里有 %d 个“%s”这类格子，当作空值处理" % (c["name"], odd, ex[0]))
        if typ in ("number", "year", "date") and ratio < MIN_OK:
            bad = df[col][v.isna() & df[col].notna()].astype(str).head(3).tolist()
            problems.append("“%s”（文件里的“%s”）应该是%s，但有 %.0f%% 的格子读不懂，比如：%s"
                            % (c["name"], col, TYPES.get(typ, typ), (1 - ratio) * 100, "、".join(bad)))
        if miss > MAX_MISSING:
            problems.append("“%s”（文件里的“%s”）有 %.0f%% 是空的" % (c["name"], col, miss * 100))
        elif miss > 0.05:
            warnings.append("“%s”有 %.0f%% 是空的" % (c["name"], miss * 100))
        if typ == "code":
            s = df[col].dropna().astype(str)
            if len(s) and s.str.fullmatch(r"\d{1,5}").mean() > 0.3:
                warnings.append("“%s”里有不少不足 6 位的代码（如 %s），可能丢了前导零；合成时会补齐还是原样用，请留意"
                                % (c["name"], s[s.str.fullmatch(r"\d{1,5}")].iloc[0]))
    uniq = [u for u in (need.get("unique") or []) if mapping.get(u)]
    if uniq and len(df) and not missing:
        keys = pd.DataFrame({u: conv.get(u, df[mapping[u]]) for u in uniq})
        dup = int(keys.duplicated(keep=False).sum())
        if dup:
            ex = keys[keys.duplicated(keep=False)].head(2).astype(str).values.tolist()
            warnings.append("按 %s 有 %d 行重复（同一组出现不止一次），如 %s；合成代码要说清怎么处理"
                            % ("+".join(uniq), dup, "；".join("、".join(r) for r in ex)))
    ycol = next((c["name"] for c in spec if c.get("type") == "year" and c["name"] in conv), None)
    if ycol is not None:
        ys = conv[ycol].dropna()
        if len(ys):
            info["years"] = [int(ys.min()), int(ys.max())]
            want = year_range(need.get("years"))
            if want:
                have = set(int(y) for y in ys.unique())
                lack = [y for y in range(want[0], want[1] + 1) if y not in have]
                if len(lack) == want[1] - want[0] + 1:      # 年份只提醒不挡：用户自己的研究可以用别的年份
                    warnings.append("AI 列的是 %d—%d 年，文件里是 %d—%d 年，一年都不重合；如果你本来就要用这些年份，可以不管" % (want[0], want[1], info["years"][0], info["years"][1]))
                elif lack:
                    warnings.append("要 %d—%d 年，文件里缺这些年：%s" % (want[0], want[1], "、".join(map(str, lack[:12])) + ("…" if len(lack) > 12 else "")))
    return {"ok": not problems, "problems": problems, "warnings": warnings, "info": info, "mapping": mapping}


def load_for_build(path, need, colmap=None):
    """给合成代码用的表：所需列改成 AI 定的列名、按类型转好；文件里别的列原样带着（文字）。"""
    df = read(path)
    df.columns = [str(c).strip() for c in df.columns]
    mapping = match_columns(list(df.columns), need.get("columns") or [], colmap)
    out = df.copy()
    for c in need.get("columns") or []:
        col = mapping.get(c["name"])
        if not col:
            continue
        v, _ = convert(df[col], c.get("type") or "text")
        if c["name"] != col and c["name"] in out.columns:
            out = out.drop(columns=[c["name"]])
        out[c["name"]] = v
    return out
