// 区域图标与区域菜单（白条按区域合并）
import { syncNativeCover } from './bus.js';
import { paintIcon, paintPluginIcon } from './icons.js';
import { refreshFixedSlot } from './mount.js';
import { closePanelMenus, renderPanel } from './panel.js';
import { applySlotHidden, buildRail, isRailPlugin, persistRail } from './rail.js';
import { AREA_LABEL, activateSlotPlugin, pluginVisible, togglePluginOpen } from './settings-tabs.js';
import { HOST, groupState, pluginBySlot, railButtons, railState, slotMap } from './state.js';
import type { PluginDescriptor } from './types.js';

  // ---- 区域图标：白条按「区域」合并，同区域共用一个图标 ----
  // 区域显示名复用设置面板的 AREA_LABEL（单一来源，见下方「UI 插件主面板」分组）
  // 「内置容器」是真实的内置插件（plugins/builtin/builtin-panel）：与第三方容器插件
  // （如涂鸦面板容器）同属 panel-container 区域、等位互斥，白条上可按区域独立开关。
  // 它的外壳结构与样式由该插件自己的 index.html 提供，宿主只按其渲染（见 renderPanel）。
  export const PANEL_CONTAINER_ID = 'builtin-panel';
  // 面板容器区域在白条/菜单里的统一字形：窗口 + 顶部标签条
  export const PANEL_AREA_ICON = 'panel-top';
  export function areaLabel(area: string) {
    // AREA_LABEL 是字面量常量表，按字符串键索引时补上通用索引签名
    return (AREA_LABEL as Record<string, string>)[area] || area;
  }
  // 白条分区次序：固定写死，插件按其 slot 区域自动归位；未列出的区域排在最后
  export const RAIL_AREA_ORDER = ['session', 'panel-container', 'popup', 'sidebar', 'background'];
  // 白条上的区域：除入驻容器（panel）外的全部区域，去重后按固定次序排列
  export function railAreaList(): string[] {
    const areas: string[] = [];
    groupState.plugins.forEach((p) => {
      const def = p.slotDef || {};
      if (def.type === 'panel' || !def.area) return;
      if (areas.indexOf(def.area) < 0) areas.push(def.area);
    });
    const rank = (a: string) => { const i = RAIL_AREA_ORDER.indexOf(a); return i < 0 ? RAIL_AREA_ORDER.length : i; };
    return areas.sort((a, b) => rank(a) - rank(b));
  }
  // 区域候选：声明该区域的全部插件（内置容器也是一个普通插件，不再有合成候选）
  export function areaCandidates(area: string): PluginDescriptor[] {
    return groupState.plugins.filter((p) => (p.slotDef || {}).area === area && isRailPlugin(p));
  }
  // 区域当前处于开启状态的候选（单例区域最多一个；弹窗/浮窗可多个同时开启）
  export function areaOpen(area: string) { return areaCandidates(area).filter(pluginVisible); }
  export function areaOn(area: string) { return areaOpen(area).length > 0; }
  // 区域当前生效的候选（单例区域为已挂载的那个，其余区域以首个开启者为准）
  export function areaActive(area: string): PluginDescriptor | null {
    const mounted = pluginBySlot[area];
    if (mounted) return mounted;
    return areaOpen(area)[0] || null;
  }
  // 切换区域到某个候选：固定区域统一走 activateSlotPlugin（同区域互斥 + 持久化 + 即时重挂）
  export function activateAreaCandidate(area: string, cand: PluginDescriptor | null) {
    if (cand) activateSlotPlugin(cand);
  }
  // 关闭整个区域：区域内全部候选一起让位（内置容器与容器插件互斥，一起关才真正空出中栏）
  export function deactivateArea(area: string) {
    if (!railState.hidden) railState.hidden = {};
    areaCandidates(area).forEach((p) => {
      railState.hidden[p.id] = true;
      // 单例区域的显隐由 refreshFixedSlot 统一重算；弹窗/浮窗是独立实例，逐个隐藏
      if ((p.slotDef || {}).type !== 'fixed') applySlotHidden(p.slot, true);
    });
    if (slotMap[area]) refreshFixedSlot(area);
    persistRail().catch(() => {});
    syncNativeCover();
  }
  // 重算区域图标的 on/off 与字形（内置容器与入驻插件互斥切换、开关变化后即时刷新）
  export function refreshAreaRail(area: string) {
    const btn = railButtons['__area__:' + area];
    if (!btn) return;
    btn.classList.remove('on', 'off');
    btn.classList.add(areaOn(area) ? 'on' : 'off');
    // 字形元素由宿主以 span 创建，查询结果为 Element，这里断言为 HTMLElement
    const g = btn.querySelector('.rail-glyph') as HTMLElement | null;
    if (!g) return;
    // 字形跟随该区域当前生效的插件；全关时回落到首个候选，避免文本兜底
    const target = areaActive(area) || areaCandidates(area)[0] || null;
    if (target) paintPluginIcon(g, target);
    else paintIcon(g, PANEL_AREA_ICON, '▤');
  }
  // 区域图标：区域生效=on；点击弹出候选菜单（仅一个候选时直接开/关）
  export function makeAreaRailButton(area: string): HTMLButtonElement {
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
  // 区域候选菜单：列出该区域全部候选（含内置容器），点击即切换；区域生效时附「关闭」项
  export function openAreaMenu(area: string, anchor: HTMLElement, cands: PluginDescriptor[], openList: PluginDescriptor[]) {
    const already = HOST.document.getElementById('rail-area-menu');
    closePanelMenus();
    if (already) return;   // 再次点同一区域图标 = 收起
    const menu = HOST.document.createElement('div');
    menu.className = 'wm-pp_menu';
    menu.id = 'rail-area-menu';
    const openIds = (openList || []).map((x) => x.id);
    cands.forEach((c) => {
      const isActive = openIds.indexOf(c.id) >= 0;
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
    if (openIds.length) {
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

