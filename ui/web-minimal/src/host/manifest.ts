// manifest → 宿主内存态装配与刷新
import { PANEL_CONTAINER_ID } from './areas.js';
import { applyLayoutFromManifest } from './layout.js';
import { buildSlotIndex, mountAll } from './mount.js';
import { applyPanelContainerCfg, loadPanelShell, panelContainerCfg, panelDesiredWidth, panelSavedWidth, panelTabs, setPanelSavedWidth, setPanelDesiredWidth } from './panel.js';
import { applyPersistedHidden, buildRail, persistActive } from './rail.js';
import { activeBySlot, configByPlugin, groupState, railState } from './state.js';
import { effectiveConfig } from './utils.js';
import type { WebminManifest } from './types.js';

  // ---- 刷新 manifest 并重建/挂载 ----
  // manifest → 宿主内存态的唯一装配点：插件表、全量插件配置、图标栏状态、面板容器配置、单例槽选择
  export function applyManifestState(manifest: WebminManifest): void {
    groupState.plugins = manifest.plugins || [];
    // 布局模式与平铺窗口顺序/宽度（缺省回落容器式）
    applyLayoutFromManifest(manifest.layout);
    // 为「全部」插件建立有效配置（schema 默认值 ∪ 已存值）。
    // 关键：未挂载插件（如非当前抽屉选中的面板插件）的已存配置也要进入 configByPlugin，
    // 否则设置面板展示默认值、整体保存时还会把它的已存配置覆写丢失。
    groupState.plugins.forEach((p) => { configByPlugin[p.id] = effectiveConfig(p); });
    // 图标栏持久化状态
    const railSaved = manifest.rail;
    if (railSaved && typeof railSaved === 'object') {
      const stage = Number(railSaved.stage);
      // 兼容旧三态持久化（0=收起 1=仅图标 2=图标+名称）：仅 2 → 1（图标+文字），其余 → 0（仅图标）
      railState.stage = (Number.isFinite(stage) && stage >= 2) ? 1 : 0;
      railState.hidden = (railSaved.hidden && typeof railSaved.hidden === 'object') ? railSaved.hidden : {};
      // 旧键迁移：内置容器曾是宿主的合成候选（开关键 __panel__），现为真实内置插件 builtin-panel
      if (Object.prototype.hasOwnProperty.call(railState.hidden, '__panel__')) {
        if (railState.hidden['__panel__']) railState.hidden[PANEL_CONTAINER_ID] = true;
        delete railState.hidden['__panel__'];
      }
      railState.opacity = (typeof railSaved.opacity === 'number') ? railSaved.opacity : 1;
    }
    // 面板容器配置（宿主资产，存于 plugins['panel-container']）
    const savedPanel = (manifest.panelContainer && typeof manifest.panelContainer === 'object') ? manifest.panelContainer : {};
    setPanelSavedWidth((Number(savedPanel.width) >= 260) ? Number(savedPanel.width) : null);
    panelContainerCfg.opacity = (typeof savedPanel.opacity === 'number') ? savedPanel.opacity : 0.9;
    // 有保存宽度则作为期望宽度；无则保留本次会话中拖动产生的期望宽度
    if (panelSavedWidth != null) setPanelDesiredWidth(panelSavedWidth);
    configByPlugin['panel-container'] = Object.assign({}, savedPanel);
    // 单例槽选中项（剔除已卸载插件的残留）
    const savedActive = (manifest.active && typeof manifest.active === 'object') ? manifest.active : {};
    const ids = new Set(groupState.plugins.map((p) => p.id));
    Object.keys(activeBySlot).forEach((k) => delete activeBySlot[k]);
    // 面板容器多标签：标签列表以 JSON 串存于保留键 __panelTabs__（后端 active 只收字符串键值）。
    // 原样保留在 activeBySlot 中，确保后续 persistActive 整节覆盖时不会把标签列表清空。
    panelTabs.length = 0;   // 原地清空：panelTabs 是跨模块共享的 let 绑定，不能整体赋值
    Object.keys(savedActive).forEach((k) => {
      const v = savedActive[k];
      if (k === '__panelTabs__') {
        activeBySlot[k] = String(v);
        try {
          const arr = JSON.parse(v);
          if (Array.isArray(arr)) {
            panelTabs.length = 0;
            // panel.ts 的 panelTabs 未标注类型（推断为 never[]），这里按真实元素类型收窄后再批量追加
            (panelTabs as string[]).push.apply(panelTabs as string[], arr.filter((x: unknown) => typeof x === 'string'));
          }
        } catch (_) {}
        return;
      }
      if (v === '__none__' || ids.has(v)) activeBySlot[k] = v;
    });
  }
  export async function loadManifest(): Promise<void> {
    const manifest = await (await fetch('/api/webmin/manifest')).json();
    applyManifestState(manifest);
  }
  export async function reloadManifest(): Promise<void> {
    await loadManifest();
    await loadPanelShell();
    buildSlotIndex();
    mountAll();
    applyPersistedHidden();
    buildRail();
    applyPanelContainerCfg();
  }

