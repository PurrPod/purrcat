/* ============================================================
   web-minimal 宿主核心（白灰改造版）
   - 加载 /api/webmin/manifest 拿到插件清单 + configSchema + config
   - 按 slot 把插件渲染为 iframe；每个 slot 挂载首个匹配插件
   - callAction 动作总线：
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
    activeBranchId: 'main',   // 当前查看的分支视图（main / 子代理分支），供输入框判定只读
    sessions: [],
    empty: true,
    // 草稿态：点「新建会话」后不落盘、不进列表，仅前端占位欢迎界面；
    // 首条消息发送时才按 draftParadigm 建会话并生成系统提示词。
    draft: false,
    draftParadigm: '',
    plugins: [],              // manifest 注解后的插件列表（供设置面板使用）
  };
  // 最左图标栏状态：stage 0=仅图标 1=图标+文字；hidden=各插件隐藏开关（持久化）；opacity=白条透明度
  const railState = { stage: 0, hidden: {}, opacity: 1 };
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
    'panel-top': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/>',
    'layout-panel-left': '<rect width="7" height="18" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    // sensor 默认图标（配置项未提供 icon 或图标加载失败时回退）
    sensor: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
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
  const RAIL_STAGES = 2;   // 0=仅图标；1=图标+文字
  function isRailPlugin(p) { return p && p.entry; }
  function railHidden(id) { return !!(railState.hidden && railState.hidden[id]); }
  function applySlotHidden(slot, hidden) {
    // fixed：锚定容器
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (anchor) anchor.style.display = hidden ? 'none' : '';
    if (slot === 'sidebar') {
      HOST.document.body.classList.toggle('rail-nosidebar', !!hidden);
      applyPanelWidth();   // 侧栏显隐改变可用区域，面板宽度需重新夹紧
    }
    // session：会话面板（历史 + 输入合并）的启停改变右侧需预留的宽度，面板宽度需重算
    if (slot === 'session') applyPanelWidth();
    // float：自由浮窗实例（data-fslot=slot）
    HOST.document.querySelectorAll(`.wm-float[data-fslot="${slot}"]`).forEach((el) => {
      el.style.display = hidden ? 'none' : 'block';
    });
    // modal：模态弹窗（data-mslot=slot），连遮罩一起显隐
    HOST.document.querySelectorAll(`.wm-modal-wrap[data-mslot="${slot}"]`).forEach((el) => {
      el.style.display = hidden ? 'none' : 'flex';
    });
    // panel：内容插件驻宿主单例容器（data-pslot=panel），隐藏/显示容器并切换让位
    if (slot === 'panel') {
      HOST.document.querySelectorAll('.wm-ppanel[data-pslot="panel"]').forEach((el) => {
        el.style.display = hidden ? 'none' : 'flex';
      });
      // 由第三方容器插件入驻时的容器锚点（内置容器另由 .wm-ppanel 统辖）同样受总开关统辖
      const pcHost = HOST.document.querySelector('[data-slot="panel-container"]');
      if (pcHost && thirdPartyContainerPlugin()) pcHost.style.display = hidden ? 'none' : '';
      if (hidden) { HOST.document.body.classList.remove('has-panels'); if (panelBar) panelBar.style.display = 'none'; }
      else {
        HOST.document.body.classList.add('has-panels');
        if (panelBar) panelBar.style.display = '';
        applyPanelWidth();   // 重新打开面板时按当前窗口宽度夹紧
      }
    }
    syncNativeCover();
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
      if (id === PANEL_CONTAINER_ID) return;   // 内置容器是 fixed 插件，由 refreshFixedSlot 重算
      const slot = slotOfPlugin(id);
      if (!slot || !railState.hidden[id]) return;
      // fixed 区域：关闭是按「插件」记录的，不能据此把整个区域隐藏掉（否则同区域插件连坐，
      // 例如关掉「涂鸦会话」会把原生会话一起隐藏）。该区域的显隐由 refreshFixedSlot
      // 依据各插件开关重算，这里跳过。
      // panel 内容插件同理：单个插件被关闭只应让该插件从中栏容器里消失，而不是把整个
      // 面板容器关掉（容器的显隐见下方 panelContainerVisible 的统一计算）。
      const p = groupState.plugins.find((x) => x.id === id);
      const pt = p ? (p.slotDef || {}).type : '';
      if (pt === 'fixed' || pt === 'panel') return;
      applySlotHidden(slot, true);
    });
    // 中栏容器：内置容器与入驻插件同属一个区域，谁生效都占位，两个候选全部关闭才让出中栏
    applySlotHidden('panel', !panelContainerVisible());
  }
  function applyRailStage() {
    HOST.document.body.classList.remove('rail-0', 'rail-1');
    HOST.document.body.classList.add('rail-' + railState.stage);
    const t = HOST.document.getElementById('railToggle');
    if (t) {
      // 图标形态固定不变，仅通过展开/收起影响侧栏布局
      paintIcon(t, 'panel-left', '☰');
      t.title = '收起 / 展开插件栏';
    }
    // 白条宽度变化（48px ↔ 196px）会改变可用区域：弹窗需重排，
    // 否则居中弹窗的左缘会被展开后的白条压住；面板容器宽度也需重新夹紧
    reflowFloats();
    applyPanelWidth();
  }
  function applyRailOpacity() {
    let o = typeof railState.opacity === 'number' ? railState.opacity : 1;
    o = Math.min(1, Math.max(0, o));
    const rail = HOST.document.getElementById('rail');
    if (rail) rail.style.setProperty('--wm-rail-bg', 'rgba(255,255,255,' + o.toFixed(3) + ')');
  }
  function cycleRail() {
    railState.stage = (railState.stage + 1) % RAIL_STAGES;   // 0→1→0
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
    if (slot) {
      const p = groupState.plugins.find((x) => x.id === id);
      // fixed：单例槽内多个插件互斥，开关只作用于该插件本身，区域的显隐按插件开关重算
      if (p && (p.slotDef || {}).type === 'fixed') refreshFixedSlot(slot);
      else applySlotHidden(slot, hidden);
    }
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
    // 1) 固定区域（同区域互斥，最多一个生效）：按「区域」共用一个图标——同区域多个插件
    //    （如原生会话 / 涂鸦会话）不再各占一个图标，避免认知负担；点击弹出候选菜单切换。
    fixedAreaIds().forEach((area) => { iconsEl.appendChild(makeAreaRailButton(area)); });
    // 2) 多实例类型（float 自由浮窗 / modal 模态弹窗，可多个同时存在）：逐个插件各占一个图标。
    //    panel 内容插件不进白条，由「面板容器」区域图标统辖。
    groupState.plugins
      .filter(isRailPlugin)
      .filter((p) => {
        const t = (p.slotDef || {}).type;
        return t === 'float' || t === 'modal';
      })
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
        railButtons[p.id] = btn;    // 登记，供开合状态即时刷新高亮
        btn.addEventListener('click', () => {
          if (p.railAction) { callAction(p.railAction, {}).catch(() => {}); return; }  // 例如设置 → 打开设置面板
          // float / modal：开=显示实例，关=隐藏（与设置面板同一套开关语义）
          togglePluginOpen(p);
          buildRail();
        });
        iconsEl.appendChild(btn);
      });
    // 面板容器（内置容器）不再单列开关：它是 panel-container 区域的候选之一，
    // 已并入上方的「区域图标」（见 makeAreaRailButton / areaCandidates）。
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
    // 与区域/插件图标一致：未打开设置时按「关闭」态变淡，打开时高亮
    const sbOpen = HOST.document.body.classList.contains('settings-open');
    sb.classList.toggle('on', sbOpen);
    sb.classList.toggle('off', !sbOpen);
    sb.addEventListener('click', () => setSettingsOpen(!HOST.document.body.classList.contains('settings-open')));
    iconsEl.appendChild(sb);
    railButtons['__settings__'] = sb;
    applyRailOpacity();
  }

  // ---- 固定区域：白条按区域合并图标（同区域互斥，最多一个生效）----
  // 区域显示名复用设置面板的 AREA_LABEL（单一来源，见下方「UI 插件主面板」分组）
  // 「内置容器」是真实的内置插件（plugins/builtin/builtin-panel）：与第三方容器插件
  // （如涂鸦面板容器）同属 panel-container 区域、等位互斥，白条上可按区域独立开关。
  // 它的外壳结构与样式由该插件自己的 index.html 提供，宿主只按其渲染（见 renderPanel）。
  const PANEL_CONTAINER_ID = 'builtin-panel';
  // 面板容器区域在白条/菜单里的统一字形：窗口 + 顶部标签条
  const PANEL_AREA_ICON = 'panel-top';
  function areaLabel(area) { return AREA_LABEL[area] || area; }
  // 需要按区域合并图标的固定区域（type=fixed）
  function fixedAreaIds() {
    return Object.keys(slotMap).filter((sid) => {
      const list = slotMap[sid] || [];
      return list.length > 0 && (list[0].slotDef || {}).type === 'fixed';
    });
  }
  // 区域候选：即声明该区域的插件（内置容器也是一个普通插件，不再有合成候选）
  function areaCandidates(area) {
    return (slotMap[area] || []).slice();
  }
  // 区域当前生效的候选（全部关闭时返回 null）——即该区域当前挂载的那个插件
  function areaActive(area) {
    return pluginBySlot[area] || null;
  }
  // 切换区域到某个候选：固定区域统一走 activateSlotPlugin（同区域互斥 + 持久化 + 即时重挂）
  function activateAreaCandidate(area, cand) {
    if (cand) activateSlotPlugin(cand);
  }
  // 关闭整个区域：区域内全部候选一起让位（内置容器与容器插件互斥，一起关才真正空出中栏）
  function deactivateArea(area) {
    if (!railState.hidden) railState.hidden = {};
    (slotMap[area] || []).forEach((p) => { railState.hidden[p.id] = true; });
    refreshFixedSlot(area);
    persistRail().catch(() => {});
  }
  // 重算区域图标的 on/off 与字形（内置容器与入驻插件互斥切换、开关变化后即时刷新）
  function refreshAreaRail(area) {
    const btn = railButtons['__area__:' + area];
    if (!btn) return;
    const active = areaActive(area);
    btn.classList.remove('on', 'off');
    btn.classList.add(active ? 'on' : 'off');
    const g = btn.querySelector('.rail-glyph');
    if (!g) return;
    // 区域候选统一按插件图标渲染；区域空无插件时回落到面板容器字形，避免文本兜底
    const target = active || areaCandidates(area)[0] || null;
    if (target) paintPluginIcon(g, target);
    else paintIcon(g, PANEL_AREA_ICON, '▤');
  }
  // 区域图标：区域生效=on；点击弹出候选菜单（仅一个候选时直接开/关）
  function makeAreaRailButton(area) {
    const btn = HOST.document.createElement('button');
    btn.className = 'rail-ico';
    btn.title = areaLabel(area);
    const g = HOST.document.createElement('span');
    g.className = 'rail-glyph';
    btn.appendChild(g);
    const nm = HOST.document.createElement('span');
    nm.className = 'rail-name';
    nm.textContent = areaLabel(area);
    btn.appendChild(nm);
    railButtons['__area__:' + area] = btn;
    refreshAreaRail(area);
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();   // 触发按钮自身阻止冒泡，避免被 body 的统一收起立刻关掉菜单
      const cands = areaCandidates(area);
      const active = areaActive(area);
      if (cands.length <= 1) {
        if (active) deactivateArea(area);
        else if (cands[0]) activateAreaCandidate(area, cands[0]);
        buildRail();
        return;
      }
      openAreaMenu(area, btn, cands, active);
    });
    return btn;
  }
  // 区域候选菜单：列出该区域全部候选（含内置容器），点击即切换；区域生效时附「关闭」项
  function openAreaMenu(area, anchor, cands, active) {
    const already = HOST.document.getElementById('rail-area-menu');
    closePanelMenus();
    if (already) return;   // 再次点同一区域图标 = 收起
    const menu = HOST.document.createElement('div');
    menu.className = 'wm-pp_menu';
    menu.id = 'rail-area-menu';
    cands.forEach((c) => {
      const isActive = !!active && active.id === c.id;
      const item = HOST.document.createElement('div');
      item.className = 'wm-pp_menu-item' + (isActive ? ' active' : '');
      const g = HOST.document.createElement('span');
      g.className = 'wm-pp_menu-ico';
      paintPluginIcon(g, c);
      item.appendChild(g);
      const nm = HOST.document.createElement('span');
      nm.textContent = c.name || c.id;
      item.appendChild(nm);
      if (isActive) {
        const tag = HOST.document.createElement('span');
        tag.className = 'wm-pp_menu-tag';
        tag.textContent = '使用中';
        item.appendChild(tag);
      }
      item.addEventListener('click', () => { closePanelMenus(); activateAreaCandidate(area, c); buildRail(); });
      menu.appendChild(item);
    });
    if (active) {
      const off = HOST.document.createElement('div');
      off.className = 'wm-pp_menu-item';
      const og = HOST.document.createElement('span');
      og.className = 'wm-pp_menu-ico';
      paintIcon(og, 'x', '✕');
      off.appendChild(og);
      const onm = HOST.document.createElement('span');
      onm.textContent = '关闭' + areaLabel(area);
      off.appendChild(onm);
      off.addEventListener('click', () => { closePanelMenus(); deactivateArea(area); buildRail(); });
      menu.appendChild(off);
    }
    HOST.document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const top = Math.min(r.top, HOST.innerHeight - menu.offsetHeight - 8);
    menu.style.left = (r.right + 6) + 'px';
    menu.style.right = 'auto';
    menu.style.top = Math.max(8, top) + 'px';
    syncNativeCover();
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
    broadcast('session', 'layout.empty', { empty: !!v });
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
    // 切换会话：分支视图一律回到主干，并广播给输入框等插件（子代理视图只读）
    if (event === 'session.switched') {
      groupState.activeBranchId = 'main';
      broadcastAll('branch.switched', { branch_id: 'main' });
    }
    broadcast('session', event, data);
    broadcast('sidebar', event, data);
  }

  // ---- 设置面板开合（宿主固有资产，非插件）：原生渲染到 .settings-body ----
  function setSettingsOpen(open) {
    HOST.document.body.classList.toggle('settings-open', !!open);
    // 设置按钮高亮跟随面板开合
    const sb = HOST.document.getElementById('railSettings');
    if (sb) {
      sb.classList.toggle('on', !!open);
      sb.classList.toggle('off', !open);
    }
    if (!open) closeSettingsMenus();   // 菜单挂在 body 上，面板关掉后不能留在界面上
    if (open) renderSettings();
    syncNativeCover();
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
        panelDesiredWidth = null;
        applyPanelWidth();
        settingsSavePanel();
        return;
      }
      const w = Number(num.value);
      if (w >= 260) {
        panelSavedWidth = w;
        panelDesiredWidth = w;
        applyPanelWidth();
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

  // 依赖类型 / 放置根 → 展示文案（plugin.json 的 dependency / root 字段）
  const DEP_KIND_LABEL = { skill: '技能', plugin: '插件', mcp: 'MCP', agentloop: 'AgentLoop', sensor: '传感器', graph: '图谱' };
  const ROOT_KIND_LABEL = { builtin: '内置', sandbox: '沙盒', user: '用户' };
  // 插件卡片元信息行：声明放置位置（root）不一致告警与依赖清单（dependency）；
  // 实际来源（origin）已并入标题行，与「面板/未显示」等 chip 同行展示。
  function renderPluginMeta(card, p) {
    const row = HOST.document.createElement('div');
    row.className = 'cfg-card-meta';
    const chip = (text, cls) => {
      const el = HOST.document.createElement('span');
      el.className = 'p-tag' + (cls ? ' ' + cls : '');
      el.textContent = text;
      return el;
    };
    // 声明了 root 却与实际放置位置不符 → 标黄提示
    if (p.root && p.rootOk === false) {
      row.appendChild(chip('声明 ' + (ROOT_KIND_LABEL[p.root] || p.root), 'warn'));
      row.appendChild(chip('⚠ 放置位置与声明不一致', 'warn'));
    }
    const deps = Array.isArray(p.dependency) ? p.dependency : [];
    if (deps.length) {
      const lb = HOST.document.createElement('span');
      lb.className = 'meta-label';
      lb.textContent = '依赖';
      row.appendChild(lb);
      deps.forEach((d) => row.appendChild(chip((DEP_KIND_LABEL[d.type] || d.type) + ' · ' + d.id)));
    }
    if (row.childNodes.length) card.appendChild(row);
  }

  // 插件卡片（与配置中心统一的 cfg-card 风格）：标题/行为chip/状态chip + 打开关闭 + 抽屉菜单 + 可视化字段
  function renderPluginCard(container, p, cfg) {
    const type = (p.slotDef || {}).type || 'fixed';
    const typeName = type === 'fixed' ? '固定' : (type === 'panel' ? '面板' : (type === 'modal' ? '模态' : '浮窗'));
    const vis = pluginVisible(p);
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    const h = cfgCardHead(card, p.name || p.id, typeName, p.id);
    // 状态 chip：panel 表达"容器当前显示哪个"；fixed/float 表达启停
    const st = HOST.document.createElement('span');
    st.className = 'cfg-chip ' + (vis ? 'on' : 'off');
    st.textContent = type === 'panel' ? (vis ? '显示中' : '未显示') : (vis ? '已启用' : '已关闭');
    h.titleRow.appendChild(st);
    // 来源 chip：插件实际所在根（plugin.json 的 root → 后端回填 origin），
    // 与「面板/未显示」等 chip 同行，直接显示「内置/沙盒/用户」。
    const originName = ROOT_KIND_LABEL[p.origin] || p.origin || '';
    if (originName) {
      const oc = HOST.document.createElement('span');
      oc.className = 'cfg-chip type';
      oc.textContent = originName;
      h.titleRow.appendChild(oc);
    }
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
    // 来源 / 声明位置 / 依赖（plugin.json 的 root / dependency 字段）
    renderPluginMeta(card, p);
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
  const CONFIG_NAV = ['plugins', 'model', 'sensor', 'file', 'mcp', 'app', 'soul', 'acp', 'deploy'];
  const CONFIG_LABEL = { plugins: 'UI 插件', model: '模型', sensor: '传感器', file: '文件', mcp: 'MCP', app: '应用', soul: '全局人设', acp: 'ACP', deploy: '部署' };
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
    rail: '左侧白条', sidebar: '会话列表', session: '会话', background: '背景',
    'panel-container': '面板容器', panel: '面板',
    pet: '浮窗类', popup: '模态弹窗',
  };
  // 宿主原生资产（非插件）挂在所属区域内；singleton 标记「同区域同时只能启用一个插件」
  const UI_GROUPS = [
    { area: 'rail', host: renderRailAppearance },
    { area: 'sidebar', singleton: true },
    { area: 'session', singleton: true },
    { area: 'background', singleton: true },
    { area: 'panel-container', singleton: true, host: renderPanelContainerSettings },
    { area: 'panel' },
    { area: 'pet' },
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

  // 全局人设：SOUL.md 在线编辑（GET/PUT /api/config/markdown/SOUL，落盘 ~/.purrcat/core/SOUL.md）
  function renderSoulEditor(main) {
    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '全局人设 SOUL.md：只有在 AgentLoop / Graph 等流程中显式引用 @SOUL 时，此内容才会注入对应 Agent（是否注入取决于具体实现），并非所有 Agent 自动携带（落盘 ~/.purrcat/core/SOUL.md）。';
    main.appendChild(tip);
    const tx = HOST.document.createElement('textarea');
    tx.className = 'settings-json';
    tx.spellcheck = false;
    tx.placeholder = '读取中…';
    main.appendChild(tx);
    const status = HOST.document.createElement('span');
    status.className = 'p-tag';
    fetch('/api/config/markdown/SOUL').then(function (r) { return r.json(); }).then(function (d) {
      tx.value = (d && d.content) || '';
      status.textContent = '已加载';
    }).catch(function () { status.textContent = '加载失败'; });
    const bar = HOST.document.createElement('div');
    bar.className = 'settings-actions';
    const save = HOST.document.createElement('button');
    save.className = 'btn cfg-save';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      save.disabled = true;
      status.textContent = '保存中…';
      fetch('/api/config/markdown/SOUL', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: tx.value }) })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
        .then(function () { save.disabled = false; status.textContent = '已保存'; })
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
      if (railHidden(PANEL_CONTAINER_ID)) return false;   // 中栏容器被关闭时，其内标签自然不生效
      return panelTabs.indexOf(p.id) >= 0;   // 多标签：处于已打开标签页即视为生效
    }
    return true;   // float：未隐藏即生效
  }
  function closeSettingsMenus() {
    HOST.document.querySelectorAll('.settings-card-menu').forEach(function (m) { m.remove(); });
    syncNativeCover();
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
    syncNativeCover();
  }

  // 把某插件置为对应槽位的当前活动实例（fixed 卸旧挂新；panel 切换抽屉选中），并持久化用户选择
  function activateSlotPlugin(p) {
    const slot = p.slot;
    const type = (p.slotDef || {}).type;
    if (type === 'panel') {
      // 多标签容器：把该插件打开为标签页并激活（未打开则新增，已打开则聚焦）
      openPanelTab(p.id);
      return;
    }
    if (type === 'fixed') {
      // 单例槽互斥：先把同区域其它插件全部关掉，再打开目标插件（占位者自动让位）
      if (!railState.hidden) railState.hidden = {};
      (slotMap[slot] || []).forEach((x) => { if (x.id !== p.id) railState.hidden[x.id] = true; });
      delete railState.hidden[p.id];
      // 中栏容器区域：容器插件入驻即让内置容器让位（容器仍占位，由该插件提供）
      if (slot === 'panel-container' && p.id !== PANEL_CONTAINER_ID) railState.hidden[PANEL_CONTAINER_ID] = true;
      activeBySlot[slot] = p.id;   // 记住该单例槽当前选中的插件
      refreshFixedSlot(slot);
      buildRail();
      persistActive();
      persistRail().catch(() => {});
      return;
    }
    // float：自由浮窗无单例约束，直接显示
    if (railHidden(p.id)) setPluginHidden(p.id, false);
    buildRail();
  }
  function togglePluginOpen(p) {
    const type = (p.slotDef || {}).type;
    // 多标签容器：对某面板插件的开/关 = 新开 / 关闭它对应的标签页
    if (type === 'panel') {
      if (pluginVisible(p)) closePanelTab(p.id);
      else openPanelTab(p.id);
      return;
    }
    if (pluginVisible(p)) {   // 关闭：fixed=隐藏锚定区；float=隐藏实例
      setPluginHidden(p.id, true); buildRail();
      return;
    }
    // 打开：fixed 单例槽——同区域已有别的插件在运行时先关掉占位者再打开目标，
    // 互斥规则统一由 activateSlotPlugin 处理
    activateSlotPlugin(p);   // float 无单例约束，直接显示
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
    diskLogOpen: false,
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
  // 运行时重载端点：sensor/mcp 的配置在子进程 spawn 时固化，写盘后必须通知运行中的
  // 实例重载（重启进程 / 重建 schema 与检索索引），否则「保存了但没生效」。
  const RELOAD_EP = { sensor: '/api/config/sensor/reload', mcp: '/api/config/mcp/reload' };
  async function reloadRuntime(tab) {
    const ep = RELOAD_EP[tab];
    if (!ep) return null;
    const r = await fetch(ep, { method: 'POST' });
    const body = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error((body && body.detail) || ('HTTP ' + r.status));
    return body;
  }
  async function putCfg(tab, obj) {
    cfgState.data[tab] = obj;
    const r = await fetch('/api/config/' + tab, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    // 对齐完整模式：切换开关保存后自动重载。重载失败不阻断保存（可点「重载到内存」重试）
    if (RELOAD_EP[tab]) {
      try { await reloadRuntime(tab); } catch (e) { /* 见上 */ }
    }
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
    // 支持刷新：丢弃本地缓存，重新从磁盘拉取该 tab 的配置并重绘
    const rf = HOST.document.createElement('button');
    rf.className = 'cfg-seg cfg-reload';
    rf.textContent = '刷新';
    rf.title = '丢弃本地缓存，重新从磁盘读取配置并重绘';
    rf.addEventListener('click', function () {
      delete cfgState.data[key];
      cfgState.openKey = cfgState.openKey || {};
      delete cfgState.openKey[key];
      fn(main, key);
    });
    tb.appendChild(rf);
    // sensor/mcp：手动强制重载（改了 ~/.purrcat 下的代码或外部配置文件时用）
    if (RELOAD_EP[key]) {
      const rl = HOST.document.createElement('button');
      rl.className = 'cfg-seg cfg-reload';
      rl.textContent = '重载到内存';
      rl.title = '让磁盘上的配置与代码立即生效（重启子进程 / 重建索引），无需重启应用';
      rl.addEventListener('click', function () {
        rl.disabled = true;
        rl.textContent = '重载中…';
        reloadRuntime(key)
          .then(function (d) { HOST.alert((d && d.message) || '已重载到内存'); })
          .catch(function (e) { HOST.alert('重载失败：' + (e && e.message || '')); })
          .finally(function () { rl.disabled = false; rl.textContent = '重载到内存'; });
      });
      tb.appendChild(rl);
    }
    main.appendChild(tb);
    return tb;
  }

  function renderConfigSection(main, key) {
    if (key === 'acp') return renderAcpCard(main);
    if (key === 'deploy') return renderDeployCards(main);
    if (key === 'soul') return renderSoulEditor(main);
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
  function cfgIcon(url) {
    const wrap = HOST.document.createElement('span');
    wrap.className = 'cfg-card-icon';
    const useDefault = function () {
      wrap.innerHTML = '<svg ' + ICON_SVG_ATTR + '>' + ICON_SVG.sensor + '</svg>';
    };
    const u = String(url == null ? '' : url).trim();
    if (!u) { useDefault(); return wrap; }
    const img = HOST.document.createElement('img');
    img.alt = '';
    img.referrerPolicy = 'no-referrer';
    // 图标链接加载失败时回退默认图标
    img.onerror = function () { if (img.parentNode) { img.parentNode.removeChild(img); } useDefault(); };
    img.src = u;
    wrap.appendChild(img);
    return wrap;
  }
  function cfgCardHead(card, title, kind, sub, iconUrl) {
    const head = HOST.document.createElement('div');
    head.className = 'cfg-card-head';
    const left = HOST.document.createElement('div');
    left.className = 'cfg-card-head-l';
    const trow = HOST.document.createElement('div');
    trow.className = 'cfg-card-title';
    // 传入 iconUrl（含空串）时展示头像：有链接用图片，留空或加载失败回退默认图标
    if (iconUrl !== undefined) trow.appendChild(cfgIcon(iconUrl));
    const t = HOST.document.createElement('span');
    t.className = 'cfg-card-name';
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
  // sensor 后台进程表：name -> {pid, alive}（配置页展示「运行中/未运行」与停止按钮）
  function sensorRuntimeMap() {
    return fetch('/api/config/sensor/runtime')
      .then(function (r) { return r.json(); })
      .then(function (d) { const m = {}; ((d && d.running) || []).forEach(function (s) { m[s.name] = s; }); return m; })
      .catch(function () { return {}; });
  }
  function renderGenericCards(main, key) {
    const isSensor = key === 'sensor';
    Promise.all([cfgData(key), isSensor ? sensorRuntimeMap() : Promise.resolve({})]).then(function (res) {
      const obj = res[0] || {};
      const runMap = res[1] || {};
      const keys = Object.keys(obj).filter(function (k) { return k !== '__ARRAY_WRAPPER__'; });
      if (keys.length === 0) { const e = HOST.document.createElement('div'); e.className = 'p-tag'; e.textContent = '（空配置）'; main.appendChild(e); }
      keys.forEach(function (k) {
        const val = obj[k];
        const isOpen = cfgState.openKey[key] === k;
        const card = cfgCard(main);
        const raw = (typeof val === 'object') ? JSON.stringify(val) : String(val);
        const rt = isSensor ? runMap[k] : null;
        const running = !!(rt && rt.alive);
        // sensor：卡片头展示 icon（config 里的 icon 链接，留空/失效回退默认图标）
        const iconArg = (isSensor && val && typeof val === 'object') ? (val.icon || '') : undefined;
        // 卡片不展示配置内容（env 等含凭证），其值只在展开编辑时才呈现
        const sub = isSensor ? '' : (raw.slice(0, 90) + (raw.length > 90 ? '…' : ''));
        const h = cfgCardHead(card, k, (Array.isArray(val) ? 'array' : typeof val), sub, iconArg);
        if (isSensor) {
          const st = HOST.document.createElement('span');
          st.className = 'cfg-chip ' + (running ? 'on' : 'off');
          st.textContent = running ? '运行中' : '未运行';
          if (running && rt.pid) st.title = 'PID ' + rt.pid;
          h.titleRow.appendChild(st);
        }
        // 运行中的 sensor 可直接停止：杀进程 + 置 enabled=false
        if (isSensor && running) {
          const stopBtn = HOST.document.createElement('button');
          stopBtn.className = 'btn cfg-stop';
          stopBtn.textContent = '停止';
          stopBtn.title = '杀死该 Sensor 后台进程，并在配置里置为 enabled=false';
          stopBtn.addEventListener('click', function () {
            if (!HOST.confirm('停止 Sensor "' + k + '"？将杀死其后台进程并置为 enabled=false。')) return;
            stopBtn.disabled = true;
            stopBtn.textContent = '停止中…';
            fetch('/api/config/sensor/' + encodeURIComponent(k) + '/stop', { method: 'POST' })
              .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
              .then(function () { delete cfgState.data[key]; delete cfgState.openKey[key]; rerenderConfig(main, key); })
              .catch(function (e) { stopBtn.disabled = false; stopBtn.textContent = '停止'; HOST.alert('停止失败：' + (e && e.message || '')); });
          });
          h.right.appendChild(stopBtn);
        } else if (isSensor) {
          // 未运行（被停止或启动失败）时才给「重启」：置 enabled=true 后重新拉起进程
          const restartBtn = HOST.document.createElement('button');
          restartBtn.className = 'btn cfg-restart';
          restartBtn.textContent = '重启';
          restartBtn.title = '置为 enabled=true 并重新拉起该 Sensor 后台进程';
          restartBtn.addEventListener('click', function () {
            if (!HOST.confirm('重启 Sensor "' + k + '"？将置为 enabled=true 并重新拉起后台进程。')) return;
            restartBtn.disabled = true;
            restartBtn.textContent = '重启中…';
            fetch('/api/config/sensor/' + encodeURIComponent(k) + '/restart', { method: 'POST' })
              .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
              .then(function (b) {
                delete cfgState.data[key]; delete cfgState.openKey[key];
                rerenderConfig(main, key);
                if (b && b.started === false) HOST.alert('重启未成功：' + ((b && b.message) || '请检查本地 <name>.py 与 uv'));
              })
              .catch(function (e) { restartBtn.disabled = false; restartBtn.textContent = '重启'; HOST.alert('重启失败：' + (e && e.message || '')); });
          });
          h.right.appendChild(restartBtn);
        }
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
        // sensor：删除键旁再挂一个箭头，展开下拉提供「彻底删除」（连正式文件一起删）
        if (isSensor) {
          const more = HOST.document.createElement('button');
          more.className = 'btn cfg-caret';
          more.textContent = '▾';
          more.title = '更多删除选项';
          more.addEventListener('click', function (ev) {
            ev.stopPropagation();   // 别让全局 click 把刚弹出的菜单立刻收掉
            const owner = 'cfg-' + k;
            const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + owner + '"]');
            closeSettingsMenus();
            if (wasOpen) return;   // 再点一次同一个箭头 = 收起
            const menu = HOST.document.createElement('div');
            menu.className = 'settings-card-menu';
            menu.setAttribute('data-owner', owner);
            const purge = HOST.document.createElement('button');
            purge.className = 'settings-menu-btn danger';
            purge.textContent = '彻底删除（连文件）';
            purge.addEventListener('click', function () {
              closeSettingsMenus();
              if (!HOST.confirm('彻底删除 Sensor "' + k + '"？将杀死其进程、删除正式文件 ' + k + '.py 并从配置移除，不可恢复。')) return;
              fetch('/api/config/sensor/' + encodeURIComponent(k) + '/purge', { method: 'POST' })
                .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
                .then(function () { delete cfgState.data[key]; delete cfgState.openKey[key]; rerenderConfig(main, key); })
                .catch(function (e) { HOST.alert('彻底删除失败：' + (e && e.message || '')); });
            });
            menu.appendChild(purge);
            HOST.document.body.appendChild(menu);
            const b = more.getBoundingClientRect();
            menu.style.right = (HOST.innerWidth - b.right) + 'px';
            menu.style.top = (b.bottom + 4) + 'px';
            syncNativeCover();
          });
          h.right.appendChild(more);
        }
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

  // ---- acp：接入卡片 ----
  function renderAcpCard(main) {
    const sec = makeSection('ACP 接入', main);
    const card = cfgCard(sec);
    const h = cfgCardHead(card, 'ACP 编辑器接入', 'relay');
    fetch('/api/config/acp').then(function (r) { return r.json(); }).then(function (d) {
      const sub = HOST.document.createElement('div');
      sub.className = 'cfg-card-sub';
      sub.textContent = 'relay 已部署:' + (d.relay_deployed ? '是' : '否') + ' · 与源一致:' + (d.relay_matches_source ? '是' : '否') + ' · uv:' + (d.uv_found ? '可用' : '缺失')
        + (d.actual_port ? ' · 实际端口:' + d.actual_port + (d.port_mismatch ? '（与设置不一致，relay 生效的是实际端口）' : '') : '');
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
    // 磁盘维护卡片：只读展示 vhdx 空洞，用户点按钮才执行回收
    const diskTitle = HOST.document.createElement('div');
    diskTitle.className = 'settings-subgroup';
    diskTitle.textContent = '磁盘维护';
    sec.appendChild(diskTitle);
    const diskWrap = HOST.document.createElement('div');
    sec.appendChild(diskWrap);
    function fmtBytes(n) {
      n = Number(n) || 0;
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0;
      while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
      return (i === 0 ? Math.round(n) : n.toFixed(2)) + ' ' + units[i];
    }
    function diskAction(path, btn) {
      btn.disabled = true;
      fetch('/api/config/' + path, { method: 'POST' }).then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '操作冲突'); });
        return r.json().catch(function () { return {}; });
      }).then(function (d) {
        delete cfgState.data.deploy;
        draw();
        if (d && d.message) HOST.alert(d.message);
      }).catch(function (e) { btn.disabled = false; HOST.alert('失败：' + (e && e.message || '')); });
    }
    function renderDisk(d) {
      diskWrap.innerHTML = '';
      if (!d) return;
      const card = HOST.document.createElement('div');
      card.className = 'cfg-card';
      const head = HOST.document.createElement('div');
      head.className = 'cfg-card-head';
      const left = HOST.document.createElement('div');
      left.className = 'cfg-card-head-l';
      const title = HOST.document.createElement('div');
      title.className = 'cfg-card-title';
      const nm = HOST.document.createElement('div');
      nm.className = 'cfg-card-name';
      nm.textContent = 'Docker 数据盘';
      title.appendChild(nm);
      const chip = HOST.document.createElement('span');
      if (!d.supported) {
        chip.className = 'cfg-chip bad';
        chip.textContent = '不可用';
      } else if (d.dead_ratio == null) {
        chip.className = 'cfg-chip off';
        chip.textContent = '待检测';
      } else {
        chip.className = 'cfg-chip ' + (d.needs_compact ? 'warn' : 'ok');
        chip.textContent = '空洞 ' + Math.round(d.dead_ratio * 100) + '%';
      }
      title.appendChild(chip);
      left.appendChild(title);
      const sub = HOST.document.createElement('div');
      sub.className = 'cfg-card-sub';
      sub.textContent = d.detail || '';
      left.appendChild(sub);
      if (d.sandbox && d.sandbox.age_days != null) {
        const sub2 = HOST.document.createElement('div');
        sub2.className = 'cfg-card-sub';
        sub2.textContent = '沙盒容器已使用 ' + d.sandbox.age_days + ' 天' +
          (d.sandbox.age_days >= 14 ? '（使用较久，建议重建一次释放可写层）' : '');
        left.appendChild(sub2);
      }
      head.appendChild(left);

      const taskRunning = d.task && d.task.state === 'running';
      const act = HOST.document.createElement('div');
      act.className = 'cfg-card-act';

      const cp = HOST.document.createElement('button');
      cp.className = 'btn cfg-deploy-btn ' + (taskRunning ? 'running' : 'missing');
      cp.disabled = !d.supported || taskRunning;
      cp.textContent = (taskRunning && d.task.kind === 'compact') ? '回收中…' : '一键回收';
      cp.title = '停止 Docker/WSL 后用 diskpart 压缩 vhdx，需要一次管理员授权（UAC）';
      cp.addEventListener('click', function () {
        if (!HOST.confirm('一键回收会短暂停止 Docker 与 WSL，并弹出一次管理员授权（UAC）。现在执行？')) return;
        diskAction('deploy/disk/compact', cp);
      });
      act.appendChild(cp);

      const pr = HOST.document.createElement('button');
      pr.className = 'btn cfg-deploy-btn missing';
      pr.disabled = !d.docker_running || taskRunning;
      pr.textContent = (taskRunning && d.task.kind === 'prune') ? '清理中…' : '清理构建缓存';
      pr.addEventListener('click', function () { diskAction('deploy/disk/prune', pr); });
      act.appendChild(pr);

      const rb = HOST.document.createElement('button');
      rb.className = 'btn cfg-deploy-btn failed';
      rb.disabled = !d.docker_running || taskRunning;
      rb.textContent = '重建沙盒';
      rb.title = '删除沙盒容器（可写层与容器内缓存清空），下次工具调用自动重建';
      rb.addEventListener('click', function () {
        if (!HOST.confirm('重建沙盒容器？容器内 apt/pip 装过的依赖与缓存会丢失，工作目录内的文件不受影响。')) return;
        diskAction('deploy/disk/rebuild', rb);
      });
      act.appendChild(rb);

      head.appendChild(act);
      card.appendChild(head);

      const needBody = d.needs_compact || taskRunning || (d.task && d.task.state !== 'idle' && d.task.log && d.task.log.length);
      if (needBody) {
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        if (d.needs_compact) {
          const tip = HOST.document.createElement('div');
          tip.className = 'cfg-tip';
          tip.style.margin = '0';
          tip.textContent = '空洞占比已超过 ' + Math.round((d.threshold || 0.3) * 100) +
            '%（约 ' + fmtBytes(d.dead_bytes) + '），建议执行一次「一键回收」，压缩后 Docker 会自动恢复运行。';
          body.appendChild(tip);
        }
        if (d.task && d.task.log && d.task.log.length) {
          const tg = HOST.document.createElement('button');
          tg.className = 'cfg-log-toggle';
          tg.textContent = cfgState.diskLogOpen ? '收起维护日志 ▾' : '查看维护日志 ▸';
          tg.addEventListener('click', function () { cfgState.diskLogOpen = !cfgState.diskLogOpen; renderDisk(d); });
          body.appendChild(tg);
          if (cfgState.diskLogOpen) {
            const lg = HOST.document.createElement('pre');
            lg.className = 'settings-log';
            lg.style.minHeight = '80px';
            lg.textContent = d.task.log.join('\n');
            body.appendChild(lg);
          }
        }
        card.appendChild(body);
      }
      diskWrap.appendChild(card);
    }
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
        renderDisk(ov && ov.disk);
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
    // 草稿态下首个消息到此：此刻才真正建会话，并把用户选的范式一并带入，
    // 保证系统提示词用「所选范式」生成（而非默认范式）。
    const created = await (await fetch('/api/sessions/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paradigm: groupState.draftParadigm || '' }) })).json();
    if (created && created.id) {
      groupState.activeSessionId = created.id;
      groupState.draft = false;
      groupState.draftParadigm = '';
      await refreshSessions();
      updateEmpty();
      broadcastSessions('session.switched', { session_id: created.id });
      return created.id;
    }
    return '';
  }

  // 当前活动会话的后台 Agent 是否仍在工作（/status 的 is_thinking，与历史面板同源）。
  // 用于「Agent 忙碌时禁止切换会话/新建/拉分支」，保护正在进行的任务数据。
  // 探测失败一律视为空闲（不阻断），避免会话暂不可用时完全无法操作。
  async function activeSessionBusy() {
    const sid = groupState.activeSessionId;
    if (!sid) return false;
    try {
      const st = await (await fetch('/api/sessions/' + encodeURIComponent(sid) + '/status')).json();
      return !!(st && st.is_thinking);
    } catch (_) { return false; }
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
        const body = await res.json();
        // 乐观本地即时显示用户消息，随后 fetch 同步（后端异步写入，fetch 慢时也不丢"你好"）
        // 用后端回传的 processed_message：超长输入会被后端替换为「已落盘」占位符，
        // 若这里仍广播原文，占位符永远确认不掉原文，乐观消息会一直卡在列表最下方
        const shown = body && typeof body.processed_message === 'string' ? body.processed_message : (payload.message || '');
        if (shown) broadcast('session', 'conversation.local', { session_id: sessionId, events: [{ role: 'user', content: String(shown) }] });
        refreshSessions().then(updateEmpty);   // 更新 messages_count，维持 empty 状态准确
        broadcastSessions('conversation.updated', { session_id: sessionId });
        return body;
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
        const body = await res.json();
        // 乐观本地即时显示 type=user 的事件，随后 fetch 同步去重。
        // 用后端回传的 processed_events：超长输入已替换为「已落盘」占位符，广播原文会卡在列表最下方
        const evs = (body && Array.isArray(body.processed_events)) ? body.processed_events : (Array.isArray(payload.events) ? payload.events : []);
        const uv = evs.filter((e) => e && e.type === 'user').map((e) => ({ role: 'user', content: String(e.content || '') }));
        if (uv.length) broadcast('session', 'conversation.local', { session_id: sessionId, events: uv });
        refreshSessions().then(updateEmpty);
        broadcastSessions('conversation.updated', { session_id: sessionId });
        return body;
      }
      case 'sessions.list': {
        const list = await (await fetch('/api/sessions')).json();
        groupState.sessions = list || [];
        updateEmpty();
        return groupState.sessions;
      }
      case 'sessions.new': {
        // Agent 忙碌时禁止新建并切走，避免打断正在进行的任务
        if (await activeSessionBusy()) return { status: 'busy' };
        // 纯前端草稿态：不落盘、不进列表。会话延迟到首条消息时由 ensureSessionId 创建，
        // 届时按 draftParadigm 生成系统提示词。
        groupState.draft = true;
        groupState.draftParadigm = '';
        groupState.activeSessionId = '';
        await refreshSessions();
        updateEmpty();
        broadcastSessions('session.switched', { session_id: '' });
        return { status: 'ok', draft: true };
      }
      case 'session.switch': {
        const target = String(payload.session_id || '');
        // 切到「同一个」会话无需拦截；切到不同会话时若 Agent 忙碌则拒绝（对齐原 UI：等待任务完成再切换）
        if (target && target !== groupState.activeSessionId && (await activeSessionBusy())) return { status: 'busy' };
        // 切到已有会话即退出草稿态（放弃未发送的新会话占位）
        if (target) groupState.draft = false;
        if (target) {
          // 关键：把后端「当前活跃会话」一并检出。后端 Agent 只挂载一个活跃会话，
          // 未指定 session_id 的外部事件会路由到它；只改前端状态不 checkout，
          // 新事件仍会落进上一个会话。
          const res = await fetch('/api/sessions/' + encodeURIComponent(target) + '/checkout', { method: 'POST' });
          if (!res.ok) throw new Error((await res.text()) || '切换会话失败');
          groupState.activeSessionId = target;
          await refreshSessions();
          updateEmpty();
          broadcastSessions('session.switched', { session_id: target });
        }
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
        const wasActive = groupState.activeSessionId === sid;
        // 后端禁止删除正在活跃的会话：删当前会话前先把它检出到另一个会话，
        // 否则前端与后端活跃会话同步后这条请求必被拒绝
        if (wasActive) {
          const other = groupState.sessions.find((s) => s.id !== sid);
          if (other) {
            const co = await fetch('/api/sessions/' + encodeURIComponent(other.id) + '/checkout', { method: 'POST' });
            if (!co.ok) throw new Error((await co.text()) || '切换会话失败');
          }
        }
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid), { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.text()) || '删除失败');
        // 删掉的正是当前会话：清空活动会话（回到欢迎态），并让各 slot 重新对账
        if (wasActive) groupState.activeSessionId = '';
        await refreshSessions();
        updateEmpty();
        // 只有当前会话被删才需要切换事件；删其它会话不打断正在进行的会话（避免清空乐观消息缓冲）
        broadcastSessions(wasActive ? 'session.switched' : 'conversation.updated', { session_id: groupState.activeSessionId });
        return { status: 'ok' };
      }
      // 待审批队列：对齐后端 GET /api/requests（主进程会在轮询时顺带 kick skill/sensor 免审测试）
      case 'requests.list': {
        const list = await (await fetch('/api/requests')).json();
        return Array.isArray(list) ? list : [];
      }
      // 审批裁决：对齐后端 POST /api/requests/{id}/resolve
      case 'requests.resolve': {
        const rid = String(payload.request_id || '');
        if (!rid) throw new Error('缺少 request_id');
        const res = await fetch('/api/requests/' + encodeURIComponent(rid) + '/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            approved: !!payload.approved,
            feedback: String(payload.feedback || ''),
            ignore: !!payload.ignore,
            duration: Number(payload.duration || 5),
          }),
        });
        if (!res.ok) throw new Error((await res.text()) || '裁决失败');
        const data = await res.json();
        broadcastAll('requests.updated', { request_id: rid });
        return data;
      }
      case 'chat.interrupt':
        return (await fetch('/api/chat/interrupt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })).json();
      // 会话分支：基于当前会话新建分支并切换过去（对齐后端 POST /api/sessions/{id}/branch）
      case 'session.branch': {
        // Agent 忙碌时禁止拉取分支（原 UI 同样拦截），避免新分支会话与进行中任务相互干扰
        if (await activeSessionBusy()) return { status: 'busy' };
        const sid = String(payload.session_id || groupState.activeSessionId || '');
        if (!sid) throw new Error('缺少 session_id');
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid) + '/branch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ alias: String(payload.alias || '') }),
        });
        if (!res.ok) throw new Error((await res.text()) || '分支失败');
        const data = await res.json();
        if (data && data.id) {
          groupState.activeSessionId = data.id;
          await refreshSessions();
          updateEmpty();
          broadcastSessions('session.switched', { session_id: data.id });
        }
        return data;
      }
      // trace2skill：分配技能工厂并向当前会话注入 evolve_factory 事件（对齐原 UI confirmTraceToSkill）
      case 'chat.traceToSkill': {
        const sid = String(payload.session_id || groupState.activeSessionId || '');
        if (!sid) throw new Error('缺少 session_id');
        const name = String(payload.name || '').trim();
        const goal = String(payload.goal || '').trim();
        if (!name) throw new Error('技能名称不能为空');
        if (!goal) throw new Error('期望描述不能为空');
        const initRes = await fetch('/api/evolve/init', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'skill', name, is_upgrade: !!payload.is_upgrade, goal, trace: true, session_id: sid }),
        });
        if (!initRes.ok) throw new Error((await initRes.text()) || '工厂分配失败');
        const initData = await initRes.json();
        const factoryPath = '/agent_vm/skill_workplace/' + initData.workplace_id + '/' + name;
        const content = '用户触发了技能工厂，已为你分配了技能工厂' + factoryPath + '/，请根据用户需要和本次会话的交互记录与历史经验升级或创建对应技能。以下是用户期望：\n' + goal;
        const batchRes = await fetch('/api/chat/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid, events: [{ type: 'evolve_factory', content }] }),
        });
        if (!batchRes.ok) throw new Error((await batchRes.text()) || '任务下发失败');
        setEmpty(false);
        broadcastSessions('conversation.updated', { session_id: sid });
        return { status: 'ok' };
      }
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
        buildRail();   // 固定区域已按区域合并图标，重建即可反映显隐
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
        return HOST.purrcat.openDialog({ directory: false, properties: ['openFile', 'multiSelections'] });
      }
      case 'dialog.folder': {
        if (!HOST.purrcat) throw new Error('本地文件夹选择仅在 Electron 内可用');
        return HOST.purrcat.openDialog({ directory: true, properties: ['openDirectory', 'multiSelections'] });
      }
      // 由插件用 <input type="file"> 选好 File 后，交给宿主解析真实绝对路径
      case 'dialog.resolveFiles': {
        if (!HOST.purrcat || !HOST.purrcat.getPathForFile) throw new Error('本地路径解析仅在 Electron 内可用');
        const files = Array.isArray(payload.files) ? payload.files : [];
        const paths = [];
        for (const f of files) {
          try { const p = HOST.purrcat.getPathForFile(f); if (p) paths.push(p); } catch (_) { /* 单个失败跳过 */ }
        }
        return { paths: paths };
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
      case 'ref.graphs': {
        const graphs = await (await fetch('/api/graphs')).json();
        return (graphs || []).map((g) => (typeof g === 'string' ? g : g.name));
      }
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
      // ---- 内置浏览器（原生 WebContentsView，非 iframe）----
      // 插件 iframe 拿不到 window.purrcat（preload 只在主 frame 生效，未开
      // nodeIntegrationInSubFrames），因此由宿主把原生浏览器原语转发给 purrcat，
      // 并负责「插件 iframe 局部坐标 → 主窗口内容区坐标」的换算。
      case 'browser.available':
        return { available: !!(HOST.purrcat && HOST.purrcat.browserNewTab) };
      case 'browser.bounds': {
        const pc = HOST.purrcat;
        if (!pc || !pc.browserSetBounds) throw new Error('内置浏览器仅在 Electron 内可用');
        let ox = 0, oy = 0;
        const fr = origin && origin.iframe;
        if (fr && fr.getBoundingClientRect) { const r = fr.getBoundingClientRect(); ox = r.left; oy = r.top; }
        await pc.browserSetBounds(
          Math.round(ox + (Number(payload.x) || 0)),
          Math.round(oy + (Number(payload.y) || 0)),
          Math.round(Number(payload.w) || 1),
          Math.round(Number(payload.h) || 1),
          1,
        );
        return { status: 'ok' };
      }
      case 'browser.hide': {
        if (HOST.purrcat && HOST.purrcat.browserHide) await HOST.purrcat.browserHide();
        return { status: 'ok' };
      }
      case 'browser.newTab': {
        if (!HOST.purrcat || !HOST.purrcat.browserNewTab) throw new Error('内置浏览器仅在 Electron 内可用');
        return { tabId: await HOST.purrcat.browserNewTab(payload.url || '') };
      }
      case 'browser.closeTab': {
        if (HOST.purrcat && HOST.purrcat.browserCloseTab) await HOST.purrcat.browserCloseTab(payload.tabId, payload.nextTabId || undefined);
        return { status: 'ok' };
      }
      case 'browser.switchTab': {
        if (HOST.purrcat && HOST.purrcat.browserSwitchTab) await HOST.purrcat.browserSwitchTab(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.navigate': {
        if (HOST.purrcat && HOST.purrcat.browserNavigate) await HOST.purrcat.browserNavigate(payload.tabId, payload.url);
        return { status: 'ok' };
      }
      case 'browser.reload': {
        if (HOST.purrcat && HOST.purrcat.browserReload) await HOST.purrcat.browserReload(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.goBack': {
        if (HOST.purrcat && HOST.purrcat.browserGoBack) await HOST.purrcat.browserGoBack(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.goForward': {
        if (HOST.purrcat && HOST.purrcat.browserGoForward) await HOST.purrcat.browserGoForward(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.pickStart': {
        if (!HOST.purrcat || !HOST.purrcat.browserPickStart) throw new Error('内置浏览器仅在 Electron 内可用');
        return await HOST.purrcat.browserPickStart(payload.tabId);
      }
      case 'browser.pickEnd': {
        if (HOST.purrcat && HOST.purrcat.browserPickEnd) await HOST.purrcat.browserPickEnd(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.locate': {
        if (!HOST.purrcat || !HOST.purrcat.browserLocate) return null;
        return await HOST.purrcat.browserLocate(payload.tabId, payload.x, payload.y);
      }
      case 'browser.pickElement': {
        if (!HOST.purrcat || !HOST.purrcat.browserCdpPickElement) return null;
        return await HOST.purrcat.browserCdpPickElement(payload.tabId, payload.x, payload.y);
      }
      case 'browser.openExternal': {
        if (HOST.purrcat && HOST.purrcat.openExternal) await HOST.purrcat.openExternal(payload.url);
        return { status: 'ok' };
      }
      // 网页链接统一路由：主进程拦下的 target=_blank/window.open 与插件显式调用都走这里
      case 'browser.openUrl':
        return openUrlInBrowserPanel(payload.url);
      // 草稿态下选择 Agent Loop（范式）：仅记录在宿主，待首条消息建会话时生效。
      // 与 session.* 系列同属宿主对外契约，插件无需感知彼此即可热插拔。
      case 'session.setDraftParadigm': {
        if (!groupState.draft) return { status: 'noop' };
        groupState.draftParadigm = String(payload.paradigm || '');
        return { status: 'ok', paradigm: groupState.draftParadigm };
      }
      case 'state.get':
        return { ...groupState, plugins: undefined };
      // 子代理分支视图切换：会话插件据此切换查看分支（同时由分支状态进入/退出输入只读）
      case 'branch.select': {
        const bid = String(payload.branch_id || 'main');
        groupState.activeBranchId = bid;
        broadcastAll('branch.switched', { branch_id: bid });
        return { status: 'ok' };
      }
      default:
        return null;
    }
  }

  // ---- 命令入口 ----
  async function callAction(actionId, payload, origin) {
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

  // ---- 广播事件到全部插件帧（不区分 slot）：宿主级通用状态（如原生视图遮挡）通知 ----
  function broadcastAll(event, data) {
    Object.keys(frames).forEach((k) => { broadcast(k, event, data); });
  }

  // ---- 原生视图遮挡：内置浏览器等原生 WebContentsView 永远绘制在 DOM 之上，
  //      宿主的设置中心 / 模态弹窗 / 各类下拉菜单出现时必须让持有原生视图的插件
  //      暂时隐藏视图。宿主不感知具体插件，只广播一个通用布尔状态由插件自行响应。
  let _nativeCover = null;
  function nativeCoverActive() {
    if (HOST.document.body.classList.contains('settings-open')) return true;
    if (HOST.document.querySelector('.wm-pp_menu')) return true;
    if (HOST.document.querySelector('.settings-card-menu')) return true;
    const modals = HOST.document.querySelectorAll('.wm-modal-wrap');
    for (let i = 0; i < modals.length; i++) {
      if (HOST.getComputedStyle(modals[i]).display !== 'none') return true;
    }
    return false;
  }
  function syncNativeCover() {
    const v = nativeCoverActive();
    if (v === _nativeCover) return;
    _nativeCover = v;
    broadcastAll('host.nativeCover', { covered: v });
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
      const origin = { slot: srcSlot, pluginId: srcPlugin, inst: srcFrame ? srcFrame.el : null, iframe: srcFrame ? srcFrame.iframe : null };
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
  // modal 尺寸：只设宽高（位置由遮罩 flex 居中，不写 left/top）
  function applyModalSize(el, size) {
    if (!size) return;
    if (typeof size.w === 'string' && size.w) el.style.width = size.w;
    else if (Number(size.w) > 0) el.style.width = Number(size.w) + 'px';
    if (typeof size.h === 'string' && size.h) el.style.height = size.h;
    else if (Number(size.h) > 0) el.style.height = Number(size.h) + 'px';
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
  // 窗口尺寸变化：弹窗尺寸用 vw/vh 时会自动跟随，但像素位置不会——
  // 居中声明的重新居中，其余夹回视口内，避免窗口缩小后被挤出屏幕/被覆盖
  function reflowFloats() {
    Object.keys(frames).forEach((sid) => {
      (frames[sid] || []).forEach((f) => {
        const el = f.el;
        if (!el || !el.classList.contains('wm-float') || el.style.display === 'none') return;
        const p = groupState.plugins.find((x) => x.id === f.pluginId);
        const def = (p && p.slotDef) || {};
        if (def.center) { centerFloat(el); return; }
        const w = el.offsetWidth, h = el.offsetHeight;
        const r = el.getBoundingClientRect();
        el.style.right = 'auto';
        el.style.left = Math.max(0, Math.min(Math.max(0, HOST.innerWidth - w), r.left)) + 'px';
        el.style.top = Math.max(0, Math.min(Math.max(0, HOST.innerHeight - h), r.top)) + 'px';
      });
    });
  }
  // 窗口尺寸变化：先夹紧面板宽度（缩小后必须立刻收回，否则右缘越出可视区），再重排浮窗。
  // 各自 try/catch 隔离：任一环节抛错都不能阻断另一个。
  HOST.addEventListener('resize', function () {
    try { applyPanelWidth(); } catch (_) {}
    try { reflowFloats(); } catch (_) {}
  });
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
  //     内容插件；顶部为多标签栏（Chrome 风格）：+ 按钮选择插件新开标签页，
  //     每个标签页各驻留独立 iframe（切换仅显隐，不重载，保留各自状态）。
  //     宽度由中栏右缘分隔条拖动调整（--wm-panel-w）。
  let panelBar = null;             // 中栏与聊天区之间的纵向分隔条
  let panelState = null;           // 单例：{ plugins, pluginsById, activeId, el, head, body, strip, views:{}, frames:{}, area:'panel' }
  let panelTabs = [];              // 打开的标签页（面板插件 id，按打开顺序）；持久化于 active.__panelTabs__
  // 待投递给内置浏览器面板的地址：目标 iframe 尚未加载完成时先挂起，
  // 由 mountFrame 的 load 回调补投（新挂载的面板帧收不到挂载前发出的广播）
  let pendingBrowserUrl = null;
  const PANEL_MIN_W = 260;         // 面板容器拖动下限
  let panelContainerCfg = { opacity: 0.9 }; // 宿主固有中栏容器配置（透明度）
  let panelSavedWidth = null;      // 用户显式保存的默认宽度（null=最大舒展，不落盘）
  let panelDesiredWidth = null;    // 运行时「期望宽度」：窗口缩小时显示被夹紧，但此值保留，放大后恢复
  // 「内置容器」插件提供的外壳：宿主启动时读取一次 plugins/builtin/builtin-panel/index.html，
  // 把其中的样式注入本文档、并把 <body> 里的外壳元素留作模板（容器结构与样式因此完全由
  // 该插件提供）。宿主只按外壳渲染，不把插件挂成 iframe——以保留标签页、地址路由与宽度拖拽。
  let panelShellTpl = null;        // 外壳模板元素（.wm-ppanel）
  async function loadPanelShell() {
    if (panelShellTpl) return;
    try {
      const res = await fetch('/api/webmin/plugin/' + encodeURIComponent(PANEL_CONTAINER_ID) + '/index.html');
      if (!res.ok) return;
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      const src = doc.querySelector('style');
      if (src) {
        const el = HOST.document.createElement('style');
        el.id = 'wm-builtin-panel-style';
        el.textContent = src.textContent;
        const old = HOST.document.getElementById('wm-builtin-panel-style');
        if (old) old.remove();
        HOST.document.head.appendChild(el);
      }
      panelShellTpl = (doc.body && doc.body.firstElementChild) || null;
    } catch (_) { /* 插件文件不可读（后端离线）：容器无外壳，renderPanel 会跳过 */ }
  }
  function applyPanelContainerCfg() {
    const el = HOST.document.querySelector('.wm-ppanel[data-pslot="panel"]');
    if (!el) return;
    let o = Number(panelContainerCfg.opacity);
    if (!(o >= 0)) o = 0.9;
    o = Math.min(1, Math.max(0.15, o));
    el.style.setProperty('--wm-panel-bg', 'rgba(242,244,247,' + o.toFixed(3) + ')');
  }
  // 读取 CSS 变量数值。必须从 body 作用域读取：布局变量可能在 body 上被覆盖
  // （如 body.rail-1 把 --wm-rail-w 改为 196px），从 documentElement 读会一直得到
  // :root 的 48px，导致 rail 展开时面板宽度上限偏大、右缘越出窗口。
  function cssNum(name, dflt) {
    const scope = HOST.document.body || HOST.document.documentElement;
    const v = HOST.getComputedStyle(scope).getPropertyValue(name);
    const n = parseFloat(v);
    return (n >= 0) ? n : dflt;
  }
  // 面板左侧起始偏移（rail → [侧栏]）
  function panelLeftBase() {
    const rail = cssNum('--wm-rail-w', 48);
    const gap = cssNum('--wm-sidebar-gap', 8);
    const side = cssNum('--wm-sidebar-w', 264);
    const noSidebar = HOST.document.body.classList.contains('rail-nosidebar');
    return noSidebar ? (rail + gap) : (rail + gap + side + gap);
  }
  // 槽位插件当前是否启用（被关闭或未挂载 → 该槽不占位，不为它预留宽度）
  function slotEnabled(slot) {
    const cur = pluginBySlot[slot];
    if (!cur) return false;              // 未挂载（被删除 / 未选中）
    return !railHidden(cur.id);          // 被设置或白条关闭
  }
  function sessionEnabled() { return slotEnabled('session'); }
  // 面板容器「最大舒展」宽度：面板占满左侧栏右侧全部，右侧留出会话面板。
  // 会话面板未启用则不为它预留，面板可一直舒展到最右。
  function maxPanelWidth() {
    const gap = cssNum('--wm-sidebar-gap', 8);
    let chat = sessionEnabled() ? cssNum('--wm-chat-w', 420) : 0;
    return Math.max(PANEL_MIN_W, Math.floor(HOST.innerWidth - panelLeftBase() - gap - chat));
  }
  // 面板可用宽度上限：会话面板仍启用时只保其最小宽度（--wm-chat-min-w），
  // 保证会话面板不会被面板压得过窄；关闭则不再预留，面板可贴到最右。
  // 无论哪种情况，面板右缘（含 ✕）都留在可视区内。
  function panelMaxLimit() {
    const gap = cssNum('--wm-sidebar-gap', 8);
    const chatMin = sessionEnabled() ? cssNum('--wm-chat-min-w', 360) : 0;
    return Math.floor(HOST.innerWidth - panelLeftBase() - gap - chatMin);
  }
  // 把「期望宽度」夹到 [下限, 可用上限] 后写入 CSS 变量。
  // 期望宽度本身保留，窗口放大后自动恢复原宽，不引入永久性 max-width。
  function applyPanelWidth() {
    if (!hasPanelsDef()) return;
    const gap = cssNum('--wm-sidebar-gap', 8);
    let limit = panelMaxLimit();
    // 硬性兜底：按面板元素「当前实际左缘」再夹一次。窗口缩小/白条展开等场景下，
    // 只要右缘（含 ✕）会越过视口，就按实际左缘重算上限，保证面板绝不超出 app。
    // 容器元素：内置容器 .wm-ppanel，或由插件入驻 panel-container 时其挂载的 iframe
    const el = HOST.document.querySelector('.wm-ppanel[data-pslot="panel"]')
      || HOST.document.querySelector('[data-slot="panel-container"] > iframe');
    if (el) {
      const left = el.getBoundingClientRect().left;
      if (isFinite(left)) limit = Math.min(limit, Math.floor(HOST.innerWidth - left - gap));
    }
    let raw = (panelDesiredWidth != null) ? panelDesiredWidth : maxPanelWidth();
    if (!isFinite(raw)) raw = maxPanelWidth();
    if (!isFinite(limit)) return;
    let w = Math.max(PANEL_MIN_W, raw);
    w = (limit < PANEL_MIN_W) ? Math.max(0, limit) : Math.min(w, limit);
    HOST.document.documentElement.style.setProperty('--wm-panel-w', Math.round(w) + 'px');
  }
  // 中栏容器的总开关（容器右上角 ✕ / 打开标签页时自动重开）：只改开关键，
  // 区域内的互斥与显隐一律交给 refreshFixedSlot 重算，避免出现「两个容器同时显示」
  function setContainerHidden(hidden) {
    if (!railState.hidden) railState.hidden = {};
    const list = slotMap['panel-container'] || [];
    if (hidden) {
      list.forEach((p) => { railState.hidden[p.id] = true; });   // 关闭 = 整个区域让出中栏
      closePanelMenus();
    } else {
      list.forEach((p) => { if (p.id !== PANEL_CONTAINER_ID) railState.hidden[p.id] = true; });
      delete railState.hidden[PANEL_CONTAINER_ID];
      activeBySlot['panel-container'] = PANEL_CONTAINER_ID;
    }
    refreshFixedSlot('panel-container');
    refreshAreaRail('panel-container');
    buildRail();
    persistActive();
    persistRail().catch(() => {});
  }
  function hasPanelsDef() {
    // panel-container 区域有插件入驻时（内置容器或容器插件），中栏容器同样存在
    if ((slotMap['panel-container'] || []).length) return true;
    return Object.keys(slotMap).some((sid) => (slotMap[sid][0].slotDef || {}).type === 'panel');
  }
  // 当前由「第三方容器插件」提供中栏容器（同区域互斥，最多一个生效；内置容器除外）
  function thirdPartyContainerPlugin() {
    const cur = pluginBySlot['panel-container'];
    return (cur && cur.id !== PANEL_CONTAINER_ID) ? cur : null;
  }
  // 中栏容器是否占位：第三方容器插件生效，或内置容器开关打开。二者互斥，同时只有一个成立
  function panelContainerVisible() {
    return !!thirdPartyContainerPlugin() || !railHidden(PANEL_CONTAINER_ID);
  }
  function startPanelBarDrag(e) {
    e.preventDefault();
    const el = e.currentTarget;   // 分隔条
    const w0 = HOST.document.documentElement.style.getPropertyValue('--wm-panel-w');
    const base = w0 ? parseFloat(w0) : ((panelDesiredWidth != null) ? panelDesiredWidth : 420);
    const sx0 = e.clientX;
    // 拖动期间关掉容器宽度的 0.15s 过渡：手柄 left 绑的是 --wm-panel-w 且无过渡，
    // 容器若还慢慢追，手柄与容器边缘会分离、内置浏览器的原生视图也跟着滞后。
    HOST.document.body.classList.add('wm-panel-dragging');
    const move = (ev) => {
      // 拖动只记录「期望宽度」，实际宽度由 applyPanelWidth 夹到可用范围（右缘/✕ 不出可视区）
      panelDesiredWidth = Math.max(PANEL_MIN_W, base + (ev.clientX - sx0));
      applyPanelWidth();
    };
    const up = () => {
      HOST.document.body.classList.remove('wm-panel-dragging');
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
      // 宽度交给 applyPanelWidth：期望宽度为 null 时取「最大舒展」，否则沿用用户宽度并夹到可用范围
      applyPanelWidth();
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

  // 关闭面板右上角下拉
  function closePanelMenus() {
    HOST.document.querySelectorAll('.wm-pp_menu').forEach((m) => m.remove());
    syncNativeCover();
  }
  // 持久化面板容器的标签列表与激活标签：标签列表序列化后与原 active 一并落盘
  function savePanelSel() {
    activeBySlot['__panelTabs__'] = JSON.stringify(panelTabs);
    return persistActive();
  }
  // 单个标签页按钮（图标 + 名称 + 关闭 ×）；点击激活，× 关闭该标签
  function makePanelTab(st, id, p) {
    const tab = HOST.document.createElement('div');
    tab.className = 'wm-pp_tab' + (id === st.activeId ? ' active' : '');
    tab.dataset.pid = id;
    tab.title = p.name || p.id;
    const g = HOST.document.createElement('span');
    g.className = 'wm-pp_tabico';
    paintPluginIcon(g, p);
    tab.appendChild(g);
    const nm = HOST.document.createElement('span');
    nm.className = 'wm-pp_tabname';
    nm.textContent = p.name || p.id;
    tab.appendChild(nm);
    const x = HOST.document.createElement('button');
    x.className = 'wm-pp_tabx';
    x.textContent = '✕';
    x.title = '关闭标签页';
    x.addEventListener('click', (ev) => { ev.stopPropagation(); closePanelTab(id); });
    tab.appendChild(x);
    tab.addEventListener('click', () => setActivePanelTab(st, id));
    return tab;
  }
  // 依据 tabs/activeId 同步：标签条、每个标签的视图（保留已挂载帧）、空态、广播帧集合
  function renderPanel(st) {
    // 首次（或容器被重建后）按「内置容器」插件提供的外壳搭壳：标签条 + 内容区；
    // 已挂载视图随之失效需清空
    if (!st.head || !st.head.isConnected) {
      if (!panelShellTpl) return;   // 插件外壳尚未就绪（后端未在线）：等下次渲染再搭壳
      const el = panelShellTpl.cloneNode(true);
      el.dataset.pslot = 'panel';
      el.style.display = 'flex';
      HOST.document.body.appendChild(el);
      st.el = el;
      st.head = el.querySelector('.wm-pp_head');
      st.strip = el.querySelector('.wm-pp_tabs');
      // + 按钮：选择面板插件新开标签页
      st.addBtn = el.querySelector('.wm-pp_add');
      paintIcon(st.addBtn, 'plus', '+');   // 与宿主其它图标同风格的线性 SVG 加号
      st.addBtn.addEventListener('click', (ev) => { ev.stopPropagation(); openPanelAddMenu(st, st.addBtn); });
      // ✕ 关闭按钮：关闭整个面板容器（统一走 setContainerHidden，同步状态并持久化）
      st.closeBtn = el.querySelector('.wm-pp_drawer');
      st.closeBtn.addEventListener('click', () => { setContainerHidden(true); closePanelMenus(); });
      st.body = el.querySelector('.wm-pp_body');
      st.emptyEl = el.querySelector('.wm-pp_empty');
      st.views = {};
      st.frames = {};
    }
    // 丢弃已卸载插件的残留标签
    panelTabs = panelTabs.filter((id) => !!st.pluginsById[id]);
    if (panelTabs.indexOf(st.activeId) < 0) st.activeId = panelTabs[0] || '';
    // 标签条：仅按钮，重建不触及 iframe
    st.strip.innerHTML = '';
    panelTabs.forEach((id) => st.strip.appendChild(makePanelTab(st, id, st.pluginsById[id].p)));
    // 为每个标签确保视图存在；已存在且仍在文档中的复用（不重载，保留其状态）
    panelTabs.forEach((id) => {
      const old = st.views[id];
      if (old && old.isConnected) return;
      // 视图已被清除（如插件清单重载时 buildSlotIndex 卸载过）→ 重建并重挂帧
      const v = HOST.document.createElement('div');
      v.className = 'wm-pp_view';
      v.dataset.pid = id;
      st.body.appendChild(v);
      st.views[id] = v;
      st.frames[id] = mountFrame(v, st.pluginsById[id].p);
    });
    // 卸载并移除已关闭标签的视图（如内置浏览器关闭其原生 Tab）
    Object.keys(st.views).forEach((id) => {
      if (panelTabs.indexOf(id) >= 0) return;
      notifyUnmount(st.views[id]);
      st.views[id].remove();
      delete st.views[id];
      delete st.frames[id];
    });
    // 空态占位（由插件外壳提供，容器保留，等待 + 新建标签页）
    if (panelTabs.length) { if (st.emptyEl.parentNode) st.emptyEl.remove(); }
    else if (!st.emptyEl.parentNode) st.body.appendChild(st.emptyEl);
    frames['panel'] = panelTabs.map((id) => st.frames[id]).filter(Boolean);
    applyActivePanelTab(st);
  }
  // 应用激活标签：仅切换视图显隐与标签高亮（iframe 保持挂载）
  function applyActivePanelTab(st) {
    Object.keys(st.views).forEach((id) => { st.views[id].style.display = (id === st.activeId) ? 'flex' : 'none'; });
    st.strip.querySelectorAll('.wm-pp_tab').forEach((t) => {
      const on = t.dataset.pid === st.activeId;
      t.classList.toggle('active', on);
      if (on && t.scrollIntoView) { try { t.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (_) {} }
    });
  }
  // 切换激活标签并持久化
  function setActivePanelTab(st, id) {
    if (st.activeId === id) return;
    st.activeId = id;
    activeBySlot['panel'] = id;
    applyActivePanelTab(st);
    savePanelSel();
  }
  // 打开（或聚焦已打开的）标签页并激活
  function openPanelTab(id) {
    const st = panelState;
    if (!st || !st.pluginsById[id]) return;
    const added = panelTabs.indexOf(id) < 0;
    if (added) panelTabs.push(id);
    st.activeId = id;
    activeBySlot['panel'] = id;
    if (added) renderPanel(st); else applyActivePanelTab(st);
    savePanelSel();
    setContainerHidden(false);   // 面板被关掉时自动重新打开
  }
  // 关闭某标签页：优先激活右邻、其次左邻；空则回到空态
  function closePanelTab(id) {
    const st = panelState;
    if (!st) return;
    const i = panelTabs.indexOf(id);
    if (i < 0) return;
    panelTabs.splice(i, 1);
    if (st.activeId === id) st.activeId = panelTabs[i] || panelTabs[i - 1] || '';
    activeBySlot['panel'] = st.activeId || '__none__';
    renderPanel(st);   // 内部会卸载被关闭标签的视图
    savePanelSel();
  }
  // + 下拉：列出全部面板插件，已打开者标注并可点击聚焦，未打开者点击新开标签页
  function openPanelAddMenu(st, anchor) {
    const wasOpen = HOST.document.getElementById('ppmenu-' + st.area);
    closePanelMenus();
    if (wasOpen) return;   // 再次点 + = 收起
    const menu = HOST.document.createElement('div');
    menu.className = 'wm-pp_menu';
    menu.id = 'ppmenu-' + st.area;
    st.plugins.forEach(({ p }) => {
      const isOpen = panelTabs.indexOf(p.id) >= 0;
      const item = HOST.document.createElement('div');
      item.className = 'wm-pp_menu-item' + (isOpen ? ' active' : '');
      const g = HOST.document.createElement('span');
      g.className = 'wm-pp_menu-ico';
      paintPluginIcon(g, p);
      item.appendChild(g);
      const nm = HOST.document.createElement('span');
      nm.textContent = p.name || p.id;
      item.appendChild(nm);
      if (isOpen) {
        const tag = HOST.document.createElement('span');
        tag.className = 'wm-pp_menu-tag';
        tag.textContent = '已打开';
        item.appendChild(tag);
      }
      item.addEventListener('click', () => { openPanelTab(p.id); closePanelMenus(); });
      menu.appendChild(item);
    });
    HOST.document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const left = Math.min(r.right - menu.offsetWidth, HOST.innerWidth - menu.offsetWidth - 8);
    menu.style.right = 'auto';
    menu.style.left = Math.max(8, left) + 'px';
    menu.style.top = (r.bottom + 4) + 'px';
    syncNativeCover();
  }
  // 挂载 type=panel 插件：无面板插件则不占位；有则建 .wm-ppanel 并点亮抽屉
  function mountPanels() {
    // 若已有第三方容器插件（与内置容器等位、同区域互斥）提供中栏容器，
    // 则由该插件渲染：内置容器让位，不再创建 .wm-ppanel（标签列表保留，便于切回）。
    if (thirdPartyContainerPlugin()) {
      if (panelState && panelState.el && panelState.el.parentNode) { notifyUnmount(panelState.el); panelState.el.remove(); }
      panelState = null;
      closePanelMenus();
      return;
    }
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
      if (panelState && panelState.el && panelState.el.parentNode) { notifyUnmount(panelState.el); panelState.el.remove(); }
      panelState = null;
      closePanelMenus();
      return;
    }
    const byId = {};
    byArea.panel.forEach((x) => { byId[x.p.id] = x; });
    const valid = (id) => !!byId[id];
    // 是否已有保存的标签列表：有则尊重其内容（含「空列表」= 用户主动关光了标签）
    const hasSavedTabs = Object.prototype.hasOwnProperty.call(activeBySlot, '__panelTabs__');
    let st = panelState;
    if (!st) {
      // 首次装配：恢复已保存的标签列表；无保存则回退旧版「单抽屉选中项」，再退声明顺序第一个
      panelTabs = panelTabs.filter(valid);
      if (!panelTabs.length && !hasSavedTabs) {
        const legacy = activeBySlot['panel'];
        panelTabs = (legacy && legacy !== '__none__' && valid(legacy)) ? [legacy] : [byArea.panel[0].p.id];
      }
      st = panelState = { plugins: byArea.panel, pluginsById: byId, activeId: '', area: 'panel', el: null };
    } else {
      st.plugins = byArea.panel;
      st.pluginsById = byId;
      panelTabs = panelTabs.filter(valid);
      if (!panelTabs.length && !hasSavedTabs) panelTabs = [byArea.panel[0].p.id];
    }
    const saved = activeBySlot['panel'];
    st.activeId = (saved && saved !== '__none__' && panelTabs.indexOf(saved) >= 0) ? saved : (panelTabs[0] || '');
    renderPanel(st);   // 容器外壳由「内置容器」插件提供，按需在此搭壳
    // 仅更新内存态（标签列表保留在 activeBySlot 中，确保后续 persistActive 整节覆盖时不丢）；
    // 启动时不做多余落盘，实际变更（+/×/切换）各自已持久化
    activeBySlot['panel'] = st.activeId;
    activeBySlot['__panelTabs__'] = JSON.stringify(panelTabs);
    closePanelMenus();
  }

  // ---- 网页链接路由 ----
  // 聊天历史等插件里的网页链接（target=_blank / window.open）由主进程
  // setWindowOpenHandler 拦下，经 purrcat:open-url 回传到宿主，这里统一交给
  // 「声明了 openUrl 能力的 panel 插件」（内置浏览器）打开，与完整模式同一规则。
  // 宿主不硬编码插件 id：能力由插件在自己的 plugin.json 里声明。
  function browserPanel() {
    if (!panelState) return null;
    return panelState.plugins.find((x) => (x.p || {}).openUrl) || null;
  }
  function deliverPendingBrowserUrl() {
    if (!pendingBrowserUrl) return;
    const hit = browserPanel();
    if (!hit || !panelState || panelState.activeId !== hit.p.id) return;
    const fr = panelState.frames && panelState.frames[hit.p.id];
    if (!fr || !fr.loaded) return;   // 浏览器帧未加载完：等其 load 回调再投
    const url = pendingBrowserUrl;
    pendingBrowserUrl = null;
    broadcast(hit.p.slot, 'browser.openUrl', { url: url });
  }
  function openUrlInBrowserPanel(url) {
    const u = String(url || '').trim();
    // purrcat:// 是本应用自造的虚拟协议，只有后端 envelope.parse_uri 能解析成真实文件；
    // 原样交给 Chromium/系统会被委托给操作系统外壳，Windows 便弹「找不到能打开此链接的应用」。
    // 按既有约定（完整模式 TaskPage / builtin-task）翻译成后端产物端点，再进内置浏览器打开。
    if (/^purrcat:\/\//i.test(u)) {
      const tid = (/^purrcat:\/\/task\/([^/]+)\/node\//i.exec(u) || [])[1];
      const art = '/api/tasks/' + encodeURIComponent(tid || '_unknown') +
        '/artifact?uri=' + encodeURIComponent(u);
      return openUrlInBrowserPanel(new URL(art, location.origin).href);
    }
    const pc = HOST.purrcat;
    const hit = browserPanel();
    // 中栏容器由插件入驻时宿主内置容器已让位（panelState 为空），此时把地址广播给
    // 该容器插件，由它转交给自己的内置浏览器子插件——与内置容器同样在应用内打开。
    const hostCont = hit ? null : thirdPartyContainerPlugin();
    // 非网页（mailto:/tel:/file: 等）或面板里没有可用内置浏览器 → 退回系统处理
    if (!/^https?:\/\//i.test(u) || (!hit && !hostCont) || !pc || !pc.browserNewTab) {
      if (pc && pc.openExternal && u) pc.openExternal(u);
      return { status: 'external' };
    }
    if (hostCont) {
      broadcast('panel-container', 'browser.openUrl', { url: u });
      return { status: 'ok' };
    }
    // 浏览器面板未开为标签页则先打开，再激活并投递地址（已打开则仅聚焦）
    openPanelTab(hit.p.id);
    pendingBrowserUrl = u;
    deliverPendingBrowserUrl();
    return { status: 'ok' };
  }

  // ---- 渲染：把某插件实例装进对应容器内的 iframe ----
  // 卸载通知：iframe 被移除前给插件最后一次收尾机会（如关掉自己开的浏览器 Tab、
  // 把原生视图移出屏幕）。postMessage 已入队，即使随后移除 iframe 仍会投递。
  // 插件后端随 iframe 生命周期存活：挂载时 start、卸载时 stop。
  // 改完 server/server.js 只需关掉再打开标签页，后端就会重新拉起（不必重启 PurrCat）。
  function syncPluginBackend(id, action) {
    if (!id) return;
    try {
      fetch('/api/webmin/plugin-backend/' + encodeURIComponent(id) + '/' + action, {
        method: 'POST',
        cache: 'no-store',
      }).catch(function () { /* 后端启动失败不影响 UI */ });
    } catch (_) { /* noop */ }
  }
  function notifyUnmount(rootEl) {
    if (!rootEl || !rootEl.querySelectorAll) return;
    rootEl.querySelectorAll('iframe').forEach(function (f) {
      try {
        if (f.contentWindow) f.contentWindow.postMessage({ type: 'event', event: 'host.unmount', data: {} }, '*');
      } catch (_) { /* noop */ }
      if (f.dataset && f.dataset.backend === '1' && f.dataset.pid) {
        syncPluginBackend(f.dataset.pid, 'stop');
      }
    });
  }
  function mountFrame(el, p) {
    notifyUnmount(el);
    el.querySelectorAll('iframe').forEach((f) => f.remove());
    el.querySelectorAll('.wm-fgrab, .wm-fresize').forEach((h) => h.remove());
    if (!p || !p.entry) return null;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('tabindex', '-1');
    iframe.src = `/api/webmin/plugin/${encodeURIComponent(p.id)}/${p.entry.split('/').map(encodeURIComponent).join('/')}`;
    iframe.title = p.name || p.id;
    iframe.dataset.pid = p.id;
    if (p.backend) {
      iframe.dataset.backend = '1';
      syncPluginBackend(p.id, 'start');
    }
    el.appendChild(iframe);
    // 注意：configByPlugin 的唯一初始化点是 applyManifestState（覆盖全部插件），
    // 这里不再覆写，避免用 boot 时的 manifest 旧值冲掉运行中的未保存编辑
    slotByPluginId[p.id] = p.slot;
    frameByPluginId[p.id] = iframe;
    const rec = { iframe: iframe, pluginId: p.id, el: el, loaded: false };
    iframe.addEventListener('load', function onLoad() {
      rec.loaded = true;
      applyConfigTo(p.id);
      // 启动竞态修复：activeSessionId 由 boot 里的异步请求确定，可能晚于 iframe 加载；
      // 只靠 boot 时的一次广播会让晚加载的插件错过 → 给刚加载的插件补推当前会话
      if (groupState.activeSessionId) {
        try {
          iframe.contentWindow.postMessage(
            { type: 'event', event: 'session.switched', data: { session_id: groupState.activeSessionId } },
            '*'
          );
        } catch (_) { /* noop */ }
      }
      // 同步补推当前分支视图：晚加载的输入框据此判定是否只读
      try {
        iframe.contentWindow.postMessage(
          { type: 'event', event: 'branch.switched', data: { branch_id: groupState.activeBranchId || 'main' } },
          '*'
        );
      } catch (_) { /* noop */ }
      // 启动竞态修复：插件可能在「设置中心/模态弹窗已打开」之后才挂载，
      // 此时早先的 host.nativeCover 广播已经发过，插件会误以为未被遮挡而展示原生视图（覆盖设置）。
      // 给刚加载的插件补推一次当前遮挡状态。
      try {
        iframe.contentWindow.postMessage(
          { type: 'event', event: 'host.nativeCover', data: { covered: nativeCoverActive() } },
          '*'
        );
      } catch (_) { /* noop */ }
      deliverPendingBrowserUrl();   // 帧刚就绪：补投挂起的网页链接（若有）
      iframe.removeEventListener('load', onLoad);
    });
    return rec;
  }

  // ---- 依据 manifest 的 slot 声明建立槽集合（去硬编码） ----
  function buildSlotIndex() {
    // 清理已挂载的动态实例浮层（保留 html 里的锚定容器）
    Object.keys(frames).forEach((k) => {
      (frames[k] || []).forEach((f) => { if (f.el && f.el.parentNode && !f.el.hasAttribute('data-layer')) { notifyUnmount(f.el); f.el.remove(); } });
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

  // 重算某 fixed 区域当前应显示的插件：在「未被关闭」的插件里优先取用户上次选中的，
  // 否则取声明顺序第一个；全部被关闭时该区域不占位（隐藏锚点、让出宽度）。
  // 同区域天然互斥——任意时刻最多只有一个插件被挂载。
  function refreshFixedSlot(slot) {
    const list = slotMap[slot] || [];
    const visible = list.filter((x) => !railHidden(x.id));
    const chosen = visible.find((x) => x.id === activeBySlot[slot]) || visible[0] || null;
    if (frames[slot]) {
      frames[slot].forEach((f) => { if (f.iframe && f.iframe.parentNode) f.iframe.parentNode.removeChild(f.iframe); });
      frames[slot] = [];
    }
    if (!chosen) {
      delete pluginBySlot[slot];
      applySlotHidden(slot, true);
      if (slot === 'panel-container') syncPanelContainer();
      return;
    }
    pluginBySlot[slot] = chosen;
    // 内置容器（builtin-panel）由宿主按插件提供的外壳原生渲染（.wm-ppanel），不挂 iframe
    if (chosen.id === PANEL_CONTAINER_ID) {
      const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
      if (anchor) anchor.innerHTML = '';
      syncPanelContainer();
      return;
    }
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`);
    if (anchor) {
      anchor.innerHTML = '';
      const fr = mountFrame(anchor, chosen);
      if (fr) frames[slot] = [fr];
    }
    // 有插件生效：显示锚点（mountFrame 只负责塞 iframe，不负责显隐）
    applySlotHidden(slot, false);
    if (slot === 'panel-container') syncPanelContainer();
  }

  // 中栏容器的唯一同步点：宿主内置容器与入驻插件同区域互斥（谁生效谁占位），
  // 并据此重算 has-panels / 分隔条 / 中栏宽度，最后由「面板容器」总开关统辖显隐。
  // 开关入驻插件（走 refreshFixedSlot）后必须调用，否则会出现「内置容器与插件容器同时
  // 显示」或「容器不占位、与会话历史重叠悬空」。
  function syncPanelContainer() {
    mountPanels();                                      // 有入驻插件则内置容器让位（移除 .wm-ppanel），否则重建
    reconcilePanels();                                  // has-panels / .wm-pbar / --wm-panel-w
    applySlotHidden('panel', !panelContainerVisible());  // 最后统一显隐：两候选谁生效都占位
  }

  // ---- 动态挂载全部类型窗口（type：fixed 锚定单例 / panel 分栏抽屉 / float 自由浮窗多开 / modal 模态弹窗） ----
  function mountAll() {
    // 1) fixed：按 area 挂到 html 锚定容器；优先挂载用户上次选中的插件，
    //    否则取未被关闭插件中声明顺序第一个；该区域全部插件都被关闭则不占位。
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'fixed') return;
      refreshFixedSlot(sid);
    });
    // 2) panel：无面板插件则不占位；有则建 .wm-ppanel（右上角抽屉切换）
    mountPanels();
    // 3) pet（area=pet）：自由浮窗，每个插件一个独立 .wm-float，可拖拽可缩放
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
    // 4) modal（area=popup）：模态弹窗，遮罩铺满主区（白条与设置中心在其之上），
    //    固定居中、不可拖拽；尺寸用 CSS 长度随窗口自适应，无需 resize 重排
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'modal') return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      list.forEach((p) => {
        const wrap = HOST.document.createElement('div');
        wrap.className = 'wm-modal-wrap wm-mount';
        wrap.dataset.mslot = sid;
        const box = HOST.document.createElement('div');
        box.className = 'wm-modal';
        applyModalSize(box, def.size);
        wrap.appendChild(box);
        HOST.document.body.appendChild(wrap);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(box, p);
        // 以整体遮罩为实例单位：显隐/清理/关闭时连遮罩一起处理
        if (fr) { fr.el = wrap; frames[sid].push(fr); }
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
      // 兼容旧三态持久化（0=收起 1=仅图标 2=图标+名称）：仅 2 → 1（图标+文字），其余 → 0（仅图标）
      railState.stage = (Number.isFinite(stage) && stage >= 2) ? 1 : 0;
      railState.hidden = (railSaved.hidden && typeof railSaved.hidden === 'object') ? railSaved.hidden : {};
      // 旧键迁移：内置容器曾是宿主的合成候选（开关键 __panel__），现为真实内置插件 builtin-panel
      if (Object.prototype.hasOwnProperty.call(railState.hidden, '__panel__')) {
        if (railState.hidden['__panel__']) railState.hidden[PANEL_CONTAINER_ID] = true;
        delete railState.hidden['__panel__'];
      }
      railState.opacity = (typeof railSaved.opacity === 'number') ? railSaved.opacity : 1;
    }
    // 面板容器配置（宿主资产，存于 plugins['panel-container']）
    const savedPanel = (manifest.panelContainer && typeof manifest.panelContainer === 'object') ? manifest.panelContainer : {};
    panelSavedWidth = (Number(savedPanel.width) >= 260) ? Number(savedPanel.width) : null;
    panelContainerCfg = { opacity: (typeof savedPanel.opacity === 'number') ? savedPanel.opacity : 0.9 };
    // 有保存宽度则作为期望宽度；无则保留本次会话中拖动产生的期望宽度
    if (panelSavedWidth != null) panelDesiredWidth = panelSavedWidth;
    configByPlugin['panel-container'] = Object.assign({}, savedPanel);
    // 单例槽选中项（剔除已卸载插件的残留）
    const savedActive = (manifest.active && typeof manifest.active === 'object') ? manifest.active : {};
    const ids = new Set(groupState.plugins.map((p) => p.id));
    Object.keys(activeBySlot).forEach((k) => delete activeBySlot[k]);
    // 面板容器多标签：标签列表以 JSON 串存于保留键 __panelTabs__（后端 active 只收字符串键值）。
    // 原样保留在 activeBySlot 中，确保后续 persistActive 整节覆盖时不会把标签列表清空。
    panelTabs = [];
    Object.keys(savedActive).forEach((k) => {
      const v = savedActive[k];
      if (k === '__panelTabs__') {
        activeBySlot[k] = String(v);
        try { const arr = JSON.parse(v); if (Array.isArray(arr)) panelTabs = arr.filter((x) => typeof x === 'string'); } catch (_) {}
        return;
      }
      if (v === '__none__' || ids.has(v)) activeBySlot[k] = v;
    });
  }
  async function loadManifest() {
    const manifest = await (await fetch('/api/webmin/manifest')).json();
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
    await loadPanelShell();   // 取「内置容器」插件的外壳（样式注入 + 结构模板），必须在 mountAll 前
    applyRailOpacity();
    buildSlotIndex();
    mountAll();
    bindRailToggle();
    buildRail();
    applyPanelContainerCfg();
    // 应用持久化的插件隐藏状态（需在挂载后重设，避免被 iframe 覆盖样式）
    applyPersistedHidden();

    // 原生浏览器 Tab 事件（标题/导航/被拦截）转发给全部插件帧，由持有原生视图的插件消费
    if (HOST.purrcat && HOST.purrcat.onTabEvent) {
      HOST.purrcat.onTabEvent(function (evt) { broadcastAll('browser.tabEvent', evt); });
    }
    // 网页链接路由：聊天历史里的 target=_blank / window.open 被主进程拦下后回传（与完整
    // 模式同一链路），极简模式转交内置浏览器面板打开，而不是弹原生窗口或跳走 iframe
    if (HOST.purrcat && HOST.purrcat.onOpenUrl) {
      HOST.purrcat.onOpenUrl(function (url) { openUrlInBrowserPanel(url); });
    }
    // 原生视图遮挡状态：设置中心 / 模态弹窗 / 下拉菜单出现时通知插件隐藏原生视图。
    // 在各开关点显式调用 syncNativeCover()（见 setSettingsOpen/applySlotHidden/菜单开合），
    // 不用 MutationObserver：浮窗拖拽会高频改内联样式，观察 style 会造成 getComputedStyle 抖动。
    syncNativeCover();

    try {
      const list = await (await fetch('/api/sessions')).json();
      if (Array.isArray(list) && list.length) {
        groupState.sessions = list;
        groupState.activeSessionId = list[0].id || '';
        // 修复：已加载完成的插件此刻才拿到 activeSessionId，必须补一次广播，
        // 否则聊天历史等插件会一直停在空态，直到用户手动点一次别的会话
        broadcastSessions('session.switched', { session_id: groupState.activeSessionId });
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