# -*- coding: utf-8 -*-
"""和本机 OpenCode 后台打交道：`opencode` 命令替我们带好它的口令（这里不读、不存 OpenCode 的口令）。

- 对话（会话）都开在单人版的工作区（paths.workspace()）里：那里的 opencode.jsonc 接好了工厂工具。
- 往对话里发话：POST /api/session/<会话>/prompt（工厂栏上传论文、选完指标、数据交齐时自动发）。
- 浏览器没登录 OpenCode：要一次性配对链接（/api/pair，5 分钟内有效、只能用一次），只交给钥匙对的工厂栏。
"""
import base64
import json
import os
import re
import shutil
import subprocess
import time
from urllib.parse import quote

from . import paths

_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost):\d+")
SID = re.compile(r"ses_[A-Za-z0-9]+")


def which():
    if paths.WINDOWS:
        return _which_windows()
    return shutil.which("opencode") or next((p for p in ("/opt/homebrew/bin/opencode", "/usr/local/bin/opencode",
                                                          os.path.expanduser("~/.opencode/bin/opencode")) if os.path.exists(p)), None)


def _which_windows():
    """Windows：要真正的 opencode.exe。npm 装的只在 PATH 里放了 opencode.cmd（批处理），经批处理转一道，
    发给 AI 的中文和引号会被 cmd 改坏，所以顺着它找到 node_modules 里的 exe。"""
    home = os.path.expanduser("~")
    found = [shutil.which("opencode.exe"), shutil.which("opencode.cmd"), shutil.which("opencode")]
    found += [os.path.join(home, ".opencode", "bin", "opencode.exe"),
              os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "npm", "opencode.cmd")]
    for p in found:
        if not p or not os.path.exists(p):
            continue
        low = p.lower()
        if low.endswith(".exe"):
            return p
        if low.endswith(".cmd") or low.endswith(".ps1") or "." not in os.path.basename(low):
            exe = os.path.join(os.path.dirname(p), "node_modules", "@opencode", "cli", "bin", "opencode.exe")
            if os.path.exists(exe):
                return exe
    return None


def run(args, data=None, timeout=20):
    exe = which()
    if not exe:
        return 127, "没装 OpenCode"
    cmd = [exe] + list(args)
    if data is not None:
        cmd += ["-d", json.dumps(data, ensure_ascii=False)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=paths.NO_WINDOW)
    except subprocess.TimeoutExpired:
        return 124, "OpenCode 没在 %d 秒内回应" % timeout
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def api(method, path, data=None, timeout=20, params=None):
    args = ["api", method, path]
    for k, v in (params or {}).items():
        args += ["--param", "%s=%s" % (k, v)]
    code, out = run(args, data, timeout)
    try:
        return code, json.loads(out)
    except ValueError:
        return code, {"_text": out.strip()[:400]}


_url_cache = {"at": 0, "url": None}


def url(fresh=False):
    """OpenCode 后台的本机地址；没开就 None。问一次要零点几秒，记 5 秒。"""
    if not fresh and time.time() - _url_cache["at"] < 5:
        return _url_cache["url"]
    code, out = run(["service", "status"], timeout=8)
    m = _URL.search(out) if code == 0 and "stopped" not in out else None
    _url_cache.update(at=time.time(), url=m.group(0) if m else None)
    return _url_cache["url"]


def start():
    run(["service", "start"], timeout=40)
    return url(fresh=True)


def session_path(origin, sid):
    """OpenCode 网页里打开某个会话的路径：/server/<网页地址做 base64url，去掉 =>/session/<编号>。"""
    enc = base64.urlsafe_b64encode(origin.encode("utf-8")).decode("ascii").rstrip("=")
    return "/server/%s/session/%s" % (enc, sid)


def _in_ws(directory):
    if not directory:
        return False
    ws = os.path.normcase(os.path.realpath(paths.workspace()))     # Windows 不分大小写、/ 和 \ 混用
    d = os.path.normcase(os.path.realpath(directory))
    return d == ws or d.startswith(ws.rstrip(os.sep) + os.sep)


def sessions(n=50):
    """工作区里的主对话（不含子任务），最近用过的在前。"""
    code, d = api("GET", "/api/session", params={"limit": max(n, 50), "order": "desc"})
    rows = d.get("data") if isinstance(d, dict) else None
    if not isinstance(rows, list):
        return []
    rows = [s for s in rows if not s.get("parentID") and _in_ws((s.get("location") or {}).get("directory"))]
    rows.sort(key=lambda s: (s.get("time") or {}).get("updated", 0), reverse=True)
    return [{"id": s["id"], "title": s.get("title") or "新对话", "updated": (s.get("time") or {}).get("updated", 0)} for s in rows[:n]]


