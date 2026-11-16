// 平铺式布局：多行横向窗口条、Shift 拖拽排序/删除、右缘改宽、「+」窗口面板管理
import { broadcastAll, syncNativeCover } from './bus.js';
import { paintIcon, paintPluginIcon } from './icons.js';
import {
  LAYOUT_KEY_SESSION,
  LAYOUT_KEY_SIDEBAR,
  TILE_ADD_W,
  TILE_PIN_GAP,
  activeRow,
  activeRowIndex,
  addKeyToRow,
  createRow,
  ensureOrderInRow,
  isPanelKey,
  layoutState,
  panelIdFromKey,
  panelWindowKey,
  persistLayout,
  pinWidthValue,
  removeKeyFromRow,
  reorderInRow,
  rowIndexOfKey,
  setPinWidth,
  setWindowWidthIn,
  tileMode,
  windowWidthIn,
} from './layout.js';
import type { LayoutRow } from './layout.js';
import { mountFrame, notifyUnmount } from './mount.js';
import { closePanelMenus, closePanelTab, panelTabs } from './panel.js';
import { buildRail, railHidden, setPluginHidden } from './rail.js';
import { pluginVisible, togglePluginOpen } from './settings-tabs.js';
import { HOST, activeBySlot, frames, groupState, pluginBySlot, slotMap } from './state.js';
import type { PluginDescriptor, PluginFrame } from './types.js';

interface FixedAnchor {
  el: HTMLElement;
  parent: Node | null;
  next: Node | null;
}

// 一行的工作区视图：DOM 元素与 iframe 都按行独立持有，切行只切换显隐
interface RowView {
  row: LayoutRow;
  strip: HTMLElement;
  tiles: Record<string, HTMLElement>;          // 面板窗口键 -> 本行窗口元素
  frames: Record<string, PluginFrame | null>;  // 面板插件 id -> 本行 iframe
  addEl: HTMLElement | null;
}

const fixedAnchors: Record<string, FixedAnchor> = {};
const fixedTiles: Record<string, HTMLElement> = {};   // 列表位/会话位窗口：全局唯一，归属某一行
const rowViews: RowView[] = [];
let navEl: HTMLElement | null = null;
let pinBox: HTMLElement | null = null;   // 会话位固定容器（贴应用最左/最右）
let broadcastT: number | null = null;
let managing = false;   // Shift 拖拽进行中：期间不清理 dragging 状态

function panelPlugins(): PluginDescriptor[] {
  return groupState.plugins.filter((p) => (p.slotDef || {}).type === 'panel' && !!p.entry);
}

function pluginVisibleInSlot(slot: string): PluginDescriptor | null {
  const cur = pluginBySlot[slot];
  if (cur) return railHidden(cur.id) ? null : cur;
  const list = (slotMap[slot] || []).filter((p) => !railHidden(p.id));
  return list[0] || null;
}

// 滚动/改宽/重排/切行后通知插件（内置浏览器需同步原生视图 bounds）
function broadcastLayout(): void {
  if (broadcastT != null) return;
  broadcastT = HOST.setTimeout(() => {
    broadcastT = null;
    broadcastAll('host.layoutChanged', { mode: 'tile', activeRow: activeRowIndex() });
  }, 40);
}

// 复原拖拽期间写入的行内样式。拖拽时窗口临时改为 position:fixed，
// 脱离横向滚动容器的裁剪，才能真正跟住指针（否则滚过一屏后窗口会被切掉/掉队）。
function resetTileDrag(tile: HTMLElement): void {
  tile.classList.remove('dragging', 'removing');
  tile.style.position = '';
  tile.style.left = '';
  tile.style.top = '';
  tile.style.height = '';
  tile.style.margin = '';
  tile.style.transform = '';
}

// 插入位置指示线：拖拽时提示松手后窗口会落在哪条分界上
let dropLineEl: HTMLElement | null = null;
function hideDropLine(): void {
  if (dropLineEl) dropLineEl.style.display = 'none';
}
function showDropLine(x: number, top: number, height: number): void {
  if (!dropLineEl || !dropLineEl.isConnected) {
    dropLineEl = HOST.document.createElement('div');
    dropLineEl.className = 'wm-tile-drop';
    HOST.document.body.appendChild(dropLineEl);
  }
  dropLineEl.style.display = '';
  dropLineEl.style.left = Math.round(x) + 'px';
  dropLineEl.style.top = Math.round(top) + 'px';
  dropLineEl.style.height = Math.round(height) + 'px';
}

// Shift 按下才允许管理窗口；此时每个窗口盖一层透明接收层，避免事件落进 iframe
export function setShiftMode(on: boolean): void {
  const active = on && tileMode();
  HOST.document.body.classList.toggle('wm-shift-mode', active);
  if (!active && !managing) {
    hideDropLine();
    HOST.document.querySelectorAll('.wm-tile-placeholder').forEach((el) => el.remove());
    Object.keys(fixedTiles).forEach((k) => resetTileDrag(fixedTiles[k]));
    rowViews.forEach((rv) => Object.keys(rv.tiles).forEach((k) => resetTileDrag(rv.tiles[k])));
  }
}

