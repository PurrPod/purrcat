(function () {
  // ============================================================
  // 会话面板插件：历史会话 + 输入条（原两个插件合并为单个 area=session 插件）
  // ============================================================

  // ---------- 宿主通信 ----------
  var seq = 0;
  function callAction(actionId, payload) {
    return new Promise(function (resolve, reject) {
      var id = ++seq;
      function onMsg(e) {
        var m = e.data;
        if (m && m.type === 'callActionResult' && m.id === id) {
          window.removeEventListener('message', onMsg);
          if (m.ok) resolve(m.data); else reject(new Error(m.error));
        }
      }
      window.addEventListener('message', onMsg);
      window.parent.postMessage({ type: 'callAction', id: id, actionId: actionId, payload: payload || {} }, '*');
    });
  }
  function pickPath(r) {
    if (!r) return null;
    if (Array.isArray(r)) return r[0];
    if (Array.isArray(r.filePaths)) return r.filePaths[0];
    if (Array.isArray(r.paths)) return r.paths[0];
    if (typeof r === 'string') return r;
    if (typeof r.path === 'string') return r.path;
    return null;
  }

  // ---------- 元素引用 ----------
  var listEl = document.getElementById('list');
  var input = document.getElementById('input');
  var sendBtn = document.getElementById('send');
  var plusBtn = document.getElementById('plus');
  var refPanel = document.getElementById('refPanel');
  var catsEl = document.getElementById('cats');
  var rName = document.getElementById('rName');
  var rItems = document.getElementById('rItems');
  var quotesEl = document.getElementById('quotes');

  // ---------- 面板底色 / 展示开关（历史 + 输入同属一个面板，共用一套配置） ----------
  // 会话面板底色：白色，可调透明度（输入条悬浮其上，二者不互相遮盖）
  var DEF_OP = 1;
  // 展示开关：工具调用 / 思考内容默认展示（保持既有行为）；workflow hint 为系统注入，
  // 默认不展示（与原 UI 一致），用户可在设置里打开
  var show = { tool: true, reasoning: true, hint: true };
  function applyPanel(cfg) {
    var o = cfg && typeof cfg.opacity === 'number' ? cfg.opacity : DEF_OP;
    o = Math.max(0, Math.min(1, o));
    document.body.style.backgroundColor = 'rgba(255,255,255,' + o.toFixed(2) + ')';
    show.tool = !cfg || cfg.show_tool_calls !== false;
    show.reasoning = !cfg || cfg.show_reasoning !== false;
    show.hint = !cfg || cfg.show_workflow_hint !== false;
  }
  function applyConfig(cfg) {
    var before = JSON.stringify(show);
    applyPanel(cfg);
    // 展示开关变化需要重绘消息；仅透明度变化不必重绘
    if (JSON.stringify(show) !== before && typeof lastRows !== 'undefined' && lastRows) renderMessages(lastRows);
  }
  window.addEventListener('message', function (e) {
    var m = e.data;
    if (!m || typeof m !== 'object') return;
    if (m.type === 'configApply') applyConfig(m.config);
    else if (m.type === 'event' && m.event === 'config.updated') { callAction('config.get', { plugin_id: 'builtin-history' }).then(applyConfig).catch(function () {}); }
  });
  callAction('config.get', { plugin_id: 'builtin-history' }).then(applyConfig).catch(function () {});

  // ---------- 工具函数 ----------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]; });
  }
  function extractFrom(o) {
    if (typeof o.content === 'string') return o.content;
    if (typeof o.error === 'string') return o.error;
    if (typeof o.output === 'string' || typeof o.output === 'number') return String(o.output);
    for (var k in o) { var v = o[k]; if (typeof v === 'string' && v.length < 400) return v; }
    try { return JSON.stringify(o); } catch (e) { return ''; }
  }
  // ---- 用户消息解析：只保留 type=user 的正文，*-quote 作附件，workflow_hint 单独归类 ----
  // times 收集 type=user 事件的发送时间（MM-DD HH:MM:SS），用于计算两次用户输入之间的任务耗时。
  function parseUser(content) {
    var att = [], msgs = [], hints = [], times = [];
    try {
      var d = JSON.parse(content);
      if (d && Array.isArray(d.events)) {
        d.events.forEach(function (ev) {
          var t = ev.type || '', c = ev.content || '';
          if (t === 'user') { msgs.push(c); if (ev.time) times.push(ev.time); }
          else if (t === 'workflow_hint') hints.push(c);
          else if (['file-quote','skill-quote','tool-quote','mcp-quote','graph-quote'].indexOf(t) >= 0) att.push(c);
        });
      } else if (d && typeof d === 'object' && d.type === 'workflow_hint') {
        // 系统独立注入：{"type":"workflow_hint","content":"..."}（无 events 外壳）
        hints.push(d.content || '');
      } else { throw 0; }
    } catch (e) {
      // 非事件结构：仅当是普通文本时当作 user 正文；若为 JSON 则忽略，避免把 type=其他 的内容渲染出来
      var s = String(content || '');
      if (!/^[\{\[]/.test(s.trim())) msgs.push(content);
    }
    return { att: att, msgs: msgs, hints: hints, times: times };
  }

  // ---- 复制按钮 ----
  var SVG_HEAD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">';
  var ICON_COPY = SVG_HEAD + '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  var ICON_CHECK = SVG_HEAD + '<path d="M20 6 9 17l-5-5"/></svg>';
  // 工具链步骤图标（与宿主线性风格一致）
  var ICON_TOOL = SVG_HEAD + '<path d="M12 3v4"/><path d="M12 17v4"/><path d="m5.5 5.5 2.8 2.8"/><path d="m15.7 15.7 2.8 2.8"/><path d="M3 12h4"/><path d="M17 12h4"/><path d="m5.5 18.5 2.8-2.8"/><path d="m15.7 8.3 2.8-2.8"/></svg>';
  var ICON_EYE = SVG_HEAD + '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>';
  var ICON_IMAGE = SVG_HEAD + '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></svg>';
  var ICON_PENCIL = SVG_HEAD + '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>';
  var ICON_FILE_PLUS = SVG_HEAD + '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 18v-6"/><path d="M9 15h6"/></svg>';
  var ICON_SEARCH = SVG_HEAD + '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>';
  var ICON_TERM = SVG_HEAD + '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3"/><path d="M13 15h4"/></svg>';
  var ICON_GENERIC = SVG_HEAD + '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>';
  var ICON_ASK = SVG_HEAD + '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = String(text == null ? '' : text);
    ta.style.cssText = 'position:fixed;left:-9999px;top:0;';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
  }
  function copyText(text, btn) {
    var done = function () {
      btn.classList.add('ok'); btn.innerHTML = ICON_CHECK;
      setTimeout(function () { btn.classList.remove('ok'); btn.innerHTML = ICON_COPY; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(String(text == null ? '' : text)).then(done).catch(function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  }
  // 气泡内已有的选区（用户先选了一段再点复制时，只复制这一段）
  function selectionIn(el) {
    var sel = window.getSelection ? window.getSelection() : null;
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return '';
    var n = sel.anchorNode;
    while (n && n !== el) n = n.parentNode;
    if (n !== el) return '';
    return String(sel.toString() || '');
  }
  // 兜底：没有原文时复制「屏幕上看得见的文字」
  function visibleText(el) {
    var t = el.innerText != null ? el.innerText : el.textContent;
    return String(t == null ? '' : t).replace(/[ \t]*\n[ \t]*$/, '');
  }
  // 给气泡挂一个 hover 显示的复制按钮（对齐完整模式 ClipboardCopy 交互）
  // raw：消息的原始 Markdown 文本；整条复制时保留 [文本](链接) 等源码，选中片段时只复制选中部分
  function attachCopy(el, raw) {
    el.classList.add('has-copy');
    var b = document.createElement('button');
    b.className = 'copy-btn'; b.type = 'button'; b.title = '复制';
    b.innerHTML = ICON_COPY;
    // 不阻止默认行为的话，点按钮这一下会把用户已有的选区清掉，导致"选中一段再点复制"永远拿到整条消息
    b.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      var picked = selectionIn(el);
      var text = picked || (raw != null ? String(raw) : visibleText(el));
      copyText(text, b);
    });
    el.appendChild(b);
    return el;
  }

  // ---- 轻量提示 ----
  var toastEl = document.getElementById('toast');
  var toastTimer = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('on'); }, 2200);
  }

  // ---------- MCP Apps：ui:// 资源渲染与最小 Host 桥接 ----------
  // 协议（ext-apps）：App 发 ui/initialize → Host 回 hostInfo/hostContext；
  // App 发 initialized 后 Host 推 tool-input / tool-result；App 可发 tools/call 与 size-changed。
  var appPayloads = {};   // appId -> Promise<payload>，避免每次重建重复拉取

  function appTheme() {
    var dark = false;
    try {
      if (window.matchMedia) dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      var bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g);
      if (bg && bg.length >= 3) dark = (+bg[0] + +bg[1] + +bg[2]) / 3 < 128;
    } catch (e) {}
    return dark ? 'dark' : 'light';
  }

  function fetchAppPayload(id) {
    if (!appPayloads[id]) {
      appPayloads[id] = fetch('/api/mcp/apps/' + encodeURIComponent(id) + '/payload')
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .catch(function (e) { delete appPayloads[id]; throw e; });
    }
    return appPayloads[id];
  }

  function postToApp(frame, data) {
    if (frame && frame.contentWindow) frame.contentWindow.postMessage(data, '*');
  }

  function sendToolPayload(frame, id) {
    fetchAppPayload(id).then(function (p) {
      postToApp(frame, { jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: p.arguments || {} } });
      var r = p.result || {};
      var params = { content: r.content || [], isError: false };
      if (r.structuredContent != null) params.structuredContent = r.structuredContent;
      if (r._meta != null) params._meta = r._meta;
      postToApp(frame, { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: params });
    }).catch(function (e) { console.warn('[MCP App] 载荷加载失败', id, e); });
  }

  function callAppTool(frame, id, msg) {
    var params = msg.params || {};
    fetch('/api/mcp/apps/' + encodeURIComponent(id) + '/call', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ tool: params.name || params.tool || '', arguments: params.arguments || {} })
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error((d && d.detail) || ('HTTP ' + r.status));
        return d;
      });
    }).then(function (d) {
      postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: d });
    }).catch(function (e) {
      postToApp(frame, { jsonrpc: '2.0', id: msg.id, error: { code: -32603, message: String((e && e.message) || e) } });
    });
  }

  function contentText(blocks) {
    var out = [];
    for (var i = 0; i < (blocks || []).length; i++) {
      var b = blocks[i];
      if (b && b.type === 'text' && typeof b.text === 'string') out.push(b.text);
    }
    return out.join('\n').trim();
  }

  function appCard(frame) { return frame.closest('.mcp-app'); }

  var ICON_FULL = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2H2v4M10 2h4v4M10 14h4v-4M6 14H2v-4"/></svg>';
  var ICON_BACK = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6h4V2M14 6h-4V2M14 10h-4v4M2 10h4v4"/></svg>';
  var ICON_RELOAD = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M13 8a5 5 0 1 1-1.6-3.7"/><path d="M13 2v3h-3"/></svg>';

  function setAppDisplayMode(frame, mode) {
    var card = appCard(frame);
    var next = mode === 'fullscreen' ? 'fullscreen' : 'inline';
    if (card) {
      card.classList.toggle('fullscreen', next === 'fullscreen');
      var btn = card.querySelector('.mcp-app-mode');
      if (btn) {
        btn.innerHTML = next === 'fullscreen' ? ICON_BACK : ICON_FULL;
        var label = next === 'fullscreen' ? '退出全屏' : '全屏';
        btn.title = label;
        btn.setAttribute('aria-label', label);
      }
    }
    postToApp(frame, { jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { displayMode: next } });
    return next;
  }

  function handleAppMessage(frame, id, msg) {
    var method = msg.method || '';
    if (method === 'ui/initialize' && msg.id != null) {
      var params = msg.params || {};
      postToApp(frame, {
        jsonrpc: '2.0', id: msg.id,
        result: {
          protocolVersion: params.protocolVersion || '2026-01-26',
          hostCapabilities: {
            openLinks: {},
            logging: {},
            message: { text: {} },
            updateModelContext: { text: {}, structuredContent: {} }
          },
          hostInfo: { name: 'PurrCat', version: '1.0.0' },
          hostContext: {
            theme: appTheme(),
            displayMode: 'inline',
            availableDisplayModes: ['inline', 'fullscreen']
          }
        }
      });
      return;
    }
    if (method === 'ui/notifications/initialized') { sendToolPayload(frame, id); return; }
    if (method === 'ui/notifications/size-changed') {
      var h = Number(msg.params && msg.params.height);
      if (h > 0) frame.style.height = Math.max(160, Math.min(900, h)) + 'px';
      return;
    }
    if (method === 'tools/call' && msg.id != null) { callAppTool(frame, id, msg); return; }
    if (method === 'ui/request-display-mode' && msg.id != null) {
      var mode = setAppDisplayMode(frame, msg.params && msg.params.mode);
      postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: { mode: mode } });
      return;
    }
    if (method === 'ui/update-model-context' && msg.id != null) {
      var ctx = msg.params || {};
      var parts = [];
      var text = contentText(ctx.content);
      if (text) parts.push(text);
      if (ctx.structuredContent && typeof ctx.structuredContent === 'object') parts.push(JSON.stringify(ctx.structuredContent));
      if (!parts.length) {
        postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: { isError: true } });
        return;
      }
      var block = '[MCP App 上下文] ' + parts.join('\n');
      input.value = input.value.trim() ? input.value.replace(/\s+$/, '') + '\n\n' + block : block;
      input.dispatchEvent(new Event('input'));
      input.focus();
      postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: {} });
      return;
    }
    if (method === 'ui/message' && msg.id != null) {
      var text = contentText(msg.params && msg.params.content);
      if (!text) {
        postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: { isError: true } });
        return;
      }
      callAction('chat.send', { session_id: activeSessionId, message: text })
        .then(function () { postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: {} }); })
        .catch(function () { postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: { isError: true } }); });
      return;
    }
    if (method === 'ui/open-link' || method === 'ui/notifications/open-link') {
      var url = msg.params && msg.params.url;
      if (url) window.open(url, '_blank', 'noopener');
      if (msg.id != null) {
        postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: url ? { isError: false } : { isError: true } });
      }
      return;
    }
    if (method === 'ping' && msg.id != null) {
      postToApp(frame, { jsonrpc: '2.0', id: msg.id, result: {} });
      return;
    }
    if (msg.id != null) {
      postToApp(frame, { jsonrpc: '2.0', id: msg.id, error: { code: -32601, message: 'Host 未实现 ' + method } });
    }
  }

  window.addEventListener('message', function (ev) {
    var frame = null;
    var nodes = document.querySelectorAll('iframe[data-mcp-app]');
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].contentWindow === ev.source) { frame = nodes[i]; break; }
    }
    if (!frame) return;
    var msg = ev.data;
    if (!msg || typeof msg !== 'object') return;
    handleAppMessage(frame, frame.getAttribute('data-mcp-app'), msg);
  });

  // ---------- GenUI DSL 渲染 ----------
  var genuiMounts = [];
  var genuiStates = {};
  var genuiEpoch = 0;
  var GENUI_BLOCK_RE = /```(?:openui|genui)\s*\n([\s\S]*?)```/g;

  function genuiKey(source) {
    var h = 0;
    for (var i = 0; i < source.length; i++) h = (h * 31 + source.charCodeAt(i)) | 0;
    return 'g' + (h >>> 0).toString(36) + '_' + source.length;
  }

  function splitGenUI(src) {
    var out = [], last = 0, m;
    GENUI_BLOCK_RE.lastIndex = 0;
    while ((m = GENUI_BLOCK_RE.exec(src))) {
      if (m.index > last) out.push({ text: src.slice(last, m.index) });
      out.push({ text: m[1], genui: true });
      last = m.index + m[0].length;
    }
    if (last < src.length) out.push({ text: src.slice(last) });
    return out.filter(function (seg) { return seg.genui || seg.text.trim(); });
  }

  function genuiSource(v) {
    if (!v || typeof v !== 'object') return '';
    var kind = String(v.kind || v.type || '');
    var src = v.source || v.dsl || v.ui || '';
    if ((kind === 'openui' || kind === 'genui' || kind === 'openui-lang') && typeof src === 'string') return src;
    return '';
  }

  function mountGenUI(body, source) {
    var key = genuiKey(source);
    var handle = window.PurrCatGenUI.mount(body, source, {
      state: genuiStates[key] || (genuiStates[key] = {}),
      onMessage: function (text, context) {
        var extra = '';
        if (context && typeof context === 'object' && Object.keys(context).length) {
          try { extra = '\n\n' + JSON.stringify(context, null, 2); } catch (e) { extra = ''; }
        }
        var block = String(text || '') + extra;
        if (!block) return;
        input.value = input.value.trim() ? input.value.replace(/\s+$/, '') + '\n\n' + block : block;
        input.dispatchEvent(new Event('input'));
        input.focus();
      },
      onOpenUrl: function (url) {
        if (window.purrcat && window.purrcat.openExternal) window.purrcat.openExternal(url);
        else window.open(url, '_blank', 'noopener');
      }
    });
    if (handle) genuiMounts.push(handle);
  }

  function genuiBlock(source) {
    var card = document.createElement('div');
    card.className = 'genui-card gui-scope';
    var body = document.createElement('div');
    body.className = 'genui-body';
    card.appendChild(body);
    if (!window.PurrCatGenUI) {
      body.textContent = 'GenUI 运行时未加载';
      return card;
    }
    mountGenUI(body, source);
    return card;
  }

  // ![]() 指向 .genui 文件：消息插入后异步读取并展开
  function hydrateGenUI(root) {
    if (!root || !root.querySelectorAll) return;
    var epoch = genuiEpoch;
    Array.prototype.slice.call(root.querySelectorAll('[data-genui-file]')).forEach(function (card) {
      var path = card.getAttribute('data-genui-file');
      card.removeAttribute('data-genui-file');
      var body = card.querySelector('.genui-body') || card;
      if (!window.PurrCatGenUI) { body.textContent = 'GenUI 运行时未加载'; return; }
      fetch(window.PurrCatGenUI.media.readUrl(path))
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then(function (data) {
          if (epoch !== genuiEpoch) return;
          var source = data && typeof data.content === 'string' ? data.content : '';
          if (!source.trim()) throw new Error('空文件');
          body.innerHTML = '';
          mountGenUI(body, source);
        })
        .catch(function () {
          if (epoch !== genuiEpoch) return;
          body.className = 'genui-body gui-error';
          body.textContent = '无法加载 GenUI 文件：' + path;
        });
    });
  }

  function destroyGenUI() {
    genuiEpoch++;
    genuiMounts.forEach(function (h) { try { h.destroy(); } catch (e) { /* 忽略销毁异常 */ } });
    genuiMounts = [];
  }

  function dataText(v) {
    if (v == null) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    try { return JSON.stringify(v); } catch (_) { return String(v); }
  }

  function buildMcpData(data) {
    var card = document.createElement('div');
    card.className = 'mcp-data';
    var head = document.createElement('div');
    head.className = 'mcp-data-head';
    head.textContent = (data.server || '') + (data.tool ? ' · ' + data.tool : '');
    card.appendChild(head);
    var body = document.createElement('div');
    body.className = 'mcp-data-body';
    var v = data.structuredContent;
    var rows = Array.isArray(v) ? v : null;
    if (rows && rows.length && rows.every(function (x) { return x && typeof x === 'object' && !Array.isArray(x); })) {
      var cols = [];
      rows.slice(0, 20).forEach(function (row) {
        Object.keys(row).forEach(function (k) { if (cols.indexOf(k) < 0 && cols.length < 8) cols.push(k); });
      });
      var table = document.createElement('table');
      var thead = document.createElement('thead');
      var htr = document.createElement('tr');
      cols.forEach(function (c) { var th = document.createElement('th'); th.textContent = c; htr.appendChild(th); });
      thead.appendChild(htr);
      table.appendChild(thead);
      var tbody = document.createElement('tbody');
      rows.slice(0, 8).forEach(function (row) {
        var tr = document.createElement('tr');
        cols.forEach(function (c) {
          var td = document.createElement('td');
          td.textContent = dataText(row[c]);
          td.title = td.textContent;
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      body.appendChild(table);
      if (rows.length > 8) {
        var more = document.createElement('div');
        more.className = 'more';
        more.textContent = '还有 ' + (rows.length - 8) + ' 条';
        body.appendChild(more);
      }
    } else if (v && typeof v === 'object' && !Array.isArray(v)) {
      var kv = document.createElement('div');
      kv.className = 'kv';
      Object.keys(v).slice(0, 30).forEach(function (k) {
        var b = document.createElement('b');
        b.textContent = k;
        var s = document.createElement('span');
        s.textContent = dataText(v[k]);
        kv.appendChild(b);
        kv.appendChild(s);
      });
      body.appendChild(kv);
    } else {
      var pre = document.createElement('pre');
      pre.textContent = dataText(v);
      body.appendChild(pre);
    }
    card.appendChild(body);
    return card;
  }

  function buildMcpApp(app) {
    var id = app.id;
    var card = document.createElement('div');
    card.className = 'mcp-app';
    var head = document.createElement('div');
    head.className = 'mcp-app-head';
    var srv = document.createElement('span');
    srv.className = 'srv';
    srv.textContent = app.server || 'MCP App';
    head.appendChild(srv);
    var acts = document.createElement('div');
    acts.className = 'mcp-app-acts';
    var reload = document.createElement('button');
    reload.type = 'button';
    reload.innerHTML = ICON_RELOAD;
    reload.title = '重新加载';
    reload.setAttribute('aria-label', '重新加载');
    reload.addEventListener('click', function () {
      var f = card.querySelector('iframe');
      if (f) f.src = '/api/mcp/apps/' + encodeURIComponent(id) + '/html?t=' + Date.now();
    });
    var modeBtn = document.createElement('button');
    modeBtn.type = 'button';
    modeBtn.className = 'mcp-app-mode';
    modeBtn.innerHTML = ICON_FULL;
    modeBtn.title = '全屏';
    modeBtn.setAttribute('aria-label', '全屏');
    modeBtn.addEventListener('click', function () {
      var f = card.querySelector('iframe');
      if (f) setAppDisplayMode(f, card.classList.contains('fullscreen') ? 'inline' : 'fullscreen');
    });
    acts.appendChild(modeBtn);
    acts.appendChild(reload);
    head.appendChild(acts);
    card.appendChild(head);
    var frame = document.createElement('iframe');
    frame.setAttribute('data-mcp-app', id);
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups');
    frame.setAttribute('allow', 'fullscreen');
    frame.src = '/api/mcp/apps/' + encodeURIComponent(id) + '/html';
    card.appendChild(frame);
    return card;
  }

  // ---------- Markdown 渲染（marked 解析 + KaTeX 公式 + 代码高亮，代码/表格套独立外壳） ----------
  // 兜底：marked 未加载时退化为「转义 + 保留换行」的纯文本，保证内容不丢
  function mdFallback(src) {
    return src.split(/\n{2,}/).map(function (p) {
      p = p.replace(/\n/g, '<br>');
      return p ? '<p>' + esc(p) + '</p>' : '';
    }).join('');
  }

  // 语言标签：常见别名统一成可读名称，未知语言按原样首字母大写
  var LANG_LABELS = {
    js: 'JavaScript', jsx: 'JavaScript', mjs: 'JavaScript', cjs: 'JavaScript',
    ts: 'TypeScript', tsx: 'TSX', py: 'Python', rs: 'Rust', go: 'Go', rb: 'Ruby',
    sh: 'Shell', bash: 'Bash', zsh: 'Zsh', fish: 'Fish', md: 'Markdown',
    yml: 'YAML', yaml: 'YAML', json: 'JSON', html: 'HTML', css: 'CSS',
    scss: 'SCSS', sass: 'Sass', less: 'Less', cpp: 'C++', cxx: 'C++', hpp: 'C++',
    hxx: 'C++', cc: 'C++', c: 'C', cs: 'C#', fs: 'F#', swift: 'Swift',
    kt: 'Kotlin', java: 'Java', sql: 'SQL', graphql: 'GraphQL',
    dockerfile: 'Dockerfile', makefile: 'Makefile', toml: 'TOML', xml: 'XML',
    rust: 'Rust', typescript: 'TypeScript', javascript: 'JavaScript'
  };
  function formatLangLabel(lang) {
    if (!lang) return 'Text';
    var key = String(lang).toLowerCase();
    if (LANG_LABELS[key]) return LANG_LABELS[key];
    var raw = key.replace(/[_-]/g, ' ');
    return raw.charAt(0).toUpperCase() + raw.slice(1);
  }
  // 高亮器使用的语言名与 Markdown 别名不完全一致，这里做一次归一
  var HLJS_ALIASES = {
    js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
    ts: 'typescript', tsx: 'typescript', py: 'python', rb: 'ruby', rs: 'rust',
    sh: 'bash', zsh: 'bash', fish: 'bash', md: 'markdown', yml: 'yaml',
    cpp: 'cpp', 'c++': 'cpp', cxx: 'cpp', hpp: 'cpp', hxx: 'cpp', cc: 'cpp',
    cs: 'csharp', 'c#': 'csharp', html: 'xml', kt: 'kotlin', toml: 'ini'
  };

  // 公式占位：先生成 HTML 存起来，解析后再回填，避免 LaTeX 的反斜杠/下划线被 Markdown 吃掉
  var MATH_TOKEN_RE = /@@math(\d+)@@/g;
  var CODE_SEGMENT_RE = /(```[\s\S]*?```|`[^`\n]*`)/g;
  function renderMathHTML(expr, display) {
    var body = String(expr == null ? '' : expr).trim();
    if (!body) return '';
    if (window.katex && window.katex.renderToString) {
      try {
        return window.katex.renderToString(body, {
          displayMode: !!display, throwOnError: false, strict: false, trust: false
        });
      } catch (e) { /* 渲染失败时退回原文 */ }
    }
    return '<code>' + esc(display ? '$$' + body + '$$' : '$' + body + '$') + '</code>';
  }
  function protectMath(src) {
    var store = [];
    function token(expr, display) {
      var i = store.length;
      store.push(renderMathHTML(expr, display));
      return '@@math' + i + '@@';
    }
    function scan(seg) {
      seg = seg.replace(/\\\[([\s\S]+?)\\\]/g, function (m, e) { return token(e, true); });
      seg = seg.replace(/\$\$([\s\S]+?)\$\$/g, function (m, e) { return token(e, true); });
      seg = seg.replace(/\\\(([\s\S]+?)\\\)/g, function (m, e) { return token(e, false); });
      seg = seg.replace(/\$([^\$\n]+?)\$/g, function (m, e, offset, whole) {
        var after = whole.charAt(offset + m.length);
        // 排除「$100-$200」这类金额区间：收尾 $ 后紧跟数字、内容两端带空白时不当作公式
        if (/\d/.test(after) || /^\s|\s$/.test(e)) return m;
        return token(e, false);
      });
      return seg;
    }
    var text = src.split(CODE_SEGMENT_RE).map(function (part, idx) {
      return idx % 2 ? part : scan(part);
    }).join('');
    return { text: text, store: store };
  }

  function decorateCodeBlocks(root) {
    Array.prototype.slice.call(root.querySelectorAll('pre')).forEach(function (pre) {
      var codeEl = pre.querySelector('code');
      if (!codeEl) return;
      var raw = codeEl.textContent.replace(/\n$/, '');
      var langMatch = /(?:^|\s)language-([^\s]+)/.exec(codeEl.className || '');
      var lang = langMatch ? langMatch[1].toLowerCase() : '';
      var hljsLang = HLJS_ALIASES[lang] || lang;
      var highlighted = '';
      if (hljsLang && window.hljs && window.hljs.getLanguage(hljsLang)) {
        try {
          highlighted = window.hljs.highlight(raw, { language: hljsLang, ignoreIllegals: true }).value;
        } catch (e) { /* 个别语法异常时退回纯文本 */ }
      }
      var codeHtml = '<code class="hljs' + (lang ? ' language-' + esc(lang) : '') + '">' +
        (highlighted || esc(raw)) + '</code>';
      var block = document.createElement('div');
      block.className = 'code-block';
      block.innerHTML =
        '<div class="code-toolbar">' +
          '<span class="code-lang">' + esc(formatLangLabel(lang)) + '</span>' +
          '<button type="button" class="code-copy" title="复制" aria-label="复制">' + ICON_COPY + '</button>' +
        '</div>' +
        '<div class="code-body"><pre>' + codeHtml + '</pre></div>';
      pre.parentNode.replaceChild(block, pre);
    });
  }

  function decorateTables(root) {
    Array.prototype.slice.call(root.querySelectorAll('table')).forEach(function (table) {
      var wrap = document.createElement('div');
      wrap.className = 'table-wrap';
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    });
  }

  // Markdown 里的 ![]()：本地图片/音视频展开为内嵌媒体，.genui 文件替换为占位卡
  function decorateMedia(holder) {
    if (window.PurrCatGenUI && window.PurrCatGenUI.media) window.PurrCatGenUI.media.decorate(holder);
  }

  function mdToHtml(src) {
    src = String(src == null ? '' : src).replace(/\r\n/g, '\n');
    var text = src;
    var store = [];
    var protectedSrc = null;
    if (window.marked && window.marked.parse) {
      // gfm=true：表格/删除线/GITHUB 自动链接；breaks=true：单个换行即换行
      protectedSrc = protectMath(src);
      text = protectedSrc.text;
      store = protectedSrc.store;
    }
    var html = '';
    if (window.marked && window.marked.parse) {
      try { html = window.marked.parse(text, { gfm: true, breaks: true }); }
      catch (e) { /* 语法异常时兜底 */ }
    }
    if (!html) html = mdFallback(src);
    if (store.length) {
      html = html.replace(/<p>\s*(@@math\d+@@)\s*<\/p>/g, '$1');
      html = html.replace(MATH_TOKEN_RE, function (m, i) { return store[Number(i)] || ''; });
    }
    var holder = document.createElement('div');
    holder.innerHTML = html;
    decorateCodeBlocks(holder);
    decorateTables(holder);
    decorateMedia(holder);
    return safeLinks(holder.innerHTML);
  }

  // 代码块复制：事件委托，重建历史时无需重新绑定
  document.addEventListener('click', function (ev) {
    var btn = ev.target && ev.target.closest ? ev.target.closest('.code-copy') : null;
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    var block = btn.closest('.code-block');
    var codeEl = block ? block.querySelector('code') : null;
    copyText(codeEl ? codeEl.textContent : '', btn);
  });

  // 本地文件路径识别（对齐完整模式 handleRawLinkClick 的判定范围）：
  // file:// 、/agent_vm/... 、Windows 绝对路径、./ 或 ../ 相对路径 + 已知扩展名
  var LOCAL_EXTS = ['png','jpg','jpeg','gif','webp','svg','bmp','ico','mp4','webm','mov','ogg','avi','mkv','pdf',
    'txt','text','md','markdown','csv','json','jsonc','log','html','htm',
    'py','js','ts','tsx','jsx','vue','java','c','cpp','h','hpp','cs','go','rs','rb','php','kt','swift','lua','pl','r','sh','bash','bat','ps1','sql','xml','yaml','yml','toml','ini','cfg','conf','css','scss','less','ipynb','env'];
  function safeDecode(s) { try { return decodeURIComponent(s); } catch (e) { return s; } }
  function localFilePath(href) {
    if (!href) return '';
    if (href.indexOf('file://') === 0) {
      var p = href.replace(/^file:\/\//, '');
      if (p.charAt(0) === '/' && p.charAt(2) === ':') p = p.substring(1);   // /C:/x → C:/x
      return safeDecode(p);
    }
    if (/^(?:\.{0,2}\/)agent_vm(?:\/|$)/.test(href)) return safeDecode(href);
    if (/^[A-Za-z]:[/\\]/.test(href)) return safeDecode(href);
    if (href.indexOf('./') === 0 || href.indexOf('../') === 0) {
      var ext = (href.split('.').pop() || '').toLowerCase();
      if (LOCAL_EXTS.indexOf(ext) >= 0) return safeDecode(href);
    }
    return '';
  }
  // 链接处理：绝对外链加 target=_blank（在新标签页打开，聊天作为返回点始终保留＝能返回）；
  // 本地文件链接去掉 href（防 iframe 跳走）后挂 data-fpath，由点击处理器唤起预览弹窗；
  // 其余相对/未知/危险链接去掉 href 退化为纯文本（仍可选中复制）
  function safeLinks(html) {
    return String(html).replace(/<a\b([^>]*)>/g, function (m, attrs) {
      var h = /href\s*=\s*(?:"|')([^"']*)(?:"|')/.exec(attrs);
      var hv = h ? h[1] : '';
      var noHref = attrs.replace(/\s+href\s*=\s*(?:"|')(?:[^"']*)(?:"|')/i, '');
      if (/^(https?:|mailto:|tel:|#)/i.test(hv)) {
        if (/\btarget\s*=/i.test(attrs)) return m;
        return '<a' + attrs + ' target="_blank" rel="noopener noreferrer">';
      }
      var fp = localFilePath(hv);
      if (fp) return '<a' + noHref + ' class="filelink" data-fpath="' + esc(fp) + '">';
      return '<a' + noHref + '>';
    });
  }

  // ---------- 渲染 ----------
  function bubble(clsName, inner) {
    var d = document.createElement('div');
    d.className = 'msg ' + clsName;
    d.innerHTML = inner;
    return d;
  }

  // ---------- 回合聚合：user 输入 + 其后的思考/工具/回复 ----------
  var AVATAR_SRC = '/minimal/assets/icons/purrcat-mark.png';
  var openMap = {};          // 折叠状态（key -> open），跨轮询重建保留
  var openViewKey = '';      // 会话/分支变化时重置 openMap
  var lastTurnPrefix = '';   // 最后回合的抽屉 key，任务完成时统一收起其内部细节
  var lastRenderedTurnUserTime = '';   // 最后回合的用户输入时间（用于记录完成时刻）
  var lastTurnEndedAt = 0;             // 最近一次观察到「思考 → 空闲」的本地时间
  var lastTurnEndedTime = '';          // 上述完成时刻对应的用户输入时间

  var FILE_KINDS = {
    py: ['PY', '#3572A5'], pyw: ['PY', '#3572A5'],
    ts: ['TS', '#3178C6'], tsx: ['TSX', '#3178C6'], mts: ['TS', '#3178C6'],
    js: ['JS', '#B8860B'], jsx: ['JSX', '#B8860B'], mjs: ['JS', '#B8860B'], cjs: ['JS', '#B8860B'],
    json: ['{}', '#6B7280'], jsonc: ['{}', '#6B7280'],
    md: ['MD', '#6B7280'], mdx: ['MD', '#6B7280'],
    html: ['<>', '#E44D26'], htm: ['<>', '#E44D26'],
    css: ['CSS', '#2965F1'], scss: ['SC', '#CF649A'], less: ['LESS', '#1D365D'],
    yml: ['YML', '#8A8F98'], yaml: ['YML', '#8A8F98'], toml: ['TOM', '#8A8F98'], ini: ['INI', '#8A8F98'],
    sh: ['SH', '#4EAA25'], bash: ['SH', '#4EAA25'], ps1: ['PS', '#2C6BD2'], bat: ['BAT', '#4EAA25'],
    go: ['GO', '#00ADD8'], rs: ['RS', '#DEA584'], java: ['JAVA', '#B07219'], kt: ['KT', '#A97BFF'],
    c: ['C', '#555B63'], h: ['H', '#555B63'], cpp: ['C++', '#F34B7D'], hpp: ['C++', '#F34B7D'], cs: ['C#', '#178600'],
    php: ['PHP', '#4F5D95'], rb: ['RB', '#CC342D'], swift: ['SW', '#F05138'], sql: ['SQL', '#336791'],
    png: ['IMG', '#7C5CBF'], jpg: ['IMG', '#7C5CBF'], jpeg: ['IMG', '#7C5CBF'], gif: ['IMG', '#7C5CBF'], webp: ['IMG', '#7C5CBF'], svg: ['SVG', '#D9820A'],
    txt: ['TXT', '#8A8F98'], log: ['LOG', '#8A8F98'], lock: ['LOCK', '#8A8F98'], env: ['ENV', '#8A8F98']
  };

  // 文件类型图标：沿用 OpenBitFun 的 lucide 线性图标风格，按类型换形状、按语言换颜色
  function fileGlyphSvg(inner) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
      + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/>'
      + '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>' + inner + '</svg>';
  }
  var FILE_GLYPHS = {
    code: fileGlyphSvg('<path d="m10 13-2 2 2 2"/><path d="m14 17 2-2-2-2"/>'),
    text: fileGlyphSvg('<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>'),
    json: fileGlyphSvg('<path d="M10 12a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1 1 1 0 0 1 1 1v1a1 1 0 0 0 1 1"/><path d="M14 18a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1 1 1 0 0 1-1-1v-1a1 1 0 0 0-1-1"/>'),
    term: fileGlyphSvg('<path d="m8 16 2-2-2-2"/><path d="M12 18h4"/>'),
    img: fileGlyphSvg('<circle cx="10" cy="13" r="2"/><path d="m20 18-1.5-1.5a2.4 2.4 0 0 0-3.4 0L9 22"/>'),
    db: fileGlyphSvg('<ellipse cx="12" cy="9" rx="4" ry="2"/><path d="M8 9v4c0 1.1 1.8 2 4 2s4-.9 4-2V9"/><path d="M8 13v4c0 1.1 1.8 2 4 2s4-.9 4-2v-4"/>'),
    file: fileGlyphSvg('')
  };
  var FILE_GLYPH_BY_LABEL = {
    '{}': 'json', YML: 'json', TOM: 'json', INI: 'json',
    MD: 'text', TXT: 'text', LOG: 'text', LOCK: 'text', ENV: 'text',
    SH: 'term', PS: 'term', BAT: 'term',
    IMG: 'img', SVG: 'img',
    SQL: 'db'
  };
  var FILE_CODE_LABELS = ['PY', 'TS', 'TSX', 'JS', 'JSX', 'HTML', 'CSS', 'SC', 'LESS', 'GO', 'RS', 'JAVA', 'KT', 'C', 'H', 'C++', 'C#', 'PHP', 'RB', 'SW'];

  function baseName(p) {
    var s = String(p || '').replace(/\\/g, '/');
    return s.split('/').filter(Boolean).pop() || s;
  }
  // 去掉结果摘要前面的状态 emoji，只留可读文案（图标由前端统一渲染）
  function plainSnip(s) {
    return String(s || '').replace(/^[^\u4e00-\u9fa5A-Za-z0-9]+/, '').trim();
  }
  function countLines(s) { return s ? String(s).split('\n').length : 0; }
  function firstLine(s) { return String(s || '').split('\n')[0].trim(); }
  function normName(n) { return String(n || '').replace(/[^a-z]/gi, '').toLowerCase(); }

  function fileBadge(path) {
    var base = baseName(path).toLowerCase();
    var kind = FILE_KINDS[base] || FILE_KINDS[base.indexOf('.') >= 0 ? base.split('.').pop() : ''] || ['F', '#8A8F98'];
    var g = FILE_GLYPH_BY_LABEL[kind[0]] || (FILE_CODE_LABELS.indexOf(kind[0]) >= 0 ? 'code' : 'file');
    return '<span class="fico" style="color:' + kind[1] + '" title="' + esc(kind[0]) + '">'
      + (FILE_GLYPHS[g] || FILE_GLYPHS.file) + '</span>';
  }
  // 文件名蓝链：复用消息里的文件预览委托（data-fpath → openPreview）。不带 href，避免 iframe 跳走
  function fileLink(path) {
    var p = String(path || '');
    return '<a class="filelink" data-fpath="' + esc(p) + '" title="' + esc(p) + '">'
      + esc(baseName(p) || '文件') + '</a>';
  }

  function toolNameOf(tc) {
    var fn = (tc && tc.function && typeof tc.function === 'object') ? tc.function : {};
    return fn.name || (tc && tc.name) || (tc && typeof tc.function === 'string' ? tc.function : '') || 'tool';
  }
  function parseToolArgs(tc) {
    var fn = (tc && tc.function && typeof tc.function === 'object') ? tc.function : {};
    var raw = fn.arguments != null ? fn.arguments : (tc && tc.arguments != null ? tc.arguments : '');
    if (raw && typeof raw === 'object') return raw;
    if (typeof raw === 'string' && raw.trim()) {
      try { var o = JSON.parse(raw); return (o && typeof o === 'object') ? o : {}; } catch (e) { return {}; }
    }
    return {};
  }
  // 工具结果里 content / metadata.snip / metadata.type 的拆分（与后端 text_response 一致）
  function resultInfo(row) {
    var text = '', snip = '', type = '';
    var c = row && row.content;
    var o = null;
    if (typeof c === 'string') {
      try { o = JSON.parse(c); } catch (e) { o = null; }
      if (!o || typeof o !== 'object') { text = c; o = null; }
    } else if (c && typeof c === 'object') { o = c; }
    else if (c != null) { text = String(c); }
    if (o) {
      text = typeof o.content === 'string' ? o.content : extractFrom(o);
      var md = o.metadata;
      if (md && typeof md === 'object') {
        snip = typeof md.snip === 'string' ? md.snip : '';
        type = typeof md.type === 'string' ? md.type : '';
      }
    }
    return { text: text || '', snip: snip, type: type };
  }

  // ---- 时间：用户事件 time 为 MM-DD HH:MM:SS，按当前年份推断 ----
  function userTimeOf(content) {
    var p = parseUser(content || '');
    return p.times.length ? p.times[p.times.length - 1] : '';
  }
  function parseStamp(s) {
    var m = /^(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{2}):(\d{2})$/.exec(String(s || '').trim());
    if (!m) return null;
    var now = new Date();
    var d = new Date(now.getFullYear(), +m[1] - 1, +m[2], +m[3], +m[4], +m[5]);
    if (d.getTime() - now.getTime() > 2 * 86400000) d.setFullYear(d.getFullYear() - 1);
    return d;
  }
  function fmtElapsed(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return s + 's';
    var m = Math.floor(s / 60), r = s % 60;
    if (m < 60) return m + 'm' + (r ? ' ' + r + 's' : '');
    var h = Math.floor(m / 60), mm = m % 60;
    return h + 'h' + (mm ? ' ' + mm + 'm' : '');
  }
  function nextUserTime(turns, i) {
    for (var j = i + 1; j < turns.length; j++) if (turns[j].userTime) return turns[j].userTime;
    return '';
  }

  // ---- 回合切分：真实用户输入开启新回合；workflow_hint 按原始位置收进时间线（参考内容） ----
  function buildTurns(rows) {
    var turns = [], cur = null, pendingHints = [];
    function pushRefs(turn, hints) {
      hints.forEach(function (h) { turn.items.push({ kind: 'ref', text: h }); });
    }
    rows.forEach(function (row, i) {
      if (!row) return;
      if (row.role === 'user') {
        var p = parseUser(row.content || '');
        var hasUser = p.msgs.length || p.att.length;
        if (hasUser) {
          cur = {
            userRow: row, userIdx: i, firstIdx: i,
            userTime: p.times.length ? p.times[p.times.length - 1] : '',
            items: []
          };
          if (pendingHints.length) { pushRefs(cur, pendingHints); pendingHints = []; }
          if (p.hints.length) pushRefs(cur, p.hints);
          turns.push(cur);
        } else if (p.hints.length) {
          // 只有提示的事件：挂在当前回合；还没有回合就暂存给下一个回合
          if (cur) pushRefs(cur, p.hints);
          else pendingHints = pendingHints.concat(p.hints);
        }
        return;
      }
      if (!cur) {
        cur = { userRow: null, userIdx: -1, firstIdx: i, userTime: '', items: [] };
        if (pendingHints.length) { pushRefs(cur, pendingHints); pendingHints = []; }
        turns.push(cur);
      }
      cur.items.push({ row: row, idx: i });
    });
    return turns;
  }

  // ---- 统计摘要：把一组步骤压成一行可读文字，并按工具构成选择图标 ----
  function traceCounts(steps) {
    var c = { created: 0, edited: 0, read: 0, listed: 0, searched: 0, globbed: 0, modified: 0, commands: 0, asked: 0, fetched: 0, memoAdd: 0, memoSearch: 0, memoOther: 0, plans: 0, planOps: 0, images: 0, subtasks: 0, taskOps: 0, other: 0, think: 0 };
    steps.forEach(function (st) {
      if (st.kind === 'ref' || st.kind === 'reply') return;
      if (st.kind === 'think') { c.think++; return; }
      if (st.kind !== 'call') { c.other++; return; }
      var n = normName(st.name);
      if (n === 'filesystem') {
        var act = String(st.args.action || '').toLowerCase();
        if (act === 'read') c.read++;
        else if (act === 'edit') c.edited++;
        else if (act === 'write') c.created++;
        else if (act === 'search') c.searched++;
        else if (act === 'glob') c.globbed++;
        else if (act === 'list') c.listed++;
        else if (act === 'move' || act === 'copy' || act === 'delete' || act === 'undo') c.modified++;
        else c.other++;
      } else if (n === 'bash') c.commands++;
      else if (n === 'request') c.asked++;
      else if (n === 'fetch' || n === 'search') c.fetched++;
      else if (n === 'memo') {
        var ma = String(st.args.action || '').toLowerCase();
        if (ma === 'add') c.memoAdd++;
        else if (ma === 'search') c.memoSearch++;
        else c.memoOther++;
      } else if (n === 'brainstorm') {
        var ba = String(st.args.action || '').toLowerCase();
        if (ba === 'create') c.plans++;
        else c.planOps++;
      } else if (n === 'task') {
        var ta = String(st.args.action || '').toLowerCase();
        if (ta === 'vision') c.images += (Array.isArray(st.args.attachment_paths) ? st.args.attachment_paths.length : 0) || 1;
        else if (ta === 'add') c.subtasks++;
        else c.taskOps++;
      } else c.other++;
    });
    return c;
  }
  function traceStats(steps) {
    var c = traceCounts(steps);
    var parts = [];
    if (c.created) parts.push('已创建 ' + c.created + ' 个文件');
    if (c.edited) parts.push('已编辑 ' + c.edited + ' 个文件');
    if (c.read) parts.push('已读取 ' + c.read + ' 个文件');
    if (c.listed) parts.push('浏览 ' + c.listed + ' 个目录');
    if (c.searched) parts.push('搜索 ' + c.searched + ' 次文件');
    if (c.globbed) parts.push('匹配 ' + c.globbed + ' 次文件');
    if (c.modified) parts.push('修改 ' + c.modified + ' 个文件');
    if (c.fetched) parts.push('检索 ' + c.fetched + ' 次资料');
    if (c.commands) parts.push('执行 ' + c.commands + ' 条命令');
    if (c.memoAdd) parts.push('归档了 ' + c.memoAdd + ' 个记忆');
    if (c.memoSearch) parts.push('检索了 ' + c.memoSearch + ' 次记忆');
    if (c.memoOther) parts.push('操作了 ' + c.memoOther + ' 次记忆');
    if (c.plans) parts.push('更新了 ' + c.plans + ' 次计划');
    if (c.planOps) parts.push('取消计划 ' + c.planOps + ' 次');
    if (c.images) parts.push('查看了 ' + c.images + ' 张图片');
    if (c.subtasks) parts.push('派发 ' + c.subtasks + ' 个子任务');
    if (c.taskOps) parts.push('任务操作 ' + c.taskOps + ' 次');
    if (c.asked) parts.push(c.asked > 1 ? '对用户提问 ' + c.asked + ' 次' : '对用户提问');
    if (c.other) parts.push('调用 ' + c.other + ' 次工具');
    if (!parts.length) parts.push('思考过程');
    return parts.join('，');
  }
  // 摘要图标跟随实际执行内容：命令 > 文件改动 > 读取 > 搜索 > 记忆 > 纯思考
  function traceIcon(steps) {
    var c = traceCounts(steps);
    if (c.commands) return ICON_TERM;
    if (c.created || c.edited || c.modified) return ICON_PENCIL;
    if (c.read || c.listed) return ICON_EYE;
    if (c.searched || c.globbed || c.fetched) return ICON_SEARCH;
    if (c.images) return ICON_IMAGE;
    if (c.plans || c.planOps || c.subtasks || c.taskOps) return ICON_BRANCH;
    if (c.memoAdd || c.memoSearch || c.memoOther) return ICON_BOOK;
    if (c.think) return ICON_BRAIN;
    return ICON_TOOL;
  }

  // 编辑/创建的增删行数：优先用结果里的真实 diff 统计，缺失时按参数估算
  function diffOf(st) {
    var info = st.result ? resultInfo(st.result) : null;
    if (info && info.type === 'error') return null;
    var m = info ? /新增了\s*(\d+)\s*行[\s\S]*?删除了\s*(\d+)\s*行/.exec(info.text) : null;
    if (m) return [Number(m[1]), Number(m[2])];
    var a = st.args || {};
    var act = String(a.action || '').toLowerCase();
    if (act === 'write') return [countLines(a.content), 0];
    if (act === 'edit') return [countLines(a.new_string), countLines(a.old_string)];
    return null;
  }

  // ---- 步骤渲染 ----
  function renderThinkStep(st, key, label) {
    var wrap = document.createElement('div');
    wrap.className = 'subfold' + (openMap[key] ? ' open' : '');
    var head = document.createElement('button');
    head.type = 'button'; head.className = 'subfold-head';
    head.innerHTML = '<span class="s-ico">' + ICON_BRAIN + '</span><span class="s-main">'
      + esc(label || '思考') + '</span><span class="s-chev">›</span>';
    var body = document.createElement('div');
    body.className = 'subfold-body reason-body';
    body.textContent = st.text || '';
    head.addEventListener('click', function () {
      var open = !wrap.classList.contains('open');
      wrap.classList.toggle('open', open);
      openMap[key] = open;
    });
    wrap.appendChild(head); wrap.appendChild(body);
    return wrap;
  }

  function renderReadStep(st) {
    var path = st.args.path || '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_EYE + '</span><span class="s-main">已读取 '
      + fileLink(path) + '</span>';
    return el;
  }

  function renderListStep(st) {
    var path = st.args.path || '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_EYE + '</span><span class="s-main">浏览 '
      + fileLink(path) + '</span>';
    return el;
  }

  function renderFileChange(st, isCreate, key) {
    var path = st.args.path || '';
    var wrap = document.createElement('div');
    wrap.className = 'cmd-step' + (openMap[key] ? ' open' : '');
    wrap.setAttribute('data-fk', key);
    var head = document.createElement('button');
    head.type = 'button';
    head.className = 'step-head';
    head.innerHTML = '<span class="s-ico">' + (isCreate ? ICON_FILE_PLUS : ICON_PENCIL)
      + '</span><span class="s-main">' + (isCreate ? '已创建 1 个文件' : '已编辑 1 个文件')
      + '</span><span class="s-chev">›</span>';
    var d = diffOf(st);
    var panel = document.createElement('div');
    panel.className = 'file-panel';
    panel.innerHTML = '<div class="step-files"><div class="step-file">' + fileBadge(path) + fileLink(path)
      + (d ? '<span class="add">+' + d[0] + '</span><span class="del">-' + d[1] + '</span>' : '') + '</div></div>';
    head.addEventListener('click', function () {
      var open = !wrap.classList.contains('open');
      wrap.classList.toggle('open', open);
      openMap[key] = open;
    });
    wrap.appendChild(head); wrap.appendChild(panel);
    return wrap;
  }

  function renderFileOpStep(st) {
    var labels = { move: '移动', copy: '复制', delete: '删除', undo: '回滚' };
    var act = String(st.args.action || '').toLowerCase();
    var path = st.args.path || st.args.destination || '';
    var info = st.result ? resultInfo(st.result) : null;
    var label = (info && info.type === 'error') ? (labels[act] || '修改') + '失败' : '已' + (labels[act] || '修改') + ' 1 个文件';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_PENCIL + '</span><span class="s-main">' + esc(label) + '</span>';
    if (path) {
      var files = document.createElement('div');
      files.className = 'step-files';
      files.innerHTML = '<div class="step-file">' + fileBadge(path) + fileLink(path) + '</div>';
      var frag = document.createDocumentFragment();
      frag.appendChild(el); frag.appendChild(files);
      return frag;
    }
    return el;
  }

  function renderSearchStep(st) {
    var info = st.result ? resultInfo(st.result) : null;
    var label = !info ? '搜索文件' : (info.type === 'error' ? '搜索失败' : (plainSnip(info.snip) || '搜索文件'));
    var pat = st.args.pattern || '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_SEARCH + '</span><span class="s-main">' + esc(label)
      + (pat ? ' <span class="s-mono s-dim">' + esc(pat) + '</span>' : '') + '</span>';
    return el;
  }

  function renderGlobStep(st) {
    var info = st.result ? resultInfo(st.result) : null;
    var label = !info ? '匹配文件' : (info.type === 'error' ? '匹配失败' : (plainSnip(info.snip) || '匹配文件'));
    var pat = st.args.pattern || '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_SEARCH + '</span><span class="s-main">' + esc(label)
      + (pat ? ' <span class="s-mono s-dim">' + esc(pat) + '</span>' : '') + '</span>';
    return el;
  }

  function renderBashStep(st, key) {
    var done = !!st.result;
    var info = done ? resultInfo(st.result) : null;
    var failed = done && info && info.type === 'error';
    var snip = String(st.args.snip || '').trim();
    if (!snip) {
      // 旧历史没有 snip：用命令首行截断兜底，完整命令仍在伪终端里展示
      var rawCmd = firstLine(st.args.command);
      snip = rawCmd.length > 48 ? rawCmd.slice(0, 48) + '…' : rawCmd;
    }
    if (!snip) snip = '命令';

    var wrap = document.createElement('div');
    var open = !!openMap[key];
    wrap.className = 'cmd-step' + (open ? ' open' : '');
    wrap.setAttribute('data-fk', key);

    // 这行文字本身就是抽屉：点击展开/收起伪终端
    var head = document.createElement('button');
    head.type = 'button';
    head.className = 'step-head';
    head.innerHTML = '<span class="s-ico">' + ICON_TERM + '</span><span class="s-main' + (failed ? ' err' : '') + '">'
      + (done ? '命令已执行 ' : '命令运行中 ') + esc(snip) + '</span><span class="s-chev">›</span>';

    var term = document.createElement('div');
    term.className = 'term';
    var pre = document.createElement('pre');
    pre.className = 'term-pre';
    var prompt = document.createElement('span'); prompt.className = 'prompt'; prompt.textContent = '$ ';
    var cmd = document.createElement('span'); cmd.className = 'cmd'; cmd.textContent = String(st.args.command || '');
    pre.appendChild(prompt); pre.appendChild(cmd);
    pre.appendChild(document.createTextNode('\n' + (done ? (info.text || '[无输出]') : '执行中…')));
    term.appendChild(pre);

    head.addEventListener('click', function () {
      var next = !wrap.classList.contains('open');
      wrap.classList.toggle('open', next);
      openMap[key] = next;
    });
    wrap.appendChild(head); wrap.appendChild(term);
    return wrap;
  }

  function renderAskStep(st) {
    var info = st.result ? resultInfo(st.result) : null;
    var snip = info ? plainSnip(info.snip) : '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_ASK + '</span><span class="s-main">对用户提问'
      + (snip ? ' <span class="s-dim">' + esc(snip) + '</span>' : '') + '</span>';
    return el;
  }

  function renderFetchStep(st) {
    var url = st.args.url || st.args.path || st.args.query || '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_SEARCH + '</span><span class="s-main">检索资料'
      + (url ? ' <span class="s-mono s-dim">' + esc(String(url).slice(0, 120)) + '</span>' : '') + '</span>';
    return el;
  }

  function renderGenericStep(st) {
    var info = st.result ? resultInfo(st.result) : null;
    var label = st.name || '工具';
    var snip = info ? plainSnip(info.snip) : '';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_GENERIC + '</span><span class="s-main">' + esc(label)
      + (snip ? ' <span class="s-dim">' + esc(snip) + '</span>' : '') + '</span>';
    return el;
  }

  function renderResultStep(st) {
    var info = resultInfo(st.row);
    var label = plainSnip(info.snip) || '工具结果';
    var el = document.createElement('div');
    el.className = 'step';
    el.innerHTML = '<span class="s-ico">' + ICON_GENERIC + '</span><span class="s-main">' + esc(label) + '</span>';
    return el;
  }

  function memoLabel(action) {
    switch (action) {
      case 'add': return '记忆归档';
      case 'search': return '记忆检索成功';
      case 'reinforce': return '记忆强化成功';
      case 'replace': return '记忆更新成功';
      case 'delete': return '记忆删除成功';
      default: return '记忆操作成功';
    }
  }
  // 点击后才展示具体归档了什么，不在标题里暴露文件名/ID
  function memoContent(st) {
    var a = st.args || {};
    var action = String(a.action || '').toLowerCase();
    if (action === 'add' && a.memo_data && typeof a.memo_data === 'object') {
      var d = a.memo_data, parts = [];
      if (d.short_term) parts.push('【短期记忆】\n' + d.short_term);
      if (Array.isArray(d.work_exp) && d.work_exp.length) parts.push('【工作经验】\n' + d.work_exp.map(function (x) { return '- ' + x; }).join('\n'));
      if (Array.isArray(d.user_profile) && d.user_profile.length) parts.push('【用户画像】\n' + d.user_profile.map(function (x) { return '- ' + x; }).join('\n'));
      if (Array.isArray(d.events) && d.events.length) {
        parts.push('【事件】\n' + d.events.map(function (e) {
          return '- ' + ((e && e.time ? e.time + ' ' : '') + (e && e.event ? e.event : ''));
        }).join('\n'));
      }
      if (Array.isArray(d.cognition) && d.cognition.length) parts.push('【认知】\n' + d.cognition.map(function (x) { return '- ' + x; }).join('\n'));
      if (parts.length) return parts.join('\n\n');
    }
    if (action === 'replace' && a.content) return String(a.content);
    var info = st.result ? resultInfo(st.result) : null;
    return info ? info.text : '';
  }
  function renderMemoStep(st, key) {
    var action = String(st.args.action || 'add').toLowerCase();
    var wrap = document.createElement('div');
    wrap.className = 'cmd-step' + (openMap[key] ? ' open' : '');
    wrap.setAttribute('data-fk', key);
    var head = document.createElement('button');
    head.type = 'button';
    head.className = 'step-head';
    head.innerHTML = '<span class="s-ico">' + ICON_BOOK + '</span><span class="s-main">'
      + esc(memoLabel(action)) + '</span><span class="s-chev">›</span>';
    var panel = document.createElement('div');
    panel.className = 'memo-panel';
    var pre = document.createElement('pre');
    pre.className = 'memo-pre';
    pre.textContent = memoContent(st) || '（无详细内容）';
    panel.appendChild(pre);
    head.addEventListener('click', function () {
      var open = !wrap.classList.contains('open');
      wrap.classList.toggle('open', open);
      openMap[key] = open;
    });
    wrap.appendChild(head); wrap.appendChild(panel);
    return wrap;
  }

  function taskLabel(action) {
    switch (action) {
      case 'vision': return '查看图片';
      case 'add': return '派发子任务';
      case 'list_graphs': return '查看可用工作流';
      case 'list_tasks': return '查看任务列表';
      case 'kill': return '终止任务';
      case 'submit_request': return '注入人工指令';
      case 'get_details': return '查看任务详情';
      default: return '任务操作';
    }
  }
  function detailStep(st, key, icon, label, detail, text) {
    var wrap = document.createElement('div');
    wrap.className = 'cmd-step' + (openMap[key] ? ' open' : '');
    wrap.setAttribute('data-fk', key);
    var head = document.createElement('button');
    head.type = 'button'; head.className = 'step-head';
    head.innerHTML = '<span class="s-ico">' + icon + '</span><span class="s-main">' + esc(label)
      + (detail ? ' <span class="s-dim">' + esc(detail) + '</span>' : '')
      + '</span><span class="s-chev">›</span>';
    var panel = document.createElement('div');
    panel.className = 'detail-panel';
    var pre = document.createElement('pre');
    pre.className = 'detail-pre';
    pre.textContent = text || '（无详细内容）';
    panel.appendChild(pre);
    head.addEventListener('click', function () {
      var open = !wrap.classList.contains('open');
      wrap.classList.toggle('open', open);
      openMap[key] = open;
    });
    wrap.appendChild(head); wrap.appendChild(panel);
    return wrap;
  }
  function renderTaskStep(st, key) {
    var action = String(st.args.action || '').toLowerCase();
    var label = taskLabel(action);
    var detail = '';
    var parts = [];
    var info = st.result ? resultInfo(st.result) : null;
    if (action === 'vision') {
      var atts = Array.isArray(st.args.attachment_paths) ? st.args.attachment_paths : [];
      label = '查看了 ' + atts.length + ' 张图片';
      parts = atts.map(function (p) { return baseName(p); });
    } else if (action === 'add') {
      detail = String(st.args.name || '');
      if (detail) parts.push('任务：' + detail);
      if (st.args.graph_name) parts.push('工作流：' + st.args.graph_name);
      if (st.args.prompt) parts.push('指令：\n' + st.args.prompt);
      if (st.args.inputs && typeof st.args.inputs === 'object') parts.push('参数：\n' + JSON.stringify(st.args.inputs, null, 2));
      if (info && info.text) parts.push('结果：\n' + info.text);
    } else {
      detail = st.args.task_id || st.args.target_branch_id || '';
      if (info && info.text) parts.push(info.text);
      else parts.push(JSON.stringify(st.args, null, 2));
    }
    return detailStep(st, key, action === 'vision' ? ICON_IMAGE : ICON_BRANCH, label, detail,
      parts.join(action === 'vision' ? '\n' : '\n\n'));
  }
  function renderPlanStep(st, key) {
    var action = String(st.args.action || '').toLowerCase();
    var label = action === 'cancel' ? '取消了计划分支' : '更新了计划';
    var info = st.result ? resultInfo(st.result) : null;
    var parts = [];
    if (action === 'create') {
      var plan = Array.isArray(st.args.main_plan) ? st.args.main_plan : [];
      if (plan.length) {
        parts.push('主计划：\n' + plan.map(function (s, i) { return (i + 1) + '. ' + s; }).join('\n'));
      }
      var subs = Array.isArray(st.args.sub_branches) ? st.args.sub_branches : [];
      if (subs.length) {
        parts.push('子分支：\n' + subs.map(function (b) {
          var line = '- ' + (b.branch_id || '?') + '：' + (b.action || '');
          if (Array.isArray(b.deliverable) && b.deliverable.length) line += '\n  交付物：' + b.deliverable.join('、');
          if (Array.isArray(b.depends_on) && b.depends_on.length) line += '\n  依赖：' + b.depends_on.join('、');
          return line;
        }).join('\n'));
      }
    } else if (st.args.target_branch_id) {
      parts.push('终止分支：' + st.args.target_branch_id);
    }
    if (info && info.text) parts.push('结果：\n' + info.text);
    var detail = action === 'create'
      ? (Array.isArray(st.args.main_plan) ? st.args.main_plan.length + ' 步计划' : '')
      : (st.args.target_branch_id || '');
    return detailStep(st, key, ICON_BRANCH, label, detail, parts.join('\n\n'));
  }

  function renderStep(st, key) {
    if (st.kind === 'think') return renderThinkStep(st, key);
    if (st.kind === 'result') return renderResultStep(st);
    var n = normName(st.name);
    var act = String(st.args.action || '').toLowerCase();
    if (n === 'filesystem') {
      if (act === 'edit') return renderFileChange(st, false, key);
      if (act === 'write') return renderFileChange(st, true, key);
      if (act === 'search') return renderSearchStep(st);
      if (act === 'glob') return renderGlobStep(st);
      if (act === 'read') return renderReadStep(st);
      if (act === 'list') return renderListStep(st);
      if (act === 'move' || act === 'copy' || act === 'delete' || act === 'undo') return renderFileOpStep(st);
    }
    if (n === 'bash') return renderBashStep(st, key);
    if (n === 'memo') return renderMemoStep(st, key);
    if (n === 'task') return renderTaskStep(st, key);
    if (n === 'brainstorm') return renderPlanStep(st, key);
    if (n === 'request') return renderAskStep(st);
    if (n === 'fetch' || n === 'search') return renderFetchStep(st);
    return renderGenericStep(st);
  }

  // ---- 回合耗时：相邻两次用户输入的墙钟差 ----
  function elapsedLabel(turn, opts) {
    if (turn.userTime && opts.nextTime) {
      var a = parseStamp(turn.userTime), b = parseStamp(opts.nextTime);
      if (a && b) return '任务耗时 ' + fmtElapsed(b - a);
    }
    // 最新回合没有「下一条用户输入」可参照，用插件观测到的完成时刻计算
    if (opts.last && turn.userTime && lastTurnEndedAt && lastTurnEndedTime === turn.userTime) {
      var start = parseStamp(turn.userTime);
      if (start) return '任务耗时 ' + fmtElapsed(lastTurnEndedAt - start);
    }
    return '';
  }

  // 一级：固定的回合状态行，不参与展开收起
  function buildTurnHeader(turn, opts) {
    var head = document.createElement('div');
    head.className = 'turn-head';
    var running = !!(opts.last && opts.thinking);
    var elapsed = elapsedLabel(turn, opts);
    head.innerHTML = '<img class="turn-avatar" src="' + AVATAR_SRC + '" alt="">'
      + (running ? '<span class="spin">' + ICON_SPIN + '</span>' : '')
      + '<span class="turn-time">' + (running ? '正在执行中' : '任务已完成') + '</span>'
      + (elapsed ? '<span class="sum-time">' + esc(elapsed) + '</span>' : '');
    return head;
  }

  // 二级参考分组：展开后每个参考项仍是收起的，点开才看到具体内容
  function renderRefItem(text, key, label) {
    var item = document.createElement('div');
    item.className = 'subfold ref-item' + (openMap[key] ? ' open' : '');
    var head = document.createElement('button');
    head.type = 'button'; head.className = 'subfold-head';
    head.innerHTML = '<span class="s-ico">' + ICON_BOOK + '</span><span class="s-main">'
      + esc(label) + '</span><span class="s-chev">›</span>';
    var body = document.createElement('div');
    body.className = 'subfold-body';
    var hb = document.createElement('div');
    hb.className = 'hint-body';
    hb.textContent = text || '';
    body.appendChild(hb);
    head.addEventListener('click', function () {
      var open = !item.classList.contains('open');
      item.classList.toggle('open', open);
      openMap[key] = open;
    });
    item.appendChild(head); item.appendChild(body);
    return item;
  }

  function renderRefGroup(refs, key) {
    var fold = document.createElement('div');
    fold.className = 'subfold' + (openMap[key] ? ' open' : '');
    var head = document.createElement('button');
    head.type = 'button'; head.className = 'subfold-head';
    head.innerHTML = '<span class="s-ico">' + ICON_BOOK + '</span><span class="s-main">参考了 '
      + refs.length + ' 个内容</span><span class="s-chev">›</span>';
    var body = document.createElement('div');
    body.className = 'subfold-body';
    refs.forEach(function (r, i) {
      body.appendChild(renderRefItem(r.text, key + ':r' + i, refs.length > 1 ? '参考内容 ' + (i + 1) : '参考内容'));
    });
    head.addEventListener('click', function () {
      var open = !fold.classList.contains('open');
      fold.classList.toggle('open', open);
      openMap[key] = open;
    });
    fold.appendChild(head); fold.appendChild(body);
    return fold;
  }

  // 二级：思考与工具合在一个统计信息里；展开后每一步仍可单独收起
  function renderWorkGroup(seg, key) {
    var items = seg.seq.filter(function (e) { return e.kind !== 'ref'; });
    var onlyThink = items.length > 0 && items.every(function (e) { return e.kind === 'think'; });
    var fold = document.createElement('div');
    fold.className = 'subfold' + (openMap[key] ? ' open' : '');
    var head = document.createElement('button');
    head.type = 'button'; head.className = 'subfold-head';
    head.innerHTML = '<span class="s-ico">' + (onlyThink ? ICON_BRAIN : traceIcon(items)) + '</span>'
      + '<span class="s-main">' + esc(onlyThink ? '思考' : traceStats(items)) + '</span><span class="s-chev">›</span>';
    var body = document.createElement('div');
    body.className = 'subfold-body';
    var thinkNo = 0;
    items.forEach(function (ev, i) {
      if (ev.kind === 'think') {
        thinkNo++;
        body.appendChild(renderThinkStep({ text: ev.text }, key + ':t' + i, thinkNo > 1 ? '思考 ' + thinkNo : '思考'));
      } else if (ev.kind === 'result') {
        body.appendChild(renderResultStep({ row: ev.row }));
      } else {
        body.appendChild(renderStep(ev, key + ':s' + i));
      }
    });
    head.addEventListener('click', function () {
      var open = !fold.classList.contains('open');
      fold.classList.toggle('open', open);
      openMap[key] = open;
    });
    fold.appendChild(head); fold.appendChild(body);
    return fold;
  }

  // ---- 汇总一个回合的事件流；正文（回复）保留真实位置，用于平铺 ----
  function buildActivity(turn, resultById) {
    var events = [];
    turn.items.forEach(function (it) {
      if (it.kind === 'ref') {
        if (show.hint) events.push({ kind: 'ref', text: it.text });
        return;
      }
      var row = it.row;
      if (row.role === 'assistant') {
        if (show.reasoning && row.reasoning_content) events.push({ kind: 'think', text: row.reasoning_content });
        if (row.content) events.push({ kind: 'reply', text: row.content, row: row });
        if (show.tool && row.tool_calls) {
          row.tool_calls.forEach(function (tc) {
            events.push({
              kind: 'call', name: toolNameOf(tc), args: parseToolArgs(tc),
              result: (tc && tc.id && resultById[tc.id]) || null
            });
          });
        }
      } else if (row.role === 'tool') {
        if (!show.tool) return;
        // MCP App / GenUI 卡片始终以独立块呈现，不塞进收起的工具链里
        if (row.mcp_app || (row.mcp_data && row.mcp_data.structuredContent !== undefined)) {
          events.push({ kind: 'special', row: row });
          return;
        }
        if (row.tool_call_id && resultById[row.tool_call_id] === row) return;   // 已挂到对应调用步骤
        events.push({ kind: 'result', row: row });
      }
    });
    return events;
  }

  function renderAssistantText(it) {
    if (it.empty) return bubble('assistant', '（无内容）');
    var holder = document.createElement('div');
    holder.style.cssText = 'width:100%;display:flex;flex-direction:column;gap:8px;';
    splitGenUI(it.row.content).forEach(function (seg) {
      if (seg.genui) { holder.appendChild(genuiBlock(seg.text)); return; }
      var mb = document.createElement('div');
      mb.className = 'md';
      mb.innerHTML = mdToHtml(seg.text);
      holder.appendChild(attachCopy(mb, seg.text));
      hydrateGenUI(mb);
    });
    return holder;
  }

  function renderSpecialRow(row) {
    var holder = document.createElement('div');
    holder.style.cssText = 'width:100%;';
    if (row.mcp_app && row.mcp_app.id) holder.appendChild(buildMcpApp(row.mcp_app));
    else if (row.mcp_data && row.mcp_data.structuredContent !== undefined) {
      var dsl = genuiSource(row.mcp_data.structuredContent);
      holder.appendChild(dsl ? genuiBlock(dsl) : buildMcpData(row.mcp_data));
    }
    return holder;
  }

  function renderUserRow(row) {
    var parsed = parseUser(row.content || '');
    var wrap = document.createElement('div');
    wrap.className = 'turn-user';
    var count = 0;
    if (parsed.att.length) {
      var attWrap = document.createElement('div');
      attWrap.className = 'attachments';
      parsed.att.forEach(function (a) {
        var c = document.createElement('span');
        c.className = 'att';
        c.textContent = a;
        c.title = a;
        attWrap.appendChild(c);
      });
      wrap.appendChild(attWrap); count++;
    }
    parsed.msgs.forEach(function (txt) { if (txt) { wrap.appendChild(attachCopy(bubble('user', esc(txt)), txt)); count++; } });
    return count ? wrap : null;
  }

  // 乐观插入的本地用户消息：与正式回合保持同一外层结构
  function renderLocalUser(text) {
    var turn = document.createElement('div');
    turn.className = 'turn';
    var u = document.createElement('div');
    u.className = 'turn-user';
    u.appendChild(attachCopy(bubble('user', esc(text)), text));
    turn.appendChild(u);
    return turn;
  }

  function renderTurn(turn, opts) {
    var wrap = document.createElement('div');
    wrap.className = 'turn';
    var count = 0;
    if (turn.userRow) {
      var userNode = renderUserRow(turn.userRow);
      if (userNode) { wrap.appendChild(userNode); count++; }
    }
    var events = buildActivity(turn, opts.resultById);

    // 一级状态行固定展示；正文与二级分组按真实历史顺序平铺
    if (events.length) {
      wrap.appendChild(buildTurnHeader(turn, opts)); count++;
      var group = null, groupIndex = 0;
      var flushGroup = function () {
        if (!group) return;
        var key = 't' + turn.firstIdx + ':g' + groupIndex;
        var node = group.kind === 'ref'
          ? renderRefGroup(group.items, key)
          : renderWorkGroup({ seq: group.items }, key);
        if (node) { wrap.appendChild(node); count++; }
        groupIndex++;
        group = null;
      };
      events.forEach(function (ev) {
        if (ev.kind === 'reply') {
          flushGroup();
          var textNode = renderAssistantText({ type: 'text', row: ev.row });
          if (textNode) { wrap.appendChild(textNode); count++; }
          return;
        }
        if (ev.kind === 'special') {
          flushGroup();
          wrap.appendChild(renderSpecialRow(ev.row)); count++;
          return;
        }
        // 参考内容按注入位置成组；只有连续注入的参考才合并，跨过工具/思考就另起一组
        var kind = ev.kind === 'ref' ? 'ref' : 'work';
        if (!group || group.kind !== kind) {
          flushGroup();
          group = { kind: kind, items: [] };
        }
        group.items.push(ev);
      });
      flushGroup();
    }
    if (opts.last) {
      lastTurnPrefix = 't' + turn.firstIdx;
      lastRenderedTurnUserTime = turn.userTime || '';
    }
    return count ? wrap : null;
  }

  // 任务完成（思考态 → 空闲）：收起最后回合已展开的细节
  function collapseLastTurn() {
    if (!lastTurnPrefix) return;
    Object.keys(openMap).forEach(function (k) {
      if (k === lastTurnPrefix || k.indexOf(lastTurnPrefix + ':') === 0) delete openMap[k];
    });
  }

  // ---------- 重建保护 ----------
  // 轮询每 1.5s 会把整段历史重建一次（listEl.innerHTML=''），而重建会摧毁正在进行的文本选择：
  // 选区锚点节点被换掉后，浏览器会按鼠标当前位置重新解析选区 → 选中范围剧烈跳动、多选到没选中的字。
  // 因此：拖选中/已有选区时把重建推迟到选择结束；输入没变化时干脆不重建。
  var pendingRows = null;    // 被推迟的一次重建（选择结束后补做）
  var dragging = false;      // 是否正在列表内按住鼠标拖动选择
  var lastSig = '';          // 上次渲染的输入签名（内容+展示开关+分支+思考态），未变化则跳过重建
  function hasListSelection() {
    var sel = window.getSelection ? window.getSelection() : null;
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return false;
    var n = sel.anchorNode;
    while (n && n !== listEl) n = n.parentNode;
    return n === listEl;
  }
  function rebuildBlocked() { return dragging || hasListSelection(); }
  function flushPendingRender() {
    if (!pendingRows || rebuildBlocked()) return;
    var rows = pendingRows; pendingRows = null;
    renderMessages(rows, true);
  }
  document.addEventListener('selectionchange', flushPendingRender);
  document.addEventListener('mouseup', function () { dragging = false; flushPendingRender(); });
  // 拖动到 iframe 外松开时收不到 mouseup，靠 mouseleave 兜底；此时若仍有选区，选择保护照样挡住重建
  document.addEventListener('mouseleave', function () { dragging = false; });
  listEl.addEventListener('mousedown', function () { dragging = true; });

  function renderMessages(rows, force) {
    rows = Array.isArray(rows) ? rows : [];
    // 同样的输入重建出的 DOM 完全一样，跳过可避免无意义的重建（进而保住选区、滚动位置、hover 态）
    var sig = currentBranchId + '|' + JSON.stringify(show) + '|'
      + (thinking ? '1:' + live.phase + ':' + live.text.length : '0') + '|' + JSON.stringify(rows);
    if (!force && sig === lastSig) { pendingRows = null; return; }
    if (!force && rebuildBlocked()) { pendingRows = rows; return; }   // 等选择结束再重建
    lastSig = sig; pendingRows = null;
    // 轮询会把整段历史重建一次；若用户已经往上翻看，重建后不能强行拉回底部，
    // 只在「重建前本来就贴着底部」（含首次进入）时才跟随到底。
    // 注意 listEl.innerHTML='' 会把 scrollTop 归零，故旧位置必须先存下来。
    var prevTop = listEl.scrollTop;
    var stick = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 40;
    // 切换会话/分支后行号不再对应，折叠状态整体重置
    var viewKey = (activeSessionId || '') + '|' + currentBranchId;
    if (viewKey !== openViewKey) {
      openMap = {}; openViewKey = viewKey; lastTurnPrefix = '';
      lastTurnEndedAt = 0; lastTurnEndedTime = ''; lastRenderedTurnUserTime = '';
    }
    destroyGenUI();
    listEl.innerHTML = '';
    lastRows = rows || [];
    var hasRows = !!(rows && rows.length);
    // 空会话且 Agent 空闲 → 空态；思考中则继续往下渲染流式思考块（首条消息尚未落地）
    if (!hasRows && !thinking) {
      listEl.innerHTML = '<div class="empty">暂无消息</div>';
      return;
    }
    if (hasRows) {
      lastTurnPrefix = '';
      // tool_call_id → 工具结果行，便于把结果挂到对应调用步骤上聚合展示
      var resultById = {};
      rows.forEach(function (r) {
        if (r && r.role === 'tool' && r.tool_call_id) resultById[r.tool_call_id] = r;
      });
      var turns = buildTurns(rows);
      turns.forEach(function (turn, ti) {
        var node = renderTurn(turn, {
          last: ti === turns.length - 1,
          thinking: !!thinking,
          nextTime: nextUserTime(turns, ti),
          resultById: resultById
        });
        if (node) listEl.appendChild(node);
      });
      // 消息区动作行（记忆压缩 / 会话分支 / trace2skill）：仅在有消息且 Agent 空闲时出现
      if (!thinking) listEl.appendChild(buildActions());
    }
    // 流式思考块只属于主干主 Agent 循环（/status 只回报主干），子代理分支视图不渲染，避免串台
    if (thinking && currentBranchId === 'main') appendLive(stick);
    listEl.scrollTop = stick ? listEl.scrollHeight : prevTop;
  }

  // 合并渲染：服务端历史 + 尚未被服务端确认的本地乐观消息（发送后即时显示，fetch 慢时不同步丢失）
  function renderRows(rows) {
    var server = Array.isArray(rows) ? rows : [];
    var confirmed = {};
    server.forEach(function (r) {
      if (!r || r.role !== 'user') return;
      // 服务端存的用户消息常是 events JSON；与原 UI 一样先解析出正文再判重，
      // 否则本地乐观的"你好"与历史里的"你好"匹配不上，会重复渲染成两条
      var parsed = parseUser(r.content);
      if (parsed.msgs && parsed.msgs.length) {
        parsed.msgs.forEach(function (t) { confirmed[String(t)] = true; });
      } else {
        confirmed[String(r.content)] = true;
      }
    });
    // 已被服务端确认的从本地缓冲移除，避免后续 fetch 再次合并造成重复
    localBuffer = localBuffer.filter(function (u) { return !confirmed[u.content]; });
    renderMessages(server.concat(localBuffer.map(function (u) { return { role: 'user', content: u.content }; })));
  }

  // ---------- 消息区动作行：记忆压缩 / 会话分支 / trace2skill ----------
  // 图标与宿主白条同款线性风格（插件自带，不依赖宿主图标集）
  var ICON_BRAIN = SVG_HEAD + '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.4 1 2.3h6c0-.9.4-1.8 1-2.3A7 7 0 0 0 12 2z"/></svg>';
  var ICON_BRANCH = SVG_HEAD + '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>';
  var ICON_BOOK = SVG_HEAD + '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/></svg>';
  var ICON_SPIN = SVG_HEAD + '<path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>';

  function actBtn(busy, icon, title, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'act-btn' + (busy ? ' busy' : '');
    b.title = title;
    b.disabled = busy;
    b.innerHTML = busy ? ICON_SPIN : icon;
    b.addEventListener('click', onClick);
    return b;
  }
  function buildActions() {
    var bar = document.createElement('div');
    bar.className = 'acts';
    bar.appendChild(actBtn(branchBusy, ICON_BRANCH, '会话分支', doBranch));
    bar.appendChild(actBtn(compressBusy, ICON_BRAIN, '记忆压缩', compressMemory));
    bar.appendChild(actBtn(false, ICON_BOOK, 'trace2skill', openTraceModal));
    return bar;
  }

  // 记忆压缩：触发全局大总结并截断上下文（后台异步），轮询 compressing 标记直到结束
  function compressMemory() {
    if (compressBusy || !activeSessionId) return;
    compressBusy = true; rerenderActions();
    var sid = activeSessionId;
    fetch('/api/chat/compress-memory', { method: 'POST' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json().catch(function () { return {}; }); })
      .then(function () {
        toast('记忆压缩已启动');
        var done = function () { clearInterval(timer); compressBusy = false; rerenderActions(); };
        var timer = setInterval(function () {
          fetch('/api/sessions/' + encodeURIComponent(sid) + '/status')
            .then(function (r) { return r.json(); })
            .then(function (st) { if (st && st.compressing === false) { done(); toast('记忆压缩完成'); } })
            .catch(function () {});
        }, 1500);
      })
      .catch(function (e) { compressBusy = false; rerenderActions(); toast('压缩失败：' + (e.message || e)); });
  }

  // 会话分支：交给宿主（对齐后端 POST /api/sessions/{id}/branch），宿主负责切到新会话并广播
  function doBranch() {
    if (branchBusy || !activeSessionId) return;
    branchBusy = true; rerenderActions();
    callAction('session.branch', { session_id: activeSessionId, alias: '' })
      .then(function (res) {
        if (res && res.status === 'busy') { toast('Agent 正忙，请等当前任务完成后再拉取分支'); return; }
        toast('已创建分支会话');
      })
      .catch(function (e) { toast('分支失败：' + (e.message || e)); })
      .finally(function () { branchBusy = false; rerenderActions(); });
  }

  // trace2skill：表单 → 宿主分配技能工厂并向本会话注入 evolve_factory 事件
  var t2sMask = document.getElementById('t2sMask');
  var t2sType = 'upgrade';
  var t2sBusy = false;
  function setT2sType(t) {
    t2sType = t;
    document.getElementById('t2sUpgrade').classList.toggle('on', t === 'upgrade');
    document.getElementById('t2sCreate').classList.toggle('on', t === 'create');
  }
  function openTraceModal() {
    document.getElementById('t2sName').value = '';
    document.getElementById('t2sGoal').value = '';
    setT2sType('upgrade');
    t2sMask.classList.add('on');
    setTimeout(function () { document.getElementById('t2sName').focus(); }, 0);
  }
  function closeTraceModal() { t2sMask.classList.remove('on'); }
  document.getElementById('t2sUpgrade').addEventListener('click', function () { setT2sType('upgrade'); });
  document.getElementById('t2sCreate').addEventListener('click', function () { setT2sType('create'); });
  document.getElementById('t2sCancel').addEventListener('click', closeTraceModal);
  t2sMask.addEventListener('click', function (e) { if (e.target === t2sMask) closeTraceModal(); });
  document.getElementById('t2sOk').addEventListener('click', function () {
    if (t2sBusy) return;
    var name = document.getElementById('t2sName').value.trim();
    var goal = document.getElementById('t2sGoal').value.trim();
    if (!name) { toast('请填写技能名称'); return; }
    if (!goal) { toast('请填写期望描述'); return; }
    t2sBusy = true;
    var okBtn = document.getElementById('t2sOk'); okBtn.disabled = true;
    callAction('chat.traceToSkill', { session_id: activeSessionId, name: name, is_upgrade: t2sType === 'upgrade', goal: goal })
      .then(function () { toast('技能任务已下发'); closeTraceModal(); })
      .catch(function (e) { toast('下发失败：' + (e.message || e)); })
      .finally(function () { t2sBusy = false; okBtn.disabled = false; });
  });

  // ---------- 流式思考块（Agent 思考期间实时透出思考增量）----------
  // 后端只在「一条消息真正落地」时才追加进历史（agent._append_history），思考阶段历史里
  // 没有新内容，所以只轮询历史会显得"卡住"、像要等整轮结束才刷新。这里对齐原 UI：
  // 思考期间用 /status 的 live_reasoning + phase 实时渲染流式块（THINKING/PROCESSING/ABORTING）。
  var live = { text: '', phase: 'idle' };
  var liveOpen = true;   // 展开/收起状态跨轮询保留

  var ICON_PAUSE = SVG_HEAD + '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>';
  var ICON_CHEVRON = SVG_HEAD + '<path d="m6 9 6 6 6-6"/></svg>';

  function liveTitle() {
    if (live.phase === 'processing') return '工具执行中…';
    if (live.phase === 'aborting') return '中断中…';
    return '思考中…';
  }
  function appendLive(stick) {
    var wrap = document.createElement('div');
    wrap.className = 'row live';
    var head = document.createElement('div');
    head.className = 'live-head';
    var spinning = live.phase === 'processing' || live.phase === 'aborting';
    var ico = document.createElement('span');
    ico.className = 'live-ico' + (spinning ? ' spin' : '');
    ico.innerHTML = spinning ? ICON_SPIN : ICON_BRAIN;
    var title = document.createElement('span');
    title.className = 'live-title';
    title.textContent = liveTitle();
    // 中断当前回合（对齐原 UI ReasoningBubble 的 onPause）
    var pause = document.createElement('button');
    pause.type = 'button'; pause.className = 'live-btn'; pause.title = '中断当前回合';
    pause.innerHTML = ICON_PAUSE;
    pause.addEventListener('click', function () {
      pause.disabled = true;
      callAction('chat.interrupt').catch(function () {}).finally(function () { pause.disabled = false; });
    });
    head.appendChild(ico); head.appendChild(title); head.appendChild(pause);
    if (live.text) {
      var tg = document.createElement('button');
      tg.type = 'button';
      tg.className = 'live-btn' + (liveOpen ? '' : ' collapsed');
      tg.title = liveOpen ? '收起思考内容' : '展开思考内容';
      tg.innerHTML = ICON_CHEVRON;
      tg.addEventListener('click', function () { liveOpen = !liveOpen; renderMessages(lastRows, true); });
      head.appendChild(tg);
    }
    wrap.appendChild(head);
    var body = null;
    if (live.text) {
      if (liveOpen) {
        body = document.createElement('div');
        body.className = 'reason-body live-body';
        body.textContent = live.text;
        wrap.appendChild(body);
      }
    } else {
      var hint = document.createElement('div');
      hint.className = 'live-hint';
      hint.textContent = live.phase === 'processing' ? '正在执行工具…' : '正在思考…';
      wrap.appendChild(hint);
    }
    listEl.appendChild(wrap);
    // 流式跟随：本来贴着底部时让思考内容始终停在最新一段
    if (body && stick) body.scrollTop = body.scrollHeight;
  }
  // 只增量刷新流式思考块（不重建整段历史）：思考期间的高频拍走这条路
  function updateLiveOnly() {
    if (!thinking || currentBranchId !== 'main') return;
    // 流式块也是「删掉旧的再插新的」：用户正在选它的时候同样会打断选区，推迟到选择结束补一次整段重建
    if (rebuildBlocked()) { pendingRows = lastRows || []; return; }
    var stick = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 40;
    var old = listEl.querySelector('.row.live');
    if (old) old.remove();
    appendLive(stick);
    if (stick) listEl.scrollTop = listEl.scrollHeight;
  }

  // ---------- 文件预览弹窗（图片 / 视频 / PDF / 文本）----------
  // 内容由后端文件接口提供：媒体与 PDF 走 /api/filesystem/preview（FileResponse 带正确 MIME），
  // 文本走 /api/filesystem/read 取原文用 pre 展示（对齐完整模式的链接预览能力）。
  var pvMask = document.getElementById('pvMask');
  var pvBody = document.getElementById('pvBody');
  var pvName = document.getElementById('pvName');
  var pvPath = '';
  var PV_IMG = ['png','jpg','jpeg','gif','webp','svg','bmp','ico'];
  var PV_VIDEO = ['mp4','webm','mov','ogg','avi','mkv'];
  var PV_PDF = ['pdf'];
  function previewURL(path) { return '/api/filesystem/preview?path=' + encodeURIComponent(path); }
  function fileNameOf(path) { return String(path).replace(/\\/g, '/').split('/').pop() || String(path); }
  function openPreview(path) {
    if (!path) return;
    pvPath = path;
    pvName.textContent = fileNameOf(path);
    pvName.title = path;
    pvBody.innerHTML = '';
    var ext = (String(path).split('.').pop() || '').toLowerCase();
    if (PV_IMG.indexOf(ext) >= 0) {
      var img = document.createElement('img');
      img.className = 'pv-img'; img.alt = fileNameOf(path); img.src = previewURL(path);
      pvBody.appendChild(img);
    } else if (PV_VIDEO.indexOf(ext) >= 0) {
      var v = document.createElement('video');
      v.className = 'pv-video'; v.src = previewURL(path); v.controls = true; v.autoplay = true;
      pvBody.appendChild(v);
    } else if (PV_PDF.indexOf(ext) >= 0) {
      // PDF 交给 Chromium 内置查看器渲染，避免按文本读取后展示二进制内容
      var fr = document.createElement('iframe');
      fr.className = 'pv-pdf'; fr.title = fileNameOf(path); fr.src = previewURL(path);
      pvBody.appendChild(fr);
    } else {
      var pre = document.createElement('pre');
      pre.className = 'pv-text'; pre.textContent = '加载中…';
      pvBody.appendChild(pre);
      fetch('/api/filesystem/read?path=' + encodeURIComponent(path))
        .then(function (r) {
          if (!r.ok) {
            // 404 是路径已失效（文件被移动/改名/删除），不是内容二进制，提示要区分开
            if (r.status === 404) throw new Error('文件不存在，可能已被移动或重命名');
            throw new Error('HTTP ' + r.status);
          }
          return r.json();
        })
        .then(function (d) { pre.textContent = (d && d.content) || '(空文件)'; })
        .catch(function (e) { pre.textContent = (e && e.message) || '无法预览该文件'; });
    }
    pvMask.classList.add('on');
  }
  function closePreview() { pvMask.classList.remove('on'); pvBody.innerHTML = ''; pvPath = ''; }
  document.getElementById('pvClose').addEventListener('click', closePreview);
  document.getElementById('pvExt').addEventListener('click', function () {
    if (!pvPath) return;
    var full = window.location.origin + previewURL(pvPath);
    if (window.purrcat && window.purrcat.openExternal) window.purrcat.openExternal(full);
    else window.open(full, '_blank');
  });
  pvMask.addEventListener('click', function (e) { if (e.target === pvMask) closePreview(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pvMask.classList.contains('on')) closePreview(); });
  // 消息里的本地文件链接（.filelink）点击 → 唤起预览
  listEl.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a.filelink') : null;
    if (!a) return;
    e.preventDefault();
    openPreview(a.getAttribute('data-fpath') || '');
  });

  // ---------- 数据装载 ----------
  var activeSessionId = '';
  var localBuffer = [];   // 本会话本地乐观插入的用户消息，等待服务端确认后合并去重
  var lastRows = null;    // 最近一次渲染的原始行（展示开关变化时可就地重绘）
  var thinking = false;   // Agent 是否思考中（思考中隐藏动作行）
  var compressBusy = false;
  var branchBusy = false;
  var branches = {};        // 当前会话的分支元数据（main + 子代理分支）
  var currentBranchId = 'main';   // 当前查看的分支视图（对齐完整模式的 MAIN / b1 …）
  // 仅重绘动作行（不整段重建历史，避免打断滚动位置与折叠展开态）
  function rerenderActions() {
    var old = listEl.querySelector('.acts');
    if (old) old.remove();
    if (lastRows && lastRows.length && !thinking) listEl.appendChild(buildActions());
  }

  // ---------- 子代理分支视图切换（顶部信息条右侧机器人图标：悬停列出分支，点击切换）----------
  function branchLabel(bId) { return bId === 'main' ? 'MAIN' : (bId.split('_')[1] || bId); }
  function renderBranchBar() {
    var btn = document.getElementById('sessBranchBtn');
    if (btn) {
      var hasSub = Object.keys(branches).length > 1;
      btn.disabled = !hasSub;
      btn.classList.toggle('on', hasSub && currentBranchId !== 'main');
      btn.title = hasSub
        ? '子代理分支：' + branchLabel(currentBranchId)
        : '暂无子代理分支';
    }
    renderBranchMenu();
  }
  // 悬停下拉：列出 MAIN 与全部子分支，点击切换视图
  function renderBranchMenu() {
    var menu = document.getElementById('sessBranchMenu');
    if (!menu) return;
    menu.innerHTML = '';
    var ids = Object.keys(branches);
    if (ids.length <= 1) {
      var empty = document.createElement('div');
      empty.className = 'rec-empty';
      empty.textContent = '暂无子代理分支';
      menu.appendChild(empty);
      return;
    }
    ids.forEach(function (bId) {
      var item = document.createElement('button');
      item.type = 'button';
      item.className = 'rec-item' + (bId === currentBranchId ? ' active' : '');
      item.textContent = branchLabel(bId);
      item.title = bId;
      item.addEventListener('click', function () { switchBranch(bId); });
      menu.appendChild(item);
    });
  }
  function switchBranch(bId) {
    if (bId === currentBranchId) return;
    currentBranchId = bId;
    localBuffer = [];        // 切换视图：本地乐观消息属于主分支，丢弃
    renderBranchBar();
    load(activeSessionId);
    callAction('branch.select', { branch_id: bId }).catch(function () {});   // 通知宿主：输入框据此进入/退出只读
  }
  function loadBranches(sessionId) {
    if (!sessionId) { branches = {}; renderBranchBar(); return; }
    fetch('/api/sessions/' + encodeURIComponent(sessionId) + '/branches')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        branches = (d && typeof d === 'object') ? d : { main: {} };
        // 当前查看的分支被删除时回退到主干
        if (!branches[currentBranchId]) currentBranchId = 'main';
        renderBranchBar();
      })
      .catch(function () { branches = { main: {} }; currentBranchId = 'main'; renderBranchBar(); });
  }

  // 顶部信息条：展示当前会话标题与 ID
  var headerSid = '';
  var headerDraft = false;
  function setSessHeader(sid, alias, isDraft) {
    var t = document.getElementById('sessTitle');
    var i = document.getElementById('sessId');
    if (!t || !i) return;
    var draft = !!isDraft || !sid;
    headerDraft = draft;
    if (document.body) document.body.classList.toggle('sess-draft', draft);
    if (!sid) { t.textContent = '新会话'; t.title = ''; i.textContent = ''; i.title = ''; return; }
    if (draft) { t.textContent = '新会话'; t.title = ''; i.textContent = ''; i.title = ''; return; }
    i.textContent = sid;
    i.title = sid;
    t.textContent = alias || '未命名会话';
    t.title = t.textContent;
  }
  function updateSessHeader(sid, isDraft) {
    headerSid = sid || '';
    if (!sid) { setSessHeader('', '', true); return; }
    setSessHeader(sid, '', isDraft);
    callAction('sessions.list').then(function (list) {
      if (headerSid !== sid) return;
      var s = (Array.isArray(list) ? list : []).filter(function (x) { return x.id === sid; })[0];
      if (s) setSessHeader(sid, s.alias || s.title, headerDraft);
    }).catch(function () {});
  }

  // 顶部右侧「最近会话」：悬停列出全部会话（面板内滚动），点击即切换
  function renderRecentMenu(list) {
    var menu = document.getElementById('sessRecentMenu');
    if (!menu) return;
    menu.innerHTML = '';
    var recent = Array.isArray(list) ? list : [];
    if (!recent.length) {
      var empty = document.createElement('div');
      empty.className = 'rec-empty';
      empty.textContent = '暂无最近会话';
      menu.appendChild(empty);
      return;
    }
    recent.forEach(function (s) {
      var item = document.createElement('button');
      item.type = 'button';
      item.className = 'rec-item' + (s.id === headerSid ? ' active' : '');
      item.textContent = s.alias || s.title || s.id;
      item.title = s.id;
      item.addEventListener('click', function () {
        callAction('session.switch', { session_id: s.id }).catch(function () {});
      });
      menu.appendChild(item);
    });
  }
  function refreshRecentMenu() {
    callAction('sessions.list').then(function (list) {
      var arr = (Array.isArray(list) ? list : []).slice();
      arr.sort(function (a, b) {
        return String(b.updated_at || b.created_at || '')
          .localeCompare(String(a.updated_at || a.created_at || ''));
      });
      renderRecentMenu(arr);
    }).catch(function () { renderRecentMenu([]); });
  }
  (function bindRecentMenu() {
    var wrap = document.getElementById('sessRecent');
    if (wrap) wrap.addEventListener('mouseenter', refreshRecentMenu);
  })();

  // 顶部右侧动作：子代理分支（悬停列出分支，点击切换）、新建会话
  (function bindHeaderActions() {
    var branchWrap = document.getElementById('sessBranch');
    if (branchWrap) branchWrap.addEventListener('mouseenter', renderBranchMenu);
    var newBtn = document.getElementById('sessNewBtn');
    if (newBtn) {
      newBtn.addEventListener('click', function () {
        callAction('sessions.new').catch(function () {});
      });
    }
  })();

  function load(sessionId) {
    if (!sessionId) { localBuffer = []; renderMessages([]); return; }
    fetch('/api/sessions/' + encodeURIComponent(sessionId) + '?branch_id=' + encodeURIComponent(currentBranchId))
      .then(function (r) { return r.json(); })
      .then(function (history) {
        var rows = Array.isArray(history) ? history
          : (history && Array.isArray(history.history)) ? history.history
          : (history && Array.isArray(history.messages)) ? history.messages : [];
        renderRows(rows);
      })
      .catch(function () { renderMessages([]); });
  }

  function refresh() {
    callAction('state.get').then(function (st) {
      activeSessionId = (st && st.activeSessionId) || activeSessionId || '';
      updateSessHeader(activeSessionId, !!(st && st.draft));
      load(activeSessionId);
      loadBranches(activeSessionId);
      ensurePoll();
    }).catch(function () { updateSessHeader(activeSessionId, headerDraft); load(activeSessionId); loadBranches(activeSessionId); ensurePoll(); });
  }

  // ---------- 轻量轮询刷新（与原 UI 一致的机制）----------
  // 原 UI(ChatPage)：思考期间每 0.5s、非思考每 1.5s 轮询当前会话历史，使 agent 回复自动出现。
  // 复刻同样节奏：activeSessionId 存在即轮询，is_thinking 决定快/慢两档，每次拉全量历史并合并本地乐观消息去重。
  var POLL_FAST = 500, POLL_SLOW = 1500;
  var pollTimer = null;
  var tick = 0;   // 轮询拍数（对齐原 UI：思考期间历史降频、status 保持高频）
  function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
  function setPoll(intv) {
    if (pollTimer && pollTimer._i === intv) return;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollTick, intv);
    pollTimer._i = intv;
  }
  function ensurePoll() {
    if (!activeSessionId) { stopPoll(); return; }
    setPoll(POLL_SLOW);
  }
  // 后台驱动的首条消息（如随手记投递 main）不经过输入框发送，宿主草稿标记不会自动清除。
  // 草稿态下低频核对会话列表：后端已转正就退出草稿态、恢复列表并重新判定空态。
  function reconcileDraft() {
    callAction('sessions.list').then(function (list) {
      var arr = Array.isArray(list) ? list : [];
      var s = arr.filter(function (x) { return x.id === activeSessionId; })[0];
      if (!s || s.draft) return;
      if (headerDraft) {
        updateSessHeader(activeSessionId, false);
        ensurePoll();
        load(activeSessionId);
      }
      resyncEmpty();
    }).catch(function () {});
  }

  function pollTick() {
    if (!activeSessionId) { stopPoll(); return; }
    tick += 1;
    fetch('/api/sessions/' + encodeURIComponent(activeSessionId) + '/status')
      .then(function (r) { return r.json(); })
      .then(function (st) {
        var t = !!(st && st.is_thinking);
        // 对齐原 UI：status 保持 500ms 高频（流式思考顺滑）；历史是全量 deepcopy 较重，
        // 思考期间降为每 3 拍拉一次，其余拍只增量更新流式思考块，避免重建整段历史。
        var pollHistory = !t || tick % 3 === 1;
        if (t !== thinking) {
          if (!t) {
            lastTurnEndedAt = Date.now();
            lastTurnEndedTime = lastRenderedTurnUserTime || '';
            collapseLastTurn();   // 任务完成：收起最后回合已展开的工具链细节
          }
          thinking = t; rerenderActions(); pollHistory = true;
        }
        // 流式思考内容与交互阶段（思考结束自动清空，改由 assistant 消息的 reasoning_content 渲染）
        live.text = t ? String((st && st.live_reasoning) || '') : '';
        live.phase = t ? String((st && st.phase) || 'thinking') : 'idle';
        setPoll(t ? POLL_FAST : POLL_SLOW);
        // 草稿态轮询低频核对后端是否已把会话转正（后台注入路径不刷新宿主草稿标记）
        if (headerDraft && tick % 6 === 0) reconcileDraft();
        if (pollHistory) { load(activeSessionId); loadBranches(activeSessionId); }
        else updateLiveOnly();
      })
      .catch(function () { setPoll(POLL_SLOW); });   // 会话暂不可用等：保持慢档，不轰炸
  }

  // ============================================================
  // 输入区（原「输入框」插件）
  // ============================================================

  // ---------- 引用 ----------
  var quotes = [];
  function addQuote(type, content, label) {
    quotes.push({ type: type, content: content, label: label || content });
    renderQuotes(); markSel();
  }
  function hasQuote(label) {
    return quotes.some(function (q) { return q.label === label; });
  }
  function removeQuote(label) {
    quotes = quotes.filter(function (q) { return q.label !== label; });
    renderQuotes(); markSel();
  }
  function renderQuotes() {
    quotesEl.innerHTML = '';
    quotes.forEach(function (q) {
      var d = document.createElement('div');
      d.className = 'quote';
      var s = document.createElement('span');
      s.textContent = q.label;
      var x = document.createElement('button');
      x.className = 'x';
      x.textContent = '✕';
      x.title = '移除引用';
      x.addEventListener('click', function () { removeQuote(q.label); });
      d.appendChild(s); d.appendChild(x);
      quotesEl.appendChild(d);
    });
  }

  // ---------- 左分类 ----------
  var CATS = [
    { t: 'file', label: '＋ 文件', dialog: true },
    { t: 'folder', label: '＋ 文件夹', dialog: true },
    { t: 'skill', label: 'Skill' },
    { t: 'mcp', label: 'MCP' },
    { t: 'graph', label: 'Graph' },
    { t: 'selfhost', label: '自托管' }
  ];
  var activeCat = null;
  var cache = {};   // skill/mcp/graph 的 fetched items
  function setActive(t) {
    activeCat = t;
    catsEl.querySelectorAll('.cat').forEach(function (c) { c.classList.toggle('active', c.dataset.t === t); });
  }
  function buildCats() {
    catsEl.innerHTML = '';
    CATS.forEach(function (c) {
      var b = document.createElement('button');
      b.className = 'cat';
      b.dataset.t = c.t;
      b.textContent = c.label;
      b.addEventListener('mouseenter', function () {
        setActive(c.t);
        if (c.t === 'selfhost') openSelfHost();
        else if (c.dialog) showRight(c.label, []);
        else openCat(c.t);
      });
      b.addEventListener('click', function () { handleCatClick(c); });
      catsEl.appendChild(b);
    });
  }

  // 右侧提示/条目
  var rSearch = document.getElementById('rSearch');
  var rightItems = [];        // 当前分类的完整条目；搜索只过滤展示，不丢数据
  var rightSearchable = false;

  // 搜索框只在 Skill / MCP / Graph 分类下出现
  function setSearchable(on) {
    rightSearchable = !!on;
    rSearch.classList.toggle('hide', !rightSearchable);
    if (!rightSearchable) rSearch.value = '';
  }

  function showRight(title, items, searchable) {
    rName.textContent = title;
    rightItems = items || [];
    setSearchable(searchable);
    renderRight();
  }

  function renderRight() {
    var q = rightSearchable ? (rSearch.value || '').trim().toLowerCase() : '';
    var list = !q ? rightItems : rightItems.filter(function (it) {
      return (it.text + ' ' + (it.hint || '')).toLowerCase().indexOf(q) >= 0;
    });
    rItems.innerHTML = '';
    if (!list.length) {
      var e = document.createElement('div');
      e.className = 'lb-empty';
      e.textContent = q ? '无匹配项' : '暂无可用项';
      rItems.appendChild(e);
      return;
    }
    list.forEach(function (it) {
      var b = document.createElement('button');
      b.className = 'item' + (hasQuote(it.label) ? ' sel' : '');
      b.textContent = it.text;
      b.title = it.hint || it.label;
      b.addEventListener('click', function () {
        if (hasQuote(it.label)) removeQuote(it.label);
        else addQuote(it.type, it.content, it.label);
      });
      rItems.appendChild(b);
    });
  }

  rSearch.addEventListener('input', function () { renderRight(); });
  // 已选状态回显
  function markSel() {
    var bs = rItems.querySelectorAll('.item');
    bs.forEach(function (b) { b.classList.toggle('sel', hasQuote(b.textContent)); });
  }

  function fetchList(t) {
    if (cache[t]) return Promise.resolve(cache[t]);
    var p;
    if (t === 'skill') p = fetch('/api/tools/skills').then(function (r) { return r.json(); }).then(function (s) {
      return (s || []).map(function (x) {
        var n = x.name || x.dir_name || 'unknown';
        return { label: n, text: n, hint: x.description || '', type: 'skill-quote', content: 'user want you fetch skill：' + n };
      });
    });
    else if (t === 'mcp') p = fetch('/api/tools/mcp').then(function (r) { return r.json(); }).then(function (servers) {
      var names = (servers && typeof servers === 'object') ? Object.keys(servers) : [];
      return names.map(function (n) {
        return { label: n, text: n, type: 'mcp-quote', content: 'user want you fetch mcp：' + n };
      });
    });
    else p = fetch('/api/graphs').then(function (r) { return r.json(); }).then(function (graphs) {
      var names = (graphs || []).map(function (g) { return (typeof g === 'string') ? g : g.name; });
      return names.map(function (g) {
        return { label: g, text: g, type: 'graph-quote', content: 'user quote the graph：' + g };
      });
    });
    return p.catch(function () { return []; }).then(function (items) { cache[t] = items; return items; });
  }

  function openCat(t) {
    setActive(t);
    fetchList(t).then(function (items) {
      if (activeCat !== t) return;
      var names = { skill: '选择 Skill', mcp: '选择 MCP', graph: '选择 Graph' };
      showRight(names[t] || t, items, true);
      markSel();
    });
  }

  function handleCatClick(c) {
    if (c.t === 'selfhost') { openSelfHost(); return; }
    if (c.t === 'file') {
      callAction('dialog.files').then(function (r) {
        var p = pickPath(r);
        if (p) addQuote('file-quote', 'user quote the file：' + p, p.split(/[\\/]/).pop());
      }).catch(function (e) { alert(String(e.message || e)); });
    } else if (c.t === 'folder') {
      callAction('dialog.folder').then(function (r) {
        var p = pickPath(r);
        if (p) addQuote('file-quote', 'user quote the file：' + p, p);
      }).catch(function (e) { alert(String(e.message || e)); });
    } else {
      openCat(c.t);
    }
  }

  // ---------- 自托管（心跳）：开关 + 间隔 + GOAL.md ----------
  // 唯一数据源为后端 /api/tools/heartbeat（读写 GOAL.md 与 heartbeat.json）。
  // 规则：GOAL.md 非空才允许启动；关闭自托管自动清空 GOAL.md。
  var SH_MIN = 60;
  var shEls = null;
  function shMsg(text, isErr) {
    if (!shEls) return;
    shEls.msg.textContent = text || '';
    shEls.msg.classList.toggle('err', !!isErr);
  }
  function shSetState(active) {
    if (!shEls) return;
    shEls.toggle.checked = !!active;
    shEls.state.textContent = active ? '运行中' : '已停止';
    shEls.state.classList.toggle('on', !!active);
  }
  function shInterval() {
    var n = parseInt(shEls.interval.value, 10);
    if (!n || n < SH_MIN) n = SH_MIN;
    shEls.interval.value = n;
    return n;
  }
  function shSave(active, goal) {
    return fetch('/api/tools/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval: shInterval(), active: !!active, goal: goal || '' })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error((d && d.detail) || ('HTTP ' + r.status));
        return d;
      });
    });
  }
  function loadSelfHost() {
    return fetch('/api/tools/heartbeat').then(function (r) { return r.json(); }).then(function (d) {
      if (!shEls) return;
      shEls.interval.value = (d && d.interval) || 1800;
      shEls.goal.value = (d && d.goal) || '';
      shSetState(!!(d && d.active));
      shMsg('');
    }).catch(function () { shMsg('读取自托管配置失败', true); });
  }
  function openSelfHost() {
    setActive('selfhost');
    setSearchable(false);
    rName.textContent = '自托管';
    rItems.innerHTML = '';
    var wrap = document.createElement('div');
    wrap.className = 'sh';
    wrap.innerHTML =
      '<div class="sh-head"><span class="sh-title">自托管（心跳）</span>' +
        '<label class="sh-switch"><input type="checkbox" id="shToggle"><span class="sh-slider"></span></label></div>' +
      '<div class="sh-state" id="shState">已停止</div>' +
      '<div class="sh-field"><span class="sh-label">心跳间隔（秒，最少 60）</span>' +
        '<input class="sh-interval" id="shInterval" type="number" min="60" step="60" value="1800"></div>' +
      '<div class="sh-field"><span class="sh-label">GOAL.md</span>' +
        '<textarea class="sh-goal" id="shGoal" placeholder="写下本次自托管要持续追求的目标…"></textarea></div>' +
      '<div class="sh-hint">必须填写 GOAL.md 才能启动；关闭自托管会自动清空 GOAL.md。</div>' +
      '<div class="sh-msg" id="shMsg"></div>';
    rItems.appendChild(wrap);
    shEls = {
      toggle: wrap.querySelector('#shToggle'),
      interval: wrap.querySelector('#shInterval'),
      goal: wrap.querySelector('#shGoal'),
      state: wrap.querySelector('#shState'),
      msg: wrap.querySelector('#shMsg')
    };
    shEls.toggle.addEventListener('change', function () {
      var active = shEls.toggle.checked;
      var goal = shEls.goal.value.trim();
      if (active && !goal) {
        shSetState(false);
        shMsg('请先填写 GOAL.md 才能启动', true);
        return;
      }
      shSave(active, active ? goal : '').then(function () {
        if (!active) shEls.goal.value = '';   // 关闭后自动清空 GOAL.md
        shSetState(active);
        shMsg(active ? '自托管已启动' : '自托管已停止，GOAL.md 已清空');
      }).catch(function (e) {
        shSetState(!active);
        shMsg(String((e && e.message) || e || '保存失败'), true);
      });
    });
    shEls.interval.addEventListener('change', function () {
      var active = shEls.toggle.checked;
      shSave(active, active ? shEls.goal.value.trim() : '').then(function () {
        shMsg('心跳间隔已更新为 ' + shEls.interval.value + ' 秒');
      }).catch(function (e) { shMsg(String((e && e.message) || e), true); });
    });
    shEls.goal.addEventListener('change', function () {
      if (!shEls.toggle.checked) return;   // 未启动时不落盘，保持 GOAL.md 为空
      var goal = shEls.goal.value.trim();
      if (!goal) { shMsg('GOAL.md 不能为空', true); return; }
      shSave(true, goal).then(function () { shMsg('GOAL.md 已更新'); })
        .catch(function (e) { shMsg(String((e && e.message) || e), true); });
    });
    loadSelfHost();
  }

  // ---------- 引用面板开合 ----------
  // 面板高度跟随左侧分类栏的实际内容高度：底部与最后一个分类（自托管）齐平，
  // 右栏条目超出时在 .items 内部滚动，不把面板撑高
  function sizeRefPick() {
    var pick = refPanel.querySelector('.ref-pick');
    if (!pick || !catsEl.children.length) return;
    var cap = Math.min(window.innerHeight * 0.46, 380);
    if (document.body.classList.contains('centered')) {
      cap = Math.min(cap, Math.max(120, window.innerHeight * 0.5 - 96));
    }
    pick.style.height = Math.min(catsEl.scrollHeight, cap) + 'px';
  }
  function toggleRef(show) {
    var open = show !== undefined ? !!show : !refPanel.classList.contains('open');
    refPanel.classList.toggle('open', open);
    plusBtn.classList.toggle('active', open);
    if (open) {
      // 默认悬浮在第一个分类上（文件）
      var first = catsEl.querySelector('.cat');
      if (first) first.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
      sizeRefPick();
    }
  }
  window.addEventListener('resize', function () {
    if (refPanel.classList.contains('open')) sizeRefPick();
  });
  plusBtn.addEventListener('click', function () { toggleRef(); });
  // 点击面板以外的区域（含输入框、历史列表）自动收起；点＋本身或面板内部不收起
  document.addEventListener('click', function (e) {
    if (!refPanel.classList.contains('open')) return;
    if (refPanel.contains(e.target) || plusBtn.contains(e.target)) return;
    toggleRef(false);
  });

  // ---------- Mode（切换 Agent Loop / paradigm，对齐原 UI 的热切换）----------
  var modeWrap = document.getElementById('modeWrap');
  var modeBtn = document.getElementById('mode');
  var modeMenu = document.getElementById('modeMenu');
  var modeLabel = document.getElementById('modeLabel');
  var modes = [{ name: '', label: '默认' }];
  var currentMode = '';
  var curSessionId = '';

  function modeLabelOf(name) { return name || '默认'; }
  function setModeLabel() {
    modeLabel.textContent = modeLabelOf(currentMode);
    modeBtn.title = '切换 Agent Loop，当前：' + modeLabelOf(currentMode);
  }
  function loadModes() {
    return fetch('/api/paradigms').then(function (r) { return r.json(); }).then(function (d) {
      var files = (d && d.files) || [];
      modes = [{ name: '', label: '默认' }];
      files.forEach(function (f) {
        // PARADIGM 即默认文件，已由「默认」项代表，不重复列出
        if (f && f.name && f.name !== 'PARADIGM') modes.push({ name: f.name, label: f.name });
      });
    }).catch(function () {});
  }
  function renderModeMenu() {
    modeMenu.innerHTML = '';
    modes.forEach(function (m) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = m.label;
      if (m.name === currentMode) b.className = 'sel';
      b.addEventListener('click', function () { setMode(m.name); });
      modeMenu.appendChild(b);
    });
  }
  // 当前 Mode 取自会话 meta.json（'' = 默认 PARADIGM）；草稿态（新会话未发送）取自宿主 draftParadigm
  function loadMode() {
    curSessionId = '';
    currentMode = '';
    setModeLabel();
    callAction('state.get').then(function (s) {
      curSessionId = (s && s.activeSessionId) || '';
      if (!curSessionId) {
        // 草稿态：会话尚未创建，展示用户在宿主里预选的范式（空串=默认）
        currentMode = (s && s.draftParadigm) || '';
        setModeLabel();
        return;
      }
      return fetch('/api/sessions/' + encodeURIComponent(curSessionId) + '/paradigm')
        .then(function (r) { return r.json(); })
        .then(function (d) { currentMode = (d && d.paradigm) || ''; setModeLabel(); })
        .catch(function () {});
    }).catch(function () {});
  }
  function setMode(name) {
    closeModeMenu();
    if (name === currentMode) { focusInput(); return; }
    // 草稿态：会话尚未创建，先把选择的 Agent Loop 记到宿主，首条消息建会话时再生效
    if (!curSessionId) {
      callAction('session.setDraftParadigm', { paradigm: name })
        .then(function () { currentMode = name; setModeLabel(); })
        .catch(function (e) { toast('切换 Agent Loop 失败：' + errText(e)); })
        .finally(focusInput);
      return;
    }
    fetch('/api/sessions/' + encodeURIComponent(curSessionId) + '/paradigm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paradigm: name })
    }).then(function (r) {
      if (r.ok) return null;
      // 后端错误体带 detail（如「Agent 正在忙，请稍后再切换范式」），必须原样透出，
      // 否则用户只看到「切换失败」这个空壳，不知道是被什么挡住的
      return r.json().catch(function () { return {}; }).then(function (d) {
        throw new Error((d && d.detail) || ('HTTP ' + r.status));
      });
    }).then(function () {
      currentMode = name;
      setModeLabel();
    }).catch(function (e) { toast('切换 Agent Loop 失败：' + errText(e)); })
      .finally(focusInput);
  }
  // 菜单点选后焦点停在菜单按钮上，用户接着打字会「打不进输入框」，切完把焦点还给输入框
  function focusInput() { if (!readOnly) input.focus(); }
  function errText(e) { return String((e && e.message) || e) || '未知错误'; }
  function closeModeMenu() { modeMenu.classList.remove('open'); }
  function openModeMenu() {
    loadModes().then(function () { renderModeMenu(); modeMenu.classList.add('open'); });
  }
  modeBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    if (modeMenu.classList.contains('open')) closeModeMenu();
    else openModeMenu();
  });
  document.addEventListener('click', function (e) {
    if (!modeWrap.contains(e.target)) closeModeMenu();
  });

  // ---------- 上下文占用圆环 + 本会话累计消耗 ----------
  // 黑色弧 = 上下文已占用，浅色轨道 = 未占用；hover 显示占用明细与本会话消耗（主/子）
  var ctxArc = document.getElementById('ctxArc');
  var ctxTip = document.getElementById('ctxTip');
  var CTX_C = 2 * Math.PI * 9;   // 圆环周长（r=9）

  function fmtNum(n) { return Number(n || 0).toLocaleString('en-US'); }
  function renderCtx(used, max, consumedTotal, consumedMain, consumedSub) {
    used = Number(used) || 0;
    max = Number(max) || 0;
    var ratio = max > 0 ? Math.min(1, used / max) : 0;
    // 有占用时给一个最小可见弧长（否则占比很小时黑弧短到看不见）
    var arcLen = ratio > 0 ? Math.max(ratio * CTX_C, 2.4) : 0;
    ctxArc.setAttribute('stroke-dasharray', arcLen.toFixed(2) + ' ' + CTX_C.toFixed(2));
    var pct = max > 0 ? (used / max) * 100 : 0;
    var cTotal = Number(consumedTotal) || 0;
    var cMain = Number(consumedMain) || 0;
    var cSub = Number(consumedSub) || 0;
    ctxTip.innerHTML =
      '上下文 <b>' + fmtNum(used) + ' / ' + fmtNum(max) + '</b>（<b>' + pct.toFixed(1) + '%</b>）' +
      '<br>本会话消耗 <b>' + fmtNum(cTotal) + '</b>（主 <b>' + fmtNum(cMain) + '</b> · 子 <b>' + fmtNum(cSub) + '</b>）';
  }
  var viewedSessionId = '';   // 当前“正在查看”的会话：圆环按会话展示其落盘用量
  function refreshCtx() {
    // 无「正在查看」的会话（草稿态 / 无会话）：圆环置空。
    // 否则不带 session_id 请求会拿到后端当前挂载会话的实时用量，误显示上一个会话的额度。
    if (!viewedSessionId) { renderCtx(0, 0, 0, 0, 0); return; }
    // 传入正在查看的会话：宿主点击会话不会切换后端 Agent，故由后端按会话读取落盘用量；
    // 若该会话正是 Agent 当前会话，后端会返回实时内存值（对话中即时刷新）。
    fetch('/api/agent/token?session_id=' + encodeURIComponent(viewedSessionId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        renderCtx(
          d && d.window_token, d && d.max_token,
          d && d.consumed_total, d && d.consumed_main, d && d.consumed_sub
        );
      })
      .catch(function () {});
  }
  refreshCtx();
  setInterval(refreshCtx, 5000);   // 与完整模式一致：5s 刷新一次

  // ---------- 发送 ----------
  // 子代理分支视图只读：查看子代理分支时禁止发送（对齐完整模式「READ-ONLY SUB-BRANCH VIEW」，
  // 否则消息会误发到主干）。分支状态由宿主 branch.switched 事件下发。
  var DEFAULT_PH = '输入消息，Shift+Enter 换行';
  var readOnly = false;
  function applyBranchState(bId) {
    readOnly = !!bId && bId !== 'main';
    input.disabled = readOnly;
    input.placeholder = readOnly ? '子代理分支视图（只读），回到 MAIN 可继续输入' : DEFAULT_PH;
    sendBtn.disabled = readOnly;
  }
  function send() {
    if (readOnly) return;
    var text = input.value.trim();
    if (!text && !quotes.length) return;
    var events = [];
    quotes.forEach(function (q) { events.push({ type: q.type, content: q.content }); });
    if (text) events.push({ type: 'user', content: text });
    sendBtn.disabled = true;
    callAction('chat.sendBatch', { events: events })
      .then(function () { input.value = ''; autosizeInput(); quotes = []; renderQuotes(); toggleRef(false); })
      .catch(function (e) { alert('发送失败: ' + e.message); })
      .finally(function () { sendBtn.disabled = readOnly; });
  }
  // 输入框随内容自动调高（上限由 CSS max-height 控制，超出后内部滚动）
  var INPUT_MAX_H = 240;
  function autosizeInput() {
    input.style.height = 'auto';
    var h = Math.min(input.scrollHeight, INPUT_MAX_H);
    input.style.height = h + 'px';
    input.style.overflowY = input.scrollHeight > INPUT_MAX_H ? 'auto' : 'hidden';
  }
  input.addEventListener('input', autosizeInput);
  window.addEventListener('resize', autosizeInput);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  sendBtn.addEventListener('click', send);

  // ---------- 粘贴/拖拽文件 → 文件引用 ----------
  function attachFiles(files) {
    Array.prototype.forEach.call(files || [], function (file) {
      // 拖拽进来的本地文件自带绝对路径，直接引用，不复制
      if (file.path) {
        addQuote('file-quote', 'user quote the file：' + file.path, file.path.split(/[\\/]/).pop());
        return;
      }
      // 剪贴板里的图片/文件没有路径，先落到 buffer 再用返回路径引用
      var fd = new FormData();
      fd.append('file', file, file.name || 'clipboard.png');
      fetch('/api/system/agent/upload', { method: 'POST', body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.saved_path) throw new Error('上传失败');
          addQuote('file-quote', 'user quote the file：' + d.saved_path, d.saved_path.split(/[\\/]/).pop());
        })
        .catch(function (e) { alert('附件上传失败: ' + (e.message || e)); });
    });
  }
  input.addEventListener('paste', function (e) {
    var dt = e.clipboardData;
    if (!dt) return;
    var files = Array.prototype.slice.call(dt.files || []);
    if (!files.length) {
      files = Array.prototype.slice.call(dt.items || [])
        .filter(function (it) { return it.kind === 'file'; })
        .map(function (it) { return it.getAsFile(); })
        .filter(Boolean);
    }
    if (!files.length) return;
    e.preventDefault();
    attachFiles(files);
  });
  var barWrap = input.closest('.bar-wrap');
  ['dragenter', 'dragover'].forEach(function (ev) {
    barWrap.addEventListener(ev, function (e) {
      if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  });
  barWrap.addEventListener('drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    attachFiles(e.dataTransfer.files);
  });
  // 拖到输入框以外时阻止 Electron 把主窗口导航到 file://
  window.addEventListener('dragover', function (e) {
    if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) e.preventDefault();
  });
  window.addEventListener('drop', function (e) { e.preventDefault(); });

  // ---------- 空态（欢迎语/居中）----------
  // 空态由宿主 layout.empty 下发：无活动会话或无消息 → 隐藏历史列表、输入区居中欢迎
  function setCentered(empty) { document.body.classList.toggle('centered', !!empty); }
  function resyncEmpty() {
    callAction('state.get').then(function (s) { setCentered(s && s.empty); }).catch(function () {});
  }

  // ---------- 宿主事件路由（历史 + 输入统一处理）----------
  window.addEventListener('message', function (e) {
    var m = e.data;
    if (!m || typeof m !== 'object') return;
    if (m.type === 'layout.empty') { setCentered(!!m.empty); return; }
    if (m.type !== 'event') return;
    var d = m.data || {};
    if (m.event === 'layout.empty') {
      setCentered(!!d.empty);
    } else if (m.event === 'session.switched') {
      localBuffer = [];   // 切换会话：本地乐观消息属于旧会话，丢弃
      activeSessionId = d.session_id;
      viewedSessionId = d.session_id || '';
      thinking = false;
      live.text = ''; live.phase = 'idle';
      currentBranchId = 'main';   // 新会话从主干视图进入
      branches = {};
      renderBranchBar();
      ensurePoll();
      refresh();
      resyncEmpty(); loadMode(); refreshCtx();
    } else if (m.event === 'session.renamed') {
      if (d.session_id === headerSid) setSessHeader(headerSid, d.alias || '', headerDraft);
    } else if (m.event === 'branch.switched') {
      // 宿主回推当前分支视图（含晚加载补推）：与本插件本地态对账，必要时重载；同时切换输入只读
      var bid = d.branch_id || 'main';
      applyBranchState(bid);
      if (bid !== currentBranchId) {
        currentBranchId = bid;
        localBuffer = [];
        renderBranchBar();
        load(activeSessionId);
      }
    } else if (m.event === 'conversation.updated') {
      // 首条消息发出后草稿已转正：header 立即退出草稿态
      if (headerDraft) updateSessHeader(activeSessionId, false);
      ensurePoll();
      load(activeSessionId);
      resyncEmpty();
      refreshCtx();   // 有消息落地即刷新累计消耗，比 5s 轮询更跟手
    } else if (m.event === 'requests.updated') {
      loadReqPeek();
    } else if (m.event === 'conversation.local') {
      ensurePoll();   // 刚发送，后端即将 busy，立即进入快速轮询
      if (currentBranchId !== 'main') return;   // 子代理分支视图只读，乐观消息属于主干，不渲染
      var evs = Array.isArray(d.events) ? d.events : [];
      evs.forEach(function (ev) {
        var txt = String(ev && ev.content || ''); if (!txt) return;
        localBuffer.push({ content: txt });
        var emptyEl = listEl.querySelector('.empty'); if (emptyEl) emptyEl.remove();
        listEl.appendChild(renderLocalUser(txt));
      });
      if (evs.length) listEl.scrollTop = listEl.scrollHeight;
      // 发送即进入思考态：不等下一轮 /status，立刻显示"思考中"块（对齐原 UI 的即时反馈）
      if (evs.length && !thinking) {
        thinking = true; live.text = ''; live.phase = 'thinking';
        rerenderActions();          // 思考中收起动作行
        appendLive(true);           // 复用同一套流式块，后续由 500ms 轮询续写
        listEl.scrollTop = listEl.scrollHeight;
      }
    }
  });

  /* ---------- 待办 peek：输入框上方一行摘要，展开后逐条查看 request ---------- */
  var REQ_TYPE_LABEL = {
    file_read: '读取文件',
    file_write: '写入文件',
    skill_test: '技能盲测',
    sensor_test: '协议体检',
    skill_merge: '技能合并',
    mcp_merge: 'MCP 合并',
    sensor_merge: 'Sensor 合并',
    agentloop_merge: '范式合并',
    graph_merge: '图合并',
    dependency_check: '依赖检查',
    computer_use: '电脑操作'
  };
  var REQ_IGNORE_ICON = SVG_HEAD + '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>';
  var reqPeekEl = document.getElementById('reqPeek');
  var reqHeadBtn = document.getElementById('rpHead');
  var reqBodyEl = document.getElementById('rpBody');
  var reqBadgeEl = document.getElementById('rpBadge');
  var reqList = [];          // 当前待办请求（后端按创建时间倒序）
  var reqIdx = 0;            // 正在查看的请求下标
  var reqPeekOpen = false;   // 是否向上展开
  var reqPeekSig = '';       // 内容指纹：没变就不重绘
  var reqBusy = {};          // req_id -> 是否正在提交裁决

  function reqTypeLabel(t) { return REQ_TYPE_LABEL[t] || (t || '请求'); }

  function reqNavBtn(dir) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'rp-navbtn';
    b.title = dir < 0 ? '上一条' : '下一条';
    b.innerHTML = dir < 0
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"></path></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"></path></svg>';
    b.disabled = reqList.length < 2;
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      if (reqList.length < 2) return;
      reqIdx = (reqIdx + dir + reqList.length) % reqList.length;
      renderReqPeek();
    });
    return b;
  }

  function renderReqPeek() {
    if (!reqList.length) {
      reqPeekEl.hidden = true;
      reqPeekOpen = false;
      reqHeadBtn.setAttribute('aria-expanded', 'false');
      reqBodyEl.innerHTML = '';
      return;
    }
    if (reqIdx < 0 || reqIdx >= reqList.length) reqIdx = 0;
    var req = reqList[reqIdx];
    var busy = !!reqBusy[req.id];
    reqPeekEl.hidden = false;
    reqPeekEl.classList.toggle('open', reqPeekOpen);
    reqHeadBtn.setAttribute('aria-expanded', reqPeekOpen ? 'true' : 'false');
    reqBadgeEl.textContent = String(reqList.length);

    reqBodyEl.innerHTML = '';
    if (!reqPeekOpen) return;

    // 顶行：类型标签 + 右上角左右切换与 n/m
    var top = document.createElement('div');
    top.className = 'rp-top';
    var type = document.createElement('span');
    type.className = 'rp-type' + (req.type === 'dependency_check' ? ' dep' : '');
    type.textContent = reqTypeLabel(req.type);
    type.title = req.type || '';
    top.appendChild(type);
    var nav = document.createElement('span');
    nav.className = 'rp-nav';
    nav.appendChild(reqNavBtn(-1));
    var pos = document.createElement('span');
    pos.className = 'rp-pos';
    pos.textContent = (reqIdx + 1) + '/' + reqList.length;
    nav.appendChild(pos);
    nav.appendChild(reqNavBtn(1));
    top.appendChild(nav);
    reqBodyEl.appendChild(top);

    // 目标 + 申请理由
    var target = document.createElement('div');
    target.className = 'rp-target';
    target.textContent = req.target || '(无标题)';
    target.title = req.target || '';
    reqBodyEl.appendChild(target);
    if (req.reason) {
      var reason = document.createElement('div');
      reason.className = 'rp-reason';
      reason.textContent = req.reason;
      reqBodyEl.appendChild(reason);
    }

    // 动作：普通请求批准/拒绝；依赖检查直接前往部署
    reqBodyEl.classList.toggle('busy', busy);
    var acts = document.createElement('div');
    acts.className = 'rp-acts';
    if (req.type === 'dependency_check') {
      acts.appendChild(reqActBtn('前往部署', 'ok', function () {
        callAction('settings.open', { tab: 'deploy' }).catch(function () {});
      }));
    } else {
      acts.appendChild(reqActBtn('批准', 'ok', function () { resolveReqPeek(req.id, true, false); }));
      acts.appendChild(reqActBtn('拒绝', 'no', function () { resolveReqPeek(req.id, false, false); }));
    }
    var ig = reqActBtn('', 'ig', function () { resolveReqPeek(req.id, false, true); }, REQ_IGNORE_ICON);
    ig.title = '忽略（不通知 Agent）';
    acts.appendChild(ig);
    reqBodyEl.appendChild(acts);
  }

  function reqActBtn(label, kind, onClick, icon) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'rp-btn ' + kind;
    if (icon) b.innerHTML = icon;
    else b.textContent = label;
    b.addEventListener('click', function (ev) {
      ev.stopPropagation();
      onClick();
    });
    return b;
  }

  // 裁决：批准 / 拒绝 / 忽略后刷新待办，展开态自动切到下一条
  function resolveReqPeek(id, approved, ignore) {
    if (reqBusy[id]) return;
    reqBusy[id] = true;
    renderReqPeek();
    callAction('requests.resolve', {
      request_id: id,
      approved: !!approved,
      ignore: !!ignore
    })
      .then(function () {
        delete reqBusy[id];
        reqPeekSig = null;
        return loadReqPeek();
      })
      .catch(function () {
        delete reqBusy[id];
        renderReqPeek();
      });
  }

  function loadReqPeek() {
    return callAction('requests.list')
      .then(function (list) {
        var next = Array.isArray(list) ? list : [];
        var sig = next.map(function (r) {
          return r.id + ':' + (r.status || '') + ':' + (r.type || '') + ':' + (r.target || '');
        }).join('|');
        if (sig === reqPeekSig) return;
        reqPeekSig = sig;
        reqList = next;
        if (reqIdx >= reqList.length) reqIdx = 0;
        renderReqPeek();
      })
      .catch(function () {});
  }

  reqHeadBtn.addEventListener('click', function (ev) {
    ev.stopPropagation();
    if (!reqList.length) return;
    reqPeekOpen = !reqPeekOpen;
    renderReqPeek();
  });

  // ---------- 启动 ----------
  refresh();
  buildCats();
  markSel();
  resyncEmpty();
  loadMode();
  loadReqPeek();
  // 待办没有推送通道（新请求只在后端落盘），与侧栏待办同频轮询
  setInterval(loadReqPeek, 3000);
  // 初始化分支视图态与查看中的会话：晚加载时宿主已补推 branch.switched，这里再对账一次兜底
  callAction('state.get').then(function (s) {
    applyBranchState(s && s.activeBranchId);
    viewedSessionId = (s && s.activeSessionId) || '';
    refreshCtx();
  }).catch(function () {});
})();
