// 设置面板开合与外观设置（图标栏、面板容器透明度/宽度）
import { callAction, syncNativeCover } from './bus.js';
import { saveConfig } from './config-apply.js';
import { cfgCardHead } from './config-center.js';
import { applyPanelContainerCfg, applyPanelWidth, panelContainerCfg, panelDesiredWidth, panelSavedWidth, setPanelSavedWidth, setPanelDesiredWidth } from './panel.js';
import { applyRailOpacity, persistRail } from './rail.js';
import { closeSettingsMenus, renderSettings } from './settings-tabs.js';
import { HOST, configByPlugin, railState } from './state.js';

  // ---- 设置面板开合（宿主固有资产，非插件）：原生渲染到 .settings-body ----
  export function setSettingsOpen(open: boolean) {
    HOST.document.body.classList.toggle('settings-open', !!open);
    // 设置按钮高亮跟随面板开合
    const sb = HOST.document.getElementById('railSettings');
    if (sb) {
      sb.classList.toggle('on', !!open);
      sb.classList.toggle('off', !open);
    }
    if (!open) closeSettingsMenus();   // 菜单挂在 body 上，面板关掉后不能留在界面上
    if (open) renderSettings();
    syncNativeCover();
  }

  // 设置面板内"配置变更后防抖重建"（仅离散操作调用：滑块等连续输入不打断交互）
  export let settingsRenderT: number | null = null;
  export function scheduleSettingsRender() {
    if (settingsRenderT != null) clearTimeout(settingsRenderT);
    settingsRenderT = setTimeout(renderSettings, 250);
  }
  export function settingsSave(pid: string, cfg: Record<string, any>) {
    // 实时下发 + 持久化即可；卡片控件值已在位，不再整面板重建（避免拖动滑块被打断）
    callAction('config.set', { plugin_id: pid, config: cfg }).catch(() => {});
  }

  // 通用：卡片内 range 字段（label + 滑条 + 实时数值）
  export function cfgRangeField(grid: HTMLElement, label: string, min: number, max: number, step: number, value: number, fmt: (v: number) => string, onInput: (v: number) => void) {
    const f = HOST.document.createElement('div');
    f.className = 'cfg-field';
    const lb = HOST.document.createElement('label');
    lb.className = 'cfg-label';
    lb.textContent = label;
    f.appendChild(lb);
    const rng = HOST.document.createElement('input');
    rng.type = 'range';
    rng.className = 'cfg-range';
    rng.min = String(min); rng.max = String(max); rng.step = String(step);
    rng.value = String(value);
    const valEl = HOST.document.createElement('div');
    valEl.className = 'range-val';
    function upd() { valEl.textContent = fmt(Number(rng.value)); }
    // 已拉部分填强调色，未拉部分保持白色
    function paint() {
      const span = (Number(max) - Number(min)) || 1;
      const pct = Math.max(0, Math.min(100, (Number(rng.value) - Number(min)) / span * 100));
      rng.style.background = 'linear-gradient(90deg, var(--wm-accent) 0 ' + pct + '%, #fff ' + pct + '% 100%)';
    }
    rng.addEventListener('input', function () { paint(); upd(); onInput(Number(rng.value)); });
    upd();
    paint();
    f.appendChild(rng);
    f.appendChild(valEl);
    grid.appendChild(f);
  }

  // 透明度控件（统一方向：滑块数值越大越透明）。
  // 落盘值仍是 alpha（不透明度），因此既有配置与视觉默认值均不变，仅反转控件方向。
  export function transparencyField(grid: HTMLElement, label: string, alphaMin: number, alphaValue: number, step: number, onAlpha: (v: number) => void) {
    const a = Math.min(1, Math.max(alphaMin, alphaValue));
    cfgRangeField(grid, label, 0, Number((1 - alphaMin).toFixed(4)), step,
      Number((1 - a).toFixed(4)),
      function (t: number) { return label + ' ' + t.toFixed(2); },
      function (t: number) { onAlpha(Number((1 - t).toFixed(4))); });
  }

  // 白条透明度（宿主外观项，不依赖插件）——统一 cfg-card 风格
  export function renderRailAppearance(container: HTMLElement) {
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    cfgCardHead(card, '外观设置', '宿主', '最左图标栏外观 · 透明度实时生效');
    const body = HOST.document.createElement('div');
    body.className = 'cfg-card-body';
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid one-col';
    const o = typeof railState.opacity === 'number' ? railState.opacity : 1;
    transparencyField(grid, '透明度', 0.15, o, 0.05, function (v: number) {
      railState.opacity = v;
      applyRailOpacity();
      persistRail().catch(() => {});
    });
    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }

  // 中栏容器为宿主固有资产（非插件）：设置内提供透明度 + 默认宽度；配置存到"面板容器"键
  // panelSavedWidth 区分「用户显式保存的宽度」与「运行时最大舒展宽度」——后者不落盘
  export function settingsSavePanel() {
    const persist: Record<string, any> = { opacity: panelContainerCfg.opacity };
    if (panelSavedWidth != null) persist.width = panelSavedWidth;
    configByPlugin['panel-container'] = persist;
    applyPanelContainerCfg();
    saveConfig().catch(() => {});
  }
  export function renderPanelContainerSettings(container: HTMLElement) {
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    cfgCardHead(card, '容器设置', '宿主', '中栏系统级容器 · 透明度与默认宽度');
    const body = HOST.document.createElement('div');
    body.className = 'cfg-card-body';
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid one-col';

    // 透明度
    const o = Number(panelContainerCfg.opacity);
    transparencyField(grid, '透明度', 0.15, (o >= 0.15 && o <= 1) ? o : 1, 0.05, function (v: number) {
      panelContainerCfg.opacity = v;
      applyPanelContainerCfg();
      settingsSavePanel();
    });

    // 默认宽度
    const wf = HOST.document.createElement('div');
    wf.className = 'cfg-field';
    const wl = HOST.document.createElement('label');
    wl.className = 'cfg-label';
    wl.textContent = '默认宽度 (px)';
    wf.appendChild(wl);
    const num = HOST.document.createElement('input');
    num.type = 'number';
    num.min = '260';
    num.step = '10';
    num.className = 'cfg-input';
    num.placeholder = '留空 = 最大舒展';
    num.value = (panelSavedWidth != null) ? String(panelSavedWidth) : '';
    num.addEventListener('change', function () {
      if (!num.value) {   // 清空 = 回到「最大舒展」
        setPanelSavedWidth(null);
        setPanelDesiredWidth(null);
        applyPanelWidth();
        settingsSavePanel();
        return;
      }
      const w = Number(num.value);
      if (w >= 260) {
        setPanelSavedWidth(w);
        setPanelDesiredWidth(w);
        applyPanelWidth();
        settingsSavePanel();
      } else {
        HOST.alert('宽度不能小于 260px');
        num.value = (panelSavedWidth != null) ? String(panelSavedWidth) : '';
      }
    });
    wf.appendChild(num);
    grid.appendChild(wf);

    body.appendChild(grid);
    card.appendChild(body);
    container.appendChild(card);
  }

  // 依赖类型 / 放置根 → 展示文案（plugin.json 的 dependency / root 字段）
