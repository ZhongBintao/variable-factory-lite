# -*- coding: utf-8 -*-
"""单人版的本机数据库：所有业务规则都在这里，工厂栏（server）和 AI 的工具（mcp_server）都只调这里。

对象和编号：
  论文 P001（在一个或几个 OpenCode 对话里做；一个对话只做一篇，见 sessions 表）
  候选指标 C0001（AI 从论文里提取的，全部列出）
  指标 V0001（人选中的候选指标；人选中就算认可了定义）
  数据文件 D0001（人上传的原始数据，带 MD5 和校验结果）
  合成记录 R0001（AI 写的合成代码、跑出来的结果和小结）
  旧库变量 gv0001（带进来的已有变量定义，只读，给 AI 判断“库里已有”做参照）

指标的状态：待列数据 → 待交数据 → 待合成 → 待入库 → 已入库；数据凑不齐可以“只存定义”= 等数据（也算进库，只有定义）。
只留追溯：每个指标记着论文、页码、原文摘录、用了哪份数据（MD5）、放行理由、合成代码；events 表记每一步是谁（你 / AI）做的。
"""
import hashlib
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager

from . import datacheck, paths, pdftext

ROLES = ("被解释变量", "解释变量", "控制变量", "调节变量", "中介变量", "工具变量", "其他")
SHAPES = ("公司-年", "公司-季度", "公司", "年", "省份-年", "城市-年", "行业-年", "其他")
STATES = ("待列数据", "待交数据", "待合成", "待入库", "已入库", "等数据")
IN_LIBRARY = ("已入库", "等数据")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS papers (
  id TEXT PRIMARY KEY, title TEXT, file TEXT, path TEXT, md5 TEXT, pages INTEGER, scanned INTEGER DEFAULT 0,
  session TEXT DEFAULT '', created TEXT, extracted TEXT DEFAULT '', summary TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY, paper TEXT, seq INTEGER, name TEXT, name_en TEXT, role TEXT, definition TEXT, formula TEXT,
  quote TEXT, page INTEGER, in_library TEXT DEFAULT '', common INTEGER DEFAULT 0, recommend INTEGER DEFAULT 0,
  reason TEXT DEFAULT '', state TEXT DEFAULT '待挑选', indicator TEXT DEFAULT '', created TEXT,
  formula_tex TEXT DEFAULT '', symbol_tex TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS indicators (
  id TEXT PRIMARY KEY, paper TEXT, cand TEXT, name TEXT, name_en TEXT, role TEXT, definition TEXT, formula TEXT,
  quote TEXT, page INTEGER, unit TEXT DEFAULT '', shape TEXT DEFAULT '', keys TEXT DEFAULT '[]', column TEXT DEFAULT '',
  needs TEXT DEFAULT '[]', needs_note TEXT DEFAULT '', state TEXT, run TEXT DEFAULT '', created TEXT, admitted TEXT DEFAULT '',
  formula_tex TEXT DEFAULT '', symbol_tex TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS datafiles (
  id TEXT PRIMARY KEY, indicator TEXT, need TEXT, file TEXT, path TEXT, md5 TEXT, size INTEGER, colmap TEXT DEFAULT '{}',
  result TEXT DEFAULT '{}', ok INTEGER DEFAULT 0, override TEXT DEFAULT '', uploaded TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, indicator TEXT, code TEXT, note TEXT DEFAULT '', ok INTEGER, error TEXT DEFAULT '',
  summary TEXT DEFAULT '{}', out TEXT DEFAULT '', inputs TEXT DEFAULT '[]', created TEXT);
CREATE TABLE IF NOT EXISTS events (
  n INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, obj TEXT, kind TEXT, text TEXT, who TEXT);
CREATE TABLE IF NOT EXISTS oldlib (
  id TEXT PRIMARY KEY, name TEXT, name_en TEXT, shape TEXT, unit TEXT, status TEXT, meanings TEXT, sources TEXT,
  data TEXT DEFAULT '', definition TEXT DEFAULT '', formula TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions (session TEXT PRIMARY KEY, paper TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS lib_searches (
  id TEXT PRIMARY KEY, query TEXT, session TEXT DEFAULT '', results TEXT DEFAULT '[]', note TEXT DEFAULT '',
  created TEXT, done TEXT DEFAULT '');
"""
# 后加的列：旧库文件自动补上
EXTRA_COLS = {"candidates": ("formula_tex", "symbol_tex"), "indicators": ("formula_tex", "symbol_tex"), "oldlib": ("definition", "formula")}
_migrated = set()


def _migrate(c):
    path = _db_path()
    if path in _migrated:
        return
    for table, cols in EXTRA_COLS.items():
        have = {r["name"] for r in c.execute("PRAGMA table_info(%s)" % table)}
        for col in cols:
            if col not in have:
                try:
                    c.execute("ALTER TABLE %s ADD COLUMN %s TEXT DEFAULT ''" % (table, col))
                except sqlite3.OperationalError:      # 另一个进程刚补上
                    pass
    # 一个对话只做一篇论文：旧版 papers.session 迁进 sessions 表；一个对话挂了几篇的，只留最早那篇，别的等人“移到新对话”
    if not c.execute("SELECT 1 FROM sessions LIMIT 1").fetchone() and c.execute("SELECT 1 FROM papers WHERE session != '' LIMIT 1").fetchone():
        c.execute("BEGIN IMMEDIATE")
        for p in c.execute("SELECT id, session FROM papers WHERE session != '' ORDER BY id").fetchall():
            if c.execute("SELECT 1 FROM sessions WHERE session = ?", (p["session"],)).fetchone():
                c.execute("UPDATE papers SET session = '' WHERE id = ?", (p["id"],))
            else:
                c.execute("INSERT OR IGNORE INTO sessions(session, paper, created) VALUES(?,?,?)", (p["session"], p["id"], now()))
        c.execute("COMMIT")
    _migrated.add(path)


class LiteError(Exception):
    """给人和 AI 看的错：发生了什么 + 怎么办。"""

    def __init__(self, message, what_to_do=""):
        super().__init__(message)
        self.message, self.what_to_do = message, what_to_do

    def text(self):
        return self.message + ("\n怎么办：" + self.what_to_do if self.what_to_do else "")

    def to_dict(self):
        return {"error": {"message": self.message, "what_to_do": self.what_to_do}}


def now():
    """北京时间。"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_path():
    return paths.lib("lite.db")


def connect():
    if os.environ.get("LITE_SANDBOX"):
        raise LiteError("合成代码里不能动工厂的库", "合成代码只用 inputs 算出 result")
    paths.ensure()
    c = sqlite3.connect(_db_path(), timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.executescript(SCHEMA)
    _migrate(c)
    return c


@contextmanager
def tx():
    """一次写操作：同一时间只有一个在写（几个对话同时做也不打架），写完版本号加一，工厂栏据此刷新。"""
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("INSERT INTO meta(k, v) VALUES('rev', '1') ON CONFLICT(k) DO UPDATE SET v = CAST(v AS INTEGER) + 1")
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()


@contextmanager
def ro():
    c = connect()
    try:
        yield c
    finally:
        c.close()


def rev():
    with ro() as c:
        r = c.execute("SELECT v FROM meta WHERE k='rev'").fetchone()
        return int(r["v"]) if r else 0


def _next(c, table, prefix, width):
    rows = c.execute("SELECT id FROM %s WHERE id LIKE ?" % table, (prefix + "%",)).fetchall()
    n = max([int(r["id"][len(prefix):]) for r in rows if r["id"][len(prefix):].isdigit()] or [0])
    return "%s%0*d" % (prefix, width, n + 1)


def log(c, obj, kind, text, who="你"):
    c.execute("INSERT INTO events(at, obj, kind, text, who) VALUES(?,?,?,?,?)", (now(), obj, kind, text, who))


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("keys", "needs", "colmap", "result", "summary", "inputs", "meanings", "sources"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k] or "null")
            except ValueError:
                pass
    return d


def _one(c, sql, *a):
    return _row(c.execute(sql, a).fetchone())


def _all(c, sql, *a):
    return [_row(r) for r in c.execute(sql, a).fetchall()]


def _must(c, table, oid, what):
    r = _one(c, "SELECT * FROM %s WHERE id = ?" % table, oid)
    if r is None:
        raise LiteError("没有这个%s：%s" % (what, oid), "先用 status 看看现有的编号")
    return r


# ───────────────────────── 论文 ─────────────────────────
def add_paper(src, filename, session=""):
    """登记一篇论文（src：本机文件路径）。同一份 PDF 已经登记过就返回那一篇（dup=True），不重复登记。"""
    if not os.path.isfile(src):
        raise LiteError("找不到文件：%s" % src)
    if not filename.lower().endswith(".pdf"):
        raise LiteError("只能上传 PDF 文件（%s 不是 PDF）" % filename, "把论文存成 PDF 再上传")
    with open(src, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise LiteError("这个文件打不开成 PDF：%s" % filename, "确认它是论文的 PDF（不是网页或压缩包）")
    md5 = md5_file(src)
    with tx() as c:
        old = _one(c, "SELECT * FROM papers WHERE md5 = ?", md5)
        if old:
            return dict(old, dup=True)
        pid = _next(c, "papers", "P", 3)
        dst = paths.lib("papers", pid + ".pdf")
        shutil.copyfile(src, dst)
        try:
            inf = pdftext.info(dst)
        except Exception as e:      # noqa
            os.remove(dst)
            raise LiteError("PDF 读不出来：%s" % e, "换一份 PDF 试试")
        title = inf["title"] or os.path.splitext(os.path.basename(filename))[0]
        if session and _session_paper(c, session):
            os.remove(dst)
            raise LiteError("这个对话已经在做论文 %s 了：一个对话只做一篇论文" % _session_paper(c, session), "新开一个对话再上传")
        c.execute("INSERT INTO papers(id, title, file, path, md5, pages, scanned, session, created) VALUES(?,?,?,?,?,?,?,?,?)",
                  (pid, title, os.path.basename(filename), dst, md5, inf["pages"], int(inf["scanned"]), session or "", now()))
        if session:
            c.execute("INSERT OR REPLACE INTO sessions(session, paper, created) VALUES(?,?,?)", (session, pid, now()))
        log(c, pid, "上传论文", "%s（%d 页，MD5 %s）" % (os.path.basename(filename), inf["pages"], md5))
        return dict(_one(c, "SELECT * FROM papers WHERE id = ?", pid), dup=False)


def find_paper(md5):
    with ro() as c:
        return _one(c, "SELECT * FROM papers WHERE md5 = ?", md5)


def _session_paper(c, session):
    r = c.execute("SELECT paper FROM sessions WHERE session = ?", (session,)).fetchone()
    return r["paper"] if r else ""


def session_paper(session):
    """这个对话在做哪篇论文（一个对话只做一篇）；没有就是空。"""
    if not session:
        return ""
    with ro() as c:
        return _session_paper(c, session)


def bind(paper, session):
    """把论文挂到某个 OpenCode 对话（一篇论文可以有几个对话；一个对话只做一篇）。这个对话就成了这篇论文“最近用的对话”。"""
    with tx() as c:
        _must(c, "papers", paper, "论文")
        other = _session_paper(c, session)
        if other and other != paper:
            raise LiteError("这个对话已经在做论文 %s 了：一个对话只做一篇论文" % other, "新开一个对话")
        c.execute("INSERT OR REPLACE INTO sessions(session, paper, created) VALUES(?,?,?)", (session, paper, now()))
        c.execute("UPDATE papers SET session = ? WHERE id = ?", (session, paper))
        if not other:
            log(c, paper, "开对话", "在对话 %s 里做" % session)


def touch(paper, session):
    """人在这个对话里点了按钮：它成为这篇论文最近用的对话（工厂往对话里发话发到这里）。"""
    with ro() as c:
        if _session_paper(c, session) != paper:
            return False
        p = _one(c, "SELECT session FROM papers WHERE id = ?", paper)
        if p and p["session"] == session:
            return True
    with tx() as c:
        c.execute("UPDATE papers SET session = ? WHERE id = ?", (session, paper))
    return True


def set_title(c, paper, title):
    title = (title or "").strip()
    if title:
        c.execute("UPDATE papers SET title = ? WHERE id = ?", (title[:300], paper))


def papers():
    with ro() as c:
        return [_paper_brief(c, p) for p in _all(c, "SELECT * FROM papers ORDER BY id DESC")]


def papers_of_session(session):
    with ro() as c:
        return [_paper_brief(c, p) for p in _all(c, "SELECT p.* FROM papers p JOIN sessions s ON s.paper = p.id WHERE s.session = ?", session)]


STAGE_ORDER = ["待列数据", "待交数据", "待合成", "待入库", "已入库", "等数据"]


def _paper_brief(c, p):
    cands = _all(c, "SELECT state FROM candidates WHERE paper = ?", p["id"])
    inds = _all(c, "SELECT state FROM indicators WHERE paper = ?", p["id"])
    counts = {s: 0 for s in STAGE_ORDER}
    for i in inds:
        counts[i["state"]] = counts.get(i["state"], 0) + 1
    # 论文这一级只有三步：上传 → AI 提取指标 → 挑指标；挑完以后每个指标各走各的（counts）
    if not cands:
        stage, step, label = "提取中", 2, "等 AI 提取指标"
    elif not inds:
        stage, step, label = "待挑选", 3, "等你挑指标"
    else:
        stage = "已挑选"
        step = 4
        if all(i["state"] in IN_LIBRARY for i in inds):
            label = "指标都做完了"
        else:
            mine = counts["待交数据"] + counts["待入库"]
            label = "%d 个指标等你处理" % mine if mine else "等 AI 干活"
    sess = [r["session"] for r in c.execute("SELECT session FROM sessions WHERE paper = ? ORDER BY created", (p["id"],))]
    return {"id": p["id"], "title": p["title"], "file": p["file"], "pages": p["pages"], "session": p["session"], "sessions": sess,
            "created": p["created"], "n_candidates": len(cands), "n_indicators": len(inds),
            "n_done": sum(1 for i in inds if i["state"] in IN_LIBRARY), "stage": stage, "step": step, "label": label,
            "counts": {k: v for k, v in counts.items() if v}, "scanned": bool(p["scanned"])}


def paper_path(paper):
    with ro() as c:
        return _must(c, "papers", paper, "论文")["path"]


# ───────────────────────── 候选指标 ─────────────────────────
def _txt(v, n=4000):
    return str(v if v is not None else "").strip()[:n]


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKC", str(t or "")).lower()
    return "".join(ch for ch in t if ch.isalnum() or ch == "&")


def _names(*texts):
    """一个变量的各种叫法（中文名、英文名、“/”分开的别名、括号里的缩写），规整成小写无空格。"""
    import re
    out = set()
    for t in texts:
        for part in re.split(r"[/／;；、,，]|\s{2,}", str(t or "")):
            words = part.split() if re.search(r"[\u4e00-\u9fff]", part) else []      # “总资产收益率 ROA”拆开；英文短语不拆（免得 assets 乱配）
            for x in [part] + re.findall(r"[(（]([^()（）]+)[)）]", part) + [re.sub(r"[(（][^()（）]*[)）]", "", part)] + words:
                n = _norm(x)
                if len(n) >= 2:
                    out.add(n)
    return out


def _lib_index(c, paper):
    """自动对库用：[(编号, 叫法集合)]，旧库 + 别的论文里已经进库的指标。"""
    idx = []
    for o in _all(c, "SELECT id, name, name_en, meanings FROM oldlib"):
        idx.append((o["id"], _names(o["name"], o["name_en"], *[m.get("label") for m in o["meanings"] or []])))
    for i in _all(c, "SELECT id, name, name_en FROM indicators WHERE paper != ? AND state IN ('已入库', '等数据')", paper):
        idx.append((i["id"], _names(i["name"], i["name_en"])))
    return idx


def _auto_match(idx, name, name_en):
    mine = _names(name, name_en)
    for oid, names in idx:
        if mine & names:
            return oid
    return ""


def save_candidates(paper, items, title="", summary="", replace=False):
    """AI 交候选指标（全部列出）。分轻重：推荐的（recommend）要写理由和公式；其他的一句话定义 + 原文摘录 + 页码就收。
    每条都核对原文摘录在不在那一页；对不上的不收，告诉 AI 怎么改。“变量库已有”由工厂按名字自动对（AI 写了有效编号就用 AI 的）。
    同名的（还没被选中的）候选直接更新。replace=True：先清掉这篇论文还没被选中的候选再收。
    返回 {saved: [...], rejected: [{name, why}], matched: n}。"""
    if not isinstance(items, list) or not items:
        raise LiteError("candidates 要是一个非空的列表", "把论文里的全部指标一条一条放进列表")
    with ro() as c:
        p = _must(c, "papers", paper, "论文")
        known = {r["id"] for r in _all(c, "SELECT id FROM oldlib")} | {r["id"] for r in _all(c, "SELECT id FROM indicators")}
        idx = _lib_index(c, paper)
    ok, bad, matched = [], [], 0
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            bad.append({"name": "第 %d 条" % (i + 1), "why": "每条要是一个对象（含 name、definition、quote、page 等）"})
            continue
        name = _txt(it.get("name"), 120)
        why = []
        if not name:
            why.append("缺 name（指标名称）")
        if not _txt(it.get("definition")):
            why.append("缺 definition（一句大白话：怎么算、衡量什么）")
        role = _txt(it.get("role"), 20) or "其他"
        if role not in ROLES:
            why.append("role 只能是：%s" % "、".join(ROLES))
        try:
            page = int(it.get("page"))
        except (TypeError, ValueError):
            page = 0
            why.append("缺 page（定义所在的 PDF 页码，数字）")
        quote = _txt(it.get("quote"), 2000)
        if not quote:
            why.append("缺 quote（原文摘录：从论文里逐字照抄定义那一两句）")
        elif page:
            good, msg = pdftext.quote_on_page(p["path"], page, quote)
            if not good:
                why.append(msg)
        rec = bool(it.get("recommend"))
        reason = _txt(it.get("reason"), 400)
        formula, ftex = _txt(it.get("formula"), 1000), _txt(it.get("formula_tex"), 1000)
        if rec and not reason:
            why.append("推荐的（recommend=true）要写一句 reason：它新在哪、为什么值得做")
        if rec and not (formula or ftex):
            why.append("推荐的要写 formula（最好再给 formula_tex）")
        if why:
            bad.append({"name": name or "第 %d 条" % (i + 1), "why": "；".join(why)})
            continue
        lib = _txt(it.get("in_library"), 40)
        if lib not in known:
            lib = _auto_match(idx, name, it.get("name_en"))
        matched += bool(lib)
        ok.append({"name": name, "name_en": _txt(it.get("name_en"), 120), "role": role, "definition": _txt(it.get("definition")),
                   "formula": formula, "formula_tex": ftex, "symbol_tex": _txt(it.get("symbol_tex"), 200), "quote": quote, "page": page,
                   "in_library": lib, "common": int(bool(it.get("common"))), "recommend": int(rec), "reason": reason if rec else ""})
    saved = []
    cols = ("name_en", "role", "definition", "formula", "formula_tex", "symbol_tex", "quote", "page", "in_library", "common", "recommend", "reason")
    with tx() as c:
        set_title(c, paper, title)
        if summary:
            c.execute("UPDATE papers SET summary = ? WHERE id = ?", (_txt(summary, 2000), paper))
        if replace:
            c.execute("DELETE FROM candidates WHERE paper = ? AND state = '待挑选'", (paper,))
        for it in ok:
            old = _one(c, "SELECT * FROM candidates WHERE paper = ? AND name = ?", paper, it["name"])
            if old and old["state"] != "待挑选":
                bad.append({"name": it["name"], "why": "这个候选已经被选中成指标 %s，不能再改" % old["indicator"]})
                continue
            if old:
                c.execute("UPDATE candidates SET %s WHERE id = ?" % ", ".join("%s=?" % k for k in cols), tuple(it[k] for k in cols) + (old["id"],))
                saved.append(old["id"])
                continue
            cid = _next(c, "candidates", "C", 4)
            seq = (c.execute("SELECT MAX(seq) m FROM candidates WHERE paper = ?", (paper,)).fetchone()["m"] or 0) + 1
            c.execute("INSERT INTO candidates(id, paper, seq, name, %s, created) VALUES(?,?,?,?,%s,?)" % (", ".join(cols), ",".join("?" * len(cols))),
                      (cid, paper, seq, it["name"]) + tuple(it[k] for k in cols) + (now(),))
            saved.append(cid)
        if saved:
            c.execute("UPDATE papers SET extracted = ? WHERE id = ?", (now(), paper))
            log(c, paper, "提取指标", "AI 交了 %d 个候选指标%s" % (len(saved), "（另有 %d 个没收，要改）" % len(bad) if bad else ""), "AI")
    return {"saved": saved, "rejected": bad, "matched": matched}


def candidates(paper):
    with ro() as c:
        return _all(c, "SELECT * FROM candidates WHERE paper = ? ORDER BY seq", paper)


def choose(paper, cand_ids):
    """人在工厂栏里选中候选指标：每个变成一个指标（选中就算认可了定义）。返回新指标列表。"""
    if not cand_ids:
        raise LiteError("一个都没选", "先勾选要做的候选指标")
    made = []
    with tx() as c:
        _must(c, "papers", paper, "论文")
        for cid in cand_ids:
            cd = _one(c, "SELECT * FROM candidates WHERE id = ? AND paper = ?", cid, paper)
            if cd is None:
                raise LiteError("候选指标 %s 不在论文 %s 里" % (cid, paper))
            if cd["state"] != "待挑选":
                continue
            vid = _next(c, "indicators", "V", 4)
            c.execute("INSERT INTO indicators(id, paper, cand, name, name_en, role, definition, formula, formula_tex, symbol_tex, quote, page, "
                      "state, created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (vid, paper, cid, cd["name"], cd["name_en"], cd["role"], cd["definition"], cd["formula"], cd["formula_tex"] or "",
                       cd["symbol_tex"] or "", cd["quote"], cd["page"], "待列数据", now()))
            c.execute("UPDATE candidates SET state = '选中', indicator = ? WHERE id = ?", (vid, cid))
            log(c, vid, "选中", "选中候选指标 %s「%s」，认可论文第 %s 页的定义" % (cid, cd["name"], cd["page"]))
            made.append({"id": vid, "name": cd["name"], "cand": cid})
    return made


def drop(indicator):
    """人不做这个指标了（还没入库的才行）：删掉指标，候选退回“待挑选”。"""
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] == "已入库":
            raise LiteError("%s 已经入库，不能取消" % indicator)
        c.execute("DELETE FROM indicators WHERE id = ?", (indicator,))
        c.execute("UPDATE datafiles SET active = 0 WHERE indicator = ?", (indicator,))
        c.execute("UPDATE candidates SET state = '待挑选', indicator = '' WHERE id = ?", (ind["cand"],))
        log(c, indicator, "取消", "不做「%s」了，候选 %s 退回待挑选" % (ind["name"], ind["cand"]))


# ───────────────────────── 所需数据 ─────────────────────────
def _check_needs(needs):
    if not isinstance(needs, list) or not needs:
        raise LiteError("needs 要是非空列表：合成这个指标要哪几份原始数据，一份一条")
    keys = set()
    for i, n in enumerate(needs):
        if not isinstance(n, dict):
            raise LiteError("needs 第 %d 条要是一个对象" % (i + 1))
        k = _txt(n.get("key"), 40)
        if not k or not all(ch.isalnum() or ch == "_" for ch in k):
            raise LiteError("needs 第 %d 条缺 key（英文短名，如 assets），只用字母数字下划线" % (i + 1))
        if k in keys:
            raise LiteError("needs 里 key 重复：%s" % k)
        keys.add(k)
        if not _txt(n.get("name")) or not _txt(n.get("what")):
            raise LiteError("needs「%s」要有 name（数据叫什么）和 what（具体要什么：哪些公司、哪些年、什么口径）" % k)
        cols = n.get("columns")
        if not isinstance(cols, list) or not cols:
            raise LiteError("needs「%s」要列出 columns（文件里要有哪些列）" % k)
        names = set()
        for col in cols:
            if not isinstance(col, dict) or not _txt(col.get("name")):
                raise LiteError("needs「%s」的每一列要有 name" % k)
            if (col.get("type") or "text") not in datacheck.TYPES:
                raise LiteError("needs「%s」列「%s」的 type 只能是：%s" % (k, col["name"], "、".join(datacheck.TYPES)))
            if col.get("aliases") is not None and not isinstance(col.get("aliases"), list):
                raise LiteError("needs「%s」列「%s」的 aliases 要是列表" % (k, col["name"]))
            names.add(col["name"])
        for u in n.get("unique") or []:
            if u not in names:
                raise LiteError("needs「%s」的 unique 里的「%s」不在 columns 里" % (k, u))
        if n.get("years") and not datacheck.year_range(n.get("years")):
            raise LiteError("needs「%s」的 years 写成 2008-2020 这样" % k)


def set_needs(indicator, needs, column, keys, unit="", shape="", note=""):
    """AI 列出合成这个指标要哪些原始数据（不建议去哪找，只说要什么）。已交的文件按新要求重新校验。"""
    _check_needs(needs)
    column = _txt(column, 60)
    if not column or not column.replace("_", "").isalnum() or column[0].isdigit():
        raise LiteError("column 要写结果里这个指标的英文列名（如 SA、Lev），只用字母数字下划线，不以数字开头")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k.strip() for k in keys):
        raise LiteError("keys 要写结果表的主键列（如 [\"股票代码\", \"年份\"]）")
    shape = _txt(shape, 20)
    if shape and shape not in SHAPES:
        raise LiteError("shape 只能是：%s" % "、".join(SHAPES))
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] == "已入库":
            raise LiteError("%s 已经入库，不能改所需数据" % indicator)
        c.execute("UPDATE indicators SET needs = ?, column = ?, keys = ?, unit = ?, shape = ?, needs_note = ? WHERE id = ?",
                  (json.dumps(needs, ensure_ascii=False), column, json.dumps(keys, ensure_ascii=False), _txt(unit, 40), shape,
                   _txt(note, 1000), indicator))
        live = {n["key"] for n in needs}
        c.execute("UPDATE datafiles SET active = 0 WHERE indicator = ? AND need NOT IN (%s)" % ",".join("?" * len(live)),
                  (indicator, *live))
        for df in _all(c, "SELECT * FROM datafiles WHERE indicator = ? AND active = 1", indicator):
            _recheck(c, df, next(n for n in needs if n["key"] == df["need"]))
        log(c, indicator, "列所需数据", "AI 列了 %d 份所需数据：%s" % (len(needs), "、".join(n["name"] for n in needs)), "AI")
        if ind["state"] in ("待列数据", "待交数据", "待合成", "待入库"):
            _refresh(c, indicator)
    return detail(indicator)


def _recheck(c, df, need):
    res = datacheck.check(df["path"], need, df["colmap"] if isinstance(df["colmap"], dict) else {})
    c.execute("UPDATE datafiles SET result = ?, ok = ? WHERE id = ?", (json.dumps(res, ensure_ascii=False, default=str), int(res["ok"]), df["id"]))
    return res


def need_status(c, ind):
    """每份所需数据现在的样子：未交 / 通过 / 没通过 / 放行。"""
    out = []
    files = {d["need"]: d for d in _all(c, "SELECT * FROM datafiles WHERE indicator = ? AND active = 1", ind["id"])}
    for n in ind["needs"] or []:
        d = files.get(n["key"])
        st = "未交" if not d else "通过" if d["ok"] else "放行" if d["override"] else "没通过"
        out.append({"need": n, "status": st, "file": _file_brief(d) if d else None})
    return out


def _file_brief(d):
    r = d["result"] if isinstance(d["result"], dict) else {}
    return {"id": d["id"], "file": d["file"], "md5": d["md5"], "size": d["size"], "uploaded": d["uploaded"], "ok": bool(d["ok"]),
            "override": d["override"], "problems": r.get("problems", []), "warnings": r.get("warnings", []),
            "info": r.get("info", {}), "mapping": r.get("mapping", {}), "colmap": d["colmap"]}


def _refresh(c, indicator):
    """交数据后自动推进：所需数据都通过（或放行）了 → 待合成；数据变了而小结是旧的 → 回到待合成。"""
    ind = _one(c, "SELECT * FROM indicators WHERE id = ?", indicator)
    if ind["state"] in IN_LIBRARY:
        return ind["state"]
    if not ind["needs"]:
        new = "待列数据"
    else:
        sts = [s["status"] for s in need_status(c, ind)]
        if all(s in ("通过", "放行") for s in sts):
            new = ind["state"] if ind["state"] == "待入库" and _run_fresh(c, ind) else "待合成"
        else:
            new = "待交数据"
    if new != ind["state"]:
        c.execute("UPDATE indicators SET state = ? WHERE id = ?", (new, indicator))
        if new == "待合成" and ind["state"] == "待入库":
            log(c, indicator, "数据变了", "数据换过了，之前的合成结果作废，要重新合成", "工厂")
    return new


def _run_fresh(c, ind):
    """当前的合成结果用的还是现在这几份数据吗。"""
    if not ind["run"]:
        return False
    r = _one(c, "SELECT inputs FROM runs WHERE id = ?", ind["run"])
    used = sorted(x["md5"] for x in (r["inputs"] or []))
    now_md5 = sorted(d["md5"] for d in _all(c, "SELECT md5 FROM datafiles WHERE indicator = ? AND active = 1", ind["id"]))
    return used == now_md5


def add_datafile(indicator, need_key, src, filename):
    """人上传一份原始数据：存下、算 MD5、马上校验。同一份所需数据再传，旧的作废（留在记录里）。"""
    if not os.path.isfile(src):
        raise LiteError("找不到文件：%s" % src)
    md5 = md5_file(src)
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] == "已入库":
            raise LiteError("%s 已经入库，不能再交数据" % indicator)
        need = next((n for n in ind["needs"] or [] if n["key"] == need_key), None)
        if need is None:
            raise LiteError("%s 没有叫 %s 的所需数据" % (indicator, need_key), "先让 AI 列出所需数据")
        did = _next(c, "datafiles", "D", 4)
        safe = "".join(ch if ch.isalnum() or ch in "._-（）()" else "_" for ch in os.path.basename(filename))[-120:]
        dst = paths.lib("data", "%s_%s" % (did, safe))
        shutil.copyfile(src, dst)
        c.execute("UPDATE datafiles SET active = 0 WHERE indicator = ? AND need = ?", (indicator, need_key))
        c.execute("INSERT INTO datafiles(id, indicator, need, file, path, md5, size, uploaded) VALUES(?,?,?,?,?,?,?,?)",
                  (did, indicator, need_key, os.path.basename(filename), dst, md5, os.path.getsize(dst), now()))
        df = _one(c, "SELECT * FROM datafiles WHERE id = ?", did)
        res = _recheck(c, df, need)
        if ind["state"] == "等数据":
            c.execute("UPDATE indicators SET state = '待交数据' WHERE id = ?", (indicator,))
        log(c, indicator, "上传数据", "「%s」交了 %s（MD5 %s，%s 行）：%s" % (
            need["name"], os.path.basename(filename), md5, res["info"].get("rows", "?"),
            "校验通过" if res["ok"] else "没通过：" + "；".join(res["problems"])))
        state = _refresh(c, indicator)
    return {"datafile": did, "ok": res["ok"], "problems": res["problems"], "warnings": res["warnings"], "state": state}


