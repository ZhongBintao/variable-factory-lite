# -*- coding: utf-8 -*-
"""单人版的本机网页服务（只听 127.0.0.1）：

- /lite/api/*   工厂栏的接口（要带钥匙：请求头 X-Lite-Key）
- /lite/pdf/P001、/lite/file/…   打开论文 PDF、合成代码（凭本机的 Cookie：第一次带钥匙访问时发下）
- /lite/web/*   工厂栏的脚本、样式
- 别的地址      原样转给 OpenCode 后台，它的网页里插上工厂栏（lite/proxy.py）

钥匙：第一次启动随机生成，存在 设置/key（只本人可读）；打开网址时放在 # 后面，工厂栏读走后存在本页。
别的网页拿不到钥匙，就没法借这个服务往 AI 对话里塞话、改库。
多个对话并行：一个对话只做一篇论文，一篇论文可以有几个对话；工厂栏看的是“网址里那个对话”的论文；往对话里发的话，发给人正在点的那个对话（或这篇论文最近用的对话）。
"""
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote

from . import export, library, opencode, paths, proxy, store

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2"}
MAX_UPLOAD = 1 << 30          # 1 GB
COOKIE = "lite_key"


# ───── 发进对话的话（AI 照 工作区/AGENTS.md 处理以【工厂栏】开头的话）─────
def say_uploaded(p):
    return ("【工厂栏】我上传了论文 %s《%s》（%d 页）。请按 AGENTS.md 第 1 步提取指标：先 paper_outline 看目录，只精读要紧的页，"
            "列出变量定义表和模型里的全部变量；只给推荐的 2–4 个写理由和公式，用 save_candidates 一次交给工厂。" % (p["id"], p["title"], p["pages"]))


def say_chosen(paper, made):
    return ("【工厂栏】我在 %s 里选中了：%s（选中就算认可了定义）。请逐个列出合成它们需要的原始数据（set_data_needs）。"
            % (paper, "、".join("%s %s" % (m["id"], m["name"]) for m in made)))


def say_lib_search(q):
    return ("【工厂栏】请在变量库里帮我找：%s。用 factory_search_library 换几种说法查（中文名、英文缩写、含义），"
            "挑出真正相关的，用 factory_show_search_results 交给工厂（每个写一句为什么相关）。" % q)


def say_ready(ind):
    return "【工厂栏】%s %s 的数据交齐了，请看数据、写代码合成（data_preview → build），然后把小结讲给我。" % (ind["id"], ind["name"])


ASK = {
    "extract": lambda d: "【工厂栏】请把论文 %s 的指标提取出来（先 paper_outline 看目录，精读要紧的页，用 save_candidates 一次交）。" % d["id"],
    "more": lambda d: "【工厂栏】论文 %s 的候选指标好像没列全，请去读刚才没读的页（paper_outline 看哪些没读），把漏掉的指标补上（save_candidates）。" % d["id"],
    "needs": lambda d: "【工厂栏】请列出 %s %s 合成需要的原始数据（set_data_needs）。" % (d["id"], d["name"]),
    "data_help": lambda d: "【工厂栏】我给 %s %s 交的数据没通过校验，请看看哪里不对（data_preview），用大白话告诉我要怎么改。" % (d["id"], d["name"]),
    "build": lambda d: "【工厂栏】请合成 %s %s（data_preview → build），然后把小结讲给我。" % (d["id"], d["name"]),
    "explain": lambda d: "【工厂栏】请用大白话解读一下 %s %s 的合成小结：结果合不合理、要注意什么、能不能入库。" % (d["id"], d["name"]),
    "hello": lambda d: "【工厂栏】接下来在这个对话里继续做论文 %s《%s》。请先用 factory_status 看看做到哪了，告诉我下一步。" % (d["id"], d["title"]),
    "rebuild": lambda d: "【工厂栏】%s %s 的合成结果我不太满意，请先问我哪里要改，再重新合成。" % (d["id"], d["name"]),
}


