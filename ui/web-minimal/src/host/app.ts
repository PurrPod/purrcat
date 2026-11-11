// 宿主入口 boot 与 Electron 窗口控制
import { broadcastAll, syncNativeCover } from './bus.js';
import { openUrlInBrowserPanel } from './links.js';
import { applyManifestState } from './manifest.js';
import { buildSlotIndex, mountAll } from './mount.js';
import { applyPanelContainerCfg, closePanelMenus, loadPanelShell } from './panel.js';
import { applyPersistedHidden, applyRailOpacity, applySlotHidden, bindRailToggle, buildRail } from './rail.js';
import { broadcastSessions, updateEmpty } from './sessions.js';
import { closeSettingsMenus } from './settings-tabs.js';
import { HOST, groupState } from './state.js';

  // ---- Electron 窗口控制 ----
  export function wireWindowControls() {
    const pc = HOST.purrcat;
    if (!pc) return;
    HOST.document.body.classList.add('electron');
    const byId = (id: string) => HOST.document.getElementById(id);
    // 上一步已判空的元素在同一同步流程内不会消失；win* 方法由 preload 必然注入
    if (byId('winMinimize')) byId('winMinimize')!.addEventListener('click', () => pc.winMinimize!());
    if (byId('winMaximize')) byId('winMaximize')!.addEventListener('click', () => pc.winToggleMaximize!());
    if (byId('winClose')) byId('winClose')!.addEventListener('click', () => pc.winClose!());
  }

  // ---- 入口 ----
  export async function boot() {
    wireWindowControls();
    // 弹出菜单（设置卡片 ▾ / 面板抽屉 ☰）都挂在 body 上：点界面空白处统一收起。
    // 触发按钮自身的 click 已 stopPropagation，因此不会误关刚打开的菜单。
    HOST.document.addEventListener('click', function () { closeSettingsMenus(); closePanelMenus(); });
    let manifest;
    try {
      manifest = await (await fetch('/api/webmin/manifest')).json();
    } catch (err) {
      HOST.document.body.innerHTML =
        '<div style="padding:24px;font-family:system-ui;color:#8b96a3">极简模式无法加载：后端未在线（/api/webmin/manifest 不可用）。请先启动后端。</div>';
      return;
    }
    applyManifestState(manifest);
    await loadPanelShell();   // 取「内置容器」插件的外壳（样式注入 + 结构模板），必须在 mountAll 前
    applyRailOpacity();
    buildSlotIndex();
    mountAll();
    bindRailToggle();
    buildRail();
    applyPanelContainerCfg();
    // 应用持久化的插件隐藏状态（需在挂载后重设，避免被 iframe 覆盖样式）
    applyPersistedHidden();

    // 原生浏览器 Tab 事件（标题/导航/被拦截）转发给全部插件帧，由持有原生视图的插件消费
    if (HOST.purrcat && HOST.purrcat.onTabEvent) {
      HOST.purrcat.onTabEvent(function (evt) { broadcastAll('browser.tabEvent', evt); });
    }
    // 网页链接路由：聊天历史里的 target=_blank / window.open 被主进程拦下后回传（与完整
    // 模式同一链路），极简模式转交内置浏览器面板打开，而不是弹原生窗口或跳走 iframe
    if (HOST.purrcat && HOST.purrcat.onOpenUrl) {
      HOST.purrcat.onOpenUrl(function (url) { openUrlInBrowserPanel(url); });
    }
    // 原生视图遮挡状态：设置中心 / 模态弹窗 / 下拉菜单出现时通知插件隐藏原生视图。
    // 在各开关点显式调用 syncNativeCover()（见 setSettingsOpen/applySlotHidden/菜单开合），
    // 不用 MutationObserver：浮窗拖拽会高频改内联样式，观察 style 会造成 getComputedStyle 抖动。
    syncNativeCover();

    try {
      const list = await (await fetch('/api/sessions')).json();
      if (Array.isArray(list) && list.length) {
        groupState.sessions = list;
        groupState.activeSessionId = list[0].id || '';
        // 修复：已加载完成的插件此刻才拿到 activeSessionId，必须补一次广播，
        // 否则聊天历史等插件会一直停在空态，直到用户手动点一次别的会话
        broadcastSessions('session.switched', { session_id: groupState.activeSessionId });
      }
    } catch (_) { /* 无会话时保持空 */ }
    updateEmpty();
  }