def _file_editable(df, ind):
    if not df["active"]:
        raise LiteError("这份数据已经被新上传的文件换掉了", "在新文件上操作")
    if ind is None or ind["state"] in IN_LIBRARY:
        raise LiteError("这个指标已经%s，不能再改它的数据" % ("入库" if ind and ind["state"] == "已入库" else "不在了" if ind is None else "只存了定义"),
                        "先点“继续交数据”" if ind and ind["state"] == "等数据" else "")


def set_colmap(datafile, colmap):
    """人把缺的列对应到文件里的某一列，重新校验。"""
    if not isinstance(colmap, dict):
        raise LiteError("对应关系要是 {所需列: 文件里的列}")
    with tx() as c:
        df = _must(c, "datafiles", datafile, "数据文件")
        ind = _one(c, "SELECT * FROM indicators WHERE id = ?", df["indicator"])
        _file_editable(df, ind)
        need = next(n for n in ind["needs"] if n["key"] == df["need"])
        cm = dict(df["colmap"] or {})
        cm.update({k: v for k, v in colmap.items() if v})
        for k in [k for k, v in colmap.items() if not v]:
            cm.pop(k, None)
        c.execute("UPDATE datafiles SET colmap = ? WHERE id = ?", (json.dumps(cm, ensure_ascii=False), datafile))
        df["colmap"] = cm
        res = _recheck(c, df, need)
        log(c, ind["id"], "对应列", "「%s」把 %s 对应好，重新校验：%s" % (
            need["name"], "、".join("%s→%s" % kv for kv in cm.items()), "通过" if res["ok"] else "仍没通过"))
        state = _refresh(c, ind["id"])
    return {"ok": res["ok"], "problems": res["problems"], "state": state}


