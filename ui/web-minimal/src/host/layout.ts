// 布局模式（容器式 / 平铺式）与平铺各行窗口顺序、宽度
import { HOST } from './state.js';
import { saveWebminConfig } from './utils.js';

export type LayoutMode = 'container' | 'tile';
// 会话位固定（pin）方向：空串表示不固定，随窗口条滚动
export type PinSide = '' | 'left' | 'right';

// 一行（工作区）：独立维护本行打开的窗口顺序与宽度
export interface LayoutRow {
  order: string[];
  widths: Record<string, number>;
}

export interface LayoutState {
  mode: LayoutMode;
  rows: LayoutRow[];
  activeRow: number;
  pin: PinSide;
  pinWidth: number;
}

// 窗口键：列表位 / 会话位 / 面板插件各用一个稳定键；面板窗口按行各自登记
export const LAYOUT_KEY_SIDEBAR = 'slot:sidebar';
export const LAYOUT_KEY_SESSION = 'slot:session';
export const TILE_MIN_W = 260;
export const TILE_MAX_W = 4000;
export const TILE_ADD_W = 132;
// 固定会话位的默认宽度与固定窗口之间的间隔
export const TILE_PIN_DEFAULT_W = 420;
export const TILE_PIN_GAP = 8;

export function createRow(): LayoutRow { return { order: [], widths: {} }; }

export const layoutState: LayoutState = {
  mode: 'container',
  rows: [createRow()],
  activeRow: 0,
  pin: '',
  pinWidth: TILE_PIN_DEFAULT_W,
};

export function panelWindowKey(id: string): string { return 'panel:' + id; }
export function panelIdFromKey(key: string): string { return key.slice('panel:'.length); }
export function isPanelKey(key: string): boolean { return key.indexOf('panel:') === 0; }

export function tileMode(): boolean { return layoutState.mode === 'tile'; }

export function activeRowIndex(): number {
  const n = layoutState.rows.length;
  if (!n) return 0;
  const i = Math.floor(Number(layoutState.activeRow));
  if (!isFinite(i)) return 0;
  return Math.max(0, Math.min(n - 1, i));
}

export function activeRow(): LayoutRow {
  const row = layoutState.rows[activeRowIndex()];
  if (row) return row;
  const created = createRow();
  layoutState.rows[0] = created;
  return created;
}

// 某窗口键当前归属的行（未登记返回 -1）
export function rowIndexOfKey(key: string): number {
  return layoutState.rows.findIndex((row) => row.order.indexOf(key) >= 0);
}

export function addKeyToRow(row: LayoutRow, key: string): void {
  if (row.order.indexOf(key) < 0) row.order.push(key);
}

export function removeKeyFromRow(row: LayoutRow, key: string): boolean {
  const i = row.order.indexOf(key);
  if (i < 0) return false;
  row.order.splice(i, 1);
  return true;
}

export function defaultWindowWidth(key: string): number {
  if (key === LAYOUT_KEY_SIDEBAR) return 264;
  if (key === LAYOUT_KEY_SESSION) return 420;
  return 480;
}

export function windowWidthIn(row: LayoutRow, key: string): number {
  const raw = Number(row.widths[key]);
  if (!isFinite(raw) || raw < TILE_MIN_W) return defaultWindowWidth(key);
  return Math.min(TILE_MAX_W, Math.round(raw));
}

export function setWindowWidthIn(row: LayoutRow, key: string, width: number): void {
  if (!isFinite(width)) return;
  row.widths[key] = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(width)));
}

function parseOrder(raw: unknown): string[] {
  const list = Array.isArray(raw) ? raw : [];
  const order: string[] = [];
  list.forEach((item) => {
    if (typeof item !== 'string') return;
    const key = item.trim();
    if (key && order.indexOf(key) < 0) order.push(key);
  });
  return order;
}

function parseWidths(raw: unknown): Record<string, number> {
  const data = (raw && typeof raw === 'object') ? raw as Record<string, unknown> : {};
  const widths: Record<string, number> = {};
  Object.keys(data).forEach((k) => {
    const w = Number(data[k]);
    if (k && isFinite(w)) widths[k] = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(w)));
  });
  return widths;
}

