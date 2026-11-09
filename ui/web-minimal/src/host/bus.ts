// 动作入口 callAction 与事件广播（含原生视图遮挡）
import { dispatch } from './actions.js';
import { HOST, frames } from './state.js';
import type { ActionOrigin, PluginFrame } from './types.js';

  // ---- 命令入口 ----
  export async function callAction(
    actionId: string,
    payload: Record<string, any> = {},
    origin?: ActionOrigin,
  ): Promise<unknown> {
    return dispatch(actionId, payload, origin);
  }

  // ---- 广播事件到某 slot ----
  export function broadcast(slot: string, event: string, data?: unknown): void {
    (frames[slot] || []).forEach((f) => {
      if (f.iframe && f.iframe.contentWindow) {
        f.iframe.contentWindow.postMessage({ type: 'event', event, data: data || {} }, '*' as any);
      }
    });
  }

  // ---- 广播事件到全部插件帧（不区分 slot）：宿主级通用状态（如原生视图遮挡）通知 ----
  export function broadcastAll(event: string, data?: unknown): void {
    Object.keys(frames).forEach((k) => { broadcast(k, event, data); });
  }

  // ---- 原生视图遮挡：内置浏览器等原生 WebContentsView 永远绘制在 DOM 之上，
  //      宿主的设置中心 / 模态弹窗 / 各类下拉菜单出现时必须让持有原生视图的插件
  //      暂时隐藏视图。宿主不感知具体插件，只广播一个通用布尔状态由插件自行响应。
  export let _nativeCover: boolean | null = null;
  export function nativeCoverActive(): boolean {
    if (HOST.document.body.classList.contains('settings-open')) return true;
    if (HOST.document.querySelector('.wm-pp_menu')) return true;
    if (HOST.document.querySelector('.settings-card-menu')) return true;
    const modals = HOST.document.querySelectorAll('.wm-modal-wrap');
    for (let i = 0; i < modals.length; i++) {
      if (HOST.getComputedStyle(modals[i]).display !== 'none') return true;
    }
    return false;
  }
  export function syncNativeCover(): void {
    const v = nativeCoverActive();
    if (v === _nativeCover) return;
    _nativeCover = v;
    broadcastAll('host.nativeCover', { covered: v });
  }

  // ---- 监听插件 iframe 消息 ----
  HOST.addEventListener('message', (e) => {
    const msg = e.data;
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'callAction') {
      const id = msg.id;
      // 从消息来源反查调用方所在 slot 及其具体实例，据此界定原语作用对象（如 slot.move / slot.close）
      let srcSlot: string | null = null, srcFrame: PluginFrame | null = null;
      Object.keys(frames).forEach((k) => {
        (frames[k] || []).forEach((f) => {
          if (f.iframe && f.iframe.contentWindow === e.source) { srcSlot = k; srcFrame = f; }
        });
      });
      // forEach 回调内的赋值不参与外层控制流收窄（外层仍按初始值推为 null），这里取回声明类型
      const srcFrameRef = srcFrame as PluginFrame | null;
      const srcPluginId = srcFrameRef ? srcFrameRef.pluginId : null;
      // PluginFrame.iframe 声明为可选，运行期若缺失下游也按空值处理，这里按 ActionOrigin 收窄
      const origin = { slot: srcSlot, pluginId: srcPluginId, inst: srcFrameRef ? srcFrameRef.el : null, iframe: (srcFrameRef ? srcFrameRef.iframe : null) as HTMLIFrameElement | null };
      callAction(msg.actionId, msg.payload, origin)
        .then((data) => { if (e.source) e.source.postMessage({ type: 'callActionResult', id, ok: true, data }, '*' as any); })
        .catch((err) => { if (e.source) e.source.postMessage({ type: 'callActionResult', id, ok: false, error: String(err) }, '*' as any); });
    }
  });

