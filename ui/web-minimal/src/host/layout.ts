// 布局模式（容器式 / 平铺式）与平铺窗口顺序、宽度
import { HOST } from './state.js';

export type LayoutMode = 'container' | 'tile';

export interface LayoutState {
  mode: LayoutMode;
  order: string[];
  widths: Record<string, number>;
}

// 窗口键：列表位 / 会话位 / 面板插件各用一个稳定键，顺序按此持久化
export const LAYOUT_KEY_SIDEBAR = 'slot:sidebar';
export const LAYOUT_KEY_SESSION = 'slot:session';
export const TILE_MIN_W = 260;
export const TILE_MAX_W = 4000;
export const TILE_ADD_W = 132;

export const layoutState: LayoutState = { mode: 'container', order: [], widths: {} };

export function panelWindowKey(id: string): string { return 'panel:' + id; }

export function tileMode(): boolean { return layoutState.mode === 'tile'; }

export function defaultWindowWidth(key: string): number {
  if (key === LAYOUT_KEY_SIDEBAR) return 264;
  if (key === LAYOUT_KEY_SESSION) return 420;
  return 480;
}

export function windowWidth(key: string): number {
  const raw = Number(layoutState.widths[key]);
  if (!isFinite(raw) || raw < TILE_MIN_W) return defaultWindowWidth(key);
  return Math.min(TILE_MAX_W, Math.round(raw));
}

export function setWindowWidth(key: string, width: number): void {
  if (!isFinite(width)) return;
  layoutState.widths[key] = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(width)));
}

// manifest → 内存态：非法值一律回落默认（旧配置没有 layout 分节时保持容器式）
export function applyLayoutFromManifest(raw: unknown): void {
  const data = (raw && typeof raw === 'object') ? raw as Record<string, unknown> : {};
  layoutState.mode = data.mode === 'tile' ? 'tile' : 'container';
  const rawOrder = Array.isArray(data.order) ? data.order : [];
  layoutState.order = rawOrder
    .filter((k): k is string => typeof k === 'string' && !!k.trim())
    .map((k) => k.trim());
  const widths: Record<string, number> = {};
  const rawWidths = (data.widths && typeof data.widths === 'object')
    ? data.widths as Record<string, unknown>
    : {};
  Object.keys(rawWidths).forEach((k) => {
    const w = Number(rawWidths[k]);
    if (k && isFinite(w)) widths[k] = Math.max(TILE_MIN_W, Math.min(TILE_MAX_W, Math.round(w)));
  });
  layoutState.widths = widths;
  applyLayoutClass();
}

export function applyLayoutClass(): void {
  const tile = tileMode();
  HOST.document.body.classList.toggle('layout-tile', tile);
  if (!tile) HOST.document.body.classList.remove('wm-shift-mode');
}

// 顺序表 = 开启时间顺序：从左到右依次是最早开启的窗口。
// 关闭的窗口先从表中移除，重新打开时追加到最右端（视为新的开启时间）；
// 拖拽排序仍可临时调整，但只重排当前开启集合内的相对位置。
export function ensureOrder(visibleKeys: string[]): string[] {
  const visible = new Set(visibleKeys);
  const order = layoutState.order.filter((k) => typeof k === 'string' && !!k && visible.has(k));
  visibleKeys.forEach((key) => {
    if (order.indexOf(key) < 0) order.push(key);
  });
  layoutState.order = order;
  return order;
}

// 拖拽排序：保留已关闭窗口在顺序表中的位置，只重排当前可见窗口
export function reorderWindows(visibleOrder: string[]): void {
  const visible = new Set(visibleOrder);
  const next: string[] = [];
  let i = 0;
  layoutState.order.forEach((k) => {
    if (visible.has(k)) {
      if (i < visibleOrder.length) next.push(visibleOrder[i++]);
    } else {
      next.push(k);
    }
  });
  while (i < visibleOrder.length) next.push(visibleOrder[i++]);
  layoutState.order = next;
}

export function persistLayout(): Promise<void> {
  return fetch('/api/webmin/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ layout: layoutState }),
  })
    .then((res) => { if (!res.ok) throw new Error(String(res.status)); })
    .catch(() => {});
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
