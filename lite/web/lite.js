/* 单人版工厂栏：加在 OpenCode 官方网页里（lite/proxy.py 把这个文件插进 OpenCode 网页的 <head>）。
 *
 * 跟着当前对话走：网址里是哪个对话（/session/ses_…），工厂栏就显示那个对话在做的论文。
 * 一个对话只做一篇论文，一篇论文可以有几个对话；几篇论文可以同时在各自的对话里做，互不干扰。
 *
 * 三个标签：当前论文（上传论文 → 挑指标 → 每个指标交数据、看小结、入库）/ 全部论文（含恢复出厂）/ 变量库（筛选、AI 帮我找、导出）。
 * 界面上的名字都查下面的 ST / DST / LABEL 三张表（库里的状态值不变，只改显示）。
 * 人在这里点的“选中”“放行”“先存定义”“入库”就算定了；点完需要 AI 干活的，工厂自动往这个对话里发一句话。
 * 接口都在本机 /lite/api/*，要带钥匙（网址 #k=…，第一次打开时读走，记在本页本地存储里）。
 * OpenCode 的页面由它自己画，这里只在旁边加一栏，不改它的东西；它重画把栏挤掉了就再挂回去。
 */
(function () {
  "use strict";
  if (window.__liteBar) return;
  window.__liteBar = true;

  var KEY = "lite-key", OPEN = "lite-open", WIDTH = "lite-width";
  (function readHash() {
    var p = new URLSearchParams(location.hash.slice(1));
    if (!p.get("k")) return;
    localStorage.setItem(KEY, p.get("k"));
    if (p.get("open") === "1") localStorage.setItem(OPEN, "1");
    history.replaceState(history.state, "", location.pathname + location.search);
  })();
  var key = function () { return localStorage.getItem(KEY) || ""; };

  // ───── 小工具 ─────
  function h(tag, attrs) {
    var el = document.createElement(tag);
    for (var k in attrs || {}) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "on") for (var ev in v) el.addEventListener(ev, v[ev]);
      else if (k === "text") el.textContent = v;
      else if (k === "html") el.innerHTML = v;
      else if (k === "checked" || k === "disabled" || k === "value") el[k] = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) return c.forEach(function (x) { add(el, x); });
    el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  function svg(d) { return '<svg data-slot="icon-svg" width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">' + d + "</svg>"; }
  function icon(d) { return h("span", { html: svg(d), style: "display:inline-flex" }); }
  var I = {
    factory: '<path d="M2.5 17.083H17.5M3.333 17.083V9.583L7.5 12.083V9.583L11.667 12.083V3.75H15.833V17.083" stroke="currentColor" stroke-linecap="square" stroke-linejoin="round"/>',
    refresh: '<path d="M15.833 7.917A6.25 6.25 0 1 0 16.25 12.5M15.833 3.75V7.917H11.667" stroke="currentColor" stroke-linecap="square"/>',
    close: '<path d="M5 5L15 15M15 5L5 15" stroke="currentColor" stroke-linecap="square"/>',
    search: '<path d="M8.75 15A6.25 6.25 0 1 0 8.75 2.5a6.25 6.25 0 0 0 0 12.5ZM13.333 13.333L17.083 17.083" stroke="currentColor" stroke-linecap="square"/>',
    chev: '<path d="M7.917 5L12.917 10L7.917 15" stroke="currentColor" stroke-linecap="square"/>',
    back: '<path d="M12.083 5L7.083 10L12.083 15" stroke="currentColor" stroke-linecap="square"/>',
    upload: '<path d="M10 13.333V3.75M10 3.75L6.25 7.5M10 3.75L13.75 7.5M3.75 12.5V16.25H16.25V12.5" stroke="currentColor" stroke-linecap="square"/>',
    doc: '<path d="M11.667 2.917H4.583V17.083H15.417V6.667L11.667 2.917ZM11.667 2.917V6.667H15.417M7.083 10.417H12.917M7.083 13.333H11.25" stroke="currentColor"/>',
    flow: '<path d="M5 6.667A1.667 1.667 0 1 0 5 3.333a1.667 1.667 0 0 0 0 3.334ZM15 16.667A1.667 1.667 0 1 0 15 13.333a1.667 1.667 0 0 0 0 3.334ZM5 6.667V10.833C5 12.214 6.12 13.333 7.5 13.333H13.333" stroke="currentColor"/>',
    library: '<path d="M3.333 3.333H6.667V16.667H3.333ZM8.333 3.333H11.667V16.667H8.333ZM13.081 4.167L16.25 3.333L18.75 15.833L15.581 16.667Z" stroke="currentColor" stroke-linejoin="round"/>',
    list: '<path d="M7.5 5H16.667M7.5 10H16.667M7.5 15H16.667M3.333 5H4.167M3.333 10H4.167M3.333 15H4.167" stroke="currentColor" stroke-linecap="square"/>',
    sparkle: '<path d="M9.167 3.333L10.417 7.917L15 9.167L10.417 10.417L9.167 15L7.917 10.417L3.333 9.167L7.917 7.917ZM15 2.917L15.417 4.167L16.667 4.583L15.417 5L15 6.25L14.583 5L13.333 4.583L14.583 4.167Z" stroke="currentColor" stroke-linejoin="round"/>',
    check: '<path d="M10 17.5A7.5 7.5 0 1 0 10 2.5a7.5 7.5 0 0 0 0 15ZM6.875 10.208L8.958 12.292L13.125 8.125" stroke="currentColor" stroke-linecap="square"/>',
    ext: '<path d="M8.333 4.167H4.167V15.833H15.833V11.667M11.667 3.333H16.667V8.333M16.667 3.333L9.167 10.833" stroke="currentColor" stroke-linecap="square"/>',
    box: '<path d="M2.917 6.25L10 2.917L17.083 6.25V13.75L10 17.083L2.917 13.75ZM2.917 6.25L10 9.583L17.083 6.25M10 9.583V17.083" stroke="currentColor" stroke-linejoin="round"/>',
    message: '<path d="M3.333 4.167H16.667V13.333H8.75L5.417 16.25V13.333H3.333ZM6.667 7.917H13.333M6.667 10.417H10.833" stroke="currentColor" stroke-linejoin="round"/>'
  };
  function btn(label, variant, onclick, opts) {
    opts = opts || {};
    return h("button", { type: "button", "data-component": "button-v2", "data-variant": variant || "neutral", "data-size": opts.size || "normal",
      "data-icon": opts.icon ? true : null, title: opts.title || null, disabled: opts.disabled || null, on: { click: onclick } },
      opts.icon ? icon(opts.icon) : null, h("span", { text: label }));
  }
  function iconBtn(d, label, onclick) {
    return h("button", { type: "button", "aria-label": label, title: label, "data-component": "icon-button-v2", "data-size": "large",
      "data-variant": "ghost-muted", "class": "shrink-0", on: { click: onclick }, html: svg(d) });
  }
  // 要再确认一下的按钮：点一下按钮变成“再点一下：…”，6 秒内再点才生效（不用浏览器弹窗）
  var armed = {};
  function sureBtn(id, label, ask, fn, variant) {
    var on = armed[id] && Date.now() - armed[id] < 6000;
    return btn(on ? "再点一下：" + ask : label, on ? "contrast" : (variant || "ghost-muted"), function () {
      if (armed[id] && Date.now() - armed[id] < 6000) { delete armed[id]; fn(); return; }
      armed[id] = Date.now(); render(); setTimeout(function () { if (armed[id]) { delete armed[id]; render(); } }, 6100);
    }, { size: "small" });
  }
  function pill(text, tone) { return h("span", { "class": "fb-pill", "data-tone": tone || null, text: text }); }
  function link(text, href, ic) { return h("a", { "class": "lt-link", href: href, target: "_blank", rel: "noopener" }, text, ic ? icon(ic) : null); }
  function linkBtn(text, fn, ic) { return h("button", { type: "button", "class": "lt-link", on: { click: fn } }, ic ? icon(ic) : null, text); }
  var toastTimer;
  function toast(msg, ms) {
    var t = document.getElementById("lt-toast") || document.body.appendChild(h("div", { id: "lt-toast", role: "status" }));
    t.textContent = msg;
    t.setAttribute("data-show", "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.removeAttribute("data-show"); }, ms || 3500);
  }
  function fmt(x) {
    if (x == null || x === "") return "—";
    var v = Number(x);
    if (!isFinite(v)) return String(x);
    if (v === 0) return "0";
    if (Math.abs(v) >= 1e6 || Math.abs(v) < 1e-3) return v.toPrecision(3);
    return String(+v.toFixed(4));
  }
  function int(x) { return x == null ? "—" : Number(x).toLocaleString("zh-CN"); }

  // ───── 界面上的名字（规则：对象只叫 论文 / 候选指标 / 指标 / 数据 / 变量库 / 对话；状态写“等 AI… / 等你… / 已…”；按钮动词开头）─────
  var ST = { "待列数据": "等 AI 列数据", "待交数据": "等你交数据", "待合成": "等 AI 合成", "待入库": "等你入库", "已入库": "已入库", "等数据": "只存定义" };
  var ST_TONE = { "待列数据": "", "待交数据": "warning", "待合成": "info", "待入库": "warning", "已入库": "success", "等数据": "" };
  var ST_ORDER = ["待交数据", "待入库", "待列数据", "待合成", "已入库", "等数据"];      // 等你处理的排前面
  var DST = { "未交": "还没交", "通过": "通过", "没通过": "没通过", "放行": "已放行" };
  var DST_TONE = { "未交": "", "通过": "success", "没通过": "danger", "放行": "warning" };
  var LABEL = {
    tabLine: "当前论文", tabPapers: "全部论文", tabLib: "变量库",
    remind: "提醒 AI", drop: "不做了", defer: "只存定义", resume: "继续交数据", upload: "上传数据", reupload: "重新上传",
    remap: "按对应重新校验", override: "放行", dataHelp: "让 AI 看看", admit: "入库", explain: "让 AI 解读", rebuild: "让 AI 重做",
    more: "让 AI 补漏", choose: "确定选择", newPaper: "做新论文", openSession: "打开对话", moveHere: "移到这个对话",
    moreSession: "再开一个对话", openPdf: "打开 PDF", openPage: "打开这一页", aiFind: "AI 帮我找", exportSel: "导出所选",
    importData: "带入数据", reset: "恢复出厂（清空全部）"
  };
  var GROUPS = [["rec", "AI 推荐"], ["other", "其他指标"], ["common", "常用指标（各篇都用）"], ["lib", "变量库已有"]];

  // ───── 公式：KaTeX 排版（lite/web/katex/，本机文件）；没装好或写错就显示原文字 ─────
  var katexState = "";
  function loadKatex() {
    if (katexState) return;
    katexState = "loading";
    document.head.appendChild(h("link", { rel: "stylesheet", href: "/lite/web/katex/katex.min.css" }));
    var sc = h("script", { src: "/lite/web/katex/katex.min.js" });
    sc.onload = function () { katexState = "ok"; render(); };
    sc.onerror = function () { katexState = "fail"; };
    document.head.appendChild(sc);
  }
  function tex(src, display, fallback) {
    src = (src || "").trim();
    var el = h("span", { "class": display ? "lt-tex lt-tex-d" : "lt-tex" });
    if (!src) { el.textContent = fallback || ""; return el; }
    if (window.katex) {
      try { window.katex.render(src, el, { displayMode: !!display, throwOnError: true, strict: "ignore", output: "html" }); return el; }
      catch (e) { el.textContent = fallback || src; el.title = "公式写法有误，显示原文字"; return el; }
    }
    loadKatex();
    el.textContent = fallback || src;
    return el;
  }
  // 抽屉：长文字默认只显示几行，点“展开”看全文
  function drawer(key, text, opts) {
    opts = opts || {};
    text = text == null ? "" : String(text);
    var lines = opts.lines || 2, limit = opts.limit || lines * 46;
    var cls = "lt-drawer " + (opts.cls || "");
    if (text.length <= limit) return h(opts.tag || "div", { "class": cls, text: text });
    var open = !!S.more["dr-" + key];
    return h(opts.tag || "div", { "class": cls },
      h("span", { "class": open ? "" : "lt-clamp", style: open ? null : "-webkit-line-clamp:" + lines, text: text }),
      h("button", { type: "button", "class": "lt-drawer-t", on: { click: function (e) { e.stopPropagation(); S.more["dr-" + key] = !open; render(); } } },
        open ? "收起 ▴" : "展开 ▾"));
  }
  function withSession(b) { b = b || {}; b.session = currentSession(); return b; }

  // ───── 接口 ─────
  function api(path, body, raw) {
    var opt = { method: body === undefined && !raw ? "GET" : "POST", headers: { "X-Lite-Key": key() }, credentials: "same-origin" };
    if (raw) opt.body = raw;
    else if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) {
          var e = d.error || {};
          throw new Error((e.message || "工厂服务出错（" + r.status + "）") + (e.what_to_do ? "。" + e.what_to_do : ""));
        }
        return d;
      });
    });
  }
  function act(path, body, okMsg) {
    S.busy = true;
    return api(path, body).then(function (d) { if (okMsg) toast(okMsg); return refresh(true).then(function () { return d; }); },
      function (e) { toast(e.message, 6000); throw e; }).finally(function () { S.busy = false; });
  }
  function ask(what, id, msg) {
    return api("/lite/api/ask", withSession({ what: what, id: id })).then(function () { toast(msg || "已发给对话里的 AI"); }, function (e) { toast(e.message, 6000); });
  }

  // ───── 当前对话 ─────
  function currentSession() { var m = location.pathname.match(/\/session\/(ses_[A-Za-z0-9]+)/); return m ? m[1] : ""; }
  function sessionPath(sid) {
    var m = location.pathname.match(/^\/server\/([^/]+)\//);
    var srv = m ? m[1] : btoa(location.origin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return "/server/" + srv + "/session/" + sid;
  }
  function goSession(sid) {
    if (!sid || sid === currentSession()) return;
    replaceDraftTab(sid);
    location.assign(sessionPath(sid));
  }
  // 在 OpenCode 的“新对话”草稿页上传论文时，工厂替你新开了对话：把顶上那个空草稿标签换成新对话，免得留一个空标签
  function replaceDraftTab(sid) {
    var draft = new URLSearchParams(location.search).get("draftId");
    if (location.pathname !== "/new-session" || !draft) return;
    var k = "opencode.window.browser.dat:tabs";
    try {
      var tabs = JSON.parse(localStorage.getItem(k) || "[]"), have = tabs.some(function (t) { return t.sessionId === sid; });
      tabs = tabs.map(function (t) { return t.type === "draft" && t.draftID === draft ? (have ? null : { type: "session", server: location.origin, sessionId: sid }) : t; })
        .filter(Boolean);
      localStorage.setItem(k, JSON.stringify(tabs));
    } catch (e) {}
  }

  // 浏览器还没登录 OpenCode：一次性配对链接帮人登录
  function ensureLogin() {
    if (!key()) return;
    fetch("/api/session?limit=1", { credentials: "same-origin" }).then(function (r) {
      if (r.status !== 401) return;
      var last = +sessionStorage.getItem("lite-pair") || 0;
      if (Date.now() - last < 30000) return;
      sessionStorage.setItem("lite-pair", String(Date.now()));
      sessionStorage.setItem("lite-after-login", location.pathname);   // 登录完 OpenCode 会回首页，记下原来要去的对话
      return api("/lite/api/connect").then(function (c) { if (c.path) location.replace(c.path); });
    }).catch(function () {});
  }
  function afterLogin() {
    var back = sessionStorage.getItem("lite-after-login");
    if (!back || location.pathname !== "/") return;
    sessionStorage.removeItem("lite-after-login");
    if (/\/session\/ses_/.test(back)) location.replace(back);
  }

  // ───── 状态 ─────
  var S = { open: localStorage.getItem(OPEN) !== "0", tab: "line", session: "", pick: {}, more: {}, data: null, err: null,
    lib: null, libQ: "", libF: {}, libSel: {}, libItem: null, libShow: 60, papers: null, rev: -1, busy: false, draft: {}, hideSearch: "" };

  var panel, body, tabsEl, titleBtn;
  function build() {
    panel = h("aside", { id: "lt-panel", "aria-label": "工厂栏", hidden: !S.open });
    var w = +localStorage.getItem(WIDTH);
    if (w) panel.style.setProperty("--fb-w", w + "px");
    var grip = h("div", { "class": "fb-resize", title: "拖动改宽度" });
    grip.addEventListener("pointerdown", function (e) {
      var x0 = e.clientX, w0 = panel.getBoundingClientRect().width;
      grip.setPointerCapture(e.pointerId);
      var move = function (ev) { panel.style.setProperty("--fb-w", Math.max(340, Math.min(window.innerWidth - 420, w0 - (ev.clientX - x0))) + "px"); };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", function () { grip.removeEventListener("pointermove", move); localStorage.setItem(WIDTH, String(Math.round(panel.getBoundingClientRect().width))); }, { once: true });
    });
    tabsEl = h("div", { "class": "fb-tabs", role: "tablist" });
    body = h("div", { "class": "fb-body" });
    panel.append(grip, h("div", { "class": "fb-head" }, tabsEl,
      iconBtn(I.refresh, "刷新", function () { S.lib = null; S.papers = null; refresh(true); }),
      iconBtn(I.close, "收起工厂栏", function () { setOpen(false); })), body);
    titleBtn = h("div", { id: "lt-titlebar" },
      h("button", { type: "button", "data-component": "button-v2", "data-variant": "ghost-muted", "data-size": "normal", "data-icon": true,
        title: "工厂栏", "aria-label": "工厂栏", on: { click: function () { setOpen(!S.open); } } }, icon(I.factory), h("span", { text: "工厂" })));
  }
  function setOpen(v) {
    S.open = v;
    localStorage.setItem(OPEN, v ? "1" : "0");
    panel.hidden = !v;
    var b = titleBtn.querySelector("button");
    if (v) b.setAttribute("data-expanded", ""); else b.removeAttribute("data-expanded");
    if (v) refresh(true);
  }
  function mount() {
    if (!panel) return;
    var header = document.querySelector('header[data-slot="titlebar-v2"]');
    if (header && !header.contains(titleBtn)) {
      var row = header.firstElementChild, right = row && row.lastElementChild;
      if (row) row.insertBefore(titleBtn, right && right !== titleBtn ? right : null);
    }
    var main = document.querySelector("#root main"), region = main && main.parentElement;
    if (region && panel.parentElement !== region) region.appendChild(panel);
  }
  function setTabs() {
    tabsEl.textContent = "";
    [["line", LABEL.tabLine, I.flow], ["papers", LABEL.tabPapers, I.list], ["library", LABEL.tabLib, I.library]].forEach(function (t) {
      tabsEl.appendChild(h("button", { type: "button", role: "tab", "class": "fb-tab", "aria-selected": String(S.tab === t[0]),
        on: { click: function () { S.tab = t[0]; S.libItem = null; render(); refresh(true); } } }, icon(t[2]), t[1]));
    });
  }

  // ───── 取数据、画 ─────
  var loading = null, lastSig = "";
  function refresh(force) {
    if (!S.open || !key()) return Promise.resolve();
    if (loading && !force) return loading;
    var sid = currentSession();
    var p;
    if (S.tab === "line") p = api("/lite/api/view?session=" + encodeURIComponent(sid)).then(function (d) { S.data = d; S.session = sid; });
    else if (S.tab === "papers") p = api("/lite/api/papers").then(function (d) { S.papers = d; });
    else if (S.libItem) p = api("/lite/api/item?id=" + encodeURIComponent(S.libItem)).then(function (d) { S.libDetail = d; });
    else p = api("/lite/api/library?" + libQuery()).then(function (d) { S.lib = d; });
    // 拿到的东西和上次一样就不重画（别的对话在干活时库一直在变，重画会打断正在点的按钮、正在填的字）
    loading = p.then(function () {
      var sig = JSON.stringify([S.tab, S.libItem, S.tab === "line" ? S.data : S.tab === "papers" ? S.papers : S.libItem ? S.libDetail : S.lib]);
      if (!force && sig === lastSig && !S.err) return;
      lastSig = sig; S.err = null; render();
    }, function (e) { S.err = e.message; render(); }).finally(function () { loading = null; });
    return loading;
  }
  function keepFocus(fn) {
    var a = document.activeElement, id = a && a.getAttribute && a.getAttribute("data-keep"), st = a && a.selectionStart;
    fn();
    if (id) { var n = body.querySelector('[data-keep="' + id + '"]'); if (n) { n.focus(); try { n.setSelectionRange(st, st); } catch (e) {} } }
  }
  function render() {
    if (!panel || panel.hidden) return;
    setTabs();
    var top = body.scrollTop;
    keepFocus(function () {
      body.textContent = "";
      if (!key()) return add(body, h("div", { "class": "fb-note", "data-tone": "danger" }, "工厂栏没拿到钥匙：请双击桌面上的“变量库工厂（单人版）”重新打开。"));
      if (S.err) add(body, h("div", { "class": "fb-note", "data-tone": "danger", style: "margin-bottom:10px" }, S.err));
      if (S.tab === "line") add(body, S.data ? lineView(S.data) : spinner("正在读取…"));
      else if (S.tab === "papers") add(body, S.papers ? papersView(S.papers) : spinner("正在读取…"));
      else add(body, S.libItem ? (S.libDetail && S.libDetail.id === S.libItem ? libDetail(S.libDetail) : spinner("正在读取…")) : (S.lib ? libView(S.lib) : spinner("正在读取…")));
    });
    body.scrollTop = top;
  }
  function spinner(t) { return h("div", { "class": "lt-wait" }, h("span", { "class": "fb-spin" }), h("div", {}, t)); }
  function wait(title, sub, extra) {
    return h("div", { "class": "lt-wait" }, h("span", { "class": "fb-spin" }), h("div", { "class": "fb-main" }, h("b", { text: title }), sub ? h("div", { "class": "lt-small", style: "margin-top:2px", text: sub }) : null, extra || null));
  }
  function sec(title, n, right) {
    return h("div", { "class": "fb-sec" }, h("span", { "class": "fb-sec-t", text: title }), n != null ? h("span", { "class": "fb-sec-n", text: String(n) }) : null,
      h("span", { "class": "fb-grow" }), right || null);
  }

  // 选文件（隐藏的 input）
  function pickFile(accept, cb) {
    var inp = h("input", { type: "file", accept: accept, style: "display:none" });
    inp.addEventListener("change", function () { if (inp.files[0]) cb(inp.files[0]); inp.remove(); });
    document.body.appendChild(inp);
    inp.click();
  }
  // 拖文件进来：OpenCode 自己在整页上接拖进来的文件（放进聊天输入框）。我们在最外层先接住拖到工厂栏上传区的文件，
  // 不让它再传给 OpenCode（不然文件会同时被塞进聊天框）。
  function dropTarget(el, accept, cb) { el.__ltDrop = cb; el.setAttribute("data-lt-drop", ""); return el; }
  function zoneOf(e) { var t = e.target; return t && t.closest ? t.closest("[data-lt-drop]") : null; }
  ["dragenter", "dragover"].forEach(function (ev) {
    window.addEventListener(ev, function (e) {
      var z = zoneOf(e);
      document.querySelectorAll("[data-lt-drop][data-over]").forEach(function (x) { if (x !== z) x.removeAttribute("data-over"); });
      if (!z) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      z.setAttribute("data-over", "");
    }, true);
  });
  window.addEventListener("dragleave", function (e) { var z = zoneOf(e); if (z && !z.contains(e.relatedTarget)) z.removeAttribute("data-over"); }, true);
  window.addEventListener("drop", function (e) {
    var z = zoneOf(e);
    if (!z) return;
    e.preventDefault(); e.stopImmediatePropagation();
    z.removeAttribute("data-over");
    var dt = e.dataTransfer, f = dt && (dt.files[0] || (dt.items && dt.items[0] && dt.items[0].getAsFile()));
    if (f) z.__ltDrop(f); else toast("没拿到文件，请点上传区选文件");
  }, true);

  // ───── 上传论文 ─────
  function uploadPaper(file) {
    if (!/\.pdf$/i.test(file.name)) return toast("只能上传 PDF 文件", 5000);
    var sid = currentSession();
    S.uploading = file.name; render();
    api("/lite/api/upload-paper?session=" + encodeURIComponent(sid) + "&name=" + encodeURIComponent(file.name), undefined, file).then(function (r) {
      S.uploading = null;
      if (r.dup) { S.dup = r; render(); return; }
      if (r.new_session || r.session !== sid) {
        toast(r.because_busy ? "一个对话只做一篇论文：已给 " + r.paper + " 新开一个对话，正在切过去…" : "已上传，正在打开这篇论文的对话…", 6000);
        sessionStorage.setItem("lite-open-now", "1");
        return goSession(r.session);
      }
      toast("已上传 " + r.paper + "，AI 开始读论文、提取指标", 5000);
      refresh(true);
    }, function (e) { S.uploading = null; render(); toast(e.message, 6000); });
  }
  function uploadZone(big) {
    var z = h("div", { "class": "lt-drop" + (big ? "" : " lt-drop-sm"), role: "button", tabindex: "0", on: { click: function () { pickFile(".pdf,application/pdf", uploadPaper); } } },
      icon(I.upload),
      h("div", {}, h("div", { "class": "lt-drop-t", text: S.uploading ? "正在上传 " + S.uploading + "…" : (big ? "上传论文 PDF" : "做另一篇论文（会新开一个对话）") }),
        big ? h("div", { "class": "lt-small", text: "点这里选文件，或把 PDF 拖进来" }) : null));
    return dropTarget(z, ".pdf", uploadPaper);
  }
  function dupNote() {
    var d = S.dup;
    if (!d) return null;
    var here = currentSession();
    return h("div", { "class": "fb-note", style: "margin-top:10px" },
      h("div", {}, "这篇论文之前上传过：", h("b", { text: d.paper + "《" + d.title + "》" }), "。"),
      h("div", { "class": "lt-row" },
        d.session && d.session !== here ? btn(LABEL.openSession, "contrast", function () { S.dup = null; goSession(d.session); }, { size: "small" }) : null,
        d.session !== here ? btn(LABEL.moveHere, "outline", function () { S.dup = null; bindHere(d.paper); }, { size: "small" }) : null,
        btn("知道了", "ghost-muted", function () { S.dup = null; render(); }, { size: "small" })));
  }
  function bindHere(pid) {
    var sid = currentSession();
    api("/lite/api/bind", { paper: pid, session: sid, hello: true }).then(function (r) {
      if (r.session !== sid) { toast("这个对话已经在做别的论文，已给 " + pid + " 新开一个对话"); sessionStorage.setItem("lite-open-now", "1"); return goSession(r.session); }
      toast("已在这个对话里做 " + pid); refresh(true);
    }, function (e) { toast(e.message, 6000); });
  }
  function moreSession(pid) {
    api("/lite/api/paper-session", { paper: pid }).then(function (r) { toast("已给 " + pid + " 再开一个对话"); sessionStorage.setItem("lite-open-now", "1"); goSession(r.session); },
      function (e) { toast(e.message, 6000); });
  }
  function newLine() {
    api("/lite/api/new-session", { title: "新对话" }).then(function (r) { sessionStorage.setItem("lite-open-now", "1"); goSession(r.session); },
      function (e) { toast(e.message, 6000); });
  }

  // ───── 当前论文 ─────
  function track(steps, now, cls) {
    // steps: [名字, …]；now: 正在第几步（从 0 数；>= 长度 = 全做完）
    return h("div", { "class": "lt-track " + (cls || ""), style: "grid-template-columns:repeat(" + steps.length + ",1fr)" }, steps.map(function (s, i) {
      return h("div", { "data-st": i < now ? "done" : i === now ? "now" : "" }, h("i"), s);
    }));
  }
  function lineView(d) {
    var out = [];
    var sid = currentSession();
    if (sid && d.session_known && !d.session_ok) {
      out.push(h("div", { "class": "fb-note" }, h("div", { text: "这个对话不在工厂的工作区里，AI 用不了工厂工具。" }),
        h("div", { "class": "lt-row" }, btn(LABEL.newPaper, "contrast", newLine, { size: "small" }))));
      return out;
    }
    if (d.is_assistant) {
      out.push(h("div", { "class": "fb-note" }, h("div", { text: "这是“变量库助手”对话：专门帮你在变量库里找变量，不做论文。" }),
        h("div", { "class": "lt-row" }, btn("去变量库", "contrast", function () { S.tab = "library"; S.libItem = null; render(); refresh(true); }, { size: "small" }),
          btn(LABEL.newPaper, "outline", newLine, { size: "small" }))));
      return out;
    }
    if (!d.paper) {
      out.push(h("div", { "class": "lt-h", text: "上传一篇论文开始" }));
      out.push(h("p", { "class": "lt-p", text: "一个对话做一篇论文。AI 把论文里的指标找出来，你挑要做的、交数据，AI 合成，你点入库。几篇论文可以各开一个对话同时做。" }));
      out.push(h("div", { "class": "lt-gap" }), uploadZone(true), dupNote());
      out.push(h("ol", { "class": "lt-howto" },
        h("li", {}, h("b", { text: "上传论文" }), "：PDF，能选中文字的那种"),
        h("li", {}, h("b", { text: "挑指标" }), "：AI 列出论文里的指标、推荐几个有新意的；勾了就算认可定义"),
        h("li", {}, h("b", { text: "交数据" }), "：AI 说要哪些原始数据，你上传，工厂自动校验；凑不齐可以只存定义"),
        h("li", {}, h("b", { text: "入库" }), "：AI 写代码合成、给你小结，你点“入库”")));
      if (d.others.length) {
        out.push(sec("别的论文", d.others.length));
        out.push(h("div", { "class": "fb-list" }, d.others.slice(0, 8).map(function (p) { return paperRow(p, true); })));
      }
      return out;
    }
    var P = d.paper, p = P.paper;
    var nsess = (p.sessions || []).length;
    out.push(h("div", { "class": "fb-card lt-paper" },
      h("div", { "class": "fb-line" }, h("span", { "class": "fb-id", text: p.id }), h("span", { "class": "lt-small", text: p.pages + " 页" + (nsess > 1 ? " · " + nsess + " 个对话" : "") }),
        h("span", { "class": "fb-grow" }), link(LABEL.openPdf, "/lite/pdf/" + p.id, I.ext)),
      h("div", { "class": "lt-paper-t", text: p.title }),
      p.summary ? drawer("sum-" + p.id, p.summary, { cls: "lt-body-muted", lines: 2 }) : null,
      track(["上传论文", "AI 提取指标", "挑指标"], p.stage === "提取中" ? 1 : p.stage === "待挑选" ? 2 : 3),
      p.stage === "已挑选" ? indProgress(p) : h("div", { "class": "lt-now", text: "现在：" + p.label }),
      h("div", { "class": "lt-row", style: "margin-top:10px" }, linkBtn(LABEL.moreSession, function () { moreSession(p.id); }, I.message),
        h("span", { "class": "lt-small", text: "（同一篇论文换个对话接着做，比如对话太长了）" }))));
    if (p.scanned) out.push(h("div", { "class": "fb-note", "data-tone": "danger", style: "margin-top:10px", text: "这份 PDF 几乎没有文字（可能是扫描版），AI 读不出原文。请换一份能选中文字的 PDF。" }));
    if (P.indicators.length) {
      // 选过指标以后，指标卡放在上面（等你处理的排前面），候选列表收起来放在下面
      out.push(sec("选中的指标", P.indicators.length));
      P.indicators.slice().sort(function (a, b) { return ST_ORDER.indexOf(a.state) - ST_ORDER.indexOf(b.state); }).forEach(function (ind) { out.push(indCard(ind)); });
      var ck = "candsec-" + p.id, left = P.candidates.filter(function (c) { return c.state === "待挑选"; }).length;
      out.push(h("div", { "class": "lt-gap" }));
      out.push(grpHead(ck, "候选指标", P.candidates.length + " 个，还有 " + left + " 个没选", true));
      if (S.more[ck]) out.push(candSection(P));
    } else out.push(candSection(P));
    out.push(h("div", { "class": "lt-gap" }), uploadZone(false), dupNote());
    return out;
  }
  // 指标进度：按状态分色的一根横条 + 计数（等你处理的加粗）
  function indProgress(p) {
    var c = p.counts || {}, total = p.n_indicators || 1;
    var order = ["已入库", "等数据", "待入库", "待合成", "待交数据", "待列数据"];
    return h("div", { "class": "lt-prog-w" },
      h("div", { "class": "lt-prog-h" }, h("b", { text: "指标进度" }), h("span", { "class": "lt-small", text: "已做完 " + p.n_done + " / " + p.n_indicators + "（入库或只存定义）" })),
      h("div", { "class": "lt-prog" }, order.filter(function (k) { return c[k]; }).map(function (k) {
        return h("i", { "data-st": k, style: "flex:" + c[k] / total, title: ST[k] + " " + c[k] + " 个" });
      })),
      h("div", { "class": "lt-legend" }, ST_ORDER.filter(function (k) { return c[k]; }).map(function (k) {
        return h("span", { "data-st": k, "data-mine": /^等你/.test(ST[k]) ? "" : null }, h("i"), ST[k] + " ", h("b", { text: String(c[k]) }));
      })));
  }
  function paperRow(p, canBind) {
    return h("div", { "class": "fb-row" },
      h("span", { "class": "fb-row-ic" }, icon(I.doc)),
      h("div", { "class": "fb-main" }, h("div", { "class": "fb-title", text: p.title }), h("div", { "class": "fb-sub", text: p.id + " · " + p.label })),
      p.session ? btn(LABEL.openSession, "ghost-muted", function () { goSession(p.session); }, { size: "small" }) : null,
      canBind && currentSession() && !p.session ? btn(LABEL.moveHere, "ghost-muted", function () { bindHere(p.id); }, { size: "small" }) : null);
  }
  // 可折叠的分组标题：整行可点，右边箭头
  function grpHead(k, title, n, card) {
    var open = !!S.more[k];
    return h("button", { type: "button", "class": "lt-grp" + (card ? " lt-grp-card" : ""), "aria-expanded": String(open), on: { click: function () { S.more[k] = !open; render(); } } },
      h("span", { "class": "lt-grp-t", text: title }), n != null ? h("span", { "class": "lt-grp-n", text: String(n) }) : null,
      h("span", { "class": "fb-grow" }), h("span", { "class": "lt-grp-ar", text: open ? "收起" : "展开" }),
      h("span", { "class": "fb-chev", style: open ? "transform:rotate(90deg)" : null }, icon(I.chev)));
  }

  // 候选指标
  function candGroup(c) { return c.recommend ? "rec" : c.in_library ? "lib" : c.common ? "common" : "other"; }
  function candSection(P) {
    var cs = P.candidates, pid = P.paper.id;
    var wrap = [];
    if (!cs.length) {
      wrap.push(sec("候选指标"));
      wrap.push(wait("AI 正在看论文目录、精读要紧的几页、提取指标……", "一般一两分钟。可以在左边对话里看它的进度。",
        h("div", { "class": "lt-row" }, btn(LABEL.remind, "ghost-muted", function () { ask("extract", pid, "已提醒 AI 提取指标"); }, { size: "small" }))));
      return wrap;
    }
    var open = cs.filter(function (c) { return c.state === "待挑选"; });
    var picks = S.pick[pid] || (S.pick[pid] = {});
    if (!P.indicators.length) wrap.push(sec("候选指标", cs.length, linkBtn(LABEL.more, function () { ask("more", pid, "已请 AI 补充漏掉的指标"); })));
    else wrap.push(h("div", { style: "text-align:right;margin:6px 2px 0" }, linkBtn(LABEL.more, function () { ask("more", pid, "已请 AI 补充漏掉的指标"); })));
    wrap.push(h("div", { "class": "lt-small", style: "margin:-2px 2px 8px" }, "点名字看定义、公式、原文和页码；勾选要做的，再点下面“确定选择”。"));
    GROUPS.forEach(function (g) {
      var list = cs.filter(function (c) { return candGroup(c) === g[0]; });
      if (!list.length) return;
      var k = "grp-" + pid + "-" + g[0];
      if (S.more[k] == null) S.more[k] = g[0] === "rec";          // 默认只展开 AI 推荐
      var nPick = list.filter(function (c) { return picks[c.id]; }).length;
      wrap.push(grpHead(k, g[1], list.length + (nPick ? " · 勾了 " + nPick : "")));
      if (S.more[k]) wrap.push(h("div", { "class": "fb-list lt-grp-body" }, list.map(function (c) { return candRow(c, picks); })));
    });
    if (open.length) {
      var n = Object.keys(picks).filter(function (k) { return picks[k]; }).length;
      wrap.push(h("div", { "class": "lt-sticky" },
        h("span", { "class": "lt-small", text: n ? "选中 " + n + " 个：选中就算认可了它的定义" : "还没勾选" }),
        btn(LABEL.choose + "（" + n + "）", "contrast", function () {
          var ids = Object.keys(picks).filter(function (k) { return picks[k]; });
          act("/lite/api/choose", withSession({ paper: pid, candidates: ids }), "已选中 " + ids.length + " 个，AI 开始列所需数据").then(function () { S.pick[pid] = {}; S.more["candsec-" + pid] = false; render(); body.scrollTop = 0; });
        }, { disabled: !n })));
    }
    return wrap;
  }
  function candRow(c, picks) {
    var openK = "c-" + c.id, isOpen = !!S.more[openK], chosen = c.state !== "待挑选";
    var tags = [];
    if (c.in_library) tags.push(pill("库里有 " + c.in_library, "info"));
    if (chosen) tags.push(pill("已选 " + c.indicator, "success"));
    var cb = h("input", { type: "checkbox", checked: chosen || !!picks[c.id], disabled: chosen, title: chosen ? "已经选中" : "勾选要做的",
      on: { click: function (e) { e.stopPropagation(); }, change: function (e) { picks[c.id] = e.target.checked; render(); } } });
    return h("div", { "class": "lt-cand", "data-chosen": chosen ? "" : null },
      h("div", { "class": "lt-cand-row", on: { click: function () { S.more[openK] = !isOpen; render(); } } }, cb,
        h("div", { "class": "fb-main" },
          h("div", { "class": "lt-cand-l1" }, h("span", { "class": "lt-cand-n", text: c.name }),
            c.symbol_tex ? tex(c.symbol_tex, false) : c.name_en ? h("span", { "class": "lt-cand-en", text: c.name_en }) : null,
            h("span", { "class": "lt-tags" }, h("span", { "class": "lt-role", text: c.role }), tags)),
          c.recommend && c.reason ? h("div", { "class": "lt-cand-why" }, h("b", { text: "推荐理由 " }), c.reason) : null,
          !isOpen ? h("div", { "class": "lt-cand-def lt-clamp", style: "-webkit-line-clamp:1", text: c.definition }) : null),
        h("span", { "class": "fb-chev", style: isOpen ? "transform:rotate(90deg)" : null }, icon(I.chev))),
      isOpen ? h("div", { "class": "lt-cand-more" }, defBlock(c)) : null);
  }
  function defBlock(c) {
    var k = c.id;
    return h("dl", { "class": "lt-kv" },
      h("dt", { text: "定义" }), h("dd", {}, drawer("def-" + k, c.definition, { lines: 3 })),
      h("dt", { text: "公式" }), h("dd", { "class": "lt-formula" }, c.formula_tex ? tex(c.formula_tex, true, c.formula) : (c.formula || "—"),
        c.formula_tex && c.formula ? drawer("ft-" + k, "文字写法：" + c.formula, { cls: "lt-small lt-ftext", lines: 1, limit: 50 }) : null),
      h("dt", { text: "原文" }), h("dd", {}, drawer("q-" + k, c.quote, { lines: 3, cls: "lt-quote" })),
      h("dt", { text: "出处" }), h("dd", {}, (c.paper ? c.paper + " " : "") + "PDF 第 " + c.page + " 页  ", link(LABEL.openPage, "/lite/pdf/" + (c.paper || "") + "#page=" + c.page, I.ext)),
      c.in_library ? [h("dt", { text: "库里" }), h("dd", { text: "已有 " + c.in_library + "（名字对上了，口径可在变量库里对照）" })] : null);
  }

  // 指标卡
  function indTrack(ind) {
    var st = ind.state;
    var given = (ind.data || []).filter(function (d) { return d.status === "通过" || d.status === "放行"; }).length, all = (ind.data || []).length;
    var now = { "待列数据": 0, "待交数据": 1, "待合成": 2, "待入库": 3, "已入库": 4 }[st];
    return track(["列数据", all && st === "待交数据" ? "交数据 " + given + "/" + all : "交数据", "合成", "入库"], now, "lt-track-mini");
  }
  function indCard(ind) {
    var openK = "def-" + ind.id;
    var card = h("div", { "class": "fb-card lt-ind", "data-st": ind.state },
      h("div", { "class": "lt-ind-h" }, h("span", { "class": "fb-id", text: ind.id }),
        h("span", { "class": "lt-ind-n" }, ind.name, ind.symbol_tex ? tex(ind.symbol_tex, false) : ind.column ? h("span", { "class": "lt-cand-en", text: ind.column }) : null),
        pill(ST[ind.state], ST_TONE[ind.state])),
      ind.state === "等数据" ? h("div", { "class": "lt-branch", text: "只存了定义：数据齐了可以“继续交数据”" }) : indTrack(ind),
      h("div", { "class": "lt-row", style: "margin-top:6px" }, linkBtn(S.more[openK] ? "收起定义和出处 ▴" : "定义和出处 ▾", function () { S.more[openK] = !S.more[openK]; render(); })),
      S.more[openK] ? defBlock(ind) : null);
    var st = ind.state;
    if (st === "待列数据") {
      add(card, h("div", { style: "margin-top:10px" }, wait("AI 正在列合成要的原始数据……", "列好后会在这里出现，逐份上传就行。",
        h("div", { "class": "lt-row" }, btn(LABEL.remind, "ghost-muted", function () { ask("needs", ind.id, "已提醒 AI 列所需数据"); }, { size: "small" }),
          sureBtn("drop-" + ind.id, LABEL.drop, "不做了，退回候选", function () { act("/lite/api/drop", { indicator: ind.id }, "已退回候选列表"); })))));
      return card;
    }
    if (st === "已入库") {
      add(card, h("div", { "class": "fb-tip", style: "margin-top:10px" }, icon(I.check), "已入库 " + (ind.admitted || "") + "，可在“变量库”里查看、导出"));
      if (ind.run_info) add(card, sumBlock(ind, true));
      return card;
    }
    if (st === "等数据") {
      add(card, h("div", { "class": "lt-row" }, btn(LABEL.resume, "outline", function () { act("/lite/api/resume", { indicator: ind.id }, "回到交数据"); }, { size: "small" }),
        sureBtn("drop-" + ind.id, LABEL.drop, "从库里拿掉，退回候选", function () { act("/lite/api/drop", { indicator: ind.id }, "已拿掉，退回候选列表"); })));
      return card;
    }
    if (ind.needs_note) add(card, h("div", { "class": "lt-ai" }, h("b", { text: "AI 提醒口径：" }), drawer("nn-" + ind.id, ind.needs_note, { tag: "span", lines: 2 })));
    ind.data.forEach(function (d) { add(card, needBox(ind, d)); });
    if (st === "待交数据") {
      add(card, h("div", { "class": "lt-row" },
        sureBtn("defer-" + ind.id, LABEL.defer, "数据凑不齐，只把定义存进库", function () { act("/lite/api/defer", { indicator: ind.id }, "定义已存进库（只存定义）；数据齐了还能继续交"); }),
        sureBtn("drop-" + ind.id, LABEL.drop, "不做了，退回候选", function () { act("/lite/api/drop", { indicator: ind.id }, "已退回候选列表"); })));
    }
    if (st === "待合成") {
      add(card, h("div", { style: "margin-top:10px" }, ind.last_run_failed
        ? wait("上一次合成没跑通，AI 正在改代码重试……", "报错在左边对话里。", h("div", { "class": "lt-row" }, btn(LABEL.remind, "ghost-muted", function () { ask("build", ind.id, "已提醒 AI 合成"); }, { size: "small" })))
        : wait("数据齐了，AI 正在合成……", "合成好后这里会出现小结。", h("div", { "class": "lt-row" }, btn(LABEL.remind, "ghost-muted", function () { ask("build", ind.id, "已提醒 AI 合成"); }, { size: "small" })))));
    }
    if (st === "待入库" && ind.run_info) {
      add(card, sumBlock(ind, false));
      add(card, h("div", { "class": "fb-acts" },
        btn(LABEL.admit, "contrast", function () { act("/lite/api/admit", { indicator: ind.id }, "「" + ind.name + "」已入库"); }, { icon: I.box, title: "看过小结，满意就入库" }),
        btn(LABEL.explain, "outline", function () { ask("explain", ind.id); }, { icon: I.message }),
        btn(LABEL.rebuild, "ghost-muted", function () { ask("rebuild", ind.id, "已告诉 AI，在左边对话里说哪里要改"); })));
    }
    return card;
  }

  function needBox(ind, d) {
    var n = d.need, f = d.file, st = d.status;
    var locked = ind.state === "已入库";
    var box = h("div", { "class": "lt-need" },
      h("div", { "class": "lt-need-h" }, h("span", { "class": "lt-need-n", text: n.name }), pill(DST[st], DST_TONE[st])),
      drawer("nw-" + ind.id + n.key, n.what + (n.years ? "（" + n.years + " 年）" : ""), { cls: "lt-need-w", lines: 2 }),
      h("div", { "class": "lt-cols" }, (n.columns || []).map(function (c) {
        return h("span", { "class": "lt-col", title: [c.hint, (c.aliases || []).length ? "也认：" + c.aliases.join("、") : ""].filter(Boolean).join("；") || null },
          c.name, h("em", { text: { code: "代码", year: "年份", date: "日期", number: "数", text: "文字" }[c.type || "text"] + (c.unit ? "·" + c.unit : "") }));
      })));
    if (f) {
      add(box, h("div", { "class": "lt-file" }, "已交：", h("b", { text: f.file }), "，" + int(f.info.rows) + " 行" + (f.info.years ? "，" + f.info.years[0] + "—" + f.info.years[1] + " 年" : "")));
      if (f.problems.length && !f.ok) add(box, listDrawer("pb-" + f.id, f.problems, "lt-problems"));
      if (f.warnings.length) add(box, listDrawer("wn-" + f.id, f.warnings, "lt-warn"));
      if (st === "放行") add(box, h("div", { "class": "lt-file" }, "放行理由：" + f.override));
      if (!f.ok && !locked) {
        var missing = (n.columns || []).filter(function (c) { return !f.mapping[c.name]; });
        var cols = f.info.columns || [];
        if (missing.length && cols.length) {
          var sel = {};
          add(box, h("div", { "class": "lt-small", style: "margin-top:8px", text: "把缺的列对应到文件里的列：" }));
          add(box, h("div", { "class": "lt-map" }, missing.map(function (c) {
            var s = h("select", { on: { change: function (e) { sel[c.name] = e.target.value; } } }, h("option", { value: "", text: "选文件里的列…" }),
              cols.map(function (x) { return h("option", { value: x, text: x }); }));
            return [h("span", { text: c.name }), s];
          })));
          add(box, h("div", { "class": "lt-row" }, btn(LABEL.remap, "outline", function () {
            if (!Object.keys(sel).some(function (k) { return sel[k]; })) return toast("先选好对应的列");
            act("/lite/api/colmap", withSession({ datafile: f.id, colmap: sel })).then(function (r) { toast(r.ok ? "对上了，校验通过" : "还没通过，看红字"); });
          }, { size: "small" })));
        }
        if (st === "没通过") {
          var dk = "why-" + f.id;
          var why = h("input", { type: "text", placeholder: "确实没问题？写一句理由放行", value: S.draft[dk] || "", "data-keep": dk, on: { input: function (e) { S.draft[dk] = e.target.value; } } });
          add(box, h("div", { "class": "lt-row" }, why, btn(LABEL.override, "outline", function () {
            act("/lite/api/override", withSession({ datafile: f.id, reason: S.draft[dk] || "" }), "已放行，理由记在这个指标上").then(function () { delete S.draft[dk]; });
          }, { size: "small" }), linkBtn(LABEL.dataHelp, function () { ask("data_help", ind.id, "已请 AI 看看，回复在左边对话里"); })));
        }
      }
    }
    if (!locked) {
      var accept = ".csv,.txt,.xlsx,.xlsm,.parquet,.dta";
      var up = function (file) {
        S.uploadingNeed = n.key + ind.id; render();
        api("/lite/api/upload-data?indicator=" + ind.id + "&need=" + encodeURIComponent(n.key) + "&name=" + encodeURIComponent(file.name) + "&session=" + encodeURIComponent(currentSession()), undefined, file).then(function (r) {
          S.uploadingNeed = null;
          toast(r.ok ? (r.state === "待合成" ? "校验通过，数据交齐了，AI 开始合成" : "校验通过") : "没通过校验，看红字", 5000);
          refresh(true);
        }, function (e) { S.uploadingNeed = null; render(); toast(e.message, 6000); });
      };
      var busy = S.uploadingNeed === n.key + ind.id;
      add(box, h("div", { "class": "lt-row" }, btn(busy ? "正在上传…" : f ? LABEL.reupload : LABEL.upload, f ? "ghost-muted" : "outline", function () { pickFile(accept, up); }, { size: "small", icon: I.upload, disabled: busy }),
        h("span", { "class": "lt-small", text: "CSV / Excel / parquet / dta，也可以拖进这个框" })));
      dropTarget(box, accept, up);
    }
    return box;
  }
  // 超过 3 条的问题、提醒：先显示 3 条
  function listDrawer(k, items, cls) {
    var open = !!S.more["dr-" + k], show = open || items.length <= 3 ? items : items.slice(0, 3);
    return h("ul", { "class": cls }, show.map(function (x) { return h("li", { text: x }); }),
      items.length > 3 ? h("li", { "class": "lt-li-more" }, h("button", { type: "button", "class": "lt-drawer-t", on: { click: function () { S.more["dr-" + k] = !open; render(); } } },
        open ? "收起 ▴" : "还有 " + (items.length - 3) + " 条，展开 ▾")) : null);
  }

  // 小结
  function sumBlock(ind, brief) {
    var r = ind.run_info, s = r.summary || {};
    var wrap = h("div", { "class": "lt-sum" });
    add(wrap, h("div", { "class": "lt-big" },
      h("div", {}, h("b", { text: int(s.rows) }), h("span", { text: "行" })),
      h("div", {}, h("b", { text: s.entities != null ? int(s.entities) : "—" }), h("span", { text: "个主体（" + ((ind.keys || [])[0] || "") + "）" })),
      h("div", {}, h("b", { text: s.years ? s.years[0] + "—" + s.years[1] : "—" }), h("span", { text: "年份" }))));
    if (brief) {
      add(wrap, h("div", { "class": "lt-small", style: "margin-top:6px" }, "合成记录 " + r.id + " · ", link("看合成代码", "/lite/code/" + r.id, I.ext)));
      return wrap;
    }
    var st = s.stats;
    if (st) {
      add(wrap, h("table", { "class": "lt-stats" },
        h("tr", {}, ["均值", "标准差", "最小", "1%", "中位数", "99%", "最大"].map(function (x) { return h("th", { text: x }); })),
        h("tr", {}, ["mean", "sd", "min", "p1", "median", "p99", "max"].map(function (k) { return h("td", { text: fmt(st[k]) }); }))));
    }
    add(wrap, h("div", { "class": "lt-small", style: "margin-top:6px", text: "空值 " + int(s.missing) + " 行" + (s.missing_share ? "（" + (s.missing_share * 100).toFixed(1) + "%）" : "") + (s.duplicates ? " · 主键重复 " + int(s.duplicates) + " 行" : " · 主键不重复") + (st ? " · 不同取值 " + int(st.unique) + " 个" : "") }));
    if (s.hist) {
      var mx = Math.max.apply(null, s.hist.counts.concat([1]));
      add(wrap, h("div", { "class": "lt-sub-h", text: "分布（1%—99% 之间）" }));
      add(wrap, h("div", { "class": "lt-hist" }, s.hist.counts.map(function (c) { return h("i", { style: "height:" + Math.max(2, c / mx * 100) + "%", title: c + " 个" }); })));
      add(wrap, h("div", { "class": "lt-hist-l" }, h("span", { text: fmt(s.hist.edges[0]) }), h("span", { text: fmt(s.hist.edges[s.hist.edges.length - 1]) })));
    }
    if (s.by_year && s.by_year.length > 1) {
      var my = Math.max.apply(null, s.by_year.map(function (y) { return y.filled; }).concat([1]));
      add(wrap, h("div", { "class": "lt-sub-h", text: "每年有值的行数" }));
      add(wrap, h("div", { "class": "lt-years" }, s.by_year.map(function (y) { return h("i", { style: "height:" + Math.max(3, y.filled / my * 100) + "%", title: fmt(y.year) + " 年：" + y.filled + " 行" + (y.mean != null ? "，均值 " + fmt(y.mean) : "") }); })));
      add(wrap, h("div", { "class": "lt-hist-l" }, h("span", { text: fmt(s.by_year[0].year) }), h("span", { text: fmt(s.by_year[s.by_year.length - 1].year) })));
    }
    if (s.top && s.top.length) {
      add(wrap, h("div", { "class": "lt-sub-h", text: "最大和最小的几行" }));
      add(wrap, h("table", { "class": "lt-stats", style: "margin-top:4px" },
        h("tr", {}, (s.show_cols || []).map(function (x) { return h("th", { text: x }); })),
        s.top.concat(s.bottom || []).map(function (row) { return h("tr", {}, row.map(function (v, i) { return h("td", { text: i === row.length - 1 ? fmt(v) : String(v == null ? "" : v) }); })); })));
    }
    add(wrap, (s.alerts || []).length ? h("ul", { "class": "lt-warn", style: "margin-top:10px" }, s.alerts.map(function (x) { return h("li", { text: x }); }))
      : h("div", { "class": "fb-tip" }, icon(I.check), "工厂没发现明显问题（重复、缺年份、无穷大、离群值都查过）"));
    if (r.note) add(wrap, h("div", { "class": "lt-ai" }, h("b", { text: "AI 说明口径：" }), drawer("rn-" + r.id, r.note, { tag: "span", lines: 3 })));
    add(wrap, h("div", { "class": "lt-small", style: "margin-top:8px" }, "用的数据：" + (r.inputs || []).map(function (i) { return i.file; }).join("、") + " · 合成记录 " + r.id + " · ", link("看合成代码", "/lite/code/" + r.id, I.ext)));
    return wrap;
  }

  // ───── 全部论文 ─────
  function papersView(ps) {
    var out = [h("div", { "class": "lt-small", style: "margin-bottom:10px", text: "一个对话做一篇论文，一篇论文可以有几个对话。点“打开对话”切过去，工厂栏会跟着切换。" })];
    out.push(h("div", { "class": "lt-row", style: "margin:0 0 12px" }, btn(LABEL.newPaper, "outline", newLine, { size: "small", icon: I.sparkle })));
    if (!ps.length) out.push(h("div", { "class": "fb-none", text: "还没有论文。到“" + LABEL.tabLine + "”上传第一篇。" }));
    else out.push(h("div", { "class": "fb-list" }, ps.map(function (p) {
      var here = (p.sessions || []).indexOf(currentSession()) >= 0;
      var c = p.counts || {};
      var mine = (c["待交数据"] || 0) + (c["待入库"] || 0);
      return h("div", { "class": "fb-row lt-paper-row" }, h("span", { "class": "fb-row-ic" }, icon(I.doc)),
        h("div", { "class": "fb-main" }, h("div", { "class": "fb-title", text: p.title }),
          h("div", { "class": "fb-sub" }, p.id + " · ", mine ? h("b", { "class": "lt-mine", text: mine + " 个指标等你处理" }) : p.label,
            p.n_indicators ? " · 做完 " + p.n_done + "/" + p.n_indicators : p.n_candidates ? " · 候选 " + p.n_candidates : "",
            (p.sessions || []).length > 1 ? " · " + p.sessions.length + " 个对话" : "")),
        here ? pill("就是这个对话", "info") : p.session ? btn(LABEL.openSession, "ghost-muted", function () { goSession(p.session); }, { size: "small" })
          : btn(LABEL.moveHere, "ghost-muted", function () { bindHere(p.id); }, { size: "small" }));
    })));
    out.push(h("div", { "class": "lt-danger-zone" },
      h("div", { "class": "lt-sub-h", style: "margin-top:0", text: "恢复出厂" }),
      h("div", { "class": "lt-small", text: "彻底删掉全部论文、指标、上传的数据、合成记录和工厂的对话，回到刚装好的样子（内置的变量定义会重新带进来；“导出”文件夹不动）。删了找不回。" }),
      h("div", { "class": "lt-row" }, sureBtn("reset", LABEL.reset, "删除全部论文、指标、数据和工厂对话", doReset, "outline"))));
    return out;
  }
  function doReset() {
    S.busy = true;
    toast("正在恢复出厂……", 20000);
    api("/lite/api/reset", {}).then(function (r) {
      // OpenCode 顶上的对话标签只留新对话（旧对话已经删了）
      try { localStorage.setItem("opencode.window.browser.dat:tabs", JSON.stringify([{ type: "session", server: location.origin, sessionId: r.session }])); } catch (e) {}
      S.pick = {}; S.more = {}; S.libSel = {}; S.lib = null; S.papers = null; S.data = null; S.draft = {}; S.libF = {}; S.libQ = ""; S.tab = "line";
      toast("已恢复出厂：删掉 " + r.deleted_sessions + " 个对话，旧库定义 " + r.oldlib + " 个", 6000);
      sessionStorage.setItem("lite-open-now", "1");
      location.assign(r.path);
    }, function (e) { toast(e.message, 8000); }).finally(function () { S.busy = false; });
  }

  // ───── 变量库 ─────
  function libQuery() {
    var f = S.libF, q = ["q=" + encodeURIComponent(S.libQ)];
    ["kind", "data", "paper", "role", "shape"].forEach(function (k) { if (f[k]) q.push(k + "=" + encodeURIComponent(f[k])); });
    return q.join("&");
  }
  function setF(k, v) { S.libF[k] = v; S.libShow = 60; refresh(true); }
  function chips(k, opts) {
    return h("div", { "class": "fb-chips" }, opts.map(function (o) {
      return h("button", { type: "button", "class": "fb-chipbtn", "aria-pressed": String((S.libF[k] || "") === o[0]), on: { click: function () { setF(k, o[0]); } } }, o[1]);
    }));
  }
  function facetSel(k, label, list) {
    return h("label", { "class": "lt-fsel" }, h("span", { text: label }),
      h("select", { on: { change: function (e) { setF(k, e.target.value); } } }, h("option", { value: "", text: "全部" }),
        (list || []).map(function (o) { return h("option", { value: o.value, text: o.label + "（" + o.n + "）", selected: S.libF[k] === o.value ? true : null }); })));
  }
  function aiFind() {
    var q = (S.libQ || "").trim();
    if (q.length < 2) return toast("先在搜索框里写一句话：你要找什么样的变量（如“衡量融资约束的”），再点“" + LABEL.aiFind + "”", 6000);
    api("/lite/api/lib-search", { query: q }).then(function () { S.hideSearch = ""; S.libQ = ""; toast("已请 AI 在库里找，结果会显示在最上面"); refresh(true); },
      function (e) { toast(e.message, 6000); });
  }
  function searchBlock(s) {
    if (!s || S.hideSearch === s.id) return null;
    if (!s.done) return h("div", { style: "margin-bottom:12px" }, wait("AI 正在库里找：" + s.query, "一般半分钟到一分钟。",
      h("div", { "class": "lt-row" }, btn(LABEL.remind, "ghost-muted", function () { ask("lib_search", "", "已提醒 AI"); }, { size: "small" }),
        linkBtn("去对话里看", function () { goSession(s.session); }))));
    return h("div", { "class": "fb-card lt-found" },
      h("div", { "class": "fb-line" }, h("b", { text: "AI 找到 " + s.results.length + " 个" }), h("span", { "class": "lt-small", text: "你问：" + s.query }), h("span", { "class": "fb-grow" }),
        linkBtn("收起", function () { S.hideSearch = s.id; render(); })),
      s.note ? h("div", { "class": "lt-small", style: "margin-top:4px", text: s.note }) : null,
      s.results.length ? h("div", { "class": "fb-list", style: "margin-top:8px" }, s.results.map(function (r) {
        return h("button", { type: "button", "class": "fb-row", on: { click: function () { S.libItem = r.id; S.libDetail = null; render(); refresh(true); } } },
          h("div", { "class": "fb-main" }, h("div", { "class": "fb-title" }, r.name || r.id, h("span", { "class": "lt-cand-en", text: r.id })),
            h("div", { "class": "fb-sub", style: "white-space:normal", text: r.why })), h("span", { "class": "fb-chev" }, icon(I.chev)));
      })) : h("div", { "class": "fb-none", style: "margin-top:8px", text: "库里没找到相关的变量" }),
      h("div", { "class": "lt-row" }, linkBtn("去对话里看 AI 怎么说", function () { goSession(s.session); })));
  }
  function libView(d) {
    var out = [];
    var ov = d.overview || {}, fc = d.facets || {};
    var q = h("input", { type: "text", placeholder: "搜名称、英文名、定义、论文；或写一句话让 AI 找", value: S.libQ, "data-keep": "libq",
      on: { input: debounce(function (e) { S.libQ = e.target.value; S.libShow = 60; refresh(true); }, 250),
        keydown: function (e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) aiFind(); } } });
    out.push(h("div", { "class": "lt-searchrow" }, h("div", { "class": "fb-search" }, icon(I.search), q),
      btn(LABEL.aiFind, "outline", aiFind, { size: "small", icon: I.sparkle, title: "AI 理解你的意思，换几种说法在库里找" })));
    out.push(searchBlock(d.search));
    out.push(h("div", { "class": "lt-filters" },
      h("div", { "class": "lt-frow" }, h("span", { "class": "lt-flab", text: "来源" }), chips("kind", [["", "全部"], ["本工具", "本工具入库"], ["旧库", OLD()]])),
      h("div", { "class": "lt-frow" }, h("span", { "class": "lt-flab", text: "数据" }), chips("data", [["", "全部"], ["有", "有数据"], ["无", "只有定义"]])),
      h("div", { "class": "lt-fgrid" }, facetSel("paper", "来源论文", fc.paper), facetSel("role", "角色", fc.role), facetSel("shape", "数据形状", fc.shape))));
    var items = d.items || [];
    var filtered = S.libQ || Object.keys(S.libF).some(function (k) { return S.libF[k]; });
    var sel = Object.keys(S.libSel).filter(function (k) { return S.libSel[k]; });
    out.push(h("div", { "class": "lt-count" }, h("b", { text: String(items.length) }), " 个" + (filtered ? "（已筛选）" : ""),
      h("span", { "class": "lt-small", text: " · 全库：本工具入库 " + ((ov.indicators || {})["已入库"] || 0) + "、只存定义 " + ((ov.indicators || {})["等数据"] || 0) + "、" + OLD() + " " + (ov.oldlib || 0) }),
      filtered ? linkBtn("清空筛选", function () { S.libF = {}; S.libQ = ""; refresh(true); }) : null));
    if (!items.length) out.push(h("div", { "class": "fb-none", text: filtered ? "没有符合的。可以换个说法，或点“" + LABEL.aiFind + "”" : "还没有。论文里的指标入库后会出现在这里。" }));
    else out.push(h("div", { "class": "fb-list" }, items.slice(0, S.libShow).map(function (x) {
      return h("div", { "class": "lt-lib-row" },
        h("input", { type: "checkbox", checked: !!S.libSel[x.id], title: "勾选后可以导出", on: { change: function (e) { S.libSel[x.id] = e.target.checked; render(); } } }),
        h("div", { "class": "fb-main", on: { click: function () { S.libItem = x.id; S.libDetail = null; render(); refresh(true); } } },
          h("div", { "class": "fb-title" }, x.name, x.symbol_tex ? tex(x.symbol_tex, false) : x.name_en ? h("span", { "class": "lt-cand-en", text: x.name_en }) : null),
          h("div", { "class": "fb-sub", text: x.id + " · " + (x.kind === "本工具" ? x.paper + "《" + x.paper_title + "》" : x.paper_title) + (x.role ? " · " + x.role : "") })),
        pill(x.kind === "旧库" ? OLD() + (x.has_data ? "·有数据" : "·只有定义") : ST[x.state], x.state === "已入库" ? "success" : x.kind === "旧库" && x.has_data ? "info" : ""));
    })));
    if (items.length > S.libShow) out.push(h("div", { "class": "lt-more-n" }, linkBtn("再显示 60 个（共 " + items.length + "）", function () { S.libShow += 60; render(); })));
    if (ov.old_data && ov.oldlib && items.some(function (x) { return x.kind === "旧库" && !x.has_data; })) {
      out.push(h("div", { "class": "lt-small", style: "margin:10px 2px" }, "旧库只带了定义。要用哪个的数据，点开它带入；或者",
        sureBtn("olddata", "全部带入", "复制全部旧库数据文件", function () { act("/lite/api/import-old-data", {}, "已带入旧库数据"); })));
    }
    out.push(h("div", { "class": "lt-sticky" },
      h("span", { "class": "lt-small", text: sel.length ? "选了 " + sel.length + " 个" : "勾选要导出的指标" }),
      sel.length ? linkBtn("清空", function () { S.libSel = {}; render(); }) : null,
      btn(LABEL.exportSel + "（" + sel.length + "）", "contrast", function () {
        act("/lite/api/export", { ids: sel, reveal: true }).then(function (r) { toast("已导出到 " + r.folder + "（已在访达里打开）", 8000); });
      }, { disabled: !sel.length, icon: I.upload })));
    return out;
  }
  function OLD() { return (S.lib && S.lib.overview && S.lib.overview.old_name) || "旧库"; }
  function oldData() { return !!(S.lib && S.lib.overview && S.lib.overview.old_data); }
  function debounce(fn, ms) { var t; return function () { var a = arguments; clearTimeout(t); t = setTimeout(function () { fn.apply(null, a); }, ms); }; }
  function facts(list) {
    return h("dl", { "class": "fb-facts" }, list.filter(function (f) { return f[1]; }).map(function (f) { return [h("dt", { text: f[0] }), h("dd", {}, f[1])]; }));
  }
  function libDetail(d) {
    var out = [h("div", { "class": "fb-back" }, btn("返回变量库", "ghost-muted", function () { S.libItem = null; refresh(true); render(); }, { size: "small", icon: I.back }))];
    if (d.type === "oldlib") {
      var srcs = d.sources || [];
      out.push(h("div", { "class": "fb-card fb-head-card" }, h("div", { "class": "fb-line" }, h("span", { "class": "fb-id", text: d.id }), h("span", { "class": "fb-grow" }), pill(OLD() + (d.data ? "·有数据" : "·只有定义"), d.data ? "info" : "")),
        h("div", { "class": "fb-h1", text: d.name }),
        facts([["英文名", d.name_en], ["单位", d.unit], ["数据形状", d.shape], ["定义", d.definition], ["公式", d.formula],
          ["含义", d.definition ? "" : (d.meanings || []).map(function (m) { return m.label; }).join("、")], ["出处", srcs.length ? srcs.length + " 处" : ""]])));
      if (!d.data && oldData()) out.push(h("div", { "class": "lt-row", style: "margin-top:10px" }, h("span", { "class": "lt-small", text: "旧库只带了定义。要用它的数据：" }),
        btn(LABEL.importData, "outline", function () { act("/lite/api/import-old-data", { ids: [d.id] }, "已带入 " + d.id + " 的数据文件，导出时会一起导出"); }, { size: "small" })));
      if (!srcs.length) return out.concat([h("div", { "class": "lt-small", style: "margin-top:10px", text: "这是内置的变量定义（只有名称、定义、公式）。要用它，在论文里选中对应的指标，交自己的数据合成。" })]);
      out.push(sec("出处原文", srcs.length));
      out.push(h("div", { "class": "fb-list" }, srcs.slice(0, 30).map(function (x, i) {
        return h("div", { "class": "fb-row fb-src" }, h("div", { "class": "fb-main" }, drawer("src-" + d.id + i, "“" + (x.quote || "") + "”", { cls: "fb-src-q", lines: 3 }),
          h("div", { "class": "fb-sub", style: "white-space:normal", text: (x.paper_id || "") + (x.location ? " · " + x.location : "") })));
      })));
      return out;
    }
    var r = d.run_info;
    out.push(h("div", { "class": "fb-card fb-head-card" }, h("div", { "class": "fb-line" }, h("span", { "class": "fb-id", text: d.id }), h("span", { "class": "fb-grow" }), pill(ST[d.state] || d.state, ST_TONE[d.state])),
      h("div", { "class": "fb-h1" }, d.name, d.symbol_tex ? tex(d.symbol_tex, false) : d.column ? h("span", { "class": "lt-cand-en", text: d.column }) : null),
      facts([["英文名", d.name_en], ["结果列", d.column], ["角色", d.role], ["单位", d.unit], ["数据形状", d.shape], ["主键", (d.keys || []).join(" + ")], ["入库", d.admitted]])));
    out.push(sec("定义和出处"));
    out.push(h("div", { "class": "fb-card" }, defBlock(d), h("div", { "class": "lt-small", style: "margin-top:6px", text: "论文：" + d.paper + "《" + d.paper_title + "》" })));
    if ((d.needs || []).length) {
      out.push(sec("用的数据", d.data.length));
      out.push(h("div", { "class": "fb-list" }, d.data.map(function (x) {
        var f = x.file;
        return h("div", { "class": "fb-row" }, h("div", { "class": "fb-main" }, h("div", { "class": "fb-title", text: x.need.name }),
          h("div", { "class": "fb-sub", style: "white-space:normal", text: f ? f.file + " · MD5 " + f.md5 + (f.override ? " · 放行理由：" + f.override : "") : "没交" })), pill(DST[x.status], DST_TONE[x.status]));
      })));
    }
    if (r) { out.push(sec("合成小结")); out.push(sumBlock(d, false)); }
    var ek = "ev-" + d.id, evs = (d.events || []).slice().reverse();
    out.push(grpHead(ek, "追溯记录", evs.length));
    if (S.more[ek]) out.push(h("ul", { "class": "fb-rec" }, evs.map(function (e) {
      return h("li", {}, h("div", { "class": "fb-rec-l1" }, h("span", { "class": "fb-rec-tag", "data-tone": e.kind === "入库" ? "success" : e.kind === "放行" ? "warning" : null, text: e.kind }), h("span", { "class": "fb-rec-s", text: e.who })),
        h("div", { "class": "fb-rec-d", text: e.text }), h("div", { "class": "fb-rec-m", text: e.at }));
    })));
    return out;
  }

  // ───── 跟着对话走、自动刷新 ─────
  var lastPath = "", lastRev = -1;
  function tick() {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      S.dup = null;
      if (sessionStorage.getItem("lite-open-now")) { sessionStorage.removeItem("lite-open-now"); if (!S.open) setOpen(true); S.tab = "line"; }
      if (S.open && S.tab === "line") { S.data = null; render(); refresh(true); }
    }
  }
  function poll() {
    if (!S.open || !key() || S.busy || document.hidden) return;
    api("/lite/api/stamp").then(function (s) {
      if (s.rev !== lastRev) { lastRev = s.rev; refresh(); }
    }).catch(function () {});
  }

  function start() {
    build();
    mount();
    setOpen(S.open);
    new MutationObserver(mount).observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", function () {
      var p = new URLSearchParams(location.hash.slice(1));
      if (p.get("k")) { localStorage.setItem(KEY, p.get("k")); history.replaceState(history.state, "", location.pathname + location.search); refresh(true); ensureLogin(); }
    });
    lastPath = location.pathname;
    setInterval(tick, 400);
    setInterval(poll, 1500);
    afterLogin();
    ensureLogin();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