// 输入焦点在可编辑元素上时不抢 Shift+方向键（保留文本选中）
function editableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || typeof el.tagName !== 'string') return false;
  const tag = el.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  return el.isContentEditable === true;
}

// Shift + ←/→：把当前行横向滚动吸附到相邻窗口的左边界（不改顺序与宽度）。
// 向右：第一个左缘不在可视区左边界上的窗口；向左：最后一个左缘在左边界左侧的窗口。
function snapScrollRow(dir: -1 | 1): void {
  const rv = rowViews[activeRowIndex()];
  if (!rv) return;
  const keys = sortedVisibleKeys(rv);
  if (!keys.length) return;
  const map = tilesOfRow(rv);
  const s = rv.strip.scrollLeft;
  let target = s;
  if (dir > 0) {
    for (let i = 0; i < keys.length; i++) {
      const x = map[keys[i]].offsetLeft;
      if (x - s > 1) { target = x; break; }
    }
  } else {
    for (let i = keys.length - 1; i >= 0; i--) {
      const x = map[keys[i]].offsetLeft;
      if (x - s < -1) { target = x; break; }
    }
  }
  if (target !== s) rv.strip.scrollLeft = target;
}

// Shift + 方向键：↑/↓ 换行，←/→ 行内按窗口边界横向滚动；返回 true 表示已处理（调用方应 preventDefault）
export function handleRowShortcut(ev: KeyboardEvent): boolean {
  if (!tileMode()) return false;
  if (HOST.document.body.classList.contains('settings-open')) return false;
  if (!ev.shiftKey || ev.altKey || ev.ctrlKey || ev.metaKey) return false;
  const key = ev.key;
  if (key !== 'ArrowUp' && key !== 'ArrowDown' && key !== 'ArrowLeft' && key !== 'ArrowRight') return false;
  if (editableTarget(ev.target)) return false;
  if (key === 'ArrowLeft' || key === 'ArrowRight') snapScrollRow(key === 'ArrowLeft' ? -1 : 1);
  else switchRow(key === 'ArrowUp' ? -1 : 1);
  return true;
}

HOST.addEventListener('keydown', (ev) => {
  if (ev.key === 'Shift') setShiftMode(true);
  if (handleRowShortcut(ev) || handlePinShortcut(ev)) ev.preventDefault();
});
HOST.addEventListener('keyup', (ev) => { if (ev.key === 'Shift') setShiftMode(false); });
HOST.addEventListener('blur', () => {
  // 窗口整体失焦：取消未完成的拖拽，避免接收层与 dragging 样式残留
  HOST.document.querySelectorAll('.wm-drag-layer').forEach((el) => el.remove());
  HOST.document.querySelectorAll('.wm-tile-placeholder').forEach((el) => el.remove());
  managing = false;
  hideDropLine();
  setShiftMode(false);
  Object.keys(fixedTiles).forEach((k) => resetTileDrag(fixedTiles[k]));
  rowViews.forEach((rv) => Object.keys(rv.tiles).forEach((k) => resetTileDrag(rv.tiles[k])));
});

function makeStrip(): HTMLElement {
  const el = HOST.document.createElement('div');
  el.className = 'wm-tiles';
  // 滚轮横向滚动：iframe 内部的滚轮归插件自己，宿主只处理间隙/空白
  el.addEventListener('wheel', (ev) => {
    if (!ev.deltaY) return;
    el.scrollLeft += ev.deltaY;
  }, { passive: true });
  el.addEventListener('scroll', broadcastLayout, { passive: true });
  // 空白处拖拽平移
  let panning = false;
  let panX = 0;
  let panScroll = 0;
  el.addEventListener('pointerdown', (ev) => {
    if (ev.target !== el || ev.button !== 0) return;
    panning = true;
    panX = ev.clientX;
    panScroll = el.scrollLeft;
    try { el.setPointerCapture(ev.pointerId); } catch (_) {}
  });
  el.addEventListener('pointermove', (ev) => {
    if (!panning) return;
    el.scrollLeft = panScroll - (ev.clientX - panX);
  });
  const endPan = () => { panning = false; };
  el.addEventListener('pointerup', endPan);
  el.addEventListener('pointercancel', endPan);
  HOST.document.body.appendChild(el);
  return el;
}

function makeRowView(row: LayoutRow): RowView {
  return { row, strip: makeStrip(), tiles: {}, frames: {}, addEl: null };
}

// 按行对象身份对齐视图：保留仍在配置里的行（切行/新建行都不重建 iframe）
function ensureRowViews(): void {
  const rows = layoutState.rows;
  for (let i = rowViews.length - 1; i >= 0; i--) {
    if (rows.indexOf(rowViews[i].row) >= 0) continue;
    notifyUnmount(rowViews[i].strip);
    rowViews[i].strip.remove();
    rowViews.splice(i, 1);
  }
  const next = rows.map((row) => rowViews.find((rv) => rv.row === row) || makeRowView(row));
  rowViews.length = 0;
  rowViews.push.apply(rowViews, next);
  const active = activeRowIndex();
  rowViews.forEach((rv, i) => rv.strip.classList.toggle('active', i === active));
}

