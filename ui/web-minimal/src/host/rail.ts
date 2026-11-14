// 左侧图标栏（显隐、两态、透明度、持久化）
import { PANEL_CONTAINER_ID, areaLabel, makeAreaRailButton, railAreaList } from './areas.js';
import { syncNativeCover } from './bus.js';
import { reflowFloats } from './float.js';
import { paintIcon } from './icons.js';
import { tileMode } from './layout.js';
import { refreshFixedSlot } from './mount.js';
import { applyPanelWidth, panelBar, panelContainerVisible, thirdPartyContainerPlugin } from './panel.js';
import { setSettingsOpen } from './settings-appearance.js';
import { HOST, activeBySlot, configByPlugin, groupState, railButtons, railState } from './state.js';
import { syncTiles } from './tile.js';
import type { PluginDescriptor } from './types.js';
import { slotOfPlugin } from './utils.js';

  // ---- 图标栏（固定组件）----
  export const RAIL_STAGES = 2;   // 0=仅图标；1=图标+文字
  export function isRailPlugin(p: PluginDescriptor) { return p && p.entry; }
  export function railHidden(id: string) { return !!(railState.hidden && railState.hidden[id]); }
  export function applySlotHidden(slot: string | undefined, hidden: boolean) {
    // panelBar 在 panel.ts 中初始为 null、挂载后才赋值，这里统一按可空元素处理
    const pbar = panelBar as HTMLElement | null;
    // fixed：锚定容器
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`) as HTMLElement | null;
    if (anchor) anchor.style.display = hidden ? 'none' : '';
    if (slot === 'sidebar') {
      HOST.document.body.classList.toggle('rail-nosidebar', !!hidden);
      applyPanelWidth();   // 侧栏显隐改变可用区域，面板宽度需重新夹紧
    }
    // session：会话面板（历史 + 输入合并）的启停改变右侧需预留的宽度，面板宽度需重算
    if (slot === 'session') applyPanelWidth();
    // float：自由浮窗实例（data-fslot=slot）
    HOST.document.querySelectorAll(`.wm-float[data-fslot="${slot}"]`).forEach((el) => {
      (el as HTMLElement).style.display = hidden ? 'none' : 'block';
    });
    // modal：模态弹窗（data-mslot=slot），连遮罩一起显隐
    HOST.document.querySelectorAll(`.wm-modal-wrap[data-mslot="${slot}"]`).forEach((el) => {
      (el as HTMLElement).style.display = hidden ? 'none' : 'flex';
    });
    // panel：内容插件驻宿主单例容器（data-pslot=panel），隐藏/显示容器并切换让位
    if (slot === 'panel') {
      HOST.document.querySelectorAll('.wm-ppanel[data-pslot="panel"]').forEach((el) => {
        (el as HTMLElement).style.display = hidden ? 'none' : 'flex';
      });
      // 由第三方容器插件入驻时的容器锚点（内置容器另由 .wm-ppanel 统辖）同样受总开关统辖
      const pcHost = HOST.document.querySelector('[data-slot="panel-container"]') as HTMLElement | null;
      if (pcHost && thirdPartyContainerPlugin()) pcHost.style.display = hidden ? 'none' : '';
      if (hidden) { HOST.document.body.classList.remove('has-panels'); if (pbar) pbar.style.display = 'none'; }
      else {
        HOST.document.body.classList.add('has-panels');
        if (pbar) pbar.style.display = '';
        applyPanelWidth();   // 重新打开面板时按当前窗口宽度夹紧
      }
    }
    syncNativeCover();
  }
  export function persistRail() {
    return fetch('/api/webmin/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plugins: configByPlugin, rail: railState }),
    }).then((res) => { if (!res.ok) throw new Error(String(res.status)); });
  }
  // 持久化单例槽选中项（分节更新，不影响 plugins/rail）
  export function persistActive() {
    return fetch('/api/webmin/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: activeBySlot }),
    }).then((res) => { if (!res.ok) throw new Error(String(res.status)); }).catch(() => {});
  }
  // 应用持久化的隐藏状态（挂载后调用：fixed 锚定区 / float 实例 / panel 容器）
  export function applyPersistedHidden() {
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
    // 平铺模式：显隐变化后窗口条需重算（隐藏的固定位窗口保留 DOM，仅不显示）
    if (tileMode()) syncTiles();
  }
  export function applyRailStage() {
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
  export function applyRailOpacity() {
    let o = typeof railState.opacity === 'number' ? railState.opacity : 1;
    o = Math.min(1, Math.max(0, o));
    const rail = HOST.document.getElementById('rail');
    if (rail) rail.style.setProperty('--wm-rail-bg', 'rgba(248,248,249,' + o.toFixed(3) + ')');
  }
  export function cycleRail() {
    railState.stage = ((railState.stage + 1) % RAIL_STAGES) as 0 | 1;   // 0→1→0
    applyRailStage();
    persistRail().catch(() => {});
  }
  export function bindRailToggle() {
    const t = HOST.document.getElementById('railToggle');
    if (t) t.addEventListener('click', cycleRail);
  }
  export function setPluginHidden(id: string, hidden: boolean) {
    if (!railState.hidden) railState.hidden = {};
    if (hidden) railState.hidden[id] = true; else delete railState.hidden[id];
    const slot = slotOfPlugin(id);
    if (slot) {
      const p = groupState.plugins.find((x) => x.id === id);
      // fixed：单例槽内多个插件互斥，开关只作用于该插件本身，区域的显隐按插件开关重算
      if (p && (p.slotDef || {}).type === 'fixed') refreshFixedSlot(slot);
      else applySlotHidden(slot, hidden);
    }
    if (tileMode()) syncTiles();
    persistRail().catch(() => {});
  }
  export function buildRail() {
    const iconsEl = HOST.document.getElementById('railIcons');
    if (!iconsEl) return;
    applyRailStage();
    iconsEl.innerHTML = '';
    // 底部固定区独立重建，避免每次 buildRail 在其后追加导致设置按钮越积越多
    const footEl = HOST.document.getElementById('railFoot') || iconsEl;
    if (footEl !== iconsEl) footEl.innerHTML = '';
    // 白条只保留固定的几个区域图标：插件注册后按其声明的区域自动归入对应图标，
    // 同区域共用一个图标（多个插件时点击弹出候选菜单），命名与排列次序均由宿主决定。
    railAreaList().forEach((area) => { iconsEl.appendChild(makeAreaRailButton(area)); });
    // 设置按钮（宿主固有入口，独立归类为「设置」）：固定在白条最底部的固定区，
    // 不随上方区域图标列表滚动，也不属于任何插件区域（如弹窗类）。
    const sb = HOST.document.createElement('button');
    sb.className = 'rail-ico';
    sb.id = 'railSettings';
    sb.title = areaLabel('settings');
    const sg = HOST.document.createElement('span');
    sg.className = 'rail-glyph';
    paintIcon(sg, 'settings', '⚙');
    sb.appendChild(sg);
    const snm = HOST.document.createElement('span');
    snm.className = 'rail-name';
    snm.textContent = areaLabel('settings');
    sb.appendChild(snm);
    // 与区域/插件图标一致：未打开设置时按「关闭」态变淡，打开时高亮
    const sbOpen = HOST.document.body.classList.contains('settings-open');
    sb.classList.toggle('on', sbOpen);
    sb.classList.toggle('off', !sbOpen);
    sb.addEventListener('click', () => setSettingsOpen(!HOST.document.body.classList.contains('settings-open')));
    footEl.appendChild(sb);
    railButtons['__settings__'] = sb;
    applyRailOpacity();
  }

