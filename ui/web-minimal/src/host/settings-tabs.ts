// 设置面板导航与插件总览（抽屉、启停、区域分组）
import { PANEL_CONTAINER_ID } from './areas.js';
import { callAction, syncNativeCover } from './bus.js';
import { cfgState, cfgToolbar, renderConfigSection, settingsPageHead } from './config-center.js';
import { reloadManifest } from './manifest.js';
import { refreshFixedSlot } from './mount.js';
import { closePanelTab, openPanelTab, panelTabs } from './panel.js';
import { buildRail, persistActive, persistRail, railHidden, setPluginHidden } from './rail.js';
import { renderPanelContainerSettings, renderRailAppearance } from './settings-appearance.js';
import { renderPluginCard } from './settings-cards.js';
import { HOST, activeBySlot, configByPlugin, groupState, pluginBySlot, railState, slotMap } from './state.js';
import type { PluginDescriptor } from './types.js';

  // ---- 设置面板：左导航 + 内容区（宿主固有资产，非插件）----
  // 主导航：UI 插件 + 原配置中心逐标签页
  export const CONFIG_NAV = ['plugins', 'model', 'sensor', 'file', 'mcp', 'soul', 'acp', 'deploy'];
  export const CONFIG_LABEL: Record<string, string> = { plugins: 'UI 插件', model: '模型', sensor: '传感器', file: '文件', mcp: 'MCP', soul: '全局人设', acp: 'ACP', deploy: '部署' };
  export let settingsTab = 'plugins';
  export let settingsRenderedTab = '';   // 上一次渲染的标签页（同页重建才恢复滚动位置）
  export let deployPollT: number | null = null;   // 部署页轮询定时器句柄
  // 跨模块只读导入无法赋值：由本模块持有，外部通过 setter 写入
  export function setSettingsTab(v: string) { settingsTab = v; }
  export function setDeployPollT(v: number | null) { deployPollT = v; }

  export function renderSettings() {
    const bodyEl = HOST.document.querySelector('[data-layer="settings"] .settings-body');
    if (!bodyEl) return;
    if (deployPollT) { clearInterval(deployPollT); deployPollT = null; }
    closeSettingsMenus();   // 卡片菜单挂在 body 上，重建后锚点按钮已消失，先收起避免残留
    // 内容区滚动位置：同一标签页内重建（改配置项触发的防抖重建）恢复原地，切标签页则回到顶部。
    // 卡片是 fetch 回来后才插入的，故用一次 MutationObserver 在异步内容落地后再兜底恢复一次。
    const prevMain = bodyEl.querySelector('.settings-main');
    const keepTop = (settingsRenderedTab === settingsTab && prevMain) ? prevMain.scrollTop : 0;
    bodyEl.innerHTML = '';
    // 左导航
    const nav = HOST.document.createElement('div');
    nav.className = 'settings-nav';
    CONFIG_NAV.forEach(function (key) {
      const it = HOST.document.createElement('button');
      it.className = 'settings-nav-item' + (settingsTab === key ? ' active' : '');
      it.textContent = CONFIG_LABEL[key] || key;
      it.addEventListener('click', function () { settingsTab = key; renderSettings(); });
      nav.appendChild(it);
    });
    bodyEl.appendChild(nav);
    // 内容区
    const main = HOST.document.createElement('div');
    main.className = 'settings-main';
    bodyEl.appendChild(main);
    if (settingsTab === 'plugins') renderPluginsTab(main);
    else renderConfigSection(main, settingsTab);
    settingsRenderedTab = settingsTab;
    if (keepTop) {
      main.scrollTop = keepTop;
      const mo = new MutationObserver(function () { main.scrollTop = keepTop; mo.disconnect(); });
      mo.observe(main, { childList: true, subtree: true });
      setTimeout(function () { mo.disconnect(); }, 2000);
    }
  }

  // ---- UI 插件主面板：按「区域」竖排分组（卡片 / JSON 双模式，与配置中心一致）----
  // area 是插件声明的唯一维度；行为（单例 / 容器抽屉 / 浮窗）由宿主按区域内置。
  // 白条/设置面板统一使用的区域名：由宿主固定，插件不再自行决定
  export const AREA_LABEL: Record<string, string> = {
    session: '会话位', 'panel-container': '面板容器', popup: '弹窗类',
    sidebar: '列表位', background: '背景', rail: '左侧白条', panel: '面板', pet: '浮窗类',
    settings: '设置',   // 宿主固有入口，独立归类的伪区域
  };
  // 宿主原生资产（非插件）挂在所属区域内；singleton 标记「同区域同时只能启用一个插件」
  export const UI_GROUPS: Array<{ area: string; singleton?: boolean; host?: (container: HTMLElement) => void }> = [
    { area: 'rail', host: renderRailAppearance },
    { area: 'sidebar', singleton: true },
    { area: 'session', singleton: true },
    { area: 'background', singleton: true },
    { area: 'panel-container', singleton: true, host: renderPanelContainerSettings },
    { area: 'panel' },
    { area: 'pet' },
    { area: 'popup' },
  ];
  export function cfgFor(p: PluginDescriptor): Record<string, any> { return Object.assign({}, configByPlugin[p.id] || {}); }

  export function renderPluginsTab(main: HTMLElement) {
    settingsPageHead(main, 'plugins', function () {
      reloadManifest().then(function () { renderSettings(); });
    });
    cfgToolbar(main, 'plugins', function (m: HTMLElement) { m.innerHTML = ''; renderPluginsTab(m); });
    if ((cfgState.mode['plugins'] || 'cards') === 'json') {
      renderWebminJson(main);
      return;
    }
    UI_GROUPS.forEach(function (grp) { renderPluginGroup(main, grp); });
  }

  // 整份宿主配置的 JSON 编辑（GET/PUT /api/webmin/config，保存后重建界面立即生效）
  export function renderWebminJson(main: HTMLElement) {
    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '极简 UI 宿主配置：plugins=各插件配置 · rail=图标栏状态 · active=单例槽选中项。保存后立即生效并重建界面。';
    main.appendChild(tip);
    const tx = HOST.document.createElement('textarea');
    tx.className = 'settings-json';
    tx.spellcheck = false;
    tx.placeholder = '读取配置…';
    main.appendChild(tx);
    const status = HOST.document.createElement('span');
    status.className = 'p-tag';
    fetch('/api/webmin/config').then(function (r) { return r.json(); }).then(function (cfg) {
      tx.value = JSON.stringify(cfg, null, 2);
      status.textContent = '已加载';
    }).catch(function () { status.textContent = '加载失败'; });
    const bar = HOST.document.createElement('div');
    bar.className = 'settings-actions';
    const save = HOST.document.createElement('button');
    save.className = 'btn cfg-save';
    save.textContent = '保存并应用';
    save.addEventListener('click', function () {
      let obj;
      try { obj = JSON.parse(tx.value); } catch (e) { HOST.alert('JSON 解析失败：' + (e as Error).message); return; }
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) { HOST.alert('顶层必须是 JSON 对象'); return; }
      save.disabled = true;
      status.textContent = '保存中…';
      fetch('/api/webmin/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
        .then(function () { return reloadManifest(); })
        .then(function () {
          status.textContent = '已保存并应用';
          renderSettings();
        })
        .catch(function (e) {
          save.disabled = false;
          status.textContent = '保存失败';
          HOST.alert('保存失败：' + (e && e.message || ''));
        });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }

  // 全局人设：SOUL.md 在线编辑（GET/PUT /api/config/markdown/SOUL，落盘 ~/.purrcat/core/SOUL.md）
  export function renderSoulEditor(main: HTMLElement) {
    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '全局人设 SOUL.md：只有在 AgentLoop / Graph 等流程中显式引用 @SOUL 时，此内容才会注入对应 Agent（是否注入取决于具体实现），并非所有 Agent 自动携带（落盘 ~/.purrcat/core/SOUL.md）。';
    main.appendChild(tip);
    const tx = HOST.document.createElement('textarea');
    tx.className = 'settings-json';
    tx.spellcheck = false;
    tx.placeholder = '读取中…';
    main.appendChild(tx);
    const status = HOST.document.createElement('span');
    status.className = 'p-tag';
    fetch('/api/config/markdown/SOUL').then(function (r) { return r.json(); }).then(function (d) {
      tx.value = (d && d.content) || '';
      status.textContent = '已加载';
    }).catch(function () { status.textContent = '加载失败'; });
    const bar = HOST.document.createElement('div');
    bar.className = 'settings-actions';
    const save = HOST.document.createElement('button');
    save.className = 'btn cfg-save';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      save.disabled = true;
      status.textContent = '保存中…';
      fetch('/api/config/markdown/SOUL', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: tx.value }) })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
        .then(function () { save.disabled = false; status.textContent = '已保存'; })
        .catch(function (e) {
          save.disabled = false;
          status.textContent = '保存失败';
          HOST.alert('保存失败：' + (e && e.message || ''));
        });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }

  export function renderPluginGroup(main: HTMLElement, grp: (typeof UI_GROUPS)[number]) {
    const group = HOST.document.createElement('div');
    group.className = 'settings-group';
    const gt = HOST.document.createElement('div');
    gt.className = 'settings-group-title';
    gt.textContent = AREA_LABEL[grp.area] || grp.area;
    group.appendChild(gt);
    if (grp.host) grp.host(group);   // 宿主原生资产（左侧白条 / 面板容器）
    const list = groupState.plugins.filter(function (p) { return ((p.slotDef || {}).area || '') === grp.area; });
    const multi = grp.singleton && list.length > 1;
    if (multi) {
      const sub = HOST.document.createElement('div');
      sub.className = 'settings-subgroup';
      sub.textContent = '同时只能启用一个插件';
      group.appendChild(sub);
    }
    list.forEach(function (p) { renderPluginCard(group, p, cfgFor(p)); });
    if (!group.querySelector('.cfg-card')) {
      const none = HOST.document.createElement('div');
      none.className = 'p-tag';
      none.textContent = '（暂无插件）';
      group.appendChild(none);
    }
    main.appendChild(group);
  }

  // ---- 插件生效状态与右上角抽屉（删除 / 内置标识；启停走卡片上的打开/关闭按钮）----
  // 按槽类型判定插件是否真实生效：fixed=该槽当前挂载中；panel=容器显示且为抽屉当前选中；float=未隐藏
  export function pluginVisible(p: PluginDescriptor) {
    if (railHidden(p.id)) return false;
    const type = (p.slotDef || {}).type;
    if (type === 'fixed') {
      const cur = pluginBySlot[p.slot || ''];
      return !!cur && cur.id === p.id;
    }
    if (type === 'panel') {
      if (railHidden(PANEL_CONTAINER_ID)) return false;   // 中栏容器被关闭时，其内标签自然不生效
      return (panelTabs as string[]).indexOf(p.id) >= 0;   // 多标签：处于已打开标签页即视为生效
    }
    return true;   // float：未隐藏即生效
  }
  export function closeSettingsMenus() {
    HOST.document.querySelectorAll('.settings-card-menu').forEach(function (m) { m.remove(); });
    syncNativeCover();
  }
  export function openPluginCardMenu(ev: MouseEvent, btn: HTMLElement, p: PluginDescriptor) {
    ev.stopPropagation();
    const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + p.id + '"]');
    closeSettingsMenus();
    if (wasOpen) return;   // 再次点同一个按钮 = 收起（否则只能靠点别处才关得掉）
    const menu = HOST.document.createElement('div');
    menu.className = 'settings-card-menu';
    menu.setAttribute('data-owner', p.id);
    if (p.builtin) {
      const dis = HOST.document.createElement('button');
      dis.className = 'settings-menu-btn disabled';
      dis.textContent = '内置插件 · 不可删除';
      dis.disabled = true;
      menu.appendChild(dis);
    } else {
      const d = HOST.document.createElement('button');
      d.className = 'settings-menu-btn danger';
      d.textContent = '删除';
      d.addEventListener('click', function () {
        closeSettingsMenus();
        if (HOST.confirm('确定删除插件 “' + (p.name || p.id) + '” 吗？')) {
          callAction('plugin.delete', { plugin_id: p.id }).then(function () { renderSettings(); }).catch(function (e) { HOST.alert('删除失败：' + e.message); });
        }
      });
      menu.appendChild(d);
    }
    HOST.document.body.appendChild(menu);
    const r = btn.getBoundingClientRect();
    menu.style.right = (HOST.innerWidth - r.right) + 'px';
    menu.style.top = (r.bottom + 4) + 'px';
    syncNativeCover();
  }

  // 把某插件置为对应槽位的当前活动实例（fixed 卸旧挂新；panel 切换抽屉选中），并持久化用户选择
  export function activateSlotPlugin(p: PluginDescriptor) {
    // 后端归一化后的插件描述必带 slot，这里仅收窄类型供 slotMap 索引
    const slot = p.slot as string;
    const type = (p.slotDef || {}).type;
    if (type === 'panel') {
      // 多标签容器：把该插件打开为标签页并激活（未打开则新增，已打开则聚焦）
      openPanelTab(p.id);
      return;
    }
    if (type === 'fixed') {
      // 单例槽互斥：先把同区域其它插件全部关掉，再打开目标插件（占位者自动让位）
      if (!railState.hidden) railState.hidden = {};
      (slotMap[slot] || []).forEach((x) => { if (x.id !== p.id) railState.hidden[x.id] = true; });
      delete railState.hidden[p.id];
      // 中栏容器区域：容器插件入驻即让内置容器让位（容器仍占位，由该插件提供）
      if (slot === 'panel-container' && p.id !== PANEL_CONTAINER_ID) railState.hidden[PANEL_CONTAINER_ID] = true;
      activeBySlot[slot] = p.id;   // 记住该单例槽当前选中的插件
      refreshFixedSlot(slot);
      buildRail();
      persistActive();
      persistRail().catch(() => {});
      return;
    }
    // modal：弹窗实例按 railState.hidden 控制显示/隐藏（快捷栏等外部入口也走这里）
    if (type === 'modal') {
      if (railHidden(p.id)) setPluginHidden(p.id, false);
      buildRail();
      return;
    }
    // float：自由浮窗无单例约束，直接显示
    if (railHidden(p.id)) setPluginHidden(p.id, false);
    buildRail();
  }
  export function togglePluginOpen(p: PluginDescriptor) {
    const type = (p.slotDef || {}).type;
    // 多标签容器：对某面板插件的开/关 = 新开 / 关闭它对应的标签页
    if (type === 'panel') {
      if (pluginVisible(p)) closePanelTab(p.id);
      else openPanelTab(p.id);
      return;
    }
    if (pluginVisible(p)) {   // 关闭：fixed=隐藏锚定区；float=隐藏实例
      setPluginHidden(p.id, true); buildRail();
      return;
    }
    // 打开：fixed 单例槽——同区域已有别的插件在运行时先关掉占位者再打开目标，
    // 互斥规则统一由 activateSlotPlugin 处理
    activateSlotPlugin(p);   // float 无单例约束，直接显示
  }