def override(datafile, reason):
    """校验没通过，人写一句理由强行放行；理由跟着这个指标记下来。"""
    reason = _txt(reason, 500)
    if len(reason) < 2:
        raise LiteError("放行要写一句理由", "比如：这份是券商给的口径，列名不同但内容对")
    with tx() as c:
        df = _must(c, "datafiles", datafile, "数据文件")
        _file_editable(df, _one(c, "SELECT * FROM indicators WHERE id = ?", df["indicator"]))
        if df["ok"]:
            raise LiteError("这份数据已经通过校验，不用放行")
        c.execute("UPDATE datafiles SET override = ? WHERE id = ?", (reason, datafile))
        log(c, df["indicator"], "放行", "数据 %s（%s）没通过校验，你写理由放行：%s" % (datafile, df["file"], reason))
        state = _refresh(c, df["indicator"])
    return {"state": state}


def defer(indicator):
    """数据暂时凑不齐：先存定义，标“等数据”（只有定义入库）。"""
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] in IN_LIBRARY:
            raise LiteError("%s 已经是“%s”" % (indicator, ind["state"]))
        c.execute("UPDATE indicators SET state = '等数据', admitted = ? WHERE id = ?", (now(), indicator))
        log(c, indicator, "只存定义", "数据暂时凑不齐，只把定义存进库（等数据）")


