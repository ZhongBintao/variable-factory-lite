# -*- coding: utf-8 -*-
"""单人版（lite）的单元测试：只用临时目录、合成 PDF 和合成数据，不碰真库、不需要 OpenCode。"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import anyio
import pandas as pd
import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)

PAGE2 = ("Variable definitions. Firm size is measured as the natural logarithm of total assets. "
         "The SA index is calculated as (-0.737*Size) + (0.043*Size2) - (0.040*Age), where Age is years since founding.")


@pytest.fixture()
def lite(tmp_path, monkeypatch):
    monkeypatch.setenv("LITE_HOME", str(tmp_path / "home"))
    from lite import store, paths  # noqa
    paths.ensure()
    pdf = tmp_path / "paper.pdf"
    import pymupdf
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "A synthetic paper about financing constraints.", fontsize=11)
    p = d.new_page()
    p.insert_textbox(pymupdf.Rect(72, 72, 520, 400), PAGE2, fontsize=11)
    d.save(str(pdf))
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"Stkcd": ["000001", "000002", "600003"] * 3, "Accper": ["2018-12-31"] * 3 + ["2019-12-31"] * 3 + ["2020-12-31"] * 3,
                  "A001000000": [5e9, 8e8, 1.2e10, 5.5e9, 9e8, 1.3e10, 6e9, 1e9, 1.4e10]}).to_csv(data / "bs.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"Stkcd": ["000001", "000002", "600003"], "Estbdt": ["1990-05-01", "2001-03-02", "1995-07-09"]}).to_csv(data / "info.csv", index=False)
    pd.DataFrame({"code": ["000001", "000002"], "yr": ["2018", "x"], "v": ["1", "2"]}).to_csv(data / "bad.csv", index=False)
    return {"pdf": str(pdf), "data": data}


NEEDS = [{"key": "bs", "name": "资产负债表", "what": "年末总资产", "years": "2018-2020", "unique": ["股票代码", "年份"],
          "columns": [{"name": "股票代码", "type": "code", "aliases": ["Stkcd"]}, {"name": "年份", "type": "year", "aliases": ["Accper"]},
                      {"name": "总资产", "type": "number", "aliases": ["A001000000"]}]},
         {"key": "info", "name": "公司基本信息", "what": "成立日期",
          "columns": [{"name": "股票代码", "type": "code", "aliases": ["Stkcd"]}, {"name": "成立日期", "type": "date", "aliases": ["Estbdt"]}]}]
CODE = """
bs = inputs["bs"]; info = inputs["info"]
df = bs.merge(info[["股票代码", "成立日期"]], on="股票代码", how="left")
size = np.log(df["总资产"] / 1e6)
df["SA"] = -0.737 * size + 0.043 * size ** 2 - 0.040 * (df["年份"] - df["成立日期"].dt.year)
result = df[["股票代码", "年份", "SA"]]
"""


def cand(**kw):
    c = {"name": "SA 指数", "name_en": "SA index", "role": "解释变量", "definition": "融资约束", "page": 2, "recommend": True, "reason": "只用规模和年龄",
         "formula": "SA = -0.737*Size + 0.043*Size^2 - 0.040*Age", "formula_tex": "SA = -0.737\\,Size + 0.043\\,Size^2 - 0.040\\,Age", "symbol_tex": "SA",
         "quote": "The SA index is calculated as (−0.737*Size) + (0.043*Size2) − (0.040*Age)"}
    c.update(kw)
    return c


def test_quote_check_and_candidates(lite):
    from lite import store
    p = store.add_paper(lite["pdf"], "paper.pdf", "ses_a")
    assert p["id"] == "P001" and p["pages"] == 2 and not p["dup"]
    assert store.add_paper(lite["pdf"], "again.pdf", "ses_b")["dup"]          # 同一份 PDF 不重复登记
    r = store.save_candidates("P001", [
        cand(),
        cand(name="公司规模", quote="Firm size is measured as the natural logarithm of total assets", recommend=False, common=True),
        cand(name="编造的", quote="this sentence is not in the paper at all"),
        cand(name="页码错", quote="A synthetic paper about financing constraints", page=2, recommend=False),
        cand(name="推荐没理由", reason="", quote="Firm size is measured as the natural"),
        cand(name="库里乱写", in_library="gv9999", recommend=False),
        cand(name="推荐没公式", formula="", formula_tex="", quote="Firm size is measured as the natural"),
        cand(name="不推荐只写定义", recommend=False, reason="写了也不存", formula="", formula_tex="", symbol_tex=""),
    ], title="合成论文")
    assert len(r["saved"]) == 4
    why = {b["name"]: b["why"] for b in r["rejected"]}
    assert "找不到这段摘录" in why["编造的"]
    assert "在第 1 页" in why["页码错"]
    assert "reason" in why["推荐没理由"]
    assert "formula" in why["推荐没公式"]
    cs = {c["name"]: c for c in store.candidates("P001")}
    assert cs["库里乱写"]["in_library"] == ""                 # 乱写的编号不用，工厂自己对（没对上就空）
    assert cs["不推荐只写定义"]["reason"] == "" and cs["不推荐只写定义"]["formula"] == ""
    assert cs["SA 指数"]["formula_tex"].startswith("SA =") and cs["SA 指数"]["symbol_tex"] == "SA"
    assert store.detail("P001")["paper"]["title"] == "合成论文"
    with pytest.raises(store.LiteError):
        store.add_paper(str(lite["data"] / "bs.csv"), "bs.csv")


def test_full_line(lite):
    from lite import export, runner, store
    store.add_paper(lite["pdf"], "paper.pdf", "ses_a")
    store.save_candidates("P001", [cand()])
    made = store.choose("P001", ["C0001"])
    vid = made[0]["id"]
    assert store.detail(vid)["state"] == "待列数据"
    with pytest.raises(store.LiteError):
        store.set_needs(vid, [{"key": "x"}], "SA", ["股票代码"])
    store.set_needs(vid, NEEDS, "SA", ["股票代码", "年份"], unit="指数", shape="公司-年")
    assert store.detail(vid)["state"] == "待交数据"
    bad = store.add_datafile(vid, "bs", str(lite["data"] / "bad.csv"), "bad.csv")
    assert not bad["ok"] and any("缺少这些列" in x for x in bad["problems"])
    # 对应列后还是读不懂“年份”里的 x、没有总资产 → 仍不通过；写理由放行
    r = store.set_colmap(bad["datafile"], {"股票代码": "code", "年份": "yr", "总资产": "v"})
    assert not r["ok"]
    store.override(bad["datafile"], "测试：知道有一格坏了")
    assert any(o["reason"].startswith("测试") for o in store.detail(vid)["overrides"])
    # 换成好的文件：旧的作废，放行理由跟着旧文件走
    ok = store.add_datafile(vid, "bs", str(lite["data"] / "bs.csv"), "bs.csv")
    assert ok["ok"] and ok["state"] == "待交数据"
    ok2 = store.add_datafile(vid, "info", str(lite["data"] / "info.csv"), "info.csv")
    assert ok2["state"] == "待合成"
    with pytest.raises(store.LiteError):
        store.admit(vid)
    rid, res = runner.build(vid, "result = 1")
    assert not res["ok"] and "result" in res["error"]
    rid, res = runner.build(vid, "raise ValueError('坏了')")
    assert not res["ok"] and "坏了" in res["error"]
    rid, res = runner.build(vid, CODE, note="总资产除以 100 万取对数")
    assert res["ok"], res
    sm = res["summary"]
    assert sm["rows"] == 9 and sm["entities"] == 3 and sm["years"] == [2018, 2020] and sm["duplicates"] == 0
    d = store.detail(vid)
    assert d["state"] == "待入库" and d["run_info"]["fresh"]
    store.admit(vid)
    assert store.detail(vid)["state"] == "已入库"
    assert os.path.isfile(os.path.join(os.environ["LITE_HOME"], "库", "variables", vid + ".parquet"))
    lib = store.library(kind="本工具")["items"]
    assert lib[0]["id"] == vid
    assert defs_has_tex(export, vid)
    out = export.export([vid])
    defs = pd.read_csv(os.path.join(out["folder"], "指标说明.csv"), encoding="utf-8-sig", dtype=str)
    assert defs.loc[0, "原文摘录"].startswith("The SA index") and "bs.csv" in defs.loc[0, "用的数据文件（MD5）"]
    csv = [f for f in os.listdir(os.path.join(out["folder"], "数据"))][0]
    assert pd.read_csv(os.path.join(out["folder"], "数据", csv), dtype=str)["股票代码"].iloc[0] == "000001"   # 前导零还在
    kinds = [e["kind"] for e in d["events"]] + ["入库"]
    for k in ("选中", "列所需数据", "上传数据", "放行", "合成", "入库"):
        assert k in kinds


def test_new_data_invalidates_run_and_defer(lite):
    from lite import runner, store
    store.add_paper(lite["pdf"], "paper.pdf", "ses_a")
    store.save_candidates("P001", [cand(), cand(name="公司规模", quote="Firm size is measured as the natural logarithm of total assets", recommend=False)])
    store.choose("P001", ["C0001", "C0002"])
    store.set_needs("V0001", NEEDS, "SA", ["股票代码", "年份"])
    store.add_datafile("V0001", "bs", str(lite["data"] / "bs.csv"), "bs.csv")
    store.add_datafile("V0001", "info", str(lite["data"] / "info.csv"), "info.csv")
    runner.build("V0001", CODE)
    assert store.detail("V0001")["state"] == "待入库"
    df = pd.read_csv(lite["data"] / "info.csv", dtype=str)
    df.loc[0, "Estbdt"] = "1991-01-01"
    df.to_csv(lite["data"] / "info2.csv", index=False)
    store.add_datafile("V0001", "info", str(lite["data"] / "info2.csv"), "info2.csv")
    assert store.detail("V0001")["state"] == "待合成"          # 数据换了，旧结果作废
    store.defer("V0002")
    assert store.detail("V0002")["state"] == "等数据"
    assert any(x["id"] == "V0002" and x["state"] == "等数据" for x in store.library()["items"])
    store.resume("V0002")
    assert store.detail("V0002")["state"] == "待列数据"
    store.drop("V0002")
    assert store.detail("C0002")["state"] == "待挑选"


def test_library_import_and_search(lite):
    from lite import library, store
    n = library.import_cards()
    assert n > 50
    hits = store.search_library("ROA")
    assert hits and hits[0]["where"] == "旧库" and "ROA" in (hits[0]["name"] + hits[0]["name_en"])
    assert not any("sales" in (h["name_en"] or "").lower() and "sa " not in (h["name_en"] or "").lower() for h in store.search_library("SA"))
    with pytest.raises(store.LiteError):
        store.search_library("")


def defs_has_tex(export, vid):
    out = export.export([vid])
    defs = pd.read_csv(os.path.join(out["folder"], "指标说明.csv"), encoding="utf-8-sig", dtype=str)
    return defs.loc[0, "公式（LaTeX）"].startswith("SA =") and defs.loc[0, "符号（LaTeX）"] == "SA"


def test_datacheck_types():
    from lite import datacheck
    v, ratio = datacheck.convert(pd.Series(["2015", "2016-12-31", "20171231", None]), "year")
    assert list(v[:3]) == [2015, 2016, 2017] and ratio == 1.0
    v, ratio = datacheck.convert(pd.Series(["1,000", "x", "3"]), "number")
    assert ratio == pytest.approx(2 / 3)


def _req(srv, path, key, body=None, raw=None, method=None):
    url = "http://127.0.0.1:%d%s" % (srv.server_address[1], path)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"),
                               headers={"X-Lite-Key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read())


def test_server_api(lite, monkeypatch):
    from lite import opencode, server
    sent = []
    monkeypatch.setattr(opencode, "session_info", lambda sid: {"id": sid, "title": "t", "in_workspace": sid.startswith("ses_in")})
    made = iter(["ses_innew", "ses_in3", "ses_in4", "ses_inlib", "ses_in6"])
    monkeypatch.setattr(opencode, "new_session", lambda title="": next(made))
    monkeypatch.setattr(opencode, "rename", lambda *a: None)
    monkeypatch.setattr(opencode, "send", lambda sid, text: (sent.append((sid, text)), (True, ""))[1])
    srv = server.make_server(port=0, key="k" * 32, upstream=type("U", (), {"get": lambda self, fresh=False: None})(),
                             send=lambda sid, text: sent.append((sid, text)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _req(srv, "/lite/api/stamp", "wrong")
        assert e.value.code == 403
        pdf = open(lite["pdf"], "rb").read()
        r = _req(srv, "/lite/api/upload-paper?session=ses_in1&name=paper.pdf", "k" * 32, raw=pdf)
        assert r["paper"] == "P001" and r["session"] == "ses_in1" and not r["new_session"]
        assert sent and sent[-1][0] == "ses_in1" and "P001" in sent[-1][1]
        # 不在工作区的对话（或首页）：新开一个工厂对话
        pdf2 = pdf + b"\n%extra"
        r2 = _req(srv, "/lite/api/upload-paper?session=ses_other&name=p2.pdf", "k" * 32, raw=pdf2)
        assert r2["session"] == "ses_innew" and r2["new_session"]
        # 工厂栏跟着对话走：每个对话只看到自己的论文
        v1 = _req(srv, "/lite/api/view?session=ses_in1", "k" * 32)
        v2 = _req(srv, "/lite/api/view?session=ses_innew", "k" * 32)
        assert v1["paper"]["paper"]["id"] == "P001" and v2["paper"]["paper"]["id"] == "P002"
        assert v1["session_ok"] and v1["paper"]["paper"]["stage"] == "提取中"
        # 一个对话只做一篇：在已经做 P001 的对话里再传一篇 → 自动新开对话
        r3 = _req(srv, "/lite/api/upload-paper?session=ses_in1&name=p3.pdf", "k" * 32, raw=pdf + b"\n%third")
        assert r3["paper"] == "P003" and r3["session"] == "ses_in3" and r3["new_session"] and r3["because_busy"]
        # 一篇论文可以再开一个对话；人在哪个对话里点，工厂就往哪个对话发话
        r4 = _req(srv, "/lite/api/paper-session", "k" * 32, {"paper": "P001"})
        assert r4["session"] == "ses_in4" and sent[-1][0] == "ses_in4" and "P001" in sent[-1][1]
        from lite import store
        assert store.detail("P001")["paper"]["sessions"] == ["ses_in1", "ses_in4"]
        store.save_candidates("P001", [cand()])
        assert store.detail("P001")["paper"]["stage"] == "待挑选"
        r = _req(srv, "/lite/api/choose", "k" * 32, {"paper": "P001", "candidates": ["C0001"], "session": "ses_in1"})
        assert r["made"][0]["id"] == "V0001" and "选中" in sent[-1][1] and sent[-1][0] == "ses_in1"
        b = store.detail("P001")["paper"]
        assert b["stage"] == "已挑选" and b["counts"] == {"待列数据": 1} and b["session"] == "ses_in1"
        _req(srv, "/lite/api/ask", "k" * 32, {"what": "needs", "id": "V0001", "session": "ses_in2_not_this_paper"})
        assert sent[-1][0] == "ses_in1"                          # 不是这篇论文的对话：发到最近用的
        # 移到这个对话：当前对话已经在做别的论文 → 新开（这里用不到新编号，换成空对话）
        # 变量库：筛选 + AI 帮我找
        from lite import library
        library.import_cards()
        lib = _req(srv, "/lite/api/library?kind=%E6%97%A7%E5%BA%93&shape=%E5%85%AC%E5%8F%B8-%E5%B9%B4", "k" * 32)
        assert lib["items"] and all(x["kind"] == "旧库" and x["shape"] == "公司-年" for x in lib["items"])
        from lite import paths
        assert (lib["facets"]["paper"] or paths.PUBLIC) and lib["facets"]["shape"] and lib["search"] is None   # 公开版旧库没有出处论文
        r = _req(srv, "/lite/api/lib-search", "k" * 32, {"query": "衡量公司规模的"})
        assert r["session"] == "ses_inlib" and sent[-1][0] == "ses_inlib" and "公司规模" in sent[-1][1]
        assert _req(srv, "/lite/api/view?session=ses_inlib", "k" * 32)["is_assistant"]
        res = store.set_lib_results("", [{"id": "gv0001", "why": "就是规模"}, {"id": "gv9999", "why": "乱写"}])
        assert res["kept"] == 1 and res["wrong"] == ["gv9999"]
        s = _req(srv, "/lite/api/library", "k" * 32)["search"]
        assert s["done"] and s["results"][0]["id"] == "gv0001" and s["results"][0]["name"]
        with pytest.raises(urllib.error.HTTPError) as e:
            _req(srv, "/lite/api/admit", "k" * 32, {"indicator": "V0001"})
        assert e.value.code == 400
    finally:
        srv.shutdown()


def test_mcp_tools(lite):
    from mcp.client import Client as McpClient
    from lite import mcp_server, store
    store.add_paper(lite["pdf"], "paper.pdf", "ses_a")

    async def go():
        async with McpClient(mcp_server.build()) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert {"status", "read_paper", "find_in_paper", "search_library", "save_candidates", "set_data_needs", "data_preview", "build", "get"} <= names
            assert {"paper_outline", "show_search_results"} <= names
            assert not names & {"choose", "admit", "override", "defer", "reset"}         # 人定的事 AI 没有工具
            r = await c.call_tool("paper_outline", {"paper": "P001"})
            assert "第 2 页" in r.content[0].text and "★变量定义" in r.content[0].text and "建议精读：1、2" in r.content[0].text
            r = await c.call_tool("show_search_results", {"results": [{"id": "gv1"}]})
            assert r.is_error and "没有要回答的检索" in r.content[0].text
            r = await c.call_tool("read_paper", {"paper": "P001"})
            assert "第 2 页" in r.content[0].text and "calculated as" in r.content[0].text
            r = await c.call_tool("save_candidates", {"paper": "P001", "candidates": [cand(), cand(name="假", quote="nothing like this")]})
            assert "收下 1 个" in r.content[0].text and "没收 1 个" in r.content[0].text
            r = await c.call_tool("set_data_needs", {"indicator": "V0001", "needs": NEEDS, "column": "SA", "keys": ["股票代码", "年份"]})
            assert r.is_error                                                     # 还没被人选中
            store.choose("P001", ["C0001"])
            r = await c.call_tool("set_data_needs", {"indicator": "V0001", "needs": NEEDS, "column": "SA", "keys": ["股票代码", "年份"]})
            assert not r.is_error and "待交数据" in r.content[0].text
            r = await c.call_tool("build", {"indicator": "V0001", "code": CODE})
            assert r.is_error and "没交" in r.content[0].text
    anyio.run(go)


def test_acceptance_fixes(lite, tmp_path):
    """独立验收发现的问题：合成代码不能动库、已入库不能再合成、页码写错一页不收、#N/A 当空值、作废的数据文件不能放行。"""
    from lite import runner, store
    store.add_paper(lite["pdf"], "paper.pdf", "ses_a")
    r = store.save_candidates("P001", [cand(page=1, recommend=False, name="页码错一页")])
    assert not r["saved"] and "在第 2 页" in r["rejected"][0]["why"]
    store.save_candidates("P001", [cand()])
    store.choose("P001", ["C0001"])
    store.set_needs("V0001", NEEDS, "SA", ["股票代码", "年份"])
    bad = store.add_datafile("V0001", "bs", str(lite["data"] / "bad.csv"), "bad.csv")
    store.add_datafile("V0001", "bs", str(lite["data"] / "bs.csv"), "bs.csv")
    with pytest.raises(store.LiteError):
        store.override(bad["datafile"], "旧文件已经换掉了")          # 作废的文件不能再放行
    store.add_datafile("V0001", "info", str(lite["data"] / "info.csv"), "info.csv")
    target = tmp_path / "home_write.txt"
    evil = ("from lite import store\nstore.choose('P001', ['C0001'])\n" if False else "") + (
        "import os\n"
        "try:\n    open(%r, 'w').write('x')\nexcept Exception as e:\n    print('写不了', type(e).__name__)\n"
        "try:\n    from lite import store\n    store.papers()\nexcept Exception as e:\n    print('库动不了', type(e).__name__)\n" % str(target)) + CODE
    rid, res = runner.build("V0001", evil)
    assert res["ok"], res
    assert not target.exists() and "库动不了" in res["log"]
    store.admit("V0001")
    with pytest.raises(store.LiteError):
        runner.build("V0001", CODE)                                    # 已入库的不能再合成、不会被踢出库
    assert store.detail("V0001")["state"] == "已入库"
    from lite import datacheck
    v, ratio = datacheck.convert(pd.Series(["#N/A", "3", "#DIV/0!"]), "number")
    assert ratio == 1.0 and v.isna().sum() == 2 and str(v.dtype) == "float64"


