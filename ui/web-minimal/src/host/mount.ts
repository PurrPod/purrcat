// iframe 实例挂载、槽集合建立与全量重挂载
import { PANEL_CONTAINER_ID } from './areas.js';
import { broadcastAll, nativeCoverActive } from './bus.js';
import { applyConfigTo } from './config-apply.js';
import { applyFloatSize, applyModalSize, attachFloatHandles, centerFloat } from './float.js';
import { bindRemountLayout, layoutState, tileMode } from './layout.js';
import { deliverPendingBrowserUrl } from './links.js';
import { applyManifestState } from './manifest.js';
import { applyPanelContainerCfg, mountPanels, panelContainerVisible, reconcilePanels } from './panel.js';
import { applyPersistedHidden, applySlotHidden, buildRail, railHidden } from './rail.js';
import { setShiftMode, syncTiles, teardownTiles } from './tile.js';
import { HOST, activeBySlot, configByPlugin, frameByPluginId, frames, groupState, pluginBySlot, slotByPluginId, slotMap } from './state.js';
import type { PluginDescriptor, PluginFrame } from './types.js';

  // ---- 渲染：把某插件实例装进对应容器内的 iframe ----
  // 卸载通知：iframe 被移除前给插件最后一次收尾机会（如关掉自己开的浏览器 Tab、
  // 把原生视图移出屏幕）。postMessage 已入队，即使随后移除 iframe 仍会投递。
  // 插件后端随 iframe 生命周期存活：挂载时 start、卸载时 stop。
  // 改完 server/server.js 只需关掉再打开标签页，后端就会重新拉起（不必重启 PurrCat）。
  export function syncPluginBackend(id: string, action: string): void {
    if (!id) return;
    try {
      fetch('/api/webmin/plugin-backend/' + encodeURIComponent(id) + '/' + action, {
        method: 'POST',
        cache: 'no-store',
      }).catch(function () { /* 后端启动失败不影响 UI */ });
    } catch (_) { /* noop */ }
  }
  export function notifyUnmount(rootEl: Element | null): void {
    if (!rootEl || !rootEl.querySelectorAll) return;
    rootEl.querySelectorAll('iframe').forEach(function (f) {
      try {
        if (f.contentWindow) f.contentWindow.postMessage({ type: 'event', event: 'host.unmount', data: {} }, '*');
      } catch (_) { /* noop */ }
      if (f.dataset && f.dataset.backend === '1' && f.dataset.pid) {
        syncPluginBackend(f.dataset.pid, 'stop');
      }
    });
  }
  export function mountFrame(el: HTMLElement, p: PluginDescriptor): PluginFrame | null {
    notifyUnmount(el);
    el.querySelectorAll('iframe').forEach((f) => f.remove());
    el.querySelectorAll('.wm-fgrab, .wm-fresize').forEach((h) => h.remove());
    if (!p || !p.entry) return null;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('tabindex', '-1');
    iframe.src = `/api/webmin/plugin/${encodeURIComponent(p.id)}/${p.entry.split('/').map(encodeURIComponent).join('/')}`;
    iframe.title = p.name || p.id;
    iframe.dataset.pid = p.id;
    if (p.backend) {
      iframe.dataset.backend = '1';
      syncPluginBackend(p.id, 'start');
    }
    el.appendChild(iframe);
    // 焦点在插件 iframe 内时宿主收不到 Shift 按键：把 Shift 状态桥接回宿主，
    // 平铺模式据此显示窗口管理接收层。每次导航都是新的 contentWindow，重复挂载无副作用。
    iframe.addEventListener('load', function bridgeShift() {
      try {
        const cw = iframe.contentWindow;
        if (!cw) return;
        cw.addEventListener('keydown', (ev: KeyboardEvent) => { if (ev.key === 'Shift') setShiftMode(true); }, true);
        cw.addEventListener('keyup', (ev: KeyboardEvent) => { if (ev.key === 'Shift') setShiftMode(false); }, true);
      } catch (_) { /* 跨域插件无法桥接，Shift 仅在宿主聚焦时生效 */ }
    });
    // 注意：configByPlugin 的唯一初始化点是 applyManifestState（覆盖全部插件），
    // 这里不再覆写，避免用 boot 时的 manifest 旧值冲掉运行中的未保存编辑
    slotByPluginId[p.id] = p.slot as string;   // slot 已由后端归一化，entry 存在的插件必然带 slot
    frameByPluginId[p.id] = iframe;
    const rec: PluginFrame = { iframe: iframe, pluginId: p.id, el: el, loaded: false };
    iframe.addEventListener('load', function onLoad() {
      rec.loaded = true;
      applyConfigTo(p.id);
      // 启动竞态修复：activeSessionId 由 boot 里的异步请求确定，可能晚于 iframe 加载；
      // 只靠 boot 时的一次广播会让晚加载的插件错过 → 给刚加载的插件补推当前会话
      if (groupState.activeSessionId) {
        try {
          const cw = iframe.contentWindow;   // 刚加载时可能尚未就绪；原逻辑在 try 中抛错被静默忽略，故显式判空
          if (cw) {
            cw.postMessage(
              { type: 'event', event: 'session.switched', data: { session_id: groupState.activeSessionId } },
              '*'
            );
          }
        } catch (_) { /* noop */ }
      }
      // 同步补推当前分支视图：晚加载的输入框据此判定是否只读
      try {
        const cw = iframe.contentWindow;   // 同上：可能为空，判空后跳过与原静默忽略等价
        if (cw) {
          cw.postMessage(
            { type: 'event', event: 'branch.switched', data: { branch_id: groupState.activeBranchId || 'main' } },
            '*'
          );
        }
      } catch (_) { /* noop */ }
      // 启动竞态修复：插件可能在「设置中心/模态弹窗已打开」之后才挂载，
      // 此时早先的 host.nativeCover 广播已经发过，插件会误以为未被遮挡而展示原生视图（覆盖设置）。
      // 给刚加载的插件补推一次当前遮挡状态。
      try {
        const cw = iframe.contentWindow;   // 同上：可能为空，判空后跳过与原静默忽略等价
        if (cw) {
          cw.postMessage(
            { type: 'event', event: 'host.nativeCover', data: { covered: nativeCoverActive() } },
            '*'
          );
        }
      } catch (_) { /* noop */ }
      deliverPendingBrowserUrl();   // 帧刚就绪：补投挂起的网页链接（若有）
      iframe.removeEventListener('load', onLoad);
    });
    return rec;
  }

  // ---- 依据 manifest 的 slot 声明建立槽集合（去硬编码） ----
  export function buildSlotIndex() {
    // 清理已挂载的动态实例浮层（保留 html 里的锚定容器）
    Object.keys(frames).forEach((k) => {
      (frames[k] || []).forEach((f) => { if (f.el && f.el.parentNode && !f.el.hasAttribute('data-layer')) { notifyUnmount(f.el); f.el.remove(); } });
    });
    Object.keys(slotMap).forEach((k) => delete slotMap[k]);
    Object.keys(pluginBySlot).forEach((k) => delete pluginBySlot[k]);
    Object.keys(slotByPluginId).forEach((k) => delete slotByPluginId[k]);
    Object.keys(frameByPluginId).forEach((k) => delete frameByPluginId[k]);
    Object.keys(frames).forEach((k) => delete frames[k]);   // 原地清空：frames 为跨模块共享的 let 绑定
    groupState.plugins.forEach((p) => {
      const s = p.slot;
      if (!s) return;
      (slotMap[s] = slotMap[s] || []).push(p);
      slotByPluginId[p.id] = s;   // 全插件登记（含未挂载者），供显隐换算反查
    });
  }

  // 重算某 fixed 区域当前应显示的插件：在「未被关闭」的插件里优先取用户上次选中的，
  // 否则取声明顺序第一个；全部被关闭时该区域不占位（隐藏锚点、让出宽度）。
  // 同区域天然互斥——任意时刻最多只有一个插件被挂载。
  export function refreshFixedSlot(slot: string): void {
    // 平铺模式没有面板容器：该区域整体让位，面板插件由 tile.ts 各自成窗口
    if (slot === 'panel-container' && tileMode()) {
      if (frames[slot]) {
        frames[slot].forEach((f) => { if (f.iframe && f.iframe.parentNode) f.iframe.parentNode.removeChild(f.iframe); });
        frames[slot] = [];
      }
      delete pluginBySlot[slot];
      const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`) as HTMLElement | null;
      if (anchor) { anchor.innerHTML = ''; anchor.style.display = 'none'; }
      return;
    }
    const list = slotMap[slot] || [];
    const visible = list.filter((x) => !railHidden(x.id));
    const chosen = visible.find((x) => x.id === activeBySlot[slot]) || visible[0] || null;
    if (frames[slot]) {
      frames[slot].forEach((f) => { if (f.iframe && f.iframe.parentNode) f.iframe.parentNode.removeChild(f.iframe); });
      frames[slot] = [];
    }
    if (!chosen) {
      delete pluginBySlot[slot];
      applySlotHidden(slot, true);
      if (slot === 'panel-container') syncPanelContainer();
      return;
    }
    pluginBySlot[slot] = chosen;
    // 内置容器（builtin-panel）由宿主按插件提供的外壳原生渲染（.wm-ppanel），不挂 iframe
    if (chosen.id === PANEL_CONTAINER_ID) {
      const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`) as HTMLElement | null;
      if (anchor) anchor.innerHTML = '';
      syncPanelContainer();
      return;
    }
    const anchor = HOST.document.querySelector(`[data-slot="${slot}"]`) as HTMLElement | null;
    if (anchor) {
      anchor.innerHTML = '';
      const fr = mountFrame(anchor, chosen);
      if (fr) frames[slot] = [fr];
    }
    // 有插件生效：显示锚点（mountFrame 只负责塞 iframe，不负责显隐）
    applySlotHidden(slot, false);
    if (slot === 'panel-container') syncPanelContainer();
  }

  // 中栏容器的唯一同步点：宿主内置容器与入驻插件同区域互斥（谁生效谁占位），
  // 并据此重算 has-panels / 分隔条 / 中栏宽度，最后由「面板容器」总开关统辖显隐。
  // 开关入驻插件（走 refreshFixedSlot）后必须调用，否则会出现「内置容器与插件容器同时
  // 显示」或「容器不占位、与会话历史重叠悬空」。
  export function syncPanelContainer() {
    mountPanels();                                      // 有入驻插件则内置容器让位（移除 .wm-ppanel），否则重建
    reconcilePanels();                                  // has-panels / .wm-pbar / --wm-panel-w
    applySlotHidden('panel', !panelContainerVisible());  // 最后统一显隐：两候选谁生效都占位
  }

  // ---- 动态挂载全部类型窗口（type：fixed 锚定单例 / panel 分栏抽屉 / float 自由浮窗多开 / modal 模态弹窗） ----
  export function mountAll() {
    // 1) fixed：按 area 挂到 html 锚定容器；优先挂载用户上次选中的插件，
    //    否则取未被关闭插件中声明顺序第一个；该区域全部插件都被关闭则不占位。
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'fixed') return;
      refreshFixedSlot(sid);
    });
    // 2) panel：无面板插件则不占位；有则建 .wm-ppanel（右上角抽屉切换）
    mountPanels();
    // 3) pet（area=pet）：自由浮窗，每个插件一个独立 .wm-float，可拖拽可缩放
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'float') return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      list.forEach((p, i) => {
        const el = HOST.document.createElement('div');
        el.className = 'wm-float wm-mount';
        el.dataset.fslot = sid;
        el.dataset.finst = String(i);
        el.style.top = 46 + i * 26 + 'px';
        el.style.left = `calc(100% - ${300 + i * 26}px - 16px)`;
        // 插件可声明默认尺寸（slot.size={w,h}：数字=px，字符串=CSS 长度）
        applyFloatSize(el, def.size, i);
        HOST.document.body.appendChild(el);
        // 声明 center 的弹窗初始居中（居中区域避开左侧白条，组件窗口绝不伸入白条）
        if (def.center) centerFloat(el);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(el, p);
        if (fr) frames[sid].push(fr);
        attachFloatHandles(el);
      });
    });
    // 4) modal（area=popup）：模态弹窗，遮罩铺满主区（白条与设置中心在其之上），
    //    固定居中、不可拖拽；尺寸用 CSS 长度随窗口自适应，无需 resize 重排
    Object.keys(slotMap).forEach((sid) => {
      const list = slotMap[sid];
      const def = (list[0].slotDef || {});
      if (def.type !== 'modal') return;
      pluginBySlot[sid] = list[0];
      frames[sid] = [];
      list.forEach((p) => {
        const wrap = HOST.document.createElement('div');
        wrap.className = 'wm-modal-wrap wm-mount';
        wrap.dataset.mslot = sid;
        const box = HOST.document.createElement('div');
        box.className = 'wm-modal';
        applyModalSize(box, def.size);
        wrap.appendChild(box);
        HOST.document.body.appendChild(wrap);
        slotByPluginId[p.id] = sid;
        const fr = mountFrame(box, p);
        // 以整体遮罩为实例单位：显隐/清理/关闭时连遮罩一起处理
        if (fr) { fr.el = wrap; frames[sid].push(fr); }
      });
    });
    reconcilePanels();
    // 平铺模式：把列表位/会话位与面板插件装配成横向窗口条
    if (tileMode()) syncTiles(); else teardownTiles();
  }

  // 切换布局模式后重建界面（允许 iframe 重挂载），并通知插件同步原生视图
  export function remountLayout(): void {
    buildSlotIndex();
    mountAll();
    applyPersistedHidden();
    buildRail();
    applyPanelContainerCfg();
    if (tileMode()) syncTiles(); else teardownTiles();
    broadcastAll('host.layoutChanged', { mode: layoutState.mode });
  }
  bindRemountLayout(remountLayout);

