# -*- coding: utf-8 -*-
"""一键打开 / 关掉 / 桌面入口。

  python -m lite start        没准备好就先准备（建文件夹、带进旧库定义、写工作区）；打开 OpenCode 后台和工厂服务，用浏览器打开
  python -m lite stop         关掉工厂服务（OpenCode 后台是你自己的，不关）
  python -m lite status       看看各部分开着没有
  python -m lite install      在桌面放“变量库工厂（单人版）”，双击就能打开（Mac 是一个小程序，Windows 是快捷方式）
  python -m lite launch       桌面入口调它：过程记进日志，打不开就弹窗说原因（Windows 用）

浏览器打开的是工厂服务转过来的 OpenCode 网页（http://127.0.0.1:8797/），右边是工厂栏。
打开时不清掉 OpenCode 里已经开着的对话标签，直接回到最近用过的那个工厂对话。
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

from . import agents_md, library, opencode, paths, store

APP_NAME = "变量库工厂（单人版）.app"


def say(msg):
    print(msg, flush=True)


def _listening(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def _pid_file():
    return paths.cfg("server.pid")


def _alive(pid):
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return False
    if paths.WINDOWS:
        # Windows 上 os.kill(pid, 0) 不是“问一声”，而是直接结束进程：改问系统这个进程还在不在
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)           # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259           # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def server_ok():
    """工厂服务开着、而且是这一份单人版（钥匙对得上）。"""
    import urllib.request
    if not _listening(paths.PORT):
        return False
    try:
        k = open(paths.cfg("key"), encoding="utf-8").read().strip()
        req = urllib.request.Request("http://127.0.0.1:%d/lite/api/stamp" % paths.PORT, headers={"X-Lite-Key": k})
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:       # noqa
        return False


def start_server():
    if server_ok():
        return
    if _listening(paths.PORT):
        if paths.WINDOWS:
            raise SystemExit("端口 %d 被别的程序占着。在 PowerShell 里运行 Get-NetTCPConnection -LocalPort %d 看是谁（OwningProcess 是进程号）、关掉它；"
                             "或者换个端口打开：$env:LITE_PORT=%d; .\\start.cmd" % (paths.PORT, paths.PORT, paths.PORT + 1))
        raise SystemExit("端口 %d 被别的程序占着。在终端运行 lsof -nP -iTCP:%d -sTCP:LISTEN 看是谁、关掉它；"
                         "或者换个端口打开：LITE_PORT=%d ./start.sh" % (paths.PORT, paths.PORT, paths.PORT + 1))
    from .server import stable_key
    stable_key()
    log = open(paths.logs("server.log"), "ab")
    env = dict(os.environ, PYTHONPATH=paths.REPO, LITE_HOME=paths.home())
    if paths.WINDOWS:
        # 不弹窗口、和打开它的窗口脱开（关掉命令行窗口，工厂服务照常开着）
        env["PYTHONUTF8"] = "1"
        p = subprocess.Popen(paths.py_cmd("-m", "lite", "serve"), cwd=paths.REPO, env=env, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, creationflags=paths.NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        p = subprocess.Popen(paths.py_cmd("-m", "lite", "serve"), cwd=paths.REPO, env=env, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    with open(_pid_file(), "w", encoding="utf-8") as f:
        f.write(str(p.pid))
    t0 = time.time()
    while time.time() - t0 < 30:
        if server_ok():
            return
        time.sleep(0.3)
    raise SystemExit("工厂服务没起来，日志在 %s" % paths.logs("server.log"))


def start_opencode():
    if not opencode.which():
        raise SystemExit("这台电脑没装 OpenCode（单人版的对话靠它）")
    if not opencode.url(fresh=True):
        say("正在打开 OpenCode 后台……")
        if not opencode.start():
            raise SystemExit("OpenCode 后台没打开，在%s里运行 opencode service start 看看报什么错" % ("PowerShell" if paths.WINDOWS else "终端"))


TOOLS_VERSION = "2"      # 工厂工具（mcp_server）加了、改了名就加一：配置变了，OpenCode 才会重启工具进程、认到新工具


def workspace_config():
    env = {"PYTHONPATH": paths.REPO, "LITE_HOME": paths.home(), "LITE_TOOLS_VERSION": TOOLS_VERSION}
    if paths.WINDOWS:
        env["PYTHONUTF8"] = "1"
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {"servers": {"factory": {"type": "local", "command": paths.py_cmd("-m", "lite.mcp_server"), "environment": env,
                                        "codemode": False}}},
        # 工厂的事都走工厂工具：不许 AI 跑终端命令、改文件、上网（论文和数据只经工厂栏进来，才能追溯）
        "permissions": [
            {"action": "shell", "resource": "*", "effect": "deny"},
            {"action": "edit", "resource": "*", "effect": "deny"},
            {"action": "webfetch", "resource": "*", "effect": "deny"},
            {"action": "websearch", "resource": "*", "effect": "deny"},
            {"action": "factory_*", "resource": "*", "effect": "allow"},
        ],
    }


def setup_workspace():
    ws = paths.workspace()
    os.makedirs(ws, exist_ok=True)
    cfg = "// 变量库工厂（单人版）自动生成：这个文件夹里的 OpenCode 对话接上工厂工具。只有本机路径，没有口令。\n" + \
          json.dumps(workspace_config(), ensure_ascii=False, indent=2) + "\n"
    changed = False
    for name, text in (("opencode.jsonc", cfg), ("AGENTS.md", agents_md.TEXT)):
        p = os.path.join(ws, name)
        old = open(p, encoding="utf-8").read() if os.path.exists(p) else None
        if old != text:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            # 只有接工具的配置变了才要 OpenCode 重读（重读会打断正在跑的对话）；AGENTS.md 新对话自己会读
            changed = changed or name == "opencode.jsonc"
    # 自己是一个 git 仓库：OpenCode 按 git 仓库分项目，工厂的对话单独成一个项目
    if not os.path.isdir(os.path.join(ws, ".git")):
        if not shutil.which("git"):
            raise SystemExit("这台电脑没装 Git（OpenCode 靠它分项目）。%s" % (
                "Windows 上运行 winget install --id Git.Git -e 装上，再重新打开" if paths.WINDOWS else "运行 xcode-select --install 装上，再重新打开"))
        g = ["git", "-C", ws, "-c", "core.hooksPath=" + os.devnull, "-c", "core.autocrlf=false",
             "-c", "user.name=变量库工厂", "-c", "user.email=lite@localhost"]
        for args in (g[:3] + ["init", "-q", "-b", "main"], g + ["add", "-A"], g + ["commit", "-q", "-m", "工作区"]):
            subprocess.run(args, check=True, stdin=subprocess.DEVNULL, creationflags=paths.NO_WINDOW)
    return changed


def prepare():
    paths.ensure()
    with store.ro() as c:
        n = c.execute("SELECT COUNT(*) FROM oldlib").fetchone()[0]
    if not n:
        say("· 第一次打开：带进%s……" % ("内置的变量定义" if paths.PUBLIC else "旧库的变量定义"))
        say("  带进 %d 个" % library.import_cards())
    return setup_workspace()


def landing():
    """打开到哪：最近用过的工厂对话；一个都没有就新建“新对话”。返回网页路径。"""
    rows = opencode.sessions(5)
    sid = rows[0]["id"] if rows else opencode.new_session("新对话")
    return opencode.session_path("http://127.0.0.1:%d" % paths.PORT, sid)


def url(path="/"):
    k = open(paths.cfg("key"), encoding="utf-8").read().strip()
    return "http://127.0.0.1:%d%s#k=%s&open=1" % (paths.PORT, path, k)


def start(browser=True):
    say("· 准备……")
    changed = prepare()
    say("· OpenCode 后台……")
    start_opencode()
    say("· 工厂服务……")
    start_server()
    say("· 接上工厂工具……")
    if changed and opencode.mcp_status(paths.workspace()).get("factory") == "connected" and not opencode.any_busy():
        # 接工具的配置改过、OpenCode 还连着旧的：让它重读（有对话正在干活就不重读，免得打断；下次打开再说）
        opencode.api("POST", "/api/location/reload", timeout=30)
    if not opencode.ensure_mcp(paths.workspace()):
        say("（提醒：OpenCode 里的工厂工具还没连上，可以再双击一次入口）")
    if browser:
        u = url(landing())
        if sys.platform == "darwin":
            subprocess.run(["open", u])
        else:
            import webbrowser
            webbrowser.open(u)
    say("好了：浏览器里左边是和 AI 的对话，右边是工厂栏（右上角“工厂”按钮可以收起、打开）。")


def reset():
    """恢复出厂：删掉全部论文、指标、上传的数据、合成记录、工厂对话（彻底删除，不留备份；导出、示例数据、钥匙不动），
    重新带进旧库定义，新开一个空对话。返回 {path: 新对话的网页路径, deleted_sessions: n}。"""
    if opencode.any_busy():
        raise store.LiteError("有对话里的 AI 正在干活", "等它停下（或在对话里点停止）再恢复出厂")
    sids = opencode.all_workspace_sessions()
    gone = sum(1 for sid in sids if opencode.delete_session(sid))
    for name in ("lite.db", "lite.db-wal", "lite.db-shm"):
        p = paths.lib(name)
        for i in range(20):                 # Windows：别的进程（工厂工具）刚好开着库时删不掉，等一下再删
            try:
                if os.path.exists(p):
                    os.remove(p)
                break
            except PermissionError:
                if i == 19:
                    raise store.LiteError("库文件正被占用，删不掉", "关掉工厂（python -m lite stop）再打开后重试")
                time.sleep(0.5)
    for d in ("papers", "data", "builds", "variables", "oldlib"):
        shutil.rmtree(paths.lib(d), ignore_errors=True)
    paths.ensure()
    n = library.import_cards()
    setup_workspace()
    with store.tx() as c:
        store.log(c, "工厂", "恢复出厂", "删掉了全部论文、指标、数据和 %d 个对话；重新带进旧库定义 %d 个" % (gone, n))
    sid = opencode.new_session("新对话")
    return {"session": sid, "path": opencode.session_path("http://127.0.0.1:%d" % paths.PORT, sid), "deleted_sessions": gone, "oldlib": n}


def stop():
    try:
        pid = int(open(_pid_file(), encoding="utf-8").read().strip())
    except (OSError, ValueError):
        pid = None
    if pid and _alive(pid) and paths.WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, stdin=subprocess.DEVNULL,
                       creationflags=paths.NO_WINDOW)
        for _ in range(30):
            if not _alive(pid):
                break
            time.sleep(0.1)
    elif pid and _alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not _alive(pid):
                break
            time.sleep(0.1)
    say("工厂服务已关（OpenCode 后台没动）。")


def status():
    say("数据放在：%s" % paths.home())
    say("工厂服务（%d）：%s" % (paths.PORT, "开着" if server_ok() else "没开"))
    say("OpenCode 后台：%s" % (opencode.url(fresh=True) or "没开"))
    try:
        ov = store.overview()
        say("论文 %d 篇；指标：%s；旧库定义 %d 个" % (ov["papers"], "、".join("%s %d" % kv for kv in ov["indicators"].items()) or "无", ov["oldlib"]))
    except Exception as e:      # noqa
        say("库：读不了（%s）" % e)


def _q(s):
    return "'" + s.replace("'", "'\\''") + "'"


SHORTCUT = "变量库工厂（单人版）.lnk"

# Windows 桌面快捷方式：用 PowerShell 建（值从环境变量传进去，路径里有空格、中文、引号都不怕）；
# 桌面可能被 OneDrive 挪走，用系统告诉的“桌面”位置
_PS_SHORTCUT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$desk = [Environment]::GetFolderPath('Desktop')
if (-not $desk) { $desk = Join-Path $env:USERPROFILE 'Desktop' }
New-Item -ItemType Directory -Force -Path $desk | Out-Null
$p = Join-Path $desk $env:LITE_LNK_NAME
# WScript.Shell 只认系统“非 Unicode 程序”编码里的字：英文系统上中文名存不了，先用英文名存，再改成中文名
$tmp = Join-Path $desk 'variable-factory-lite.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($tmp)
$s.TargetPath = $env:LITE_LNK_TARGET
$s.Arguments = $env:LITE_LNK_ARGS
$s.WorkingDirectory = $env:LITE_LNK_DIR
$s.Description = '变量库工厂（单人版）'
$s.Save()
Move-Item -LiteralPath $tmp -Destination $p -Force
Write-Output $p
"""


