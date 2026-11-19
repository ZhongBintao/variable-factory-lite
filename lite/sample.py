# -*- coding: utf-8 -*-
"""合成的练习数据（数值全是随机造的，不是真数据）：python -m lite sample-data 生成到 ~/变量库工厂单人版/示例数据/。

列名仿照国内常见数据库的写法（Stkcd、Accper、A001000000…），用来练习“交数据 → 校验 → 合成 → 入库”：
  公司基本信息.csv      Stkcd 股票代码、ShortName 简称、Estbdt 成立日期、Listdt 上市日期
  资产负债表.csv        Stkcd、Accper 会计期间（年末）、Typrep 报表类型、A001000000 资产总计、A002000000 负债合计、
                        A001101000 货币资金、A001111000 应收账款、A001123000 存货、A002100000 流动负债合计、A001100000 流动资产合计
  利润表.csv            Stkcd、Accper、B001100000 营业收入、B002000000 净利润、B001216000 研发费用
  现金流量表.csv        Stkcd、Accper、C001000000 经营活动现金流量净额、C002006000 购建固定资产等支付的现金
  资产负债表_有问题.csv 故意做坏的一份（缺“资产总计”列、有乱码数字），用来看校验怎么挡
"""
import os

import numpy as np
import pandas as pd

from . import paths