function navButton(icon: string, title: string, dir: -1 | 1): HTMLElement {
  const btn = HOST.document.createElement('button');
  btn.className = 'wm-row-btn';
  btn.type = 'button';
  btn.title = title;
  btn.setAttribute('aria-label', title);
  paintIcon(btn, icon, dir < 0 ? '↑' : '↓');
  btn.addEventListener('click', () => switchRow(dir));
  return btn;
}

function ensureNav(): void {
  if (navEl && navEl.isConnected) return;
  const el = HOST.document.createElement('div');
  el.className = 'wm-row-nav';
  el.appendChild(navButton('chevron-up', '上一行（Shift+↑）', -1));
  el.appendChild(navButton('chevron-down', '下一行（Shift+↓）', 1));
  // 挂到顶部细条：细条整体是窗口拖拽区且不接收指针事件，样式里单独恢复
  const bar = HOST.document.querySelector('[data-layer="topbar"]');
  (bar || HOST.document.body).appendChild(el);
  navEl = el;
}

function rowHasWindows(i: number): boolean {
  const row = layoutState.rows[i];
  return !!row && row.order.length > 0;
}

function nearestNonEmptyRow(from: number, dir: -1 | 1): number {
  for (let i = from + dir; i >= 0 && i < layoutState.rows.length; i += dir) {
    if (rowHasWindows(i)) return i;
  }
  return -1;
}

// 空行只能回到最近的非空行；非空行到边界时新建空行
function canSwitchRow(dir: -1 | 1): boolean {
  const cur = activeRowIndex();
  if (!rowHasWindows(cur)) return nearestNonEmptyRow(cur, dir) >= 0;
  return true;
}

function updateNav(): void {
  if (!navEl) return;
  const btns = navEl.querySelectorAll('.wm-row-btn');
  const up = btns[0] as HTMLButtonElement | undefined;
  const down = btns[1] as HTMLButtonElement | undefined;
  const cur = activeRowIndex();
  if (up) {
    up.disabled = !canSwitchRow(-1);
    up.title = '上一行（Shift+↑） · 当前第 ' + (cur + 1) + ' / ' + layoutState.rows.length + ' 行';
  }
  if (down) {
    down.disabled = !canSwitchRow(1);
    down.title = '下一行（Shift+↓） · 当前第 ' + (cur + 1) + ' / ' + layoutState.rows.length + ' 行';
  }
}

export function switchRow(dir: -1 | 1): void {
  if (!tileMode() || !canSwitchRow(dir)) return;
  const rows = layoutState.rows;
  const cur = activeRowIndex();
  if (rowHasWindows(cur)) {
    const target = cur + dir;
    if (target >= 0 && target < rows.length) layoutState.activeRow = target;
    else if (dir < 0) { rows.unshift(createRow()); layoutState.activeRow = 0; }
    else { rows.push(createRow()); layoutState.activeRow = rows.length - 1; }
  } else {
    layoutState.activeRow = nearestNonEmptyRow(cur, dir);
  }
  syncTiles();
  persistLayout();
}

export function switchToRow(index: number): void {
  if (!tileMode()) return;
  if (index < 0 || index >= layoutState.rows.length) return;
  if (index === activeRowIndex()) return;
  layoutState.activeRow = index;
  syncTiles();
  persistLayout();
}

function tileBody(tile: HTMLElement): HTMLElement {
  return tile.querySelector('.wm-tile-body') as HTMLElement;
}

function rowViewOfStrip(strip: HTMLElement | null): RowView | null {
  if (!strip) return null;
  return rowViews.find((rv) => rv.strip === strip) || null;
}

// 本行当前挂着的窗口（面板 + 归属本行的固定位）
function tilesOfRow(rv: RowView): Record<string, HTMLElement> {
  const out: Record<string, HTMLElement> = {};
  Object.keys(rv.tiles).forEach((key) => { out[key] = rv.tiles[key]; });
  [LAYOUT_KEY_SIDEBAR, LAYOUT_KEY_SESSION].forEach((key) => {
    const tile = fixedTiles[key];
    if (tile && tile.parentElement === rv.strip) out[key] = tile;
  });
  return out;
}

function sortedVisibleKeys(rv: RowView): string[] {
  const map = tilesOfRow(rv);
  return Object.keys(map)
    .filter((k) => map[k].style.display !== 'none')
    .sort((a, b) => Number(map[a].style.order || 0) - Number(map[b].style.order || 0));
}

function closeFixedSlot(slot: string): void {
  const cur = pluginVisibleInSlot(slot);
  if (cur) setPluginHidden(cur.id, true);
}

function closeTileByKey(key: string): void {
  if (key === LAYOUT_KEY_SIDEBAR) closeFixedSlot('sidebar');
  else if (key === LAYOUT_KEY_SESSION) closeFixedSlot('session');
  else if (isPanelKey(key)) closePanelTab(panelIdFromKey(key));
  syncTiles();
  buildRail();
}

