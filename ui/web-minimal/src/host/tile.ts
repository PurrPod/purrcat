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

// Shift 按下才允许管理窗口；此时每个窗口盖一层透明接收层，避免事件落进 iframe
export function setShiftMode(on: boolean): void {
  const active = on && tileMode();
  HOST.document.body.classList.toggle('wm-shift-mode', active);
  if (!active && !managing) {
    Object.keys(tileEls).forEach((k) => {
      tileEls[k].classList.remove('dragging', 'removing');
      tileEls[k].style.transform = '';
    });
  }
}

HOST.addEventListener('keydown', (ev) => { if (ev.key === 'Shift') setShiftMode(true); });
HOST.addEventListener('keyup', (ev) => { if (ev.key === 'Shift') setShiftMode(false); });
HOST.addEventListener('blur', () => {
  // 窗口整体失焦：取消未完成的拖拽，避免接收层与 dragging 样式残留
  HOST.document.querySelectorAll('.wm-drag-layer').forEach((el) => el.remove());
  managing = false;
  setShiftMode(false);
  Object.keys(tileEls).forEach((k) => {
    tileEls[k].classList.remove('dragging', 'removing');
    tileEls[k].style.transform = '';
  });
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

// Shift + 拖拽：窗口跟手（transform 位移）；横向移动换位；向下拖过窗口高度一半标记删除，松开时关闭
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
    let offsetX = 0;   // 当前视觉位移，窗口始终跟着指针走
    managing = true;
    tile.classList.add('dragging');
    // 全屏接收层：拖出源窗口后指针仍归宿主（否则事件落进其它 iframe 会丢失）
    const layer = HOST.document.createElement('div');
    layer.className = 'wm-drag-layer';
    HOST.document.body.appendChild(layer);
    const setTransform = () => { tile.style.transform = 'translate(' + Math.round(offsetX) + 'px, 0px)'; };
    const move = (e2: PointerEvent) => {
      offsetX += e2.clientX - lastX;
      lastX = e2.clientX;
      const dy = e2.clientY - startY;
      const willRemove = dy >= removeAt;
      if (willRemove !== removing) {
        removing = willRemove;
        tile.classList.toggle('removing', removing);
      }
      if (removing) {
        // 待删除：跟随幅度收缩并轻微下沉，给出「正在拖走」的手感
        tile.style.transform = 'translate(' + Math.round(offsetX * 0.15) + 'px, '
          + Math.round(Math.min(dy - removeAt, 40)) + 'px)';
        return;
      }
      setTransform();
      if (strip) {
        // 拖到窗口条左右边缘时自动横向滚动，便于把窗口拖到视口外
        const sr = strip.getBoundingClientRect();
        if (e2.clientX < sr.left + 56) strip.scrollLeft -= 20;
        else if (e2.clientX > sr.right - 56) strip.scrollLeft += 20;
      }
      // 以各窗口中心线判定插入位置，指针越过中心即换位
      const keys = sortedVisibleKeys();
      const from = keys.indexOf(key);
      if (from < 0) return;
      let target = keys.length;
      for (let i = 0; i < keys.length; i++) {
        const other = keys[i];
        if (other === key) continue;
        const r = tileEls[other].getBoundingClientRect();
        if (e2.clientX < r.left + r.width / 2) { target = i; break; }
      }
      if (target > from) target -= 1;   // 移除自身后目标索引左移
      if (target === from) return;      // 位置未变：不重排，避免抖动
      const next = keys.slice();
      next.splice(from, 1);
      next.splice(Math.max(0, Math.min(next.length, target)), 0, key);
      const before = tile.getBoundingClientRect().left;
      reorderWindows(next);
      applyOrder();
      // 换位后窗口的自然位置变了，抵消这段位移，让窗口继续停在指针下
      offsetX -= tile.getBoundingClientRect().left - before;
      setTransform();
      broadcastLayout();
    };
    const finish = (commit: boolean) => {
      if (done) return;
      done = true;
      managing = false;
      layer.removeEventListener('pointermove', move);
      layer.removeEventListener('pointerup', up);
      layer.removeEventListener('pointercancel', cancel);
      try { layer.releasePointerCapture(ev.pointerId); } catch (_) {}
      layer.remove();
      tile.classList.remove('dragging', 'removing');
      tile.style.transform = '';   // 落位：由 CSS 过渡滑回自然位置
      if (commit) {
        if (removing) closeTileByKey(key);
        else persistLayout();
      }
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

function syncFixedTile(strip: HTMLElement, key: string, slot: string): void {
  let tile = tileEls[key];
  if (!tile) {
    tile = makeTile(key);
    strip.appendChild(tile);
    tileEls[key] = tile;
  }
  moveAnchorInto(tileBody(tile), slot);
  tile.style.display = pluginVisibleInSlot(slot) ? '' : 'none';
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

  syncFixedTile(strip, LAYOUT_KEY_SIDEBAR, 'sidebar');
  syncFixedTile(strip, LAYOUT_KEY_SESSION, 'session');

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

  const visible = [LAYOUT_KEY_SIDEBAR]
    .concat(validPanels.map((p) => panelWindowKey(p.id)))
    .concat([LAYOUT_KEY_SESSION]);
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
