// 浮窗/模态拖拽与缩放（type=float / modal）
import { applyPanelWidth } from './panel.js';
import { HOST, frames, groupState } from './state.js';
import type { SlotSize } from './types.js';

  // ---- 通用拖拽/缩放（type=float 弹窗：多插件各自独立、宿主只操作容器几何） ----
  // 关键：在手柄上做 pointer capture。否则鼠标快速移出手柄条、落到 iframe 上时，
  // pointermove 事件会被 iframe 吞掉，拖拽随即「失去控制」。
  export function beginFloatGesture(handle: HTMLElement, e: PointerEvent, onMove: (ev: PointerEvent) => void) {
    const pid = e.pointerId;
    try { handle.setPointerCapture(pid); } catch (_) { /* 不支持时退化为仅手柄内有效 */ }
    const move = (ev: PointerEvent) => { if (ev.pointerId === pid) onMove(ev); };
    const end = (ev: PointerEvent) => {
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
  export function startFloatDrag(el: HTMLElement, e: PointerEvent) {
    e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    // 监听器挂在手柄元素上，事件派发过程中 currentTarget 必为该元素（此处断言为 HTMLElement）
    beginFloatGesture(e.currentTarget as HTMLElement, e, (ev) => {
      el.style.right = 'auto';
      el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r0.left + (ev.clientX - sx))) + 'px';
      el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r0.top + (ev.clientY - sy))) + 'px';
    });
  }
  export function startFloatResize(el: HTMLElement, e: PointerEvent) {
    e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY, r0 = el.getBoundingClientRect();
    // 同上：currentTarget 必为挂载监听器的手柄元素
    beginFloatGesture(e.currentTarget as HTMLElement, e, (ev) => {
      el.style.width = Math.max(160, r0.width + (ev.clientX - sx)) + 'px';
      el.style.height = Math.max(160, r0.height + (ev.clientY - sy)) + 'px';
    });
  }
  // float 尺寸：数字按 px，字符串按 CSS 长度（如 "min(1040px, 96vw)" / "86vh"）
  export function applyFloatSize(el: HTMLElement, size: SlotSize | undefined, i?: number) {
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
  export function applyModalSize(el: HTMLElement, size?: SlotSize) {
    if (!size) return;
    if (typeof size.w === 'string' && size.w) el.style.width = size.w;
    else if (Number(size.w) > 0) el.style.width = Number(size.w) + 'px';
    if (typeof size.h === 'string' && size.h) el.style.height = size.h;
    else if (Number(size.h) > 0) el.style.height = Number(size.h) + 'px';
  }
  // 初始居中（须在 appendChild 之后调用，否则拿不到实际尺寸）
  export function centerFloat(el: HTMLElement) {
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
  export function reflowFloats() {
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
  export function attachFloatHandles(el: HTMLElement) {
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