// manifest → 内存态：非法值一律回落默认（旧配置没有 layout 分节时保持容器式）
export function applyLayoutFromManifest(raw: unknown): void {
  const data = (raw && typeof raw === 'object') ? raw as Record<string, unknown> : {};
  layoutState.mode = data.mode === 'tile' ? 'tile' : 'container';
  const rows: LayoutRow[] = [];
  const rawRows = Array.isArray(data.rows) ? data.rows : [];
  rawRows.forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const r = item as Record<string, unknown>;
    rows.push({ order: parseOrder(r.order), widths: parseWidths(r.widths) });
  });
  // 兼容旧版平铺配置（顶层 order/widths）：迁入第一行
  if (!rows.length) rows.push({ order: parseOrder(data.order), widths: parseWidths(data.widths) });
  // 尽量沿用已有行对象：重载 manifest 时行视图（含固定位锚点与 iframe）不能被重建
  const prev = layoutState.rows;
  layoutState.rows = rows.map((row, i) => {
    const cur = prev[i];
    if (!cur) return row;
    cur.order = row.order;
    cur.widths = row.widths;
    return cur;
  });
  if (!layoutState.rows.length) layoutState.rows.push(createRow());
  const rawActive = Math.floor(Number(data.activeRow));
  layoutState.activeRow = isFinite(rawActive)
    ? Math.max(0, Math.min(layoutState.rows.length - 1, rawActive))
    : 0;
  layoutState.pin = data.pin === 'left' || data.pin === 'right' ? data.pin : '';
  const rawPinW = Number(data.pinWidth);
  layoutState.pinWidth = isFinite(rawPinW)
    ? Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(rawPinW)))
    : TILE_PIN_DEFAULT_W;
  applyLayoutClass();
}

// 固定宽度读取（夹紧）与写入：固定窗口的宽度独立于行内宽度持久化
export function pinWidthValue(): number {
  const raw = Number(layoutState.pinWidth);
  if (!isFinite(raw)) return TILE_PIN_DEFAULT_W;
  return Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(raw)));
}

export function setPinWidth(width: number): void {
  if (!isFinite(width)) return;
  layoutState.pinWidth = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(width)));
}

export function applyLayoutClass(): void {
  const tile = tileMode();
  HOST.document.body.classList.toggle('layout-tile', tile);
  if (!tile) HOST.document.body.classList.remove('wm-shift-mode');
}

// 顺序表 = 开启时间顺序：从左到右依次是最早开启的窗口。
// 关闭的窗口先从表中移除，重新打开时追加到最右端（视为新的开启时间）；
// 拖拽排序仍可临时调整，但只重排当前开启集合内的相对位置。
export function ensureOrderInRow(row: LayoutRow, visibleKeys: string[]): string[] {
  const visible = new Set(visibleKeys);
  const order = row.order.filter((k) => typeof k === 'string' && !!k && visible.has(k));
  visibleKeys.forEach((key) => {
    if (order.indexOf(key) < 0) order.push(key);
  });
  row.order = order;
  return order;
}

// 拖拽排序：保留已关闭窗口在顺序表中的位置，只重排当前可见窗口
export function reorderInRow(row: LayoutRow, visibleOrder: string[]): void {
  const visible = new Set(visibleOrder);
  const next: string[] = [];
  let i = 0;
  row.order.forEach((k) => {
    if (visible.has(k)) {
      if (i < visibleOrder.length) next.push(visibleOrder[i++]);
    } else {
      next.push(k);
    }
  });
  while (i < visibleOrder.length) next.push(visibleOrder[i++]);
  row.order = next;
}

export function persistLayout(): Promise<void> {
  return saveWebminConfig({ layout: layoutState }).catch(() => {});
}

export function setLayoutMode(mode: LayoutMode): void {
  if (layoutState.mode === mode) return;
  layoutState.mode = mode;
  applyLayoutClass();
  remountLayout();
  persistLayout();
}

// 由 mount.ts 注入（避免 init 期循环依赖：只在用户切换模式时调用）
let remountLayout: () => void = () => {};

export function bindRemountLayout(fn: () => void): void {
  remountLayout = fn;
}