def key_path():
    return paths.cfg("key")


def stable_key():
    p = key_path()
    try:
        k = open(p, encoding="utf-8").read().strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{24,}", k):
            return k
    except OSError:
        pass
    paths.ensure()
    k = secrets.token_urlsafe(24)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(k)
    return k


class Upstream(object):
    """OpenCode 后台地址，记一会儿；转发连不上时重新问。"""

    def __init__(self):
        self.base = None

    def get(self, fresh=False):
        if fresh or self.base is None:
            self.base = opencode.url(fresh=fresh)
        return self.base


def notify(sid, text):
    """后台往对话里发话（不让网页等）。"""
    if sid:
        threading.Thread(target=opencode.send, args=(sid, text), daemon=True).start()


def make_handler(key, upstream=None, send=None):
    upstream = upstream or Upstream()
    send = send or notify

    class H(BaseHTTPRequestHandler):
        server_version = "lite"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # ── 回应 ──
        def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
            b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _host_ok(self):
            return (self.headers.get("Host") or "").rsplit(":", 1)[0] in ("127.0.0.1", "localhost")

        def _key_ok(self):
            return secrets.compare_digest(self.headers.get("X-Lite-Key") or "", key)

        def _cookie_ok(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE and secrets.compare_digest(v, key):
                    return True
            return False

        def _json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 2_000_000:
                raise store.LiteError("请求太大")
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                raise store.LiteError("请求不是合法的 JSON")

        def _upload(self, suffix):
            """把请求体（文件原样）存到临时文件。"""
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                raise store.LiteError("文件是空的")
            if n > MAX_UPLOAD:
                raise store.LiteError("文件太大（超过 1 GB）", "拆成几份，或只保留要用的列再上传")
            fd, tmp = tempfile.mkstemp(suffix=suffix)
            left = n
            with os.fdopen(fd, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            return tmp

        def _guard(self, fn):
            if not self._host_ok():
                return self._send(403, {"error": {"message": "只给本机用"}})
            if not self._key_ok():
                return self._send(403, {"error": {"message": "钥匙不对", "what_to_do": "双击桌面上的“变量库工厂（单人版）”重新打开"}})
            try:
                return self._send(200, fn(), extra={"Set-Cookie": "%s=%s; Path=/lite/; HttpOnly; SameSite=Strict" % (COOKIE, key)})
            except store.LiteError as e:
                return self._send(400, e.to_dict())
            except Exception as e:      # noqa
                import traceback
                traceback.print_exc()
                return self._send(500, {"error": {"message": "工厂自己出了问题：%s: %s" % (type(e).__name__, e)}})

        def _static(self, name):
            ext = os.path.splitext(name)[1].lower()
            p = os.path.join(HERE, "web", name)
            if not re.fullmatch(r"(katex/(fonts/)?)?[A-Za-z0-9_.-]+", name) or ".." in name or ext not in STATIC or not os.path.isfile(p):
                return self._send(404, {"error": {"message": "没有这个文件"}})
            with open(p, "rb") as f:
                return self._send(200, f.read(), STATIC[ext])

        def _file(self, path, ctype, name=None):
            if not self._host_ok() or not self._cookie_ok():
                return self._send(403, "请从工厂栏里点开（钥匙不对）".encode("utf-8"), "text/plain; charset=utf-8")
            if not path or not os.path.isfile(path):
                return self._send(404, "文件不在了".encode("utf-8"), "text/plain; charset=utf-8")
            with open(path, "rb") as f:
                data = f.read()
            extra = {"Content-Disposition": "inline"}
            return self._send(200, data, ctype, extra)

        def _opencode(self):
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            body = proxy.read_body(self)
            base = upstream.get()
            if base and proxy.forward(self, base, body):
                return
            base = upstream.get(fresh=True)
            if base and proxy.forward(self, base, body):
                return
            return self._send(502, ("<meta charset=utf-8><body style='font:16px -apple-system;padding:40px'>"
                                    "<h3>OpenCode 后台没开</h3><p>双击桌面上的“变量库工厂（单人版）”重新打开。</p>").encode("utf-8"),
                              "text/html; charset=utf-8")

        # ── 路由 ──
        def do_GET(self):
            path, _, query = self.path.partition("?")
            q = {k: v[-1] for k, v in parse_qs(query).items()}
            if path.startswith("/lite/web/"):
                return self._static(path[len("/lite/web/"):])
            m = re.fullmatch(r"/lite/pdf/(P\d+)(?:\.pdf)?", path)
            if m:
                try:
                    return self._file(store.paper_path(m.group(1)), "application/pdf")
                except store.LiteError:
                    return self._send(404, "没有这篇论文".encode("utf-8"), "text/plain; charset=utf-8")
            m = re.fullmatch(r"/lite/code/(R\d+)", path)
            if m:
                p = paths.lib("builds", m.group(1), "code.py")
                return self._file(p, "text/plain; charset=utf-8")
            if path == "/lite/api/stamp":
                return self._guard(lambda: {"rev": store.rev()})
            if path == "/lite/api/view":
                return self._guard(lambda: view(q.get("session", ""), q.get("paper", "")))
            if path == "/lite/api/papers":
                return self._guard(store.papers)
            if path == "/lite/api/item":
                return self._guard(lambda: store.detail(q.get("id", "")))
            if path == "/lite/api/library":
                return self._guard(lambda: dict(store.library(q.get("q", ""), q.get("kind", ""), q.get("paper", ""), q.get("role", ""),
                                                              q.get("shape", ""), q.get("data", "")),
                                                overview=dict(store.overview(), old_data=library.old_data_available(),
                                                              old_name="内置定义" if paths.PUBLIC else "旧库"),
                                                search=store.lib_search_latest()))
            if path == "/lite/api/connect":
                return self._guard(lambda: {"path": opencode.pair()})
            if path.startswith("/lite/"):
                return self._send(404, {"error": {"message": "没有这个地址"}})
            return self._opencode()

        def do_POST(self):
            path, _, query = self.path.partition("?")
            q = {k: unquote(v[-1]) for k, v in parse_qs(query).items()}
            routes = {
                "/lite/api/upload-paper": lambda: upload_paper(self, q),
                "/lite/api/upload-data": lambda: upload_data(self, q),
                "/lite/api/choose": lambda: choose(self._json()),
                "/lite/api/drop": lambda: (store.drop(self._json()["indicator"]), {})[1],
                "/lite/api/colmap": lambda: colmap(self._json()),
                "/lite/api/override": lambda: override(self._json()),
                "/lite/api/defer": lambda: (store.defer(self._json()["indicator"]), {})[1],
                "/lite/api/resume": lambda: (store.resume(self._json()["indicator"]), {})[1],
                "/lite/api/admit": lambda: (store.admit(self._json()["indicator"]), {})[1],
                "/lite/api/export": lambda: do_export(self._json()),
                "/lite/api/ask": lambda: ask(self._json()),
                "/lite/api/bind": lambda: bind(self._json()),
                "/lite/api/new-session": lambda: {"session": opencode.new_session(self._json().get("title") or "新对话")},
                "/lite/api/paper-session": lambda: paper_session(self._json()),
                "/lite/api/lib-search": lambda: lib_search(self._json()),
                "/lite/api/reset": lambda: (self._json(), do_reset())[1],      # 先读掉请求体，免得留在连接里
                "/lite/api/import-old-data": lambda: import_old(self._json()),
            }
            if path in routes:
                return self._guard(routes[path])
            if path.startswith("/lite/"):
                return self._send(404, {"error": {"message": "没有这个地址"}})
            return self._opencode()

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = _opencode

    # ───── 动作 ─────
    def session_of(paper, cur=""):
        """往哪个对话发话：人正在点的那个对话（属于这篇论文才算），否则这篇论文最近用的对话。"""
        if cur and store.touch(paper, cur):
            return cur
        with store.ro() as c:
            r = c.execute("SELECT session FROM papers WHERE id = ?", (paper,)).fetchone()
            return r["session"] if r else ""

    def free_session(cur):
        """要给一篇论文找个对话：当前对话在工作区里、还没做别的论文，就用它；否则（首页、草稿、别的项目、已经在做别的论文）新开一个。
        返回 (会话, 是不是新开的)。"""
        info = opencode.session_info(cur) if cur else None
        if info and info["in_workspace"] and not store.session_paper(cur):
            return cur, False
        return opencode.new_session("新对话"), True

    def upload_paper(h, q):
        name = q.get("name") or "论文.pdf"
        tmp = h._upload(".pdf")
        try:
            old = store.find_paper(store.md5_file(tmp))
            if old:          # 之前上传过：不新开对话，告诉人它在哪
                return {"paper": old["id"], "dup": True, "session": old["session"], "title": old["title"],
                        "message": "这篇论文之前上传过（%s）。" % old["id"]}
            busy = bool(store.session_paper(q.get("session", "")))
            sid, new = free_session(q.get("session", ""))
            p = store.add_paper(tmp, name, sid)
        finally:
            os.remove(tmp)
        if p["dup"]:
            return {"paper": p["id"], "dup": True, "session": p["session"], "title": p["title"],
                    "message": "这篇论文之前上传过（%s）。" % p["id"]}
        name_session(sid, p)
        send(sid, say_uploaded(p))
        return {"paper": p["id"], "dup": False, "session": sid, "new_session": new, "because_busy": busy, "title": p["title"]}

    def name_session(sid, p, n=1):
        """对话名改成 论文编号 + 标题（同一篇的第 2 个对话加“（2）”）。"""
        t = p["title"]
        t = t if len(t) <= 40 else t[:38] + "…"
        threading.Thread(target=opencode.rename, args=(sid, "%s %s%s" % (p["id"], t, "（%d）" % n if n > 1 else "")), daemon=True).start()

    def upload_data(h, q):
        ind, need, name = q.get("indicator", ""), q.get("need", ""), q.get("name") or "数据.csv"
        tmp = h._upload(os.path.splitext(name)[1] or ".dat")
        try:
            r = store.add_datafile(ind, need, tmp, name)
        finally:
            os.remove(tmp)
        _maybe_ready(ind, r["state"], q.get("session", ""))
        return r

    def _maybe_ready(ind, state, cur=""):
        if state == "待合成":
            d = store.detail(ind)
            send(session_of(d["paper"], cur), say_ready(d))

    def choose(b):
        made = store.choose(b["paper"], b.get("candidates") or [])
        if made:
            send(session_of(b["paper"], b.get("session", "")), say_chosen(b["paper"], made))
        return {"made": made}

    def colmap(b):
        r = store.set_colmap(b["datafile"], b.get("colmap") or {})
        d = store.detail(b["datafile"])
        _maybe_ready(d["indicator"], r["state"], b.get("session", ""))
        return r

    def override(b):
        r = store.override(b["datafile"], b.get("reason", ""))
        d = store.detail(b["datafile"])
        _maybe_ready(d["indicator"], r["state"], b.get("session", ""))
        return r

    def ask(b):
        what, oid = b.get("what", ""), b.get("id", "")
        if what not in ASK and what != "lib_search":
            raise store.LiteError("不认识的请求：%s" % what)
        if what == "lib_search":
            s = store.lib_search_latest()
            if not s:
                raise store.LiteError("还没有让 AI 找过")
            sid, text = s["session"], say_lib_search(s["query"])
        else:
            d = store.detail(oid)
            obj = d["paper"] if d.get("type") == "paper" else d
            sid = session_of(obj["id"] if d.get("type") == "paper" else d["paper"], b.get("session", ""))
            text = ASK[what](obj)
        ok, why = opencode.send(sid, text)
        if not ok:
            raise store.LiteError("没发出去：%s" % why, "在对话里直接跟 AI 说")
        return {"sent": True}

    def bind(b):
        """把一篇论文挪到当前对话（当前对话已经在做别的论文就新开一个）。"""
        sid, new = free_session(b.get("session", ""))
        store.bind(b["paper"], sid)
        p = store.detail(b["paper"])["paper"]
        name_session(sid, p, len(p["sessions"]))
        if b.get("hello"):
            send(sid, ASK["hello"](p))
        return {"session": sid, "new_session": new}

    def paper_session(b):
        """给一篇论文再开一个对话。"""
        p = store.detail(b["paper"])["paper"]
        sid = opencode.new_session("%s %s" % (p["id"], p["title"][:30]))
        store.bind(p["id"], sid)
        name_session(sid, p, len(p["sessions"]) + 1)
        send(sid, ASK["hello"](p))
        return {"session": sid}

    def lib_search(b):
        """AI 帮我找：发给“变量库助手”对话（没有或不在了就新开）。"""
        sid = store.lib_assistant()
        info = opencode.session_info(sid) if sid else None
        if not (info and info["in_workspace"]):
            sid = store.lib_assistant(opencode.new_session("变量库助手"))
        q = (b.get("query") or "").strip()
        sr = store.add_lib_search(q, sid)
        ok, why = opencode.send(sid, say_lib_search(q))
        if not ok:
            raise store.LiteError("没发出去：%s" % why, "过一会儿再试")
        return {"search": sr, "session": sid}

    def do_reset():
        from . import app
        return app.reset()

    def import_old(b):
        n = library.import_data(ids=b.get("ids") or None)
        if not n:
            raise store.LiteError("没找到这个变量的数据文件", "旧库的数据文件夹里没有它")
        return {"n": n}

    def do_export(b):
        r = export.export(b.get("ids") or [])
        if b.get("reveal") and sys.platform == "darwin":
            subprocess.run(["open", r["folder"]], check=False)
        elif b.get("reveal") and paths.WINDOWS:
            os.startfile(r["folder"])       # noqa  在资源管理器里打开
        return r

    return H


def view(session, paper=""):
    """工厂栏一次要的东西：当前对话在做的那篇论文（一个对话只做一篇）、对话在不在工作区、别的论文。"""
    info = opencode.session_info(session) if session else None
    pid = store.session_paper(session) if session else ""
    paper = store.detail(pid) if pid else None
    if info and paper:
        # AI 交候选时会从第 1 页抄出真标题；对话名还是上传时的文件名，就跟着改
        t = paper["paper"]["title"]
        want = "%s %s" % (pid, t if len(t) <= 40 else t[:38] + "…")
        if info["title"].startswith(pid + " ") and not info["title"].startswith(want):
            m = re.search(r"（\d+）$", info["title"])
            info["title"] = want + (m.group(0) if m else "")
            threading.Thread(target=opencode.rename, args=(session, info["title"]), daemon=True).start()
    return {"session": session, "session_ok": bool(info and info["in_workspace"]), "session_known": info is not None,
            "is_assistant": bool(session) and session == store.lib_assistant(),
            "paper": paper,
            "others": [p for p in store.papers() if p["id"] != pid][:30]}


def make_server(port=None, key=None, upstream=None, send=None):
    key = key or stable_key()
    srv = ThreadingHTTPServer(("127.0.0.1", paths.PORT if port is None else port), make_handler(key, upstream, send))
    srv.daemon_threads = True
    srv.key = key
    return srv


def serve(port=None):
    paths.ensure()
    srv = make_server(port)
    print("单人版工厂已开：http://127.0.0.1:%d/" % srv.server_address[1], file=sys.stderr, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve()
