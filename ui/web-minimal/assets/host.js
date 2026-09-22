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
  const SLOTS = ['pet', 'sidebar', 'history', 'input', 'background', 'conversation', 'settings'];

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
  // 最左图标栏状态：stage 0=收起(仅开关) 1=仅图标 2=图标+名称(左侧栏)；hidden=各插件隐藏开关（持久化）
  const railState = { stage: 1, hidden: {} };

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
      t.textContent = railState.stage === 2 ? '▤' : (railState.stage === 1 ? '☰' : '≡');
      t.title = railState.stage === 2 ? '收为图标栏' : (railState.stage === 1 ? '展开为左侧栏' : '展开图标栏');
    }
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
  function buildRail() {
    const iconsEl = HOST.document.getElementById('railIcons');
    if (!iconsEl) return;
    applyRailStage();
    iconsEl.innerHTML = '';
    groupState.plugins.filter(isRailPlugin).forEach((p) => {
      const btn = HOST.document.createElement('button');
      btn.className = 'rail-ico' + (p.railAction ? ' on' : (railHidden(p.id) ? ' off' : ' on'));
      btn.title = (p.name || p.id);
      const g = HOST.document.createElement('span');
      g.className = 'rail-glyph';
      g.textContent = railIcon(p);
      btn.appendChild(g);
      const nm = HOST.document.createElement('span');
      nm.className = 'rail-name';
      nm.textContent = p.name || p.id;
      btn.appendChild(nm);
      btn.addEventListener('click', () => {
        if (p.railAction) { callAction(p.railAction, {}).catch(() => {}); return; }  // 例如设置 → 打开设置面板
        setPluginHidden(p.id, !railHidden(p.id));
      });
      iconsEl.appendChild(btn);
    });
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

  // ---- 设置面板开合 ----
  function setSettingsOpen(open) {
    HOST.document.body.classList.toggle('settings-open', !!open);
    if (open) broadcast('settings', 'settings.opened', { plugins: groupState.plugins });
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
    const created = await (await fetch('/api/sessions/new', { method: 'POST' })).json();
    if (created && created.id) {
      groupState.activeSessionId = created.id;
      broadcast('conversation', 'session.switched', { session_id: created.id });
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
  async function dispatch(actionId, payload) {
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
        broadcast('conversation', 'conversation.updated', { session_id: sessionId });
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
        broadcast('conversation', 'conversation.updated', { session_id: sessionId });
        return await res.json();
      }
      case 'sessions.list': {
        const list = await (await fetch('/api/sessions')).json();
        groupState.sessions = list || [];
        updateEmpty();
        return groupState.sessions;
      }
      case 'sessions.new': {
        const res = await (await fetch('/api/sessions/new', { method: 'POST' })).json();
        if (res && res.id) { groupState.activeSessionId = res.id; updateEmpty(); broadcast('conversation', 'session.switched', { session_id: res.id }); }
        return res;
      }
      case 'session.switch': {
        if (payload.session_id) { groupState.activeSessionId = payload.session_id; updateEmpty(); broadcast('conversation', 'session.switched', { session_id: payload.session_id }); }
        return { status: 'ok' };
      }
      case 'chat.interrupt':
        return (await fetch('/api/chat/interrupt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })).json();
      // ---- 配置 ----
      case 'config.get':
        return configByPlugin[payload.plugin_id] || {};
      case 'config.set': {
        const pid = payload.plugin_id;
        if (!pid) throw new Error('缺少 plugin_id');
        configByPlugin[pid] = Object.assign({}, configByPlugin[pid], payload.config || {});
        await saveConfig();
        applyConfigTo(pid);
        broadcast('settings', 'config.updated', { plugin_id: pid, config: configByPlugin[pid] });
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
      default:
        return null;
    }
  }

  // ---- 命令入口 ----
  async function callAction(actionId, payload) {
    if (actionId === 'switch_to_normal') {
      const res = await fetch('/api/webmin/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actionId, payload: payload || {} }) });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data && data.restart) HOST.alert('已切换为完整模式，请重启应用生效。');
      return data;
    }
    return dispatch(actionId, payload);
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
      callAction(msg.actionId, msg.payload)
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
    if (slot !== 'settings') {
      // 非 settings slot：铺满 iframe；settings 由宿主内部结构承载
    }
    if (!desc || !desc.entry) return;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('tabindex', '-1');
    iframe.src = `/api/webmin/plugin/${encodeURIComponent(desc.id)}/${desc.entry.split('/').map(encodeURIComponent).join('/')}`;
    iframe.title = desc.name || desc.id;
    const holder = slot === 'settings' ? container.querySelector('.settings-body') : container;
    holder.appendChild(iframe);
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
    }
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