// 中栏面板容器单例（标签页、抽屉、宽度、持久化）
import { PANEL_CONTAINER_ID, refreshAreaRail } from './areas.js';
import { syncNativeCover } from './bus.js';
import { paintIcon, paintPluginIcon } from './icons.js';
import { panelWindowKey, tileMode } from './layout.js';
import { buildSlotIndex, mountFrame, notifyUnmount, refreshFixedSlot } from './mount.js';
import { buildRail, persistActive, persistRail, railHidden } from './rail.js';
import { HOST, activeBySlot, frames, groupState, pluginBySlot, railState, slotMap } from './state.js';
import { scrollTileIntoView, syncTiles } from './tile.js';
import type { PluginDescriptor, PluginFrame, SlotDef } from './types.js';

  // 面板插件条目：p 为插件描述（links 会直接读取 openUrl 等插件自定义能力字段），def 为其 slot 声明
  interface PanelEntry {
    p: PluginDescriptor;
    def: SlotDef;
  }
  // 中栏容器单例状态：外壳各节点由 builtin-panel 插件模板提供，尚未搭壳时为 null
  interface PanelState {
    plugins: Array<Record<string, any>>;       // 面板插件条目（对 p 保持宽松，兼容插件自定义能力字段）
    pluginsById: Record<string, PanelEntry>;
    activeId: string;
    area: string;
    el: HTMLElement | null;                    // 外壳元素 .wm-ppanel
    head?: HTMLElement | null;                 // 标签条容器
    body?: HTMLElement | null;                 // 视图内容区
    strip?: HTMLElement | null;                // 标签按钮条
    addBtn?: HTMLElement | null;               // + 新建标签页按钮
    closeBtn?: HTMLElement | null;             // ✕ 关闭整个容器按钮
    emptyEl?: HTMLElement | null;              // 空态占位
    views: Record<string, HTMLDivElement>;
    frames: Record<string, PluginFrame | null>;
  }

  // ---- panel-container：宿主系统级单例中栏容器，非弹窗。容纳全部 type=panel
  //     内容插件；顶部为多标签栏（Chrome 风格）：+ 按钮选择插件新开标签页，
  //     每个标签页各驻留独立 iframe（切换仅显隐，不重载，保留各自状态）。
  //     宽度由中栏右缘分隔条拖动调整（--wm-panel-w）。
  export let panelBar: HTMLElement | null = null;             // 中栏与聊天区之间的纵向分隔条
  export let panelState: PanelState | null = null;           // 单例：{ plugins, pluginsById, activeId, el, head, body, strip, views:{}, frames:{}, area:'panel' }
  export let panelTabs: string[] = [];              // 打开的标签页（面板插件 id，按打开顺序）；持久化于 active.__panelTabs__
  export const PANEL_MIN_W = 260;         // 面板容器拖动下限
  export let panelContainerCfg: Record<string, any> = { opacity: 0.9 }; // 宿主固有中栏容器配置（透明度）
  export let panelSavedWidth: number | null = null;      // 用户显式保存的默认宽度（null=最大舒展，不落盘）
  export let panelDesiredWidth: number | null = null;    // 运行时「期望宽度」：窗口缩小时显示被夹紧，但此值保留，放大后恢复
  // 跨模块只读导入无法赋值：宽度这两个原始值由本模块统一持有，外部通过 setter 写入
  export function setPanelSavedWidth(v: number | null) { panelSavedWidth = v; }
  export function setPanelDesiredWidth(v: number | null) { panelDesiredWidth = v; }
  // 「内置容器」插件提供的外壳：宿主启动时读取一次 plugins/builtin/builtin-panel/index.html，
  // 把其中的样式注入本文档、并把 <body> 里的外壳元素留作模板（容器结构与样式因此完全由
  // 该插件提供）。宿主只按外壳渲染，不把插件挂成 iframe——以保留标签页、地址路由与宽度拖拽。
  export let panelShellTpl: HTMLElement | null = null;        // 外壳模板元素（.wm-ppanel）
  export async function loadPanelShell() {
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
      // 模板根是 HTMLElement（.wm-ppanel）；缺失时为 null，renderPanel 会跳过搭壳
      panelShellTpl = ((doc.body && doc.body.firstElementChild) || null) as HTMLElement | null;
    } catch (_) { /* 插件文件不可读（后端离线）：容器无外壳，renderPanel 会跳过 */ }
  }
  export function applyPanelContainerCfg() {
    const el = HOST.document.querySelector('.wm-ppanel[data-pslot="panel"]') as HTMLElement | null;
    if (!el) return;
    let o = Number(panelContainerCfg.opacity);
    if (!(o >= 0)) o = 1;
    o = Math.min(1, Math.max(0.15, o));
    el.style.setProperty('--wm-panel-bg', 'rgba(255,255,255,' + o.toFixed(3) + ')');
  }
  // 读取 CSS 变量数值。必须从 body 作用域读取：布局变量可能在 body 上被覆盖
  // （如 body.rail-1 把 --wm-rail-w 改为 196px），从 documentElement 读会一直得到
  // :root 的 48px，导致 rail 展开时面板宽度上限偏大、右缘越出窗口。
  export function cssNum(name: string, dflt: number): number {
    const scope = HOST.document.body || HOST.document.documentElement;
    const v = HOST.getComputedStyle(scope).getPropertyValue(name);
    const n = parseFloat(v);
    return (n >= 0) ? n : dflt;
  }
  // 面板左侧起始偏移（rail → [侧栏]）
  export function panelLeftBase() {
    const rail = cssNum('--wm-rail-w', 48);
    const gap = cssNum('--wm-sidebar-gap', 8);
    const side = cssNum('--wm-sidebar-w', 264);
    const noSidebar = HOST.document.body.classList.contains('rail-nosidebar');
    return noSidebar ? (rail + gap) : (rail + gap + side + gap);
  }
  // 槽位插件当前是否启用（被关闭或未挂载 → 该槽不占位，不为它预留宽度）
  export function slotEnabled(slot: string): boolean {
    const cur = pluginBySlot[slot];
    if (!cur) return false;              // 未挂载（被删除 / 未选中）
    return !railHidden(cur.id);          // 被设置或白条关闭
  }
  export function sessionEnabled() { return slotEnabled('session'); }
  // 面板容器「最大舒展」宽度：面板占满左侧栏右侧全部，右侧留出会话面板。
  // 会话面板未启用则不为它预留，面板可一直舒展到最右。
  export function maxPanelWidth() {
    const gap = cssNum('--wm-sidebar-gap', 8);
    let chat = sessionEnabled() ? cssNum('--wm-chat-w', 420) : 0;
    return Math.max(PANEL_MIN_W, Math.floor(HOST.innerWidth - panelLeftBase() - gap - chat));
  }
  // 面板可用宽度上限：会话面板仍启用时只保其最小宽度（--wm-chat-min-w），
  // 保证会话面板不会被面板压得过窄；关闭则不再预留，面板可贴到最右。
  // 无论哪种情况，面板右缘（含 ✕）都留在可视区内。
  export function panelMaxLimit() {
    const gap = cssNum('--wm-sidebar-gap', 8);
    const chatMin = sessionEnabled() ? cssNum('--wm-chat-min-w', 360) : 0;
    return Math.floor(HOST.innerWidth - panelLeftBase() - gap - chatMin);
  }
  // 把「期望宽度」夹到 [下限, 可用上限] 后写入 CSS 变量。
  // 期望宽度本身保留，窗口放大后自动恢复原宽，不引入永久性 max-width。
  export function applyPanelWidth() {
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
  export function setContainerHidden(hidden: boolean): void {
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
  export function hasPanelsDef() {
    // 平铺模式没有中栏容器实体：面板插件各自成窗口，不再占中栏
    if (tileMode()) return false;
    // panel-container 区域有插件入驻时（内置容器或容器插件），中栏容器同样存在
    if ((slotMap['panel-container'] || []).length) return true;
    return Object.keys(slotMap).some((sid) => (slotMap[sid][0].slotDef || {}).type === 'panel');
  }
  // 当前由「第三方容器插件」提供中栏容器（同区域互斥，最多一个生效；内置容器除外）
  export function thirdPartyContainerPlugin() {
    const cur = pluginBySlot['panel-container'];
    return (cur && cur.id !== PANEL_CONTAINER_ID) ? cur : null;
  }
  // 中栏容器是否占位：第三方容器插件生效，或内置容器开关打开。二者互斥，同时只有一个成立
  export function panelContainerVisible() {
    if (tileMode()) return false;
    return !!thirdPartyContainerPlugin() || !railHidden(PANEL_CONTAINER_ID);
  }
  export function startPanelBarDrag(e: PointerEvent): void {
    e.preventDefault();
    const el = e.currentTarget as HTMLElement;   // 分隔条（事件派发期间 currentTarget 即该元素，必然非空）
    const w0 = HOST.document.documentElement.style.getPropertyValue('--wm-panel-w');
    const base = w0 ? parseFloat(w0) : ((panelDesiredWidth != null) ? panelDesiredWidth : 420);
    const sx0 = e.clientX;
    // 拖动期间关掉容器宽度的 0.15s 过渡：手柄 left 绑的是 --wm-panel-w 且无过渡，
    // 容器若还慢慢追，手柄与容器边缘会分离、内置浏览器的原生视图也跟着滞后。
    HOST.document.body.classList.add('wm-panel-dragging');
    const move = (ev: PointerEvent) => {
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
  export function reconcilePanels() {
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
  export function closePanelMenus() {
    HOST.document.querySelectorAll('.wm-pp_menu').forEach((m) => m.remove());
    syncNativeCover();
  }
  // 持久化面板容器的标签列表与激活标签：标签列表序列化后与原 active 一并落盘
  export function savePanelSel() {
    activeBySlot['__panelTabs__'] = JSON.stringify(panelTabs);
    return persistActive();
  }
  // 单个标签页按钮（图标 + 名称 + 关闭 ×）；点击激活，× 关闭该标签
  export function makePanelTab(st: PanelState, id: string, p: PluginDescriptor): HTMLElement {
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
  export function renderPanel(st: PanelState): void {
    // 首次（或容器被重建后）按「内置容器」插件提供的外壳搭壳：标签条 + 内容区；
    // 已挂载视图随之失效需清空
    if (!st.head || !st.head.isConnected) {
      if (!panelShellTpl) return;   // 插件外壳尚未就绪（后端未在线）：等下次渲染再搭壳
      const el = panelShellTpl.cloneNode(true) as HTMLElement;   // 模板根为 HTMLElement（.wm-ppanel）
      el.dataset.pslot = 'panel';
      el.style.display = 'flex';
      HOST.document.body.appendChild(el);
      st.el = el;
      // 外壳模板（builtin-panel）固定包含以下节点，缺失即模板损坏（原逻辑随后同样会抛错），故按元素类型断言
      st.head = el.querySelector('.wm-pp_head') as HTMLElement;
      st.strip = el.querySelector('.wm-pp_tabs') as HTMLElement;
      // + 按钮：选择面板插件新开标签页
      st.addBtn = el.querySelector('.wm-pp_add') as HTMLElement;
      paintIcon(st.addBtn!, 'plus', '+');   // 与宿主其它图标同风格的线性 SVG 加号
      st.addBtn!.addEventListener('click', (ev) => { ev.stopPropagation(); openPanelAddMenu(st, st.addBtn!); });
      // ✕ 关闭按钮：关闭整个面板容器（统一走 setContainerHidden，同步状态并持久化）
      st.closeBtn = el.querySelector('.wm-pp_drawer') as HTMLElement;
      st.closeBtn!.addEventListener('click', () => { setContainerHidden(true); closePanelMenus(); });
      st.body = el.querySelector('.wm-pp_body') as HTMLElement;
      st.emptyEl = el.querySelector('.wm-pp_empty') as HTMLElement;
      st.views = {};
      st.frames = {};
    }
    // 丢弃已卸载或已改挂到固定区域的插件残留标签
    panelTabs = panelTabs.filter((id) => {
      const rec = st.pluginsById[id];
      return !!rec && (rec.p.slotDef || {}).type === 'panel';
    });
    if (panelTabs.indexOf(st.activeId) < 0) st.activeId = panelTabs[0] || '';
    // 标签条：仅按钮，重建不触及 iframe
    st.strip!.innerHTML = '';
    panelTabs.forEach((id) => st.strip!.appendChild(makePanelTab(st, id, st.pluginsById[id].p)));
    // 为每个标签确保视图存在；已存在且仍在文档中的复用（不重载，保留其状态）
    panelTabs.forEach((id) => {
      const old = st.views[id];
      if (old && old.isConnected) return;
      // 视图已被清除（如插件清单重载时 buildSlotIndex 卸载过）→ 重建并重挂帧
      const v = HOST.document.createElement('div');
      v.className = 'wm-pp_view';
      v.dataset.pid = id;
      st.body!.appendChild(v);
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
    if (panelTabs.length) { if (st.emptyEl!.parentNode) st.emptyEl!.remove(); }
    else if (!st.emptyEl!.parentNode) st.body!.appendChild(st.emptyEl!);
    frames['panel'] = panelTabs.map((id) => st.frames[id]).filter(Boolean) as PluginFrame[];
    applyActivePanelTab(st);
  }
  // 应用激活标签：仅切换视图显隐与标签高亮（iframe 保持挂载）
  export function applyActivePanelTab(st: PanelState): void {
    Object.keys(st.views).forEach((id) => { st.views[id].style.display = (id === st.activeId) ? 'flex' : 'none'; });
    st.strip!.querySelectorAll<HTMLElement>('.wm-pp_tab').forEach((t) => {
      const on = t.dataset.pid === st.activeId;
      t.classList.toggle('active', on);
      if (on && t.scrollIntoView) { try { t.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (_) {} }
    });
  }
  // 切换激活标签并持久化
  export function setActivePanelTab(st: PanelState, id: string): void {
    if (st.activeId === id) return;
    st.activeId = id;
    activeBySlot['panel'] = id;
    applyActivePanelTab(st);
    savePanelSel();
  }
  // 打开（或聚焦已打开的）标签页并激活
  export function openPanelTab(id: string): void {
    // 平铺模式：面板插件 = 独立窗口，开/关即窗口的增删
    if (tileMode()) {
      const p = groupState.plugins.find((x) => x.id === id && (x.slotDef || {}).type === 'panel');
      if (!p) return;
      if (panelTabs.indexOf(id) < 0) panelTabs.push(id);
      // 曾被白条/设置关闭过的插件：重新打开时清掉隐藏标记，窗口才会真正出现
      if (railHidden(id)) {
        if (!railState.hidden) railState.hidden = {};
        delete railState.hidden[id];
        persistRail().catch(() => {});
      }
      activeBySlot['panel'] = id;
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
    activeBySlot['panel'] = id;
    if (added) renderPanel(st); else applyActivePanelTab(st);
    savePanelSel();
    setContainerHidden(false);   // 面板被关掉时自动重新打开
  }
  // 关闭某标签页：优先激活右邻、其次左邻；空则回到空态
  export function closePanelTab(id: string): void {
    if (tileMode()) {
      const at = panelTabs.indexOf(id);
      if (at < 0) return;
      panelTabs.splice(at, 1);
      activeBySlot['panel'] = panelTabs[at] || panelTabs[at - 1] || '__none__';
      savePanelSel();
      syncTiles();
      return;
    }
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
  export function openPanelAddMenu(st: PanelState, anchor: HTMLElement): void {
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
  export function mountPanels() {
    // 平铺模式不渲染中栏容器外壳：面板插件由 tile.ts 各自成窗口
    if (tileMode()) {
      if (panelState && panelState.el && panelState.el.parentNode) { notifyUnmount(panelState.el); panelState.el.remove(); }
      panelState = null;
      closePanelMenus();
      return;
    }
    // 若已有第三方容器插件（与内置容器等位、同区域互斥）提供中栏容器，
    // 则由该插件渲染：内置容器让位，不再创建 .wm-ppanel（标签列表保留，便于切回）。
    if (thirdPartyContainerPlugin()) {
      if (panelState && panelState.el && panelState.el.parentNode) { notifyUnmount(panelState.el); panelState.el.remove(); }
      panelState = null;
      closePanelMenus();
      return;
    }
    // 收集全部 type=panel 内容插件进单例中栏容器
    const byArea: { panel: PanelEntry[] } = { panel: [] };
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
    const byId: Record<string, PanelEntry> = {};
    byArea.panel.forEach((x) => { byId[x.p.id] = x; });
    const valid = (id: string) => !!byId[id];
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
      st = panelState = { plugins: byArea.panel, pluginsById: byId, activeId: '', area: 'panel', el: null, views: {}, frames: {} };
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

