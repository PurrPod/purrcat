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

  // --- 状态 ---
  // slot 仅声明「窗口类型」，由各插件 plugin.json 的 slot 动态建立，host 不再写死槽位表：
  //   * fixed  —— 锚定单例，同 area 只取第一个插件生效（input/conversation/sidebar/background）
  //   * panel  —— 与聊天区并排的分栏面板：无面板插件则不占位；有则在右上角抽屉里切换显示
  //   * float  —— 弹窗，多插件各自独立、可拖拽可缩放
  //   slotMap[slotId]      -> 声明该窗口的插件列表
  //   pluginBySlot[slotId] -> slot -> primary descriptor（兼容既有读取点）
  //   frames[slotId]       -> slot -> [ {iframe, pluginId, el} ]
  //   slotByPluginId / frameByPluginId -> 由插件反查其所在槽/实例
  const slotMap = {};
  const pluginBySlot = {};
  let frames = {};
  const configByPlugin = {};  // plugin_id -> 有效配置（默认值 ∪ 已存值）
  const slotByPluginId = {};  // plugin_id -> slotId
  const frameByPluginId = {}; // plugin_id -> iframe element
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
    // fixed：锚定容器
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (anchor) anchor.style.display = hidden ? 'none' : '';
    if (slot === 'sidebar') HOST.document.body.classList.toggle('rail-nosidebar', !!hidden);
    // float：弹窗实例（data-fslot=slot）
    HOST.document.querySelectorAll(`.wm-float[data-fslot="${slot}"]`).forEach((el) => {
      el.style.display = hidden ? 'none' : 'block';
    });
    // panel：内容插件驻宿主单例容器（data-pslot=panel），隐藏/显示容器并切换让位
    if (slot === 'panel') {
      HOST.document.querySelectorAll('.wm-ppanel[data-pslot="panel"]').forEach((el) => {
        el.style.display = hidden ? 'none' : 'flex';
      });
      if (hidden) { HOST.document.body.classList.remove('has-panels'); if (panelBar) panelBar.style.display = 'none'; }
      else { HOST.document.body.classList.add('has-panels'); if (panelBar) panelBar.style.display = ''; }
    }
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
    groupState.plugins
      .filter(isRailPlugin)
      .filter((p) => (p.slotDef || {}).type !== 'panel')   // panel 内容插件不进白条，由下方「面板容器」开关统辖
      .forEach((p) => {
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
    // 面板容器开关（宿主固有资产，非插件）：存在 type=panel 内容插件时才显示，控制中栏容器的显隐
    if (hasPanelsDef()) {
      const cb = HOST.document.createElement('button');
      cb.className = 'rail-ico';
      cb.title = '面板容器';
      const cg = HOST.document.createElement('span');
      cg.className = 'rail-glyph';
      cg.textContent = '▦';
      cb.appendChild(cg);
      const cnm = HOST.document.createElement('span');
      cnm.className = 'rail-name';
      cnm.textContent = '面板容器';
      cb.appendChild(cnm);
      updateContainerRail(cb);
      railButtons['__panel__'] = cb;
      cb.addEventListener('click', () => {
        setContainerHidden(!railHidden('__panel__'));
        updateContainerRail(cb);
      });
      iconsEl.appendChild(cb);
    }
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
    return slotByPluginId[pid] || null;
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

  // 中栏容器为宿主固有资产（非插件）：设置内提供透明度 + 默认宽度；配置存到"面板容器"键
  function settingsSavePanel() {
    configByPlugin['panel-container'] = Object.assign({}, panelContainerCfg);
    applyPanelContainerCfg();
    saveConfig().catch(() => {});
  }
  function renderPanelContainerSettings(container) {
    const box = HOST.document.createElement('div');
    box.className = 'plugin';
    const head = HOST.document.createElement('div');
    head.className = 'p-head';
    const nm = HOST.document.createElement('span');
    nm.className = 'p-name';
    nm.textContent = '面板容器';
    head.appendChild(nm);
    const tag = HOST.document.createElement('span');
    tag.className = 'p-tag';
    tag.textContent = 'system';
    head.appendChild(tag);
    box.appendChild(head);
    const sep = HOST.document.createElement('div');
    sep.className = 'p-sep';
    box.appendChild(sep);
    const form = HOST.document.createElement('div');

    // 透明度
    const rowO = HOST.document.createElement('div');
    rowO.className = 'field';
    const labO = HOST.document.createElement('label');
    labO.textContent = '透明度';
    rowO.appendChild(labO);
    const rng = HOST.document.createElement('input');
    rng.type = 'range';
    rng.min = 0.15;
    rng.max = 1;
    rng.step = 0.05;
    rng.style.width = '100%';
    const o = Number(panelContainerCfg.opacity);
    rng.value = (o >= 0.15 && o <= 1) ? o : 0.9;
    const valEl = HOST.document.createElement('div');
    valEl.className = 'range-val';
    function upd() { valEl.textContent = '透明度 ' + Number(rng.value).toFixed(2); }
    rng.addEventListener('input', function () {
      panelContainerCfg.opacity = Number(rng.value);
      applyPanelContainerCfg();
      settingsSavePanel();
      upd();
    });
    upd();
    rowO.appendChild(rng);
    rowO.appendChild(valEl);
    form.appendChild(rowO);

    // 默认宽度
    const rowW = HOST.document.createElement('div');
    rowW.className = 'field';
    const labW = HOST.document.createElement('label');
    labW.textContent = '默认宽度 (px)';
    rowW.appendChild(labW);
    const num = HOST.document.createElement('input');
    num.type = 'number';
    num.min = 260;
    num.max = 700;
    num.step = 10;
    num.value = Number(panelContainerCfg.width) || 380;
    num.style.width = '100%';
    num.addEventListener('change', function () {
      const w = Number(num.value);
      if (w >= 260 && w <= 700) {
        panelContainerCfg.width = w;
        settingsSavePanel();
      }
    });
    rowW.appendChild(num);
    form.appendChild(rowW);

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
    renderPanelContainerSettings(bodyEl);
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
    const iframe = frameByPluginId[pid];
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage({ type: 'configApply', config: configByPlugin[pid] || {} }, '*');
    }
  }
  // 兼容：frames 用对象，保留原访问方式（值为该 slot 的实例数组）
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
      // ---- 浮层原语：宿主只认"调用方所属实例"，做通用移动/关闭（不感知具体插件；many 槽各实例独立） ----
      case 'slot.move': {
        const el = origin && origin.inst;
        if (!el) throw new Error('缺少调用方实例');
        if (payload.dx || payload.dy) {
          const r = el.getBoundingClientRect();
          const w = el.offsetWidth, h = el.offsetHeight;
          el.style.right = 'auto';
          el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r.left + (Number(payload.dx) || 0))) + 'px';
          el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r.top + (Number(payload.dy) || 0))) + 'px';
        }
        return { status: 'ok' };
      }
      case 'slot.close': {
        const el = origin && origin.inst;
        if (el) el.style.display = 'none';   // 只隐藏调用方实例
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
    (frames[slot] || []).forEach((f) => {
      if (f.iframe && f.iframe.contentWindow) {
        f.iframe.contentWindow.postMessage({ type: 'event', event, data: data || {} }, '*');
      }
    });
  }

  // ---- 监听插件 iframe 消息 ----
  HOST.addEventListener('message', (e) => {
    const msg = e.data;
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'callAction') {
      const id = msg.id;
      // 从消息来源反查调用方所在 slot 及其具体实例，据此界定原语作用对象（如 slot.move / slot.close）
      let srcSlot = null, srcFrame = null;
      Object.keys(frames).forEach((k) => {
        (frames[k] || []).forEach((f) => {
          if (f.iframe && f.iframe.contentWindow === e.source) { srcSlot = k; srcFrame = f; }
        });
      });
      const srcPlugin = srcFrame ? srcFrame.pluginId : null;
      const origin = { slot: srcSlot, pluginId: srcPlugin, inst: srcFrame ? srcFrame.el : null };
      callAction(msg.actionId, msg.payload, origin)
        .then((data) => { if (e.source) e.source.postMessage({ type: 'callActionResult', id, ok: true, data }, '*'); })
        .catch((err) => { if (e.source) e.source.postMessage({ type: 'callActionResult', id, ok: false, error: String(err) }, '*'); });
    }
  });

  // ---- 通用拖拽/缩放（type=float 弹窗：多插件各自独立、宿主只操作容器几何） ----
  function startFloatDrag(el, e) {
    e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    const move = (ev) => {
      el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r0.left + (ev.clientX - sx))) + 'px';
      el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r0.top + (ev.clientY - sy))) + 'px';
      el.style.right = 'auto';
    };
    const up = () => { HOST.removeEventListener('pointermove', move); HOST.removeEventListener('pointerup', up); };
    HOST.addEventListener('pointermove', move); HOST.addEventListener('pointerup', up);
  }
  function startFloatResize(el, e) {
    e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    const move = (ev) => {
      el.style.width = Math.max(160, r0.width + (ev.clientX - sx)) + 'px';
      el.style.height = Math.max(160, r0.height + (ev.clientY - sy)) + 'px';
    };
    const up = () => { HOST.removeEventListener('pointermove', move); HOST.removeEventListener('pointerup', up); };
    HOST.addEventListener('pointermove', move); HOST.addEventListener('pointerup', up);
  }
  // float 类型天然可拖拽可缩放：总会补上两个手柄（宿主不感知具体插件）
  function attachFloatHandles(el) {
    el.querySelectorAll('.wm-fgrab, .wm-fresize').forEach((hd) => hd.remove());
    const g = HOST.document.createElement('div');
    g.className = 'wm-fgrab';
    g.title = '拖动';
    g.addEventListener('pointerdown', (e) => startFloatDrag(el, e));
    el.appendChild(g);
    const r = HOST.document.createElement('div');
    r.className = 'wm-fresize';
    r.title = '缩放';
    r.addEventListener('pointerdown', (e) => startFloatResize(el, e));
    el.appendChild(r);
  }

  // ---- panel-container：宿主系统级单例中栏容器，非弹窗。容纳全部 type=panel
  //     内容插件，右上角抽屉切换显示；宽度由中栏右缘分隔条拖动调整（--wm-panel-w）。
  let panelBar = null;             // 中栏与聊天区之间的纵向分隔条
  let panelState = null;           // 单例：{ plugins:[{p,def}], activeId, el, area:'panel' }
  let panelContainerCfg = { opacity: 0.9, width: 380 }; // 宿主固有中栏容器配置（透明度/默认宽度）
  function applyPanelContainerCfg() {
    const el = HOST.document.querySelector('.wm-ppanel[data-pslot="panel"]');
    if (!el) return;
    let o = Number(panelContainerCfg.opacity);
    if (!(o >= 0)) o = 0.9;
    o = Math.min(1, Math.max(0.15, o));
    el.style.setProperty('--wm-panel-bg', 'rgba(242,244,247,' + o.toFixed(3) + ')');
    const w = Number(panelContainerCfg.width);
    if (w >= 260) {   // 只保下限，不设最大宽度，面板可尽量舒展
      HOST.document.documentElement.style.setProperty('--wm-panel-w', w + 'px');
    }
  }
  function cssNum(name, dflt) {
    const v = HOST.getComputedStyle(HOST.document.documentElement).getPropertyValue(name);
    const n = parseFloat(v);
    return (n >= 0) ? n : dflt;
  }
  // 面板容器「最大舒展」宽度：面板占满左侧栏右侧全部，右侧留出固定聊天列（--wm-chat-w）
  function maxPanelWidth() {
    const rail = cssNum('--wm-rail-w', 48);
    const gap = cssNum('--wm-sidebar-gap', 8);
    const side = cssNum('--wm-sidebar-w', 264);
    const chat = cssNum('--wm-chat-w', 420);
    const noSidebar = HOST.document.body.classList.contains('rail-nosidebar');
    const left = noSidebar ? (rail + gap) : (rail + gap + side + gap);
    return Math.max(260, Math.floor(HOST.innerWidth - left - gap - chat));
  }
  function setContainerHidden(hidden) {
    if (!railState.hidden) railState.hidden = {};
    if (hidden) railState.hidden['__panel__'] = true; else delete railState.hidden['__panel__'];
    applySlotHidden('panel', hidden);
    updateContainerRail();
    persistRail().catch(() => {});
  }
  function updateContainerRail(btnOverride) {
    const btn = btnOverride || railButtons['__panel__'];
    if (!btn) return;
    btn.classList.remove('on', 'off');
    btn.classList.add(railHidden('__panel__') ? 'off' : 'on');
  }
  function hasPanelsDef() {
    return Object.keys(slotMap).some((sid) => (slotMap[sid][0].slotDef || {}).type === 'panel');
  }
  function startPanelBarDrag(e) {
    e.preventDefault();
    const el = e.currentTarget;   // 分隔条
    const w0 = HOST.document.documentElement.style.getPropertyValue('--wm-panel-w');
    const base = w0 ? parseFloat(w0) : 420;
    const sx0 = e.clientX;
    const move = (ev) => {
      const w = Math.max(260, base + (ev.clientX - sx0));   // 只保下限，不设最大宽度
      HOST.document.documentElement.style.setProperty('--wm-panel-w', w + 'px');
    };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      try { el.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    // 指针捕获：按住期间持续收到事件，光标移出/甩动也不脱手；松开时释放
    try { el.setPointerCapture(e.pointerId); } catch (_) {}
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }
  function reconcilePanels() {
    if (hasPanelsDef()) {
      HOST.document.body.classList.add('has-panels');
      // 未拖动过：中栏默认宽度 = 最大舒展（右侧留出聊天列）
      if (!HOST.document.documentElement.style.getPropertyValue('--wm-panel-w')) {
        HOST.document.documentElement.style.setProperty('--wm-panel-w', maxPanelWidth() + 'px');
      }
      if (!panelBar || !panelBar.isConnected) {
        panelBar = HOST.document.createElement('div');
        panelBar.className = 'wm-pbar';
        panelBar.title = '拖动以调整中栏宽度';
        panelBar.addEventListener('pointerdown', startPanelBarDrag);
        HOST.document.body.appendChild(panelBar);
      }
    } else {
      HOST.document.body.classList.remove('has-panels');
      if (panelBar && panelBar.isConnected) panelBar.remove();
    }
  }

  // 关闭面板右上角抽屉下拉
  function closePanelMenus() {
    HOST.document.querySelectorAll('.wm-pp_menu').forEach((m) => m.remove());
  }
  // panel 内容区重建：标题 + 抽屉 + 当前选中插件 iframe（切换即在容器内卸载旧图挂新图）
  function renderPanelContent(st) {
    const el = st.el;
    el.innerHTML = '';
    const cur = st.plugins.find((x) => x.p.id === st.activeId) || null;   // 支持 none：不选中任意插件时显示空面板
    const head = HOST.document.createElement('div');
    head.className = 'wm-pp_head';
    // ☰ 抽屉放左上角：切换面板插件
    const dbtn = HOST.document.createElement('button');
    dbtn.className = 'wm-pp_drawer';
    dbtn.textContent = '☰';
    dbtn.title = '切换面板插件';
    dbtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const open = HOST.document.getElementById('ppmenu-' + st.area);
      closePanelMenus();
      if (open) return;
      const menu = HOST.document.createElement('div');
      menu.className = 'wm-pp_menu';
      menu.id = 'ppmenu-' + st.area;
      // 「无」：选择后不显示任何面板插件
      const noneItem = HOST.document.createElement('div');
      noneItem.className = 'wm-pp_menu-item' + (!cur ? ' active' : '');
      const ng = HOST.document.createElement('span');
      ng.className = 'wm-pp_menu-ico';
      ng.textContent = '—';
      noneItem.appendChild(ng);
      const nn = HOST.document.createElement('span');
      nn.textContent = '无';
      noneItem.appendChild(nn);
      noneItem.addEventListener('click', () => {
        st.activeId = '__none__';
        renderPanelContent(st);
        closePanelMenus();
      });
      menu.appendChild(noneItem);
      st.plugins.forEach(({ p }) => {
        const item = HOST.document.createElement('div');
        item.className = 'wm-pp_menu-item' + (p.id === st.activeId ? ' active' : '');
        const g = HOST.document.createElement('span');
        g.className = 'wm-pp_menu-ico';
        g.textContent = p.icon || (p.name || p.id || '?').charAt(0);
        item.appendChild(g);
        const nm = HOST.document.createElement('span');
        nm.textContent = p.name || p.id;
        item.appendChild(nm);
        item.addEventListener('click', () => {
          st.activeId = p.id;
          renderPanelContent(st);
          closePanelMenus();
        });
        menu.appendChild(item);
      });
      HOST.document.body.appendChild(menu);
      const r = dbtn.getBoundingClientRect();
      menu.style.right = 'auto';
      menu.style.left = Math.max(8, r.right - menu.offsetWidth) + 'px';
      menu.style.top = (r.bottom + 4) + 'px';
    });
    head.appendChild(dbtn);
    // ✕ 关闭按钮放右上角：关闭面板容器
    const closeBtn = HOST.document.createElement('button');
    closeBtn.className = 'wm-pp_drawer';
    closeBtn.textContent = '✕';
    closeBtn.title = '关闭面板';
    closeBtn.addEventListener('click', () => {
      if (st.el) st.el.style.display = 'none';
      HOST.document.body.classList.remove('has-panels');
      if (panelBar) panelBar.style.display = 'none';
      closePanelMenus();
    });
    head.appendChild(closeBtn);
    el.appendChild(head);
    const body = HOST.document.createElement('div');
    body.className = 'wm-pp_body';
    el.appendChild(body);
    for (const k in frames) if (k === 'panel') delete frames[k];
    if (cur) {
      const fr = mountFrame(body, cur.p, cur.def);
      if (fr) frames[cur.p.slot] = [fr];
    } else {
      // 「无」状态：容器保留但内容区为占位提示
      const ph = HOST.document.createElement('div');
      ph.className = 'wm-pp_empty';
      ph.textContent = '未选择面板插件';
      body.appendChild(ph);
    }
  }
  // 挂载 type=panel 插件：无面板插件则不占位；有则建 .wm-ppanel 并点亮抽屉
  function mountPanels() {
    // 收集全部 type=panel 内容插件进单例中栏容器
    const byArea = { panel: [] };
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type === 'panel') {
        byArea.panel.push(...list.map((p) => ({ p, def })));
      }
    });
    // 无 panel 插件：移除容器与状态
    if (!byArea.panel.length) {
      if (panelState && panelState.el && panelState.el.parentNode) panelState.el.remove();
      panelState = null;
      closePanelMenus();
      return;
    }
    let st = panelState;
    if (!st) {
      st = panelState = { plugins: byArea.panel, activeId: byArea.panel[0].p.id, area: 'panel', el: null };
    } else {
      st.plugins = byArea.panel;
      if (!byArea.panel.some((x) => x.p.id === st.activeId)) st.activeId = byArea.panel[0].p.id;
    }
    if (!st.el || !st.el.parentNode) {
      st.el = HOST.document.createElement('div');
      st.el.className = 'wm-ppanel wm-mount';
      st.el.dataset.pslot = 'panel';
      st.el.style.display = 'flex';
      HOST.document.body.appendChild(st.el);
    }
    renderPanelContent(st);
    closePanelMenus();
  }

  // ---- 渲染：把某插件实例装进对应容器内的 iframe ----
  function mountFrame(el, p) {
    el.querySelectorAll('iframe').forEach((f) => f.remove());
    el.querySelectorAll('.wm-fgrab, .wm-fresize').forEach((h) => h.remove());
    if (!p || !p.entry) return null;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('tabindex', '-1');
    iframe.src = `/api/webmin/plugin/${encodeURIComponent(p.id)}/${p.entry.split('/').map(encodeURIComponent).join('/')}`;
    iframe.title = p.name || p.id;
    el.appendChild(iframe);
    configByPlugin[p.id] = effectiveConfig(p);
    slotByPluginId[p.id] = p.slot;
    frameByPluginId[p.id] = iframe;
    iframe.addEventListener('load', function onLoad() {
      applyConfigTo(p.id);
      iframe.removeEventListener('load', onLoad);
    });
    return { iframe, pluginId: p.id, el };
  }

  // ---- 依据 manifest 的 slot 声明建立槽集合（去硬编码） ----
  function buildSlotIndex() {
    // 清理已挂载的动态实例浮层（保留 html 里的锚定容器）
    Object.keys(frames).forEach((k) => {
      (frames[k] || []).forEach((f) => { if (f.el && f.el.parentNode && !f.el.hasAttribute('data-layer')) f.el.remove(); });
    });
    Object.keys(slotMap).forEach((k) => delete slotMap[k]);
    Object.keys(pluginBySlot).forEach((k) => delete pluginBySlot[k]);
    Object.keys(slotByPluginId).forEach((k) => delete slotByPluginId[k]);
    Object.keys(frameByPluginId).forEach((k) => delete frameByPluginId[k]);
    frames = {};
    groupState.plugins.forEach((p) => {
      const s = p.slot;
      if (!s) return;
      (slotMap[s] = slotMap[s] || []).push(p);
    });
  }

  // ---- 动态挂载全部类型窗口（type：fixed 锚定单例 / panel 分栏抽屉 / float 弹窗多开） ----
  function mountAll() {
    // 1) fixed：按 area 挂到 html 锚定容器，同 area 只取第一个生效
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'fixed') return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      const mainEl = HOST.document.querySelector(`[data-slot="${sid}"]`);
      if (!mainEl) return;
      const p = list[0];
      slotByPluginId[p.id] = sid;
      const fr = mountFrame(mainEl, p);
      if (fr) frames[sid].push(fr);
    });
    // 2) panel：无面板插件则不占位；有则建 .wm-ppanel（右上角抽屉切换）
    mountPanels();
    // 3) float：每个插件一个独立 .wm-float，可拖拽可缩放
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'float') return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      list.forEach((p, i) => {
        const el = HOST.document.createElement('div');
        el.className = 'wm-float wm-mount';
        el.dataset.fslot = sid;
        el.dataset.finst = String(i);
        el.style.top = 46 + i * 26 + 'px';
        el.style.left = `calc(100% - ${300 + i * 26}px - 16px)`;
        HOST.document.body.appendChild(el);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(el, p);
        if (fr) frames[sid].push(fr);
        attachFloatHandles(el);
      });
    });
    reconcilePanels();
  }

  // ---- 刷新 manifest 并重建/挂载 ----
  async function loadManifest() {
    const manifest = await (await fetch('/api/webmin/manifest')).json();
    groupState.plugins = manifest.plugins || [];
  }
  async function reloadManifest() {
    await loadManifest();
    buildSlotIndex();
    mountAll();
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
    panelContainerCfg = Object.assign({ opacity: 0.9 }, manifest.panelContainer || {});
    // 默认宽度 = 最大舒展；仅当用户在设置里保存了显式宽度时才沿用该值
    if (!(Number(panelContainerCfg.width) >= 260)) panelContainerCfg.width = maxPanelWidth();
    buildSlotIndex();
    mountAll();
    bindRailToggle();
    buildRail();
    applyPanelContainerCfg();
    // 应用持久化的插件隐藏状态（需在挂载后重设，避免被 iframe 覆盖样式）
    Object.keys(railState.hidden).forEach((id) => {
      const slot = slotOfPlugin(id);
      if (slot && railState.hidden[id]) applySlotHidden(slot, true);
    });
    // 面板容器独立于插件隐藏态之外，单独持久化在 rail.hidden['__panel__']
    if (railState.hidden && railState.hidden['__panel__']) {
      applySlotHidden('panel', true);
    }

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