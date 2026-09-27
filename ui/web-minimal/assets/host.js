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
  // 单例槽当前选中的插件（fixed: {area: plugin_id}；panel 容器: {panel: plugin_id|'__none__'}）。
  // 由后端 webminConfig.active 持久化，重启后恢复用户上次的选择。
  const activeBySlot = {};

  // ---- 图标集（宿主内置内联 SVG 线性图标，描边跟随 currentColor）----
  // 插件在 plugin.json 的 icon 写这里登记的名字即可；也可内嵌自己的 <svg>…</svg>；
  // 写其它任意字符则按文本字形渲染（兼容只给字符的老插件）。尺寸由宿主 CSS 统一控制。
  const ICON_SVG = {
    list: '<path d="M3 6h.01M3 12h.01M3 18h.01"/><path d="M8 6h13M8 12h13M8 18h13"/>',
    pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    'panel-left': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
    'layout-panel-left': '<rect width="7" height="18" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  };
  const ICON_SVG_ATTR = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"';
  // 把 icon 画进容器：登记名 → 内置 SVG；<svg> → 去脚本后原样内嵌；其它 → 文本字形
  function paintIcon(el, icon, fallbackChar) {
    const raw = String(icon == null ? '' : icon).trim();
    if (/^<svg[\s>]/i.test(raw)) {
      el.innerHTML = raw.replace(/<script[\s\S]*?<\/script>/gi, '');
      return;
    }
    if (ICON_SVG[raw]) {
      el.innerHTML = '<svg ' + ICON_SVG_ATTR + '>' + ICON_SVG[raw] + '</svg>';
      return;
    }
    el.textContent = raw || fallbackChar || '';
  }
  function paintPluginIcon(el, p) {
    const nm = (p && (p.name || p.id)) || '?';
    paintIcon(el, p && p.icon, (nm.charAt(0) || '?').toUpperCase());
  }

  // ---- 图标栏（固定组件）----
  const RAIL_STAGES = 3;
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
  // 持久化单例槽选中项（分节更新，不影响 plugins/rail）
  function persistActive() {
    return fetch('/api/webmin/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: activeBySlot }),
    }).then((res) => { if (!res.ok) throw new Error(res.status); }).catch(() => {});
  }
  // 应用持久化的隐藏状态（挂载后调用：fixed 锚定区 / float 实例 / panel 容器）
  function applyPersistedHidden() {
    Object.keys(railState.hidden).forEach((id) => {
      if (id === '__panel__') return;
      const slot = slotOfPlugin(id);
      if (slot && railState.hidden[id]) applySlotHidden(slot, true);
    });
    if (railState.hidden && railState.hidden['__panel__']) applySlotHidden('panel', true);
  }
  function applyRailStage() {
    HOST.document.body.classList.remove('rail-0', 'rail-1', 'rail-2');
    HOST.document.body.classList.add('rail-' + railState.stage);
    const t = HOST.document.getElementById('railToggle');
    if (t) {
      // 图标形态固定不变，仅通过展开/收起影响侧栏布局
      paintIcon(t, 'panel-left', '☰');
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
  // 按当前生效状态即时重算单个图标按钮的 on/off 高亮
  function updateRailButton(btn, p) {
    if (!btn) return;
    btn.classList.remove('on', 'off');
    if (p.railAction) {
      // 动作型图标不表达"显隐"，只在对应面板开启时高亮（如设置）
      if (panelActionActive(p)) btn.classList.add('on');
    } else {
      btn.classList.add(pluginVisible(p) ? 'on' : 'off');
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
        paintPluginIcon(g, p);
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
      paintIcon(cg, 'layout-panel-left', '▦');
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
    paintIcon(sg, 'settings', '⚙');
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
    if (!open) closeSettingsMenus();   // 菜单挂在 body 上，面板关掉后不能留在界面上
    if (open) renderSettings();
  }

  // 设置面板内"配置变更后防抖重建"（仅离散操作调用：滑块等连续输入不打断交互）
  let settingsRenderT = null;
  function scheduleSettingsRender() {
    clearTimeout(settingsRenderT);
    settingsRenderT = setTimeout(renderSettings, 250);
  }
  function settingsSave(pid, cfg) {
    // 实时下发 + 持久化即可；卡片控件值已在位，不再整面板重建（避免拖动滑块被打断）
    callAction('config.set', { plugin_id: pid, config: cfg }).catch(() => {});
  }

  // 通用：卡片内 range 字段（label + 滑条 + 实时数值）
  function cfgRangeField(grid, label, min, max, step, value, fmt, onInput) {
    const f = HOST.document.createElement('div');
    f.className = 'cfg-field';
    const lb = HOST.document.createElement('label');
    lb.className = 'cfg-label';
    lb.textContent = label;
    f.appendChild(lb);
    const rng = HOST.document.createElement('input');
    rng.type = 'range';
    rng.className = 'cfg-range';
    rng.min = min; rng.max = max; rng.step = step;
    rng.value = value;
    const valEl = HOST.document.createElement('div');
    valEl.className = 'range-val';
    function upd() { valEl.textContent = fmt(Number(rng.value)); }
    // 已拉部分填强调色，未拉部分保持白色
    function paint() {
      const span = (Number(max) - Number(min)) || 1;
      const pct = Math.max(0, Math.min(100, (Number(rng.value) - Number(min)) / span * 100));
      rng.style.background = 'linear-gradient(90deg, var(--wm-accent) 0 ' + pct + '%, #fff ' + pct + '% 100%)';
    }
    rng.addEventListener('input', function () { paint(); upd(); onInput(Number(rng.value)); });
    upd();
    paint();
    f.appendChild(rng);
    f.appendChild(valEl);
    grid.appendChild(f);
  }

  // 透明度控件（统一方向：滑块数值越大越透明）。
  // 落盘值仍是 alpha（不透明度），因此既有配置与视觉默认值均不变，仅反转控件方向。
  function transparencyField(grid, label, alphaMin, alphaValue, step, onAlpha) {
    const a = Math.min(1, Math.max(alphaMin, alphaValue));
    cfgRangeField(grid, label, 0, Number((1 - alphaMin).toFixed(4)), step,
      Number((1 - a).toFixed(4)),
      function (t) { return label + ' ' + t.toFixed(2); },
      function (t) { onAlpha(Number((1 - t).toFixed(4))); });
  }

  // 白条透明度（宿主外观项，不依赖插件）——统一 cfg-card 风格
  function renderRailAppearance(container) {
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    cfgCardHead(card, '外观设置', '宿主', '最左图标栏外观 · 透明度实时生效');
    const body = HOST.document.createElement('div');
    body.className = 'cfg-card-body';
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid one-col';
    const o = typeof railState.opacity === 'number' ? railState.opacity : 1;
    transparencyField(grid, '透明度', 0.15, o, 0.05, function (v) {
      railState.opacity = v;
      applyRailOpacity();
      persistRail().catch(() => {});
    });
    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }

  // 中栏容器为宿主固有资产（非插件）：设置内提供透明度 + 默认宽度；配置存到"面板容器"键
  // panelSavedWidth 区分「用户显式保存的宽度」与「运行时最大舒展宽度」——后者不落盘
  function settingsSavePanel() {
    const persist = { opacity: panelContainerCfg.opacity };
    if (panelSavedWidth != null) persist.width = panelSavedWidth;
    configByPlugin['panel-container'] = persist;
    applyPanelContainerCfg();
    saveConfig().catch(() => {});
  }
  function renderPanelContainerSettings(container) {
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    cfgCardHead(card, '容器设置', '宿主', '中栏系统级容器 · 透明度与默认宽度');
    const body = HOST.document.createElement('div');
    body.className = 'cfg-card-body';
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid one-col';

    // 透明度
    const o = Number(panelContainerCfg.opacity);
    transparencyField(grid, '透明度', 0.15, (o >= 0.15 && o <= 1) ? o : 0.9, 0.05, function (v) {
      panelContainerCfg.opacity = v;
      applyPanelContainerCfg();
      settingsSavePanel();
    });

    // 默认宽度
    const wf = HOST.document.createElement('div');
    wf.className = 'cfg-field';
    const wl = HOST.document.createElement('label');
    wl.className = 'cfg-label';
    wl.textContent = '默认宽度 (px)';
    wf.appendChild(wl);
    const num = HOST.document.createElement('input');
    num.type = 'number';
    num.min = 260;
    num.step = 10;
    num.className = 'cfg-input';
    num.placeholder = '留空 = 最大舒展';
    num.value = (panelSavedWidth != null) ? panelSavedWidth : '';
    num.addEventListener('change', function () {
      if (!num.value) {   // 清空 = 回到「最大舒展」
        panelSavedWidth = null;
        delete panelContainerCfg.width;
        HOST.document.documentElement.style.removeProperty('--wm-panel-w');
        settingsSavePanel();
        return;
      }
      const w = Number(num.value);
      if (w >= 260) {
        panelSavedWidth = w;
        panelContainerCfg.width = w;
        settingsSavePanel();
      } else {
        HOST.alert('宽度不能小于 260px');
        num.value = (panelSavedWidth != null) ? panelSavedWidth : '';
      }
    });
    wf.appendChild(num);
    grid.appendChild(wf);

    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }

  // 插件卡片（与配置中心统一的 cfg-card 风格）：标题/行为chip/状态chip + 打开关闭 + 抽屉菜单 + 可视化字段
  function renderPluginCard(container, p, cfg) {
    const type = (p.slotDef || {}).type || 'fixed';
    const typeName = type === 'fixed' ? '固定' : (type === 'panel' ? '面板' : '弹窗');
    const vis = pluginVisible(p);
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    const h = cfgCardHead(card, p.name || p.id, typeName, p.id);
    // 状态 chip：panel 表达"容器当前显示哪个"；fixed/float 表达启停
    const st = HOST.document.createElement('span');
    st.className = 'cfg-chip ' + (vis ? 'on' : 'off');
    st.textContent = type === 'panel' ? (vis ? '显示中' : '未显示') : (vis ? '已启用' : '已关闭');
    h.titleRow.appendChild(st);
    // 打开 / 关闭
    const tg = HOST.document.createElement('button');
    tg.className = 'btn cfg-edit';
    tg.textContent = vis ? '关闭' : '打开';
    tg.addEventListener('click', function () { togglePluginOpen(p); renderSettings(); });
    h.right.appendChild(tg);
    // 抽屉菜单（删除 / 内置标识）
    const menuBtn = HOST.document.createElement('button');
    menuBtn.className = 'btn icon menu-btn';
    menuBtn.textContent = '▾';
    menuBtn.title = '更多操作';
    menuBtn.addEventListener('click', function (ev) { openPluginCardMenu(ev, menuBtn, p); });
    h.right.appendChild(menuBtn);
    // 配置字段
    if (p.configSchema && p.configSchema.length) {
      const body = HOST.document.createElement('div');
      body.className = 'cfg-card-body';
      const grid = HOST.document.createElement('div');
      grid.className = 'cfg-grid one-col';
      renderFields(grid, p, cfg);
      body.appendChild(grid);
      card.appendChild(body);
    } else {
      const body = HOST.document.createElement('div');
      body.className = 'cfg-card-body';
      const none = HOST.document.createElement('span');
      none.className = 'p-tag';
      none.textContent = '该插件无配置项';
      body.appendChild(none);
      card.appendChild(body);
    }
    container.appendChild(card);
  }

  function renderFields(grid, p, cfg) {
    (p.configSchema || []).forEach(function (field) {
      const key = field.key;
      const type = field.type || 'text';
      const label = field.label || key;
      if (type === 'switch') {
        const row = HOST.document.createElement('div');
        row.className = 'cfg-field switch-row';
        const lb = HOST.document.createElement('label');
        lb.className = 'cfg-label';
        lb.textContent = label;
        row.appendChild(lb);
        const sw = HOST.document.createElement('label');
        sw.className = 'switch';
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector('input');
        chk.checked = !!cfg[key];
        chk.addEventListener('change', function () { cfg[key] = chk.checked; settingsSave(p.id, cfg); });
        row.appendChild(sw);
        grid.appendChild(row);
        return;
      }
      if (type === 'range') {
        let fv = cfg[key];
        const initVal = (typeof fv === 'number' && !isNaN(fv)) ? fv : ((field.default != null) ? field.default : ((field.max != null) ? field.max : 1));
        const min0 = (field.min != null) ? field.min : 0;
        const step0 = (field.step != null) ? field.step : 0.01;
        const applyVal = function (v) { cfg[key] = v; settingsSave(p.id, cfg); };
        if (key === 'opacity') {
          // 透明度：滑块越大越透明（落盘仍是 alpha，视觉默认不变）
          transparencyField(grid, label, min0, initVal, step0, applyVal);
        } else {
          cfgRangeField(grid, label, min0, (field.max != null) ? field.max : 1, step0, initVal,
            function (v) { return label + ' ' + v.toFixed(2); }, applyVal);
        }
        return;
      }
      const f = HOST.document.createElement('div');
      f.className = 'cfg-field' + (type === 'wallpapers' ? ' wide' : '');
      const lb = HOST.document.createElement('label');
      lb.className = 'cfg-label';
      lb.textContent = label;
      f.appendChild(lb);
      if (type === 'select') {
        const sel = HOST.document.createElement('select');
        sel.className = 'cfg-input';
        (field.options || []).forEach(function (op) {
          const o2 = HOST.document.createElement('option');
          o2.value = op;
          o2.textContent = op;
          sel.appendChild(o2);
        });
        sel.value = cfg[key] || '';
        sel.addEventListener('change', function () { cfg[key] = sel.value; settingsSave(p.id, cfg); });
        f.appendChild(sel);
      } else if (type === 'number') {
        const num = HOST.document.createElement('input');
        num.type = 'number';
        num.step = 'any';
        num.className = 'cfg-input';
        num.value = cfg[key] == null ? '' : cfg[key];
        num.addEventListener('change', function () { cfg[key] = num.value === '' ? null : Number(num.value); settingsSave(p.id, cfg); });
        f.appendChild(num);
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
              scheduleSettingsRender();   // 离散操作：重建面板让"背景模式"下拉同步
            }).catch(function () {});
          });
          wallsWrap.appendChild(add);
        }
        function commit() { cfg[key] = list; settingsSave(p.id, cfg); }
        draw();
        f.appendChild(wallsWrap);
      } else {
        const txt = HOST.document.createElement('input');
        txt.type = 'text';
        txt.className = 'cfg-input';
        txt.value = cfg[key] || '';
        txt.addEventListener('change', function () { cfg[key] = txt.value; settingsSave(p.id, cfg); });
        f.appendChild(txt);
      }
      grid.appendChild(f);
    });
  }

  // ---- 设置面板：左导航 + 内容区（宿主固有资产，非插件）----
  // 主导航：UI 插件 + 原配置中心逐标签页
  const CONFIG_NAV = ['plugins', 'view', 'model', 'sensor', 'file', 'mcp', 'app', 'acp', 'deploy'];
  const CONFIG_LABEL = { plugins: 'UI 插件', view: '视图设置', model: '模型', sensor: '传感器', file: '文件', mcp: 'MCP', app: '应用', acp: 'ACP', deploy: '部署' };
  let settingsTab = 'plugins';
  let settingsRenderedTab = '';   // 上一次渲染的标签页（同页重建才恢复滚动位置）
  let deployPollT = null;   // 部署页轮询定时器句柄

  function renderSettings() {
    const bodyEl = HOST.document.querySelector('[data-layer="settings"] .settings-body');
    if (!bodyEl) return;
    if (deployPollT) { clearInterval(deployPollT); deployPollT = null; }
    closeSettingsMenus();   // 卡片菜单挂在 body 上，重建后锚点按钮已消失，先收起避免残留
    // 内容区滚动位置：同一标签页内重建（改配置项触发的防抖重建）恢复原地，切标签页则回到顶部。
    // 卡片是 fetch 回来后才插入的，故用一次 MutationObserver 在异步内容落地后再兜底恢复一次。
    const prevMain = bodyEl.querySelector('.settings-main');
    const keepTop = (settingsRenderedTab === settingsTab && prevMain) ? prevMain.scrollTop : 0;
    bodyEl.innerHTML = '';
    // 左导航
    const nav = HOST.document.createElement('div');
    nav.className = 'settings-nav';
    CONFIG_NAV.forEach(function (key) {
      const it = HOST.document.createElement('button');
      it.className = 'settings-nav-item' + (settingsTab === key ? ' active' : '');
      it.textContent = CONFIG_LABEL[key] || key;
      it.addEventListener('click', function () { settingsTab = key; renderSettings(); });
      nav.appendChild(it);
    });
    bodyEl.appendChild(nav);
    // 内容区
    const main = HOST.document.createElement('div');
    main.className = 'settings-main';
    bodyEl.appendChild(main);
    if (settingsTab === 'plugins') renderPluginsTab(main);
    else renderConfigSection(main, settingsTab);
    settingsRenderedTab = settingsTab;
    if (keepTop) {
      main.scrollTop = keepTop;
      const mo = new MutationObserver(function () { main.scrollTop = keepTop; mo.disconnect(); });
      mo.observe(main, { childList: true, subtree: true });
      setTimeout(function () { mo.disconnect(); }, 2000);
    }
  }

  // ---- UI 插件主面板：按「区域」竖排分组（卡片 / JSON 双模式，与配置中心一致）----
  // area 是插件声明的唯一维度；行为（单例 / 容器抽屉 / 浮窗）由宿主按区域内置。
  const AREA_LABEL = {
    rail: '左侧白条', sidebar: '会话列表', input: '输入框', background: '背景',
    conversation: '历史会话', 'panel-container': '面板容器', panel: '面板', popup: '弹窗类',
  };
  // 宿主原生资产（非插件）挂在所属区域内；singleton 标记「同区域同时只能启用一个插件」
  const UI_GROUPS = [
    { area: 'rail', host: renderRailAppearance },
    { area: 'sidebar', singleton: true },
    { area: 'input', singleton: true },
    { area: 'background', singleton: true },
    { area: 'conversation', singleton: true },
    { area: 'panel-container', host: renderPanelContainerSettings },
    { area: 'panel' },
    { area: 'popup' },
  ];
  function cfgFor(p) { return Object.assign({}, configByPlugin[p.id] || {}); }

  function renderPluginsTab(main) {
    cfgToolbar(main, 'plugins', function (m) { m.innerHTML = ''; renderPluginsTab(m); });
    if ((cfgState.mode['plugins'] || 'cards') === 'json') {
      renderWebminJson(main);
      return;
    }
    UI_GROUPS.forEach(function (grp) { renderPluginGroup(main, grp); });
    const btnNormal = HOST.document.createElement('div');
    btnNormal.className = 'mode-row';
    const b = HOST.document.createElement('button');
    b.className = 'btn';
    b.textContent = '回到完整模式';
    b.addEventListener('click', function () {
      callAction('switch_to_normal', {}).then(function (d) { if (d && d.restart) HOST.alert('已切换为完整模式，请重启应用生效。'); }).catch(function () {});
    });
    btnNormal.appendChild(b);
    main.appendChild(btnNormal);
  }

  // 整份宿主配置的 JSON 编辑（GET/PUT /api/webmin/config，保存后重建界面立即生效）
  function renderWebminJson(main) {
    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '极简 UI 宿主配置：plugins=各插件配置 · rail=图标栏状态 · active=单例槽选中项。保存后立即生效并重建界面。';
    main.appendChild(tip);
    const tx = HOST.document.createElement('textarea');
    tx.className = 'settings-json';
    tx.spellcheck = false;
    tx.placeholder = '读取配置…';
    main.appendChild(tx);
    const status = HOST.document.createElement('span');
    status.className = 'p-tag';
    fetch('/api/webmin/config').then(function (r) { return r.json(); }).then(function (cfg) {
      tx.value = JSON.stringify(cfg, null, 2);
      status.textContent = '已加载';
    }).catch(function () { status.textContent = '加载失败'; });
    const bar = HOST.document.createElement('div');
    bar.className = 'settings-actions';
    const save = HOST.document.createElement('button');
    save.className = 'btn cfg-save';
    save.textContent = '保存并应用';
    save.addEventListener('click', function () {
      let obj;
      try { obj = JSON.parse(tx.value); } catch (e) { HOST.alert('JSON 解析失败：' + e.message); return; }
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) { HOST.alert('顶层必须是 JSON 对象'); return; }
      save.disabled = true;
      status.textContent = '保存中…';
      fetch('/api/webmin/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
        .then(function () { return reloadManifest(); })
        .then(function () {
          status.textContent = '已保存并应用';
          renderSettings();
        })
        .catch(function (e) {
          save.disabled = false;
          status.textContent = '保存失败';
          HOST.alert('保存失败：' + (e && e.message || ''));
        });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }

  function renderPluginGroup(main, grp) {
    const group = HOST.document.createElement('div');
    group.className = 'settings-group';
    const gt = HOST.document.createElement('div');
    gt.className = 'settings-group-title';
    gt.textContent = AREA_LABEL[grp.area] || grp.area;
    group.appendChild(gt);
    if (grp.host) grp.host(group);   // 宿主原生资产（左侧白条 / 面板容器）
    const list = groupState.plugins.filter(function (p) { return ((p.slotDef || {}).area || '') === grp.area; });
    const multi = grp.singleton && list.length > 1;
    if (multi) {
      const sub = HOST.document.createElement('div');
      sub.className = 'settings-subgroup';
      sub.textContent = '同时只能启用一个插件';
      group.appendChild(sub);
    }
    list.forEach(function (p) { renderPluginCard(group, p, cfgFor(p)); });
    if (!group.querySelector('.cfg-card')) {
      const none = HOST.document.createElement('div');
      none.className = 'p-tag';
      none.textContent = '（暂无插件）';
      group.appendChild(none);
    }
    main.appendChild(group);
  }

  // ---- 插件生效状态与右上角抽屉（删除 / 内置标识；启停走卡片上的打开/关闭按钮）----
  // 按槽类型判定插件是否真实生效：fixed=该槽当前挂载中；panel=容器显示且为抽屉当前选中；float=未隐藏
  function pluginVisible(p) {
    if (railHidden(p.id)) return false;
    const type = (p.slotDef || {}).type;
    if (type === 'fixed') {
      const cur = pluginBySlot[p.slot];
      return !!cur && cur.id === p.id;
    }
    if (type === 'panel') {
      if (railState.hidden && railState.hidden['__panel__']) return false;
      return !!panelState && panelState.activeId === p.id;
    }
    return true;   // float：未隐藏即生效
  }
  function closeSettingsMenus() {
    HOST.document.querySelectorAll('.settings-card-menu').forEach(function (m) { m.remove(); });
  }
  function openPluginCardMenu(ev, btn, p) {
    ev.stopPropagation();
    const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + p.id + '"]');
    closeSettingsMenus();
    if (wasOpen) return;   // 再次点同一个按钮 = 收起（否则只能靠点别处才关得掉）
    const menu = HOST.document.createElement('div');
    menu.className = 'settings-card-menu';
    menu.setAttribute('data-owner', p.id);
    if (p.builtin) {
      const dis = HOST.document.createElement('button');
      dis.className = 'settings-menu-btn disabled';
      dis.textContent = '内置插件 · 不可删除';
      dis.disabled = true;
      menu.appendChild(dis);
    } else {
      const d = HOST.document.createElement('button');
      d.className = 'settings-menu-btn danger';
      d.textContent = '删除';
      d.addEventListener('click', function () {
        closeSettingsMenus();
        if (HOST.confirm('确定删除插件 “' + (p.name || p.id) + '” 吗？')) {
          callAction('plugin.delete', { plugin_id: p.id }).then(function () { renderSettings(); }).catch(function (e) { HOST.alert('删除失败：' + e.message); });
        }
      });
      menu.appendChild(d);
    }
    HOST.document.body.appendChild(menu);
    const r = btn.getBoundingClientRect();
    menu.style.right = (HOST.innerWidth - r.right) + 'px';
    menu.style.top = (r.bottom + 4) + 'px';
  }

  // 把某插件置为对应槽位的当前活动实例（fixed 卸旧挂新；panel 切换抽屉选中），并持久化用户选择
  function activateSlotPlugin(p) {
    const slot = p.slot;
    const type = (p.slotDef || {}).type;
    if (type === 'panel') {
      activeBySlot['panel'] = p.id;                 // 记住抽屉当前选中的面板插件（重启恢复）
      if (panelState) { panelState.activeId = p.id; renderPanelContent(panelState); }
      setContainerHidden(false);
      if (railHidden(p.id)) setPluginHidden(p.id, false);
      buildRail();
      persistActive();
      return;
    }
    if (type === 'fixed') activeBySlot[slot] = p.id;   // 记住该单例槽当前选中的插件
    // fixed：已是主挂载则仅取消隐藏；否则卸载当前并挂载目标
    if (pluginBySlot[slot] !== p) {
      if (frames[slot]) { frames[slot].forEach(function (f) { if (f.iframe && f.iframe.parentNode) f.iframe.parentNode.removeChild(f.iframe); }); frames[slot] = []; }
      pluginBySlot[slot] = p;
      const anchor = HOST.document.querySelector('[data-slot="' + slot + '"]');
      if (anchor) {
        anchor.innerHTML = '';
        const fr = mountFrame(anchor, p);
        if (fr) frames[slot] = [fr];
      }
    }
    if (railHidden(p.id)) setPluginHidden(p.id, false);
    buildRail();
    if (type === 'fixed') persistActive();
  }
  function togglePluginOpen(p) {
    const type = (p.slotDef || {}).type;
    if (pluginVisible(p)) {   // 关闭：fixed=隐藏锚定区；panel=收起容器；float=隐藏实例
      if (type === 'panel') setContainerHidden(true);
      else { setPluginHidden(p.id, true); buildRail(); }
      return;
    }
    // 打开：fixed 单例槽拦截——同槽位已有其他插件运行时，必须先关闭它
    if (type === 'fixed') {
      const cur = pluginBySlot[p.slot];
      if (cur && cur.id !== p.id && !railHidden(cur.id)) {
        HOST.alert('「' + (p.name || p.id) + '」与「' + (cur.name || cur.id) + '」占用同一位置，同时只能启用一个插件。请先关闭「' + (cur.name || cur.id) + '」。');
        return;
      }
    }
    activateSlotPlugin(p);   // panel/float 无单例约束；panel 切换抽屉，float 直接显示
  }

  // ---- 原配置中心逐标签页复刻（卡片 + 裸 JSON 双模式）----
  const MODEL_CATS = [ // 三个模型角色：title/jsonKey
    { key: 'main', title: '核心模型' },
    { key: 'task', title: '后台模型' },
    { key: 'vision', title: '视觉顾问' },
  ];
  const MODEL_SDKS = ['openai'];
  const DEPLOY_ITEMS = ['uv', 'node', 'sandbox', 'embedding'];
  const DEPLOY_LABEL = { uv: 'uv', node: 'node', sandbox: 'sandbox / Docker 沙盒', embedding: 'embedding' };
  const cfgState = {
    data: {},         // tab -> 已加载的配置对象（GET /api/config/{tab}）
    mode: {},         // tab -> 'cards'|'json'
    openKey: {},      // tab -> 处于展开态的顶级 key
    editStr: {},      // tab+'::'+key -> 编辑区文本
    sandboxRegistry: '',
    deployLogOpen: {},
  };
  function makeSection(title, main) {
    const sec = HOST.document.createElement('div');
    sec.className = 'settings-section';
    const t = HOST.document.createElement('div');
    t.className = 'settings-section-title';
    t.textContent = title;
    sec.appendChild(t);
    main.appendChild(sec);
    return sec;
  }
  // 配置缓存读取（首次拉取后复用），以及保存
  async function cfgData(tab) {
    if (!cfgState.data[tab]) {
      try { cfgState.data[tab] = await (await fetch('/api/config/' + tab)).json(); }
      catch (e) { cfgState.data[tab] = {}; }
    }
    return cfgState.data[tab];
  }
  async function putCfg(tab, obj) {
    cfgState.data[tab] = obj;
    const r = await fetch('/api/config/' + tab, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  function rerenderConfig(main, key) { main.innerHTML = ''; renderConfigSection(main, key); }

  // 每个 JSON 型 tab 里：左上角「卡片 / 裸 JSON」切换（rerender 默认重建当前配置页）
  function cfgToolbar(main, key, rerender) {
    const fn = rerender || rerenderConfig;
    const tb = HOST.document.createElement('div');
    tb.className = 'cfg-toolbar';
    ['卡片', 'JSON'].forEach(function (label, i) {
      const mode = i === 0 ? 'cards' : 'json';
      const seg = HOST.document.createElement('button');
      seg.className = 'cfg-seg' + ((cfgState.mode[key] || 'cards') === mode ? ' active' : '');
      seg.textContent = label;
      seg.addEventListener('click', function () { cfgState.mode[key] = mode; fn(main, key); });
      tb.appendChild(seg);
    });
    main.appendChild(tb);
    return tb;
  }

  function renderConfigSection(main, key) {
    if (key === 'view') return renderViewCard(main);
    if (key === 'acp') return renderAcpCard(main);
    if (key === 'deploy') return renderDeployCards(main);
    cfgToolbar(main, key);
    if ((cfgState.mode[key] || 'cards') === 'json') {
      renderRawJson(main, key);
    } else if (key === 'model') {
      renderModelCards(main, key);
    } else if (key === 'mcp') {
      renderMcpCards(main, key);
    } else {
      renderGenericCards(main, key);
    }
  }

  // ---- 裸 JSON 编辑 ----
  function renderRawJson(main, key) {
    const tx = HOST.document.createElement('textarea');
    tx.className = 'settings-json';
    tx.spellcheck = false;
    tx.placeholder = '读取配置…';
    main.appendChild(tx);
    const status = HOST.document.createElement('span');
    status.className = 'p-tag';
    cfgData(key).then(function (data) { tx.value = JSON.stringify(data, null, 2); status.textContent = '已加载'; });
    const bar = HOST.document.createElement('div');
    bar.className = 'settings-actions';
    const save = HOST.document.createElement('button');
    save.className = 'btn';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      let obj;
      try { obj = JSON.parse(tx.value); } catch (e) { HOST.alert('JSON 解析失败：' + e.message); return; }
      putCfg(key, obj).then(function () { status.textContent = '已保存'; }).catch(function (e) { status.textContent = '保存失败'; HOST.alert('保存失败：' + (e && e.message || '')); });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }

  // 通用卡片：卡片头（左列=标题行+副标题，右列=动作区）+ 右上动作
  function cfgCard(main) {
    const c = HOST.document.createElement('div');
    c.className = 'cfg-card';
    main.appendChild(c);
    return c;
  }
  function cfgCardHead(card, title, kind, sub) {
    const head = HOST.document.createElement('div');
    head.className = 'cfg-card-head';
    const left = HOST.document.createElement('div');
    left.className = 'cfg-card-head-l';
    const trow = HOST.document.createElement('div');
    trow.className = 'cfg-card-title';
    const t = HOST.document.createElement('span');
    t.textContent = title;
    trow.appendChild(t);
    if (kind) { const k = HOST.document.createElement('span'); k.className = 'cfg-chip type'; k.textContent = kind; trow.appendChild(k); }
    left.appendChild(trow);
    if (sub) {
      const s = HOST.document.createElement('div');
      s.className = 'cfg-card-sub';
      s.textContent = sub;
      left.appendChild(s);
    }
    head.appendChild(left);
    const right = HOST.document.createElement('div');
    right.className = 'cfg-card-act';
    head.appendChild(right);
    card.appendChild(head);
    return { head: head, right: right, left: left, titleRow: trow };
  }

  // ---- model：三角色卡片（每个角色直接平铺展示编辑表单，无展开/收起）----
  function modelList(data, cat) {
    return (data && data[cat] && typeof data[cat] === 'object') ? Object.keys(data[cat]) : [];
  }
  // 由已有条目构造编辑表单（无条目时给出空白表单，模型名留空）
  function modelFormOf(entry, entryKey) {
    const e = entry || {};
    const idx = entryKey.indexOf(':');
    const sdk = idx >= 0 ? entryKey.slice(0, idx) : 'openai';
    const modelName = idx >= 0 ? entryKey.slice(idx + 1) : entryKey;
    return {
      sdk: sdk || 'openai',
      modelName: modelName,
      apiKey: (Array.isArray(e.api_keys) && e.api_keys[0]) ? e.api_keys[0] : '',
      baseUrl: e.base_url || '',
      rpm: e.rpm != null ? String(e.rpm) : '60',
      tpm: e.tpm != null ? String(e.tpm) : '1000000',
      concurrency: e.concurrency != null ? String(e.concurrency) : '3',
      maxToken: e.max_token != null ? String(e.max_token) : '500000',
      vision: !!e.vision,
    };
  }
  function modelField(grid, label, input) {
    const f = HOST.document.createElement('div');
    f.className = 'cfg-field';
    const lb = HOST.document.createElement('label');
    lb.className = 'cfg-label';
    lb.textContent = label;
    f.appendChild(lb);
    input.className = 'cfg-input';
    f.appendChild(input);
    grid.appendChild(f);
  }
  function renderModelCards(main, key) {
    cfgData(key).then(function (data) {
      MODEL_CATS.forEach(function (cat) {
        const card = cfgCard(main);
        const head = cfgCardHead(card, cat.title, 'model');
        if (!data[cat.key] || typeof data[cat.key] !== 'object') data[cat.key] = {};
        const keys = modelList(data, cat.key);
        // 无已配置条目时也平铺一个空白表单，直接填写即可
        (keys.length ? keys : ['']).forEach(function (entryKey) {
          renderModelForm(card, key, data, cat.key, entryKey, head.right);
        });
      });
    });
  }
  // 角色下的单个模型表单：直接平铺展示，保存后写回并热重载
  function renderModelForm(card, key, data, cat, entryKey, act) {
    const f = modelFormOf((data[cat] || {})[entryKey], entryKey);
    const body = HOST.document.createElement('div');
    body.className = 'cfg-card-body';
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid';
    const mk = HOST.document.createElement('input'); mk.type = 'text'; mk.value = f.modelName; mk.addEventListener('input', function () { f.modelName = mk.value; });
    modelField(grid, '模型名 (key 后缀)', mk);
    const ak = HOST.document.createElement('input'); ak.type = 'password'; ak.value = f.apiKey; ak.placeholder = 'sk-...'; ak.spellcheck = false; ak.addEventListener('input', function () { f.apiKey = ak.value; });
    modelField(grid, 'API KEY', ak);
    const bu = HOST.document.createElement('input'); bu.type = 'text'; bu.value = f.baseUrl; bu.placeholder = 'https://api.deepseek.com'; bu.spellcheck = false; bu.addEventListener('input', function () { f.baseUrl = bu.value; });
    modelField(grid, 'BASE URL', bu);
    if (cat !== 'vision') {
      [['rpm', 'RPM'], ['tpm', 'TPM'], ['concurrency', '并发数'], ['maxToken', 'MAX TOKEN']].forEach(function (pair) {
        const e2 = HOST.document.createElement('input'); e2.type = 'number'; e2.value = f[pair[0]]; e2.addEventListener('input', function () { f[pair[0]] = e2.value; });
        modelField(grid, pair[1], e2);
      });
    }
    body.appendChild(grid);
    if (cat !== 'vision') {
      const swRow = HOST.document.createElement('div');
      swRow.className = 'cfg-field switch-row';
      const swl = HOST.document.createElement('label');
      swl.textContent = '视觉直注（把图片直接注入上下文）';
      swRow.appendChild(swl);
      const sw = HOST.document.createElement('label');
      sw.className = 'switch';
      sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
      sw.querySelector('input').checked = f.vision;
      sw.querySelector('input').addEventListener('change', function (e2) { f.vision = e2.target.checked; });
      swRow.appendChild(sw);
      body.appendChild(swRow);
    }
    const save = HOST.document.createElement('button');
    save.className = 'btn cfg-save';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      const nm = f.modelName.trim();
      if (!nm) { HOST.alert('请填写模型名'); return; }
      const newKey = (f.sdk || 'openai') + ':' + nm;
      const obj = { api_keys: [f.apiKey.trim()], base_url: f.baseUrl.trim() };
      if (cat !== 'vision') {
        obj.rpm = Number(f.rpm) || 60; obj.tpm = Number(f.tpm) || 1000000; obj.concurrency = Number(f.concurrency) || 3; obj.max_token = Number(f.maxToken) || 500000; obj.vision = f.vision;
      }
      if (entryKey && newKey !== entryKey) delete data[cat][entryKey];
      data[cat][newKey] = obj;
      putCfg(key, data).then(function () { rerenderConfig(main, key); HOST.alert('模型已保存并热重载。'); }).catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
    });
    (act || card).appendChild(save);
    card.appendChild(body);
  }

  // ---- mcp：服务器卡片（按单服务器拆分）----
  function renderMcpCards(main, key) {
    cfgData(key).then(function (data) {
      // mcp_config.json 的结构为 { mcpServers: { 服务器名: 配置 } }，需先解包这一层
      if (!data || typeof data !== 'object' || Array.isArray(data)) data = {};
      if (!data.mcpServers || typeof data.mcpServers !== 'object' || Array.isArray(data.mcpServers)) data.mcpServers = {};
      cfgState.data[key] = data;
      const servers = data.mcpServers;
      const names = Object.keys(servers);
      if (names.length === 0) {
        const empty = HOST.document.createElement('div'); empty.className = 'p-tag'; empty.textContent = '（暂无 MCP 服务器）'; main.appendChild(empty);
      }
      names.forEach(function (name) {
        const isOpen = cfgState.openKey[key] === name;
        const val = servers[name];
        const card = cfgCard(main);
        const preview = JSON.stringify(val);
        const h = cfgCardHead(card, name, (Array.isArray(val) ? 'array' : typeof val), preview.slice(0, 90) + (preview.length > 90 ? '…' : ''));
        const edit = HOST.document.createElement('button');
        edit.className = 'btn cfg-edit';
        edit.textContent = isOpen ? '关闭' : '编辑';
        edit.addEventListener('click', function () {
          if (isOpen) delete cfgState.openKey[key]; else { cfgState.openKey[key] = name; cfgState.editStr[key + '::' + name] = JSON.stringify(val, null, 2); }
          rerenderConfig(main, key);
        });
        h.right.appendChild(edit);
        const del = HOST.document.createElement('button');
        del.className = 'btn cfg-del';
        del.textContent = '删除';
        del.addEventListener('click', function () {
          if (!HOST.confirm('删除 MCP 服务器 "' + name + '"？')) return;
          delete servers[name];
          delete cfgState.openKey[key];
          putCfg(key, data).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('删除失败：' + (e && e.message || '')); });
        });
        h.right.appendChild(del);
        if (!isOpen) return;
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        const ta = HOST.document.createElement('textarea');
        ta.className = 'settings-json';
        ta.style.minHeight = '150px';
        ta.value = cfgState.editStr[key + '::' + name] || JSON.stringify(val, null, 2);
        ta.addEventListener('input', function () { cfgState.editStr[key + '::' + name] = ta.value; });
        body.appendChild(ta);
        const save = HOST.document.createElement('button');
        save.className = 'btn cfg-save';
        save.textContent = '保存该服务器';
        save.addEventListener('click', function () {
          let obj;
          try { obj = JSON.parse(cfgState.editStr[key + '::' + name]); } catch (e) { HOST.alert('JSON 解析失败：' + e.message); return; }
          servers[name] = obj;
          delete cfgState.openKey[key];
          putCfg(key, data).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
        });
        body.appendChild(save);
        card.appendChild(body);
      });
    });
  }

  // ---- 通用 key-value（sensor/file/app）----
  function coerceVal(str, orig) {
    if (orig === null || orig === undefined) return str;
    const t = Array.isArray(orig) ? 'array' : typeof orig;
    if (t === 'number') return Number(str);
    if (t === 'boolean') return (str === 'true' || str === '1' || str === '是');
    if (t === 'object') { try { return JSON.parse(str); } catch (e) { return orig; } }
    return str;
  }
  function renderGenericCards(main, key) {
    cfgData(key).then(function (data) {
      const obj = data || {};
      const keys = Object.keys(obj).filter(function (k) { return k !== '__ARRAY_WRAPPER__'; });
      if (keys.length === 0) { const e = HOST.document.createElement('div'); e.className = 'p-tag'; e.textContent = '（空配置）'; main.appendChild(e); }
      keys.forEach(function (k) {
        const val = obj[k];
        const isOpen = cfgState.openKey[key] === k;
        const card = cfgCard(main);
        const raw = (typeof val === 'object') ? JSON.stringify(val) : String(val);
        const h = cfgCardHead(card, k, (Array.isArray(val) ? 'array' : typeof val), raw.slice(0, 90) + (raw.length > 90 ? '…' : ''));
        const edit = HOST.document.createElement('button');
        edit.className = 'btn cfg-edit';
        edit.textContent = isOpen ? '关闭' : '编辑';
        edit.addEventListener('click', function () {
          if (isOpen) delete cfgState.openKey[key]; else { cfgState.openKey[key] = k; cfgState.editStr[key + '::' + k] = (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val)); }
          rerenderConfig(main, key);
        });
        h.right.appendChild(edit);
        const del = HOST.document.createElement('button');
        del.className = 'btn cfg-del';
        del.textContent = '删除';
        del.addEventListener('click', function () {
          if (!HOST.confirm('删除配置项 "' + k + '"？')) return;
          delete obj[k];
          delete cfgState.openKey[key];
          putCfg(key, obj).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('删除失败：' + (e && e.message || '')); });
        });
        h.right.appendChild(del);
        if (!isOpen) return;
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        const ta = HOST.document.createElement('textarea');
        ta.className = 'settings-json';
        ta.style.minHeight = '140px';
        ta.value = cfgState.editStr[key + '::' + k] || (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val));
        ta.addEventListener('input', function () { cfgState.editStr[key + '::' + k] = ta.value; });
        body.appendChild(ta);
        const save = HOST.document.createElement('button');
        save.className = 'btn cfg-save';
        save.textContent = '保存该配置项';
        save.addEventListener('click', function () {
          let newVal;
          try { newVal = coerceVal(cfgState.editStr[key + '::' + k], val); } catch (e) { HOST.alert(e.message); return; }
          obj[k] = newVal;
          delete cfgState.openKey[key];
          putCfg(key, obj).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
        });
        body.appendChild(save);
        card.appendChild(body);
      });
    });
  }

  // ---- view：极简模式卡片 ----
  function renderViewCard(main) {
    const sec = makeSection('视图设置', main);
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    sec.appendChild(card);
    const h = cfgCardHead(card, '极简模式（minimal）', 'ui_mode', '开启后极简 UI 作为默认界面，需重启应用生效');
    const swl = HOST.document.createElement('label');
    swl.className = 'switch';
    swl.innerHTML = '<input type="checkbox"><span class="slider"></span>';
    const chk = swl.querySelector('input');
    h.right.appendChild(swl);
    fetch('/api/config/view').then(function (r) { return r.json(); }).then(function (d) { chk.checked = d.ui_mode === 'minimal'; }).catch(function () {});
    chk.addEventListener('change', function () {
      fetch('/api/config/view', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ui_mode: chk.checked ? 'minimal' : 'normal' }) })
        .then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('视图模式已更新，请重启应用生效。'); })
        .catch(function () { chk.checked = !chk.checked; HOST.alert('保存失败'); });
    });
  }

  // ---- acp：接入卡片 ----
  function renderAcpCard(main) {
    const sec = makeSection('ACP 接入', main);
    const card = cfgCard(sec);
    const h = cfgCardHead(card, 'ACP 编辑器接入', 'relay');
    fetch('/api/config/acp').then(function (r) { return r.json(); }).then(function (d) {
      const sub = HOST.document.createElement('div');
      sub.className = 'cfg-card-sub';
      sub.textContent = 'relay 已部署:' + (d.relay_deployed ? '是' : '否') + ' · 与源一致:' + (d.relay_matches_source ? '是' : '否') + ' · uv:' + (d.uv_found ? '可用' : '缺失');
      h.left.appendChild(sub);
      const body = HOST.document.createElement('div');
      body.className = 'cfg-card-body';
      const grid = HOST.document.createElement('div');
      grid.className = 'cfg-grid';
      const portF = HOST.document.createElement('div');
      portF.className = 'cfg-field';
      const plb = HOST.document.createElement('label'); plb.className = 'cfg-label'; plb.textContent = '端口';
      portF.appendChild(plb);
      const port = HOST.document.createElement('input'); port.type = 'number'; port.className = 'cfg-input'; if (d.port) port.value = d.port;
      portF.appendChild(port);
      grid.appendChild(portF);
      body.appendChild(grid);
      const ops = HOST.document.createElement('div');
      ops.className = 'settings-actions';
      const enact = HOST.document.createElement('button'); enact.className = 'btn'; enact.textContent = '保存端口';
      enact.addEventListener('click', function () { fetch('/api/config/acp', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port: Number(port.value) }) }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('端口已更新'); }).catch(function () { HOST.alert('保存失败'); }); });
      ops.appendChild(enact);
      const red = HOST.document.createElement('button'); red.className = 'btn'; red.textContent = '重新部署 relay';
      red.addEventListener('click', function () { fetch('/api/config/acp/redeploy', { method: 'POST' }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('已重新部署'); }).catch(function () { HOST.alert('部署失败'); }); });
      ops.appendChild(red);
      const rtk = HOST.document.createElement('button'); rtk.className = 'btn'; rtk.textContent = '重置 token';
      rtk.addEventListener('click', function () { fetch('/api/config/acp/reset-token', { method: 'POST' }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('token 已重置，relay 需重启重连'); }).catch(function () { HOST.alert('重置失败'); }); });
      ops.appendChild(rtk);
      body.appendChild(ops);
      card.appendChild(body);
    }).catch(function () {});
    sec.appendChild(card);
  }

  // ---- deploy：四步线性列表 + 状态指示灯 ----
  function deployState(it, ov) {
    const item = (ov && ov.items) ? ov.items[it] : null;
    const task = (ov && ov.tasks) ? ov.tasks[it] : null;
    const running = task && task.state === 'running';
    let state;
    if (running) state = 'running';
    else if (task && task.state === 'success') state = 'installed';
    else if (task && task.state === 'failed') state = 'failed';
    else if (item && item.ready) state = 'ready';
    else state = 'missing';
    const clickable = state === 'missing' || state === 'failed';
    const text = state === 'missing' ? '一键部署' : state === 'failed' ? '重新部署' : state === 'running' ? '部署中…' : state === 'installed' ? '已安装待重启' : '已就绪';
    return { state: state, clickable: clickable, text: text, item: item, task: task };
  }
  function renderDeployCards(main) {
    const sec = makeSection('部署中心', main);
    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '按顺序逐步安装依赖：uv → node → sandbox → embedding。需重启应用生效，建议网络稳定。';
    sec.appendChild(tip);
    const list = HOST.document.createElement('div');
    list.className = 'cfg-stepper';
    sec.appendChild(list);
    if (!cfgState.sandboxRegistry) {
      fetch('/api/config/sandbox-registry').then(function (r) { return r.json(); }).then(function (d) { if (d) cfgState.sandboxRegistry = d.sandbox_registry || 'ghcr.io/purrpod'; }).catch(function () { cfgState.sandboxRegistry = 'ghcr.io/purrpod'; });
    }
    function draw() {
      cfgData('deploy').then(function (ov) {
        list.innerHTML = '';
        DEPLOY_ITEMS.forEach(function (it, idx) {
          const st = deployState(it, ov);
          const row = HOST.document.createElement('div');
          row.className = 'cfg-step';
          const rail = HOST.document.createElement('div');
          rail.className = 'cfg-step-rail';
          const dot = HOST.document.createElement('div');
          dot.className = 'cfg-step-dot ' + st.state;
          dot.textContent = idx + 1;
          rail.appendChild(dot);
          if (idx < DEPLOY_ITEMS.length - 1) { const line = HOST.document.createElement('div'); line.className = 'cfg-step-line'; rail.appendChild(line); }
          row.appendChild(rail);
          const body = HOST.document.createElement('div');
          body.className = 'cfg-step-body';
          const head = HOST.document.createElement('div');
          head.className = 'cfg-step-head';
          const nm = HOST.document.createElement('div');
          nm.className = 'cfg-step-title';
          nm.textContent = DEPLOY_LABEL[it];
          head.appendChild(nm);
          const act = HOST.document.createElement('div');
          act.className = 'cfg-step-act';
          if (it === 'sandbox' && st.item) {
            const docker = HOST.document.createElement('span');
            docker.className = 'cfg-chip ' + (st.item.docker_installed ? 'ok' : 'bad');
            docker.textContent = 'Docker ' + (st.item.docker_installed ? '✓' : '✗');
            act.appendChild(docker);
            const img = HOST.document.createElement('span');
            img.className = 'cfg-chip ' + (st.item.image_ready ? 'ok' : 'warn');
            img.textContent = '镜像 ' + (st.item.image_ready ? '✓' : '✗');
            act.appendChild(img);
          }
          const btn = HOST.document.createElement('button');
          btn.className = 'btn cfg-deploy-btn ' + st.state;
          btn.disabled = !st.clickable;
          btn.textContent = (st.state === 'running' ? '··· ' : '') + st.text;
          btn.addEventListener('click', function () {
            if (!st.clickable) return;
            fetch('/api/config/deploy/' + it, { method: 'POST' }).then(function (r) { if (!r.ok) return r.json().then(function (d2) { throw new Error(d2.detail || '部署冲突'); }); }).then(function () { delete cfgState.data.deploy; draw(); }).catch(function (e) { HOST.alert('失败：' + (e && e.message || '')); });
          });
          act.appendChild(btn);
          head.appendChild(act);
          body.appendChild(head);
          if (it === 'sandbox') {
            const reg = HOST.document.createElement('div');
            reg.className = 'cfg-registry-row';
            const inp = HOST.document.createElement('input');
            inp.type = 'text'; inp.placeholder = 'ghcr.io/…（默认 ghcr.io/purrpod）'; inp.value = cfgState.sandboxRegistry;
            inp.addEventListener('input', function () { cfgState.sandboxRegistry = inp.value; });
            const rs = HOST.document.createElement('button');
            rs.className = 'btn'; rs.textContent = '保存镜像源';
            rs.addEventListener('click', function () { cfgData('deploy'); fetch('/api/config/sandbox-registry', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sandbox_registry: cfgState.sandboxRegistry }) }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('镜像源已保存'); }).catch(function () { HOST.alert('保存失败'); }); });
            reg.appendChild(inp);
            reg.appendChild(rs);
            body.appendChild(reg);
          }
          if (st.item && st.item.detail) { const det = HOST.document.createElement('div'); det.className = 'cfg-card-sub'; det.textContent = st.item.detail; body.appendChild(det); }
          const lgToggle = HOST.document.createElement('button');
          lgToggle.className = 'cfg-log-toggle';
          lgToggle.textContent = (cfgState.deployLogOpen[it] ? '收起日志 ▾' : '查看日志 ▸');
          lgToggle.addEventListener('click', function () { cfgState.deployLogOpen[it] = !cfgState.deployLogOpen[it]; draw(); });
          body.appendChild(lgToggle);
          if (cfgState.deployLogOpen[it]) {
            const lgr = HOST.document.createElement('pre');
            lgr.className = 'settings-log';
            lgr.style.minHeight = '80px';
            lgr.textContent = (st.task && st.task.log && st.task.log.length) ? st.task.log.join('\n') : '（暂无日志）';
            body.appendChild(lgr);
          }
          row.appendChild(body);
          list.appendChild(row);
        });
      });
    }
    draw();
    if (deployPollT) clearInterval(deployPollT);
    deployPollT = setInterval(function () {
      if (!HOST.document.body.classList.contains('settings-open')) return;
      delete cfgState.data.deploy;   // 失效缓存
      // 聚焦于列表内输入（如镜像源）时不打断编辑，下个 tick 再重建
      if (HOST.document.activeElement && list.contains(HOST.document.activeElement)) return;
      draw();
    }, 3000);
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
      // 重命名会话：对齐后端 PUT /api/sessions/{id}/rename
      case 'session.rename': {
        const sid = String(payload.session_id || '');
        const alias = String(payload.alias || '').trim();
        if (!sid) throw new Error('缺少 session_id');
        if (!alias) throw new Error('会话名称不能为空');
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid) + '/rename', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ alias }),
        });
        if (!res.ok) throw new Error((await res.text()) || '重命名失败');
        await refreshSessions();
        broadcastSessions('conversation.updated', { session_id: sid });
        return { status: 'ok', alias };
      }
      // 删除会话：对齐后端 DELETE /api/sessions/{id}
      case 'session.delete': {
        const sid = String(payload.session_id || '');
        if (!sid) throw new Error('缺少 session_id');
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid), { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.text()) || '删除失败');
        // 删掉的正是当前会话：清空活动会话（回到欢迎态），并让各 slot 重新对账
        const wasActive = groupState.activeSessionId === sid;
        if (wasActive) groupState.activeSessionId = '';
        await refreshSessions();
        updateEmpty();
        // 只有当前会话被删才需要切换事件；删其它会话不打断正在进行的会话（避免清空乐观消息缓冲）
        broadcastSessions(wasActive ? 'session.switched' : 'conversation.updated', { session_id: groupState.activeSessionId });
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
      // 插件请求「关闭并记住」：与白条开关共用同一状态源（webminConfig.rail.hidden），
      // 重启后保持关闭；白条图标同步置灰，点白条图标即可重新启用
      case 'slot.hide': {
        const pid = origin && origin.pluginId;
        if (!pid) throw new Error('缺少调用方插件');
        setPluginHidden(pid, true);
        const pbtn = railButtons[pid];
        const pdef = groupState.plugins.find((x) => x.id === pid);
        if (pbtn && pdef) updateRailButton(pbtn, pdef);
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
  // 关键：在手柄上做 pointer capture。否则鼠标快速移出手柄条、落到 iframe 上时，
  // pointermove 事件会被 iframe 吞掉，拖拽随即「失去控制」。
  function beginFloatGesture(handle, e, onMove) {
    const pid = e.pointerId;
    try { handle.setPointerCapture(pid); } catch (_) { /* 不支持时退化为仅手柄内有效 */ }
    const move = (ev) => { if (ev.pointerId === pid) onMove(ev); };
    const end = (ev) => {
      if (ev.pointerId !== pid) return;
      try { handle.releasePointerCapture(pid); } catch (_) { /* noop */ }
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', end);
      handle.removeEventListener('pointercancel', end);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  }
  function startFloatDrag(el, e) {
    e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    beginFloatGesture(e.currentTarget, e, (ev) => {
      el.style.right = 'auto';
      el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r0.left + (ev.clientX - sx))) + 'px';
      el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r0.top + (ev.clientY - sy))) + 'px';
    });
  }
  function startFloatResize(el, e) {
    e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    beginFloatGesture(e.currentTarget, e, (ev) => {
      el.style.width = Math.max(160, r0.width + (ev.clientX - sx)) + 'px';
      el.style.height = Math.max(160, r0.height + (ev.clientY - sy)) + 'px';
    });
  }
  // float 尺寸：数字按 px，字符串按 CSS 长度（如 "min(1040px, 96vw)" / "86vh"）
  function applyFloatSize(el, size, i) {
    if (!size) return;
    const w = size.w, h = size.h;
    if (typeof w === 'string' && w) {
      el.style.width = w;
    } else if (Number(w) > 0) {
      const wpx = Number(w);
      el.style.width = wpx + 'px';
      el.style.left = `calc(100% - ${wpx + (i || 0) * 26}px - 16px)`;   // 保持右上角起始
    }
    if (typeof h === 'string' && h) el.style.height = h;
    else if (Number(h) > 0) el.style.height = Number(h) + 'px';
  }
  // 初始居中（须在 appendChild 之后调用，否则拿不到实际尺寸）
  function centerFloat(el) {
    const railEl = HOST.document.getElementById('rail');
    const railW = railEl ? railEl.getBoundingClientRect().width : 0;
    const avail = Math.max(0, HOST.innerWidth - railW);
    const w = el.offsetWidth, h = el.offsetHeight;
    el.style.right = 'auto';
    el.style.left = Math.max(0, Math.round(railW + (avail - w) / 2)) + 'px';
    el.style.top = Math.max(0, Math.round((HOST.innerHeight - h) / 2)) + 'px';
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
  let panelContainerCfg = { opacity: 0.9 }; // 宿主固有中栏容器配置（透明度/运行时宽度）
  let panelSavedWidth = null;      // 用户显式保存的默认宽度（null=最大舒展，不落盘）
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
        activeBySlot['panel'] = '__none__';   // 记住"无"选择（重启后保持空面板）
        persistActive();
        renderPanelContent(st);
        closePanelMenus();
      });
      menu.appendChild(noneItem);
      st.plugins.forEach(({ p }) => {
        const item = HOST.document.createElement('div');
        item.className = 'wm-pp_menu-item' + (p.id === st.activeId ? ' active' : '');
        const g = HOST.document.createElement('span');
        g.className = 'wm-pp_menu-ico';
        paintPluginIcon(g, p);
        item.appendChild(g);
        const nm = HOST.document.createElement('span');
        nm.textContent = p.name || p.id;
        item.appendChild(nm);
        item.addEventListener('click', () => {
          st.activeId = p.id;
          activeBySlot['panel'] = p.id;   // 记住抽屉当前选中的面板插件（重启恢复）
          persistActive();
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
    // ✕ 关闭按钮放右上角：关闭面板容器（统一走 setContainerHidden，同步状态并持久化）
    const closeBtn = HOST.document.createElement('button');
    closeBtn.className = 'wm-pp_drawer';
    closeBtn.textContent = '✕';
    closeBtn.title = '关闭面板';
    closeBtn.addEventListener('click', () => {
      setContainerHidden(true);
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
      // 恢复用户上次抽屉选中的面板插件（含"无"选择），否则取声明顺序第一个
      const saved = activeBySlot['panel'];
      const initial = (saved === '__none__' || byArea.panel.some((x) => x.p.id === saved)) ? saved : byArea.panel[0].p.id;
      st = panelState = { plugins: byArea.panel, activeId: initial, area: 'panel', el: null };
    } else {
      st.plugins = byArea.panel;
      if (st.activeId !== '__none__' && !byArea.panel.some((x) => x.p.id === st.activeId)) st.activeId = byArea.panel[0].p.id;
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
    // 注意：configByPlugin 的唯一初始化点是 applyManifestState（覆盖全部插件），
    // 这里不再覆写，避免用 boot 时的 manifest 旧值冲掉运行中的未保存编辑
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
      slotByPluginId[p.id] = s;   // 全插件登记（含未挂载者），供显隐换算反查
    });
  }

  // ---- 动态挂载全部类型窗口（type：fixed 锚定单例 / panel 分栏抽屉 / float 弹窗多开） ----
  function mountAll() {
    // 1) fixed：按 area 挂到 html 锚定容器；优先挂载用户上次选中的插件（activeBySlot），否则取第一个
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'fixed') return;
      const chosen = list.find((x) => x.id === activeBySlot[sid]) || list[0];
      pluginBySlot[sid] = chosen;
      frames[sid] = [];
      const mainEl = HOST.document.querySelector(`[data-slot="${sid}"]`);
      if (!mainEl) return;
      slotByPluginId[chosen.id] = sid;
      const fr = mountFrame(mainEl, chosen);
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
        // 插件可声明默认尺寸（slot.size={w,h}：数字=px，字符串=CSS 长度）
        applyFloatSize(el, def.size, i);
        HOST.document.body.appendChild(el);
        // 声明 center 的弹窗初始居中（居中区域避开左侧白条，组件窗口绝不伸入白条）
        if (def.center) centerFloat(el);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(el, p);
        if (fr) frames[sid].push(fr);
        attachFloatHandles(el);
      });
    });
    reconcilePanels();
  }

  // ---- 刷新 manifest 并重建/挂载 ----
  // manifest → 宿主内存态的唯一装配点：插件表、全量插件配置、图标栏状态、面板容器配置、单例槽选择
  function applyManifestState(manifest) {
    groupState.plugins = manifest.plugins || [];
    // 为「全部」插件建立有效配置（schema 默认值 ∪ 已存值）。
    // 关键：未挂载插件（如非当前抽屉选中的面板插件）的已存配置也要进入 configByPlugin，
    // 否则设置面板展示默认值、整体保存时还会把它的已存配置覆写丢失。
    groupState.plugins.forEach((p) => { configByPlugin[p.id] = effectiveConfig(p); });
    // 图标栏持久化状态
    const railSaved = manifest.rail;
    if (railSaved && typeof railSaved === 'object') {
      const stage = Number(railSaved.stage);
      railState.stage = (stage >= 0 && stage < RAIL_STAGES) ? stage : 1;
      railState.hidden = (railSaved.hidden && typeof railSaved.hidden === 'object') ? railSaved.hidden : {};
      railState.opacity = (typeof railSaved.opacity === 'number') ? railSaved.opacity : 1;
    }
    // 面板容器配置（宿主资产，存于 plugins['panel-container']）
    const savedPanel = (manifest.panelContainer && typeof manifest.panelContainer === 'object') ? manifest.panelContainer : {};
    panelSavedWidth = (Number(savedPanel.width) >= 260) ? Number(savedPanel.width) : null;
    panelContainerCfg = { opacity: (typeof savedPanel.opacity === 'number') ? savedPanel.opacity : 0.9 };
    if (panelSavedWidth != null) panelContainerCfg.width = panelSavedWidth;
    configByPlugin['panel-container'] = Object.assign({}, savedPanel);
    // 单例槽选中项（剔除已卸载插件的残留）
    const savedActive = (manifest.active && typeof manifest.active === 'object') ? manifest.active : {};
    const ids = new Set(groupState.plugins.map((p) => p.id));
    Object.keys(activeBySlot).forEach((k) => delete activeBySlot[k]);
    Object.keys(savedActive).forEach((k) => {
      const v = savedActive[k];
      if (v === '__none__' || ids.has(v)) activeBySlot[k] = v;
    });
  }
  async function loadManifest() {
    const manifest = await (await fetch('/api/webmin/manifest')).json();
    applyManifestState(manifest);
  }
  async function reloadManifest() {
    await loadManifest();
    buildSlotIndex();
    mountAll();
    applyPersistedHidden();
    buildRail();
    applyPanelContainerCfg();
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
    // 弹出菜单（设置卡片 ▾ / 面板抽屉 ☰）都挂在 body 上：点界面空白处统一收起。
    // 触发按钮自身的 click 已 stopPropagation，因此不会误关刚打开的菜单。
    HOST.document.addEventListener('click', function () { closeSettingsMenus(); closePanelMenus(); });
    let manifest;
    try {
      manifest = await (await fetch('/api/webmin/manifest')).json();
    } catch (err) {
      HOST.document.body.innerHTML =
        '<div style="padding:24px;font-family:system-ui;color:#8b96a3">极简模式无法加载：后端未在线（/api/webmin/manifest 不可用）。请先启动后端。</div>';
      return;
    }
    applyManifestState(manifest);
    applyRailOpacity();
    buildSlotIndex();
    mountAll();
    bindRailToggle();
    buildRail();
    applyPanelContainerCfg();
    // 应用持久化的插件隐藏状态（需在挂载后重设，避免被 iframe 覆盖样式）
    applyPersistedHidden();

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