def make(folder=None, n_firms=400, years=(2008, 2020), seed=7):
    folder = folder or paths.sub("示例数据")
    os.makedirs(folder, exist_ok=True)
    rng = np.random.default_rng(seed)
    codes = sorted(rng.choice(np.arange(1, 4000), n_firms, replace=False))
    codes = ["%06d" % (c if c < 1000 else 600000 + c) for c in codes]
    est = rng.integers(1980, 2006, n_firms)
    lst = np.minimum(est + rng.integers(1, 12, n_firms), 2012)
    info = pd.DataFrame({"Stkcd": codes, "ShortName": ["示例公司%03d" % i for i in range(n_firms)],
                         "Estbdt": ["%d-%02d-%02d" % (y, rng.integers(1, 13), rng.integers(1, 29)) for y in est],
                         "Listdt": ["%d-%02d-%02d" % (y, rng.integers(1, 13), rng.integers(1, 29)) for y in lst]})
    rows = []
    base = np.exp(rng.normal(21.5, 1.2, n_firms))
    for i, code in enumerate(codes):
        size = base[i]
        for y in range(years[0], years[1] + 1):
            if y < lst[i] or rng.random() < 0.03:
                continue
            size *= np.exp(rng.normal(0.08, 0.15))
            lev = float(np.clip(rng.normal(0.45, 0.18), 0.03, 0.97))
            cur = float(np.clip(rng.normal(0.55, 0.15), 0.1, 0.95))
            rev = size * float(np.clip(rng.normal(0.7, 0.3), 0.05, 3))
            ni = rev * rng.normal(0.06, 0.08)
            rows.append({"Stkcd": code, "Accper": "%d-12-31" % y, "Typrep": "A", "size": size, "lev": lev, "cur": cur, "rev": rev, "ni": ni})
    p = pd.DataFrame(rows)
    bs = pd.DataFrame({"Stkcd": p.Stkcd, "Accper": p.Accper, "Typrep": p.Typrep, "A001000000": p["size"].round(2),
                       "A002000000": (p["size"] * p.lev).round(2), "A001100000": (p["size"] * p.cur).round(2),
                       "A001101000": (p["size"] * p.cur * rng.uniform(0.1, 0.4, len(p))).round(2),
                       "A001111000": (p["size"] * p.cur * rng.uniform(0.1, 0.35, len(p))).round(2),
                       "A001123000": (p["size"] * p.cur * rng.uniform(0.05, 0.4, len(p))).round(2),
                       "A002100000": (p["size"] * p.lev * rng.uniform(0.5, 0.95, len(p))).round(2)})
    inc = pd.DataFrame({"Stkcd": p.Stkcd, "Accper": p.Accper, "B001100000": p.rev.round(2), "B002000000": p.ni.round(2),
                        "B001216000": (p.rev * np.clip(rng.normal(0.03, 0.02, len(p)), 0, None)).round(2)})
    cf = pd.DataFrame({"Stkcd": p.Stkcd, "Accper": p.Accper, "C001000000": (p.ni * rng.normal(1.2, 0.6, len(p))).round(2),
                       "C002006000": (p["size"] * np.clip(rng.normal(0.05, 0.03, len(p)), 0, None)).round(2)})
    bad = bs.drop(columns=["A001000000"]).copy()
    bad["A002000000"] = bad["A002000000"].astype(object)
    bad.loc[bad.sample(frac=0.2, random_state=1).index, "A002000000"] = "#N/A"
    for name, df in (("公司基本信息", info), ("资产负债表", bs), ("利润表", inc), ("现金流量表", cf), ("资产负债表_有问题", bad)):
        df.to_csv(os.path.join(folder, name + ".csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(folder, "说明.txt"), "w", encoding="utf-8") as f:
        f.write("这里的数据全是随机造的练习数据（%d 家虚构公司，%d—%d 年），不是真数据，只用来练习上传、校验、合成、入库。\n\n%s"
                % (n_firms, years[0], years[1], __doc__))
    return folder


PAPER_NAME = "示例论文_融资约束与企业投资（虚构）.pdf"
PAPER = [
    ("融资约束、现金流与企业投资：来自示例数据的证据", """（这是一篇为练习单人版而虚构的示例论文，作者、数据和结论都是编的，可以随意分发。）

摘要：本文以 2008—2020 年 400 家虚构上市公司为样本，检验融资约束是否放大企业投资对内部现金流的依赖。
我们用 SA 指数度量融资约束，发现融资约束越强的公司，投资—现金流敏感度越高。
本文的新意在于构造“融资约束 × 现金流”交互项，并给出可复现的变量定义。

关键词：融资约束；SA 指数；投资—现金流敏感度"""),
    ("一、引言", """企业投资是否受内部资金的限制，是公司金融的经典问题。融资约束较强的公司难以从外部筹集资金，
只能更多依赖经营活动产生的现金流来安排投资。本文在示例数据上重新检验这一关系。
第二部分介绍研究设计与变量定义，第三部分报告描述性统计，第四部分为结论。"""),
    ("二、研究设计", """（一）样本与数据
样本为 2008—2020 年 400 家虚构公司，财务数据来自资产负债表、利润表、现金流量表和公司基本信息表。

（二）模型设定
本文估计如下模型：
Inv(i,t) = β0 + β1·CF(i,t) + β2·SA(i,t) + β3·CF(i,t)×SA(i,t) + γ·Controls + ε(i,t)
其中 β3 衡量融资约束对投资—现金流敏感度的影响。

（三）变量定义
被解释变量为投资支出 Inv，等于购建固定资产、无形资产和其他长期资产支付的现金除以期初资产总计。
解释变量为现金流 CF，等于经营活动产生的现金流量净额除以期初资产总计。
融资约束用 SA 指数度量：SA = -0.737×Size + 0.043×Size^2 - 0.040×Age，其中 Size 为资产总计（百万元）的自然对数，
Age 为公司成立以来的年数。SA 指数取值越大，表示融资约束越强。
交互项 CF×SA 为现金流与 SA 指数的乘积。"""),
    ("表1 变量定义", """变量名称            符号      定义
投资支出            Inv       购建固定资产等支付的现金 / 期初资产总计
现金流              CF        经营活动现金流量净额 / 期初资产总计
融资约束（SA 指数） SA        -0.737×Size + 0.043×Size^2 - 0.040×Age
公司规模            Size      资产总计（百万元）的自然对数
公司年龄            Age       当年年份 - 成立年份
资产负债率          Lev       负债合计 / 资产总计
总资产收益率        ROA       净利润 / 资产总计
营业收入增长率      Growth    （本年营业收入 - 上年营业收入）/ 上年营业收入
现金持有            Cash      货币资金 / 资产总计
控制变量包括 Size、Lev、ROA、Growth 和 Cash，并控制年份和行业固定效应。"""),
    ("三、描述性统计与四、结论", """表2 报告主要变量的描述性统计（略，示例论文不提供真实结果）。
结论：在示例数据中，融资约束越强，投资对现金流越敏感。本文只用于演示“从论文到变量”的流程。

参考文献
（示例论文不列真实文献。）"""),
]


def make_paper(folder=None):
    """虚构的示例论文 PDF（中文，5 页），可以公开分发；用来练习上传论文、挑指标。返回路径。"""
    import pymupdf
    folder = folder or paths.sub("示例数据")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, PAPER_NAME)
    doc = pymupdf.open()
    doc.set_metadata({"title": PAPER[0][0], "author": "示例（虚构）"})
    for i, (head, text) in enumerate(PAPER):
        page = doc.new_page(width=595, height=842)
        page.insert_textbox(pymupdf.Rect(60, 60, 535, 110), head, fontname="china-s", fontsize=16 if i == 0 else 14)
        page.insert_textbox(pymupdf.Rect(60, 120, 535, 800), text, fontname="china-s", fontsize=10.5, lineheight=1.6)
        page.insert_text((290, 820), str(i + 1), fontname="helv", fontsize=9)
    doc.save(path)
    doc.close()
    return path
