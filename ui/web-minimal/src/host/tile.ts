// 平铺式布局：横向窗口条、Shift 拖拽排序/删除、右缘改宽、「+」窗口面板管理
import { broadcastAll, syncNativeCover } from './bus.js';
import { paintIcon, paintPluginIcon } from './icons.js';
import {
  LAYOUT_KEY_SESSION,
  LAYOUT_KEY_SIDEBAR,
  TILE_ADD_W,
  ensureOrder,
  layoutState,
  panelWindowKey,
  persistLayout,
  reorderWindows,
  setWindowWidth,
  tileMode,
  windowWidth,
} from './layout.js';
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

const fixedAnchors: Record<string, FixedAnchor> = {};
const tileEls: Record<string, HTMLElement> = {};
const tileFrames: Record<string, PluginFrame | null> = {};
let stripEl: HTMLElement | null = null;
let addEl: HTMLElement | null = null;
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

// 滚动/改宽/重排后通知插件（内置浏览器需同步原生视图 bounds）
function broadcastLayout(): void {
  if (broadcastT != null) return;
  broadcastT = HOST.setTimeout(() => {
    broadcastT = null;
    broadcastAll('host.layoutChanged', { mode: 'tile' });
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
    Object.keys(tileEls).forEach((k) => resetTileDrag(tileEls[k]));
  }
}

HOST.addEventListener('keydown', (ev) => { if (ev.key === 'Shift') setShiftMode(true); });
HOST.addEventListener('keyup', (ev) => { if (ev.key === 'Shift') setShiftMode(false); });
HOST.addEventListener('blur', () => {
  // 窗口整体失焦：取消未完成的拖拽，避免接收层与 dragging 样式残留
  HOST.document.querySelectorAll('.wm-drag-layer').forEach((el) => el.remove());
  HOST.document.querySelectorAll('.wm-tile-placeholder').forEach((el) => el.remove());
  managing = false;
  hideDropLine();
  setShiftMode(false);
  Object.keys(tileEls).forEach((k) => resetTileDrag(tileEls[k]));
});

function ensureStrip(): HTMLElement {
  if (stripEl && stripEl.isConnected) return stripEl;
  const el = HOST.document.createElement('div');
  el.className = 'wm-tiles';
  el.id = 'wmTiles';
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
  stripEl = el;
  return el;
}

function tileBody(tile: HTMLElement): HTMLElement {
  return tile.querySelector('.wm-tile-body') as HTMLElement;
}

function closeFixedSlot(slot: string): void {
  const cur = pluginVisibleInSlot(slot);
  if (cur) setPluginHidden(cur.id, true);
}

function closeTileByKey(key: string): void {
  if (key === LAYOUT_KEY_SIDEBAR) closeFixedSlot('sidebar');
  else if (key === LAYOUT_KEY_SESSION) closeFixedSlot('session');
  else if (key.indexOf('panel:') === 0) closePanelTab(key.slice('panel:'.length));
  syncTiles();
  buildRail();
}

function bindResize(tile: HTMLElement, grip: HTMLElement, key: string): void {
  grip.addEventListener('pointerdown', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    const startX = ev.clientX;
    const startW = tile.getBoundingClientRect().width;
    const move = (e2: PointerEvent) => {
      setWindowWidth(key, startW + (e2.clientX - startX));
      tile.style.width = windowWidth(key) + 'px';
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

function sortedVisibleKeys(): string[] {
  return Object.keys(tileEls)
    .filter((k) => tileEls[k].style.display !== 'none')
    .sort((a, b) => Number(tileEls[a].style.order || 0) - Number(tileEls[b].style.order || 0));
}

// Shift + 拖拽：窗口临时脱离文档流跟手（position:fixed），横向移动换位；
// 向下拖过窗口高度一半标记删除，松开时关闭
function bindManageDrag(tile: HTMLElement, shield: HTMLElement, key: string): void {
  shield.addEventListener('pointerdown', (ev) => {
    if (!HOST.document.body.classList.contains('wm-shift-mode') || ev.button !== 0) return;
    ev.preventDefault();
    ev.stopPropagation();
    const strip = stripEl;
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
    let targetIndex = Math.max(0, sortedVisibleKeys().indexOf(key));
    // 依据指针位置算出插入下标，并把指示线画在对应分界处（不实时重排，松手才落位）
    const updateIndicator = (x: number): number => {
      if (!strip) { hideDropLine(); return 0; }
      const others = sortedVisibleKeys().filter((k) => k !== key);
      if (!others.length) { hideDropLine(); return 0; }
      let index = others.length;
      for (let i = 0; i < others.length; i++) {
        const r = tileEls[others[i]].getBoundingClientRect();
        if (x < r.left + r.width / 2) { index = i; break; }
      }
      const sr = strip.getBoundingClientRect();
      let lineX: number;
      // 指示线画在插入槽的前沿：首个槽贴第一个窗口左侧，其余槽贴前一个窗口右侧
      if (index === 0) lineX = tileEls[others[0]].getBoundingClientRect().left - 4;
      else lineX = tileEls[others[index - 1]].getBoundingClientRect().right + 4;
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
      if (strip) {
        // 拖到窗口条左右边缘时自动横向滚动，便于把窗口拖到视口外
        const sr = strip.getBoundingClientRect();
        if (e2.clientX < sr.left + 56) strip.scrollLeft -= 20;
        else if (e2.clientX > sr.right - 56) strip.scrollLeft += 20;
      }
      targetIndex = updateIndicator(pointerX);
    };
    // 自动滚动会带着其它窗口移动，指示线要跟着重算
    const onScroll = () => { if (!removing) targetIndex = updateIndicator(pointerX); };
    if (strip) strip.addEventListener('scroll', onScroll, { passive: true });
    const finish = (commit: boolean) => {
      if (done) return;
      done = true;
      managing = false;
      layer.removeEventListener('pointermove', move);
      layer.removeEventListener('pointerup', up);
      layer.removeEventListener('pointercancel', cancel);
      if (strip) strip.removeEventListener('scroll', onScroll);
      try { layer.releasePointerCapture(ev.pointerId); } catch (_) {}
      layer.remove();
      placeholder.remove();
      hideDropLine();
      if (commit && !removing) {
        // 落位：按指示线所在分界插入，再让窗口回到文档流
        const others = sortedVisibleKeys().filter((k) => k !== key);
        const next = others.slice();
        next.splice(Math.max(0, Math.min(next.length, targetIndex)), 0, key);
        reorderWindows(next);
        applyOrder();
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

function syncFixedTile(strip: HTMLElement, key: string, slot: string): boolean {
  let tile = tileEls[key];
  if (!tile) {
    tile = makeTile(key);
    strip.appendChild(tile);
    tileEls[key] = tile;
  }
  moveAnchorInto(tileBody(tile), slot);
  const on = !!pluginVisibleInSlot(slot);
  tile.style.display = on ? '' : 'none';
  return on;
}

function ensureAddTile(strip: HTMLElement): void {
  if (addEl && addEl.isConnected) return;
  const tile = HOST.document.createElement('div');
  tile.className = 'wm-tile wm-tile-add';
  tile.id = 'wmTileAdd';
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
  strip.appendChild(tile);
  addEl = tile;
}

function menuItem(p: PluginDescriptor, on: boolean, onclick: () => void): HTMLElement {
  const item = HOST.document.createElement('div');
  item.className = 'wm-pp_menu-item' + (on ? ' active' : '');
  const g = HOST.document.createElement('span');
  g.className = 'wm-pp_menu-ico';
  paintPluginIcon(g, p);
  const nm = HOST.document.createElement('span');
  nm.textContent = p.name || p.id;
  item.appendChild(g);
  item.appendChild(nm);
  if (on) {
    const tag = HOST.document.createElement('span');
    tag.className = 'wm-pp_menu-tag';
    tag.textContent = '已打开';
    item.appendChild(tag);
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

// 「+」窗口：平铺模式下统一的插件开/关入口
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
    list.forEach((p) => menu.appendChild(menuItem(p, pluginVisible(p), () => toggle(p))));
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

function applyOrder(): void {
  const order = layoutState.order;
  const rank = (k: string) => { const i = order.indexOf(k); return i < 0 ? order.length : i; };
  Object.keys(tileEls).forEach((k) => { tileEls[k].style.order = String(rank(k)); });
  if (addEl) addEl.style.order = '99999';
}

export function syncTiles(): void {
  if (!tileMode()) { teardownTiles(); return; }
  const strip = ensureStrip();
  const panels = panelPlugins();
  // 与容器式一致：从未保存过标签列表时默认打开第一个面板；用户主动关光后不再自动补开
  const hasSavedTabs = Object.prototype.hasOwnProperty.call(activeBySlot, '__panelTabs__');
  if (!panelTabs.length && !hasSavedTabs && panels.length) {
    const legacy = panels.find((p) => p.id === activeBySlot['panel']);
    panelTabs.push((legacy || panels[0]).id);
  }
  const validPanels = panels.filter(
    (p) => (panelTabs as string[]).indexOf(p.id) >= 0 && !railHidden(p.id),
  );

  const sidebarOn = syncFixedTile(strip, LAYOUT_KEY_SIDEBAR, 'sidebar');
  const sessionOn = syncFixedTile(strip, LAYOUT_KEY_SESSION, 'session');

  validPanels.forEach((p) => {
    const key = panelWindowKey(p.id);
    let tile = tileEls[key];
    if (!tile) {
      tile = makeTile(key);
      strip.appendChild(tile);
      tileEls[key] = tile;
    }
    const body = tileBody(tile);
    if (!tileFrames[p.id]) tileFrames[p.id] = mountFrame(body, p);
    tile.style.display = '';
  });

  // 关闭的面板窗口：卸载并移除
  Object.keys(tileEls).forEach((key) => {
    if (key.indexOf('panel:') !== 0) return;
    const id = key.slice('panel:'.length);
    if (validPanels.some((p) => p.id === id)) return;
    notifyUnmount(tileEls[key]);
    tileEls[key].remove();
    delete tileEls[key];
    delete tileFrames[id];
  });

  // 广播/链接投递仍以 'panel' 为槽键
  frames['panel'] = validPanels
    .map((p) => tileFrames[p.id])
    .filter(Boolean) as PluginFrame[];

  ensureAddTile(strip);

  // 只登记当前真正显示的窗口：关闭的窗口从顺序表移除，重新打开才会追加到最右端。
  // 已关闭的固定位也留在表里会导致它们重开时回到旧位置（例如一直排在第一个）。
  const visible = (sidebarOn ? [LAYOUT_KEY_SIDEBAR] : [])
    .concat(validPanels.map((p) => panelWindowKey(p.id)))
    .concat(sessionOn ? [LAYOUT_KEY_SESSION] : []);
  const orderBefore = layoutState.order.join('\u0000');
  ensureOrder(visible);
  applyOrder();
  // 顺序按开启时间维护（关闭即出表、重开追加到最右），变化时落盘
  if (orderBefore !== layoutState.order.join('\u0000')) persistLayout();

  Object.keys(tileEls).forEach((k) => { tileEls[k].style.width = windowWidth(k) + 'px'; });
  broadcastLayout();
  syncNativeCover();
}

export function scrollTileIntoView(key: string): void {
  const tile = tileEls[key];
  if (!tile || !stripEl) return;
  const left = tile.offsetLeft;
  const right = left + tile.offsetWidth;
  if (left < stripEl.scrollLeft) stripEl.scrollLeft = left - 8;
  else if (right > stripEl.scrollLeft + stripEl.clientWidth) {
    stripEl.scrollLeft = right - stripEl.clientWidth + 8;
  }
}

export function teardownTiles(): void {
  if (stripEl) {
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
    notifyUnmount(stripEl);
    stripEl.remove();
  }
  stripEl = null;
  addEl = null;
  Object.keys(tileEls).forEach((k) => delete tileEls[k]);
  Object.keys(tileFrames).forEach((k) => delete tileFrames[k]);
  delete frames['panel'];
  setShiftMode(false);
}
