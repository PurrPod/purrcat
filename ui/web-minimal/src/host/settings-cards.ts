// 插件卡片渲染（元信息、字段表单）
import { callAction } from './bus.js';
import { cfgCardHead } from './config-center.js';
import { cfgRangeField, scheduleSettingsRender, settingsSave, transparencyField } from './settings-appearance.js';
import { AREA_LABEL, openPluginCardMenu, pluginVisible, renderSettings, togglePluginOpen } from './settings-tabs.js';
import { HOST, groupState } from './state.js';
import type { ConfigField, PluginDescriptor, PluginDependency } from './types.js';

  export const DEP_KIND_LABEL: Record<string, string> = { skill: '技能', plugin: '插件', mcp: 'MCP', agentloop: 'AgentLoop', sensor: '传感器', graph: '图谱' };
  export const ROOT_KIND_LABEL: Record<string, string> = { builtin: '内置', sandbox: '沙盒', user: '用户' };
  // 插件卡片元信息行：声明放置位置（root）不一致告警与依赖清单（dependency）；
  // 实际来源（origin）已并入标题行，与「面板/未显示」等 chip 同行展示。
  export function renderPluginMeta(card: HTMLElement, p: PluginDescriptor) {
    const row = HOST.document.createElement('div');
    row.className = 'cfg-card-meta';
    const chip = (text: string, cls?: string) => {
      const el = HOST.document.createElement('span');
      el.className = 'p-tag' + (cls ? ' ' + cls : '');
      el.textContent = text;
      return el;
    };
    // 声明了 root 却与实际放置位置不符 → 标黄提示
    if (p.root && p.rootOk === false) {
      row.appendChild(chip('声明 ' + (ROOT_KIND_LABEL[p.root] || p.root), 'warn'));
      row.appendChild(chip('⚠ 放置位置与声明不一致', 'warn'));
    }
    const deps = Array.isArray(p.dependency) ? p.dependency : [];
    if (deps.length) {
      const lb = HOST.document.createElement('span');
      lb.className = 'meta-label';
      lb.textContent = '依赖';
      row.appendChild(lb);
      deps.forEach((d: PluginDependency) => row.appendChild(chip((DEP_KIND_LABEL[d.type] || d.type) + ' · ' + d.id)));
    }
    if (row.childNodes.length) card.appendChild(row);
  }

  // 插件卡片（与配置中心统一的 cfg-card 风格）：标题/行为chip/状态chip + 打开关闭 + 抽屉菜单 + 可视化字段
  export function renderPluginCard(container: HTMLElement, p: PluginDescriptor, cfg: Record<string, any>) {
    const type = (p.slotDef || {}).type || 'fixed';
    const typeName = type === 'fixed' ? '固定' : (type === 'panel' ? '面板' : (type === 'modal' ? '模态' : '浮窗'));
    const vis = pluginVisible(p);
    const card = HOST.document.createElement('div');
    card.className = 'cfg-card';
    const h = cfgCardHead(card, p.name || p.id, typeName, p.id);
    // 状态 chip：panel 表达"容器当前显示哪个"；fixed/float 表达启停
    const st = HOST.document.createElement('span');
    st.className = 'cfg-chip ' + (vis ? 'on' : 'off');
    st.textContent = type === 'panel' ? (vis ? '显示中' : '未显示') : (vis ? '已启用' : '已关闭');
    h.titleRow.appendChild(st);
    // 来源 chip：插件实际所在根（plugin.json 的 root → 后端回填 origin），
    // 与「面板/未显示」等 chip 同行，直接显示「内置/沙盒/用户」。
    const originName = ROOT_KIND_LABEL[p.origin || ''] || p.origin || '';
    if (originName) {
      const oc = HOST.document.createElement('span');
      oc.className = 'cfg-chip type';
      oc.textContent = originName;
      h.titleRow.appendChild(oc);
    }
    // 打开 / 关闭
    const tg = HOST.document.createElement('button');
    tg.className = 'btn cfg-edit';
    tg.textContent = vis ? '关闭' : '打开';
    tg.addEventListener('click', function () { togglePluginOpen(p); renderSettings(); });
    h.right.appendChild(tg);
    // 抽屉菜单（删除 / 内置标识）
    const menuBtn = HOST.document.createElement('button');
    menuBtn.className = 'btn icon menu-btn';
    menuBtn.textContent = '▾';
    menuBtn.title = '更多操作';
    menuBtn.addEventListener('click', function (ev) { openPluginCardMenu(ev, menuBtn, p); });
    h.right.appendChild(menuBtn);
    // 来源 / 声明位置 / 依赖（plugin.json 的 root / dependency 字段）
    renderPluginMeta(card, p);
    // 配置字段
    if (p.configSchema && p.configSchema.length) {
      const body = HOST.document.createElement('div');
      body.className = 'cfg-card-body';
      const grid = HOST.document.createElement('div');
      grid.className = 'cfg-grid one-col';
      renderFields(grid, p, cfg);
      body.appendChild(grid);
      card.appendChild(body);
    } else {
      const body = HOST.document.createElement('div');
      body.className = 'cfg-card-body';
      const none = HOST.document.createElement('span');
      none.className = 'p-tag';
      none.textContent = '该插件无配置项';
      body.appendChild(none);
      card.appendChild(body);
    }
    container.appendChild(card);
  }

  export function renderFields(grid: HTMLElement, p: PluginDescriptor, cfg: Record<string, any>) {
    (p.configSchema || []).forEach(function (field: ConfigField) {
      const key = field.key;
      const type = field.type || 'text';
      const label = field.label || key;
      if (type === 'switch') {
        const row = HOST.document.createElement('div');
        row.className = 'cfg-field switch-row';
        const lb = HOST.document.createElement('label');
        lb.className = 'cfg-label';
        lb.textContent = label;
        row.appendChild(lb);
        const sw = HOST.document.createElement('label');
        sw.className = 'switch';
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector('input');
        if (!chk) return;   // 新建的 label 内必然含 input，守卫仅为类型收窄
        chk.checked = !!cfg[key];
        chk.addEventListener('change', function () { cfg[key] = chk.checked; settingsSave(p.id, cfg); });
        row.appendChild(sw);
        grid.appendChild(row);
        return;
      }
      if (type === 'range') {
        let fv = cfg[key];
        const initVal: number = (typeof fv === 'number' && !isNaN(fv)) ? fv : ((field.default != null) ? (field.default as number) : ((field.max != null) ? field.max : 1));
        const min0 = (field.min != null) ? field.min : 0;
        const step0 = (field.step != null) ? field.step : 0.01;
        const applyVal = function (v: number) { cfg[key] = v; settingsSave(p.id, cfg); };
        if (key === 'opacity') {
          // 透明度：滑块越大越透明（落盘仍是 alpha，视觉默认不变）
          transparencyField(grid, label, min0, initVal, step0, applyVal);
        } else {
          cfgRangeField(grid, label, min0, (field.max != null) ? field.max : 1, step0, initVal,
            function (v: number) { return label + ' ' + v.toFixed(2); }, applyVal);
        }
        return;
      }
      if (type === 'plugin-multi') {
        // 插件多选：扫描当前插件清单，勾选后由插件自己在界面上消费（如侧栏快捷栏）
        const f = HOST.document.createElement('div');
        f.className = 'cfg-field wide';
        const lb = HOST.document.createElement('label');
        lb.className = 'cfg-label';
        lb.textContent = label;
        f.appendChild(lb);

        const box = HOST.document.createElement('div');
        box.className = 'plugin-picker';
        let sel = Array.isArray(cfg[key]) ? cfg[key].slice() : [];
        const cands = (groupState.plugins || []).filter(function (x) { return x.id !== p.id && x.entry; });
        if (!cands.length) {
          const emp = HOST.document.createElement('div');
          emp.className = 'p-tag';
          emp.textContent = '没有可添加的插件';
          box.appendChild(emp);
        }
        cands.forEach(function (pl) {
          const row = HOST.document.createElement('div');
          row.className = 'pk-row';
          const info = HOST.document.createElement('div');
          info.className = 'pk-info';
          const nm = HOST.document.createElement('div');
          nm.className = 'pk-name';
          nm.textContent = pl.name || pl.id;
          info.appendChild(nm);
          const area = HOST.document.createElement('div');
          area.className = 'pk-area';
          const slotArea = (pl.slotDef || {}).area || '';
          const areaName = AREA_LABEL[slotArea] || slotArea;
          area.textContent = pl.id + (areaName ? ' · ' + areaName : '');
          info.appendChild(area);
          row.appendChild(info);

          const sw = HOST.document.createElement('label');
          sw.className = 'switch';
          sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
          const chk = sw.querySelector('input');
          if (!chk) return;   // 新建的 label 内必然含 input，守卫仅为类型收窄
          chk.checked = sel.indexOf(pl.id) >= 0;
          chk.addEventListener('change', function () {
            if (chk.checked) { if (sel.indexOf(pl.id) < 0) sel.push(pl.id); }
            else sel = sel.filter(function (x) { return x !== pl.id; });
            cfg[key] = sel;
            settingsSave(p.id, cfg);
          });
          row.appendChild(sw);
          box.appendChild(row);
        });
        f.appendChild(box);

        const hint = HOST.document.createElement('div');
        hint.className = 'pk-hint';
        hint.textContent = '勾选后出现在侧栏「快捷栏」，点击即可唤起对应插件。';
        f.appendChild(hint);
        grid.appendChild(f);
        return;
      }
      const f = HOST.document.createElement('div');
      f.className = 'cfg-field' + (type === 'wallpapers' ? ' wide' : '');
      const lb = HOST.document.createElement('label');
      lb.className = 'cfg-label';
      lb.textContent = label;
      f.appendChild(lb);
      if (type === 'select') {
        const sel = HOST.document.createElement('select');
        sel.className = 'cfg-input';
        ((field.options || []) as string[]).forEach(function (op) {
          const o2 = HOST.document.createElement('option');
          o2.value = op;
          o2.textContent = op;
          sel.appendChild(o2);
        });
        sel.value = cfg[key] || '';
        sel.addEventListener('change', function () { cfg[key] = sel.value; settingsSave(p.id, cfg); });
        f.appendChild(sel);
      } else if (type === 'number') {
        const num = HOST.document.createElement('input');
        num.type = 'number';
        num.step = 'any';
        num.className = 'cfg-input';
        num.value = cfg[key] == null ? '' : cfg[key];
        num.addEventListener('change', function () { cfg[key] = num.value === '' ? null : Number(num.value); settingsSave(p.id, cfg); });
        f.appendChild(num);
      } else if (type === 'wallpapers') {
        const wallsWrap = HOST.document.createElement('div');
        wallsWrap.className = 'walls';
        const list = Array.isArray(cfg[key]) ? cfg[key] : [];
        function isV(url: string) { return /\.(mp4|webm|mov)(\?|$)/i.test(url); }
        function draw() {
          wallsWrap.innerHTML = '';
          list.forEach(function (w, i) {
            const t = HOST.document.createElement('div');
            t.className = 'wall-thumb';
            if (isV(w.src || '')) { const v = HOST.document.createElement('video'); v.src = w.src; v.muted = true; v.loop = true; t.appendChild(v); }
            else { const im = HOST.document.createElement('img'); im.src = w.src; im.alt = ''; t.appendChild(im); }
            const del = HOST.document.createElement('button');
            del.className = 'wall-del';
            del.textContent = '×';
            del.addEventListener('click', function () { list.splice(i, 1); commit(); draw(); });
            t.appendChild(del);
            wallsWrap.appendChild(t);
          });
          const add = HOST.document.createElement('button');
          add.className = 'btn sm';
          add.textContent = '+ 添加';
          add.addEventListener('click', function () {
            callAction('dialog.pickWallpaper', {}).then(function (up) {
              const r = up as { url?: string; filename?: string } | null;
              if (!r || !r.url) return;
              list.push({ src: r.url, type: isV(r.url) ? 'video' : 'image', name: r.filename });
              cfg.mode = 'wallpaper';
              commit();
              draw();
              scheduleSettingsRender();   // 离散操作：重建面板让"背景模式"下拉同步
            }).catch(function () {});
          });
          wallsWrap.appendChild(add);
        }
        function commit() { cfg[key] = list; settingsSave(p.id, cfg); }
        draw();
        f.appendChild(wallsWrap);
      } else {
        const txt = HOST.document.createElement('input');
        txt.type = 'text';
        txt.className = 'cfg-input';
        txt.value = cfg[key] || '';
        txt.addEventListener('change', function () { cfg[key] = txt.value; settingsSave(p.id, cfg); });
        f.appendChild(txt);
      }
      grid.appendChild(f);
    });
  }