def _install_windows():
    paths.ensure()
    pyw = os.path.join(os.path.dirname(paths.python()), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = paths.python()
    args = "-X utf8 -m lite launch"
    if os.environ.get("LITE_HOME"):
        args += ' --home "%s"' % paths.home()
    env = dict(os.environ, LITE_LNK_NAME=SHORTCUT, LITE_LNK_TARGET=pyw, LITE_LNK_ARGS=args, LITE_LNK_DIR=paths.REPO)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS_SHORTCUT],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60,
                           stdin=subprocess.DEVNULL, creationflags=paths.NO_WINDOW)
        ok, out = r.returncode == 0, (r.stdout or "").strip() or (r.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as e:
        ok, out = False, str(e)
    if not ok:
        say("桌面快捷方式没放成（%s）。不影响使用：双击仓库文件夹里的 start.cmd 打开。" % out[:200])
        return False
    say("放好了：%s（双击打开）" % out.splitlines()[-1])
    return True


def launch(browser=True):
    """桌面入口（Windows 快捷方式）调它：没有命令行窗口，过程写进日志；打不开就弹窗说原因。"""
    paths.ensure()
    log = open(paths.logs("launcher.log"), "w", encoding="utf-8")
    sys.stdout = sys.stderr = log
    try:
        start(browser=browser)
        return
    except SystemExit as e:
        msg = str(e.code) if e.code not in (None, 0) else ""
        if not msg:
            return
    except Exception as e:      # noqa
        import traceback
        traceback.print_exc()
        msg = "%s: %s" % (type(e).__name__, e)
    finally:
        log.flush()
    say("没打开成功：" + msg)
    log.flush()
    if paths.WINDOWS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "没打开成功：\n\n%s\n\n（过程记在 %s）" % (msg[-1500:], paths.logs("launcher.log")),
                                         "变量库工厂（单人版）", 0x10)
    raise SystemExit(1)


