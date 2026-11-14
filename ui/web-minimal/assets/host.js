"use strict";
(() => {
  // ui/web-minimal/src/host/state.ts
  var HOST = window;
  var slotMap = {};
  var pluginBySlot = {};
  var frames = {};
  var configByPlugin = {};
  var slotByPluginId = {};
  var frameByPluginId = {};
  var groupState = {
    activeSessionId: "",
    activeBranchId: "main",
    // 当前查看的分支视图（main / 子代理分支），供输入框判定只读
    sessions: [],
    empty: true,
    // 草稿态：点「新建会话」后不落盘、不进列表，仅前端占位欢迎界面；
    // 首条消息发送时才按 draftParadigm 建会话并生成系统提示词。
    draft: false,
    draftParadigm: "",
    draftProjectId: "",
    // 草稿态所属项目（从项目内新建时携带，用于注入 MEMORY.md 路径）
    plugins: []
    // manifest 注解后的插件列表（供设置面板使用）
  };
  var railState = { stage: 0, hidden: {}, opacity: 1 };
  var railButtons = {};
  var activeBySlot = {};

  // ui/web-minimal/src/host/layout.ts
  var LAYOUT_KEY_SIDEBAR = "slot:sidebar";
  var LAYOUT_KEY_SESSION = "slot:session";
  var TILE_MIN_W = 260;
  var TILE_MAX_W = 4e3;
  var TILE_ADD_W = 132;
  var layoutState = { mode: "container", order: [], widths: {} };
  function panelWindowKey(id) {
    return "panel:" + id;
  }
  function tileMode() {
    return layoutState.mode === "tile";
  }
  function defaultWindowWidth(key) {
    if (key === LAYOUT_KEY_SIDEBAR) return 264;
    if (key === LAYOUT_KEY_SESSION) return 420;
    return 480;
  }
  function windowWidth(key) {
    const raw = Number(layoutState.widths[key]);
    if (!isFinite(raw) || raw < TILE_MIN_W) return defaultWindowWidth(key);
    return Math.min(TILE_MAX_W, Math.round(raw));
  }
  function setWindowWidth(key, width) {
    if (!isFinite(width)) return;
    layoutState.widths[key] = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(width)));
  }
  function applyLayoutFromManifest(raw) {
    const data = raw && typeof raw === "object" ? raw : {};
    layoutState.mode = data.mode === "tile" ? "tile" : "container";
    const rawOrder = Array.isArray(data.order) ? data.order : [];
    layoutState.order = rawOrder.filter((k) => typeof k === "string" && !!k.trim()).map((k) => k.trim());
    const widths = {};
    const rawWidths = data.widths && typeof data.widths === "object" ? data.widths : {};
    Object.keys(rawWidths).forEach((k) => {
      const w = Number(rawWidths[k]);
      if (k && isFinite(w)) widths[k] = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(w)));
    });
    layoutState.widths = widths;
    applyLayoutClass();
  }
  function applyLayoutClass() {
    const tile = tileMode();
    HOST.document.body.classList.toggle("layout-tile", tile);
    if (!tile) HOST.document.body.classList.remove("wm-shift-mode");
  }
  function ensureOrder(visibleKeys) {
    const visible = new Set(visibleKeys);
    const order = layoutState.order.filter((k) => typeof k === "string" && !!k && visible.has(k));
    visibleKeys.forEach((key) => {
      if (order.indexOf(key) < 0) order.push(key);
    });
    layoutState.order = order;
    return order;
  }
  function reorderWindows(visibleOrder) {
    const visible = new Set(visibleOrder);
    const next = [];
    let i = 0;
    layoutState.order.forEach((k) => {
      if (visible.has(k)) {
        if (i < visibleOrder.length) next.push(visibleOrder[i++]);
      } else {
        next.push(k);
      }
    });
    while (i < visibleOrder.length) next.push(visibleOrder[i++]);
    layoutState.order = next;
  }
  function persistLayout() {
    return fetch("/api/webmin/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ layout: layoutState })
    }).then((res) => {
      if (!res.ok) throw new Error(String(res.status));
    }).catch(() => {
    });
  }
  function setLayoutMode(mode) {
    if (layoutState.mode === mode) return;
    layoutState.mode = mode;
    applyLayoutClass();
    remountLayout();
    persistLayout();
  }
  var remountLayout = () => {
  };
  function bindRemountLayout(fn) {
    remountLayout = fn;
  }

  // ui/web-minimal/src/host/icons.ts
  var ICON_SVG = {
    list: '<path d="M3 6h.01M3 12h.01M3 18h.01"/><path d="M8 6h13M8 12h13M8 18h13"/>',
    pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "panel-left": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
    "panel-top": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/>',
    "layout-panel-left": '<rect width="7" height="18" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    // sensor 默认图标（配置项未提供 icon 或图标加载失败时回退）
    sensor: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>'
  };
  var ICON_SVG_ATTR = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"';
  function paintIcon(el, icon, fallbackChar) {
    const raw = String(icon == null ? "" : icon).trim();
    if (/^<svg[\s>]/i.test(raw)) {
      el.innerHTML = raw.replace(/<script[\s\S]*?<\/script>/gi, "");
      return;
    }
    if (ICON_SVG[raw]) {
      el.innerHTML = "<svg " + ICON_SVG_ATTR + ">" + ICON_SVG[raw] + "</svg>";
      return;
    }
    el.textContent = raw || fallbackChar || "";
  }
  function paintPluginIcon(el, p) {
    const nm = p && (p.name || p.id) || "?";
    paintIcon(el, p && p.icon, (nm.charAt(0) || "?").toUpperCase());
  }

  // ui/web-minimal/src/host/sessions.ts
  function setEmpty(v) {
    groupState.empty = !!v;
    broadcast("session", "layout.empty", { empty: !!v });
  }
  function updateEmpty() {
    const activeId = groupState.activeSessionId;
    let empty = !activeId;
    if (activeId) {
      const s = groupState.sessions.find((x) => x.id === activeId);
      const count = s ? Number(s.messages_count) || 0 : 0;
      empty = count === 0;
    }
    setEmpty(empty);
  }
  async function refreshSessions() {
    try {
      const list = await (await fetch("/api/sessions")).json();
      groupState.sessions = Array.isArray(list) ? list : groupState.sessions;
    } catch (_) {
    }
  }
  function broadcastSessions(event, data) {
    if (event === "session.switched") {
      groupState.activeBranchId = "main";
      broadcastAll("branch.switched", { branch_id: "main" });
    }
    broadcast("session", event, data);
    broadcast("sidebar", event, data);
  }

  // ui/web-minimal/src/host/config-apply.ts
  async function saveConfig() {
    const res = await fetch("/api/webmin/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plugins: configByPlugin })
    });
    if (!res.ok) throw new Error(await res.text());
  }
  function applyConfigTo(pid) {
    const iframe = frameByPluginId[pid];
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage({ type: "configApply", config: configByPlugin[pid] || {} }, "*");
    }
  }
  function draftSessionAlias(message) {
    let text = String(message == null ? "" : message).replace(/[\u0000-\u001f\u007f-\u009f\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, " ").replace(/\s+/g, " ").trim();
    if (!text) return "";
    const chars = Array.from(text);
    let alias = chars.length > 10 ? chars.slice(0, 10).join("") : text;
    return alias.replace(/[\u200c\u200d]+$/, "").trim();
  }
  async function ensureSessionId(sessionId, firstMessage) {
    if (sessionId) return sessionId;
    const body = { paradigm: groupState.draftParadigm || "", project_id: groupState.draftProjectId || "" };
    const alias = draftSessionAlias(firstMessage);
    if (alias) body.alias = alias;
    const created = await (await fetch("/api/sessions/new", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
    if (created && created.id) {
      groupState.activeSessionId = created.id;
      groupState.draft = false;
      groupState.draftParadigm = "";
      groupState.draftProjectId = "";
      await refreshSessions();
      updateEmpty();
      broadcastSessions("session.switched", { session_id: created.id });
      return created.id;
    }
    return "";
  }
  async function activeSessionBusy() {
    const sid = groupState.activeSessionId;
    if (!sid) return false;
    try {
      const st = await (await fetch("/api/sessions/" + encodeURIComponent(sid) + "/status")).json();
      return !!(st && st.is_thinking);
    } catch (_) {
      return false;
    }
  }

  // ui/web-minimal/src/host/dialog.ts
  function pickPath(r) {
    if (!r) return null;
    if (Array.isArray(r)) return r[0] || null;
    const o = r;
    if (Array.isArray(o.filePaths)) return o.filePaths[0] || null;
    if (Array.isArray(o.paths)) return o.paths[0] || null;
    if (typeof r === "string") return r;
    if (typeof o.path === "string") return o.path;
    return null;
  }
  async function apiErrorMessage(res, fallback) {
    try {
      const text = await res.text();
      try {
        const data = JSON.parse(text);
        return data && (data.detail || data.message) || fallback;
      } catch (_) {
        return text || fallback;
      }
    } catch (_) {
      return fallback;
    }
  }

  // ui/web-minimal/src/host/float.ts
  function beginFloatGesture(handle, e, onMove) {
    const pid = e.pointerId;
    try {
      handle.setPointerCapture(pid);
    } catch (_) {
    }
    const move = (ev) => {
      if (ev.pointerId === pid) onMove(ev);
    };
    const end = (ev) => {
      if (ev.pointerId !== pid) return;
      try {
        handle.releasePointerCapture(pid);
      } catch (_) {
      }
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }
  function startFloatDrag(el, e) {
    e.preventDefault();
    e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    beginFloatGesture(e.currentTarget, e, (ev) => {
      el.style.right = "auto";
      el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r0.left + (ev.clientX - sx))) + "px";
      el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r0.top + (ev.clientY - sy))) + "px";
    });
  }
  function startFloatResize(el, e) {
    e.preventDefault();
    e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    beginFloatGesture(e.currentTarget, e, (ev) => {
      el.style.width = Math.max(160, r0.width + (ev.clientX - sx)) + "px";
      el.style.height = Math.max(160, r0.height + (ev.clientY - sy)) + "px";
    });
  }
  function applyFloatSize(el, size, i) {
    if (!size) return;
    const w = size.w, h = size.h;
    if (typeof w === "string" && w) {
      el.style.width = w;
    } else if (Number(w) > 0) {
      const wpx = Number(w);
      el.style.width = wpx + "px";
      el.style.left = `calc(100% - ${wpx + (i || 0) * 26}px - 16px)`;
    }
    if (typeof h === "string" && h) el.style.height = h;
    else if (Number(h) > 0) el.style.height = Number(h) + "px";
  }
  function applyModalSize(el, size) {
    if (!size) return;
    if (typeof size.w === "string" && size.w) el.style.width = size.w;
    else if (Number(size.w) > 0) el.style.width = Number(size.w) + "px";
    if (typeof size.h === "string" && size.h) el.style.height = size.h;
    else if (Number(size.h) > 0) el.style.height = Number(size.h) + "px";
  }
  function centerFloat(el) {
    const railEl = HOST.document.getElementById("rail");
    const railW = railEl ? railEl.getBoundingClientRect().width : 0;
    const avail = Math.max(0, HOST.innerWidth - railW);
    const w = el.offsetWidth, h = el.offsetHeight;
    el.style.right = "auto";
    el.style.left = Math.max(0, Math.round(railW + (avail - w) / 2)) + "px";
    el.style.top = Math.max(0, Math.round((HOST.innerHeight - h) / 2)) + "px";
  }
  function reflowFloats() {
    Object.keys(frames).forEach((sid) => {
      (frames[sid] || []).forEach((f) => {
        const el = f.el;
        if (!el || !el.classList.contains("wm-float") || el.style.display === "none") return;
        const p = groupState.plugins.find((x) => x.id === f.pluginId);
        const def = p && p.slotDef || {};
        if (def.center) {
          centerFloat(el);
          return;
        }
        const w = el.offsetWidth, h = el.offsetHeight;
        const r = el.getBoundingClientRect();
        el.style.right = "auto";
        el.style.left = Math.max(0, Math.min(Math.max(0, HOST.innerWidth - w), r.left)) + "px";
        el.style.top = Math.max(0, Math.min(Math.max(0, HOST.innerHeight - h), r.top)) + "px";
      });
    });
  }
  HOST.addEventListener("resize", function() {
    try {
      applyPanelWidth();
    } catch (_) {
    }
    try {
      reflowFloats();
    } catch (_) {
    }
  });
  function attachFloatHandles(el) {
    el.querySelectorAll(".wm-fgrab, .wm-fresize").forEach((hd) => hd.remove());
    const g = HOST.document.createElement("div");
    g.className = "wm-fgrab";
    g.title = "\u62D6\u52A8";
    g.addEventListener("pointerdown", (e) => startFloatDrag(el, e));
    el.appendChild(g);
    const r = HOST.document.createElement("div");
    r.className = "wm-fresize";
    r.title = "\u7F29\u653E";
    r.addEventListener("pointerdown", (e) => startFloatResize(el, e));
    el.appendChild(r);
  }

  // ui/web-minimal/src/host/config-center.ts
  var MODEL_CATS = [
    // 三个模型角色：title/jsonKey
    { key: "main", title: "\u6838\u5FC3\u6A21\u578B" },
    { key: "task", title: "\u540E\u53F0\u6A21\u578B" },
    { key: "vision", title: "\u89C6\u89C9\u987E\u95EE" }
  ];
  var DEPLOY_ITEMS = ["uv", "node", "sandbox", "embedding"];
  var DEPLOY_LABEL = { uv: "uv", node: "node", sandbox: "Docker \u6C99\u76D2", embedding: "embedding" };
  var DEPLOY_DESC = { uv: "Python \u4F9D\u8D56\u4E0E\u8FD0\u884C\u73AF\u5883", node: "\u524D\u7AEF\u5BBF\u4E3B\u4E0E\u63D2\u4EF6\u6784\u5EFA", sandbox: "Docker \u9694\u79BB\u6267\u884C\u73AF\u5883", embedding: "\u672C\u5730\u5411\u91CF\u5316\u6A21\u578B" };
  var DEPLOY_CHIP = { missing: "\u672A\u5B89\u88C5", failed: "\u5931\u8D25", running: "\u90E8\u7F72\u4E2D", installed: "\u5F85\u91CD\u542F", ready: "\u5DF2\u5C31\u7EEA" };
  var cfgState = {
    data: {},
    // tab -> 已加载的配置对象（GET /api/config/{tab}）
    mode: {},
    // tab -> 'cards'|'json'
    openKey: {},
    // tab -> 处于展开态的顶级 key
    editStr: {},
    // tab+'::'+key -> 编辑区文本
    deployLogOpen: {},
    diskLogOpen: false,
    rawSensor: {}
  };
  function makeSection(title, main) {
    const sec = HOST.document.createElement("div");
    sec.className = "settings-section";
    const t = HOST.document.createElement("div");
    t.className = "settings-section-title";
    t.textContent = title;
    sec.appendChild(t);
    main.appendChild(sec);
    return sec;
  }
  async function cfgData(tab) {
    if (!cfgState.data[tab]) {
      try {
        cfgState.data[tab] = await (await fetch("/api/config/" + tab)).json();
      } catch (e) {
        cfgState.data[tab] = {};
      }
    }
    return cfgState.data[tab];
  }
  var RELOAD_EP = { sensor: "/api/config/sensor/reload", mcp: "/api/config/mcp/reload" };
  async function reloadRuntime(tab) {
    const ep = RELOAD_EP[tab];
    if (!ep) return null;
    const r = await fetch(ep, { method: "POST" });
    const body = await r.json().catch(function() {
      return {};
    });
    if (!r.ok) throw new Error(body && body.detail || "HTTP " + r.status);
    return body;
  }
  async function putCfg(tab, obj) {
    cfgState.data[tab] = obj;
    const r = await fetch("/api/config/" + tab, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) });
    if (!r.ok) throw new Error("HTTP " + r.status);
    if (RELOAD_EP[tab]) {
      try {
        await reloadRuntime(tab);
      } catch (e) {
      }
    }
  }
  function rerenderConfig(main, key) {
    main.innerHTML = "";
    renderConfigSection(main, key);
  }
  function cfgToolbar(main, key, rerender) {
    const fn = rerender || rerenderConfig;
    const tb = HOST.document.createElement("div");
    tb.className = "cfg-toolbar";
    ["\u5361\u7247", "JSON"].forEach(function(label, i) {
      const mode = i === 0 ? "cards" : "json";
      const seg = HOST.document.createElement("button");
      seg.className = "cfg-seg" + ((cfgState.mode[key] || "cards") === mode ? " active" : "");
      seg.textContent = label;
      seg.addEventListener("click", function() {
        cfgState.mode[key] = mode;
        fn(main, key);
      });
      tb.appendChild(seg);
    });
    if (key !== "sensor") {
      const rf = HOST.document.createElement("button");
      rf.className = "cfg-seg cfg-reload";
      rf.textContent = "\u5237\u65B0";
      rf.title = "\u4E22\u5F03\u672C\u5730\u7F13\u5B58\uFF0C\u91CD\u65B0\u4ECE\u78C1\u76D8\u8BFB\u53D6\u914D\u7F6E\u5E76\u91CD\u7ED8";
      rf.addEventListener("click", function() {
        delete cfgState.data[key];
        cfgState.openKey = cfgState.openKey || {};
        delete cfgState.openKey[key];
        fn(main, key);
      });
      tb.appendChild(rf);
    }
    if (RELOAD_EP[key] && key !== "sensor") {
      const rl = HOST.document.createElement("button");
      rl.className = "cfg-seg cfg-reload";
      rl.textContent = "\u91CD\u8F7D\u5230\u5185\u5B58";
      rl.title = "\u8BA9\u78C1\u76D8\u4E0A\u7684\u914D\u7F6E\u4E0E\u4EE3\u7801\u7ACB\u5373\u751F\u6548\uFF08\u91CD\u542F\u5B50\u8FDB\u7A0B / \u91CD\u5EFA\u7D22\u5F15\uFF09\uFF0C\u65E0\u9700\u91CD\u542F\u5E94\u7528";
      rl.addEventListener("click", function() {
        rl.disabled = true;
        rl.textContent = "\u91CD\u8F7D\u4E2D\u2026";
        reloadRuntime(key).then(function(d) {
          HOST.alert(d && d.message || "\u5DF2\u91CD\u8F7D\u5230\u5185\u5B58");
        }).catch(function(e) {
          HOST.alert("\u91CD\u8F7D\u5931\u8D25\uFF1A" + (e && e.message || ""));
        }).finally(function() {
          rl.disabled = false;
          rl.textContent = "\u91CD\u8F7D\u5230\u5185\u5B58";
        });
      });
      tb.appendChild(rl);
    }
    main.appendChild(tb);
    return tb;
  }
  var CONFIG_TITLE = { plugins: "UI \u63D2\u4EF6\u8BBE\u7F6E", model: "\u6A21\u578B\u8BBE\u7F6E", sensor: "\u4F20\u611F\u5668\u8BBE\u7F6E", file: "\u6587\u4EF6\u6743\u9650\u8BBE\u7F6E", mcp: "MCP \u8BBE\u7F6E", soul: "\u5168\u5C40\u4EBA\u8BBE\u8BBE\u7F6E", acp: "ACP \u8BBE\u7F6E", deploy: "\u90E8\u7F72\u8BBE\u7F6E" };
  var REFRESH_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 6.1"/><path d="M20 4v7h-7"/></svg>';
  var EYE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  var EYE_OFF_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"/><path d="M10.6 6.3A10.7 10.7 0 0 1 12 6c6.5 0 10 6 10 6a17.6 17.6 0 0 1-2.4 3.1"/><path d="M6.6 6.6C3.6 8.6 2 12 2 12s3.5 6 10 6c1.4 0 2.7-.3 3.9-.7"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  var COPY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
  function settingsPageHead(main, key, onRefresh) {
    const head = HOST.document.createElement("div");
    head.className = "settings-page-head";
    const title = HOST.document.createElement("h2");
    title.className = "settings-page-title";
    title.textContent = CONFIG_TITLE[key] || key + "\u8BBE\u7F6E";
    const rf = HOST.document.createElement("button");
    rf.type = "button";
    rf.className = "settings-page-refresh";
    rf.title = "\u91CD\u65B0\u8BFB\u53D6\u914D\u7F6E\u6587\u4EF6";
    rf.setAttribute("aria-label", "\u5237\u65B0");
    rf.innerHTML = REFRESH_SVG;
    rf.addEventListener("click", function() {
      rf.classList.add("spinning");
      rf.disabled = true;
      delete cfgState.data[key];
      delete cfgState.openKey[key];
      if (onRefresh) onRefresh();
      else rerenderConfig(main, key);
    });
    head.appendChild(title);
    head.appendChild(rf);
    main.appendChild(head);
  }
  function renderConfigSection(main, key) {
    settingsPageHead(main, key);
    if (key === "acp") return renderAcpCard(main);
    if (key === "deploy") return renderDeployCards(main);
    if (key === "soul") return renderSoulEditor(main);
    if (key === "mcp") return renderMcpCards(main, key);
    if (key === "model") return renderModelCards(main, key);
    if (key === "file") return renderFilePermissions(main, key);
    cfgToolbar(main, key);
    if ((cfgState.mode[key] || "cards") === "json") {
      renderRawJson(main, key);
    } else if (key === "sensor") {
      renderSensorCards(main, key);
    } else {
      renderGenericCards(main, key);
    }
  }
  function renderRawJson(main, key) {
    const tx = HOST.document.createElement("textarea");
    tx.className = "settings-json";
    tx.spellcheck = false;
    tx.placeholder = "\u8BFB\u53D6\u914D\u7F6E\u2026";
    main.appendChild(tx);
    const status = HOST.document.createElement("span");
    status.className = "p-tag";
    cfgData(key).then(function(data) {
      tx.value = JSON.stringify(data, null, 2);
      status.textContent = "\u5DF2\u52A0\u8F7D";
    });
    const bar = HOST.document.createElement("div");
    bar.className = "settings-actions";
    const save = HOST.document.createElement("button");
    save.className = "btn";
    save.textContent = "\u4FDD\u5B58";
    save.addEventListener("click", function() {
      let obj;
      try {
        obj = JSON.parse(tx.value);
      } catch (e) {
        HOST.alert("JSON \u89E3\u6790\u5931\u8D25\uFF1A" + e.message);
        return;
      }
      putCfg(key, obj).then(function() {
        status.textContent = "\u5DF2\u4FDD\u5B58";
      }).catch(function(e) {
        status.textContent = "\u4FDD\u5B58\u5931\u8D25";
        HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
      });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }
  function cfgCard(main) {
    const c = HOST.document.createElement("div");
    c.className = "cfg-card";
    main.appendChild(c);
    return c;
  }
  function cfgIcon(url) {
    const wrap = HOST.document.createElement("span");
    wrap.className = "cfg-card-icon";
    const useDefault = function() {
      wrap.innerHTML = "<svg " + ICON_SVG_ATTR + ">" + ICON_SVG.sensor + "</svg>";
    };
    const u = String(url == null ? "" : url).trim();
    if (!u) {
      useDefault();
      return wrap;
    }
    const img = HOST.document.createElement("img");
    img.alt = "";
    img.referrerPolicy = "no-referrer";
    img.onerror = function() {
      if (img.parentNode) {
        img.parentNode.removeChild(img);
      }
      useDefault();
    };
    img.src = u;
    wrap.appendChild(img);
    return wrap;
  }
  function cfgCardHead(card, title, kind, sub, iconUrl) {
    const head = HOST.document.createElement("div");
    head.className = "cfg-card-head";
    const left = HOST.document.createElement("div");
    left.className = "cfg-card-head-l";
    const trow = HOST.document.createElement("div");
    trow.className = "cfg-card-title";
    if (iconUrl !== void 0) trow.appendChild(cfgIcon(iconUrl));
    const t = HOST.document.createElement("span");
    t.className = "cfg-card-name";
    t.textContent = title;
    trow.appendChild(t);
    if (kind) {
      const k = HOST.document.createElement("span");
      k.className = "cfg-chip type";
      k.textContent = kind;
      trow.appendChild(k);
    }
    left.appendChild(trow);
    if (sub) {
      const s = HOST.document.createElement("div");
      s.className = "cfg-card-sub";
      s.textContent = sub;
      left.appendChild(s);
    }
    head.appendChild(left);
    const right = HOST.document.createElement("div");
    right.className = "cfg-card-act";
    head.appendChild(right);
    card.appendChild(head);
    return { head, right, left, titleRow: trow };
  }
  function modelList(data, cat) {
    return data && data[cat] && typeof data[cat] === "object" ? Object.keys(data[cat]) : [];
  }
  function modelFormOf(entry, entryKey) {
    const e = entry || {};
    const idx = entryKey.indexOf(":");
    const sdk = idx >= 0 ? entryKey.slice(0, idx) : "openai";
    const modelName = idx >= 0 ? entryKey.slice(idx + 1) : entryKey;
    return {
      sdk: sdk || "openai",
      modelName,
      apiKey: Array.isArray(e.api_keys) && e.api_keys[0] ? e.api_keys[0] : "",
      baseUrl: e.base_url || "",
      rpm: e.rpm != null ? String(e.rpm) : "60",
      tpm: e.tpm != null ? String(e.tpm) : "1000000",
      concurrency: e.concurrency != null ? String(e.concurrency) : "3",
      maxToken: e.max_token != null ? String(e.max_token) : "500000",
      vision: !!e.vision
    };
  }
  function modelField(grid, label, input) {
    const f = HOST.document.createElement("div");
    f.className = "cfg-field";
    const lb = HOST.document.createElement("label");
    lb.className = "cfg-label";
    lb.textContent = label;
    f.appendChild(lb);
    input.className = "cfg-input";
    f.appendChild(input);
    grid.appendChild(f);
  }
  function renderModelCards(main, key) {
    cfgData(key).then(function(data) {
      MODEL_CATS.forEach(function(cat) {
        const card = cfgCard(main);
        const head = cfgCardHead(card, cat.title, "model");
        if (!data[cat.key] || typeof data[cat.key] !== "object") data[cat.key] = {};
        const keys = modelList(data, cat.key);
        (keys.length ? keys : [""]).forEach(function(entryKey) {
          renderModelForm(card, key, data, cat.key, entryKey, head.right);
        });
      });
    });
  }
  function renderModelForm(card, key, data, cat, entryKey, act) {
    const main = card.parentNode;
    const f = modelFormOf((data[cat] || {})[entryKey], entryKey);
    const body = HOST.document.createElement("div");
    body.className = "cfg-card-body";
    const grid = HOST.document.createElement("div");
    grid.className = "cfg-grid";
    const mk = HOST.document.createElement("input");
    mk.type = "text";
    mk.value = f.modelName;
    mk.addEventListener("input", function() {
      f.modelName = mk.value;
    });
    modelField(grid, "\u6A21\u578B\u540D (key \u540E\u7F00)", mk);
    const ak = HOST.document.createElement("input");
    ak.type = "password";
    ak.value = f.apiKey;
    ak.placeholder = "sk-...";
    ak.spellcheck = false;
    ak.addEventListener("input", function() {
      f.apiKey = ak.value;
    });
    modelField(grid, "API KEY", ak);
    const bu = HOST.document.createElement("input");
    bu.type = "text";
    bu.value = f.baseUrl;
    bu.placeholder = "https://api.deepseek.com";
    bu.spellcheck = false;
    bu.addEventListener("input", function() {
      f.baseUrl = bu.value;
    });
    modelField(grid, "BASE URL", bu);
    if (cat !== "vision") {
      [["rpm", "RPM"], ["tpm", "TPM"], ["concurrency", "\u5E76\u53D1\u6570"], ["maxToken", "MAX TOKEN"]].forEach(function(pair) {
        const e2 = HOST.document.createElement("input");
        e2.type = "number";
        e2.value = f[pair[0]];
        e2.addEventListener("input", function() {
          f[pair[0]] = e2.value;
        });
        modelField(grid, pair[1], e2);
      });
    }
    body.appendChild(grid);
    if (cat !== "vision") {
      const swRow = HOST.document.createElement("div");
      swRow.className = "cfg-field switch-row";
      const swl = HOST.document.createElement("label");
      swl.textContent = "\u89C6\u89C9\u76F4\u6CE8\uFF08\u628A\u56FE\u7247\u76F4\u63A5\u6CE8\u5165\u4E0A\u4E0B\u6587\uFF09";
      swRow.appendChild(swl);
      const sw = HOST.document.createElement("label");
      sw.className = "switch";
      sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
      sw.querySelector("input").checked = f.vision;
      sw.querySelector("input").addEventListener("change", function(e2) {
        f.vision = e2.target.checked;
      });
      swRow.appendChild(sw);
      body.appendChild(swRow);
    }
    const save = HOST.document.createElement("button");
    save.className = "btn cfg-save";
    save.textContent = "\u4FDD\u5B58";
    save.addEventListener("click", function() {
      const nm = f.modelName.trim();
      if (!nm) {
        HOST.alert("\u8BF7\u586B\u5199\u6A21\u578B\u540D");
        return;
      }
      const newKey = (f.sdk || "openai") + ":" + nm;
      const obj = { api_keys: [f.apiKey.trim()], base_url: f.baseUrl.trim() };
      if (cat !== "vision") {
        obj.rpm = Number(f.rpm) || 60;
        obj.tpm = Number(f.tpm) || 1e6;
        obj.concurrency = Number(f.concurrency) || 3;
        obj.max_token = Number(f.maxToken) || 5e5;
        obj.vision = f.vision;
      }
      if (entryKey && newKey !== entryKey) delete data[cat][entryKey];
      data[cat][newKey] = obj;
      putCfg(key, data).then(function() {
        rerenderConfig(main, key);
        HOST.alert("\u6A21\u578B\u5DF2\u4FDD\u5B58\u5E76\u70ED\u91CD\u8F7D\u3002");
      }).catch(function(e) {
        HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
      });
    });
    (act || card).appendChild(save);
    card.appendChild(body);
  }
  var MCP_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/></svg>';
  function renderMcpCards(main, key) {
    cfgData(key).then(function(data) {
      if (!data || typeof data !== "object" || Array.isArray(data)) data = {};
      if (!data.mcpServers || typeof data.mcpServers !== "object" || Array.isArray(data.mcpServers)) data.mcpServers = {};
      cfgState.data[key] = data;
      const servers = data.mcpServers;
      const names = Object.keys(servers);
      if (names.length === 0) {
        const empty = HOST.document.createElement("div");
        empty.className = "cfg-empty";
        empty.textContent = "\u6682\u65E0 MCP \u670D\u52A1\u5668";
        main.appendChild(empty);
        return;
      }
      const grid = HOST.document.createElement("div");
      grid.className = "entry-grid";
      main.appendChild(grid);
      names.forEach(function(name) {
        const isOpen = cfgState.openKey[key] === name;
        const val = servers[name];
        const isObj = !!val && typeof val === "object" && !Array.isArray(val);
        const kind = isObj ? val.url ? "http" : val.command ? "stdio" : "object" : Array.isArray(val) ? "array" : typeof val;
        const envCount = isObj && val.env && typeof val.env === "object" ? Object.keys(val.env).length : 0;
        const card = HOST.document.createElement("div");
        card.className = "entry-card" + (isOpen ? " is-open" : "");
        const head = HOST.document.createElement("div");
        head.className = "entry-card-head";
        const icon = HOST.document.createElement("span");
        icon.className = "cfg-card-icon";
        icon.innerHTML = MCP_ICON;
        head.appendChild(icon);
        const info = HOST.document.createElement("div");
        info.className = "entry-card-info";
        const titleRow = HOST.document.createElement("div");
        titleRow.className = "entry-card-title";
        const nm = HOST.document.createElement("span");
        nm.className = "entry-card-name";
        nm.textContent = name;
        nm.title = name;
        titleRow.appendChild(nm);
        const badge = HOST.document.createElement("span");
        badge.className = "cfg-chip type";
        badge.textContent = kind;
        titleRow.appendChild(badge);
        const meta = HOST.document.createElement("div");
        meta.className = "entry-card-meta";
        meta.textContent = (isObj && val.url ? String(val.url) : isObj && val.command ? String(val.command) : "\u672A\u914D\u7F6E\u542F\u52A8\u547D\u4EE4") + (envCount ? " \xB7 " + envCount + " \u4E2A\u73AF\u5883\u53D8\u91CF" : "");
        info.appendChild(titleRow);
        info.appendChild(meta);
        head.appendChild(info);
        const act = HOST.document.createElement("div");
        act.className = "entry-card-act";
        const reload = entryIconBtn("restart", "\u5237\u65B0\u5230\u5185\u5B58");
        reload.addEventListener("click", function() {
          reload.disabled = true;
          reload.classList.add("spinning");
          reloadRuntime(key).then(function() {
            reload.classList.remove("spinning");
            reload.disabled = false;
          }).catch(function(e) {
            reload.classList.remove("spinning");
            reload.disabled = false;
            HOST.alert("\u5237\u65B0\u5931\u8D25\uFF1A" + (e && e.message || ""));
          });
        });
        const edit = entryIconBtn("edit", isOpen ? "\u6536\u8D77" : "\u7F16\u8F91");
        if (isOpen) edit.classList.add("active");
        edit.addEventListener("click", function() {
          if (isOpen) delete cfgState.openKey[key];
          else {
            cfgState.openKey[key] = name;
            cfgState.editStr[key + "::" + name] = JSON.stringify(val, null, 2);
          }
          rerenderConfig(main, key);
        });
        const del = entryIconBtn("trash", "\u5220\u9664", true);
        del.addEventListener("click", function() {
          if (!HOST.confirm('\u5220\u9664 MCP \u670D\u52A1\u5668 "' + name + '"\uFF1F')) return;
          delete servers[name];
          delete cfgState.openKey[key];
          putCfg(key, data).then(function() {
            rerenderConfig(main, key);
          }).catch(function(e) {
            HOST.alert("\u5220\u9664\u5931\u8D25\uFF1A" + (e && e.message || ""));
          });
        });
        act.appendChild(reload);
        act.appendChild(edit);
        act.appendChild(del);
        head.appendChild(act);
        card.appendChild(head);
        if (isOpen) {
          const body = HOST.document.createElement("div");
          body.className = "entry-card-body";
          const ta = HOST.document.createElement("textarea");
          ta.className = "settings-json";
          ta.style.minHeight = "150px";
          ta.value = cfgState.editStr[key + "::" + name] || JSON.stringify(val, null, 2);
          ta.addEventListener("input", function() {
            cfgState.editStr[key + "::" + name] = ta.value;
          });
          body.appendChild(ta);
          const save = HOST.document.createElement("button");
          save.className = "btn cfg-save entry-save";
          save.textContent = "\u4FDD\u5B58\u5E76\u5237\u65B0";
          save.addEventListener("click", function() {
            let obj;
            try {
              obj = JSON.parse(cfgState.editStr[key + "::" + name]);
            } catch (e) {
              HOST.alert("JSON \u89E3\u6790\u5931\u8D25\uFF1A" + e.message);
              return;
            }
            servers[name] = obj;
            delete cfgState.openKey[key];
            save.disabled = true;
            save.textContent = "\u4FDD\u5B58\u4E2D\u2026";
            putCfg(key, data).then(function() {
              rerenderConfig(main, key);
            }).catch(function(e) {
              save.disabled = false;
              save.textContent = "\u4FDD\u5B58\u5E76\u5237\u65B0";
              HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
            });
          });
          body.appendChild(save);
          card.appendChild(body);
        }
        grid.appendChild(card);
      });
    });
  }
  var FILE_PERM_MODES = [
    { value: "readonly", label: "\u53EA\u8BFB" },
    { value: "writeonly", label: "\u53EA\u5199" },
    { value: "readwrite", label: "\u8BFB\u5199" },
    { value: "blocked", label: "\u7981\u6B62\u8BFB\u5199" }
  ];
  function normalizeFilePerm(raw) {
    const src = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
    let def = String(src.default_permission || "readonly");
    if (def === "writable") def = "readwrite";
    if (def === "none") def = "blocked";
    if (["readonly", "writeonly", "readwrite", "blocked"].indexOf(def) < 0) def = "readonly";
    const p = src.permissions && typeof src.permissions === "object" && !Array.isArray(src.permissions) ? src.permissions : {};
    const list = function(v) {
      return Array.isArray(v) ? v.map(String).filter(Boolean) : [];
    };
    return {
      default_permission: def,
      permissions: { blocked: list(p.blocked), readonly: list(p.readonly), writable: list(p.writable) }
    };
  }
  function saveFilePerm(main, key, data) {
    return putCfg(key, data).then(function() {
      rerenderConfig(main, key);
    }).catch(function(e) {
      HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
    });
  }
  function pickPermPaths(directory) {
    const pc = HOST.purrcat;
    if (!pc || !pc.openDialog) return Promise.reject(new Error("\u6587\u4EF6\u9009\u62E9\u4EC5\u5728\u684C\u9762\u7AEF\u53EF\u7528"));
    return pc.openDialog({
      directory,
      properties: directory ? ["openDirectory", "multiSelections"] : ["openFile", "multiSelections"]
    }).then(function(r) {
      return Array.isArray(r) ? r.map(String).filter(Boolean) : [];
    });
  }
  function appendPermSection(wrap, opt) {
    const sec = HOST.document.createElement("section");
    sec.className = "perm-section";
    const head = HOST.document.createElement("div");
    head.className = "perm-section-head";
    const txt = HOST.document.createElement("div");
    txt.className = "perm-section-text";
    const title = HOST.document.createElement("h3");
    title.className = "perm-section-title";
    title.textContent = opt.title;
    const desc = HOST.document.createElement("p");
    desc.className = "perm-section-desc";
    desc.textContent = opt.desc;
    txt.appendChild(title);
    txt.appendChild(desc);
    const actions = HOST.document.createElement("div");
    actions.className = "perm-actions";
    const addFile = entryIconBtn("filePlus", "\u6DFB\u52A0\u6587\u4EF6");
    addFile.addEventListener("click", function() {
      opt.onAdd(false);
    });
    const addFolder = entryIconBtn("folderPlus", "\u6DFB\u52A0\u6587\u4EF6\u5939");
    addFolder.addEventListener("click", function() {
      opt.onAdd(true);
    });
    actions.appendChild(addFile);
    actions.appendChild(addFolder);
    head.appendChild(txt);
    head.appendChild(actions);
    const group = HOST.document.createElement("div");
    group.className = "perm-group";
    if (opt.paths.length === 0) {
      const empty = HOST.document.createElement("div");
      empty.className = "perm-empty";
      empty.textContent = "\u6682\u65E0\u8DEF\u5F84";
      group.appendChild(empty);
    } else {
      opt.paths.forEach(function(path) {
        const row = HOST.document.createElement("div");
        row.className = "perm-row";
        const text = HOST.document.createElement("span");
        text.className = "perm-path";
        text.textContent = path;
        text.title = path;
        const del = entryIconBtn("trash", "\u79FB\u9664", true);
        del.addEventListener("click", function() {
          opt.onRemove(path);
        });
        row.appendChild(text);
        row.appendChild(del);
        group.appendChild(row);
      });
    }
    sec.appendChild(head);
    sec.appendChild(group);
    wrap.appendChild(sec);
  }
  function renderFilePermissions(main, key) {
    cfgData(key).then(function(raw) {
      const data = normalizeFilePerm(raw);
      cfgState.data[key] = data;
      const readAllowed = data.default_permission === "readonly" || data.default_permission === "readwrite";
      const writeAllowed = data.default_permission === "writeonly" || data.default_permission === "readwrite";
      const wrap = HOST.document.createElement("div");
      wrap.className = "perm-page";
      const defSec = HOST.document.createElement("section");
      defSec.className = "perm-section";
      const defTitle = HOST.document.createElement("h3");
      defTitle.className = "perm-section-title";
      defTitle.textContent = "\u9ED8\u8BA4\u6743\u9650";
      const defGroup = HOST.document.createElement("div");
      defGroup.className = "perm-group";
      const defRow = HOST.document.createElement("div");
      defRow.className = "perm-row";
      const defTxt = HOST.document.createElement("div");
      defTxt.className = "perm-row-text";
      const defLabel = HOST.document.createElement("div");
      defLabel.className = "perm-row-label";
      defLabel.textContent = "\u5168\u5C40\u9ED8\u8BA4\u6743\u9650";
      const defDesc = HOST.document.createElement("div");
      defDesc.className = "perm-row-desc";
      defDesc.textContent = "\u672A\u547D\u4E2D\u4EFB\u610F\u8DEF\u5F84\u89C4\u5219\u65F6\u4F7F\u7528\u7684\u8BFB\u5199\u7B56\u7565";
      defTxt.appendChild(defLabel);
      defTxt.appendChild(defDesc);
      const select = HOST.document.createElement("select");
      select.className = "cfg-input perm-select";
      FILE_PERM_MODES.forEach(function(m) {
        const o = HOST.document.createElement("option");
        o.value = m.value;
        o.textContent = m.label;
        select.appendChild(o);
      });
      select.value = data.default_permission;
      select.addEventListener("change", function() {
        data.default_permission = select.value;
        saveFilePerm(main, key, data);
      });
      defRow.appendChild(defTxt);
      defRow.appendChild(select);
      defGroup.appendChild(defRow);
      defSec.appendChild(defTitle);
      defSec.appendChild(defGroup);
      wrap.appendChild(defSec);
      if (!writeAllowed) {
        appendPermSection(wrap, {
          title: "\u53EF\u5199\u767D\u540D\u5355",
          desc: "\u5168\u5C40\u9ED8\u8BA4\u6743\u9650\u4E0D\u5305\u542B\u5199\u5165\u65F6\uFF0C\u5141\u8BB8\u5199\u5165\u7684\u8DEF\u5F84",
          paths: data.permissions.writable,
          onAdd: function(directory) {
            pickPermPaths(directory).then(function(paths) {
              if (!paths.length) return;
              paths.forEach(function(p) {
                if (data.permissions.writable.indexOf(p) < 0) data.permissions.writable.push(p);
              });
              saveFilePerm(main, key, data);
            }).catch(function(e) {
              HOST.alert(e && e.message || "\u9009\u62E9\u5931\u8D25");
            });
          },
          onRemove: function(path) {
            data.permissions.writable = data.permissions.writable.filter(function(p) {
              return p !== path;
            });
            saveFilePerm(main, key, data);
          }
        });
      }
      if (!readAllowed) {
        appendPermSection(wrap, {
          title: "\u53EF\u8BFB\u767D\u540D\u5355",
          desc: "\u5168\u5C40\u9ED8\u8BA4\u6743\u9650\u4E0D\u5305\u542B\u8BFB\u53D6\u65F6\uFF0C\u5141\u8BB8\u8BFB\u53D6\u7684\u8DEF\u5F84",
          paths: data.permissions.readonly,
          onAdd: function(directory) {
            pickPermPaths(directory).then(function(paths) {
              if (!paths.length) return;
              paths.forEach(function(p) {
                if (data.permissions.readonly.indexOf(p) < 0) data.permissions.readonly.push(p);
              });
              saveFilePerm(main, key, data);
            }).catch(function(e) {
              HOST.alert(e && e.message || "\u9009\u62E9\u5931\u8D25");
            });
          },
          onRemove: function(path) {
            data.permissions.readonly = data.permissions.readonly.filter(function(p) {
              return p !== path;
            });
            saveFilePerm(main, key, data);
          }
        });
      }
      appendPermSection(wrap, {
        title: "\u6700\u9AD8\u4F18\u5148\u7EA7\u62E6\u622A",
        desc: "\u6700\u5148\u5224\u5B9A\uFF0C\u547D\u4E2D\u540E\u65E0\u8BBA\u5168\u5C40\u9ED8\u8BA4\u6743\u9650\u5982\u4F55\u90FD\u7981\u6B62\u8BFB\u5199",
        paths: data.permissions.blocked,
        onAdd: function(directory) {
          pickPermPaths(directory).then(function(paths) {
            if (!paths.length) return;
            paths.forEach(function(p) {
              if (data.permissions.blocked.indexOf(p) < 0) data.permissions.blocked.push(p);
            });
            saveFilePerm(main, key, data);
          }).catch(function(e) {
            HOST.alert(e && e.message || "\u9009\u62E9\u5931\u8D25");
          });
        },
        onRemove: function(path) {
          data.permissions.blocked = data.permissions.blocked.filter(function(p) {
            return p !== path;
          });
          saveFilePerm(main, key, data);
        }
      });
      main.appendChild(wrap);
    });
  }
  function coerceVal(str, orig) {
    if (orig === null || orig === void 0) return str;
    const t = Array.isArray(orig) ? "array" : typeof orig;
    if (t === "number") return Number(str);
    if (t === "boolean") return str === "true" || str === "1" || str === "\u662F";
    if (t === "object") {
      try {
        return JSON.parse(str);
      } catch (e) {
        return orig;
      }
    }
    return str;
  }
  function sensorRuntimeMap() {
    return fetch("/api/config/sensor/runtime").then(function(r) {
      return r.json();
    }).then(function(d) {
      const m = {};
      (d && d.running || []).forEach(function(s) {
        m[s.name] = s;
      });
      return m;
    }).catch(function() {
      return {};
    });
  }
  function sensorJsonValue(raw, fallback) {
    if (!raw) return fallback;
    try {
      const v = JSON.parse(raw);
      return v && typeof v === "object" ? v : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function sensorFieldLabel(text) {
    const lb = HOST.document.createElement("label");
    lb.className = "cfg-label";
    lb.textContent = text;
    return lb;
  }
  function sensorMiniBtn(text, title, onClick, cls) {
    const b = HOST.document.createElement("button");
    b.type = "button";
    b.className = "btn sm" + (cls ? " " + cls : "");
    b.textContent = text;
    if (title) b.title = title;
    b.addEventListener("click", onClick);
    return b;
  }
  function renderSensorFields(body, sensorCfg, save) {
    const fields = Array.isArray(sensorCfg.fields) ? sensorCfg.fields : [];
    const env = sensorCfg.env && typeof sensorCfg.env === "object" ? sensorCfg.env : {};
    const grid = HOST.document.createElement("div");
    grid.className = "cfg-grid";
    const readers = [];
    fields.forEach(function(field) {
      const key = field.key;
      if (!key) return;
      const type = field.type || "text";
      const raw = env[key] == null ? "" : String(env[key]);
      const label = field.label || key;
      let read = function() {
        return raw;
      };
      if (type === "switch") {
        const f = HOST.document.createElement("div");
        f.className = "cfg-field";
        const row = HOST.document.createElement("div");
        row.className = "switch-row";
        row.appendChild(sensorFieldLabel(label));
        const sw = HOST.document.createElement("label");
        sw.className = "switch";
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector("input");
        let on = raw === "true" || raw === "1";
        chk.checked = on;
        chk.addEventListener("change", function() {
          on = chk.checked;
        });
        row.appendChild(sw);
        f.appendChild(row);
        if (field.help) {
          const hint = HOST.document.createElement("div");
          hint.className = "pk-hint";
          hint.textContent = field.help;
          f.appendChild(hint);
        }
        grid.appendChild(f);
        read = function() {
          return on ? "true" : "false";
        };
      } else {
        const f = HOST.document.createElement("div");
        f.className = "cfg-field" + (type === "kv" || type === "list" || type === "textarea" ? " wide" : "");
        f.appendChild(sensorFieldLabel(label));
        if (type === "select") {
          const sel = HOST.document.createElement("select");
          sel.className = "cfg-input";
          (field.options || []).forEach(function(op) {
            const o = HOST.document.createElement("option");
            const val = op && typeof op === "object" ? op.value : op;
            o.value = String(val);
            o.textContent = op && typeof op === "object" ? op.label || val : op;
            sel.appendChild(o);
          });
          const init = raw || (field.default != null ? String(field.default) : "");
          sel.value = init;
          sel.addEventListener("change", function() {
            read = function() {
              return sel.value;
            };
          });
          read = function() {
            return sel.value;
          };
          f.appendChild(sel);
        } else if (type === "number" || type === "slider") {
          const min = field.min != null ? Number(field.min) : 0;
          const max = field.max != null ? Number(field.max) : 100;
          const step = field.step != null ? Number(field.step) : 1;
          let init = raw === "" ? field.default != null ? Number(field.default) : min : Number(raw);
          if (!isFinite(init)) init = min;
          if (type === "slider") {
            const rng = HOST.document.createElement("input");
            rng.type = "range";
            rng.className = "cfg-range";
            rng.min = String(min);
            rng.max = String(max);
            rng.step = String(step);
            rng.value = String(init);
            const valEl = HOST.document.createElement("div");
            valEl.className = "range-val";
            const paint = function() {
              const span = max - min || 1;
              const pct = Math.max(0, Math.min(100, (Number(rng.value) - min) / span * 100));
              rng.style.background = "linear-gradient(90deg, var(--wm-accent) 0 " + pct + "%, #fff " + pct + "% 100%)";
              valEl.textContent = rng.value + (field.unit ? " " + field.unit : "");
            };
            rng.addEventListener("input", function() {
              paint();
              read = function() {
                return String(Number(rng.value));
              };
            });
            read = function() {
              return String(Number(rng.value));
            };
            paint();
            f.appendChild(rng);
            f.appendChild(valEl);
          } else {
            const num = HOST.document.createElement("input");
            num.type = "number";
            num.className = "cfg-input";
            num.min = String(min);
            num.max = String(max);
            num.step = String(step);
            num.value = raw === "" ? field.default != null ? field.default : "" : raw;
            read = function() {
              if (num.value === "" && field.default != null) return String(field.default);
              return num.value;
            };
            f.appendChild(num);
          }
        } else if (type === "kv") {
          let draw2 = function() {
            wrap.innerHTML = "";
            rows.forEach(function(row, i) {
              const line = HOST.document.createElement("div");
              line.className = "sensor-row";
              const ki = HOST.document.createElement("input");
              ki.className = "cfg-input";
              ki.placeholder = field.key_label || "\u952E";
              ki.value = row.k;
              ki.addEventListener("input", function() {
                row.k = ki.value;
              });
              const vi = HOST.document.createElement("input");
              vi.className = "cfg-input";
              vi.placeholder = field.value_label || "\u503C";
              vi.value = row.v;
              vi.addEventListener("input", function() {
                row.v = vi.value;
              });
              line.appendChild(ki);
              line.appendChild(vi);
              line.appendChild(sensorMiniBtn("\xD7", "\u5220\u9664\u8FD9\u6761", function() {
                rows.splice(i, 1);
                draw2();
              }, "sensor-del"));
              wrap.appendChild(line);
            });
            if (!rows.length) {
              const emp = HOST.document.createElement("div");
              emp.className = "pk-hint";
              emp.textContent = "\u8FD8\u6CA1\u6709\u6761\u76EE";
              wrap.appendChild(emp);
            }
            wrap.appendChild(sensorMiniBtn("+ \u6DFB\u52A0", "", function() {
              rows.push({ k: "", v: "" });
              draw2();
            }, "sensor-add"));
          };
          var draw = draw2;
          const dict = sensorJsonValue(raw, {});
          const rows = Object.keys(dict).map(function(k) {
            return { k, v: dict[k] == null ? "" : String(dict[k]) };
          });
          const wrap = HOST.document.createElement("div");
          wrap.className = "sensor-rows";
          draw2();
          f.appendChild(wrap);
          read = function() {
            const out = {};
            rows.forEach(function(row) {
              const k = String(row.k).trim();
              if (k) out[k] = row.v;
            });
            return JSON.stringify(out);
          };
        } else if (type === "list") {
          let draw2 = function() {
            wrap.innerHTML = "";
            rows.forEach(function(row, i) {
              const line = HOST.document.createElement("div");
              line.className = "sensor-row";
              const subs = itemFields || [{ key: "", placeholder: field.item_placeholder || "\u503C" }];
              subs.forEach(function(sub, j) {
                const inp = HOST.document.createElement("input");
                inp.className = "cfg-input";
                inp.placeholder = sub.placeholder || sub.label || sub.key || "\u503C";
                inp.value = row.vals[j] || "";
                inp.addEventListener("input", function() {
                  row.vals[j] = inp.value;
                });
                line.appendChild(inp);
              });
              line.appendChild(sensorMiniBtn("\xD7", "\u5220\u9664\u8FD9\u6761", function() {
                rows.splice(i, 1);
                draw2();
              }, "sensor-del"));
              wrap.appendChild(line);
            });
            if (!rows.length) {
              const emp = HOST.document.createElement("div");
              emp.className = "pk-hint";
              emp.textContent = "\u8FD8\u6CA1\u6709\u6761\u76EE";
              wrap.appendChild(emp);
            }
            wrap.appendChild(sensorMiniBtn("+ \u6DFB\u52A0", "", function() {
              rows.push({ vals: (itemFields || [1]).map(function() {
                return "";
              }) });
              draw2();
            }, "sensor-add"));
          };
          var draw = draw2;
          const itemFields = Array.isArray(field.item_fields) ? field.item_fields : null;
          const arr = sensorJsonValue(raw, []);
          const rows = arr.map(function(item) {
            if (itemFields) {
              const obj = item && typeof item === "object" ? item : {};
              return { vals: itemFields.map(function(sub) {
                return obj[sub.key] == null ? "" : String(obj[sub.key]);
              }) };
            }
            return { vals: [String(item == null ? "" : item)] };
          });
          const wrap = HOST.document.createElement("div");
          wrap.className = "sensor-rows";
          draw2();
          f.appendChild(wrap);
          read = function() {
            const out = [];
            rows.forEach(function(row) {
              if (itemFields) {
                const obj = {};
                let any = false;
                itemFields.forEach(function(sub, j) {
                  const v = row.vals[j] || "";
                  obj[sub.key] = v;
                  if (v.trim()) any = true;
                });
                if (any) out.push(obj);
              } else if ((row.vals[0] || "").trim()) {
                out.push(row.vals[0]);
              }
            });
            return JSON.stringify(out);
          };
        } else if (type === "textarea") {
          const ta = HOST.document.createElement("textarea");
          ta.className = "cfg-input settings-json";
          ta.style.minHeight = "96px";
          ta.value = raw;
          ta.addEventListener("input", function() {
            read = function() {
              return ta.value;
            };
          });
          read = function() {
            return ta.value;
          };
          f.appendChild(ta);
        } else {
          const inp = HOST.document.createElement("input");
          inp.type = type === "password" ? "password" : type === "url" ? "url" : "text";
          inp.className = "cfg-input";
          inp.spellcheck = false;
          inp.placeholder = field.placeholder || "";
          inp.value = raw === "" && field.default != null ? String(field.default) : raw;
          inp.addEventListener("input", function() {
            read = function() {
              return inp.value;
            };
          });
          read = function() {
            return inp.value;
          };
          if (type === "password") {
            const wrap = HOST.document.createElement("div");
            wrap.className = "cfg-secret";
            wrap.appendChild(inp);
            const eye = HOST.document.createElement("button");
            eye.type = "button";
            eye.className = "cfg-inline-icon";
            eye.title = "\u663E\u793A\u660E\u6587";
            eye.setAttribute("aria-label", "\u663E\u793A\u660E\u6587");
            eye.innerHTML = EYE_SVG;
            eye.addEventListener("click", function() {
              const show = inp.type === "password";
              inp.type = show ? "text" : "password";
              eye.innerHTML = show ? EYE_OFF_SVG : EYE_SVG;
              eye.title = show ? "\u9690\u85CF" : "\u663E\u793A\u660E\u6587";
            });
            const copy = HOST.document.createElement("button");
            copy.type = "button";
            copy.className = "cfg-inline-icon";
            copy.title = "\u590D\u5236";
            copy.setAttribute("aria-label", "\u590D\u5236");
            copy.innerHTML = COPY_SVG;
            copy.addEventListener("click", function() {
              const done = function() {
                copy.title = "\u5DF2\u590D\u5236";
                setTimeout(function() {
                  copy.title = "\u590D\u5236";
                }, 1200);
              };
              if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(inp.value).then(done).catch(function() {
                  inp.select();
                  HOST.document.execCommand("copy");
                  done();
                });
              } else {
                inp.select();
                HOST.document.execCommand("copy");
                done();
              }
            });
            wrap.appendChild(eye);
            wrap.appendChild(copy);
            f.appendChild(wrap);
          } else {
            f.appendChild(inp);
          }
        }
        if (field.help) {
          const hint = HOST.document.createElement("div");
          hint.className = "pk-hint";
          hint.textContent = field.help;
          f.appendChild(hint);
        }
        grid.appendChild(f);
      }
      readers.push({ field, key, read });
    });
    body.appendChild(grid);
    const saveBtn = HOST.document.createElement("button");
    saveBtn.className = "btn cfg-save entry-save";
    saveBtn.textContent = "\u4FDD\u5B58\u5E76\u5237\u65B0";
    saveBtn.addEventListener("click", function() {
      const nextEnv = Object.assign({}, env);
      for (var i = 0; i < readers.length; i++) {
        const r = readers[i];
        const v = r.read();
        if (r.field.required && !String(v).trim()) {
          HOST.alert("\u8BF7\u586B\u5199\uFF1A" + (r.field.label || r.key));
          return;
        }
        nextEnv[r.key] = v;
      }
      save(nextEnv);
    });
    body.appendChild(saveBtn);
  }
  function renderGenericCards(main, key) {
    cfgData(key).then(function(loaded) {
      const obj = loaded || {};
      const keys = Object.keys(obj).filter(function(k) {
        return k !== "__ARRAY_WRAPPER__";
      });
      if (keys.length === 0) {
        const e = HOST.document.createElement("div");
        e.className = "cfg-empty";
        e.textContent = "\u6682\u65E0\u914D\u7F6E\u9879";
        main.appendChild(e);
      }
      keys.forEach(function(k) {
        const val = obj[k];
        const isOpen = cfgState.openKey[key] === k;
        const card = cfgCard(main);
        const raw = typeof val === "object" ? JSON.stringify(val) : String(val);
        const sub = raw.slice(0, 90) + (raw.length > 90 ? "\u2026" : "");
        const h = cfgCardHead(card, k, Array.isArray(val) ? "array" : typeof val, sub);
        const edit = HOST.document.createElement("button");
        edit.className = "btn cfg-edit";
        edit.textContent = isOpen ? "\u5173\u95ED" : "\u7F16\u8F91";
        edit.addEventListener("click", function() {
          if (isOpen) delete cfgState.openKey[key];
          else {
            cfgState.openKey[key] = k;
            cfgState.editStr[key + "::" + k] = typeof val === "object" ? JSON.stringify(val, null, 2) : String(val);
          }
          rerenderConfig(main, key);
        });
        h.right.appendChild(edit);
        const del = HOST.document.createElement("button");
        del.className = "btn cfg-del";
        del.textContent = "\u5220\u9664";
        del.addEventListener("click", function() {
          if (!HOST.confirm('\u5220\u9664\u914D\u7F6E\u9879 "' + k + '"\uFF1F')) return;
          delete obj[k];
          delete cfgState.openKey[key];
          putCfg(key, obj).then(function() {
            rerenderConfig(main, key);
          }).catch(function(e) {
            HOST.alert("\u5220\u9664\u5931\u8D25\uFF1A" + (e && e.message || ""));
          });
        });
        h.right.appendChild(del);
        if (!isOpen) return;
        const body = HOST.document.createElement("div");
        body.className = "cfg-card-body";
        const ta = HOST.document.createElement("textarea");
        ta.className = "settings-json";
        ta.style.minHeight = "140px";
        ta.value = cfgState.editStr[key + "::" + k] || (typeof val === "object" ? JSON.stringify(val, null, 2) : String(val));
        ta.addEventListener("input", function() {
          cfgState.editStr[key + "::" + k] = ta.value;
        });
        body.appendChild(ta);
        const save = HOST.document.createElement("button");
        save.className = "btn cfg-save";
        save.textContent = "\u4FDD\u5B58\u8BE5\u914D\u7F6E\u9879";
        save.addEventListener("click", function() {
          let newVal;
          try {
            newVal = coerceVal(cfgState.editStr[key + "::" + k], val);
          } catch (e) {
            HOST.alert(e.message);
            return;
          }
          obj[k] = newVal;
          delete cfgState.openKey[key];
          putCfg(key, obj).then(function() {
            rerenderConfig(main, key);
          }).catch(function(e) {
            HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
          });
        });
        body.appendChild(save);
        card.appendChild(body);
      });
    });
  }
  var ENTRY_ACTION_ICON = {
    restart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 6.1"/><path d="M20 4v7h-7"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M9 7V5h6v2"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v5M14 11v5"/></svg>',
    filePlus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6M9 15h6"/></svg>',
    folderPlus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v6M9 14h6"/></svg>'
  };
  function entryIconBtn(name, title, danger) {
    const b = HOST.document.createElement("button");
    b.type = "button";
    b.className = "entry-icon-btn" + (danger ? " danger" : "");
    b.title = title;
    b.setAttribute("aria-label", title);
    b.innerHTML = ENTRY_ACTION_ICON[name] || "";
    return b;
  }
  function renderSensorCards(main, key) {
    Promise.all([cfgData(key), sensorRuntimeMap()]).then(function(res) {
      const obj = res[0] || {};
      const runMap = res[1] || {};
      const names = Object.keys(obj).filter(function(k) {
        return k !== "__ARRAY_WRAPPER__";
      });
      if (names.length === 0) {
        const empty = HOST.document.createElement("div");
        empty.className = "cfg-empty";
        empty.textContent = "\u6682\u65E0\u4F20\u611F\u5668";
        main.appendChild(empty);
        return;
      }
      const grid = HOST.document.createElement("div");
      grid.className = "entry-grid";
      main.appendChild(grid);
      names.forEach(function(name) {
        const val = obj[name];
        const isOpen = cfgState.openKey[key] === name;
        const rt = runMap[name];
        const running = !!(rt && rt.alive);
        const fieldCount = val && Array.isArray(val.fields) ? val.fields.length : 0;
        const card = HOST.document.createElement("div");
        card.className = "entry-card" + (isOpen ? " is-open" : "");
        const head = HOST.document.createElement("div");
        head.className = "entry-card-head";
        head.appendChild(cfgIcon(val && typeof val === "object" ? val.icon || "" : ""));
        const info = HOST.document.createElement("div");
        info.className = "entry-card-info";
        const titleRow = HOST.document.createElement("div");
        titleRow.className = "entry-card-title";
        const nm = HOST.document.createElement("span");
        nm.className = "entry-card-name";
        nm.textContent = name;
        nm.title = name;
        const st = HOST.document.createElement("span");
        st.className = "cfg-chip " + (running ? "on" : "off");
        st.textContent = running ? "\u8FD0\u884C\u4E2D" : "\u672A\u8FD0\u884C";
        if (running && rt.pid) st.title = "PID " + rt.pid;
        titleRow.appendChild(nm);
        titleRow.appendChild(st);
        const meta = HOST.document.createElement("div");
        meta.className = "entry-card-meta";
        meta.textContent = (val && val.source === "remote" ? "\u8FDC\u7A0B" : "\u672C\u5730") + " \xB7 " + (fieldCount ? fieldCount + " \u4E2A\u914D\u7F6E\u5B57\u6BB5" : "\u65E0\u5B57\u6BB5\u58F0\u660E");
        info.appendChild(titleRow);
        info.appendChild(meta);
        head.appendChild(info);
        const act = HOST.document.createElement("div");
        act.className = "entry-card-act";
        const power = entryIconBtn(running ? "stop" : "restart", running ? "\u505C\u6B62" : "\u91CD\u542F", running);
        power.addEventListener("click", function() {
          const verb = running ? "\u505C\u6B62" : "\u91CD\u542F";
          if (!HOST.confirm(verb + ' Sensor "' + name + '"\uFF1F')) return;
          power.disabled = true;
          fetch("/api/config/sensor/" + encodeURIComponent(name) + (running ? "/stop" : "/restart"), { method: "POST" }).then(function(r) {
            return r.json().then(function(b) {
              if (!r.ok) throw new Error(b && b.detail || "HTTP " + r.status);
              return b;
            });
          }).then(function(b) {
            delete cfgState.data[key];
            delete cfgState.openKey[key];
            rerenderConfig(main, key);
            if (!running && b && b.started === false) HOST.alert("\u91CD\u542F\u672A\u6210\u529F\uFF1A" + (b && b.message || "\u8BF7\u68C0\u67E5\u672C\u5730 " + name + ".py \u4E0E uv"));
          }).catch(function(e) {
            power.disabled = false;
            HOST.alert(verb + "\u5931\u8D25\uFF1A" + (e && e.message || ""));
          });
        });
        const edit = entryIconBtn("edit", isOpen ? "\u6536\u8D77" : "\u7F16\u8F91");
        if (isOpen) edit.classList.add("active");
        edit.addEventListener("click", function() {
          if (isOpen) delete cfgState.openKey[key];
          else {
            cfgState.openKey[key] = name;
            cfgState.editStr[key + "::" + name] = val && typeof val === "object" ? JSON.stringify(val, null, 2) : String(val);
          }
          rerenderConfig(main, key);
        });
        const del = entryIconBtn("trash", "\u5220\u9664", true);
        del.addEventListener("click", function(ev) {
          ev.stopPropagation();
          const owner = "sensor-" + name;
          const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + owner + '"]');
          closeSettingsMenus();
          if (wasOpen) return;
          const menu = HOST.document.createElement("div");
          menu.className = "settings-card-menu";
          menu.setAttribute("data-owner", owner);
          const conf = HOST.document.createElement("button");
          conf.className = "settings-menu-btn";
          conf.textContent = "\u5220\u9664\u914D\u7F6E";
          conf.addEventListener("click", function() {
            closeSettingsMenus();
            if (!HOST.confirm('\u5220\u9664 Sensor "' + name + '" \u7684\u914D\u7F6E\uFF1F')) return;
            delete obj[name];
            delete cfgState.openKey[key];
            putCfg(key, obj).then(function() {
              delete cfgState.data[key];
              rerenderConfig(main, key);
            }).catch(function(e) {
              HOST.alert("\u5220\u9664\u5931\u8D25\uFF1A" + (e && e.message || ""));
            });
          });
          const purge = HOST.document.createElement("button");
          purge.className = "settings-menu-btn danger";
          purge.textContent = "\u5F7B\u5E95\u5220\u9664\uFF08\u542B\u6587\u4EF6\uFF09";
          purge.addEventListener("click", function() {
            closeSettingsMenus();
            if (!HOST.confirm('\u5F7B\u5E95\u5220\u9664 Sensor "' + name + '"\uFF1F\u5C06\u6740\u6B7B\u5176\u8FDB\u7A0B\u3001\u5220\u9664\u6B63\u5F0F\u6587\u4EF6 ' + name + ".py \u5E76\u4ECE\u914D\u7F6E\u79FB\u9664\uFF0C\u4E0D\u53EF\u6062\u590D\u3002")) return;
            fetch("/api/config/sensor/" + encodeURIComponent(name) + "/purge", { method: "POST" }).then(function(r) {
              return r.json().then(function(b2) {
                if (!r.ok) throw new Error(b2 && b2.detail || "HTTP " + r.status);
                return b2;
              });
            }).then(function() {
              delete cfgState.data[key];
              delete cfgState.openKey[key];
              rerenderConfig(main, key);
            }).catch(function(e) {
              HOST.alert("\u5F7B\u5E95\u5220\u9664\u5931\u8D25\uFF1A" + (e && e.message || ""));
            });
          });
          menu.appendChild(conf);
          menu.appendChild(purge);
          HOST.document.body.appendChild(menu);
          const b = del.getBoundingClientRect();
          menu.style.right = HOST.innerWidth - b.right + "px";
          menu.style.top = b.bottom + 4 + "px";
          syncNativeCover();
        });
        act.appendChild(power);
        act.appendChild(edit);
        act.appendChild(del);
        head.appendChild(act);
        card.appendChild(head);
        if (isOpen) {
          const body = HOST.document.createElement("div");
          body.className = "entry-card-body";
          const hasSchema = val && typeof val === "object" && Array.isArray(val.fields) && val.fields.length > 0;
          const saveCfg = function(next, btn) {
            obj[name] = next;
            if (btn) {
              btn.disabled = true;
              btn.textContent = "\u4FDD\u5B58\u4E2D\u2026";
            }
            putCfg(key, obj).then(function() {
              return fetch("/api/config/sensor/reload", { method: "POST" });
            }).then(function(r) {
              if (!r.ok) throw new Error("HTTP " + r.status);
              delete cfgState.data[key];
              rerenderConfig(main, key);
            }).catch(function(e) {
              if (btn) {
                btn.disabled = false;
                btn.textContent = "\u4FDD\u5B58\u5E76\u5237\u65B0";
              }
              HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
            });
          };
          if (hasSchema) {
            renderSensorFields(body, val, function(nextEnv) {
              val.env = nextEnv;
              cfgState.editStr[key + "::" + name] = JSON.stringify(val, null, 2);
              saveCfg(val);
            });
          } else {
            const ta = HOST.document.createElement("textarea");
            ta.className = "settings-json";
            ta.style.minHeight = "140px";
            ta.value = cfgState.editStr[key + "::" + name] || (typeof val === "object" ? JSON.stringify(val, null, 2) : String(val));
            ta.addEventListener("input", function() {
              cfgState.editStr[key + "::" + name] = ta.value;
            });
            body.appendChild(ta);
            const save = HOST.document.createElement("button");
            save.className = "btn cfg-save entry-save";
            save.textContent = "\u4FDD\u5B58\u5E76\u5237\u65B0";
            save.addEventListener("click", function() {
              let next;
              try {
                next = coerceVal(cfgState.editStr[key + "::" + name], val);
              } catch (e) {
                HOST.alert(e.message);
                return;
              }
              saveCfg(next, save);
            });
            body.appendChild(save);
          }
          card.appendChild(body);
        }
        grid.appendChild(card);
      });
    });
  }
  function renderAcpCard(main) {
    const sec = makeSection("ACP \u63A5\u5165", main);
    const card = cfgCard(sec);
    const h = cfgCardHead(card, "ACP \u7F16\u8F91\u5668\u63A5\u5165", "relay");
    fetch("/api/config/acp").then(function(r) {
      return r.json();
    }).then(function(d) {
      const sub = HOST.document.createElement("div");
      sub.className = "cfg-card-sub";
      sub.textContent = "relay \u5DF2\u90E8\u7F72:" + (d.relay_deployed ? "\u662F" : "\u5426") + " \xB7 \u4E0E\u6E90\u4E00\u81F4:" + (d.relay_matches_source ? "\u662F" : "\u5426") + " \xB7 uv:" + (d.uv_found ? "\u53EF\u7528" : "\u7F3A\u5931") + (d.actual_port ? " \xB7 \u5B9E\u9645\u7AEF\u53E3:" + d.actual_port + (d.port_mismatch ? "\uFF08\u4E0E\u8BBE\u7F6E\u4E0D\u4E00\u81F4\uFF0Crelay \u751F\u6548\u7684\u662F\u5B9E\u9645\u7AEF\u53E3\uFF09" : "") : "");
      h.left.appendChild(sub);
      const body = HOST.document.createElement("div");
      body.className = "cfg-card-body";
      const grid = HOST.document.createElement("div");
      grid.className = "cfg-grid";
      const portF = HOST.document.createElement("div");
      portF.className = "cfg-field";
      const plb = HOST.document.createElement("label");
      plb.className = "cfg-label";
      plb.textContent = "\u7AEF\u53E3";
      portF.appendChild(plb);
      const port = HOST.document.createElement("input");
      port.type = "number";
      port.className = "cfg-input";
      if (d.port) port.value = d.port;
      portF.appendChild(port);
      grid.appendChild(portF);
      body.appendChild(grid);
      const ops = HOST.document.createElement("div");
      ops.className = "settings-actions";
      const enact = HOST.document.createElement("button");
      enact.className = "btn";
      enact.textContent = "\u4FDD\u5B58\u7AEF\u53E3";
      enact.addEventListener("click", function() {
        fetch("/api/config/acp", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ port: Number(port.value) }) }).then(function(r) {
          if (!r.ok) throw new Error("");
          HOST.alert("\u7AEF\u53E3\u5DF2\u66F4\u65B0");
        }).catch(function() {
          HOST.alert("\u4FDD\u5B58\u5931\u8D25");
        });
      });
      ops.appendChild(enact);
      const red = HOST.document.createElement("button");
      red.className = "btn";
      red.textContent = "\u91CD\u65B0\u90E8\u7F72 relay";
      red.addEventListener("click", function() {
        fetch("/api/config/acp/redeploy", { method: "POST" }).then(function(r) {
          if (!r.ok) throw new Error("");
          HOST.alert("\u5DF2\u91CD\u65B0\u90E8\u7F72");
        }).catch(function() {
          HOST.alert("\u90E8\u7F72\u5931\u8D25");
        });
      });
      ops.appendChild(red);
      const rtk = HOST.document.createElement("button");
      rtk.className = "btn";
      rtk.textContent = "\u91CD\u7F6E token";
      rtk.addEventListener("click", function() {
        fetch("/api/config/acp/reset-token", { method: "POST" }).then(function(r) {
          if (!r.ok) throw new Error("");
          HOST.alert("token \u5DF2\u91CD\u7F6E\uFF0Crelay \u9700\u91CD\u542F\u91CD\u8FDE");
        }).catch(function() {
          HOST.alert("\u91CD\u7F6E\u5931\u8D25");
        });
      });
      ops.appendChild(rtk);
      body.appendChild(ops);
      card.appendChild(body);
      const conf = HOST.document.createElement("div");
      conf.className = "cfg-card";
      cfgCardHead(conf, "\u5BA2\u6237\u7AEF\u914D\u7F6E", "stdio", "\u7C98\u8D34\u5230 Zed \u7684 agent_servers \u4E2D\uFF0C\u5176\u4ED6 ACP \u5BA2\u6237\u7AEF\u6309\u5404\u81EA\u683C\u5F0F\u586B\u5199");
      const cbody = HOST.document.createElement("div");
      cbody.className = "cfg-card-body";
      const tx = HOST.document.createElement("textarea");
      tx.className = "settings-json cfg-acp-json";
      tx.readOnly = true;
      tx.spellcheck = false;
      const useUv = !!d.uv_found;
      const script = "import os,runpy;runpy.run_path(os.path.expanduser('~/.purrcat/bin/acp_relay.py'), run_name='__main__')";
      tx.value = JSON.stringify({ agent_servers: { PurrCat: { command: useUv ? "uv" : "python", args: useUv ? ["run", "--no-project", "python", "-c", script] : ["-c", script] } } }, null, 2);
      cbody.appendChild(tx);
      const cbar = HOST.document.createElement("div");
      cbar.className = "settings-actions";
      const cp = HOST.document.createElement("button");
      cp.className = "btn";
      cp.textContent = "\u590D\u5236 JSON";
      cp.addEventListener("click", function() {
        let finished = false;
        function feedback(ok) {
          if (finished) return;
          finished = true;
          cp.textContent = ok ? "\u5DF2\u590D\u5236" : "\u590D\u5236\u5931\u8D25";
          setTimeout(function() {
            cp.textContent = "\u590D\u5236 JSON";
          }, 4e3);
        }
        function legacyCopy() {
          try {
            const tmp = HOST.document.createElement("textarea");
            tmp.value = tx.value;
            tmp.style.position = "fixed";
            tmp.style.opacity = "0";
            HOST.document.body.appendChild(tmp);
            tmp.focus();
            tmp.select();
            const ok = HOST.document.execCommand("copy");
            tmp.remove();
            return ok;
          } catch (e) {
            return false;
          }
        }
        if (legacyCopy()) return feedback(true);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          try {
            navigator.clipboard.writeText(tx.value).then(function() {
              feedback(true);
            }).catch(function() {
              feedback(false);
            });
          } catch (e) {
            feedback(false);
          }
        } else {
          feedback(false);
        }
      });
      cbar.appendChild(cp);
      cbody.appendChild(cbar);
      conf.appendChild(cbody);
      sec.appendChild(conf);
    }).catch(function() {
    });
    sec.appendChild(card);
  }
  function deployState(it, ov) {
    const item = ov && ov.items ? ov.items[it] : null;
    const task = ov && ov.tasks ? ov.tasks[it] : null;
    const running = task && task.state === "running";
    let state;
    if (running) state = "running";
    else if (task && task.state === "success") state = "installed";
    else if (task && task.state === "failed") state = "failed";
    else if (item && item.ready) state = "ready";
    else state = "missing";
    const clickable = state === "missing" || state === "failed";
    const text = state === "missing" ? "\u4E00\u952E\u90E8\u7F72" : state === "failed" ? "\u91CD\u65B0\u90E8\u7F72" : state === "running" ? "\u90E8\u7F72\u4E2D\u2026" : state === "installed" ? "\u5DF2\u5B89\u88C5\u5F85\u91CD\u542F" : "\u5DF2\u5C31\u7EEA";
    return { state, clickable, text, item, task };
  }
  function renderDeployCards(main) {
    const sec = makeSection("\u90E8\u7F72\u4E2D\u5FC3", main);
    const tip = HOST.document.createElement("div");
    tip.className = "cfg-tip";
    tip.textContent = "\u5B89\u88C5\u5B8C\u6210\u540E\u9700\u91CD\u542F\u5E94\u7528\u751F\u6548\uFF0C\u5EFA\u8BAE\u7F51\u7EDC\u7A33\u5B9A\u3002";
    sec.appendChild(tip);
    const list = HOST.document.createElement("div");
    list.className = "cfg-deploy-grid";
    sec.appendChild(list);
    const diskTitle = HOST.document.createElement("div");
    diskTitle.className = "settings-subgroup";
    diskTitle.textContent = "\u78C1\u76D8\u7EF4\u62A4";
    sec.appendChild(diskTitle);
    const diskWrap = HOST.document.createElement("div");
    sec.appendChild(diskWrap);
    function fmtBytes(n) {
      n = Number(n) || 0;
      const units = ["B", "KB", "MB", "GB", "TB"];
      let i = 0;
      while (n >= 1024 && i < units.length - 1) {
        n /= 1024;
        i++;
      }
      return (i === 0 ? Math.round(n) : n.toFixed(2)) + " " + units[i];
    }
    function diskAction(path, btn) {
      btn.disabled = true;
      fetch("/api/config/" + path, { method: "POST" }).then(function(r) {
        if (!r.ok) return r.json().then(function(d) {
          throw new Error(d.detail || "\u64CD\u4F5C\u51B2\u7A81");
        });
        return r.json().catch(function() {
          return {};
        });
      }).then(function(d) {
        delete cfgState.data.deploy;
        draw();
        if (d && d.message) HOST.alert(d.message);
      }).catch(function(e) {
        btn.disabled = false;
        HOST.alert("\u5931\u8D25\uFF1A" + (e && e.message || ""));
      });
    }
    function renderDisk(d) {
      diskWrap.innerHTML = "";
      if (!d) return;
      const card = HOST.document.createElement("div");
      card.className = "cfg-card";
      const head = HOST.document.createElement("div");
      head.className = "cfg-card-head";
      const left = HOST.document.createElement("div");
      left.className = "cfg-card-head-l";
      const title = HOST.document.createElement("div");
      title.className = "cfg-card-title";
      const nm = HOST.document.createElement("div");
      nm.className = "cfg-card-name";
      nm.textContent = "Docker \u6570\u636E\u76D8";
      title.appendChild(nm);
      const chip = HOST.document.createElement("span");
      if (!d.supported) {
        chip.className = "cfg-chip bad";
        chip.textContent = "\u4E0D\u53EF\u7528";
      } else if (d.dead_ratio == null) {
        chip.className = "cfg-chip off";
        chip.textContent = "\u5F85\u68C0\u6D4B";
      } else {
        chip.className = "cfg-chip " + (d.needs_compact ? "warn" : "ok");
        chip.textContent = "\u7A7A\u6D1E " + Math.round(d.dead_ratio * 100) + "%";
      }
      title.appendChild(chip);
      left.appendChild(title);
      const sub = HOST.document.createElement("div");
      sub.className = "cfg-card-sub";
      sub.textContent = d.detail || "";
      left.appendChild(sub);
      if (d.sandbox && d.sandbox.age_days != null) {
        const sub2 = HOST.document.createElement("div");
        sub2.className = "cfg-card-sub";
        sub2.textContent = "\u6C99\u76D2\u5BB9\u5668\u5DF2\u4F7F\u7528 " + d.sandbox.age_days + " \u5929" + (d.sandbox.age_days >= 14 ? "\uFF08\u4F7F\u7528\u8F83\u4E45\uFF0C\u5EFA\u8BAE\u91CD\u5EFA\u4E00\u6B21\u91CA\u653E\u53EF\u5199\u5C42\uFF09" : "");
        left.appendChild(sub2);
      }
      head.appendChild(left);
      const taskRunning = d.task && d.task.state === "running";
      const act = HOST.document.createElement("div");
      act.className = "cfg-card-act";
      const cp = HOST.document.createElement("button");
      cp.className = "btn cfg-deploy-btn " + (taskRunning ? "running" : "missing");
      cp.disabled = !d.supported || taskRunning;
      cp.textContent = taskRunning && d.task.kind === "compact" ? "\u56DE\u6536\u4E2D\u2026" : "\u4E00\u952E\u56DE\u6536";
      cp.title = "\u505C\u6B62 Docker/WSL \u540E\u7528 diskpart \u538B\u7F29 vhdx\uFF0C\u9700\u8981\u4E00\u6B21\u7BA1\u7406\u5458\u6388\u6743\uFF08UAC\uFF09";
      cp.addEventListener("click", function() {
        if (!HOST.confirm("\u4E00\u952E\u56DE\u6536\u4F1A\u77ED\u6682\u505C\u6B62 Docker \u4E0E WSL\uFF0C\u5E76\u5F39\u51FA\u4E00\u6B21\u7BA1\u7406\u5458\u6388\u6743\uFF08UAC\uFF09\u3002\u73B0\u5728\u6267\u884C\uFF1F")) return;
        diskAction("deploy/disk/compact", cp);
      });
      act.appendChild(cp);
      const pr = HOST.document.createElement("button");
      pr.className = "btn cfg-deploy-btn missing";
      pr.disabled = !d.docker_running || taskRunning;
      pr.textContent = taskRunning && d.task.kind === "prune" ? "\u6E05\u7406\u4E2D\u2026" : "\u6E05\u7406\u6784\u5EFA\u7F13\u5B58";
      pr.addEventListener("click", function() {
        diskAction("deploy/disk/prune", pr);
      });
      act.appendChild(pr);
      const rb = HOST.document.createElement("button");
      rb.className = "btn cfg-deploy-btn failed";
      rb.disabled = !d.docker_running || taskRunning;
      rb.textContent = "\u91CD\u5EFA\u6C99\u76D2";
      rb.title = "\u5220\u9664\u6C99\u76D2\u5BB9\u5668\uFF08\u53EF\u5199\u5C42\u4E0E\u5BB9\u5668\u5185\u7F13\u5B58\u6E05\u7A7A\uFF09\uFF0C\u4E0B\u6B21\u5DE5\u5177\u8C03\u7528\u81EA\u52A8\u91CD\u5EFA";
      rb.addEventListener("click", function() {
        if (!HOST.confirm("\u91CD\u5EFA\u6C99\u76D2\u5BB9\u5668\uFF1F\u5BB9\u5668\u5185 apt/pip \u88C5\u8FC7\u7684\u4F9D\u8D56\u4E0E\u7F13\u5B58\u4F1A\u4E22\u5931\uFF0C\u5DE5\u4F5C\u76EE\u5F55\u5185\u7684\u6587\u4EF6\u4E0D\u53D7\u5F71\u54CD\u3002")) return;
        diskAction("deploy/disk/rebuild", rb);
      });
      act.appendChild(rb);
      head.appendChild(act);
      card.appendChild(head);
      const needBody = d.needs_compact || taskRunning || d.task && d.task.state !== "idle" && d.task.log && d.task.log.length;
      if (needBody) {
        const body = HOST.document.createElement("div");
        body.className = "cfg-card-body";
        if (d.needs_compact) {
          const tip2 = HOST.document.createElement("div");
          tip2.className = "cfg-tip";
          tip2.style.margin = "0";
          tip2.textContent = "\u7A7A\u6D1E\u5360\u6BD4\u5DF2\u8D85\u8FC7 " + Math.round((d.threshold || 0.3) * 100) + "%\uFF08\u7EA6 " + fmtBytes(d.dead_bytes) + "\uFF09\uFF0C\u5EFA\u8BAE\u6267\u884C\u4E00\u6B21\u300C\u4E00\u952E\u56DE\u6536\u300D\uFF0C\u538B\u7F29\u540E Docker \u4F1A\u81EA\u52A8\u6062\u590D\u8FD0\u884C\u3002";
          body.appendChild(tip2);
        }
        if (d.task && d.task.log && d.task.log.length) {
          const tg = HOST.document.createElement("button");
          tg.className = "cfg-log-toggle";
          tg.textContent = cfgState.diskLogOpen ? "\u6536\u8D77\u7EF4\u62A4\u65E5\u5FD7 \u25BE" : "\u67E5\u770B\u7EF4\u62A4\u65E5\u5FD7 \u25B8";
          tg.addEventListener("click", function() {
            cfgState.diskLogOpen = !cfgState.diskLogOpen;
            renderDisk(d);
          });
          body.appendChild(tg);
          if (cfgState.diskLogOpen) {
            const lg = HOST.document.createElement("pre");
            lg.className = "settings-log";
            lg.style.minHeight = "80px";
            lg.textContent = d.task.log.join("\n");
            body.appendChild(lg);
          }
        }
        card.appendChild(body);
      }
      diskWrap.appendChild(card);
    }
    function draw() {
      cfgData("deploy").then(function(ov) {
        list.innerHTML = "";
        DEPLOY_ITEMS.forEach(function(it) {
          const st = deployState(it, ov);
          const card = HOST.document.createElement("div");
          card.className = "cfg-card cfg-deploy-card";
          const head = HOST.document.createElement("div");
          head.className = "cfg-card-head";
          const left = HOST.document.createElement("div");
          left.className = "cfg-card-head-l";
          const title = HOST.document.createElement("div");
          title.className = "cfg-card-title";
          const nm = HOST.document.createElement("div");
          nm.className = "cfg-card-name";
          nm.textContent = DEPLOY_LABEL[it];
          let chipText = DEPLOY_CHIP[st.state];
          let chipTone = st.state === "ready" ? "ok" : st.state === "failed" || st.state === "missing" ? "bad" : "warn";
          if (it === "sandbox" && st.item && st.state !== "running" && st.state !== "failed") {
            if (!st.item.docker_installed) {
              chipText = "Docker \u7F3A";
              chipTone = "bad";
            } else if (!st.item.image_ready) {
              chipText = "\u955C\u50CF\u7F3A";
              chipTone = "warn";
            } else {
              chipText = "\u5DF2\u5C31\u7EEA";
              chipTone = "ok";
            }
          }
          const chip = HOST.document.createElement("span");
          chip.className = "cfg-chip " + chipTone;
          chip.textContent = chipText;
          title.appendChild(nm);
          title.appendChild(chip);
          left.appendChild(title);
          const sub = HOST.document.createElement("div");
          sub.className = "cfg-card-sub";
          sub.textContent = st.item && st.item.detail || DEPLOY_DESC[it];
          left.appendChild(sub);
          const act = HOST.document.createElement("div");
          act.className = "cfg-card-act";
          const btn = HOST.document.createElement("button");
          btn.className = "btn cfg-deploy-btn " + st.state;
          btn.disabled = !st.clickable;
          btn.textContent = (st.state === "running" ? "\xB7\xB7\xB7 " : "") + st.text;
          btn.addEventListener("click", function() {
            if (!st.clickable) return;
            fetch("/api/config/deploy/" + it, { method: "POST" }).then(function(r) {
              if (!r.ok) return r.json().then(function(d2) {
                throw new Error(d2.detail || "\u90E8\u7F72\u51B2\u7A81");
              });
            }).then(function() {
              delete cfgState.data.deploy;
              draw();
            }).catch(function(e) {
              HOST.alert("\u5931\u8D25\uFF1A" + (e && e.message || ""));
            });
          });
          act.appendChild(btn);
          head.appendChild(left);
          head.appendChild(act);
          card.appendChild(head);
          const foot = HOST.document.createElement("div");
          foot.className = "cfg-deploy-card-foot";
          const lgToggle = HOST.document.createElement("button");
          lgToggle.className = "cfg-log-toggle";
          lgToggle.textContent = cfgState.deployLogOpen[it] ? "\u6536\u8D77\u65E5\u5FD7 \u25BE" : "\u67E5\u770B\u65E5\u5FD7 \u25B8";
          lgToggle.addEventListener("click", function() {
            cfgState.deployLogOpen[it] = !cfgState.deployLogOpen[it];
            draw();
          });
          foot.appendChild(lgToggle);
          card.appendChild(foot);
          if (cfgState.deployLogOpen[it]) {
            const lgr = HOST.document.createElement("pre");
            lgr.className = "settings-log cfg-deploy-log";
            lgr.style.minHeight = "80px";
            lgr.textContent = st.task && st.task.log && st.task.log.length ? st.task.log.join("\n") : "\uFF08\u6682\u65E0\u65E5\u5FD7\uFF09";
            card.appendChild(lgr);
          }
          list.appendChild(card);
        });
        renderDisk(ov && ov.disk);
      });
    }
    draw();
    if (deployPollT) clearInterval(deployPollT);
    setDeployPollT(setInterval(function() {
      if (!HOST.document.body.classList.contains("settings-open")) return;
      delete cfgState.data.deploy;
      if (HOST.document.activeElement && list.contains(HOST.document.activeElement)) return;
      draw();
    }, 3e3));
  }

  // ui/web-minimal/src/host/utils.ts
  function effectiveConfig(desc) {
    const sch = desc.configSchema || [];
    const stored = desc.config || {};
    const out = {};
    sch.forEach((f) => {
      if (f.default !== void 0) out[f.key] = f.default;
      else if (f.type === "switch") out[f.key] = false;
      else if (f.type === "number") out[f.key] = 0;
      else if (f.type === "select") out[f.key] = f.options && f.options[0] || "";
      else out[f.key] = "";
    });
    Object.assign(out, stored);
    return out;
  }
  function slotOfPlugin(pid) {
    return slotByPluginId[pid] || null;
  }

  // ui/web-minimal/src/host/manifest.ts
  function applyManifestState(manifest) {
    groupState.plugins = manifest.plugins || [];
    applyLayoutFromManifest(manifest.layout);
    groupState.plugins.forEach((p) => {
      configByPlugin[p.id] = effectiveConfig(p);
    });
    const railSaved = manifest.rail;
    if (railSaved && typeof railSaved === "object") {
      const stage = Number(railSaved.stage);
      railState.stage = Number.isFinite(stage) && stage >= 2 ? 1 : 0;
      railState.hidden = railSaved.hidden && typeof railSaved.hidden === "object" ? railSaved.hidden : {};
      if (Object.prototype.hasOwnProperty.call(railState.hidden, "__panel__")) {
        if (railState.hidden["__panel__"]) railState.hidden[PANEL_CONTAINER_ID] = true;
        delete railState.hidden["__panel__"];
      }
      railState.opacity = typeof railSaved.opacity === "number" ? railSaved.opacity : 1;
    }
    const savedPanel = manifest.panelContainer && typeof manifest.panelContainer === "object" ? manifest.panelContainer : {};
    setPanelSavedWidth(Number(savedPanel.width) >= 260 ? Number(savedPanel.width) : null);
    panelContainerCfg.opacity = typeof savedPanel.opacity === "number" ? savedPanel.opacity : 0.9;
    if (panelSavedWidth != null) setPanelDesiredWidth(panelSavedWidth);
    configByPlugin["panel-container"] = Object.assign({}, savedPanel);
    const savedActive = manifest.active && typeof manifest.active === "object" ? manifest.active : {};
    const ids = new Set(groupState.plugins.map((p) => p.id));
    Object.keys(activeBySlot).forEach((k) => delete activeBySlot[k]);
    panelTabs.length = 0;
    Object.keys(savedActive).forEach((k) => {
      const v = savedActive[k];
      if (k === "__panelTabs__") {
        activeBySlot[k] = String(v);
        try {
          const arr = JSON.parse(v);
          if (Array.isArray(arr)) {
            panelTabs.length = 0;
            panelTabs.push.apply(panelTabs, arr.filter((x) => typeof x === "string"));
          }
        } catch (_) {
        }
        return;
      }
      if (v === "__none__" || ids.has(v)) activeBySlot[k] = v;
    });
  }
  async function loadManifest() {
    const manifest = await (await fetch("/api/webmin/manifest")).json();
    applyManifestState(manifest);
  }
  async function reloadManifest() {
    await loadManifest();
    await loadPanelShell();
    buildSlotIndex();
    mountAll();
    applyPersistedHidden();
    buildRail();
    applyPanelContainerCfg();
  }

  // ui/web-minimal/src/host/settings-appearance.ts
  function setSettingsOpen(open) {
    HOST.document.body.classList.toggle("settings-open", !!open);
    const sb = HOST.document.getElementById("railSettings");
    if (sb) {
      sb.classList.toggle("on", !!open);
      sb.classList.toggle("off", !open);
    }
    if (!open) closeSettingsMenus();
    if (open) renderSettings();
    syncNativeCover();
  }
  var settingsRenderT = null;
  function scheduleSettingsRender() {
    if (settingsRenderT != null) clearTimeout(settingsRenderT);
    settingsRenderT = setTimeout(renderSettings, 250);
  }
  function settingsSave(pid, cfg) {
    callAction("config.set", { plugin_id: pid, config: cfg }).catch(() => {
    });
  }
  function cfgRangeField(grid, label, min, max, step, value, fmt, onInput) {
    const f = HOST.document.createElement("div");
    f.className = "cfg-field";
    const lb = HOST.document.createElement("label");
    lb.className = "cfg-label";
    lb.textContent = label;
    f.appendChild(lb);
    const rng = HOST.document.createElement("input");
    rng.type = "range";
    rng.className = "cfg-range";
    rng.min = String(min);
    rng.max = String(max);
    rng.step = String(step);
    rng.value = String(value);
    const valEl = HOST.document.createElement("div");
    valEl.className = "range-val";
    function upd() {
      valEl.textContent = fmt(Number(rng.value));
    }
    function paint() {
      const span = Number(max) - Number(min) || 1;
      const pct = Math.max(0, Math.min(100, (Number(rng.value) - Number(min)) / span * 100));
      rng.style.background = "linear-gradient(90deg, var(--wm-accent) 0 " + pct + "%, #fff " + pct + "% 100%)";
    }
    rng.addEventListener("input", function() {
      paint();
      upd();
      onInput(Number(rng.value));
    });
    upd();
    paint();
    f.appendChild(rng);
    f.appendChild(valEl);
    grid.appendChild(f);
  }
  function transparencyField(grid, label, alphaMin, alphaValue, step, onAlpha) {
    const a = Math.min(1, Math.max(alphaMin, alphaValue));
    cfgRangeField(
      grid,
      label,
      0,
      Number((1 - alphaMin).toFixed(4)),
      step,
      Number((1 - a).toFixed(4)),
      function(t) {
        return label + " " + t.toFixed(2);
      },
      function(t) {
        onAlpha(Number((1 - t).toFixed(4)));
      }
    );
  }
  function renderLayoutSettings(container) {
    const card = HOST.document.createElement("div");
    card.className = "cfg-card";
    cfgCardHead(card, "\u5E03\u5C40\u6A21\u5F0F", "\u5BBF\u4E3B", "\u5BB9\u5668\u5F0F\u4FDD\u6301\u73B0\u72B6\uFF1B\u5E73\u94FA\u5F0F\u5C06\u7A97\u53E3\u6A2A\u5411\u6392\u5217\uFF0C\u53EF\u6EDA\u52A8\u3001\u6392\u5E8F\u4E0E\u6539\u5BBD");
    const body = HOST.document.createElement("div");
    body.className = "cfg-card-body";
    const grid = HOST.document.createElement("div");
    grid.className = "cfg-grid one-col";
    const row = HOST.document.createElement("div");
    row.className = "cfg-field";
    const lb = HOST.document.createElement("label");
    lb.className = "cfg-label";
    lb.textContent = "\u6A21\u5F0F";
    row.appendChild(lb);
    const seg = HOST.document.createElement("div");
    seg.className = "cfg-seg-row";
    const modes = [["container", "\u5BB9\u5668\u5F0F"], ["tile", "\u5E73\u94FA\u5F0F"]];
    modes.forEach(function([mode, label]) {
      const btn = HOST.document.createElement("button");
      btn.className = "cfg-seg" + (layoutState.mode === mode ? " active" : "");
      btn.textContent = label;
      btn.addEventListener("click", function() {
        if (layoutState.mode === mode) return;
        setLayoutMode(mode);
        renderSettings();
      });
      seg.appendChild(btn);
    });
    row.appendChild(seg);
    grid.appendChild(row);
    const tip = HOST.document.createElement("div");
    tip.className = "cfg-tip";
    tip.textContent = layoutState.mode === "tile" ? "\u5E73\u94FA\u6A21\u5F0F\uFF1A\u5217\u8868\u4F4D\u3001\u5DF2\u6253\u5F00\u9762\u677F\u3001\u4F1A\u8BDD\u4F4D\u5404\u4E3A\u72EC\u7ACB\u7A97\u53E3\uFF0C\u6309\u5F00\u542F\u65F6\u95F4\u4ECE\u5DE6\u5230\u53F3\u6392\u5217\uFF08\u91CD\u5F00\u8FFD\u52A0\u5230\u6700\u53F3\uFF09\uFF1B\u6700\u53F3\u4FA7\u300C+\u300D\u7A97\u53E3\u7EDF\u4E00\u5F00\u5173\u63D2\u4EF6\u3002\u6309\u4F4F Shift \u5DE6\u53F3\u62D6\u8DDF\u624B\u6392\u5E8F\u3001\u5411\u4E0B\u62D6\u8FC7\u7A97\u53E3\u4E00\u534A\u5173\u95ED\uFF1B\u62D6\u53F3\u7F18\u6539\u5BBD\u3002" : "\u5BB9\u5668\u5F0F\uFF1A\u5217\u8868\u4F4D\u3001\u4E2D\u680F\u9762\u677F\u5BB9\u5668\uFF08\u591A\u6807\u7B7E\uFF09\u3001\u4F1A\u8BDD\u4F4D\u3002";
    grid.appendChild(tip);
    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }
  function renderRailAppearance(container) {
    const card = HOST.document.createElement("div");
    card.className = "cfg-card";
    cfgCardHead(card, "\u5916\u89C2\u8BBE\u7F6E", "\u5BBF\u4E3B", "\u6700\u5DE6\u56FE\u6807\u680F\u5916\u89C2 \xB7 \u900F\u660E\u5EA6\u5B9E\u65F6\u751F\u6548");
    const body = HOST.document.createElement("div");
    body.className = "cfg-card-body";
    const grid = HOST.document.createElement("div");
    grid.className = "cfg-grid one-col";
    const o = typeof railState.opacity === "number" ? railState.opacity : 1;
    transparencyField(grid, "\u900F\u660E\u5EA6", 0.15, o, 0.05, function(v) {
      railState.opacity = v;
      applyRailOpacity();
      persistRail().catch(() => {
      });
    });
    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }
  function settingsSavePanel() {
    const persist = { opacity: panelContainerCfg.opacity };
    if (panelSavedWidth != null) persist.width = panelSavedWidth;
    configByPlugin["panel-container"] = persist;
    applyPanelContainerCfg();
    saveConfig().catch(() => {
    });
  }
  function renderPanelContainerSettings(container) {
    const card = HOST.document.createElement("div");
    card.className = "cfg-card";
    cfgCardHead(card, "\u5BB9\u5668\u8BBE\u7F6E", "\u5BBF\u4E3B", "\u4E2D\u680F\u7CFB\u7EDF\u7EA7\u5BB9\u5668 \xB7 \u900F\u660E\u5EA6\u4E0E\u9ED8\u8BA4\u5BBD\u5EA6");
    const body = HOST.document.createElement("div");
    body.className = "cfg-card-body";
    const grid = HOST.document.createElement("div");
    grid.className = "cfg-grid one-col";
    const o = Number(panelContainerCfg.opacity);
    transparencyField(grid, "\u900F\u660E\u5EA6", 0.15, o >= 0.15 && o <= 1 ? o : 1, 0.05, function(v) {
      panelContainerCfg.opacity = v;
      applyPanelContainerCfg();
      settingsSavePanel();
    });
    const wf = HOST.document.createElement("div");
    wf.className = "cfg-field";
    const wl = HOST.document.createElement("label");
    wl.className = "cfg-label";
    wl.textContent = "\u9ED8\u8BA4\u5BBD\u5EA6 (px)";
    wf.appendChild(wl);
    const num = HOST.document.createElement("input");
    num.type = "number";
    num.min = "260";
    num.step = "10";
    num.className = "cfg-input";
    num.placeholder = "\u7559\u7A7A = \u6700\u5927\u8212\u5C55";
    num.value = panelSavedWidth != null ? String(panelSavedWidth) : "";
    num.addEventListener("change", function() {
      if (!num.value) {
        setPanelSavedWidth(null);
        setPanelDesiredWidth(null);
        applyPanelWidth();
        settingsSavePanel();
        return;
      }
      const w = Number(num.value);
      if (w >= 260) {
        setPanelSavedWidth(w);
        setPanelDesiredWidth(w);
        applyPanelWidth();
        settingsSavePanel();
      } else {
        HOST.alert("\u5BBD\u5EA6\u4E0D\u80FD\u5C0F\u4E8E 260px");
        num.value = panelSavedWidth != null ? String(panelSavedWidth) : "";
      }
    });
    wf.appendChild(num);
    grid.appendChild(wf);
    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }

  // ui/web-minimal/src/host/settings-cards.ts
  var DEP_KIND_LABEL = { skill: "\u6280\u80FD", plugin: "\u63D2\u4EF6", mcp: "MCP", agentloop: "AgentLoop", sensor: "\u4F20\u611F\u5668", graph: "\u56FE\u8C31" };
  var ROOT_KIND_LABEL = { builtin: "\u5185\u7F6E", sandbox: "\u6C99\u76D2", user: "\u7528\u6237" };
  function renderPluginMeta(card, p) {
    const row = HOST.document.createElement("div");
    row.className = "cfg-card-meta";
    const chip = (text, cls) => {
      const el = HOST.document.createElement("span");
      el.className = "p-tag" + (cls ? " " + cls : "");
      el.textContent = text;
      return el;
    };
    if (p.root && p.rootOk === false) {
      row.appendChild(chip("\u58F0\u660E " + (ROOT_KIND_LABEL[p.root] || p.root), "warn"));
      row.appendChild(chip("\u26A0 \u653E\u7F6E\u4F4D\u7F6E\u4E0E\u58F0\u660E\u4E0D\u4E00\u81F4", "warn"));
    }
    const deps = Array.isArray(p.dependency) ? p.dependency : [];
    if (deps.length) {
      const lb = HOST.document.createElement("span");
      lb.className = "meta-label";
      lb.textContent = "\u4F9D\u8D56";
      row.appendChild(lb);
      deps.forEach((d) => row.appendChild(chip((DEP_KIND_LABEL[d.type] || d.type) + " \xB7 " + d.id)));
    }
    if (row.childNodes.length) card.appendChild(row);
  }
  function renderPluginCard(container, p, cfg) {
    const type = (p.slotDef || {}).type || "fixed";
    const typeName = type === "fixed" ? "\u56FA\u5B9A" : type === "panel" ? "\u9762\u677F" : type === "modal" ? "\u6A21\u6001" : "\u6D6E\u7A97";
    const vis = pluginVisible(p);
    const card = HOST.document.createElement("div");
    card.className = "cfg-card";
    const h = cfgCardHead(card, p.name || p.id, typeName, p.id);
    const st = HOST.document.createElement("span");
    st.className = "cfg-chip " + (vis ? "on" : "off");
    st.textContent = type === "panel" ? vis ? "\u663E\u793A\u4E2D" : "\u672A\u663E\u793A" : vis ? "\u5DF2\u542F\u7528" : "\u5DF2\u5173\u95ED";
    h.titleRow.appendChild(st);
    const originName = ROOT_KIND_LABEL[p.origin || ""] || p.origin || "";
    if (originName) {
      const oc = HOST.document.createElement("span");
      oc.className = "cfg-chip type";
      oc.textContent = originName;
      h.titleRow.appendChild(oc);
    }
    const tg = HOST.document.createElement("button");
    tg.className = "btn cfg-edit";
    tg.textContent = vis ? "\u5173\u95ED" : "\u6253\u5F00";
    tg.addEventListener("click", function() {
      togglePluginOpen(p);
      renderSettings();
    });
    h.right.appendChild(tg);
    const menuBtn = HOST.document.createElement("button");
    menuBtn.className = "btn icon menu-btn";
    menuBtn.textContent = "\u25BE";
    menuBtn.title = "\u66F4\u591A\u64CD\u4F5C";
    menuBtn.addEventListener("click", function(ev) {
      openPluginCardMenu(ev, menuBtn, p);
    });
    h.right.appendChild(menuBtn);
    renderPluginMeta(card, p);
    if (p.configSchema && p.configSchema.length) {
      const body = HOST.document.createElement("div");
      body.className = "cfg-card-body";
      const grid = HOST.document.createElement("div");
      grid.className = "cfg-grid one-col";
      renderFields(grid, p, cfg);
      body.appendChild(grid);
      card.appendChild(body);
    } else {
      const body = HOST.document.createElement("div");
      body.className = "cfg-card-body";
      const none = HOST.document.createElement("span");
      none.className = "p-tag";
      none.textContent = "\u8BE5\u63D2\u4EF6\u65E0\u914D\u7F6E\u9879";
      body.appendChild(none);
      card.appendChild(body);
    }
    container.appendChild(card);
  }
  function renderFields(grid, p, cfg) {
    (p.configSchema || []).forEach(function(field) {
      const key = field.key;
      const type = field.type || "text";
      const label = field.label || key;
      if (type === "switch") {
        const row = HOST.document.createElement("div");
        row.className = "cfg-field switch-row";
        const lb2 = HOST.document.createElement("label");
        lb2.className = "cfg-label";
        lb2.textContent = label;
        row.appendChild(lb2);
        const sw = HOST.document.createElement("label");
        sw.className = "switch";
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector("input");
        if (!chk) return;
        chk.checked = !!cfg[key];
        chk.addEventListener("change", function() {
          cfg[key] = chk.checked;
          settingsSave(p.id, cfg);
        });
        row.appendChild(sw);
        grid.appendChild(row);
        return;
      }
      if (type === "range") {
        let fv = cfg[key];
        const initVal = typeof fv === "number" && !isNaN(fv) ? fv : field.default != null ? field.default : field.max != null ? field.max : 1;
        const min0 = field.min != null ? field.min : 0;
        const step0 = field.step != null ? field.step : 0.01;
        const applyVal = function(v) {
          cfg[key] = v;
          settingsSave(p.id, cfg);
        };
        if (key === "opacity") {
          transparencyField(grid, label, min0, initVal, step0, applyVal);
        } else {
          cfgRangeField(
            grid,
            label,
            min0,
            field.max != null ? field.max : 1,
            step0,
            initVal,
            function(v) {
              return label + " " + v.toFixed(2);
            },
            applyVal
          );
        }
        return;
      }
      if (type === "plugin-multi") {
        const f2 = HOST.document.createElement("div");
        f2.className = "cfg-field wide";
        const lb2 = HOST.document.createElement("label");
        lb2.className = "cfg-label";
        lb2.textContent = label;
        f2.appendChild(lb2);
        const box = HOST.document.createElement("div");
        box.className = "plugin-picker";
        let sel = Array.isArray(cfg[key]) ? cfg[key].slice() : [];
        const cands = (groupState.plugins || []).filter(function(x) {
          return x.id !== p.id && x.entry;
        });
        if (!cands.length) {
          const emp = HOST.document.createElement("div");
          emp.className = "p-tag";
          emp.textContent = "\u6CA1\u6709\u53EF\u6DFB\u52A0\u7684\u63D2\u4EF6";
          box.appendChild(emp);
        }
        cands.forEach(function(pl) {
          const row = HOST.document.createElement("div");
          row.className = "pk-row";
          const info = HOST.document.createElement("div");
          info.className = "pk-info";
          const nm = HOST.document.createElement("div");
          nm.className = "pk-name";
          nm.textContent = pl.name || pl.id;
          info.appendChild(nm);
          const area = HOST.document.createElement("div");
          area.className = "pk-area";
          const slotArea = (pl.slotDef || {}).area || "";
          const areaName = AREA_LABEL[slotArea] || slotArea;
          area.textContent = pl.id + (areaName ? " \xB7 " + areaName : "");
          info.appendChild(area);
          row.appendChild(info);
          const sw = HOST.document.createElement("label");
          sw.className = "switch";
          sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
          const chk = sw.querySelector("input");
          if (!chk) return;
          chk.checked = sel.indexOf(pl.id) >= 0;
          chk.addEventListener("change", function() {
            if (chk.checked) {
              if (sel.indexOf(pl.id) < 0) sel.push(pl.id);
            } else sel = sel.filter(function(x) {
              return x !== pl.id;
            });
            cfg[key] = sel;
            settingsSave(p.id, cfg);
          });
          row.appendChild(sw);
          box.appendChild(row);
        });
        f2.appendChild(box);
        const hint = HOST.document.createElement("div");
        hint.className = "pk-hint";
        hint.textContent = "\u52FE\u9009\u540E\u51FA\u73B0\u5728\u4FA7\u680F\u300C\u5FEB\u6377\u680F\u300D\uFF0C\u70B9\u51FB\u5373\u53EF\u5524\u8D77\u5BF9\u5E94\u63D2\u4EF6\u3002";
        f2.appendChild(hint);
        grid.appendChild(f2);
        return;
      }
      const f = HOST.document.createElement("div");
      f.className = "cfg-field" + (type === "wallpapers" ? " wide" : "");
      const lb = HOST.document.createElement("label");
      lb.className = "cfg-label";
      lb.textContent = label;
      f.appendChild(lb);
      if (type === "select") {
        const sel = HOST.document.createElement("select");
        sel.className = "cfg-input";
        (field.options || []).forEach(function(op) {
          const o2 = HOST.document.createElement("option");
          o2.value = op;
          o2.textContent = op;
          sel.appendChild(o2);
        });
        sel.value = cfg[key] || "";
        sel.addEventListener("change", function() {
          cfg[key] = sel.value;
          settingsSave(p.id, cfg);
        });
        f.appendChild(sel);
      } else if (type === "number") {
        const num = HOST.document.createElement("input");
        num.type = "number";
        num.step = "any";
        num.className = "cfg-input";
        num.value = cfg[key] == null ? "" : cfg[key];
        num.addEventListener("change", function() {
          cfg[key] = num.value === "" ? null : Number(num.value);
          settingsSave(p.id, cfg);
        });
        f.appendChild(num);
      } else if (type === "wallpapers") {
        let isV2 = function(url) {
          return /\.(mp4|webm|mov)(\?|$)/i.test(url);
        }, draw2 = function() {
          wallsWrap.innerHTML = "";
          list.forEach(function(w, i) {
            const t = HOST.document.createElement("div");
            t.className = "wall-thumb";
            if (isV2(w.src || "")) {
              const v = HOST.document.createElement("video");
              v.src = w.src;
              v.muted = true;
              v.loop = true;
              t.appendChild(v);
            } else {
              const im = HOST.document.createElement("img");
              im.src = w.src;
              im.alt = "";
              t.appendChild(im);
            }
            const del = HOST.document.createElement("button");
            del.className = "wall-del";
            del.textContent = "\xD7";
            del.addEventListener("click", function() {
              list.splice(i, 1);
              commit2();
              draw2();
            });
            t.appendChild(del);
            wallsWrap.appendChild(t);
          });
          const add = HOST.document.createElement("button");
          add.className = "btn sm";
          add.textContent = "+ \u6DFB\u52A0";
          add.addEventListener("click", function() {
            callAction("dialog.pickWallpaper", {}).then(function(up) {
              const r = up;
              if (!r || !r.url) return;
              list.push({ src: r.url, type: isV2(r.url) ? "video" : "image", name: r.filename });
              cfg.mode = "wallpaper";
              commit2();
              draw2();
              scheduleSettingsRender();
            }).catch(function() {
            });
          });
          wallsWrap.appendChild(add);
        }, commit2 = function() {
          cfg[key] = list;
          settingsSave(p.id, cfg);
        };
        var isV = isV2, draw = draw2, commit = commit2;
        const wallsWrap = HOST.document.createElement("div");
        wallsWrap.className = "walls";
        const list = Array.isArray(cfg[key]) ? cfg[key] : [];
        draw2();
        f.appendChild(wallsWrap);
      } else {
        const txt = HOST.document.createElement("input");
        txt.type = "text";
        txt.className = "cfg-input";
        txt.value = cfg[key] || "";
        txt.addEventListener("change", function() {
          cfg[key] = txt.value;
          settingsSave(p.id, cfg);
        });
        f.appendChild(txt);
      }
      grid.appendChild(f);
    });
  }

  // ui/web-minimal/src/host/settings-tabs.ts
  var CONFIG_NAV = ["plugins", "model", "sensor", "file", "mcp", "soul", "acp", "deploy"];
  var CONFIG_LABEL = { plugins: "UI \u63D2\u4EF6", model: "\u6A21\u578B", sensor: "\u4F20\u611F\u5668", file: "\u6587\u4EF6\u6743\u9650", mcp: "MCP", soul: "\u5168\u5C40\u4EBA\u8BBE", acp: "ACP", deploy: "\u90E8\u7F72" };
  var settingsTab = "plugins";
  var settingsRenderedTab = "";
  var deployPollT = null;
  function setSettingsTab(v) {
    settingsTab = v;
  }
  function setDeployPollT(v) {
    deployPollT = v;
  }
  function renderSettings() {
    const bodyEl = HOST.document.querySelector('[data-layer="settings"] .settings-body');
    if (!bodyEl) return;
    if (deployPollT) {
      clearInterval(deployPollT);
      deployPollT = null;
    }
    closeSettingsMenus();
    const prevMain = bodyEl.querySelector(".settings-main");
    const keepTop = settingsRenderedTab === settingsTab && prevMain ? prevMain.scrollTop : 0;
    bodyEl.innerHTML = "";
    const nav = HOST.document.createElement("div");
    nav.className = "settings-nav";
    CONFIG_NAV.forEach(function(key) {
      const it = HOST.document.createElement("button");
      it.className = "settings-nav-item" + (settingsTab === key ? " active" : "");
      it.textContent = CONFIG_LABEL[key] || key;
      it.addEventListener("click", function() {
        settingsTab = key;
        renderSettings();
      });
      nav.appendChild(it);
    });
    bodyEl.appendChild(nav);
    const main = HOST.document.createElement("div");
    main.className = "settings-main";
    bodyEl.appendChild(main);
    if (settingsTab === "plugins") renderPluginsTab(main);
    else renderConfigSection(main, settingsTab);
    settingsRenderedTab = settingsTab;
    if (keepTop) {
      main.scrollTop = keepTop;
      const mo = new MutationObserver(function() {
        main.scrollTop = keepTop;
        mo.disconnect();
      });
      mo.observe(main, { childList: true, subtree: true });
      setTimeout(function() {
        mo.disconnect();
      }, 2e3);
    }
  }
  var AREA_LABEL = {
    session: "\u4F1A\u8BDD\u4F4D",
    "panel-container": "\u9762\u677F\u5BB9\u5668",
    popup: "\u5F39\u7A97\u7C7B",
    sidebar: "\u5217\u8868\u4F4D",
    background: "\u80CC\u666F",
    rail: "\u5DE6\u4FA7\u767D\u6761",
    panel: "\u9762\u677F",
    pet: "\u6D6E\u7A97\u7C7B",
    settings: "\u8BBE\u7F6E",
    // 宿主固有入口，独立归类的伪区域
    layout: "\u754C\u9762\u5E03\u5C40"
  };
  var UI_GROUPS = [
    { area: "layout", host: renderLayoutSettings },
    { area: "rail", host: renderRailAppearance },
    { area: "sidebar", singleton: true },
    { area: "session", singleton: true },
    { area: "background", singleton: true },
    { area: "panel-container", singleton: true, host: renderPanelContainerSettings },
    { area: "panel" },
    { area: "pet" },
    { area: "popup" }
  ];
  function cfgFor(p) {
    return Object.assign({}, configByPlugin[p.id] || {});
  }
  function renderPluginsTab(main) {
    settingsPageHead(main, "plugins", function() {
      reloadManifest().then(function() {
        renderSettings();
      });
    });
    cfgToolbar(main, "plugins", function(m) {
      m.innerHTML = "";
      renderPluginsTab(m);
    });
    if ((cfgState.mode["plugins"] || "cards") === "json") {
      renderWebminJson(main);
      return;
    }
    UI_GROUPS.forEach(function(grp) {
      if (tileMode() && grp.area === "panel-container") return;
      renderPluginGroup(main, grp);
    });
  }
  function renderWebminJson(main) {
    const tip = HOST.document.createElement("div");
    tip.className = "cfg-tip";
    tip.textContent = "\u6781\u7B80 UI \u5BBF\u4E3B\u914D\u7F6E\uFF1Aplugins=\u5404\u63D2\u4EF6\u914D\u7F6E \xB7 rail=\u56FE\u6807\u680F\u72B6\u6001 \xB7 active=\u5355\u4F8B\u69FD\u9009\u4E2D\u9879\u3002\u4FDD\u5B58\u540E\u7ACB\u5373\u751F\u6548\u5E76\u91CD\u5EFA\u754C\u9762\u3002";
    main.appendChild(tip);
    const tx = HOST.document.createElement("textarea");
    tx.className = "settings-json";
    tx.spellcheck = false;
    tx.placeholder = "\u8BFB\u53D6\u914D\u7F6E\u2026";
    main.appendChild(tx);
    const status = HOST.document.createElement("span");
    status.className = "p-tag";
    fetch("/api/webmin/config").then(function(r) {
      return r.json();
    }).then(function(cfg) {
      tx.value = JSON.stringify(cfg, null, 2);
      status.textContent = "\u5DF2\u52A0\u8F7D";
    }).catch(function() {
      status.textContent = "\u52A0\u8F7D\u5931\u8D25";
    });
    const bar = HOST.document.createElement("div");
    bar.className = "settings-actions";
    const save = HOST.document.createElement("button");
    save.className = "btn cfg-save";
    save.textContent = "\u4FDD\u5B58\u5E76\u5E94\u7528";
    save.addEventListener("click", function() {
      let obj;
      try {
        obj = JSON.parse(tx.value);
      } catch (e) {
        HOST.alert("JSON \u89E3\u6790\u5931\u8D25\uFF1A" + e.message);
        return;
      }
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
        HOST.alert("\u9876\u5C42\u5FC5\u987B\u662F JSON \u5BF9\u8C61");
        return;
      }
      save.disabled = true;
      status.textContent = "\u4FDD\u5B58\u4E2D\u2026";
      fetch("/api/webmin/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) }).then(function(r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
      }).then(function() {
        return reloadManifest();
      }).then(function() {
        status.textContent = "\u5DF2\u4FDD\u5B58\u5E76\u5E94\u7528";
        renderSettings();
      }).catch(function(e) {
        save.disabled = false;
        status.textContent = "\u4FDD\u5B58\u5931\u8D25";
        HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
      });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }
  function renderSoulEditor(main) {
    const tip = HOST.document.createElement("div");
    tip.className = "cfg-tip";
    tip.textContent = "\u5168\u5C40\u4EBA\u8BBE SOUL.md\uFF1A\u53EA\u6709\u5728 AgentLoop / Graph \u7B49\u6D41\u7A0B\u4E2D\u663E\u5F0F\u5F15\u7528 @SOUL \u65F6\uFF0C\u6B64\u5185\u5BB9\u624D\u4F1A\u6CE8\u5165\u5BF9\u5E94 Agent\uFF08\u662F\u5426\u6CE8\u5165\u53D6\u51B3\u4E8E\u5177\u4F53\u5B9E\u73B0\uFF09\uFF0C\u5E76\u975E\u6240\u6709 Agent \u81EA\u52A8\u643A\u5E26\uFF08\u843D\u76D8 ~/.purrcat/core/SOUL.md\uFF09\u3002";
    main.appendChild(tip);
    const tx = HOST.document.createElement("textarea");
    tx.className = "settings-json";
    tx.spellcheck = false;
    tx.placeholder = "\u8BFB\u53D6\u4E2D\u2026";
    main.appendChild(tx);
    const status = HOST.document.createElement("span");
    status.className = "p-tag";
    fetch("/api/config/markdown/SOUL").then(function(r) {
      return r.json();
    }).then(function(d) {
      tx.value = d && d.content || "";
      status.textContent = "\u5DF2\u52A0\u8F7D";
    }).catch(function() {
      status.textContent = "\u52A0\u8F7D\u5931\u8D25";
    });
    const bar = HOST.document.createElement("div");
    bar.className = "settings-actions";
    const save = HOST.document.createElement("button");
    save.className = "btn cfg-save";
    save.textContent = "\u4FDD\u5B58";
    save.addEventListener("click", function() {
      save.disabled = true;
      status.textContent = "\u4FDD\u5B58\u4E2D\u2026";
      fetch("/api/config/markdown/SOUL", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: tx.value }) }).then(function(r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
      }).then(function() {
        save.disabled = false;
        status.textContent = "\u5DF2\u4FDD\u5B58";
      }).catch(function(e) {
        save.disabled = false;
        status.textContent = "\u4FDD\u5B58\u5931\u8D25";
        HOST.alert("\u4FDD\u5B58\u5931\u8D25\uFF1A" + (e && e.message || ""));
      });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }
  function renderPluginGroup(main, grp) {
    const group = HOST.document.createElement("div");
    group.className = "settings-group";
    const gt = HOST.document.createElement("div");
    gt.className = "settings-group-title";
    gt.textContent = AREA_LABEL[grp.area] || grp.area;
    group.appendChild(gt);
    if (grp.host) grp.host(group);
    const list = groupState.plugins.filter(function(p) {
      return ((p.slotDef || {}).area || "") === grp.area;
    });
    const multi = grp.singleton && list.length > 1;
    if (multi) {
      const sub = HOST.document.createElement("div");
      sub.className = "settings-subgroup";
      sub.textContent = "\u540C\u65F6\u53EA\u80FD\u542F\u7528\u4E00\u4E2A\u63D2\u4EF6";
      group.appendChild(sub);
    }
    list.forEach(function(p) {
      renderPluginCard(group, p, cfgFor(p));
    });
    if (!group.querySelector(".cfg-card")) {
      const none = HOST.document.createElement("div");
      none.className = "p-tag";
      none.textContent = "\uFF08\u6682\u65E0\u63D2\u4EF6\uFF09";
      group.appendChild(none);
    }
    main.appendChild(group);
  }
  function pluginVisible(p) {
    if (railHidden(p.id)) return false;
    const type = (p.slotDef || {}).type;
    if (type === "fixed") {
      const cur = pluginBySlot[p.slot || ""];
      return !!cur && cur.id === p.id;
    }
    if (type === "panel") {
      if (!tileMode() && railHidden(PANEL_CONTAINER_ID)) return false;
      return panelTabs.indexOf(p.id) >= 0;
    }
    return true;
  }
  function closeSettingsMenus() {
    HOST.document.querySelectorAll(".settings-card-menu").forEach(function(m) {
      m.remove();
    });
    syncNativeCover();
  }
  function openPluginCardMenu(ev, btn, p) {
    ev.stopPropagation();
    const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + p.id + '"]');
    closeSettingsMenus();
    if (wasOpen) return;
    const menu = HOST.document.createElement("div");
    menu.className = "settings-card-menu";
    menu.setAttribute("data-owner", p.id);
    if (p.builtin) {
      const dis = HOST.document.createElement("button");
      dis.className = "settings-menu-btn disabled";
      dis.textContent = "\u5185\u7F6E\u63D2\u4EF6 \xB7 \u4E0D\u53EF\u5220\u9664";
      dis.disabled = true;
      menu.appendChild(dis);
    } else {
      const d = HOST.document.createElement("button");
      d.className = "settings-menu-btn danger";
      d.textContent = "\u5220\u9664";
      d.addEventListener("click", function() {
        closeSettingsMenus();
        if (HOST.confirm("\u786E\u5B9A\u5220\u9664\u63D2\u4EF6 \u201C" + (p.name || p.id) + "\u201D \u5417\uFF1F")) {
          callAction("plugin.delete", { plugin_id: p.id }).then(function() {
            renderSettings();
          }).catch(function(e) {
            HOST.alert("\u5220\u9664\u5931\u8D25\uFF1A" + e.message);
          });
        }
      });
      menu.appendChild(d);
    }
    HOST.document.body.appendChild(menu);
    const r = btn.getBoundingClientRect();
    menu.style.right = HOST.innerWidth - r.right + "px";
    menu.style.top = r.bottom + 4 + "px";
    syncNativeCover();
  }
  function activateSlotPlugin(p) {
    const slot = p.slot;
    const type = (p.slotDef || {}).type;
    if (type === "panel") {
      openPanelTab(p.id);
      return;
    }
    if (type === "fixed") {
      if (!railState.hidden) railState.hidden = {};
      (slotMap[slot] || []).forEach((x) => {
        if (x.id !== p.id) railState.hidden[x.id] = true;
      });
      delete railState.hidden[p.id];
      if (slot === "panel-container" && p.id !== PANEL_CONTAINER_ID) railState.hidden[PANEL_CONTAINER_ID] = true;
      activeBySlot[slot] = p.id;
      refreshFixedSlot(slot);
      buildRail();
      if (tileMode()) syncTiles();
      persistActive2();
      persistRail().catch(() => {
      });
      return;
    }
    if (type === "modal") {
      if (railHidden(p.id)) setPluginHidden(p.id, false);
      buildRail();
      return;
    }
    if (railHidden(p.id)) setPluginHidden(p.id, false);
    buildRail();
  }
  function togglePluginOpen(p) {
    const type = (p.slotDef || {}).type;
    if (type === "panel") {
      if (pluginVisible(p)) closePanelTab(p.id);
      else openPanelTab(p.id);
      return;
    }
    if (pluginVisible(p)) {
      setPluginHidden(p.id, true);
      buildRail();
      return;
    }
    activateSlotPlugin(p);
  }

  // ui/web-minimal/src/host/tile.ts
  var fixedAnchors = {};
  var tileEls = {};
  var tileFrames = {};
  var stripEl = null;
  var addEl = null;
  var broadcastT = null;
  var managing = false;
  function panelPlugins() {
    return groupState.plugins.filter((p) => (p.slotDef || {}).type === "panel" && !!p.entry);
  }
  function pluginVisibleInSlot(slot) {
    const cur = pluginBySlot[slot];
    if (cur) return railHidden(cur.id) ? null : cur;
    const list = (slotMap[slot] || []).filter((p) => !railHidden(p.id));
    return list[0] || null;
  }
  function broadcastLayout() {
    if (broadcastT != null) return;
    broadcastT = HOST.setTimeout(() => {
      broadcastT = null;
      broadcastAll("host.layoutChanged", { mode: "tile" });
    }, 40);
  }
  function resetTileDrag(tile) {
    tile.classList.remove("dragging", "removing");
    tile.style.position = "";
    tile.style.left = "";
    tile.style.top = "";
    tile.style.height = "";
    tile.style.margin = "";
    tile.style.transform = "";
  }
  var dropLineEl = null;
  function hideDropLine() {
    if (dropLineEl) dropLineEl.style.display = "none";
  }
  function showDropLine(x, top, height) {
    if (!dropLineEl || !dropLineEl.isConnected) {
      dropLineEl = HOST.document.createElement("div");
      dropLineEl.className = "wm-tile-drop";
      HOST.document.body.appendChild(dropLineEl);
    }
    dropLineEl.style.display = "";
    dropLineEl.style.left = Math.round(x) + "px";
    dropLineEl.style.top = Math.round(top) + "px";
    dropLineEl.style.height = Math.round(height) + "px";
  }
  function setShiftMode(on) {
    const active = on && tileMode();
    HOST.document.body.classList.toggle("wm-shift-mode", active);
    if (!active && !managing) {
      hideDropLine();
      HOST.document.querySelectorAll(".wm-tile-placeholder").forEach((el) => el.remove());
      Object.keys(tileEls).forEach((k) => resetTileDrag(tileEls[k]));
    }
  }
  HOST.addEventListener("keydown", (ev) => {
    if (ev.key === "Shift") setShiftMode(true);
  });
  HOST.addEventListener("keyup", (ev) => {
    if (ev.key === "Shift") setShiftMode(false);
  });
  HOST.addEventListener("blur", () => {
    HOST.document.querySelectorAll(".wm-drag-layer").forEach((el) => el.remove());
    HOST.document.querySelectorAll(".wm-tile-placeholder").forEach((el) => el.remove());
    managing = false;
    hideDropLine();
    setShiftMode(false);
    Object.keys(tileEls).forEach((k) => resetTileDrag(tileEls[k]));
  });
  function ensureStrip() {
    if (stripEl && stripEl.isConnected) return stripEl;
    const el = HOST.document.createElement("div");
    el.className = "wm-tiles";
    el.id = "wmTiles";
    el.addEventListener("wheel", (ev) => {
      if (!ev.deltaY) return;
      el.scrollLeft += ev.deltaY;
    }, { passive: true });
    el.addEventListener("scroll", broadcastLayout, { passive: true });
    let panning = false;
    let panX = 0;
    let panScroll = 0;
    el.addEventListener("pointerdown", (ev) => {
      if (ev.target !== el || ev.button !== 0) return;
      panning = true;
      panX = ev.clientX;
      panScroll = el.scrollLeft;
      try {
        el.setPointerCapture(ev.pointerId);
      } catch (_) {
      }
    });
    el.addEventListener("pointermove", (ev) => {
      if (!panning) return;
      el.scrollLeft = panScroll - (ev.clientX - panX);
    });
    const endPan = () => {
      panning = false;
    };
    el.addEventListener("pointerup", endPan);
    el.addEventListener("pointercancel", endPan);
    HOST.document.body.appendChild(el);
    stripEl = el;
    return el;
  }
  function tileBody(tile) {
    return tile.querySelector(".wm-tile-body");
  }
  function closeFixedSlot(slot) {
    const cur = pluginVisibleInSlot(slot);
    if (cur) setPluginHidden(cur.id, true);
  }
  function closeTileByKey(key) {
    if (key === LAYOUT_KEY_SIDEBAR) closeFixedSlot("sidebar");
    else if (key === LAYOUT_KEY_SESSION) closeFixedSlot("session");
    else if (key.indexOf("panel:") === 0) closePanelTab(key.slice("panel:".length));
    syncTiles();
    buildRail();
  }
  function bindResize(tile, grip, key) {
    grip.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const startX = ev.clientX;
      const startW = tile.getBoundingClientRect().width;
      const move = (e2) => {
        setWindowWidth(key, startW + (e2.clientX - startX));
        tile.style.width = windowWidth(key) + "px";
        broadcastLayout();
      };
      const up = () => {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        try {
          grip.releasePointerCapture(ev.pointerId);
        } catch (_) {
        }
        persistLayout();
        broadcastLayout();
      };
      try {
        grip.setPointerCapture(ev.pointerId);
      } catch (_) {
      }
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    });
  }
  function sortedVisibleKeys() {
    return Object.keys(tileEls).filter((k) => tileEls[k].style.display !== "none").sort((a, b) => Number(tileEls[a].style.order || 0) - Number(tileEls[b].style.order || 0));
  }
  function bindManageDrag(tile, shield, key) {
    shield.addEventListener("pointerdown", (ev) => {
      if (!HOST.document.body.classList.contains("wm-shift-mode") || ev.button !== 0) return;
      ev.preventDefault();
      ev.stopPropagation();
      const strip = stripEl;
      const rect = tile.getBoundingClientRect();
      const startY = ev.clientY;
      const removeAt = Math.max(80, rect.height / 2);
      let removing = false;
      let done = false;
      let lastX = ev.clientX;
      let offsetX = 0;
      managing = true;
      tile.classList.add("dragging");
      tile.style.position = "fixed";
      tile.style.left = rect.left + "px";
      tile.style.top = rect.top + "px";
      tile.style.height = rect.height + "px";
      tile.style.margin = "0";
      const placeholder = HOST.document.createElement("div");
      placeholder.className = "wm-tile-placeholder";
      placeholder.style.width = rect.width + "px";
      if (tile.parentElement) tile.parentElement.insertBefore(placeholder, tile);
      const layer = HOST.document.createElement("div");
      layer.className = "wm-drag-layer";
      HOST.document.body.appendChild(layer);
      let pointerX = ev.clientX;
      let targetIndex = Math.max(0, sortedVisibleKeys().indexOf(key));
      const updateIndicator = (x) => {
        if (!strip) {
          hideDropLine();
          return 0;
        }
        const others = sortedVisibleKeys().filter((k) => k !== key);
        if (!others.length) {
          hideDropLine();
          return 0;
        }
        let index = others.length;
        for (let i = 0; i < others.length; i++) {
          const r = tileEls[others[i]].getBoundingClientRect();
          if (x < r.left + r.width / 2) {
            index = i;
            break;
          }
        }
        const sr = strip.getBoundingClientRect();
        let lineX;
        if (index === 0) lineX = tileEls[others[0]].getBoundingClientRect().left - 4;
        else lineX = tileEls[others[index - 1]].getBoundingClientRect().right + 4;
        showDropLine(lineX, sr.top + 6, Math.max(40, sr.height - 12));
        return index;
      };
      const move = (e2) => {
        pointerX = e2.clientX;
        offsetX += e2.clientX - lastX;
        lastX = e2.clientX;
        const dy = e2.clientY - startY;
        const willRemove = dy >= removeAt;
        if (willRemove !== removing) {
          removing = willRemove;
          tile.classList.toggle("removing", removing);
        }
        tile.style.left = Math.round(rect.left + offsetX) + "px";
        tile.style.top = Math.round(rect.top + (removing ? Math.min(dy - removeAt, 40) : 0)) + "px";
        if (removing) {
          hideDropLine();
          return;
        }
        if (strip) {
          const sr = strip.getBoundingClientRect();
          if (e2.clientX < sr.left + 56) strip.scrollLeft -= 20;
          else if (e2.clientX > sr.right - 56) strip.scrollLeft += 20;
        }
        targetIndex = updateIndicator(pointerX);
      };
      const onScroll = () => {
        if (!removing) targetIndex = updateIndicator(pointerX);
      };
      if (strip) strip.addEventListener("scroll", onScroll, { passive: true });
      const finish = (commit) => {
        if (done) return;
        done = true;
        managing = false;
        layer.removeEventListener("pointermove", move);
        layer.removeEventListener("pointerup", up);
        layer.removeEventListener("pointercancel", cancel);
        if (strip) strip.removeEventListener("scroll", onScroll);
        try {
          layer.releasePointerCapture(ev.pointerId);
        } catch (_) {
        }
        layer.remove();
        placeholder.remove();
        hideDropLine();
        if (commit && !removing) {
          const others = sortedVisibleKeys().filter((k) => k !== key);
          const next = others.slice();
          next.splice(Math.max(0, Math.min(next.length, targetIndex)), 0, key);
          reorderWindows(next);
          applyOrder();
          persistLayout();
        }
        resetTileDrag(tile);
        if (commit && removing) closeTileByKey(key);
        broadcastLayout();
      };
      const up = () => finish(true);
      const cancel = () => finish(false);
      try {
        layer.setPointerCapture(ev.pointerId);
      } catch (_) {
      }
      layer.addEventListener("pointermove", move);
      layer.addEventListener("pointerup", up);
      layer.addEventListener("pointercancel", cancel);
    });
  }
  function makeTile(key) {
    const tile = HOST.document.createElement("div");
    tile.className = "wm-tile";
    tile.dataset.key = key;
    const body = HOST.document.createElement("div");
    body.className = "wm-tile-body";
    const shield = HOST.document.createElement("div");
    shield.className = "wm-tile-shield";
    const grip = HOST.document.createElement("div");
    grip.className = "wm-tile-resize";
    grip.title = "\u62D6\u52A8\u8C03\u6574\u5BBD\u5EA6";
    tile.appendChild(body);
    tile.appendChild(shield);
    tile.appendChild(grip);
    bindManageDrag(tile, shield, key);
    bindResize(tile, grip, key);
    return tile;
  }
  function moveAnchorInto(body, slot) {
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (!anchor) return;
    if (!fixedAnchors[slot]) {
      fixedAnchors[slot] = { el: anchor, parent: anchor.parentNode, next: anchor.nextSibling };
    }
    if (anchor.parentNode !== body) body.appendChild(anchor);
  }
  function syncFixedTile(strip, key, slot) {
    let tile = tileEls[key];
    if (!tile) {
      tile = makeTile(key);
      strip.appendChild(tile);
      tileEls[key] = tile;
    }
    moveAnchorInto(tileBody(tile), slot);
    const on = !!pluginVisibleInSlot(slot);
    tile.style.display = on ? "" : "none";
    return on;
  }
  function ensureAddTile(strip) {
    if (addEl && addEl.isConnected) return;
    const tile = HOST.document.createElement("div");
    tile.className = "wm-tile wm-tile-add";
    tile.id = "wmTileAdd";
    tile.title = "\u9009\u62E9\u8981\u5F00\u542F\u7684\u63D2\u4EF6";
    tile.style.width = TILE_ADD_W + "px";
    tile.style.order = "99999";
    const plus = HOST.document.createElement("span");
    plus.className = "wm-tile-add-plus";
    paintIcon(plus, "plus", "+");
    const label = HOST.document.createElement("span");
    label.textContent = "\u6DFB\u52A0";
    tile.appendChild(plus);
    tile.appendChild(label);
    tile.addEventListener("click", (ev) => {
      ev.stopPropagation();
      openTileAddMenu(tile);
    });
    strip.appendChild(tile);
    addEl = tile;
  }
  function menuItem(p, on, onclick) {
    const item = HOST.document.createElement("div");
    item.className = "wm-pp_menu-item" + (on ? " active" : "");
    const g = HOST.document.createElement("span");
    g.className = "wm-pp_menu-ico";
    paintPluginIcon(g, p);
    const nm = HOST.document.createElement("span");
    nm.textContent = p.name || p.id;
    item.appendChild(g);
    item.appendChild(nm);
    if (on) {
      const tag = HOST.document.createElement("span");
      tag.className = "wm-pp_menu-tag";
      tag.textContent = "\u5DF2\u6253\u5F00";
      item.appendChild(tag);
    }
    item.addEventListener("click", onclick);
    return item;
  }
  function menuSection(menu, title) {
    const head = HOST.document.createElement("div");
    head.className = "wm-tile-menu-head";
    head.textContent = title;
    menu.appendChild(head);
  }
  function openTileAddMenu(anchor) {
    const wasOpen = !!HOST.document.getElementById("tile-add-menu");
    closePanelMenus();
    if (wasOpen) return;
    const menu = HOST.document.createElement("div");
    menu.className = "wm-pp_menu";
    menu.id = "tile-add-menu";
    const toggle = (p) => {
      closePanelMenus();
      togglePluginOpen(p);
      syncTiles();
      buildRail();
    };
    const fixedAreas = [["sidebar", "\u5217\u8868\u4F4D"], ["session", "\u4F1A\u8BDD\u4F4D"]];
    fixedAreas.forEach(([area, label]) => {
      const list = groupState.plugins.filter((p) => (p.slotDef || {}).area === area && !!p.entry);
      if (!list.length) return;
      menuSection(menu, label);
      list.forEach((p) => menu.appendChild(menuItem(p, pluginVisible(p), () => toggle(p))));
    });
    const panels = panelPlugins();
    if (panels.length) {
      menuSection(menu, "\u9762\u677F");
      panels.forEach((p) => menu.appendChild(menuItem(p, pluginVisible(p), () => toggle(p))));
    }
    HOST.document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const left = Math.max(8, r.left - menu.offsetWidth - 8);
    menu.style.left = left + "px";
    menu.style.right = "auto";
    menu.style.top = Math.max(8, Math.min(r.top, HOST.innerHeight - menu.offsetHeight - 8)) + "px";
    syncNativeCover();
  }
  function applyOrder() {
    const order = layoutState.order;
    const rank = (k) => {
      const i = order.indexOf(k);
      return i < 0 ? order.length : i;
    };
    Object.keys(tileEls).forEach((k) => {
      tileEls[k].style.order = String(rank(k));
    });
    if (addEl) addEl.style.order = "99999";
  }
  function syncTiles() {
    if (!tileMode()) {
      teardownTiles();
      return;
    }
    const strip = ensureStrip();
    const panels = panelPlugins();
    const hasSavedTabs = Object.prototype.hasOwnProperty.call(activeBySlot, "__panelTabs__");
    if (!panelTabs.length && !hasSavedTabs && panels.length) {
      const legacy = panels.find((p) => p.id === activeBySlot["panel"]);
      panelTabs.push((legacy || panels[0]).id);
    }
    const validPanels = panels.filter(
      (p) => panelTabs.indexOf(p.id) >= 0 && !railHidden(p.id)
    );
    const sidebarOn = syncFixedTile(strip, LAYOUT_KEY_SIDEBAR, "sidebar");
    const sessionOn = syncFixedTile(strip, LAYOUT_KEY_SESSION, "session");
    validPanels.forEach((p) => {
      const key = panelWindowKey(p.id);
      let tile = tileEls[key];
      if (!tile) {
        tile = makeTile(key);
        strip.appendChild(tile);
        tileEls[key] = tile;
      }
      const body = tileBody(tile);
      if (!tileFrames[p.id]) tileFrames[p.id] = mountFrame(body, p);
      tile.style.display = "";
    });
    Object.keys(tileEls).forEach((key) => {
      if (key.indexOf("panel:") !== 0) return;
      const id = key.slice("panel:".length);
      if (validPanels.some((p) => p.id === id)) return;
      notifyUnmount(tileEls[key]);
      tileEls[key].remove();
      delete tileEls[key];
      delete tileFrames[id];
    });
    frames["panel"] = validPanels.map((p) => tileFrames[p.id]).filter(Boolean);
    ensureAddTile(strip);
    const visible = (sidebarOn ? [LAYOUT_KEY_SIDEBAR] : []).concat(validPanels.map((p) => panelWindowKey(p.id))).concat(sessionOn ? [LAYOUT_KEY_SESSION] : []);
    const orderBefore = layoutState.order.join("\0");
    ensureOrder(visible);
    applyOrder();
    if (orderBefore !== layoutState.order.join("\0")) persistLayout();
    Object.keys(tileEls).forEach((k) => {
      tileEls[k].style.width = windowWidth(k) + "px";
    });
    broadcastLayout();
    syncNativeCover();
  }
  function scrollTileIntoView(key) {
    const tile = tileEls[key];
    if (!tile || !stripEl) return;
    const left = tile.offsetLeft;
    const right = left + tile.offsetWidth;
    if (left < stripEl.scrollLeft) stripEl.scrollLeft = left - 8;
    else if (right > stripEl.scrollLeft + stripEl.clientWidth) {
      stripEl.scrollLeft = right - stripEl.clientWidth + 8;
    }
  }
  function teardownTiles() {
    if (stripEl) {
      Object.keys(fixedAnchors).forEach((slot) => {
        const rec = fixedAnchors[slot];
        if (rec.el.parentNode && rec.parent) {
          if (rec.next && rec.next.parentNode === rec.parent) rec.parent.insertBefore(rec.el, rec.next);
          else rec.parent.appendChild(rec.el);
        }
        delete fixedAnchors[slot];
      });
      notifyUnmount(stripEl);
      stripEl.remove();
    }
    stripEl = null;
    addEl = null;
    Object.keys(tileEls).forEach((k) => delete tileEls[k]);
    Object.keys(tileFrames).forEach((k) => delete tileFrames[k]);
    delete frames["panel"];
    setShiftMode(false);
  }

  // ui/web-minimal/src/host/mount.ts
  function syncPluginBackend(id, action) {
    if (!id) return;
    try {
      fetch("/api/webmin/plugin-backend/" + encodeURIComponent(id) + "/" + action, {
        method: "POST",
        cache: "no-store"
      }).catch(function() {
      });
    } catch (_) {
    }
  }
  function notifyUnmount(rootEl) {
    if (!rootEl || !rootEl.querySelectorAll) return;
    rootEl.querySelectorAll("iframe").forEach(function(f) {
      try {
        if (f.contentWindow) f.contentWindow.postMessage({ type: "event", event: "host.unmount", data: {} }, "*");
      } catch (_) {
      }
      if (f.dataset && f.dataset.backend === "1" && f.dataset.pid) {
        syncPluginBackend(f.dataset.pid, "stop");
      }
    });
  }
  function mountFrame(el, p) {
    notifyUnmount(el);
    el.querySelectorAll("iframe").forEach((f) => f.remove());
    el.querySelectorAll(".wm-fgrab, .wm-fresize").forEach((h) => h.remove());
    if (!p || !p.entry) return null;
    const iframe = document.createElement("iframe");
    iframe.setAttribute("tabindex", "-1");
    iframe.src = `/api/webmin/plugin/${encodeURIComponent(p.id)}/${p.entry.split("/").map(encodeURIComponent).join("/")}`;
    iframe.title = p.name || p.id;
    iframe.dataset.pid = p.id;
    if (p.backend) {
      iframe.dataset.backend = "1";
      syncPluginBackend(p.id, "start");
    }
    el.appendChild(iframe);
    iframe.addEventListener("load", function bridgeShift() {
      try {
        const cw = iframe.contentWindow;
        if (!cw) return;
        cw.addEventListener("keydown", (ev) => {
          if (ev.key === "Shift") setShiftMode(true);
        }, true);
        cw.addEventListener("keyup", (ev) => {
          if (ev.key === "Shift") setShiftMode(false);
        }, true);
      } catch (_) {
      }
    });
    slotByPluginId[p.id] = p.slot;
    frameByPluginId[p.id] = iframe;
    const rec = { iframe, pluginId: p.id, el, loaded: false };
    iframe.addEventListener("load", function onLoad() {
      rec.loaded = true;
      applyConfigTo(p.id);
      if (groupState.activeSessionId) {
        try {
          const cw = iframe.contentWindow;
          if (cw) {
            cw.postMessage(
              { type: "event", event: "session.switched", data: { session_id: groupState.activeSessionId } },
              "*"
            );
          }
        } catch (_) {
        }
      }
      try {
        const cw = iframe.contentWindow;
        if (cw) {
          cw.postMessage(
            { type: "event", event: "branch.switched", data: { branch_id: groupState.activeBranchId || "main" } },
            "*"
          );
        }
      } catch (_) {
      }
      try {
        const cw = iframe.contentWindow;
        if (cw) {
          cw.postMessage(
            { type: "event", event: "host.nativeCover", data: { covered: nativeCoverActive() } },
            "*"
          );
        }
      } catch (_) {
      }
      deliverPendingBrowserUrl();
      iframe.removeEventListener("load", onLoad);
    });
    return rec;
  }
  function buildSlotIndex() {
    Object.keys(frames).forEach((k) => {
      (frames[k] || []).forEach((f) => {
        if (f.el && f.el.parentNode && !f.el.hasAttribute("data-layer")) {
          notifyUnmount(f.el);
          f.el.remove();
        }
      });
    });
    Object.keys(slotMap).forEach((k) => delete slotMap[k]);
    Object.keys(pluginBySlot).forEach((k) => delete pluginBySlot[k]);
    Object.keys(slotByPluginId).forEach((k) => delete slotByPluginId[k]);
    Object.keys(frameByPluginId).forEach((k) => delete frameByPluginId[k]);
    Object.keys(frames).forEach((k) => delete frames[k]);
    groupState.plugins.forEach((p) => {
      const s = p.slot;
      if (!s) return;
      (slotMap[s] = slotMap[s] || []).push(p);
      slotByPluginId[p.id] = s;
    });
  }
  function refreshFixedSlot(slot) {
    if (slot === "panel-container" && tileMode()) {
      if (frames[slot]) {
        frames[slot].forEach((f) => {
          if (f.iframe && f.iframe.parentNode) f.iframe.parentNode.removeChild(f.iframe);
        });
        frames[slot] = [];
      }
      delete pluginBySlot[slot];
      const anchor2 = HOST.document.querySelector(`[data-slot="${slot}"]`);
      if (anchor2) {
        anchor2.innerHTML = "";
        anchor2.style.display = "none";
      }
      return;
    }
    const list = slotMap[slot] || [];
    const visible = list.filter((x) => !railHidden(x.id));
    const chosen = visible.find((x) => x.id === activeBySlot[slot]) || visible[0] || null;
    if (frames[slot]) {
      frames[slot].forEach((f) => {
        if (f.iframe && f.iframe.parentNode) f.iframe.parentNode.removeChild(f.iframe);
      });
      frames[slot] = [];
    }
    if (!chosen) {
      delete pluginBySlot[slot];
      applySlotHidden(slot, true);
      if (slot === "panel-container") syncPanelContainer();
      return;
    }
    pluginBySlot[slot] = chosen;
    if (chosen.id === PANEL_CONTAINER_ID) {
      const anchor2 = HOST.document.querySelector(`[data-slot="${slot}"]`);
      if (anchor2) anchor2.innerHTML = "";
      syncPanelContainer();
      return;
    }
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (anchor) {
      anchor.innerHTML = "";
      const fr = mountFrame(anchor, chosen);
      if (fr) frames[slot] = [fr];
    }
    applySlotHidden(slot, false);
    if (slot === "panel-container") syncPanelContainer();
  }
  function syncPanelContainer() {
    mountPanels();
    reconcilePanels();
    applySlotHidden("panel", !panelContainerVisible());
  }
  function mountAll() {
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = list[0].slotDef || {};
      if (def.type !== "fixed") return;
      refreshFixedSlot(sid);
    });
    mountPanels();
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = list[0].slotDef || {};
      if (def.type !== "float") return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      list.forEach((p, i) => {
        const el = HOST.document.createElement("div");
        el.className = "wm-float wm-mount";
        el.dataset.fslot = sid;
        el.dataset.finst = String(i);
        el.style.top = 46 + i * 26 + "px";
        el.style.left = `calc(100% - ${300 + i * 26}px - 16px)`;
        applyFloatSize(el, def.size, i);
        HOST.document.body.appendChild(el);
        if (def.center) centerFloat(el);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(el, p);
        if (fr) frames[sid].push(fr);
        attachFloatHandles(el);
      });
    });
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = list[0].slotDef || {};
      if (def.type !== "modal") return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      list.forEach((p) => {
        const wrap = HOST.document.createElement("div");
        wrap.className = "wm-modal-wrap wm-mount";
        wrap.dataset.mslot = sid;
        const box = HOST.document.createElement("div");
        box.className = "wm-modal";
        applyModalSize(box, def.size);
        wrap.appendChild(box);
        HOST.document.body.appendChild(wrap);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(box, p);
        if (fr) {
          fr.el = wrap;
          frames[sid].push(fr);
        }
      });
    });
    reconcilePanels();
    if (tileMode()) syncTiles();
    else teardownTiles();
  }
  function remountLayout2() {
    buildSlotIndex();
    mountAll();
    applyPersistedHidden();
    buildRail();
    applyPanelContainerCfg();
    if (tileMode()) syncTiles();
    else teardownTiles();
    broadcastAll("host.layoutChanged", { mode: layoutState.mode });
  }
  bindRemountLayout(remountLayout2);

  // ui/web-minimal/src/host/panel.ts
  var panelBar = null;
  var panelState = null;
  var panelTabs = [];
  var PANEL_MIN_W = 260;
  var panelContainerCfg = { opacity: 0.9 };
  var panelSavedWidth = null;
  var panelDesiredWidth3 = null;
  function setPanelSavedWidth(v) {
    panelSavedWidth = v;
  }
  function setPanelDesiredWidth(v) {
    panelDesiredWidth3 = v;
  }
  var panelShellTpl = null;
  async function loadPanelShell() {
    if (panelShellTpl) return;
    try {
      const res = await fetch("/api/webmin/plugin/" + encodeURIComponent(PANEL_CONTAINER_ID) + "/index.html");
      if (!res.ok) return;
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      const src = doc.querySelector("style");
      if (src) {
        const el = HOST.document.createElement("style");
        el.id = "wm-builtin-panel-style";
        el.textContent = src.textContent;
        const old = HOST.document.getElementById("wm-builtin-panel-style");
        if (old) old.remove();
        HOST.document.head.appendChild(el);
      }
      panelShellTpl = doc.body && doc.body.firstElementChild || null;
    } catch (_) {
    }
  }
  function applyPanelContainerCfg() {
    const el = HOST.document.querySelector('.wm-ppanel[data-pslot="panel"]');
    if (!el) return;
    let o = Number(panelContainerCfg.opacity);
    if (!(o >= 0)) o = 1;
    o = Math.min(1, Math.max(0.15, o));
    el.style.setProperty("--wm-panel-bg", "rgba(255,255,255," + o.toFixed(3) + ")");
  }
  function cssNum(name, dflt) {
    const scope = HOST.document.body || HOST.document.documentElement;
    const v = HOST.getComputedStyle(scope).getPropertyValue(name);
    const n = parseFloat(v);
    return n >= 0 ? n : dflt;
  }
  function panelLeftBase() {
    const rail = cssNum("--wm-rail-w", 48);
    const gap = cssNum("--wm-sidebar-gap", 8);
    const side = cssNum("--wm-sidebar-w", 264);
    const noSidebar = HOST.document.body.classList.contains("rail-nosidebar");
    return noSidebar ? rail + gap : rail + gap + side + gap;
  }
  function slotEnabled(slot) {
    const cur = pluginBySlot[slot];
    if (!cur) return false;
    return !railHidden(cur.id);
  }
  function sessionEnabled() {
    return slotEnabled("session");
  }
  function maxPanelWidth() {
    const gap = cssNum("--wm-sidebar-gap", 8);
    let chat = sessionEnabled() ? cssNum("--wm-chat-w", 420) : 0;
    return Math.max(PANEL_MIN_W, Math.floor(HOST.innerWidth - panelLeftBase() - gap - chat));
  }
  function panelMaxLimit() {
    const gap = cssNum("--wm-sidebar-gap", 8);
    const chatMin = sessionEnabled() ? cssNum("--wm-chat-min-w", 360) : 0;
    return Math.floor(HOST.innerWidth - panelLeftBase() - gap - chatMin);
  }
  function applyPanelWidth() {
    if (!hasPanelsDef()) return;
    const gap = cssNum("--wm-sidebar-gap", 8);
    let limit = panelMaxLimit();
    const el = HOST.document.querySelector('.wm-ppanel[data-pslot="panel"]') || HOST.document.querySelector('[data-slot="panel-container"] > iframe');
    if (el) {
      const left = el.getBoundingClientRect().left;
      if (isFinite(left)) limit = Math.min(limit, Math.floor(HOST.innerWidth - left - gap));
    }
    let raw = panelDesiredWidth3 != null ? panelDesiredWidth3 : maxPanelWidth();
    if (!isFinite(raw)) raw = maxPanelWidth();
    if (!isFinite(limit)) return;
    let w = Math.max(PANEL_MIN_W, raw);
    w = limit < PANEL_MIN_W ? Math.max(0, limit) : Math.min(w, limit);
    HOST.document.documentElement.style.setProperty("--wm-panel-w", Math.round(w) + "px");
  }
  function setContainerHidden(hidden) {
    if (!railState.hidden) railState.hidden = {};
    const list = slotMap["panel-container"] || [];
    if (hidden) {
      list.forEach((p) => {
        railState.hidden[p.id] = true;
      });
      closePanelMenus();
    } else {
      list.forEach((p) => {
        if (p.id !== PANEL_CONTAINER_ID) railState.hidden[p.id] = true;
      });
      delete railState.hidden[PANEL_CONTAINER_ID];
      activeBySlot["panel-container"] = PANEL_CONTAINER_ID;
    }
    refreshFixedSlot("panel-container");
    refreshAreaRail("panel-container");
    buildRail();
    persistActive2();
    persistRail().catch(() => {
    });
  }
  function hasPanelsDef() {
    if (tileMode()) return false;
    if ((slotMap["panel-container"] || []).length) return true;
    return Object.keys(slotMap).some((sid) => (slotMap[sid][0].slotDef || {}).type === "panel");
  }
  function thirdPartyContainerPlugin() {
    const cur = pluginBySlot["panel-container"];
    return cur && cur.id !== PANEL_CONTAINER_ID ? cur : null;
  }
  function panelContainerVisible() {
    if (tileMode()) return false;
    return !!thirdPartyContainerPlugin() || !railHidden(PANEL_CONTAINER_ID);
  }
  function startPanelBarDrag(e) {
    e.preventDefault();
    const el = e.currentTarget;
    const w0 = HOST.document.documentElement.style.getPropertyValue("--wm-panel-w");
    const base = w0 ? parseFloat(w0) : panelDesiredWidth3 != null ? panelDesiredWidth3 : 420;
    const sx0 = e.clientX;
    HOST.document.body.classList.add("wm-panel-dragging");
    const move = (ev) => {
      panelDesiredWidth3 = Math.max(PANEL_MIN_W, base + (ev.clientX - sx0));
      applyPanelWidth();
    };
    const up = () => {
      HOST.document.body.classList.remove("wm-panel-dragging");
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      try {
        el.releasePointerCapture(e.pointerId);
      } catch (_) {
      }
    };
    try {
      el.setPointerCapture(e.pointerId);
    } catch (_) {
    }
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }
  function reconcilePanels() {
    if (hasPanelsDef()) {
      HOST.document.body.classList.add("has-panels");
      applyPanelWidth();
      if (!panelBar || !panelBar.isConnected) {
        panelBar = HOST.document.createElement("div");
        panelBar.className = "wm-pbar";
        panelBar.title = "\u62D6\u52A8\u4EE5\u8C03\u6574\u4E2D\u680F\u5BBD\u5EA6";
        panelBar.addEventListener("pointerdown", startPanelBarDrag);
        HOST.document.body.appendChild(panelBar);
      }
    } else {
      HOST.document.body.classList.remove("has-panels");
      if (panelBar && panelBar.isConnected) panelBar.remove();
    }
  }
  function closePanelMenus() {
    HOST.document.querySelectorAll(".wm-pp_menu").forEach((m) => m.remove());
    syncNativeCover();
  }
  function savePanelSel() {
    activeBySlot["__panelTabs__"] = JSON.stringify(panelTabs);
    return persistActive2();
  }
  function makePanelTab(st, id, p) {
    const tab = HOST.document.createElement("div");
    tab.className = "wm-pp_tab" + (id === st.activeId ? " active" : "");
    tab.dataset.pid = id;
    tab.title = p.name || p.id;
    const g = HOST.document.createElement("span");
    g.className = "wm-pp_tabico";
    paintPluginIcon(g, p);
    tab.appendChild(g);
    const nm = HOST.document.createElement("span");
    nm.className = "wm-pp_tabname";
    nm.textContent = p.name || p.id;
    tab.appendChild(nm);
    const x = HOST.document.createElement("button");
    x.className = "wm-pp_tabx";
    x.textContent = "\u2715";
    x.title = "\u5173\u95ED\u6807\u7B7E\u9875";
    x.addEventListener("click", (ev) => {
      ev.stopPropagation();
      closePanelTab(id);
    });
    tab.appendChild(x);
    tab.addEventListener("click", () => setActivePanelTab(st, id));
    return tab;
  }
  function renderPanel(st) {
    if (!st.head || !st.head.isConnected) {
      if (!panelShellTpl) return;
      const el = panelShellTpl.cloneNode(true);
      el.dataset.pslot = "panel";
      el.style.display = "flex";
      HOST.document.body.appendChild(el);
      st.el = el;
      st.head = el.querySelector(".wm-pp_head");
      st.strip = el.querySelector(".wm-pp_tabs");
      st.addBtn = el.querySelector(".wm-pp_add");
      paintIcon(st.addBtn, "plus", "+");
      st.addBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        openPanelAddMenu(st, st.addBtn);
      });
      st.closeBtn = el.querySelector(".wm-pp_drawer");
      st.closeBtn.addEventListener("click", () => {
        setContainerHidden(true);
        closePanelMenus();
      });
      st.body = el.querySelector(".wm-pp_body");
      st.emptyEl = el.querySelector(".wm-pp_empty");
      st.views = {};
      st.frames = {};
    }
    panelTabs = panelTabs.filter((id) => {
      const rec = st.pluginsById[id];
      return !!rec && (rec.p.slotDef || {}).type === "panel";
    });
    if (panelTabs.indexOf(st.activeId) < 0) st.activeId = panelTabs[0] || "";
    st.strip.innerHTML = "";
    panelTabs.forEach((id) => st.strip.appendChild(makePanelTab(st, id, st.pluginsById[id].p)));
    panelTabs.forEach((id) => {
      const old = st.views[id];
      if (old && old.isConnected) return;
      const v = HOST.document.createElement("div");
      v.className = "wm-pp_view";
      v.dataset.pid = id;
      st.body.appendChild(v);
      st.views[id] = v;
      st.frames[id] = mountFrame(v, st.pluginsById[id].p);
    });
    Object.keys(st.views).forEach((id) => {
      if (panelTabs.indexOf(id) >= 0) return;
      notifyUnmount(st.views[id]);
      st.views[id].remove();
      delete st.views[id];
      delete st.frames[id];
    });
    if (panelTabs.length) {
      if (st.emptyEl.parentNode) st.emptyEl.remove();
    } else if (!st.emptyEl.parentNode) st.body.appendChild(st.emptyEl);
    frames["panel"] = panelTabs.map((id) => st.frames[id]).filter(Boolean);
    applyActivePanelTab(st);
  }
  function applyActivePanelTab(st) {
    Object.keys(st.views).forEach((id) => {
      st.views[id].style.display = id === st.activeId ? "flex" : "none";
    });
    st.strip.querySelectorAll(".wm-pp_tab").forEach((t) => {
      const on = t.dataset.pid === st.activeId;
      t.classList.toggle("active", on);
      if (on && t.scrollIntoView) {
        try {
          t.scrollIntoView({ block: "nearest", inline: "nearest" });
        } catch (_) {
        }
      }
    });
  }
  function setActivePanelTab(st, id) {
    if (st.activeId === id) return;
    st.activeId = id;
    activeBySlot["panel"] = id;
    applyActivePanelTab(st);
    savePanelSel();
  }
  function openPanelTab(id) {
    if (tileMode()) {
      const p = groupState.plugins.find((x) => x.id === id && (x.slotDef || {}).type === "panel");
      if (!p) return;
      if (panelTabs.indexOf(id) < 0) panelTabs.push(id);
      if (railHidden(id)) {
        if (!railState.hidden) railState.hidden = {};
        delete railState.hidden[id];
        persistRail().catch(() => {
        });
      }
      activeBySlot["panel"] = id;
      savePanelSel();
      syncTiles();
      scrollTileIntoView(panelWindowKey(id));
      return;
    }
    const st = panelState;
    if (!st || !st.pluginsById[id]) return;
    const added = panelTabs.indexOf(id) < 0;
    if (added) panelTabs.push(id);
    st.activeId = id;
    activeBySlot["panel"] = id;
    if (added) renderPanel(st);
    else applyActivePanelTab(st);
    savePanelSel();
    setContainerHidden(false);
  }
  function closePanelTab(id) {
    if (tileMode()) {
      const at = panelTabs.indexOf(id);
      if (at < 0) return;
      panelTabs.splice(at, 1);
      activeBySlot["panel"] = panelTabs[at] || panelTabs[at - 1] || "__none__";
      savePanelSel();
      syncTiles();
      return;
    }
    const st = panelState;
    if (!st) return;
    const i = panelTabs.indexOf(id);
    if (i < 0) return;
    panelTabs.splice(i, 1);
    if (st.activeId === id) st.activeId = panelTabs[i] || panelTabs[i - 1] || "";
    activeBySlot["panel"] = st.activeId || "__none__";
    renderPanel(st);
    savePanelSel();
  }
  function openPanelAddMenu(st, anchor) {
    const wasOpen = HOST.document.getElementById("ppmenu-" + st.area);
    closePanelMenus();
    if (wasOpen) return;
    const menu = HOST.document.createElement("div");
    menu.className = "wm-pp_menu";
    menu.id = "ppmenu-" + st.area;
    st.plugins.forEach(({ p }) => {
      const isOpen = panelTabs.indexOf(p.id) >= 0;
      const item = HOST.document.createElement("div");
      item.className = "wm-pp_menu-item" + (isOpen ? " active" : "");
      const g = HOST.document.createElement("span");
      g.className = "wm-pp_menu-ico";
      paintPluginIcon(g, p);
      item.appendChild(g);
      const nm = HOST.document.createElement("span");
      nm.textContent = p.name || p.id;
      item.appendChild(nm);
      if (isOpen) {
        const tag = HOST.document.createElement("span");
        tag.className = "wm-pp_menu-tag";
        tag.textContent = "\u5DF2\u6253\u5F00";
        item.appendChild(tag);
      }
      item.addEventListener("click", () => {
        openPanelTab(p.id);
        closePanelMenus();
      });
      menu.appendChild(item);
    });
    HOST.document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const left = Math.min(r.right - menu.offsetWidth, HOST.innerWidth - menu.offsetWidth - 8);
    menu.style.right = "auto";
    menu.style.left = Math.max(8, left) + "px";
    menu.style.top = r.bottom + 4 + "px";
    syncNativeCover();
  }
  function mountPanels() {
    if (tileMode()) {
      if (panelState && panelState.el && panelState.el.parentNode) {
        notifyUnmount(panelState.el);
        panelState.el.remove();
      }
      panelState = null;
      closePanelMenus();
      return;
    }
    if (thirdPartyContainerPlugin()) {
      if (panelState && panelState.el && panelState.el.parentNode) {
        notifyUnmount(panelState.el);
        panelState.el.remove();
      }
      panelState = null;
      closePanelMenus();
      return;
    }
    const byArea = { panel: [] };
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = list[0].slotDef || {};
      if (def.type === "panel") {
        byArea.panel.push(...list.map((p) => ({ p, def })));
      }
    });
    if (!byArea.panel.length) {
      if (panelState && panelState.el && panelState.el.parentNode) {
        notifyUnmount(panelState.el);
        panelState.el.remove();
      }
      panelState = null;
      closePanelMenus();
      return;
    }
    const byId = {};
    byArea.panel.forEach((x) => {
      byId[x.p.id] = x;
    });
    const valid = (id) => !!byId[id];
    const hasSavedTabs = Object.prototype.hasOwnProperty.call(activeBySlot, "__panelTabs__");
    let st = panelState;
    if (!st) {
      panelTabs = panelTabs.filter(valid);
      if (!panelTabs.length && !hasSavedTabs) {
        const legacy = activeBySlot["panel"];
        panelTabs = legacy && legacy !== "__none__" && valid(legacy) ? [legacy] : [byArea.panel[0].p.id];
      }
      st = panelState = { plugins: byArea.panel, pluginsById: byId, activeId: "", area: "panel", el: null, views: {}, frames: {} };
    } else {
      st.plugins = byArea.panel;
      st.pluginsById = byId;
      panelTabs = panelTabs.filter(valid);
      if (!panelTabs.length && !hasSavedTabs) panelTabs = [byArea.panel[0].p.id];
    }
    const saved = activeBySlot["panel"];
    st.activeId = saved && saved !== "__none__" && panelTabs.indexOf(saved) >= 0 ? saved : panelTabs[0] || "";
    renderPanel(st);
    activeBySlot["panel"] = st.activeId;
    activeBySlot["__panelTabs__"] = JSON.stringify(panelTabs);
    closePanelMenus();
  }

  // ui/web-minimal/src/host/links.ts
  var pendingBrowserUrl = null;
  function browserPanel() {
    const st = panelState;
    if (st) return st.plugins.find((x) => (x.p || {}).openUrl) || null;
    if (!tileMode()) return null;
    const p = groupState.plugins.find((x) => (x.slotDef || {}).type === "panel" && x.openUrl);
    return p ? { p } : null;
  }
  function deliverPendingBrowserUrl() {
    if (!pendingBrowserUrl) return;
    const hit = browserPanel();
    if (!hit) return;
    const st = panelState;
    const inTile = !st && tileMode();
    if (!inTile && (!st || st.activeId !== hit.p.id)) return;
    const fr = inTile ? (frames["panel"] || []).find((f) => f.pluginId === hit.p.id) : st && st.frames && st.frames[hit.p.id];
    if (!fr || !fr.loaded) return;
    const url = pendingBrowserUrl;
    pendingBrowserUrl = null;
    broadcast(inTile ? "panel" : hit.p.slot, "browser.openUrl", { url });
  }
  function openUrlInBrowserPanel(url) {
    const u = String(url || "").trim();
    if (/^purrcat:\/\//i.test(u)) {
      const tid = (/^purrcat:\/\/task\/([^/]+)\/node\//i.exec(u) || [])[1];
      const art = "/api/tasks/" + encodeURIComponent(tid || "_unknown") + "/artifact?uri=" + encodeURIComponent(u);
      return openUrlInBrowserPanel(new URL(art, location.origin).href);
    }
    const pc = HOST.purrcat;
    const hit = browserPanel();
    const hostCont = hit || tileMode() ? null : thirdPartyContainerPlugin();
    if (!/^https?:\/\//i.test(u) || !hit && !hostCont || !pc || !pc.browserNewTab) {
      if (pc && pc.openExternal && u) pc.openExternal(u);
      return { status: "external" };
    }
    if (hostCont) {
      broadcast("panel-container", "browser.openUrl", { url: u });
      return { status: "ok" };
    }
    openPanelTab(hit.p.id);
    pendingBrowserUrl = u;
    deliverPendingBrowserUrl();
    return { status: "ok" };
  }

  // ui/web-minimal/src/host/actions.ts
  async function dispatch(actionId, payload = {}, origin) {
    payload = payload || {};
    switch (actionId) {
      case "chat.send": {
        let sessionId = await ensureSessionId(payload.session_id || groupState.activeSessionId, payload.message);
        if (!sessionId) throw new Error("\u65E0\u6CD5\u521B\u5EFA\u4F1A\u8BDD");
        groupState.activeSessionId = sessionId;
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: payload.message || "" })
        });
        if (!res.ok) throw new Error(await res.text());
        setEmpty(false);
        const body = await res.json();
        const shown = body && typeof body.processed_message === "string" ? body.processed_message : payload.message || "";
        if (shown) broadcast("session", "conversation.local", { session_id: sessionId, events: [{ role: "user", content: String(shown) }] });
        refreshSessions().then(updateEmpty);
        broadcastSessions("conversation.updated", { session_id: sessionId });
        return body;
      }
      case "chat.sendBatch": {
        const batch = Array.isArray(payload.events) ? payload.events : [];
        const firstUser = batch.find((ev) => ev && ev.type === "user" && typeof ev.content === "string");
        let sessionId = await ensureSessionId(payload.session_id || groupState.activeSessionId, firstUser ? firstUser.content : "");
        if (!sessionId) throw new Error("\u65E0\u6CD5\u521B\u5EFA\u4F1A\u8BDD");
        groupState.activeSessionId = sessionId;
        const res = await fetch("/api/chat/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, events: payload.events || [] })
        });
        if (!res.ok) throw new Error(await res.text());
        setEmpty(false);
        const body = await res.json();
        const evs = body && Array.isArray(body.processed_events) ? body.processed_events : Array.isArray(payload.events) ? payload.events : [];
        const uv = evs.filter((e) => e && e.type === "user").map((e) => ({ role: "user", content: String(e.content || "") }));
        if (uv.length) broadcast("session", "conversation.local", { session_id: sessionId, events: uv });
        refreshSessions().then(updateEmpty);
        broadcastSessions("conversation.updated", { session_id: sessionId });
        return body;
      }
      case "sessions.list": {
        const list = await (await fetch("/api/sessions")).json();
        groupState.sessions = list || [];
        updateEmpty();
        return groupState.sessions;
      }
      case "sessions.new": {
        if (await activeSessionBusy()) return { status: "busy" };
        groupState.draft = true;
        groupState.draftParadigm = "";
        groupState.draftProjectId = String(payload.project_id || "");
        groupState.activeSessionId = "";
        await refreshSessions();
        updateEmpty();
        broadcastSessions("session.switched", { session_id: "" });
        return { status: "ok", draft: true };
      }
      case "session.switch": {
        const target = String(payload.session_id || "");
        if (target && target !== groupState.activeSessionId && await activeSessionBusy()) return { status: "busy" };
        if (target) {
          groupState.draft = false;
          groupState.draftProjectId = "";
        }
        if (target) {
          const res = await fetch("/api/sessions/" + encodeURIComponent(target) + "/checkout", { method: "POST" });
          if (!res.ok) throw new Error(await res.text() || "\u5207\u6362\u4F1A\u8BDD\u5931\u8D25");
          groupState.activeSessionId = target;
          await refreshSessions();
          updateEmpty();
          broadcastSessions("session.switched", { session_id: target });
        }
        return { status: "ok" };
      }
      // 重命名会话：对齐后端 PUT /api/sessions/{id}/rename
      case "session.rename": {
        const sid = String(payload.session_id || "");
        const alias = String(payload.alias || "").trim();
        if (!sid) throw new Error("\u7F3A\u5C11 session_id");
        if (!alias) throw new Error("\u4F1A\u8BDD\u540D\u79F0\u4E0D\u80FD\u4E3A\u7A7A");
        const res = await fetch("/api/sessions/" + encodeURIComponent(sid) + "/rename", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ alias })
        });
        if (!res.ok) throw new Error(await res.text() || "\u91CD\u547D\u540D\u5931\u8D25");
        await refreshSessions();
        broadcastSessions("conversation.updated", { session_id: sid });
        broadcast("session", "session.renamed", { session_id: sid, alias });
        return { status: "ok", alias };
      }
      // 删除会话：对齐后端 DELETE /api/sessions/{id}
      case "session.delete": {
        const sid = String(payload.session_id || "");
        if (!sid) throw new Error("\u7F3A\u5C11 session_id");
        const wasActive = groupState.activeSessionId === sid;
        if (wasActive) {
          const other = groupState.sessions.find((s) => s.id !== sid);
          if (other) {
            const co = await fetch("/api/sessions/" + encodeURIComponent(other.id) + "/checkout", { method: "POST" });
            if (!co.ok) throw new Error(await co.text() || "\u5207\u6362\u4F1A\u8BDD\u5931\u8D25");
          }
        }
        const res = await fetch("/api/sessions/" + encodeURIComponent(sid), { method: "DELETE" });
        if (!res.ok) throw new Error(await res.text() || "\u5220\u9664\u5931\u8D25");
        if (wasActive) groupState.activeSessionId = "";
        await refreshSessions();
        updateEmpty();
        broadcastSessions(wasActive ? "session.switched" : "conversation.updated", { session_id: groupState.activeSessionId });
        return { status: "ok" };
      }
      // ---- 项目（会话分类器）：对齐后端 /api/projects* ----
      case "projects.list": {
        const list = await (await fetch("/api/projects")).json();
        return Array.isArray(list) ? list : [];
      }
      case "projects.create": {
        const name = String(payload.name || "").trim();
        if (!name) throw new Error("\u9879\u76EE\u540D\u79F0\u4E0D\u80FD\u4E3A\u7A7A");
        const res = await fetch("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name })
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, "\u521B\u5EFA\u9879\u76EE\u5931\u8D25"));
        const data = await res.json();
        broadcast("sidebar", "projects.updated", { project_id: data.id });
        return data;
      }
      case "projects.update": {
        const pid = String(payload.project_id || "");
        if (!pid) throw new Error("\u7F3A\u5C11 project_id");
        const body = {};
        if (payload.name !== void 0) body.name = String(payload.name).trim();
        const res = await fetch("/api/projects/" + encodeURIComponent(pid), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, "\u4FDD\u5B58\u9879\u76EE\u5931\u8D25"));
        const data = await res.json();
        broadcast("sidebar", "projects.updated", { project_id: pid });
        return data;
      }
      case "projects.delete": {
        const pid = String(payload.project_id || "");
        if (!pid) throw new Error("\u7F3A\u5C11 project_id");
        const deleteSessions = !!payload.delete_sessions;
        if (deleteSessions) {
          const inProject = groupState.sessions.filter((s) => String(s.project_id || "") === pid);
          if (inProject.some((s) => s.id === groupState.activeSessionId)) {
            const other = groupState.sessions.find((s) => String(s.project_id || "") !== pid);
            if (!other) throw new Error("\u9879\u76EE\u5185\u53EA\u5269\u5F53\u524D\u6D3B\u8DC3\u4F1A\u8BDD\uFF0C\u8BF7\u5148\u65B0\u5EFA\u6216\u5207\u6362\u5230\u5176\u5B83\u4F1A\u8BDD\u518D\u5220\u9664");
            const co = await fetch("/api/sessions/" + encodeURIComponent(other.id) + "/checkout", { method: "POST" });
            if (!co.ok) throw new Error(await apiErrorMessage(co, "\u5207\u6362\u4F1A\u8BDD\u5931\u8D25"));
            groupState.activeSessionId = other.id;
            groupState.draft = false;
            groupState.draftProjectId = "";
            broadcastSessions("session.switched", { session_id: other.id });
          }
        }
        const res = await fetch("/api/projects/" + encodeURIComponent(pid) + "?delete_sessions=" + (deleteSessions ? "true" : "false"), { method: "DELETE" });
        if (!res.ok) throw new Error(await apiErrorMessage(res, "\u5220\u9664\u9879\u76EE\u5931\u8D25"));
        const data = await res.json();
        await refreshSessions();
        updateEmpty();
        broadcast("sidebar", "projects.updated", { project_id: pid });
        broadcastSessions("conversation.updated", { session_id: groupState.activeSessionId });
        return data;
      }
      // 会话归入/移出项目（空 project_id = 移回未分类）；不改写会话系统提示
      case "session.moveToProject": {
        const sid = String(payload.session_id || "");
        const pid = String(payload.project_id || "");
        if (!sid) throw new Error("\u7F3A\u5C11 session_id");
        const res = await fetch("/api/sessions/" + encodeURIComponent(sid) + "/project", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: pid })
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, "\u79FB\u52A8\u4F1A\u8BDD\u5931\u8D25"));
        const data = await res.json();
        await refreshSessions();
        broadcast("sidebar", "projects.updated", { project_id: pid });
        broadcastSessions("conversation.updated", { session_id: groupState.activeSessionId });
        return data;
      }
      // 待审批队列：对齐后端 GET /api/requests（主进程会在轮询时顺带 kick skill/sensor 免审测试）
      case "requests.list": {
        const list = await (await fetch("/api/requests")).json();
        return Array.isArray(list) ? list : [];
      }
      // 审批裁决：对齐后端 POST /api/requests/{id}/resolve
      case "requests.resolve": {
        const rid = String(payload.request_id || "");
        if (!rid) throw new Error("\u7F3A\u5C11 request_id");
        const res = await fetch("/api/requests/" + encodeURIComponent(rid) + "/resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            approved: !!payload.approved,
            feedback: String(payload.feedback || ""),
            ignore: !!payload.ignore,
            duration: Number(payload.duration || 5)
          })
        });
        if (!res.ok) throw new Error(await res.text() || "\u88C1\u51B3\u5931\u8D25");
        const data = await res.json();
        broadcastAll("requests.updated", { request_id: rid });
        return data;
      }
      case "chat.interrupt":
        return (await fetch("/api/chat/interrupt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })).json();
      // 会话分支：基于当前会话新建分支并切换过去（对齐后端 POST /api/sessions/{id}/branch）
      case "session.branch": {
        if (await activeSessionBusy()) return { status: "busy" };
        const sid = String(payload.session_id || groupState.activeSessionId || "");
        if (!sid) throw new Error("\u7F3A\u5C11 session_id");
        const res = await fetch("/api/sessions/" + encodeURIComponent(sid) + "/branch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ alias: String(payload.alias || "") })
        });
        if (!res.ok) throw new Error(await res.text() || "\u5206\u652F\u5931\u8D25");
        const data = await res.json();
        if (data && data.id) {
          groupState.activeSessionId = data.id;
          await refreshSessions();
          updateEmpty();
          broadcastSessions("session.switched", { session_id: data.id });
        }
        return data;
      }
      // trace2skill：分配技能工厂并向当前会话注入 evolve_factory 事件（对齐原 UI confirmTraceToSkill）
      case "chat.traceToSkill": {
        const sid = String(payload.session_id || groupState.activeSessionId || "");
        if (!sid) throw new Error("\u7F3A\u5C11 session_id");
        const name = String(payload.name || "").trim();
        const goal = String(payload.goal || "").trim();
        if (!name) throw new Error("\u6280\u80FD\u540D\u79F0\u4E0D\u80FD\u4E3A\u7A7A");
        if (!goal) throw new Error("\u671F\u671B\u63CF\u8FF0\u4E0D\u80FD\u4E3A\u7A7A");
        const initRes = await fetch("/api/evolve/init", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "skill", name, is_upgrade: !!payload.is_upgrade, goal, trace: true, session_id: sid })
        });
        if (!initRes.ok) throw new Error(await initRes.text() || "\u5DE5\u5382\u5206\u914D\u5931\u8D25");
        const initData = await initRes.json();
        const factoryPath = "/agent_vm/skill_workplace/" + initData.workplace_id + "/" + name;
        const content = "\u7528\u6237\u89E6\u53D1\u4E86\u6280\u80FD\u5DE5\u5382\uFF0C\u5DF2\u4E3A\u4F60\u5206\u914D\u4E86\u6280\u80FD\u5DE5\u5382" + factoryPath + "/\uFF0C\u8BF7\u6839\u636E\u7528\u6237\u9700\u8981\u548C\u672C\u6B21\u4F1A\u8BDD\u7684\u4EA4\u4E92\u8BB0\u5F55\u4E0E\u5386\u53F2\u7ECF\u9A8C\u5347\u7EA7\u6216\u521B\u5EFA\u5BF9\u5E94\u6280\u80FD\u3002\u4EE5\u4E0B\u662F\u7528\u6237\u671F\u671B\uFF1A\n" + goal;
        const batchRes = await fetch("/api/chat/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid, events: [{ type: "evolve_factory", content }] })
        });
        if (!batchRes.ok) throw new Error(await batchRes.text() || "\u4EFB\u52A1\u4E0B\u53D1\u5931\u8D25");
        setEmpty(false);
        broadcastSessions("conversation.updated", { session_id: sid });
        return { status: "ok" };
      }
      // ---- 浮层原语：宿主只认"调用方所属实例"，做通用移动/关闭（不感知具体插件；many 槽各实例独立） ----
      case "slot.move": {
        const el = origin && origin.inst;
        if (!el) throw new Error("\u7F3A\u5C11\u8C03\u7528\u65B9\u5B9E\u4F8B");
        if (payload.dx || payload.dy) {
          const r = el.getBoundingClientRect();
          const w = el.offsetWidth, h = el.offsetHeight;
          el.style.right = "auto";
          el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r.left + (Number(payload.dx) || 0))) + "px";
          el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r.top + (Number(payload.dy) || 0))) + "px";
        }
        return { status: "ok" };
      }
      case "slot.close": {
        const el = origin && origin.inst;
        if (el) el.style.display = "none";
        return { status: "ok" };
      }
      // 插件请求「关闭并记住」：与白条开关共用同一状态源（webminConfig.rail.hidden），
      // 重启后保持关闭；白条图标同步置灰，点白条图标即可重新启用
      case "slot.hide": {
        const pid = origin && origin.pluginId;
        if (!pid) throw new Error("\u7F3A\u5C11\u8C03\u7528\u65B9\u63D2\u4EF6");
        setPluginHidden(pid, true);
        buildRail();
        return { status: "ok" };
      }
      // ---- 配置 ----
      case "config.get":
        return configByPlugin[payload.plugin_id] || {};
      case "config.set": {
        const pid = payload.plugin_id;
        if (!pid) throw new Error("\u7F3A\u5C11 plugin_id");
        configByPlugin[pid] = Object.assign({}, configByPlugin[pid], payload.config || {});
        applyConfigTo(pid);
        broadcast("settings", "config.updated", { plugin_id: pid, config: configByPlugin[pid] });
        await saveConfig();
        return configByPlugin[pid];
      }
      case "settings.meta":
        return { plugins: groupState.plugins, config: configByPlugin };
      case "settings.open": {
        const tab = String(payload && payload.tab || "");
        if (tab && CONFIG_NAV.indexOf(tab) >= 0) setSettingsTab(tab);
        setSettingsOpen(true);
        return { status: "ok" };
      }
      case "settings.close":
        setSettingsOpen(false);
        return { status: "ok" };
      // ---- 引用 ----
      case "dialog.files": {
        const pc = HOST.purrcat;
        if (!pc || !pc.openDialog) throw new Error("\u672C\u5730\u6587\u4EF6\u9009\u62E9\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        return pc.openDialog({ directory: false, properties: ["openFile", "multiSelections"] });
      }
      case "dialog.folder": {
        const pc = HOST.purrcat;
        if (!pc || !pc.openDialog) throw new Error("\u672C\u5730\u6587\u4EF6\u5939\u9009\u62E9\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        return pc.openDialog({ directory: true, properties: ["openDirectory", "multiSelections"] });
      }
      // 由插件用 <input type="file"> 选好 File 后，交给宿主解析真实绝对路径
      case "dialog.resolveFiles": {
        if (!HOST.purrcat || !HOST.purrcat.getPathForFile) throw new Error("\u672C\u5730\u8DEF\u5F84\u89E3\u6790\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        const files = Array.isArray(payload.files) ? payload.files : [];
        const paths = [];
        for (const f of files) {
          try {
            const p = HOST.purrcat.getPathForFile(f);
            if (p) paths.push(p);
          } catch (_) {
          }
        }
        return { paths };
      }
      case "dialog.pickWallpaper": {
        const pc = HOST.purrcat;
        if (!pc || !pc.openDialog) throw new Error("\u672C\u5730\u58C1\u7EB8\u9009\u62E9\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        const r = await pc.openDialog({ properties: ["openFile"], filters: [{ name: "Walls", extensions: ["png", "jpg", "jpeg", "gif", "webp", "bmp", "mp4", "webm", "mov"] }] });
        const p = pickPath(r);
        if (!p) return null;
        const up = await (await fetch("/api/webmin/wallpaper", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p }) })).json();
        return up;
      }
      case "plugin.delete": {
        if (!payload.plugin_id) throw new Error("\u7F3A\u5C11 plugin_id");
        const res = await fetch(`/api/webmin/plugin/${encodeURIComponent(payload.plugin_id)}/delete`, { method: "POST" });
        if (!res.ok) throw new Error(await res.text() || "\u5220\u9664\u5931\u8D25");
        await reloadManifest();
        return { status: "ok" };
      }
      case "plugin.activate": {
        const p = (groupState.plugins || []).find((x) => x.id === payload.plugin_id);
        if (!p) throw new Error("\u63D2\u4EF6\u4E0D\u5B58\u5728");
        activateSlotPlugin(p);
        return { status: "ok" };
      }
      case "ref.graphs": {
        const graphs = await (await fetch("/api/graphs")).json();
        return (graphs || []).map((g) => typeof g === "string" ? g : g.name);
      }
      // ---- 插件自带后端 RPC ----
      case "plugin.rpc": {
        const pid = payload.plugin_id;
        if (!pid) throw new Error("\u7F3A\u5C11 plugin_id");
        const res = await fetch(`/api/webmin/plugin-rpc/${encodeURIComponent(pid)}/${encodeURIComponent(payload.handler || "")}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payload: payload.payload || {}, timeout: payload.timeout })
        });
        if (!res.ok) throw new Error(await res.text() || "\u63D2\u4EF6\u540E\u7AEF\u8C03\u7528\u5931\u8D25");
        return (await res.json()).result;
      }
      // ---- 内置浏览器（原生 WebContentsView，非 iframe）----
      // 插件 iframe 拿不到 window.purrcat（preload 只在主 frame 生效，未开
      // nodeIntegrationInSubFrames），因此由宿主把原生浏览器原语转发给 purrcat，
      // 并负责「插件 iframe 局部坐标 → 主窗口内容区坐标」的换算。
      case "browser.available":
        return { available: !!(HOST.purrcat && HOST.purrcat.browserNewTab) };
      case "browser.bounds": {
        const pc = HOST.purrcat;
        if (!pc || !pc.browserSetBounds) throw new Error("\u5185\u7F6E\u6D4F\u89C8\u5668\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        let ox = 0, oy = 0;
        const fr = origin && origin.iframe;
        if (fr && fr.getBoundingClientRect) {
          const r = fr.getBoundingClientRect();
          ox = r.left;
          oy = r.top;
        }
        await pc.browserSetBounds(
          Math.round(ox + (Number(payload.x) || 0)),
          Math.round(oy + (Number(payload.y) || 0)),
          Math.round(Number(payload.w) || 1),
          Math.round(Number(payload.h) || 1),
          1
        );
        return { status: "ok" };
      }
      case "browser.hide": {
        if (HOST.purrcat && HOST.purrcat.browserHide) await HOST.purrcat.browserHide();
        return { status: "ok" };
      }
      case "browser.newTab": {
        if (!HOST.purrcat || !HOST.purrcat.browserNewTab) throw new Error("\u5185\u7F6E\u6D4F\u89C8\u5668\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        return { tabId: await HOST.purrcat.browserNewTab(payload.url || "") };
      }
      case "browser.closeTab": {
        if (HOST.purrcat && HOST.purrcat.browserCloseTab) await HOST.purrcat.browserCloseTab(payload.tabId, payload.nextTabId || void 0);
        return { status: "ok" };
      }
      case "browser.switchTab": {
        if (HOST.purrcat && HOST.purrcat.browserSwitchTab) await HOST.purrcat.browserSwitchTab(payload.tabId);
        return { status: "ok" };
      }
      case "browser.navigate": {
        if (HOST.purrcat && HOST.purrcat.browserNavigate) await HOST.purrcat.browserNavigate(payload.tabId, payload.url);
        return { status: "ok" };
      }
      case "browser.reload": {
        if (HOST.purrcat && HOST.purrcat.browserReload) await HOST.purrcat.browserReload(payload.tabId);
        return { status: "ok" };
      }
      case "browser.goBack": {
        if (HOST.purrcat && HOST.purrcat.browserGoBack) await HOST.purrcat.browserGoBack(payload.tabId);
        return { status: "ok" };
      }
      case "browser.goForward": {
        if (HOST.purrcat && HOST.purrcat.browserGoForward) await HOST.purrcat.browserGoForward(payload.tabId);
        return { status: "ok" };
      }
      case "browser.pickStart": {
        if (!HOST.purrcat || !HOST.purrcat.browserPickStart) throw new Error("\u5185\u7F6E\u6D4F\u89C8\u5668\u4EC5\u5728 Electron \u5185\u53EF\u7528");
        return await HOST.purrcat.browserPickStart(payload.tabId);
      }
      case "browser.pickEnd": {
        if (HOST.purrcat && HOST.purrcat.browserPickEnd) await HOST.purrcat.browserPickEnd(payload.tabId);
        return { status: "ok" };
      }
      case "browser.locate": {
        if (!HOST.purrcat || !HOST.purrcat.browserLocate) return null;
        return await HOST.purrcat.browserLocate(payload.tabId, payload.x, payload.y);
      }
      case "browser.pickElement": {
        if (!HOST.purrcat || !HOST.purrcat.browserCdpPickElement) return null;
        return await HOST.purrcat.browserCdpPickElement(payload.tabId, payload.x, payload.y);
      }
      case "browser.openExternal": {
        if (HOST.purrcat && HOST.purrcat.openExternal) await HOST.purrcat.openExternal(payload.url);
        return { status: "ok" };
      }
      // 网页链接统一路由：主进程拦下的 target=_blank/window.open 与插件显式调用都走这里
      case "browser.openUrl":
        return openUrlInBrowserPanel(payload.url);
      // 草稿态下选择 Agent Loop（范式）：仅记录在宿主，待首条消息建会话时生效。
      // 与 session.* 系列同属宿主对外契约，插件无需感知彼此即可热插拔。
      case "session.setDraftParadigm": {
        if (!groupState.draft) return { status: "noop" };
        groupState.draftParadigm = String(payload.paradigm || "");
        return { status: "ok", paradigm: groupState.draftParadigm };
      }
      case "state.get":
        return { ...groupState, plugins: void 0, activeBySlot: { ...activeBySlot } };
      // 子代理分支视图切换：会话插件据此切换查看分支（同时由分支状态进入/退出输入只读）
      case "branch.select": {
        const bid = String(payload.branch_id || "main");
        groupState.activeBranchId = bid;
        broadcastAll("branch.switched", { branch_id: bid });
        return { status: "ok" };
      }
      default:
        return null;
    }
  }

  // ui/web-minimal/src/host/bus.ts
  async function callAction(actionId, payload = {}, origin) {
    return dispatch(actionId, payload, origin);
  }
  function broadcast(slot, event, data) {
    (frames[slot] || []).forEach((f) => {
      if (f.iframe && f.iframe.contentWindow) {
        f.iframe.contentWindow.postMessage({ type: "event", event, data: data || {} }, "*");
      }
    });
  }
  function broadcastAll(event, data) {
    Object.keys(frames).forEach((k) => {
      broadcast(k, event, data);
    });
  }
  var _nativeCover = null;
  function nativeCoverActive() {
    if (HOST.document.body.classList.contains("settings-open")) return true;
    if (HOST.document.querySelector(".wm-pp_menu")) return true;
    if (HOST.document.querySelector(".settings-card-menu")) return true;
    const modals = HOST.document.querySelectorAll(".wm-modal-wrap");
    for (let i = 0; i < modals.length; i++) {
      if (HOST.getComputedStyle(modals[i]).display !== "none") return true;
    }
    return false;
  }
  function syncNativeCover() {
    const v = nativeCoverActive();
    if (v === _nativeCover) return;
    _nativeCover = v;
    broadcastAll("host.nativeCover", { covered: v });
  }
  HOST.addEventListener("message", (e) => {
    const msg = e.data;
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "callAction") {
      const id = msg.id;
      let srcSlot = null, srcFrame = null;
      Object.keys(frames).forEach((k) => {
        (frames[k] || []).forEach((f) => {
          if (f.iframe && f.iframe.contentWindow === e.source) {
            srcSlot = k;
            srcFrame = f;
          }
        });
      });
      const srcFrameRef = srcFrame;
      const srcPluginId = srcFrameRef ? srcFrameRef.pluginId : null;
      const origin = { slot: srcSlot, pluginId: srcPluginId, inst: srcFrameRef ? srcFrameRef.el : null, iframe: srcFrameRef ? srcFrameRef.iframe : null };
      callAction(msg.actionId, msg.payload, origin).then((data) => {
        if (e.source) e.source.postMessage({ type: "callActionResult", id, ok: true, data }, "*");
      }).catch((err) => {
        if (e.source) e.source.postMessage({ type: "callActionResult", id, ok: false, error: String(err) }, "*");
      });
    }
  });

  // ui/web-minimal/src/host/areas.ts
  var PANEL_CONTAINER_ID = "builtin-panel";
  var PANEL_AREA_ICON = "panel-top";
  function areaLabel(area) {
    return AREA_LABEL[area] || area;
  }
  var RAIL_AREA_ORDER = ["session", "panel-container", "popup", "sidebar", "background"];
  function railAreaList() {
    const areas = [];
    groupState.plugins.forEach((p) => {
      const def = p.slotDef || {};
      if (def.type === "panel" || !def.area) return;
      if (tileMode() && def.area === "panel-container") return;
      if (areas.indexOf(def.area) < 0) areas.push(def.area);
    });
    const rank = (a) => {
      const i = RAIL_AREA_ORDER.indexOf(a);
      return i < 0 ? RAIL_AREA_ORDER.length : i;
    };
    return areas.sort((a, b) => rank(a) - rank(b));
  }
  function areaCandidates(area) {
    return groupState.plugins.filter((p) => (p.slotDef || {}).area === area && isRailPlugin(p));
  }
  function areaOpen(area) {
    return areaCandidates(area).filter(pluginVisible);
  }
  function areaOn(area) {
    return areaOpen(area).length > 0;
  }
  function areaActive(area) {
    const mounted = pluginBySlot[area];
    if (mounted) return mounted;
    return areaOpen(area)[0] || null;
  }
  function activateAreaCandidate(area, cand) {
    if (cand) activateSlotPlugin(cand);
  }
  function deactivateArea(area) {
    if (!railState.hidden) railState.hidden = {};
    areaCandidates(area).forEach((p) => {
      railState.hidden[p.id] = true;
      if ((p.slotDef || {}).type !== "fixed") applySlotHidden(p.slot, true);
    });
    if (slotMap[area]) refreshFixedSlot(area);
    if (tileMode()) syncTiles();
    persistRail().catch(() => {
    });
    syncNativeCover();
  }
  function refreshAreaRail(area) {
    const btn = railButtons["__area__:" + area];
    if (!btn) return;
    btn.classList.remove("on", "off");
    btn.classList.add(areaOn(area) ? "on" : "off");
    const g = btn.querySelector(".rail-glyph");
    if (!g) return;
    const target = areaActive(area) || areaCandidates(area)[0] || null;
    if (target) paintPluginIcon(g, target);
    else paintIcon(g, PANEL_AREA_ICON, "\u25A4");
  }
  function makeAreaRailButton(area) {
    const btn = HOST.document.createElement("button");
    btn.className = "rail-ico";
    btn.title = areaLabel(area);
    const g = HOST.document.createElement("span");
    g.className = "rail-glyph";
    btn.appendChild(g);
    const nm = HOST.document.createElement("span");
    nm.className = "rail-name";
    nm.textContent = areaLabel(area);
    btn.appendChild(nm);
    railButtons["__area__:" + area] = btn;
    refreshAreaRail(area);
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const cands = areaCandidates(area);
      if (!cands.length) return;
      if (cands.length <= 1) {
        togglePluginOpen(cands[0]);
        buildRail();
        return;
      }
      openAreaMenu(area, btn, cands, areaOpen(area));
    });
    return btn;
  }
  function openAreaMenu(area, anchor, cands, openList) {
    const already = HOST.document.getElementById("rail-area-menu");
    closePanelMenus();
    if (already) return;
    const menu = HOST.document.createElement("div");
    menu.className = "wm-pp_menu";
    menu.id = "rail-area-menu";
    const openIds = (openList || []).map((x) => x.id);
    cands.forEach((c) => {
      const isActive = openIds.indexOf(c.id) >= 0;
      const item = HOST.document.createElement("div");
      item.className = "wm-pp_menu-item" + (isActive ? " active" : "");
      const g = HOST.document.createElement("span");
      g.className = "wm-pp_menu-ico";
      paintPluginIcon(g, c);
      item.appendChild(g);
      const nm = HOST.document.createElement("span");
      nm.textContent = c.name || c.id;
      item.appendChild(nm);
      if (isActive) {
        const tag = HOST.document.createElement("span");
        tag.className = "wm-pp_menu-tag";
        tag.textContent = "\u4F7F\u7528\u4E2D";
        item.appendChild(tag);
      }
      item.addEventListener("click", () => {
        closePanelMenus();
        activateAreaCandidate(area, c);
        buildRail();
      });
      menu.appendChild(item);
    });
    if (openIds.length) {
      const off = HOST.document.createElement("div");
      off.className = "wm-pp_menu-item";
      const og = HOST.document.createElement("span");
      og.className = "wm-pp_menu-ico";
      paintIcon(og, "x", "\u2715");
      off.appendChild(og);
      const onm = HOST.document.createElement("span");
      onm.textContent = "\u5173\u95ED" + areaLabel(area);
      off.appendChild(onm);
      off.addEventListener("click", () => {
        closePanelMenus();
        deactivateArea(area);
        buildRail();
      });
      menu.appendChild(off);
    }
    HOST.document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const top = Math.min(r.top, HOST.innerHeight - menu.offsetHeight - 8);
    menu.style.left = r.right + 6 + "px";
    menu.style.right = "auto";
    menu.style.top = Math.max(8, top) + "px";
    syncNativeCover();
  }

  // ui/web-minimal/src/host/rail.ts
  var RAIL_STAGES = 2;
  function isRailPlugin(p) {
    return p && p.entry;
  }
  function railHidden(id) {
    return !!(railState.hidden && railState.hidden[id]);
  }
  function applySlotHidden(slot, hidden) {
    const pbar = panelBar;
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (anchor) anchor.style.display = hidden ? "none" : "";
    if (slot === "sidebar") {
      HOST.document.body.classList.toggle("rail-nosidebar", !!hidden);
      applyPanelWidth();
    }
    if (slot === "session") applyPanelWidth();
    HOST.document.querySelectorAll(`.wm-float[data-fslot="${slot}"]`).forEach((el) => {
      el.style.display = hidden ? "none" : "block";
    });
    HOST.document.querySelectorAll(`.wm-modal-wrap[data-mslot="${slot}"]`).forEach((el) => {
      el.style.display = hidden ? "none" : "flex";
    });
    if (slot === "panel") {
      HOST.document.querySelectorAll('.wm-ppanel[data-pslot="panel"]').forEach((el) => {
        el.style.display = hidden ? "none" : "flex";
      });
      const pcHost = HOST.document.querySelector('[data-slot="panel-container"]');
      if (pcHost && thirdPartyContainerPlugin()) pcHost.style.display = hidden ? "none" : "";
      if (hidden) {
        HOST.document.body.classList.remove("has-panels");
        if (pbar) pbar.style.display = "none";
      } else {
        HOST.document.body.classList.add("has-panels");
        if (pbar) pbar.style.display = "";
        applyPanelWidth();
      }
    }
    syncNativeCover();
  }
  function persistRail() {
    return fetch("/api/webmin/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plugins: configByPlugin, rail: railState })
    }).then((res) => {
      if (!res.ok) throw new Error(String(res.status));
    });
  }
  function persistActive2() {
    return fetch("/api/webmin/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: activeBySlot })
    }).then((res) => {
      if (!res.ok) throw new Error(String(res.status));
    }).catch(() => {
    });
  }
  function applyPersistedHidden() {
    Object.keys(railState.hidden).forEach((id) => {
      if (id === PANEL_CONTAINER_ID) return;
      const slot = slotOfPlugin(id);
      if (!slot || !railState.hidden[id]) return;
      const p = groupState.plugins.find((x) => x.id === id);
      const pt = p ? (p.slotDef || {}).type : "";
      if (pt === "fixed" || pt === "panel") return;
      applySlotHidden(slot, true);
    });
    applySlotHidden("panel", !panelContainerVisible());
    if (tileMode()) syncTiles();
  }
  function applyRailStage() {
    HOST.document.body.classList.remove("rail-0", "rail-1");
    HOST.document.body.classList.add("rail-" + railState.stage);
    const t = HOST.document.getElementById("railToggle");
    if (t) {
      paintIcon(t, "panel-left", "\u2630");
      t.title = "\u6536\u8D77 / \u5C55\u5F00\u63D2\u4EF6\u680F";
    }
    reflowFloats();
    applyPanelWidth();
  }
  function applyRailOpacity() {
    let o = typeof railState.opacity === "number" ? railState.opacity : 1;
    o = Math.min(1, Math.max(0, o));
    const rail = HOST.document.getElementById("rail");
    if (rail) rail.style.setProperty("--wm-rail-bg", "rgba(248,248,249," + o.toFixed(3) + ")");
  }
  function cycleRail() {
    railState.stage = (railState.stage + 1) % RAIL_STAGES;
    applyRailStage();
    persistRail().catch(() => {
    });
  }
  function bindRailToggle() {
    const t = HOST.document.getElementById("railToggle");
    if (t) t.addEventListener("click", cycleRail);
  }
  function setPluginHidden(id, hidden) {
    if (!railState.hidden) railState.hidden = {};
    if (hidden) railState.hidden[id] = true;
    else delete railState.hidden[id];
    const slot = slotOfPlugin(id);
    if (slot) {
      const p = groupState.plugins.find((x) => x.id === id);
      if (p && (p.slotDef || {}).type === "fixed") refreshFixedSlot(slot);
      else applySlotHidden(slot, hidden);
    }
    if (tileMode()) syncTiles();
    persistRail().catch(() => {
    });
  }
  function buildRail() {
    const iconsEl = HOST.document.getElementById("railIcons");
    if (!iconsEl) return;
    applyRailStage();
    iconsEl.innerHTML = "";
    const footEl = HOST.document.getElementById("railFoot") || iconsEl;
    if (footEl !== iconsEl) footEl.innerHTML = "";
    railAreaList().forEach((area) => {
      iconsEl.appendChild(makeAreaRailButton(area));
    });
    const sb = HOST.document.createElement("button");
    sb.className = "rail-ico";
    sb.id = "railSettings";
    sb.title = areaLabel("settings");
    const sg = HOST.document.createElement("span");
    sg.className = "rail-glyph";
    paintIcon(sg, "settings", "\u2699");
    sb.appendChild(sg);
    const snm = HOST.document.createElement("span");
    snm.className = "rail-name";
    snm.textContent = areaLabel("settings");
    sb.appendChild(snm);
    const sbOpen = HOST.document.body.classList.contains("settings-open");
    sb.classList.toggle("on", sbOpen);
    sb.classList.toggle("off", !sbOpen);
    sb.addEventListener("click", () => setSettingsOpen(!HOST.document.body.classList.contains("settings-open")));
    footEl.appendChild(sb);
    railButtons["__settings__"] = sb;
    applyRailOpacity();
  }

  // ui/web-minimal/src/host/app.ts
  function wireWindowControls() {
    const pc = HOST.purrcat;
    if (!pc) return;
    HOST.document.body.classList.add("electron");
    const byId = (id) => HOST.document.getElementById(id);
    if (byId("winMinimize")) byId("winMinimize").addEventListener("click", () => pc.winMinimize());
    if (byId("winMaximize")) byId("winMaximize").addEventListener("click", () => pc.winToggleMaximize());
    if (byId("winClose")) byId("winClose").addEventListener("click", () => pc.winClose());
  }
  async function boot() {
    wireWindowControls();
    HOST.document.addEventListener("click", function() {
      closeSettingsMenus();
      closePanelMenus();
    });
    let manifest;
    try {
      manifest = await (await fetch("/api/webmin/manifest")).json();
    } catch (err) {
      HOST.document.body.innerHTML = '<div style="padding:24px;font-family:system-ui;color:#8b96a3">\u6781\u7B80\u6A21\u5F0F\u65E0\u6CD5\u52A0\u8F7D\uFF1A\u540E\u7AEF\u672A\u5728\u7EBF\uFF08/api/webmin/manifest \u4E0D\u53EF\u7528\uFF09\u3002\u8BF7\u5148\u542F\u52A8\u540E\u7AEF\u3002</div>';
      return;
    }
    applyManifestState(manifest);
    await loadPanelShell();
    applyRailOpacity();
    buildSlotIndex();
    mountAll();
    bindRailToggle();
    buildRail();
    applyPanelContainerCfg();
    applyPersistedHidden();
    if (HOST.purrcat && HOST.purrcat.onTabEvent) {
      HOST.purrcat.onTabEvent(function(evt) {
        broadcastAll("browser.tabEvent", evt);
      });
    }
    if (HOST.purrcat && HOST.purrcat.onOpenUrl) {
      HOST.purrcat.onOpenUrl(function(url) {
        openUrlInBrowserPanel(url);
      });
    }
    syncNativeCover();
    try {
      const list = await (await fetch("/api/sessions")).json();
      if (Array.isArray(list) && list.length) {
        groupState.sessions = list;
        groupState.activeSessionId = list[0].id || "";
        broadcastSessions("session.switched", { session_id: groupState.activeSessionId });
      }
    } catch (_) {
    }
    updateEmpty();
  }

  // ui/web-minimal/src/host/main.ts
  HOST.purrcatWebmin = { callAction };
  if (HOST.document.readyState === "loading") {
    HOST.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
//# sourceMappingURL=host.js.map
