# -*- coding: utf-8 -*-
"""带进旧库：把已有变量的定义抄进单人版的总库，给 AI 判断“库里已有 / 常用 / 有新意”做参照。

两种来源：
- 原仓库里有登记卡（warehouse/registry/cards/gv*.yaml）：读登记卡（名称、定义、公式、出处摘录），只读不改。
- 公开版没有登记卡：读 lite/oldlib_defs.json，只有变量名、定义、公式（不带出处原文、不带数据）。
  这个文件由发布工具从登记卡生成（export_public_defs）。

已有变量的数据文件只在原仓库里有，由人自己选带不带：python -m lite import-data [文件夹]。公开版没有这些数据。
"""
import glob
import json
import os
import re
import shutil

from . import paths, store

CARDS = os.path.join(paths.REPO, "warehouse", "registry", "cards")
DEFS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oldlib_defs.json")
SHAPE = {"firm_year": "公司-年", "firm": "公司", "year": "年", "firm_quarter": "公司-季度", "province_year": "省份-年",
         "city_year": "城市-年", "industry_year": "行业-年"}


def _algo(card):
    a = card.get("algorithm") or {}
    formula = str(a.get("formula") or "").strip().strip("`").replace("`", "")
    return str(a.get("description") or "").strip(), formula


def _read_cards(folder):
    import yaml
    out = []
    for p in sorted(glob.glob(os.path.join(folder, "gv*.yaml"))):
        with open(p, encoding="utf-8") as f:
            card = yaml.safe_load(f) or {}
        vid = card.get("var_id") or os.path.splitext(os.path.basename(p))[0]
        meanings, sources = [], []
        for m in card.get("meanings") or []:
            meanings.append({"tag": m.get("tag"), "label": m.get("label")})
            for s in m.get("sources") or []:
                sources.append({"paper_id": s.get("paper_id"), "quote": s.get("quote"), "location": s.get("location"),
                                "meaning": m.get("label")})
        definition, formula = _algo(card)
        out.append({"id": vid, "name": card.get("name") or vid, "name_en": card.get("name_en") or "",
                    "shape": SHAPE.get(card.get("shape"), card.get("shape") or ""), "unit": card.get("unit") or "",
                    "status": card.get("status") or "", "meanings": meanings, "sources": sources,
                    "definition": definition, "formula": formula})
    return out


def _public_name(name):
    """去掉名字里的内部旧编号，如“（V26_CEOAge）”“· 口径变体（V23_n_org_cninfo）”里的括号部分。"""
    name = re.sub(r"[（(][A-Za-z][A-Za-z0-9]*_[^）)]*[）)]", "", name or "")
    return re.sub(r"\s*·\s*口径变体\s*$", "（口径变体）", name).strip()


def _clean(text):
    """去掉括号里的内部说明（出处编号、数据商、课题组扩展之类）。"""
    return re.sub(r"\s*[（(][^（()）]*(课题组|出处|Tushare|CSMAR|万得|Wind)[^（()）]*[）)]", "", text or "").strip()


def export_public_defs(path=DEFS_JSON, folder=CARDS):
    """生成公开版的旧库定义：只留编号、变量名、英文名、数据形状、单位、定义、公式（不带出处原文、不带数据）。返回个数。"""
    rows = []
    for r in _read_cards(folder):
        name, definition = _public_name(r["name"]), _clean(r["definition"])
        rows.append({"id": r["id"], "name": name, "name_en": r["name_en"], "shape": r["shape"], "unit": _clean(r["unit"]),
                     "definition": definition if definition not in ("", name, r["name"]) else "", "formula": _clean(r["formula"])})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return len(rows)


def _read_defs(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return [dict(r, status="", sources=[], meanings=[{"tag": "", "label": r["name"]}]) for r in rows]


def import_cards(folder=CARDS):
    """带进旧库定义，写进 oldlib 表（已有的就更新）。有登记卡读登记卡，没有就读 lite/oldlib_defs.json。返回个数。"""
    if os.path.isdir(folder):
        rows, what = _read_cards(folder), "登记卡"
    elif os.path.isfile(DEFS_JSON):
        rows, what = _read_defs(DEFS_JSON), "内置定义"
    else:
        return 0
    with store.tx() as c:
        for r in rows:
            c.execute("INSERT INTO oldlib(id, name, name_en, shape, unit, status, meanings, sources, definition, formula) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, name_en=excluded.name_en, "
                      "shape=excluded.shape, unit=excluded.unit, status=excluded.status, meanings=excluded.meanings, "
                      "sources=excluded.sources, definition=excluded.definition, formula=excluded.formula",
                      (r["id"], r["name"], r["name_en"], r["shape"], r["unit"], r["status"], json.dumps(r["meanings"], ensure_ascii=False),
                       json.dumps(r["sources"], ensure_ascii=False), r["definition"], r["formula"]))
        if rows:
            store.log(c, "旧库", "带进旧库", "带进 %d 个已有变量的定义（%s）" % (len(rows), what), "工厂")
    return len(rows)


def old_data_available():
    return not paths.PUBLIC and os.path.isdir(default_data_folder())


def default_data_folder():
    """原仓库主文件夹（不是工作树）里的变量文件夹：工作树没有数据文件，按 git 的公共目录找主文件夹。"""
    import subprocess
    repo = paths.REPO
    try:
        common = subprocess.run(["git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
        if common.endswith("/.git"):
            repo = os.path.dirname(common)
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.join(repo, "warehouse", "library", "variables", "firm_year")


def import_data(folder=None, ids=None):
    """把旧库变量的数据文件复制进来（人自己决定带不带；ids 给了就只带这几个）。返回复制的个数。"""
    if paths.PUBLIC and not folder:
        raise store.LiteError("公开版不带旧库的数据文件，只有变量定义", "要用这些变量，在论文里选中后交自己的数据合成")
    folder = folder or default_data_folder()
    if not os.path.isdir(folder):
        raise store.LiteError("找不到旧库的数据文件夹：%s" % folder, "把放 gvXXXX.parquet 的文件夹路径写在命令后面")
    dst_dir = paths.lib("oldlib")
    os.makedirs(dst_dir, exist_ok=True)
    n = 0
    with store.ro() as c:
        known = [r["id"] for r in c.execute("SELECT id FROM oldlib")]
    ids = [i for i in known if not ids or i in ids]
    if not ids:
        raise store.LiteError("没有这些旧库变量")
    done = []
    for vid in ids:
        src = os.path.join(folder, vid + ".parquet")
        if os.path.isfile(src):
            dst = os.path.join(dst_dir, vid + ".parquet")
            shutil.copyfile(src, dst)
            done.append((vid, dst))
            n += 1
    with store.tx() as c:
        for vid, dst in done:
            c.execute("UPDATE oldlib SET data = ? WHERE id = ?", (dst, vid))
        store.log(c, "旧库", "带进旧库数据", "从 %s 复制了 %d 个旧库变量的数据文件" % (folder, n), "你")
    return n