def resume(indicator):
    """“等数据”的指标接着补数据。"""
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] != "等数据":
            raise LiteError("%s 不是“等数据”" % indicator)
        c.execute("UPDATE indicators SET state = '待交数据', admitted = '' WHERE id = ?", (indicator,))
        log(c, indicator, "继续交数据", "从“只存定义”回到交数据")
        _refresh(c, indicator)


def build_inputs(indicator):
    """合成要用的数据：[{key, name, path, md5, file, colmap, need}]。不齐就报错。"""
    with ro() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] in IN_LIBRARY:
            raise LiteError("%s 已经是“%s”，不能再合成" % (indicator, ind["state"]),
                            "已入库的不再改；要换口径就请用户在论文里另选一个候选做新指标" if ind["state"] == "已入库"
                            else "请用户先在工厂栏点“继续交数据”")
        if not ind["needs"]:
            raise LiteError("%s 还没列所需数据" % indicator, "先用 set_data_needs 列出所需数据")
        out = []
        for s in need_status(c, ind):
            if s["status"] not in ("通过", "放行"):
                raise LiteError("「%s」还%s，不能合成" % (s["need"]["name"], "没交" if s["status"] == "未交" else "没通过校验"),
                                "请用户在工厂栏上传或放行，交齐了再合成")
            d = _one(c, "SELECT * FROM datafiles WHERE id = ?", s["file"]["id"])
            out.append({"key": s["need"]["key"], "name": s["need"]["name"], "path": d["path"], "md5": d["md5"], "file": d["file"],
                        "colmap": d["colmap"] or {}, "need": s["need"], "datafile": d["id"]})
        return ind, out


