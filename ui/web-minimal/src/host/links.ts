// 网页链接路由到内置浏览器面板
import { broadcast } from './bus.js';
import { tileMode } from './layout.js';
import { openPanelTab, panelState, thirdPartyContainerPlugin } from './panel.js';
import { HOST, frames, groupState } from './state.js';
import type { PluginDescriptor, PluginFrame } from './types.js';

// panel.ts 的 panelState 尚未标注类型（被推断为 null），这里按其在 panel.ts 中的真实结构
// 做模块内类型收窄：面板插件描述（p）在归一化后必然带 slot，帧表来自 mountFrame
interface PanelPluginRef extends PluginDescriptor {
  slot: string;
}
interface PanelEntry {
  p: PanelPluginRef;
  [key: string]: unknown;
}
interface PanelStateView {
  plugins: PanelEntry[];
  activeId?: string;
  frames?: Record<string, PluginFrame | undefined>;
  [key: string]: unknown;
}

export let pendingBrowserUrl: string | null = null;   // 待打开的内置浏览器链接（由动作分发/链接路由写入）

  // ---- 网页链接路由 ----
  // 聊天历史等插件里的网页链接（target=_blank / window.open）由主进程
  // setWindowOpenHandler 拦下，经 purrcat:open-url 回传到宿主，这里统一交给
  // 「声明了 openUrl 能力的 panel 插件」（内置浏览器）打开，与完整模式同一规则。
  // 宿主不硬编码插件 id：能力由插件在自己的 plugin.json 里声明。
  export function browserPanel(): PanelEntry | null {
    const st = panelState as unknown as PanelStateView | null;
    if (st) return st.plugins.find((x) => (x.p || {}).openUrl) || null;
    // 平铺模式没有容器 state：直接从插件表里找声明了 openUrl 能力的 panel 插件
    if (!tileMode()) return null;
    const p = groupState.plugins.find((x) => (x.slotDef || {}).type === 'panel' && (x as any).openUrl);
    return p ? { p: p as PanelPluginRef } : null;
  }
  export function deliverPendingBrowserUrl() {
    if (!pendingBrowserUrl) return;
    const hit = browserPanel();
    if (!hit) return;
    const st = panelState as unknown as PanelStateView | null;
    const inTile = !st && tileMode();
    if (!inTile && (!st || st.activeId !== hit.p.id)) return;
    const fr = inTile
      ? (frames['panel'] || []).find((f) => f.pluginId === hit.p.id)
      : (st && st.frames && st.frames[hit.p.id]);
    if (!fr || !fr.loaded) return;   // 浏览器帧未加载完：等其 load 回调再投
    const url = pendingBrowserUrl;
    pendingBrowserUrl = null;
    broadcast(inTile ? 'panel' : hit.p.slot, 'browser.openUrl', { url: url });
  }
  export function openUrlInBrowserPanel(url: string) {
    const u = String(url || '').trim();
    // purrcat:// 是本应用自造的虚拟协议，只有后端 envelope.parse_uri 能解析成真实文件；
    // 原样交给 Chromium/系统会被委托给操作系统外壳，Windows 便弹「找不到能打开此链接的应用」。
    // 按既有约定（完整模式 TaskPage / builtin-task）翻译成后端产物端点，再进内置浏览器打开。
    if (/^purrcat:\/\//i.test(u)) {
      const tid = (/^purrcat:\/\/task\/([^/]+)\/node\//i.exec(u) || [])[1];
      const art = '/api/tasks/' + encodeURIComponent(tid || '_unknown') +
        '/artifact?uri=' + encodeURIComponent(u);
      return openUrlInBrowserPanel(new URL(art, location.origin).href);
    }
    const pc = HOST.purrcat;
    const hit = browserPanel();
    // 中栏容器由插件入驻时宿主内置容器已让位（panelState 为空），此时把地址广播给
    // 该容器插件，由它转交给自己的内置浏览器子插件——与内置容器同样在应用内打开。
    // 平铺模式没有容器实体，第三方容器插件不参与链接转交
    const hostCont = (hit || tileMode()) ? null : thirdPartyContainerPlugin();
    // 非网页（mailto:/tel:/file: 等）或面板里没有可用内置浏览器 → 退回系统处理
    if (!/^https?:\/\//i.test(u) || (!hit && !hostCont) || !pc || !pc.browserNewTab) {
      if (pc && pc.openExternal && u) pc.openExternal(u);
      return { status: 'external' };
    }
    if (hostCont) {
      broadcast('panel-container', 'browser.openUrl', { url: u });
      return { status: 'ok' };
    }
    // 浏览器面板未开为标签页则先打开，再激活并投递地址（已打开则仅聚焦）
    // 前置分支已保证：走到这里时要么 hit 存在，要么 hostCont 已在上方 return，故 hit 必不为空
    openPanelTab(hit!.p.id);
    pendingBrowserUrl = u;
    deliverPendingBrowserUrl();
    return { status: 'ok' };
  }

