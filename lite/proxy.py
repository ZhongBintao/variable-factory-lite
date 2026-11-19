# -*- coding: utf-8 -*-
"""工厂栏 = OpenCode 官方网页 + 工厂栏：本机服务把 OpenCode 官方网页原样转过来，只在网页里加两行
（一个脚本、一个样式表），工厂栏由这两个文件画出来。OpenCode 的代码一行不改。

为什么这样做（2026-11-12 调研）：OpenCode v2 有正式的界面插件接口（@opencode/plugin/gui），但只有桌面版加载
配置里的插件，纯网页版（opencode serve / 后台服务）不加载；所以网页版只能在页面外面加。

- 原样转发：请求方法、路径、请求头、请求体照搬；回应边收边转（OpenCode 的事件流要实时）；终端用的 WebSocket 整条接通。
- 只改 OpenCode 的网页本身（content-type 是 text/html 的回应）：在 <head> 后面插入工厂栏的两个文件。
  OpenCode 的页面安全设置（CSP）只许同源脚本，工厂栏的文件就从同一个地址（工厂服务）给，不用改它的安全设置。
- 登录照旧走 OpenCode 自己的：工厂服务不替浏览器带 OpenCode 的口令（不然别的网页借这个地址就能指挥 OpenCode），
  浏览器没登录时工厂栏用一次性配对链接帮人登录。
"""
import http.client
import re
import select
import socket
from urllib.parse import urlsplit

# 工厂栏的两个文件（lite/web/ 下），插在 OpenCode 网页的 <head> 最前面：脚本要在 OpenCode 自己的脚本之前读走网址里的钥匙
INJECT = (b'<link rel="stylesheet" href="/lite/web/lite.css">'
          b'<script src="/lite/web/lite.js"></script>')
_HEAD = re.compile(rb"<head(\s[^>]*)?>", re.I)

# 逐跳的请求头：只管这一段连接，不往下转
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length"}
SKIP_OUT = HOP | {"date", "server"}             # 这两个看板服务自己会写


def inject(html):
    """在 OpenCode 网页的 <head> 后面插入工厂栏；找不到 <head> 就放最前面。"""
    m = _HEAD.search(html)
    if not m:
        return INJECT + html
    return html[:m.end()] + INJECT + html[m.end():]


def split(base):
    u = urlsplit(base)
    return u.hostname, u.port or 80


def read_body(h):
    n = int(h.headers.get("Content-Length") or 0)
    return h.rfile.read(n) if n else None


def own_origin(h):
    """看板自己的地址（浏览器眼里的来源），如 http://127.0.0.1:8791。"""
    port = h.server.server_address[1]
    return {"http://127.0.0.1:%d" % port, "http://localhost:%d" % port}


def fix_origin(h, headers, host, port):
    """OpenCode 只收来自它自己地址的写请求（新建会话、发送等，来源不对回 401）。浏览器里打开的是看板地址，
    所以来源正好是看板自己时，换成 OpenCode 的地址；别的网站发来的请求原样交过去，让 OpenCode 照常拒绝。"""
    mine = own_origin(h)
    up = "http://%s:%d" % (host, port)
    for k in list(headers):
        v = headers[k]
        if k.lower() == "origin" and v in mine:
            headers[k] = up
        elif k.lower() == "referer" and any(v == o or v.startswith(o + "/") for o in mine):
            headers[k] = up + v[v.index("/", len("http://")):] if v.count("/") > 2 else up + "/"


def forward(h, base, body=None):
    """把这次请求原样转给 OpenCode（base 如 http://127.0.0.1:49374），回应写回浏览器。连不上返回 False
    （这时还没往浏览器写任何东西，可以换个地址再试）。请求体由调用方先读好（body），重试时不丢。"""
    host, port = split(base)
    if (h.headers.get("Upgrade") or "").lower() == "websocket":
        return _tunnel(h, host, port)
    headers = {k: v for k, v in h.headers.items() if k.lower() not in HOP and k.lower() != "accept-encoding"}
    headers["Host"] = "%s:%d" % (host, port)
    fix_origin(h, headers, host, port)
    conn = http.client.HTTPConnection(host, port, timeout=900)
    try:
        conn.request(h.command, h.path, body=body, headers=headers)
        r = conn.getresponse()
    except OSError:
        conn.close()
        return False
    try:
        out = [(k, v) for k, v in r.getheaders() if k.lower() not in SKIP_OUT]
        no_body = h.command == "HEAD" or r.status in (204, 304) or 100 <= r.status < 200
        if (r.getheader("Content-Type") or "").startswith("text/html") and not no_body:
            data = inject(r.read())
            h.send_response(r.status)
            for k, v in out:
                h.send_header(k, v)
            h.send_header("Content-Length", str(len(data)))
            h.end_headers()
            h.wfile.write(data)
            return True
        h.send_response(r.status)
        for k, v in out:
            h.send_header(k, v)
        if no_body:
            h.send_header("Content-Length", "0")
            h.end_headers()
            return True
        length = r.getheader("Content-Length")
        if length is not None:                      # 知道长度：照原样
            h.send_header("Content-Length", length)
            h.end_headers()
            left = int(length)
            while left > 0:
                chunk = r.read(min(65536, left))
                if not chunk:
                    break
                h.wfile.write(chunk)
                left -= len(chunk)
            return True
        h.send_header("Transfer-Encoding", "chunked")   # 不知道长度（事件流等）：收到一点转一点
        h.end_headers()
        while True:
            chunk = r.read1(65536)
            if not chunk:
                break
            h.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
            h.wfile.flush()
        h.wfile.write(b"0\r\n\r\n")
        return True
    except (BrokenPipeError, ConnectionResetError):
        h.close_connection = True                     # 浏览器那头关了（换页、关标签）
        return True
    finally:
        conn.close()


def _tunnel(h, host, port):
    """WebSocket（OpenCode 的终端）：把握手原样交给 OpenCode，之后两头的字节互相转，直到一头关掉。"""
    try:
        up = socket.create_connection((host, port), timeout=10)
    except OSError:
        return False
    lines = ["%s %s HTTP/1.1" % (h.command, h.path), "Host: %s:%d" % (host, port)]
    hd = {k: v for k, v in h.headers.items() if k.lower() != "host"}
    fix_origin(h, hd, host, port)
    lines += ["%s: %s" % (k, v) for k, v in hd.items()]
    up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    h.close_connection = True
    h.wfile.flush()
    down = h.connection
    up.settimeout(None)
    down.settimeout(None)
    try:
        while True:
            ready, _, _ = select.select([down, up], [], [], 300)
            if not ready:
                continue
            for s in ready:
                data = s.recv(65536)
                if not data:
                    return True
                (up if s is down else down).sendall(data)
    except OSError:
        return True
    finally:
        up.close()