def record_run(indicator, code, note, res, inputs):
    """记一次合成：代码、结果、小结都存下。成功了指标变“待入库”。"""
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] in IN_LIBRARY:
            raise LiteError("%s 已经是“%s”，不能再记合成结果" % (indicator, ind["state"]))
        rid = _next(c, "runs", "R", 4)
        d = paths.lib("builds", rid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "code.py"), "w", encoding="utf-8") as f:
            f.write(code)
        out = ""
        if res.get("ok") and res.get("tmp_out"):
            out = os.path.join(d, "result.parquet")
            shutil.move(res["tmp_out"], out)
        c.execute("INSERT INTO runs(id, indicator, code, note, ok, error, summary, out, inputs, created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (rid, indicator, code, _txt(note, 3000), int(bool(res.get("ok"))), _txt(res.get("error"), 6000),
                   json.dumps(res.get("summary") or {}, ensure_ascii=False, default=str), out,
                   json.dumps([{"key": i["key"], "name": i["name"], "file": i["file"], "md5": i["md5"], "datafile": i["datafile"]} for i in inputs],
                              ensure_ascii=False), now()))
        if res.get("ok"):
            c.execute("UPDATE indicators SET run = ?, state = '待入库' WHERE id = ?", (rid, indicator))
            sm = res.get("summary") or {}
            log(c, indicator, "合成", "AI 合成了一版（%s）：%s 行" % (rid, sm.get("rows", "?")), "AI")
        else:
            log(c, indicator, "合成失败", "AI 的合成代码没跑通（%s）" % rid, "AI")
        return rid