function bindResize(tile: HTMLElement, grip: HTMLElement, key: string): void {
  grip.addEventListener('pointerdown', (ev) => {
    // 行对象在拖拽开始时解析：窗口可能被换到别的行（固定位重开）
    const rv = rowViewOfStrip(tile.parentElement);
    const pinned = tile.classList.contains('wm-tile-pinned');
    if (!rv && !pinned) return;
    ev.preventDefault();
    ev.stopPropagation();
    const startX = ev.clientX;
    const startW = tile.getBoundingClientRect().width;
    // 右侧固定时手柄在左缘：往左拖变大，位移方向取反
    const sign = pinned && layoutState.pin === 'right' ? -1 : 1;
    const move = (e2: PointerEvent) => {
      if (pinned) {
        setPinWidth(startW + (e2.clientX - startX) * sign);
        tile.style.width = pinWidthValue() + 'px';
        applyPinMetrics();
      } else if (rv) {
        setWindowWidthIn(rv.row, key, startW + (e2.clientX - startX));
        tile.style.width = windowWidthIn(rv.row, key) + 'px';
      }
      broadcastLayout();
    };
    const up = () => {
      grip.removeEventListener('pointermove', move);
      grip.removeEventListener('pointerup', up);
      grip.removeEventListener('pointercancel', up);
      try { grip.releasePointerCapture(ev.pointerId); } catch (_) {}
      persistLayout();
      broadcastLayout();
    };
    try { grip.setPointerCapture(ev.pointerId); } catch (_) {}
    grip.addEventListener('pointermove', move);
    grip.addEventListener('pointerup', up);
    grip.addEventListener('pointercancel', up);
  });
}

// Shift + 拖拽：窗口临时脱离文档流跟手（position:fixed），横向移动换位；
// 向下拖过窗口高度一半标记删除，松开时关闭
function bindManageDrag(tile: HTMLElement, shield: HTMLElement, key: string): void {
  shield.addEventListener('pointerdown', (ev) => {
    if (!HOST.document.body.classList.contains('wm-shift-mode') || ev.button !== 0) return;
    const rv = rowViewOfStrip(tile.parentElement);
    if (!rv) return;
    ev.preventDefault();
    ev.stopPropagation();
    const strip = rv.strip;
    const rect = tile.getBoundingClientRect();
    const startY = ev.clientY;
    const removeAt = Math.max(80, rect.height / 2);   // 向下拖过窗口高度一半（至少 80px）= 删除
    let removing = false;
    let done = false;
    let lastX = ev.clientX;
    let offsetX = 0;   // 相对按下位置的横向位移
    managing = true;
    // 脱离文档流：窗口按视口坐标跟手，不再被横向滚动容器裁剪，
    // 跨过一屏窗口时也不会和鼠标拉开距离
    tile.classList.add('dragging');
    tile.style.position = 'fixed';
    tile.style.left = rect.left + 'px';
    tile.style.top = rect.top + 'px';
    tile.style.height = rect.height + 'px';
    tile.style.margin = '0';
    // 占位块留在原位：其它窗口不因窗口被拎起而移动，插入判断与指示线才不会跳
    const placeholder = HOST.document.createElement('div');
    placeholder.className = 'wm-tile-placeholder';
    placeholder.style.width = rect.width + 'px';
    if (tile.parentElement) tile.parentElement.insertBefore(placeholder, tile);
    // 全屏接收层：拖出源窗口后指针仍归宿主（否则事件落进其它 iframe 会丢失）
    const layer = HOST.document.createElement('div');
    layer.className = 'wm-drag-layer';
    HOST.document.body.appendChild(layer);
    let pointerX = ev.clientX;
    // 未移动就松手时保持原位：当前下标即它在其它窗口中的插入位置
    let targetIndex = Math.max(0, sortedVisibleKeys(rv).indexOf(key));
    // 依据指针位置算出插入下标，并把指示线画在对应分界处（不实时重排，松手才落位）
    const updateIndicator = (x: number): number => {
      const map = tilesOfRow(rv);
      const others = sortedVisibleKeys(rv).filter((k) => k !== key);
      if (!others.length) { hideDropLine(); return 0; }
      let index = others.length;
      for (let i = 0; i < others.length; i++) {
        const r = map[others[i]].getBoundingClientRect();
        if (x < r.left + r.width / 2) { index = i; break; }
      }
      const sr = strip.getBoundingClientRect();
      let lineX: number;
      // 指示线画在插入槽的前沿：首个槽贴第一个窗口左侧，其余槽贴前一个窗口右侧
      if (index === 0) lineX = map[others[0]].getBoundingClientRect().left - 4;
      else lineX = map[others[index - 1]].getBoundingClientRect().right + 4;
      showDropLine(lineX, sr.top + 6, Math.max(40, sr.height - 12));
      return index;
    };
    const move = (e2: PointerEvent) => {
      pointerX = e2.clientX;
      offsetX += e2.clientX - lastX;
      lastX = e2.clientX;
      const dy = e2.clientY - startY;
      const willRemove = dy >= removeAt;
      if (willRemove !== removing) {
        removing = willRemove;
        tile.classList.toggle('removing', removing);
      }
      tile.style.left = Math.round(rect.left + offsetX) + 'px';
      tile.style.top = Math.round(rect.top + (removing ? Math.min(dy - removeAt, 40) : 0)) + 'px';
      if (removing) { hideDropLine(); return; }
      // 拖到窗口条左右边缘时自动横向滚动，便于把窗口拖到视口外
      const sr = strip.getBoundingClientRect();
      if (e2.clientX < sr.left + 56) strip.scrollLeft -= 20;
      else if (e2.clientX > sr.right - 56) strip.scrollLeft += 20;
      targetIndex = updateIndicator(pointerX);
    };
    // 自动滚动会带着其它窗口移动，指示线要跟着重算
    const onScroll = () => { if (!removing) targetIndex = updateIndicator(pointerX); };
    strip.addEventListener('scroll', onScroll, { passive: true });
    const finish = (commit: boolean) => {
      if (done) return;
      done = true;
      managing = false;
      layer.removeEventListener('pointermove', move);
      layer.removeEventListener('pointerup', up);
      layer.removeEventListener('pointercancel', cancel);
      strip.removeEventListener('scroll', onScroll);
      try { layer.releasePointerCapture(ev.pointerId); } catch (_) {}
      layer.remove();
      placeholder.remove();
      hideDropLine();
      if (commit && !removing) {
        // 落位：按指示线所在分界插入，再让窗口回到文档流
        const others = sortedVisibleKeys(rv).filter((k) => k !== key);
        const next = others.slice();
        next.splice(Math.max(0, Math.min(next.length, targetIndex)), 0, key);
        reorderInRow(rv.row, next);
        applyOrder(rv);
        persistLayout();
      }
      resetTileDrag(tile);   // 落回文档流，按新顺序归位
      if (commit && removing) closeTileByKey(key);
      broadcastLayout();
    };
    const up = () => finish(true);
    const cancel = () => finish(false);
    try { layer.setPointerCapture(ev.pointerId); } catch (_) {}
    layer.addEventListener('pointermove', move);
    layer.addEventListener('pointerup', up);
    layer.addEventListener('pointercancel', cancel);
  });
}