def test_summary_not_forgeable_and_year_int(lite):
    """小结由工厂在沙箱外算（合成代码改不了）；年份导出是整数。"""
    from lite import export, runner, store
    store.add_paper(lite["pdf"], "paper.pdf", "ses_a")
    store.save_candidates("P001", [cand()])
    store.choose("P001", ["C0001"])
    store.set_needs("V0001", NEEDS, "SA", ["股票代码", "年份"])
    store.add_datafile("V0001", "bs", str(lite["data"] / "bs.csv"), "bs.csv")
    store.add_datafile("V0001", "info", str(lite["data"] / "info.csv"), "info.csv")
    forge = "import lite.summary as S\nS.summarize = lambda *a, **k: {'rows': 999999, 'alerts': []}\n" + CODE
    rid, res = runner.build("V0001", forge)
    assert res["ok"] and res["summary"]["rows"] == 9
    store.admit("V0001")
    out = export.export(["V0001"])
    csv = [f for f in os.listdir(os.path.join(out["folder"], "数据"))][0]
    text = open(os.path.join(out["folder"], "数据", csv), encoding="utf-8-sig").read()
    assert ",2018," in text and "2018.0" not in text


def test_auto_match_one_paper_per_session_and_reset(lite, monkeypatch):
    from lite import app, library, opencode, store
    library.import_cards()
    store.add_paper(lite["pdf"], "paper.pdf", "ses_a")
    r = store.save_candidates("P001", [cand(name="公司规模", name_en="Size", recommend=False,
                                            quote="Firm size is measured as the natural logarithm of total assets"),
                                       cand(name="总资产", name_en="Total assets", recommend=False,
                                            quote="Firm size is measured as the natural logarithm of total assets")])
    cs = {c["name"]: c["in_library"] for c in store.candidates("P001")}
    assert cs["公司规模"].startswith("gv") and cs["总资产"] == "" and r["matched"] == 1     # 英文短语不拆词乱配
    # 一个对话只做一篇论文
    other = lite["pdf"] + ".2.pdf"
    open(other, "wb").write(open(lite["pdf"], "rb").read() + b"\n%2")
    with pytest.raises(store.LiteError):
        store.add_paper(other, "p2.pdf", "ses_a")
    p2 = store.add_paper(other, "p2.pdf", "ses_b")
    with pytest.raises(store.LiteError):
        store.bind("P001", "ses_b")
    assert store.session_paper("ses_b") == p2["id"] and [p["id"] for p in store.papers_of_session("ses_a")] == ["P001"]
    # 恢复出厂：库清空，旧库定义重新带进来，工作区对话删光
    deleted = []
    monkeypatch.setattr(opencode, "any_busy", lambda: False)
    monkeypatch.setattr(opencode, "all_workspace_sessions", lambda: ["ses_a", "ses_b"])
    monkeypatch.setattr(opencode, "delete_session", lambda sid: deleted.append(sid) or True)
    monkeypatch.setattr(opencode, "new_session", lambda title="": "ses_fresh")
    n_old = store.overview()["oldlib"]
    out = app.reset()
    assert deleted == ["ses_a", "ses_b"] and out["session"] == "ses_fresh" and out["deleted_sessions"] == 2
    ov = store.overview()
    assert ov["papers"] == 0 and ov["indicators"] == {} and ov["oldlib"] == n_old == out["oldlib"]
    assert not os.listdir(os.path.join(os.environ["LITE_HOME"], "库", "papers"))
    monkeypatch.setattr(opencode, "any_busy", lambda: True)
    with pytest.raises(store.LiteError):
        app.reset()


