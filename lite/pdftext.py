# -*- coding: utf-8 -*-
"""读论文 PDF 的文字层，核对原文摘录（不编造出处：摘录必须在那一页的原文里找得到）。

页码一律是 PDF 的第几页（从 1 开始），和浏览器打开 PDF 时的页码一致（网址 #page=N 跳得过去）。
核对时把两边都“压平”再比：统一全角半角和连字（ﬁ → fi）、去掉断行连字符和所有空白、不分大小写。
这样 PDF 里“公 司 业 绩”这种字间带空格的、英文断行“quantita-\\ntive”的，照原文抄也对得上；改了字就对不上。
"""
import functools
import os
import re
import unicodedata

MAX_PAGES_PER_READ = 6
MAX_CHARS_PER_READ = 45000


@functools.lru_cache(maxsize=16)
def _pages(path, mtime):
    import pymupdf
    with pymupdf.open(path) as d:
        return tuple(p.get_text() for p in d)


def pages(path):
    """[(第 1 页文字), ...]"""
    return list(_pages(path, os.path.getmtime(path)))


def info(path):
    import pymupdf
    with pymupdf.open(path) as d:
        meta = d.metadata or {}
        n = d.page_count
    title = (meta.get("title") or "").strip()
    if not title or len(title) < 4 or title.lower().endswith((".pdf", ".doc", ".docx")) or title.lower() in ("untitled", "无标题"):
        title = ""
    txt = pages(path)
    chars = sum(len(t.strip()) for t in txt)
    return {"pages": n, "title": title, "chars": chars, "scanned": n > 0 and chars / n < 80}


def parse_pages(spec, n):
    """"3-5" / "3,7" / "" → 页码列表（1 开始）。"""
    spec = (spec or "").strip().replace("，", ",").replace("～", "-").replace("~", "-").replace("—", "-")
    if not spec:
        return list(range(1, min(n, MAX_PAGES_PER_READ) + 1))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            out += list(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise ValueError("页码写法看不懂：%s（写成 3-5 或 3,7）" % part)
    out = [p for p in dict.fromkeys(out) if 1 <= p <= n]
    if not out:
        raise ValueError("页码超出范围：这篇论文共 %d 页" % n)
    return out


def flat(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("­", "")                     # 软连字符
    s = re.sub(r"[-‐‑‒–—−]", "", s)       # 连字符、破折号、减号都不比（断行连字符和原有连字符分不清）
    s = re.sub(r"[\s　]+", "", s)
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return s.lower()


def quote_on_page(path, page, quote):
    """摘录在第 page 页吗。返回 (在不在, 说明)。也看看它是不是其实在别的页。"""
    q = flat(quote)
    if len(q) < 6:
        return False, "摘录太短（至少 6 个字），要能看出定义"
    txt = pages(path)
    if not 1 <= int(page) <= len(txt):
        return False, "页码 %s 超出范围：这篇论文共 %d 页" % (page, len(txt))
    if q in flat(txt[int(page) - 1]):
        return True, ""
    # 跨页的摘录：和下一页连起来看
    if int(page) < len(txt):
        a, both = flat(txt[int(page) - 1]), flat(txt[int(page) - 1] + txt[int(page)])
        pos = both.find(q)
        if pos != -1 and pos < len(a) < pos + len(q):     # 从这一页开头、接到下一页：算这一页
            return True, ""
    others = [i + 1 for i, t in enumerate(txt) if q in flat(t)]
    if others:
        return False, "这段摘录不在第 %s 页，在第 %s 页；把页码改对" % (page, "、".join(map(str, others[:5])))
    return False, "第 %s 页的原文里找不到这段摘录：摘录要从原文逐字照抄（可以只抄定义那一两句），不能改写、翻译或拼接" % page


def find(path, phrase, limit=12):
    """在全文里找一个词，返回 [{page, context}]。"""
    q = flat(phrase)
    if not q:
        return []
    out = []
    for i, t in enumerate(pages(path)):
        one = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", t))
        f = flat(one)
        if q not in f:
            continue
        # 在不压平的文字里大致找位置：按压平前后字数比例估一个，给前后 160 个字
        pos = f.index(q)
        ratio = len(one) / max(1, len(f))
        c = int(pos * ratio)
        out.append({"page": i + 1, "context": one[max(0, c - 160): c + 220].strip()})
        if len(out) >= limit:
            break
    return out


# 精读哪几页：找变量定义、研究设计、附录这些地方
KEYS = [("变量定义", r"变量(的)?定义|变量说明|变量界定|变量设定|主要变量|variable\s+(definition|description|construction|measure)s?|definitions?\s+of\s+(the\s+)?variables|measurement\s+of"),
        ("研究设计", r"研究设计|模型设定|模型构建|实证模型|计量模型|研究方法|research\s+design|empirical\s+(model|strategy|specification)|methodology"),
        ("样本数据", r"样本选择|数据来源|样本与数据|sample\s+(selection|construction)|data\s+(and|source)"),
        ("描述性统计", r"描述性统计|descriptive\s+statistics|summary\s+statistics"),
        ("附录", r"^\s*(附录|appendix|online\s+appendix)"),
        ("稳健性", r"稳健性检验|robustness"),
        ("参考文献", r"^\s*(参考文献|references|bibliography)\s*$")]
HEAD = re.compile(r"^\s*((第?[一二三四五六七八九十]+[、.．章节])|([（(][一二三四五六七八九十]+[)）])|(\d+(\.\d+){0,2}[.、．\s]\s*\S)|([IVX]+\.\s)|(表\s*\d+)|(table\s+\d+)|(appendix)|(附录))", re.I)


def outline(path):
    """每页一行：像标题的几行 + 命中的关键词（★变量定义 等）。给 AI 挑精读的页，不用从头读到尾。"""
    out = []
    for i, t in enumerate(pages(path), 1):
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        heads = [ln[:40] for ln in lines if len(ln) <= 60 and HEAD.match(ln) and len(re.findall(r"[A-Za-z\u4e00-\u9fff]", ln)) >= 3][:3]
        if not heads and lines:
            heads = [lines[0][:50]]
        tags = [name for name, rx in KEYS if re.search(rx, t, re.I | re.M)]
        out.append({"page": i, "heads": heads, "tags": tags, "chars": len(t.strip())})
    return out