function makeTile(key: string): HTMLElement {
  const tile = HOST.document.createElement('div');
  tile.className = 'wm-tile';
  tile.dataset.key = key;
  const body = HOST.document.createElement('div');
  body.className = 'wm-tile-body';
  const shield = HOST.document.createElement('div');
  shield.className = 'wm-tile-shield';
  const grip = HOST.document.createElement('div');
  grip.className = 'wm-tile-resize';
  grip.title = '拖动调整宽度';
  tile.appendChild(body);
  tile.appendChild(shield);
  tile.appendChild(grip);
  bindManageDrag(tile, shield, key);
  bindResize(tile, grip, key);
  return tile;
}

// 列表位/会话位的锚点（含其 iframe）整体移入窗口，避免重建 iframe
function moveAnchorInto(body: HTMLElement, slot: string): void {
  const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`) as HTMLElement | null;
  if (!anchor) return;
  if (!fixedAnchors[slot]) {
    fixedAnchors[slot] = { el: anchor, parent: anchor.parentNode, next: anchor.nextSibling };
  }
  if (anchor.parentNode !== body) body.appendChild(anchor);
}

// 会话位固定：窗口移出窗口条贴到应用最左/最右，窗口条据此让位
function ensurePinBox(side: 'left' | 'right'): HTMLElement {
  if (pinBox && pinBox.isConnected) {
    pinBox.classList.toggle('wm-pin-left', side === 'left');
    pinBox.classList.toggle('wm-pin-right', side === 'right');
    return pinBox;
  }
  const el = HOST.document.createElement('div');
  el.className = 'wm-pin ' + (side === 'left' ? 'wm-pin-left' : 'wm-pin-right');
  HOST.document.body.appendChild(el);
  pinBox = el;
  return el;
}

// 窗口条让位：左侧固定让出左边，右侧固定让出右边（CSS 变量由 body 上的类选择）
function applyPinMetrics(): void {
  const body = HOST.document.body;
  const tile = fixedTiles[LAYOUT_KEY_SESSION];
  const side = tileMode() && tile && tile.style.display !== 'none' ? layoutState.pin : '';
  body.classList.toggle('wm-pin-left', side === 'left');
  body.classList.toggle('wm-pin-right', side === 'right');
  const w = side ? pinWidthValue() : 0;
  body.style.setProperty('--wm-pin-w', w ? (w + TILE_PIN_GAP) + 'px' : '0px');
  if (pinBox) pinBox.style.width = w ? w + 'px' : '0px';
}

// 首次固定会沿用窗口当前宽度：超过可用空间时收缩到可用宽度
function clampPinToViewport(): void {
  const rv = rowViews[activeRowIndex()];
  const stripW = rv ? rv.strip.getBoundingClientRect().width : HOST.innerWidth - 80;
  const full = layoutState.pin ? stripW + pinWidthValue() + TILE_PIN_GAP : stripW;
  setPinWidth(Math.min(pinWidthValue(), Math.max(260, full - TILE_PIN_GAP)));
}

// 解除固定：会话位回到当前行的窗口条（固定态下它不属于任何行，这里重新登记归属）
function unpinSession(): void {
  if (!layoutState.pin) return;
  layoutState.pin = '';
  addKeyToRow(activeRow(), LAYOUT_KEY_SESSION);
  syncTiles();
  persistLayout();
}

function togglePin(side: 'left' | 'right'): void {
  const tile = fixedTiles[LAYOUT_KEY_SESSION];
  if (!tile || tile.style.display === 'none') return;   // 会话位未打开：不进入固定态
  const cur = layoutState.pin;
  if (cur === side) return;                 // 已固定在同一侧：同方向键不再改变
  if (cur) { unpinSession(); return; }      // 固定在另一侧：按反方向键 = 解除固定
  const w = Math.round(tile.getBoundingClientRect().width);
  if (w > 0) setPinWidth(w);
  clampPinToViewport();
  // 固定态：会话位不属于任何行，先从所有行的顺序表里摘掉（避免被当成行内窗口）
  layoutState.rows.forEach((row) => removeKeyFromRow(row, LAYOUT_KEY_SESSION));
  layoutState.pin = side;
  syncTiles();
  persistLayout();
}

// Ctrl + ←/→：会话位固定到最左/最右；已固定在一侧时按相反方向键解除固定
export function handlePinShortcut(ev: KeyboardEvent): boolean {
  if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return false;
  if (!ev.ctrlKey || ev.shiftKey || ev.altKey || ev.metaKey) return false;
  if (!tileMode()) return false;
  if (HOST.document.body.classList.contains('settings-open')) return false;
  if (editableTarget(ev.target)) return false;
  const tile = fixedTiles[LAYOUT_KEY_SESSION];
  if (!tile || tile.style.display === 'none') return true;
  togglePin(ev.key === 'ArrowLeft' ? 'left' : 'right');
  return true;
}

// 固定位是全局单例：只归属一行，其它行不再重复挂载
function syncFixedWindow(key: string, slot: string): void {
  const p = pluginVisibleInSlot(slot);
  if (!p) {
    layoutState.rows.forEach((row) => removeKeyFromRow(row, key));
    const tile = fixedTiles[key];
    if (tile) {
      tile.style.display = 'none';
      tile.classList.remove('wm-tile-pinned', 'wm-tile-pin-right');
    }
    applyPinMetrics();
    return;
  }
  let tile = fixedTiles[key];
  if (!tile) {
    tile = makeTile(key);
    fixedTiles[key] = tile;
  }
  const side = key === LAYOUT_KEY_SESSION ? layoutState.pin : '';
  if (side) {
    // 固定窗口脱离窗口条，也不属于任何行：行顺序表里不留它的登记
    layoutState.rows.forEach((row) => removeKeyFromRow(row, key));
    const box = ensurePinBox(side);
    if (tile.parentElement !== box) box.appendChild(tile);
    tile.classList.add('wm-tile-pinned');
    tile.classList.toggle('wm-tile-pin-right', side === 'right');
    tile.style.width = pinWidthValue() + 'px';
  } else {
    let owner = rowIndexOfKey(key);
    if (owner < 0) {
      // 新打开 / 刚解除固定：落在当前行
      owner = activeRowIndex();
      addKeyToRow(layoutState.rows[owner], key);
    } else {
      layoutState.rows.forEach((row, i) => { if (i !== owner) removeKeyFromRow(row, key); });
    }
    const rv = rowViews[owner];
    if (!rv) return;
    if (tile.parentElement !== rv.strip) rv.strip.appendChild(tile);
    tile.classList.remove('wm-tile-pinned', 'wm-tile-pin-right');
    tile.style.width = windowWidthIn(rv.row, key) + 'px';
    if (pinBox && !pinBox.firstChild) { pinBox.remove(); pinBox = null; }
  }
  moveAnchorInto(tileBody(tile), slot);
  tile.style.display = '';
  applyPinMetrics();
}

function syncRowPanels(rv: RowView): void {
  const panels = panelPlugins();
  const byId: Record<string, PluginDescriptor> = {};
  panels.forEach((p) => { byId[p.id] = p; });
  const open: PluginDescriptor[] = [];
  rv.row.order.forEach((key) => {
    if (!isPanelKey(key)) return;
    const p = byId[panelIdFromKey(key)];
    if (p && !railHidden(p.id)) open.push(p);
  });
  open.forEach((p) => {
    const key = panelWindowKey(p.id);
    let tile = rv.tiles[key];
    if (!tile) {
      tile = makeTile(key);
      rv.strip.appendChild(tile);
      rv.tiles[key] = tile;
    }
    const body = tileBody(tile);
    if (!body.isConnected) tile.appendChild(body);   // 重载后挂载点被移出文档时先接回窗口
    const rec = rv.frames[p.id];
    // manifest 重载会清掉动态实例的挂载点：记录失效时按当前窗口体重挂
    if (!rec || !rec.el.isConnected || rec.el !== body) rv.frames[p.id] = mountFrame(body, p);
    tile.style.display = '';
  });
  // 关闭的面板窗口：卸载并移除
  Object.keys(rv.tiles).forEach((key) => {
    const id = panelIdFromKey(key);
    if (open.some((p) => p.id === id)) return;
    notifyUnmount(rv.tiles[key]);
    rv.tiles[key].remove();
    delete rv.tiles[key];
    delete rv.frames[id];
  });
}

function ensureAddTile(rv: RowView): void {
  if (rv.addEl && rv.addEl.isConnected) return;
  const tile = HOST.document.createElement('div');
  tile.className = 'wm-tile wm-tile-add';
  tile.title = '选择要开启的插件';
  tile.style.width = TILE_ADD_W + 'px';
  tile.style.order = '99999';
  const plus = HOST.document.createElement('span');
  plus.className = 'wm-tile-add-plus';
  paintIcon(plus, 'plus', '+');
  const label = HOST.document.createElement('span');
  label.textContent = '添加';
  tile.appendChild(plus);
  tile.appendChild(label);
  tile.addEventListener('click', (ev) => {
    ev.stopPropagation();
    openTileAddMenu(tile);
  });
  rv.strip.appendChild(tile);
  rv.addEl = tile;
}

function menuItem(p: PluginDescriptor, on: boolean, onclick: () => void, tag?: string): HTMLElement {
  const item = HOST.document.createElement('div');
  item.className = 'wm-pp_menu-item' + (on ? ' active' : '');
  const g = HOST.document.createElement('span');
  g.className = 'wm-pp_menu-ico';
  paintPluginIcon(g, p);
  const nm = HOST.document.createElement('span');
  nm.textContent = p.name || p.id;
  item.appendChild(g);
  item.appendChild(nm);
  const text = tag != null ? tag : (on ? '已打开' : '');
  if (text) {
    const tagEl = HOST.document.createElement('span');
    tagEl.className = 'wm-pp_menu-tag';
    tagEl.textContent = text;
    item.appendChild(tagEl);
  }
  item.addEventListener('click', onclick);
  return item;
}

function menuSection(menu: HTMLElement, title: string): void {
  const head = HOST.document.createElement('div');
  head.className = 'wm-tile-menu-head';
  head.textContent = title;
  menu.appendChild(head);
}

function fixedKeyFor(p: PluginDescriptor): string {
  if ((p.slotDef || {}).type !== 'fixed') return '';
  if (p.slot === 'sidebar') return LAYOUT_KEY_SIDEBAR;
  if (p.slot === 'session') return LAYOUT_KEY_SESSION;
  return '';
}

// 会话位搬进当前行：先解除固定，再从原归属行摘掉，追加到当前行窗口条末尾
function moveFixedToActiveRow(key: string): void {
  if (key === LAYOUT_KEY_SESSION && layoutState.pin) layoutState.pin = '';
  layoutState.rows.forEach((row) => removeKeyFromRow(row, key));
  addKeyToRow(activeRow(), key);
  syncTiles();
  persistLayout();
}

// 「+」窗口：平铺模式下统一的插件开/关入口（只管理当前行的窗口）
function openTileAddMenu(anchor: HTMLElement): void {
  const wasOpen = !!HOST.document.getElementById('tile-add-menu');
  closePanelMenus();
  if (wasOpen) return;
  const menu = HOST.document.createElement('div');
  menu.className = 'wm-pp_menu';
  menu.id = 'tile-add-menu';
  const toggle = (p: PluginDescriptor) => {
    closePanelMenus();
    togglePluginOpen(p);
    syncTiles();
    buildRail();
  };
  const fixedAreas: Array<[string, string]> = [['sidebar', '列表位'], ['session', '会话位']];
  fixedAreas.forEach(([area, label]) => {
    const list = groupState.plugins.filter((p) => (p.slotDef || {}).area === area && !!p.entry);
    if (!list.length) return;
    menuSection(menu, label);
    list.forEach((p) => {
      const key = fixedKeyFor(p);
      const open = pluginVisible(p);
      const owner = open ? rowIndexOfKey(key) : -1;
      // 会话位：处于固定态或挂在别的行时不再跳转，直接搬进当前窗口条末尾
      if (key === LAYOUT_KEY_SESSION && open && (layoutState.pin !== '' || owner !== activeRowIndex())) {
        menu.appendChild(menuItem(p, true, () => {
          closePanelMenus();
          moveFixedToActiveRow(key);
        }, '移至本行'));
        return;
      }
      // 固定位是全局单例：在别的行打开时只标注并跳过去，不重复挂载
      if (open && owner >= 0 && owner !== activeRowIndex()) {
        menu.appendChild(menuItem(p, false, () => {
          closePanelMenus();
          switchToRow(owner);
        }, '第 ' + (owner + 1) + ' 行'));
      } else {
        menu.appendChild(menuItem(p, open, () => toggle(p)));
      }
    });
  });
  const panels = panelPlugins();
  if (panels.length) {
    menuSection(menu, '面板');
    panels.forEach((p) => menu.appendChild(menuItem(p, pluginVisible(p), () => toggle(p))));
  }
  HOST.document.body.appendChild(menu);
  const r = anchor.getBoundingClientRect();
  const left = Math.max(8, r.left - menu.offsetWidth - 8);
  menu.style.left = left + 'px';
  menu.style.right = 'auto';
  menu.style.top = Math.max(8, Math.min(r.top, HOST.innerHeight - menu.offsetHeight - 8)) + 'px';
  syncNativeCover();
}

function applyOrder(rv: RowView): void {
  const order = rv.row.order;
  const rank = (k: string) => { const i = order.indexOf(k); return i < 0 ? order.length : i; };
  const map = tilesOfRow(rv);
  Object.keys(map).forEach((k) => { map[k].style.order = String(rank(k)); });
  if (rv.addEl) rv.addEl.style.order = '99999';
}

// 未打开任何面板且从未保存过标签列表时，默认打开第一个（与容器式一致）。
// 每次进入平铺模式只补开一次：用户主动关光后不再自动补开。
let defaultSeeded = false;
function seedDefaultPanel(): void {
  if (defaultSeeded) return;
  defaultSeeded = true;
  const panels = panelPlugins();
  if (!panels.length) return;
  const anyOpen = layoutState.rows.some((row) => row.order.some(isPanelKey));
  if (anyOpen) return;
  const hasSavedTabs = Object.prototype.hasOwnProperty.call(activeBySlot, '__panelTabs__');
  const inherited = (panelTabs as string[]).filter((id) => panels.some((p) => p.id === id));
  if (!inherited.length && hasSavedTabs) return;   // 明确关光过：不再自动补开
  const legacy = panels.find((p) => p.id === activeBySlot['panel']);
  const targets = inherited.length ? inherited : [(legacy || panels[0]).id];
  targets.forEach((id) => addKeyToRow(activeRow(), panelWindowKey(id)));
}

// 面板窗口列表在各行之间取并集，切回容器式时沿用
function syncPanelTabsMirror(): void {
  const union: string[] = [];
  layoutState.rows.forEach((row) => row.order.forEach((key) => {
    if (!isPanelKey(key)) return;
    const id = panelIdFromKey(key);
    if (union.indexOf(id) < 0) union.push(id);
  }));
  (panelTabs as string[]).length = 0;
  (panelTabs as string[]).push.apply(panelTabs as string[], union);
}

export function syncTiles(): void {
  if (!tileMode()) { teardownTiles(); return; }
  ensureNav();
  ensureRowViews();
  seedDefaultPanel();

  // 固定位：全局单例，只归属一行；面板：每行独立实例
  syncFixedWindow(LAYOUT_KEY_SIDEBAR, 'sidebar');
  syncFixedWindow(LAYOUT_KEY_SESSION, 'session');
  rowViews.forEach(syncRowPanels);

  let orderChanged = false;
  rowViews.forEach((rv) => {
    const before = rv.row.order.join('\u0000');
    const visible = sortedVisibleKeys(rv);
    ensureOrderInRow(rv.row, visible);
    if (before !== rv.row.order.join('\u0000')) orderChanged = true;
    applyOrder(rv);
    const map = tilesOfRow(rv);
    Object.keys(map).forEach((k) => { map[k].style.width = windowWidthIn(rv.row, k) + 'px'; });
    ensureAddTile(rv);
  });

  // 广播/链接投递仍以 'panel' 为槽键：汇总所有行的面板帧
  const panelFrames: PluginFrame[] = [];
  rowViews.forEach((rv) => Object.keys(rv.frames).forEach((id) => {
    const frame = rv.frames[id];
    if (frame) panelFrames.push(frame);
  }));
  frames['panel'] = panelFrames;
  syncPanelTabsMirror();

  updateNav();
  if (orderChanged) persistLayout();
  broadcastLayout();
  syncNativeCover();
}

export function scrollTileIntoView(key: string): void {
  const rv = rowViews[activeRowIndex()];
  if (!rv) return;
  const tile = rv.tiles[key];
  if (!tile) return;
  const left = tile.offsetLeft;
  const right = left + tile.offsetWidth;
  if (left < rv.strip.scrollLeft) rv.strip.scrollLeft = left - 8;
  else if (right > rv.strip.scrollLeft + rv.strip.clientWidth) {
    rv.strip.scrollLeft = right - rv.strip.clientWidth + 8;
  }
}

export function teardownTiles(): void {
  // 先把固定锚点（连同其 iframe）移回原位，再接续容器式布局；
  // 再对仍留在窗口条内的面板帧发 unmount，避免误伤刚重建的固定位插件
  Object.keys(fixedAnchors).forEach((slot) => {
    const rec = fixedAnchors[slot];
    if (rec.el.parentNode && rec.parent) {
      if (rec.next && rec.next.parentNode === rec.parent) rec.parent.insertBefore(rec.el, rec.next);
      else rec.parent.appendChild(rec.el);
    }
    delete fixedAnchors[slot];
  });
  rowViews.forEach((rv) => { notifyUnmount(rv.strip); rv.strip.remove(); });
  rowViews.length = 0;
  Object.keys(fixedTiles).forEach((k) => delete fixedTiles[k]);
  if (pinBox) { pinBox.remove(); pinBox = null; }
  HOST.document.body.classList.remove('wm-pin-left', 'wm-pin-right');
  HOST.document.body.style.removeProperty('--wm-pin-w');
  if (navEl) { navEl.remove(); navEl = null; }
  if (dropLineEl) { dropLineEl.remove(); dropLineEl = null; }
  defaultSeeded = false;
  // 不清 frames['panel']：容器式重建时 mountPanels 已先写入本模式的帧，
  // 在这里删除会让容器里面板收不到广播与动作来源反查。
  setShiftMode(false);
}