def test_migrate_old_sessions(lite):
    """旧版一个对话挂了几篇论文：迁移后只留最早那篇，别的等人“移到这个对话”。"""
    import sqlite3
    from lite import paths, store
    paths.ensure()
    c = sqlite3.connect(paths.lib("lite.db"))
    c.executescript("CREATE TABLE papers (id TEXT PRIMARY KEY, title TEXT, file TEXT, path TEXT, md5 TEXT, pages INTEGER, scanned INTEGER DEFAULT 0,"
                    " session TEXT DEFAULT '', created TEXT, extracted TEXT DEFAULT '', summary TEXT DEFAULT '');"
                    "INSERT INTO papers(id, title, session) VALUES('P001', 'a', 'ses_x'), ('P002', 'b', 'ses_x'), ('P003', 'c', 'ses_y');")
    c.commit(); c.close()
    store._migrated.clear()
    assert store.session_paper("ses_x") == "P001" and store.session_paper("ses_y") == "P003"
    assert store.detail("P002")["paper"]["session"] == ""


def test_public_defs_have_no_quotes(tmp_path):
    """公开版的旧库定义：只有名称、定义、公式；不带出处原文、内部编号、数据商和课题组字样。"""
    from lite import library, paths
    if paths.PUBLIC:
        pytest.skip("公开版里没有登记卡，定义文件已经生成好了")
    out = tmp_path / "defs.json"
    n = library.export_public_defs(str(out))
    rows = json.load(open(out, encoding="utf-8"))
    assert n == len(rows) > 80
    assert all(set(r) == {"id", "name", "name_en", "shape", "unit", "definition", "formula"} for r in rows)
    text = out.read_text(encoding="utf-8")
    for bad in ("quote", "课题组", "Tushare", "CN-A-", "CN-B-", "V26_CEOAge", "口径变体（"):
        assert bad not in text, bad