def admit(indicator):
    """人看过小结，点“入库”。结果存进库里的变量文件夹。"""
    with tx() as c:
        ind = _must(c, "indicators", indicator, "指标")
        if ind["state"] != "待入库":
            raise LiteError("%s 现在是“%s”，不能入库" % (indicator, ind["state"]),
                            "要先交齐数据、让 AI 合成出结果，看过小结再入库")
        if not _run_fresh(c, ind):
            raise LiteError("数据换过了，合成结果是旧的", "让 AI 重新合成")
        r = _one(c, "SELECT * FROM runs WHERE id = ?", ind["run"])
        dst = paths.lib("variables", indicator + ".parquet")
        shutil.copyfile(r["out"], dst)
        c.execute("UPDATE indicators SET state = '已入库', admitted = ? WHERE id = ?", (now(), indicator))
        log(c, indicator, "入库", "看过小结后入库（合成记录 %s，%s 行）" % (r["id"], (r["summary"] or {}).get("rows", "?")))


# ───────────────────────── 看 ─────────────────────────
def detail(oid):
    oid = (oid or "").strip()
    with ro() as c:
        if oid.startswith("P"):
            p = _must(c, "papers", oid, "论文")
            return {"type": "paper", "paper": dict(_paper_brief(c, p), summary=p["summary"], md5=p["md5"]),
                    "candidates": _all(c, "SELECT * FROM candidates WHERE paper = ? ORDER BY seq", oid),
                    "indicators": [_ind_view(c, i) for i in _all(c, "SELECT * FROM indicators WHERE paper = ? ORDER BY id", oid)],
                    "events": _all(c, "SELECT * FROM events WHERE obj = ? ORDER BY n", oid)}
        if oid.startswith("V"):
            return dict(_ind_view(c, _must(c, "indicators", oid, "指标"), full=True), type="indicator")
        if oid.startswith("C"):
            return dict(_must(c, "candidates", oid, "候选指标"), type="candidate")
        if oid.startswith("gv"):
            return dict(_must(c, "oldlib", oid, "旧库变量"), type="oldlib")
        if oid.startswith("R"):
            return dict(_must(c, "runs", oid, "合成记录"), type="run")
        if oid.startswith("D"):
            d = _must(c, "datafiles", oid, "数据文件")
            return dict(_file_brief(d), type="datafile", indicator=d["indicator"], need=d["need"])
    raise LiteError("看不懂这个编号：%s" % oid, "编号像 P001（论文）、C0001（候选）、V0001（指标）、gv0001（旧库变量）")


