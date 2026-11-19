# -*- coding: utf-8 -*-
"""合成结果的小结：给人看了能决定“入不入库”的信息——多少行、多少家、覆盖哪几年、每年多少、分布、缺失、
重复、极端值，再把值得注意的地方写成几句提醒。"""
import math
import re

import numpy as np
import pandas as pd

YEARISH = re.compile(r"(年|year|fyear|yr)", re.I)


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, 6)


def year_col(df, keys):
    for k in keys:
        if YEARISH.search(str(k)) and k in df.columns:
            return k
    return None


def summarize(df, keys, column):
    s = {"rows": int(len(df)), "columns": [str(c) for c in df.columns], "keys": keys, "column": column}
    alerts = []
    ent = keys[0] if keys and keys[0] in df.columns else None
    yc = year_col(df, keys)
    if ent and ent != yc:
        s["entities"] = int(df[ent].nunique())
    dup = int(df.duplicated(subset=[k for k in keys if k in df.columns], keep=False).sum()) if keys else 0
    s["duplicates"] = dup
    if dup:
        alerts.append("按主键（%s）有 %d 行重复：同一组出现了不止一次" % ("+".join(keys), dup))
    v = df[column]
    if pd.api.types.is_numeric_dtype(v.dtype):
        v = v.astype("float64")
    num = pd.to_numeric(v, errors="coerce") if v.dtype == object else v
    is_num = pd.api.types.is_numeric_dtype(num) and (num.notna().sum() >= max(1, 0.9 * v.notna().sum()))
    s["missing"] = int(v.isna().sum())
    s["missing_share"] = _f(v.isna().mean()) if len(v) else 0
    if len(v) and v.isna().mean() > 0.1:
        alerts.append("%s 有 %.1f%% 是空的（%d 行）" % (column, v.isna().mean() * 100, int(v.isna().sum())))
    if yc:
        by = df.groupby(yc)[column].agg(["size", "count"])
        if is_num:
            by["mean"] = pd.to_numeric(df[column], errors="coerce").groupby(df[yc]).mean()
        s["by_year"] = [{"year": _f(y) if not isinstance(y, str) else y, "rows": int(r["size"]), "filled": int(r["count"]),
                         "mean": _f(r.get("mean")) if is_num else None} for y, r in by.iterrows()]
        if len(by) >= 3:
            med = by["count"].median()
            thin = [str(int(y)) if isinstance(y, (int, float, np.integer, np.floating)) else str(y)
                    for y, r in by.iterrows() if r["count"] < 0.3 * med]
            if thin:
                alerts.append("这几年的数据明显偏少（不到中位数的三成）：%s" % "、".join(thin[:10]))
        ys = [y for y in by.index if isinstance(y, (int, float, np.integer, np.floating)) and not pd.isna(y)]
        if ys:
            s["years"] = [int(min(ys)), int(max(ys))]
            gaps = [y for y in range(int(min(ys)), int(max(ys)) + 1) if y not in set(int(x) for x in ys)]
            if gaps:
                alerts.append("中间缺这几年：%s" % "、".join(map(str, gaps[:10])))
    if is_num:
        x = num.astype(float)
        inf = int(np.isinf(x).sum())
        if inf:
            alerts.append("有 %d 个无穷大（多半是除以 0）" % inf)
        x = x[np.isfinite(x)]
        s["numeric"] = True
        if len(x):
            q = x.quantile([0, .01, .05, .25, .5, .75, .95, .99, 1]).tolist()
            s["stats"] = {"n": int(len(x)), "mean": _f(x.mean()), "sd": _f(x.std()), "min": _f(q[0]), "p1": _f(q[1]), "p5": _f(q[2]),
                          "p25": _f(q[3]), "median": _f(q[4]), "p75": _f(q[5]), "p95": _f(q[6]), "p99": _f(q[7]), "max": _f(q[8]),
                          "unique": int(x.nunique()), "zero_share": _f((x == 0).mean()), "neg_share": _f((x < 0).mean())}
            lo, hi = q[1], q[7]
            if hi > lo:
                inner = x[(x >= lo) & (x <= hi)]
                cnt, edges = np.histogram(inner, bins=12)
                s["hist"] = {"counts": [int(c) for c in cnt], "edges": [_f(e) for e in edges],
                             "below": int((x < lo).sum()), "above": int((x > hi).sum())}
            iqr = q[5] - q[3]
            if iqr > 0:
                far = int(((x < q[3] - 5 * iqr) | (x > q[5] + 5 * iqr)).sum())
                s["far"] = far
                if far:
                    alerts.append("有 %d 个离群很远的值（超出四分位距 5 倍），最小 %s、最大 %s，要不要缩尾请留意"
                                  % (far, _fmt(q[0]), _fmt(q[8])))
            if x.nunique() == 1:
                alerts.append("所有值都一样（%s），多半算错了" % _fmt(q[0]))
            show = [c for c in (keys or []) if c in df.columns][:3] + [column]
            d2 = df.loc[x.index, show].assign(**{column: x})
            s["top"] = d2.nlargest(3, column).astype(object).where(d2.nlargest(3, column).notna(), None).values.tolist()
            s["bottom"] = d2.nsmallest(3, column).astype(object).where(d2.nsmallest(3, column).notna(), None).values.tolist()
            s["show_cols"] = show
    else:
        s["numeric"] = False
        vc = v.astype(str).value_counts().head(10)
        s["categories"] = [[k, int(n)] for k, n in vc.items()]
    if len(df) < 30:
        alerts.append("结果只有 %d 行，样本很小" % len(df))
    s["sample"] = df.head(5).astype(object).where(df.head(5).notna(), None).values.tolist()
    s["alerts"] = alerts
    return s


def _fmt(x):
    if x is None:
        return "—"
    x = float(x)
    if x == 0:
        return "0"
    if abs(x) >= 1e6 or abs(x) < 1e-3:
        return "%.3g" % x
    return ("%.4f" % x).rstrip("0").rstrip(".")