def install():
    if paths.WINDOWS:
        return _install_windows()
    paths.ensure()
    log = paths.logs("launcher.log")
    path = ":".join(dict.fromkeys([os.path.dirname(opencode.which() or "/opt/homebrew/bin/opencode"), "/opt/homebrew/bin", "/usr/local/bin",
                                   "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    env = "export PATH=%s;" % _q(path)
    if os.environ.get("LITE_HOME"):
        env += " export LITE_HOME=%s;" % _q(paths.home())
    sh = "%s cd %s && %s -m lite start > %s 2>&1" % (env, _q(paths.REPO), _q(paths.python()), _q(log))
    title = "变量库工厂（单人版）"
    src = "\n".join([
        'display notification "正在打开，稍等几秒……" with title "%s"' % title,
        "try",
        "  do shell script \"%s\"" % sh.replace("\\", "\\\\").replace('"', '\\"'),
        "on error",
        "  set t to do shell script \"tail -n 15 %s\"" % _q(log).replace('"', '\\"'),
        '  display dialog "没打开成功：" & return & return & t buttons {"好"} default button "好" with title "%s"' % title,
        "end try"])
    desk = os.path.expanduser("~/Desktop")
    os.makedirs(desk, exist_ok=True)
    dst = os.path.join(desk, APP_NAME)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    r = subprocess.run(["osacompile", "-o", dst, "-e", src], capture_output=True, text=True)
    if r.returncode != 0:
        say("桌面入口没放成（%s）。不影响使用：在仓库文件夹里运行 ./start.sh 打开。" % (r.stderr or r.stdout).strip()[:200])
        return False
    say("放好了：%s（双击打开）" % dst)
    return True