def _ind_view(c, ind, full=False):
    v = dict(ind)
    p = _one(c, "SELECT id, title, file FROM papers WHERE id = ?", ind["paper"])
    v["paper_title"] = p["title"] if p else ""
    v["data"] = need_status(c, ind)
    v["run_info"] = None
    if ind["run"]:
        r = _one(c, "SELECT * FROM runs WHERE id = ?", ind["run"])
        v["run_info"] = {"id": r["id"], "ok": bool(r["ok"]), "note": r["note"], "summary": r["summary"], "created": r["created"],
                         "inputs": r["inputs"], "fresh": _run_fresh(c, ind), "code": r["code"] if full else None}
    last = _one(c, "SELECT * FROM runs WHERE indicator = ? ORDER BY id DESC LIMIT 1", ind["id"])
    v["last_run_failed"] = bool(last and not last["ok"] and last["id"] != ind["run"])
    if v["last_run_failed"] and full:
        v["last_error"] = last["error"]
    v["next"] = NEXT.get(ind["state"], "")
    if full:
        v["events"] = _all(c, "SELECT * FROM events WHERE obj = ? ORDER BY n", ind["id"])
        v["overrides"] = [{"file": d["file"], "md5": d["md5"], "reason": d["override"]}
                          for d in _all(c, "SELECT * FROM datafiles WHERE indicator = ? AND active = 1 AND override != ''", ind["id"])]
    return v


NEXT = {
    "待列数据": "AI：用 set_data_needs 列出合成它要哪些原始数据",
    "待交数据": "你：在工厂栏上传数据（校验没过可以对应列、写理由放行，或只存定义）",
    "待合成": "AI：用 data_preview 看数据，再用 build 写合成代码",
    "待入库": "你：在工厂栏看小结，满意就点“入库”；不满意在对话里让 AI 重做",
    "已入库": "已入库",
    "等数据": "只存了定义；数据齐了可以在工厂栏点“继续交数据”",
}


def session_view(session):
    """工厂栏要的：这个对话在做的论文（新的在前）。"""
    ps = papers_of_session(session) if session else []
    return {"session": session, "papers": ps}


def library(q="", kind="", paper="", role="", shape="", data=""):
    """总库：本工具做的（已入库 + 等数据）+ 旧库带进来的定义。
    筛选：kind 来源（本工具 / 旧库）、paper 来源论文、role 角色、shape 数据形状、data（有 / 无）数据；q 搜索词。
    返回 {items, facets}：facets 是各筛选项的可选值和个数（按当前别的筛选算之前的全库）。"""
    q = (q or "").strip().lower()
    out = []
    with ro() as c:
        for i in _all(c, "SELECT * FROM indicators WHERE state IN ('已入库', '等数据') ORDER BY id DESC"):
            p = _one(c, "SELECT title FROM papers WHERE id = ?", i["paper"])
            out.append({"id": i["id"], "name": i["name"], "name_en": i["name_en"], "kind": "本工具", "state": i["state"],
                        "has_data": i["state"] == "已入库", "paper": i["paper"], "papers": [i["paper"]], "paper_title": p["title"] if p else "",
                        "role": i["role"], "definition": i["definition"], "shape": i["shape"], "unit": i["unit"], "column": i["column"],
                        "symbol_tex": i["symbol_tex"] or "", "admitted": i["admitted"]})
        for o in _all(c, "SELECT * FROM oldlib ORDER BY id"):
            srcs = o["sources"] or []
            pids = sorted({s.get("paper_id") for s in srcs if s.get("paper_id")})
            out.append({"id": o["id"], "name": o["name"], "name_en": o["name_en"], "kind": "旧库", "state": "旧库",
                        "has_data": bool(o["data"]), "paper": "", "papers": pids,
                        "paper_title": "%d 篇论文出处" % len(pids) if pids else (o["formula"] or o["definition"] or ""),
                        "role": "", "definition": o["definition"] or "；".join(m.get("label", "") for m in (o["meanings"] or [])),
                        "formula": o["formula"] or "", "shape": o["shape"], "unit": o["unit"],
                        "column": o["id"], "symbol_tex": "", "admitted": ""})
        titles = {r["id"]: r["title"] for r in _all(c, "SELECT id, title FROM papers")}

    def count(key_fn):
        n = {}
        for x in out:
            for v in key_fn(x):
                if v:
                    n[v] = n.get(v, 0) + 1
        return n
    papers_n = count(lambda x: x["papers"])
    facets = {
        "paper": [{"value": k, "label": "%s《%s》" % (k, titles[k]) if k in titles else "%s（旧库出处）" % k, "n": v}
                  for k, v in sorted(papers_n.items(), key=lambda kv: (kv[0] not in titles, kv[0]))],
        "role": [{"value": k, "label": k, "n": v} for k, v in sorted(count(lambda x: [x["role"]]).items(), key=lambda kv: ROLES.index(kv[0]) if kv[0] in ROLES else 99)],
        "shape": [{"value": k, "label": k, "n": v} for k, v in sorted(count(lambda x: [x["shape"]]).items(), key=lambda kv: -kv[1])],
    }
    if kind:
        out = [x for x in out if x["kind"] == kind]
    if paper:
        out = [x for x in out if paper in x["papers"]]
    if role:
        out = [x for x in out if x["role"] == role]
    if shape:
        out = [x for x in out if x["shape"] == shape]
    if data in ("有", "无"):
        out = [x for x in out if x["has_data"] == (data == "有")]
    if q:
        out = [x for x in out if all(w in " ".join(str(x.get(k, "")) for k in ("id", "name", "name_en", "definition", "paper", "paper_title")).lower()
                                     for w in q.split())]
    return {"items": out, "facets": facets}