def all_workspace_sessions():
    """工作区里的全部对话编号（含子任务、归档的），重置时用。"""
    code, d = api("GET", "/api/session", params={"limit": 500, "directory": paths.workspace()})
    rows = d.get("data") if isinstance(d, dict) else None
    if code != 0 or not isinstance(rows, list):
        raise RuntimeError("问 OpenCode 要对话列表没成功：%s" % (d.get("_text") if isinstance(d, dict) else d))
    return [s["id"] for s in rows if _in_ws((s.get("location") or {}).get("directory"))]


def delete_session(sid):
    if sid and SID.fullmatch(sid):
        code, _ = api("DELETE", "/api/session/%s" % sid)
        _sess_cache.pop(sid, None)
        return code == 0
    return False


_sess_cache = {}


def session_info(sid):
    """{id, title, in_workspace}；没有这个对话返回 None。记 10 秒。"""
    if not sid or not SID.fullmatch(sid):
        return None
    hit = _sess_cache.get(sid)
    if hit and time.time() - hit[0] < 10:
        return hit[1]
    code, d = api("GET", "/api/session/%s" % sid)
    d = d.get("data", d) if isinstance(d, dict) else {}
    info = None
    if code == 0 and isinstance(d, dict) and d.get("id") == sid:
        info = {"id": sid, "title": d.get("title") or "新对话", "in_workspace": _in_ws((d.get("location") or {}).get("directory"))}
    _sess_cache[sid] = (time.time(), info)
    return info


def new_session(title=""):
    body = {"title": (title or "").strip()[:80] or None, "location": {"directory": paths.workspace()}}
    code, d = api("POST", "/api/session", data=body)
    d = d.get("data", d) if isinstance(d, dict) else {}
    sid = d.get("id") if isinstance(d, dict) else None
    if code != 0 or not sid or not SID.fullmatch(sid):
        raise RuntimeError("OpenCode 没建成对话：%s" % (d.get("_text") if isinstance(d, dict) else d))
    return sid


def rename(sid, title):
    """给对话改名（侧边栏、标签上显示论文名，几个对话好分）。"""
    if sid and SID.fullmatch(sid) and title:
        api("PATCH", "/api/session/%s" % sid, data={"title": title[:60]})
        _sess_cache.pop(sid, None)


def send(sid, text):
    """往对话里发一句话（AI 收到就开始干）。返回 (成功, 说明)。"""
    if not sid or not SID.fullmatch(sid):
        return False, "没有对话"
    code, d = api("POST", "/api/session/%s/prompt" % sid, data={"text": text}, timeout=30)
    if code != 0:
        return False, "OpenCode 没收下：%s" % (d.get("_text") if isinstance(d, dict) else d)
    return True, ""


def pair():
    """一次性配对链接（帮浏览器登录 OpenCode）。返回路径 /auth/connect/<码>；拿不到返回 None。"""
    code, d = api("POST", "/api/pair")
    pc = (d.get("code") or (d.get("data") or {}).get("code")) if isinstance(d, dict) else None
    if code != 0 or not pc or not re.fullmatch(r"[A-Za-z0-9_-]+", pc):
        return None
    return "/auth/connect/%s" % pc


def any_busy():
    """有没有对话里的 AI 正在干活（让 OpenCode 重读配置会打断它们）。"""
    code, d = api("GET", "/api/session", params={"limit": 50, "order": "desc"})
    for r in (d.get("data") or []) if isinstance(d, dict) else []:
        t = r.get("time") or {}
        if t.get("busy") and t.get("busy", 0) > t.get("idle", 0):
            return True
    return False


def mcp_status(folder):
    code, d = api("GET", "/api/mcp?location%%5Bdirectory%%5D=%s" % quote(folder))
    try:
        return {m["name"]: (m.get("status") or {}).get("status") for m in d["data"]}
    except (KeyError, TypeError):
        return {}


def ensure_mcp(folder, wait=40):
    """OpenCode 后台按文件夹缓存设置：工作区刚建好时它可能还记着“这里没有工具”。没连上就让它重读一遍。"""
    if mcp_status(folder).get("factory") == "connected":
        return True
    api("POST", "/api/location/reload", timeout=30)
    t0 = time.time()
    while time.time() - t0 < wait:
        if mcp_status(folder).get("factory") == "connected":
            return True
        time.sleep(1)
    return False
