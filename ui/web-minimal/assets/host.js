/* ============================================================
   web-minimal 宿主核心（白灰改造版）
   - 加载 /api/webmin/manifest 拿到插件清单 + configSchema + config
   - 按 slot 把插件渲染为 iframe；每个 slot 挂载首个匹配插件
   - callAction 动作总线：
       * 后端副作用动作 → POST /api/webmin/action
       * 聊天/会话/配置/引用/枚举 → 直接同源 fetch 现有 /api/*
       * 本地 Electron 能力（对话框/窗口控制/壁纸选择）→ 仅在宿主访问 window.purrcat
   - 配置管理：manifest → effective() 合并 schema 默认值+已存值，
     通过 config.get / config.set / configApply 注入插件
   - 广播事件：动作后向相关 slot 广播 {type:'event', event, data}
   ============================================================ */
(function () {
  'use strict';

  const HOST = window;
  const SLOTS = ['pet', 'sidebar', 'history', 'input', 'background', 'conversation'];

  // ---- 状态 ----
  const pluginBySlot = {};    // slot -> descriptor（含 configSchema/config/builtin）
  const frames = {};          // slot -> iframe element
  const configByPlugin = {};  // plugin_id -> 有效配置（默认值 ∪ 已存值）
  const groupState = {
    activeSessionId: '',
    sessions: [],
    empty: true,
    plugins: [],              // manifest 注解后的插件列表（供设置面板使用）
  };
  // 最左图标栏状态：stage 0=收起(仅开关) 1=仅图标 2=图标+名称(左侧栏)；hidden=各插件隐藏开关（持久化）；opacity=白条透明度
  const railState = { stage: 1, hidden: {}, opacity: 1 };
  const railButtons = {};   // plugin_id -> 图标栏按钮元素（供即时刷新高亮）

  // ---- 图标栏（固定组件）----
  const RAIL_STAGES = 3;
  // 图标与名称由插件本体(plugin.json)定义；无 icon 时退回名称首字符
  function railIcon(p) { return p.icon || ((p.name || p.id || '?').charAt(0) || '?').toUpperCase(); }
  function isRailPlugin(p) { return p && p.entry; }
  function railHidden(id) { return !!(railState.hidden && railState.hidden[id]); }
  function applySlotHidden(slot, hidden) {
    const el = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (el) el.style.display = hidden ? 'none' : '';
    // 会话列表(侧栏)隐藏时，让主区舒展到最左，腾出侧栏空间
    if (slot === 'sidebar') HOST.document.body.classList.toggle('rail-nosidebar', !!hidden);
  }
  function persistRail() {
    return fetch('/api/webmin/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plugins: configByPlugin, rail: railState }),
    }).then((res) => { if (!res.ok) throw new Error(res.status); });
  }
  function applyRailStage() {
    HOST.document.body.classList.remove('rail-0', 'rail-1', 'rail-2');
    HOST.document.body.classList.add('rail-' + railState.stage);
    const t = HOST.document.getElementById('railToggle');
    if (t) {
      // 图标形态固定不变，仅通过展开/收起影响侧栏布局
      t.textContent = '☰';
      t.title = '收起 / 展开插件栏';
    }
  }
  function applyRailOpacity() {
    let o = typeof railState.opacity === 'number' ? railState.opacity : 1;
    o = Math.min(1, Math.max(0, o));
    const rail = HOST.document.getElementById('rail');
    if (rail) rail.style.setProperty('--wm-rail-bg', 'rgba(255,255,255,' + o.toFixed(3) + ')');
  }
  function cycleRail() {
    railState.stage = (railState.stage + 1) % RAIL_STAGES;   // 0→1→2→0
    applyRailStage();
    persistRail().catch(() => {});
  }
  function bindRailToggle() {
    const t = HOST.document.getElementById('railToggle');
    if (t) t.addEventListener('click', cycleRail);
  }
  function setPluginHidden(id, hidden) {
    if (!railState.hidden) railState.hidden = {};
    if (hidden) railState.hidden[id] = true; else delete railState.hidden[id];
    const slot = slotOfPlugin(id);
    if (slot) applySlotHidden(slot, hidden);
    persistRail().catch(() => {});
  }
  // 按当前显隐状态即时重算单个图标按钮的 on/off 高亮
  function updateRailButton(btn, p) {
    if (!btn) return;
    btn.classList.remove('on', 'off');
    if (p.railAction) {
      // 动作型图标不表达"显隐"，只在对应面板开启时高亮（如设置）
      if (panelActionActive(p)) btn.classList.add('on');
    } else {
      btn.classList.add(railHidden(p.id) ? 'off' : 'on');
    }
  }
  // 动作型图标当前是否"激活"（用于高亮跟随面板开合）
  function panelActionActive(p) {
    if (p.railAction === 'settings.open') return HOST.document.body.classList.contains('settings-open');
    return false;
  }
  function buildRail() {
    const iconsEl = HOST.document.getElementById('railIcons');
    if (!iconsEl) return;
    applyRailStage();
    iconsEl.innerHTML = '';
    groupState.plugins.filter(isRailPlugin).forEach((p) => {
      const btn = HOST.document.createElement('button');
      btn.className = 'rail-ico';
      btn.title = (p.name || p.id);
      const g = HOST.document.createElement('span');
      g.className = 'rail-glyph';
      g.textContent = railIcon(p);
      btn.appendChild(g);
      const nm = HOST.document.createElement('span');
      nm.className = 'rail-name';
      nm.textContent = p.name || p.id;
      btn.appendChild(nm);
      updateRailButton(btn, p);   // 初始高亮
      railButtons[p.id] = btn;    // 登记，供面板开合状态即时刷新高亮
      btn.addEventListener('click', () => {
        if (p.railAction) { callAction(p.railAction, {}).catch(() => {}); return; }  // 例如设置 → 打开设置面板
        setPluginHidden(p.id, !railHidden(p.id));
        updateRailButton(btn, p); // 即时刷新高亮，无需重建
      });
      iconsEl.appendChild(btn);
    });
    // 设置按钮（宿主固有资产，非插件）：固定在图标栏末尾
    const sb = HOST.document.createElement('button');
    sb.className = 'rail-ico';
    sb.id = 'railSettings';
    sb.title = '设置';
    const sg = HOST.document.createElement('span');
    sg.className = 'rail-glyph';
    sg.textContent = '⚙';
    sb.appendChild(sg);
    const snm = HOST.document.createElement('span');
    snm.className = 'rail-name';
    snm.textContent = '设置';
    sb.appendChild(snm);
    sb.addEventListener('click', () => setSettingsOpen(!HOST.document.body.classList.contains('settings-open')));
    iconsEl.appendChild(sb);
    railButtons['__settings__'] = sb;
    applyRailOpacity();
  }

  // ---- 工具 ----
  function effectiveConfig(desc) {
    const sch = desc.configSchema || [];
    const stored = desc.config || {};
    const out = {};
    sch.forEach((f) => {
      if (f.default !== undefined) out[f.key] = f.default;
      else if (f.type === 'switch') out[f.key] = false;
      else if (f.type === 'number') out[f.key] = 0;
      else if (f.type === 'select') out[f.key] = (f.options && f.options[0]) || '';
      else out[f.key] = '';
    });
    Object.assign(out, stored);
    return out;
  }
  function slotOfPlugin(pid) {
    for (const s of SLOTS) {
      if (pluginBySlot[s] && pluginBySlot[s].id === pid) return s;
    }
    return null;
  }

  // ---- 空态 ----（沿用现有机制）
  function setEmpty(v) {
    groupState.empty = !!v;
    HOST.document.body.classList.toggle('empty', !!v);
    broadcast('input', 'layout.empty', { empty: !!v });
    broadcast('conversation', 'layout.empty', { empty: !!v });
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
  // 重新拉取会话列表，保证 empty 判定与侧栏高亮基于最新数据
  async function refreshSessions() {
    try {
      const list = await (await fetch('/api/sessions')).json();
      groupState.sessions = Array.isArray(list) ? list : groupState.sessions;
    } catch (_) { /* 保持原样 */ }
  }
  // 会话状态变更事件需同时通知会话卡片(history)与侧栏(列表)，侧栏据此刷新选中高亮
  function broadcastSessions(event, data) {
    broadcast('conversation', event, data);
    broadcast('sidebar', event, data);
    broadcast('input', event, data);   // 输入框据此重新对账空态（欢迎语/居中）
  }

  // ---- 设置面板开合（宿主固有资产，非插件）：原生渲染到 .settings-body ----
  function setSettingsOpen(open) {
    HOST.document.body.classList.toggle('settings-open', !!open);
    // 设置按钮高亮跟随面板开合
    const sb = HOST.document.getElementById('railSettings');
    if (sb) sb.classList.toggle('on', !!open);
    if (open) renderSettings();
  }

  // 设置面板内"配置变更后防抖重建"，避免高频事件打乱滑块
  let settingsRenderT = null;
  function scheduleSettingsRender() {
    clearTimeout(settingsRenderT);
    settingsRenderT = setTimeout(renderSettings, 250);
  }
  function settingsSave(pid, cfg) {
    callAction('config.set', { plugin_id: pid, config: cfg }).catch(() => {});
    scheduleSettingsRender();
  }

  // 白条透明度（宿主外观项，不依赖插件）
  function renderRailAppearance(container) {
    const box = HOST.document.createElement('div');
    box.className = 'plugin';
    const head = HOST.document.createElement('div');
    head.className = 'p-head';
    const nm = HOST.document.createElement('span');
    nm.className = 'p-name';
    nm.textContent = '左侧白条';
    head.appendChild(nm);
    box.appendChild(head);
    const sep = HOST.document.createElement('div');
    sep.className = 'p-sep';
    box.appendChild(sep);
    const form = HOST.document.createElement('div');
    const row = HOST.document.createElement('div');
    row.className = 'field';
    const label = HOST.document.createElement('label');
    label.textContent = '透明度';
    row.appendChild(label);
    const rng = HOST.document.createElement('input');
    rng.type = 'range';
    rng.min = 0.15;
    rng.max = 1;
    rng.step = 0.05;
    rng.style.width = '100%';
    const o = typeof railState.opacity === 'number' ? railState.opacity : 1;
    rng.value = Math.min(1, Math.max(0.15, o));
    const valEl = HOST.document.createElement('div');
    valEl.className = 'range-val';
    function upd() { valEl.textContent = '透明度 ' + Number(rng.value).toFixed(2); }
    rng.addEventListener('input', function () {
      railState.opacity = Number(rng.value);
      applyRailOpacity();
      persistRail().catch(() => {});
      upd();
    });
    upd();
    row.appendChild(rng);
    row.appendChild(valEl);
    form.appendChild(row);
    box.appendChild(form);
    container.appendChild(box);
  }

  function renderPluginCard(container, p, cfg) {
    const box = HOST.document.createElement('div');
    box.className = 'plugin';
    const head = HOST.document.createElement('div');
    head.className = 'p-head';
    const name = HOST.document.createElement('span');
    name.className = 'p-name';
    name.textContent = p.name || p.id;
    const right = HOST.document.createElement('span');
    right.className = 'row-actions';
    const slug = HOST.document.createElement('span');
    slug.className = 'p-tag';
    slug.textContent = p.slot || '';
    right.appendChild(slug);
    if (!p.builtin) {
      const del = HOST.document.createElement('button');
      del.className = 'btn sm danger';
      del.textContent = '删除';
      del.addEventListener('click', function () {
        if (HOST.confirm('确定删除插件 “' + (p.name || p.id) + '” 吗？')) {
          callAction('plugin.delete', { plugin_id: p.id }).then(function () { renderSettings(); }).catch(function (e) { HOST.alert('删除失败：' + e.message); });
        }
      });
      right.appendChild(del);
    }
    head.appendChild(name);
    head.appendChild(right);
    box.appendChild(head);
    if (p.configSchema && p.configSchema.length) {
      const sep2 = HOST.document.createElement('div');
      sep2.className = 'p-sep';
      box.appendChild(sep2);
      renderFields(box, p, cfg);
    } else {
      const none = HOST.document.createElement('div');
      none.className = 'p-tag';
      none.textContent = '该插件无配置项';
      box.appendChild(none);
    }
    container.appendChild(box);
  }

  function renderFields(form, p, cfg) {
    (p.configSchema || []).forEach(function (field) {
      const key = field.key;
      const type = field.type || 'text';
      const row = HOST.document.createElement('div');
      row.className = 'field';
      const label = HOST.document.createElement('label');
      label.textContent = field.label || key;
      if (type === 'switch') {
        row.classList.add('switch-row');
        const left = HOST.document.createElement('div');
        left.appendChild(label);
        row.appendChild(left);
        const sw = HOST.document.createElement('label');
        sw.className = 'switch';
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector('input');
        chk.checked = !!cfg[key];
        chk.addEventListener('change', function () { cfg[key] = chk.checked; settingsSave(p.id, cfg); });
        row.appendChild(sw);
      } else if (type === 'select') {
        const sel = HOST.document.createElement('select');
        (field.options || []).forEach(function (op) {
          const o2 = HOST.document.createElement('option');
          o2.value = op;
          o2.textContent = op;
          sel.appendChild(o2);
        });
        sel.value = cfg[key] || '';
        sel.addEventListener('change', function () { cfg[key] = sel.value; settingsSave(p.id, cfg); });
        row.appendChild(sel);
      } else if (type === 'number') {
        const num = HOST.document.createElement('input');
        num.type = 'number';
        num.step = 'any';
        num.value = cfg[key] == null ? 0 : cfg[key];
        num.addEventListener('change', function () { cfg[key] = num.value === '' ? null : Number(num.value); settingsSave(p.id, cfg); });
        row.appendChild(num);
      } else if (type === 'range') {
        const rng = HOST.document.createElement('input');
        rng.type = 'range';
        rng.min = (field.min != null) ? field.min : 0;
        rng.max = (field.max != null) ? field.max : 1;
        rng.step = (field.step != null) ? field.step : 0.01;
        rng.style.width = '100%';
        let fv = cfg[key];
        rng.value = (typeof fv === 'number' && !isNaN(fv)) ? fv : ((field.default != null) ? field.default : rng.max);
        const valEl = HOST.document.createElement('div');
        valEl.className = 'range-val';
        function upd() { valEl.textContent = (field.label || key) + ' ' + Number(rng.value).toFixed(2); }
        rng.addEventListener('input', function () { upd(); cfg[key] = Number(rng.value); settingsSave(p.id, cfg); });
        upd();
        row.appendChild(rng);
        row.appendChild(valEl);
      } else if (type === 'wallpapers') {
        const wallsWrap = HOST.document.createElement('div');
        wallsWrap.className = 'walls';
        const list = Array.isArray(cfg[key]) ? cfg[key] : [];
        function isV(url) { return /\.(mp4|webm|mov)(\?|$)/i.test(url); }
        function draw() {
          wallsWrap.innerHTML = '';
          list.forEach(function (w, i) {
            const t = HOST.document.createElement('div');
            t.className = 'wall-thumb';
            if (isV(w.src || '')) { const v = HOST.document.createElement('video'); v.src = w.src; v.muted = true; v.loop = true; t.appendChild(v); }
            else { const im = HOST.document.createElement('img'); im.src = w.src; im.alt = ''; t.appendChild(im); }
            const del = HOST.document.createElement('button');
            del.className = 'wall-del';
            del.textContent = '×';
            del.addEventListener('click', function () { list.splice(i, 1); commit(); draw(); });
            t.appendChild(del);
            wallsWrap.appendChild(t);
          });
          const add = HOST.document.createElement('button');
          add.className = 'btn sm';
          add.textContent = '+ 添加';
          add.addEventListener('click', function () {
            callAction('dialog.pickWallpaper', {}).then(function (up) {
              if (!up || !up.url) return;
              list.push({ src: up.url, type: isV(up.url) ? 'video' : 'image', name: up.filename });
              cfg.mode = 'wallpaper';
              commit();
              draw();
            }).catch(function () {});
          });
          wallsWrap.appendChild(add);
        }
        function commit() { cfg[key] = list; settingsSave(p.id, cfg); }
        draw();
        row.appendChild(wallsWrap);
      } else {
        const txt = HOST.document.createElement('input');
        txt.type = 'text';
        txt.value = cfg[key] || '';
        txt.addEventListener('change', function () { cfg[key] = txt.value; settingsSave(p.id, cfg); });
        row.appendChild(txt);
      }
      form.appendChild(row);
    });
  }

  function renderSettings() {
    const bodyEl = HOST.document.querySelector('[data-layer="settings"] .settings-body');
    if (!bodyEl) return;
    bodyEl.innerHTML = '';
    renderRailAppearance(bodyEl);
    const btnNormal = HOST.document.createElement('div');
    btnNormal.className = 'mode-row';
    const b = HOST.document.createElement('button');
    b.className = 'btn';
    b.textContent = '回到完整模式';
    b.addEventListener('click', function () {
      callAction('switch_to_normal', {}).then(function (d) { if (d && d.restart) HOST.alert('已切换为完整模式，请重启应用生效。'); }).catch(function () {});
    });
    btnNormal.appendChild(b);
    bodyEl.appendChild(btnNormal);
    groupState.plugins.forEach(function (p) {
      const base = {};
      (p.configSchema || []).forEach(function (f) { if (f.default !== undefined) base[f.key] = f.default; });
      const cfg = Object.assign({}, base, configByPlugin[p.id] || {});
      renderPluginCard(bodyEl, p, cfg);
    });
  }

  // ---- 配置持久化与下发 ----
  async function saveConfig() {
    const res = await fetch('/api/webmin/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plugins: configByPlugin }),
    });
    if (!res.ok) throw new Error(await res.text());
  }
  function applyConfigTo(pid) {
    const slot = slotOfPlugin(pid);
    const frame = slots(slot);
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ type: 'configApply', config: configByPlugin[pid] || {} }, '*');
    }
  }
  // 兼容：frames 用对象，保留原访问方式
  function slots(s) { return frames[s]; }

  async function ensureSessionId(sessionId) {
    if (sessionId) return sessionId;
    const created = await (await fetch('/api/sessions/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).json();
    if (created && created.id) {
      groupState.activeSessionId = created.id;
      await refreshSessions();
      updateEmpty();
      broadcastSessions('session.switched', { session_id: created.id });
      return created.id;
    }
    return '';
  }

  // ---- 本地 Electron 对话框 ----
  function pickPath(r) {
    if (!r) return null;
    if (Array.isArray(r)) return r[0] || null;
    if (Array.isArray(r.filePaths)) return r.filePaths[0] || null;
    if (Array.isArray(r.paths)) return r.paths[0] || null;
    if (typeof r === 'string') return r;
    if (typeof r.path === 'string') return r.path;
    return null;
  }

  // ---- 动作分发：宿主直接处理 ----
  async function dispatch(actionId, payload, origin) {
    payload = payload || {};
    switch (actionId) {
      case 'chat.send': {
        let sessionId = await ensureSessionId(payload.session_id || groupState.activeSessionId);
        if (!sessionId) throw new Error('无法创建会话');
        groupState.activeSessionId = sessionId;
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: payload.message || '' }),
        });
        if (!res.ok) throw new Error(await res.text());
        setEmpty(false);
        // 乐观本地即时显示用户消息，随后 fetch 同步（后端异步写入，fetch 慢时也不丢"你好"）
        if (payload.message) broadcast('conversation', 'conversation.local', { session_id: sessionId, events: [{ role: 'user', content: String(payload.message) }] });
        refreshSessions().then(updateEmpty);   // 更新 messages_count，维持 empty 状态准确
        broadcastSessions('conversation.updated', { session_id: sessionId });
        return await res.json();
      }
      case 'chat.sendBatch': {
        let sessionId = await ensureSessionId(payload.session_id || groupState.activeSessionId);
        if (!sessionId) throw new Error('无法创建会话');
        groupState.activeSessionId = sessionId;
        const res = await fetch('/api/chat/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, events: payload.events || [] }),
        });
        if (!res.ok) throw new Error(await res.text());
        setEmpty(false);
        // 乐观本地即时显示 type=user 的事件，随后 fetch 同步去重
        const uv = Array.isArray(payload.events) ? payload.events.filter((e) => e && e.type === 'user').map((e) => ({ role: 'user', content: String(e.content || '') })) : [];
        if (uv.length) broadcast('conversation', 'conversation.local', { session_id: sessionId, events: uv });
        refreshSessions().then(updateEmpty);
        broadcastSessions('conversation.updated', { session_id: sessionId });
        return await res.json();
      }
      case 'sessions.list': {
        const list = await (await fetch('/api/sessions')).json();
        groupState.sessions = list || [];
        updateEmpty();
        return groupState.sessions;
      }
      case 'sessions.new': {
        const res = await (await fetch('/api/sessions/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).json();
        if (res && res.id) { groupState.activeSessionId = res.id; await refreshSessions(); updateEmpty(); broadcastSessions('session.switched', { session_id: res.id }); }
        return res;
      }
      case 'session.switch': {
        if (payload.session_id) { groupState.activeSessionId = payload.session_id; await refreshSessions(); updateEmpty(); broadcastSessions('session.switched', { session_id: payload.session_id }); }
        return { status: 'ok' };
      }
      case 'chat.interrupt':
        return (await fetch('/api/chat/interrupt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })).json();
      // ---- 浮动卡片原语：宿主不关心具体插件，只对"调用方所在 slot"做通用移动/关闭 ----
      case 'slot.move': {
        const slot = origin && origin.slot;
        if (!slot) throw new Error('缺少调用方 slot');
        const el = HOST.document.querySelector(`[data-slot="${slot}"]`);
        if (el && (payload.dx || payload.dy)) {
          const r = el.getBoundingClientRect();
          const w = el.offsetWidth, h = el.offsetHeight;
          el.style.right = 'auto';
          el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r.left + (Number(payload.dx) || 0))) + 'px';
          el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r.top + (Number(payload.dy) || 0))) + 'px';
        }
        return { status: 'ok' };
      }
      case 'slot.close': {
        const slot = origin && origin.slot;
        const dd = pluginBySlot[slot];
        if (dd) setPluginHidden(dd.id, true);   // 走既有显隐机制，图标栏可重新唤出
        return { status: 'ok' };
      }
      // ---- 配置 ----
      case 'config.get':
        return configByPlugin[payload.plugin_id] || {};
      case 'config.set': {
        const pid = payload.plugin_id;
        if (!pid) throw new Error('缺少 plugin_id');
        configByPlugin[pid] = Object.assign({}, configByPlugin[pid], payload.config || {});
        // 先实时下发到目标插件（透明度热加载），再持久化；写盘失败不阻断视觉更新
        applyConfigTo(pid);
        broadcast('settings', 'config.updated', { plugin_id: pid, config: configByPlugin[pid] });
        await saveConfig();
        return configByPlugin[pid];
      }
      case 'settings.meta':
        return { plugins: groupState.plugins, config: configByPlugin };
      case 'settings.open':
        setSettingsOpen(true); return { status: 'ok' };
      case 'settings.close':
        setSettingsOpen(false); return { status: 'ok' };
      // ---- 引用 ----
      case 'dialog.files': {
        if (!HOST.purrcat) throw new Error('本地文件选择仅在 Electron 内可用');
        return HOST.purrcat.openDialog({ properties: ['openFile', 'multiSelections'] });
      }
      case 'dialog.folder': {
        if (!HOST.purrcat) throw new Error('本地文件夹选择仅在 Electron 内可用');
        return HOST.purrcat.openDialog({ properties: ['openDirectory'] });
      }
      case 'dialog.pickWallpaper': {
        if (!HOST.purrcat) throw new Error('本地壁纸选择仅在 Electron 内可用');
        const r = await HOST.purrcat.openDialog({ properties: ['openFile'], filters: [{ name: 'Walls', extensions: ['png','jpg','jpeg','gif','webp','bmp','mp4','webm','mov'] }] });
        const p = pickPath(r);
        if (!p) return null;
        const up = await (await fetch('/api/webmin/wallpaper', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: p }) })).json();
        return up;
      }
      case 'plugin.delete': {
        if (!payload.plugin_id) throw new Error('缺少 plugin_id');
        const res = await fetch(`/api/webmin/plugin/${encodeURIComponent(payload.plugin_id)}/delete`, { method: 'POST' });
        if (!res.ok) throw new Error((await res.text()) || '删除失败');
        await reloadManifest();
        return { status: 'ok' };
      }
      case 'ref.graphs':
        return (await fetch('/api/webmin/ref/graphs')).json();
      // ---- 插件自带后端 RPC ----
      case 'plugin.rpc': {
        const pid = payload.plugin_id;
        if (!pid) throw new Error('缺少 plugin_id');
        const res = await fetch(`/api/webmin/plugin-rpc/${encodeURIComponent(pid)}/${encodeURIComponent(payload.handler || '')}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ payload: payload.payload || {}, timeout: payload.timeout }),
        });
        if (!res.ok) throw new Error((await res.text()) || '插件后端调用失败');
        return (await res.json()).result;
      }
      case 'state.get':
        return { ...groupState, plugins: undefined };
      // 输入插件展开引用菜单时，宿主腾出更高输入区，避免面板被容器裁切
      case 'input.dropdown':
        HOST.document.body.classList.toggle('input-menu', !!payload.open);
        return { status: 'ok' };
      default:
        return null;
    }
  }

  // ---- 命令入口 ----
  async function callAction(actionId, payload, origin) {
    if (actionId === 'switch_to_normal') {
      const res = await fetch('/api/webmin/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actionId, payload: payload || {} }) });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data && data.restart) HOST.alert('已切换为完整模式，请重启应用生效。');
      return data;
    }
    return dispatch(actionId, payload, origin);
  }

  // ---- 广播事件到某 slot ----
  function broadcast(slot, event, data) {
    const frame = frames[slot];
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ type: 'event', event, data: data || {} }, '*');
    }
  }

  // ---- 监听插件 iframe 消息 ----
  HOST.addEventListener('message', (e) => {
    const msg = e.data;
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'callAction') {
      const id = msg.id;
      // 从消息来源反查调用方 slot，据此界定原语作用对象（如 slot.move / slot.close）
      const srcSlot = Object.keys(frames).find((k) => frames[k].contentWindow === e.source) || null;
      const srcPlugin = srcSlot && pluginBySlot[srcSlot] ? pluginBySlot[srcSlot].id : null;
      const origin = { slot: srcSlot, pluginId: srcPlugin };
      callAction(msg.actionId, msg.payload, origin)
        .then((data) => { if (e.source) e.source.postMessage({ type: 'callActionResult', id, ok: true, data }, '*'); })
        .catch((err) => { if (e.source) e.source.postMessage({ type: 'callActionResult', id, ok: false, error: String(err) }, '*'); });
    }
  });

  // ---- 渲染：把某 slot 的插件装进对应 iframe ----
  function mountSlot(slot) {
    const desc = pluginBySlot[slot];
    const container = document.querySelector(`[data-slot="${slot}"]`);
    if (!container) return;
    container.querySelectorAll('iframe').forEach((f) => f.remove());
    if (!desc || !desc.entry) return;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('tabindex', '-1');
    iframe.src = `/api/webmin/plugin/${encodeURIComponent(desc.id)}/${desc.entry.split('/').map(encodeURIComponent).join('/')}`;
    iframe.title = desc.name || desc.id;
    container.appendChild(iframe);
    frames[slot] = iframe;
    // 注入该插件配置
    configByPlugin[desc.id] = effectiveConfig(desc);
    iframe.addEventListener('load', function onLoad() {
      applyConfigTo(desc.id);
      iframe.removeEventListener('load', onLoad);
    });
  }

  // ---- 刷新 manifest 并重挂载 ----
  async function loadManifest() {
    const manifest = await (await fetch('/api/webmin/manifest')).json();
    groupState.plugins = manifest.plugins || [];
    for (const slot of SLOTS) {
      pluginBySlot[slot] = groupState.plugins.find((p) => p.slot === slot) || null;
    }
  }
  async function reloadManifest() {
    await loadManifest();
    SLOTS.forEach(mountSlot);
    buildRail();
  }

  // ---- Electron 窗口控制 ----
  function wireWindowControls() {
    if (!HOST.purrcat) return;
    HOST.document.body.classList.add('electron');
    const byId = (id) => HOST.document.getElementById(id);
    if (byId('winMinimize')) byId('winMinimize').addEventListener('click', () => HOST.purrcat.winMinimize());
    if (byId('winMaximize')) byId('winMaximize').addEventListener('click', () => HOST.purrcat.winToggleMaximize());
    if (byId('winClose')) byId('winClose').addEventListener('click', () => HOST.purrcat.winClose());
  }

  // ---- 入口 ----
  async function boot() {
    wireWindowControls();
    // 设置面板关闭按钮
    const settingsClose = HOST.document.getElementById('settingsClose');
    if (settingsClose) settingsClose.addEventListener('click', () => setSettingsOpen(false));
    let manifest;
    try {
      manifest = await (await fetch('/api/webmin/manifest')).json();
    } catch (err) {
      HOST.document.body.innerHTML =
        '<div style="padding:24px;font-family:system-ui;color:#8b96a3">极简模式无法加载：后端未在线（/api/webmin/manifest 不可用）。请先启动后端。</div>';
      return;
    }
    groupState.plugins = manifest.plugins || [];
    // 读取图标栏持久化状态
    const railSaved = manifest.rail;
    if (railSaved && typeof railSaved === 'object') {
      const stage = Number(railSaved.stage);
      railState.stage = (stage >= 0 && stage < RAIL_STAGES) ? stage : 1;
      railState.hidden = (railSaved.hidden && typeof railSaved.hidden === 'object') ? railSaved.hidden : {};
      railState.opacity = (typeof railSaved.opacity === 'number') ? railSaved.opacity : 1;
    }
    applyRailOpacity();
    for (const slot of SLOTS) {
      pluginBySlot[slot] = groupState.plugins.find((p) => p.slot === slot) || null;
    }
    SLOTS.forEach(mountSlot);
    bindRailToggle();
    buildRail();
    // 应用持久化的插件隐藏状态（需在挂载后重设，避免被 iframe 覆盖样式）
    Object.keys(railState.hidden).forEach((id) => {
      const slot = slotOfPlugin(id);
      if (slot && railState.hidden[id]) applySlotHidden(slot, true);
    });

    try {
      const list = await (await fetch('/api/sessions')).json();
      if (Array.isArray(list) && list.length) {
        groupState.sessions = list;
        groupState.activeSessionId = list[0].id || '';
      }
    } catch (_) { /* 无会话时保持空 */ }
    updateEmpty();
  }

  // ---- 提供宿主侧脚本接口 ----
  HOST.purrcatWebmin = { callAction };

  if (HOST.document.readyState === 'loading') {
    HOST.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();