# ───────────────────────── AI 帮我找 ─────────────────────────
def lib_assistant(session=None):
    """“变量库助手”对话（专门帮人在库里找变量，不打扰各篇论文的对话）。session 给了就记下。"""
    with (tx() if session is not None else ro()) as c:
        if session is not None:
            c.execute("INSERT INTO meta(k, v) VALUES('lib_session', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (session,))
            return session
        r = c.execute("SELECT v FROM meta WHERE k = 'lib_session'").fetchone()
        return r["v"] if r else ""


def add_lib_search(query, session):
    query = _txt(query, 300)
    if len(query) < 2:
        raise LiteError("写一句话说你要找什么样的变量", "比如：衡量融资约束的指标、和企业创新有关的")
    with tx() as c:
        sid = _next(c, "lib_searches", "S", 3)
        c.execute("INSERT INTO lib_searches(id, query, session, created) VALUES(?,?,?,?)", (sid, query, session, now()))
        return sid


def set_lib_results(search, results, note=""):
    """AI 交检索结果：只收库里真有的编号。search 留空 = 最近一次还没交结果的。"""
    if not isinstance(results, list):
        raise LiteError("results 要是列表：[{id, why}]")
    with tx() as c:
        s = _one(c, "SELECT * FROM lib_searches WHERE id = ?", search) if search else \
            _one(c, "SELECT * FROM lib_searches WHERE done = '' ORDER BY id DESC LIMIT 1") or _one(c, "SELECT * FROM lib_searches ORDER BY id DESC LIMIT 1")
        if s is None:
            raise LiteError("没有要回答的检索", "用户在工厂栏点“AI 帮我找”后才有")
        known = {r["id"] for r in _all(c, "SELECT id FROM oldlib")} | \
                {r["id"] for r in _all(c, "SELECT id FROM indicators WHERE state IN ('已入库', '等数据')")}
        keep, wrong = [], []
        for r in results:
            oid = _txt((r or {}).get("id"), 40) if isinstance(r, dict) else ""
            if oid in known and oid not in [k["id"] for k in keep]:
                keep.append({"id": oid, "why": _txt(r.get("why"), 300)})
            elif oid:
                wrong.append(oid)
        c.execute("UPDATE lib_searches SET results = ?, note = ?, done = ? WHERE id = ?",
                  (json.dumps(keep, ensure_ascii=False), _txt(note, 600), now(), s["id"]))
        return {"search": s["id"], "kept": len(keep), "wrong": wrong}


def lib_search_latest():
    with ro() as c:
        s = _one(c, "SELECT * FROM lib_searches ORDER BY id DESC LIMIT 1")
        if not s:
            return None
        s["results"] = json.loads(s["results"] or "[]")
        names = {}
        for r in s["results"]:
            row = _one(c, "SELECT name, name_en FROM oldlib WHERE id = ?", r["id"]) or _one(c, "SELECT name, name_en, symbol_tex FROM indicators WHERE id = ?", r["id"])
            names[r["id"]] = row or {}
        for r in s["results"]:
            r.update({"name": names[r["id"]].get("name", ""), "name_en": names[r["id"]].get("name_en", ""), "symbol_tex": names[r["id"]].get("symbol_tex", "")})
        return s


def _hit(word, text):
    """短的英文缩写（ROA、SA）要整词出现，免得 sa 命中 sales。"""
    import re
    if word.isascii() and word.isalnum() and len(word) <= 4:
        return re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(word), text) is not None
    return word in text


def search_library(q):
    """给 AI 查重用：旧库变量（含出处摘录）+ 本工具里已有的指标。名称、英文名命中的排在前面。"""
    q = (q or "").strip().lower()
    if not q:
        raise LiteError("query 不能空", "写指标的中文名、英文名或关键词，如 ROA、资产负债率、融资约束")
    words = [w for w in q.replace("，", " ").replace(",", " ").split() if w]
    hits = []
    with ro() as c:
        for o in _all(c, "SELECT * FROM oldlib"):
            head = " ".join([o["id"], o["name"] or "", o["name_en"] or ""] + [m.get("label") or "" for m in o["meanings"] or []]).lower()
            body = " ".join([o["definition"] or "", o["formula"] or ""] + [s.get("quote") or "" for s in (o["sources"] or [])]).lower()
            if all(_hit(w, head + " " + body) for w in words):
                score = sum(2 if _hit(w, head) else 0 for w in words)
                hits.append((score, {"id": o["id"], "name": o["name"], "name_en": o["name_en"], "where": "旧库",
                                     "meanings": [m.get("label") or "" for m in o["meanings"] or []], "formula": o["formula"] or "",
                                     "quotes": [s.get("quote") or "" for s in (o["sources"] or [])][:3]}))
        for i in _all(c, "SELECT * FROM indicators"):
            head = " ".join([i["id"], i["name"] or "", i["name_en"] or ""]).lower()
            text = head + " " + (i["definition"] or "").lower()
            if all(_hit(w, text) for w in words):
                score = 1 + sum(2 if _hit(w, head) else 0 for w in words)
                hits.append((score, {"id": i["id"], "name": i["name"], "name_en": i["name_en"], "where": "本工具（%s）" % i["state"],
                                     "definition": i["definition"], "paper": i["paper"]}))
    hits.sort(key=lambda x: -x[0])
    return [h for _, h in hits][:20]


def overview():
    with ro() as c:
        st = {r["state"]: r["n"] for r in c.execute("SELECT state, COUNT(*) n FROM indicators GROUP BY state")}
        return {"papers": c.execute("SELECT COUNT(*) FROM papers").fetchone()[0], "indicators": st,
                "oldlib": c.execute("SELECT COUNT(*) FROM oldlib").fetchone()[0]}
