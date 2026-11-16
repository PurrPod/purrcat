// 中栏面板容器单例（标签页、抽屉、宽度、持久化）
import { PANEL_CONTAINER_ID, refreshAreaRail } from './areas.js';
import { syncNativeCover } from './bus.js';
import { paintIcon, paintPluginIcon } from './icons.js';
import { addKeyToRow, activeRow, isPanelKey, layoutState, panelIdFromKey, panelWindowKey, removeKeyFromRow, tileMode } from './layout.js';
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
    tileBtn?: HTMLElement | null;              // 平铺/标签视图切换按钮
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
  export let panelTileView = false;                 // 容器内平铺视图：全部已打开标签横向平铺单行滚动；持久化于 active.__panelTile__
  let panelTileWidths: Record<string, number> = {}; // 平铺视图下各标签的窗口宽度；持久化于 active.__panelTileW__
  const PANEL_TILE_MIN_W = 320;                     // 与平铺窗口 CSS min-width 保持一致
  const PANEL_TILE_MAX_W = 1600;
  // 恢复持久化的平铺窗口宽度（manifest 重载时调用；非法项丢弃）
  export function restorePanelTileWidths(raw: unknown): void {
    const next: Record<string, number> = {};
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      Object.keys(raw as Record<string, unknown>).forEach((k) => {
        const n = Number((raw as Record<string, unknown>)[k]);
        if (isFinite(n)) next[k] = Math.max(PANEL_TILE_MIN_W, Math.min(PANEL_TILE_MAX_W, Math.round(n)));
      });
    }
    panelTileWidths = next;
  }
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
    activeBySlot['__panelTileW__'] = JSON.stringify(panelTileWidths);
    return persistActive();
  }
  // 单个标签页按钮（图标 + 名称 + 关闭 ×）；点击激活，× 关闭该标签；横向拖拽改顺序
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
    bindTabDrag(st, tab, id);
    return tab;
  }
  // 标签拖拽排序：按住标签横向拖动实时换位，松手落序（标签/平铺两种视图共用同一顺序）
  function bindTabDrag(st: PanelState, tab: HTMLElement, id: string): void {
    let suppressClick = false;
    tab.addEventListener('click', () => {
      if (suppressClick) { suppressClick = false; return; }   // 拖拽结束后的 click 不算激活
      setActivePanelTab(st, id);
    });
    tab.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0) return;
      if ((ev.target as HTMLElement).closest('.wm-pp_tabx')) return;   // ✕ 上按下不触发拖拽
      const strip = st.strip!;
      const startX = ev.clientX;
      let dragging = false;
      const move = (e2: PointerEvent) => {
        if (!dragging) {
          if (Math.abs(e2.clientX - startX) < 6) return;
          dragging = true;
          suppressClick = true;
          tab.classList.add('dragging');
          try { tab.setPointerCapture(ev.pointerId); } catch (_) {}
        }
        // 目标位置：第一个中线在指针右侧的兄弟标签之前，否则排到末尾
        const next = Array.from(strip.querySelectorAll<HTMLElement>('.wm-pp_tab')).find((t) => {
          if (t === tab) return false;
          const r = t.getBoundingClientRect();
          return e2.clientX < r.left + r.width / 2;
        });
        if (next) { if (next.previousElementSibling !== tab) strip.insertBefore(tab, next); }
        else if (strip.lastElementChild !== tab) strip.appendChild(tab);
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        window.removeEventListener('pointercancel', up);
        tab.classList.remove('dragging');
        if (!dragging) return;
        // 按拖完的 DOM 顺序落序，并同步视图与持久化
        const order = Array.from(strip.querySelectorAll<HTMLElement>('.wm-pp_tab')).map((t) => t.dataset.pid || '');
        panelTabs.length = 0;
        order.forEach((k) => { if (k) panelTabs.push(k); });
        applyPanelViewMode(st);
        savePanelSel();
        window.setTimeout(() => { suppressClick = false; }, 0);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
      window.addEventListener('pointercancel', up);
    });
  }
  // 容器内视图模式同步：平铺时视图按标签顺序排成单行且全部可见，否则仅激活标签可见
  export function applyPanelViewMode(st: PanelState): void {
    const tiled = panelTileView;
    st.body!.classList.toggle('wm-pp-tiled', tiled);
    st.tileBtn?.classList.toggle('active', tiled);
    // 视图 DOM 顺序与标签顺序一致（平铺模式下即窗口排列顺序）
    panelTabs.forEach((pid) => {
      const v = st.views[pid];
      if (v && v.parentNode === st.body) st.body!.appendChild(v);
      if (v) ensureViewResize(st, v, pid, tiled);
    });
    Object.keys(st.views).forEach((pid) => {
      st.views[pid].style.display = (tiled || pid === st.activeId) ? 'flex' : 'none';
    });
    scrollActiveTileIntoView(st);
  }
  // 平铺视图窗口右缘调宽手柄：仅平铺模式显示；宽度按标签记忆并持久化
  function ensureViewResize(st: PanelState, view: HTMLElement, id: string, tiled: boolean): void {
    let grip = view.querySelector('.wm-pp_vresize') as HTMLElement | null;
    if (!grip) {
      grip = HOST.document.createElement('div');
      grip.className = 'wm-pp_vresize';
      grip.title = '拖动调整宽度';
      bindViewResize(view, grip, id);
      view.appendChild(grip);
    }
    const w = panelTileWidths[id];
    if (tiled && w) { view.style.flex = '0 0 ' + w + 'px'; view.style.width = w + 'px'; }
    else { view.style.flex = ''; view.style.width = ''; }   // 无记忆宽度时回到 CSS 自适应（1 0 320px）
  }
  function bindViewResize(view: HTMLElement, grip: HTMLElement, id: string): void {
    grip.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0 || !panelTileView) return;
      ev.preventDefault();
      ev.stopPropagation();
      const startX = ev.clientX;
      const startW = view.getBoundingClientRect().width;
      const move = (e2: PointerEvent) => {
        const w = Math.max(PANEL_TILE_MIN_W, Math.min(PANEL_TILE_MAX_W, Math.round(startW + (e2.clientX - startX))));
        panelTileWidths[id] = w;
        view.style.flex = '0 0 ' + w + 'px';
        view.style.width = w + 'px';
      };
      const up = () => {
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', up);
        grip.removeEventListener('pointercancel', up);
        try { grip.releasePointerCapture(ev.pointerId); } catch (_) {}
        savePanelSel();
      };
      // 指针捕获锁定在手柄上：快速拖动划过插件 iframe 时事件不脱手（与平铺模式窗口调宽一致）
      try { grip.setPointerCapture(ev.pointerId); } catch (_) {}
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', up);
      grip.addEventListener('pointercancel', up);
    });
  }
  // 切换容器内「平铺 / 标签」两种视图并持久化（会话位、列表位不受影响）
  function togglePanelViewMode(): void {
    const st = panelState;
    if (!st) return;
    panelTileView = !panelTileView;
    activeBySlot['__panelTile__'] = panelTileView ? '1' : '';
    applyPanelViewMode(st);
    persistActive();
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
      // 平铺/标签视图切换按钮（+ 右边、✕ 左边）：容器内单行横向平铺全部已打开标签
      st.tileBtn = el.querySelector('.wm-pp_tilebtn') as HTMLElement;
      paintIcon(st.tileBtn!, 'columns');
      st.tileBtn!.addEventListener('click', (ev) => { ev.stopPropagation(); togglePanelViewMode(); });
      // ✕ 关闭按钮：关闭整个面板容器（统一走 setContainerHidden，同步状态并持久化）
      st.closeBtn = el.querySelector('.wm-pp_drawer') as HTMLElement;
      st.closeBtn!.addEventListener('click', () => { setContainerHidden(true); closePanelMenus(); });
      st.body = el.querySelector('.wm-pp_body') as HTMLElement;
      st.emptyEl = el.querySelector('.wm-pp_empty') as HTMLElement;
      st.views = {};
      st.frames = {};
      bindTileScrollSync(st);
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
    applyPanelViewMode(st);
  }
  // 平铺视图：把激活标签的窗口横向滚到可视区（标签条不在平铺区上方也对齐）
  function scrollActiveTileIntoView(st: PanelState): void {
    if (!panelTileView) return;
    const v = st.views[st.activeId];
    const b = st.body!;
    if (v) b.scrollLeft = Math.max(0, Math.min(v.offsetLeft - 12, b.scrollWidth - b.clientWidth));
  }
  let tileScrollSaveTimer: ReturnType<typeof setTimeout> | null = null;
  // 平铺视图横向滚动跟随：滚到哪扇窗口，高亮标签就转移到哪个（取与可视区交集最大者）；
  // 只改高亮不回滚窗口条，避免与滚动互相触发；选中态防抖持久化
  function bindTileScrollSync(st: PanelState): void {
    const b = st.body;
    if (!b) return;
    b.addEventListener('scroll', () => {
      if (!panelTileView || !st.views[st.activeId]) return;
      const br = b.getBoundingClientRect();
      let best = '';
      let bestArea = -1;
      panelTabs.forEach((pid) => {
        const v = st.views[pid];
        if (!v || v.style.display === 'none') return;
        const r = v.getBoundingClientRect();
        const w = Math.min(r.right, br.right) - Math.max(r.left, br.left);
        const h = Math.min(r.bottom, br.bottom) - Math.max(r.top, br.top);
        const area = Math.max(0, w) * Math.max(0, h);
        if (area > bestArea) { bestArea = area; best = pid; }
      });
      if (!best || best === st.activeId) return;
      st.activeId = best;
      activeBySlot['panel'] = best;
      st.strip!.querySelectorAll<HTMLElement>('.wm-pp_tab').forEach((t) => {
        const on = t.dataset.pid === best;
        t.classList.toggle('active', on);
        if (on && t.scrollIntoView) { try { t.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (_) {} }
      });
      if (tileScrollSaveTimer) clearTimeout(tileScrollSaveTimer);
      tileScrollSaveTimer = setTimeout(() => { tileScrollSaveTimer = null; savePanelSel(); }, 400);
    }, { passive: true });
  }
  // 应用激活标签：仅切换视图显隐与标签高亮（iframe 保持挂载；平铺视图下全部可见）
  export function applyActivePanelTab(st: PanelState): void {
    Object.keys(st.views).forEach((id) => { st.views[id].style.display = (panelTileView || id === st.activeId) ? 'flex' : 'none'; });
    st.strip!.querySelectorAll<HTMLElement>('.wm-pp_tab').forEach((t) => {
      const on = t.dataset.pid === st.activeId;
      t.classList.toggle('active', on);
      if (on && t.scrollIntoView) { try { t.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (_) {} }
    });
    scrollActiveTileIntoView(st);
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
      // 曾被白条/设置关闭过的插件：重新打开时清掉隐藏标记，窗口才会真正出现
      if (railHidden(id)) {
        if (!railState.hidden) railState.hidden = {};
        delete railState.hidden[id];
        persistRail().catch(() => {});
      }
      addKeyToRow(activeRow(), panelWindowKey(id));
      activeBySlot['panel'] = id;
      syncTiles();
      savePanelSel();
      scrollTileIntoView(panelWindowKey(id));
      return;
    }
    const st = panelState;
    if (!st || !st.pluginsById[id]) return;
    const added = panelTabs.indexOf(id) < 0;
    if (added) panelTabs.push(id);
    // 曾被白条/设置关闭过的插件：残留 hidden 标记会让它一直显示为关闭（平铺恢复也会跳过），
    // 与平铺分支一致，打开标签时一并清掉
    if (railHidden(id)) {
      if (!railState.hidden) railState.hidden = {};
      delete railState.hidden[id];
      persistRail().catch(() => {});
    }
    st.activeId = id;
    activeBySlot['panel'] = id;
    if (added) renderPanel(st); else applyActivePanelTab(st);
    savePanelSel();
    setContainerHidden(false);   // 面板被关掉时自动重新打开
  }
  // 关闭某标签页：优先激活右邻、其次左邻；空则回到空态
  export function closePanelTab(id: string): void {
    if (tileMode()) {
      if (!removeKeyFromRow(activeRow(), panelWindowKey(id))) return;
      activeBySlot['panel'] = id;
      syncTiles();
      savePanelSel();
      return;
    }
    const st = panelState;
    if (!st) return;
    const i = panelTabs.indexOf(id);
    if (i < 0) return;
    panelTabs.splice(i, 1);
    delete panelTileWidths[id];   // 关闭的标签不再保留平铺宽度记忆
    if (st.activeId === id) st.activeId = panelTabs[i] || panelTabs[i - 1] || '';
    activeBySlot['panel'] = st.activeId || '__none__';
    renderPanel(st);   // 内部会卸载被关闭标签的视图
    savePanelSel();
  }
  // 切回容器式：把各行已打开的面板并入标签页（保留容器式自己的标签）
  export function adoptLayoutRowsForTabs(): void {
    const merged: string[] = panelTabs.slice();
    layoutState.rows.forEach((row) => row.order.forEach((key) => {
      if (!isPanelKey(key)) return;
      const id = panelIdFromKey(key);
      if (merged.indexOf(id) < 0) merged.push(id);
    }));
    panelTabs.length = 0;
    panelTabs.push.apply(panelTabs, merged);
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
    panelTileView = activeBySlot['__panelTile__'] === '1';   // 恢复容器内平铺/标签视图模式
    const saved = activeBySlot['panel'];
    st.activeId = (saved && saved !== '__none__' && panelTabs.indexOf(saved) >= 0) ? saved : (panelTabs[0] || '');
    renderPanel(st);   // 容器外壳由「内置容器」插件提供，按需在此搭壳
    // 仅更新内存态（标签列表保留在 activeBySlot 中，确保后续 persistActive 整节覆盖时不丢）；
    // 启动时不做多余落盘，实际变更（+/×/切换）各自已持久化
    activeBySlot['panel'] = st.activeId;
    activeBySlot['__panelTabs__'] = JSON.stringify(panelTabs);
    closePanelMenus();
  }

