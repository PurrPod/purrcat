// 配置中心各标签页（model / mcp / sensor / acp / deploy）
import { syncNativeCover } from './bus.js';
import { ICON_SVG, ICON_SVG_ATTR } from './icons.js';
import { closeSettingsMenus, deployPollT, renderSoulEditor, setDeployPollT } from './settings-tabs.js';
import { HOST } from './state.js';

  // ---- 原配置中心逐标签页复刻（卡片 + 裸 JSON 双模式）----
  export const MODEL_CATS = [ // 三个模型角色：title/jsonKey
    { key: 'main', title: '核心模型' },
    { key: 'task', title: '后台模型' },
    { key: 'vision', title: '视觉顾问' },
  ];
  export const MODEL_SDKS = ['openai'];
  export const DEPLOY_ITEMS = ['uv', 'node', 'sandbox', 'embedding'];
  export const DEPLOY_LABEL: Record<string, string> = { uv: 'uv', node: 'node', sandbox: 'Docker 沙盒', embedding: 'embedding' };
  const DEPLOY_DESC: Record<string, string> = { uv: 'Python 依赖与运行环境', node: '前端宿主与插件构建', sandbox: 'Docker 隔离执行环境', embedding: '本地向量化模型' };
  const DEPLOY_CHIP: Record<string, string> = { missing: '未安装', failed: '失败', running: '部署中', installed: '待重启', ready: '已就绪' };
  export const cfgState: {
    data: Record<string, any>;
    mode: Record<string, string>;
    openKey: Record<string, string>;
    editStr: Record<string, string>;
    deployLogOpen: Record<string, boolean>;
    diskLogOpen: boolean;
    rawSensor: Record<string, boolean>;
  } = {
    data: {},         // tab -> 已加载的配置对象（GET /api/config/{tab}）
    mode: {},         // tab -> 'cards'|'json'
    openKey: {},      // tab -> 处于展开态的顶级 key
    editStr: {},      // tab+'::'+key -> 编辑区文本
    deployLogOpen: {},
    diskLogOpen: false,
    rawSensor: {},
  };
  export function makeSection(title: string, main: HTMLElement) {
    const sec = HOST.document.createElement('div');
    sec.className = 'settings-section';
    const t = HOST.document.createElement('div');
    t.className = 'settings-section-title';
    t.textContent = title;
    sec.appendChild(t);
    main.appendChild(sec);
    return sec;
  }
  // 配置缓存读取（首次拉取后复用），以及保存
  export async function cfgData(tab: string) {
    if (!cfgState.data[tab]) {
      try { cfgState.data[tab] = await (await fetch('/api/config/' + tab)).json(); }
      catch (e) { cfgState.data[tab] = {}; }
    }
    return cfgState.data[tab];
  }
  // 运行时重载端点：sensor/mcp 的配置在子进程 spawn 时固化，写盘后必须通知运行中的
  // 实例重载（重启进程 / 重建 schema 与检索索引），否则「保存了但没生效」。
  export const RELOAD_EP: Record<string, string> = { sensor: '/api/config/sensor/reload', mcp: '/api/config/mcp/reload' };
  export async function reloadRuntime(tab: string) {
    const ep = RELOAD_EP[tab];
    if (!ep) return null;
    const r = await fetch(ep, { method: 'POST' });
    const body = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error((body && body.detail) || ('HTTP ' + r.status));
    return body;
  }
  export async function putCfg(tab: string, obj: Record<string, any>) {
    cfgState.data[tab] = obj;
    const r = await fetch('/api/config/' + tab, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    // 对齐完整模式：切换开关保存后自动重载。重载失败不阻断保存（可点「重载到内存」重试）
    if (RELOAD_EP[tab]) {
      try { await reloadRuntime(tab); } catch (e) { /* 见上 */ }
    }
  }
  export function rerenderConfig(main: HTMLElement, key: string) { main.innerHTML = ''; renderConfigSection(main, key); }

  // 每个 JSON 型 tab 里：左上角「卡片 / 裸 JSON」切换（rerender 默认重建当前配置页）
  export function cfgToolbar(main: HTMLElement, key: string, rerender?: (main: HTMLElement, key: string) => void) {
    const fn = rerender || rerenderConfig;
    const tb = HOST.document.createElement('div');
    tb.className = 'cfg-toolbar';
    ['卡片', 'JSON'].forEach(function (label, i) {
      const mode = i === 0 ? 'cards' : 'json';
      const seg = HOST.document.createElement('button');
      seg.className = 'cfg-seg' + ((cfgState.mode[key] || 'cards') === mode ? ' active' : '');
      seg.textContent = label;
      seg.addEventListener('click', function () { cfgState.mode[key] = mode; fn(main, key); });
      tb.appendChild(seg);
    });
    if (key !== 'sensor') {
      // 支持刷新：丢弃本地缓存，重新从磁盘拉取该 tab 的配置并重绘
      const rf = HOST.document.createElement('button');
      rf.className = 'cfg-seg cfg-reload';
      rf.textContent = '刷新';
      rf.title = '丢弃本地缓存，重新从磁盘读取配置并重绘';
      rf.addEventListener('click', function () {
        delete cfgState.data[key];
        cfgState.openKey = cfgState.openKey || {};
        delete cfgState.openKey[key];
        fn(main, key);
      });
      tb.appendChild(rf);
    }
    // mcp：手动强制重载（改了 ~/.purrcat 下的代码或外部配置文件时用）
    if (RELOAD_EP[key] && key !== 'sensor') {
      const rl = HOST.document.createElement('button');
      rl.className = 'cfg-seg cfg-reload';
      rl.textContent = '重载到内存';
      rl.title = '让磁盘上的配置与代码立即生效（重启子进程 / 重建索引），无需重启应用';
      rl.addEventListener('click', function () {
        rl.disabled = true;
        rl.textContent = '重载中…';
        reloadRuntime(key)
          .then(function (d) { HOST.alert((d && d.message) || '已重载到内存'); })
          .catch(function (e) { HOST.alert('重载失败：' + (e && e.message || '')); })
          .finally(function () { rl.disabled = false; rl.textContent = '重载到内存'; });
      });
      tb.appendChild(rl);
    }
    main.appendChild(tb);
    return tb;
  }

  export const CONFIG_TITLE: Record<string, string> = { plugins: 'UI 插件设置', model: '模型设置', sensor: '传感器设置', file: '文件权限设置', mcp: 'MCP 设置', soul: '全局人设设置', acp: 'ACP 设置', deploy: '部署设置' };
  const REFRESH_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 6.1"/><path d="M20 4v7h-7"/></svg>';
  const EYE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  const EYE_OFF_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"/><path d="M10.6 6.3A10.7 10.7 0 0 1 12 6c6.5 0 10 6 10 6a17.6 17.6 0 0 1-2.4 3.1"/><path d="M6.6 6.6C3.6 8.6 2 12 2 12s3.5 6 10 6c1.4 0 2.7-.3 3.9-.7"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  const COPY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';

  export function settingsPageHead(main: HTMLElement, key: string, onRefresh?: () => void) {
    const head = HOST.document.createElement('div');
    head.className = 'settings-page-head';
    const title = HOST.document.createElement('h2');
    title.className = 'settings-page-title';
    title.textContent = CONFIG_TITLE[key] || (key + '设置');
    const rf = HOST.document.createElement('button');
    rf.type = 'button';
    rf.className = 'settings-page-refresh';
    rf.title = '重新读取配置文件';
    rf.setAttribute('aria-label', '刷新');
    rf.innerHTML = REFRESH_SVG;
    rf.addEventListener('click', function () {
      rf.classList.add('spinning');
      rf.disabled = true;
      delete cfgState.data[key];
      delete cfgState.openKey[key];
      if (onRefresh) onRefresh();
      else rerenderConfig(main, key);
    });
    head.appendChild(title);
    head.appendChild(rf);
    main.appendChild(head);
  }

  export function renderConfigSection(main: HTMLElement, key: string) {
    settingsPageHead(main, key);
    if (key === 'acp') return renderAcpCard(main);
    if (key === 'deploy') return renderDeployCards(main);
    if (key === 'soul') return renderSoulEditor(main);
    if (key === 'mcp') return renderMcpCards(main, key);
    if (key === 'model') return renderModelCards(main, key);
    if (key === 'file') return renderFilePermissions(main, key);
    cfgToolbar(main, key);
    if ((cfgState.mode[key] || 'cards') === 'json') {
      renderRawJson(main, key);
    } else if (key === 'sensor') {
      renderSensorCards(main, key);
    } else {
      renderGenericCards(main, key);
    }
  }

  // ---- 裸 JSON 编辑 ----
  export function renderRawJson(main: HTMLElement, key: string) {
    const tx = HOST.document.createElement('textarea');
    tx.className = 'settings-json';
    tx.spellcheck = false;
    tx.placeholder = '读取配置…';
    main.appendChild(tx);
    const status = HOST.document.createElement('span');
    status.className = 'p-tag';
    cfgData(key).then(function (data) { tx.value = JSON.stringify(data, null, 2); status.textContent = '已加载'; });
    const bar = HOST.document.createElement('div');
    bar.className = 'settings-actions';
    const save = HOST.document.createElement('button');
    save.className = 'btn';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      let obj;
      try { obj = JSON.parse(tx.value); } catch (e) { HOST.alert('JSON 解析失败：' + (e as Error).message); return; }
      putCfg(key, obj).then(function () { status.textContent = '已保存'; }).catch(function (e) { status.textContent = '保存失败'; HOST.alert('保存失败：' + (e && e.message || '')); });
    });
    bar.appendChild(save);
    bar.appendChild(status);
    main.appendChild(bar);
  }

  // 通用卡片：卡片头（左列=标题行+副标题，右列=动作区）+ 右上动作
  export function cfgCard(main: HTMLElement) {
    const c = HOST.document.createElement('div');
    c.className = 'cfg-card';
    main.appendChild(c);
    return c;
  }
  export function cfgIcon(url?: string) {
    const wrap = HOST.document.createElement('span');
    wrap.className = 'cfg-card-icon';
    const useDefault = function () {
      wrap.innerHTML = '<svg ' + ICON_SVG_ATTR + '>' + ICON_SVG.sensor + '</svg>';
    };
    const u = String(url == null ? '' : url).trim();
    if (!u) { useDefault(); return wrap; }
    const img = HOST.document.createElement('img');
    img.alt = '';
    img.referrerPolicy = 'no-referrer';
    // 图标链接加载失败时回退默认图标
    img.onerror = function () { if (img.parentNode) { img.parentNode.removeChild(img); } useDefault(); };
    img.src = u;
    wrap.appendChild(img);
    return wrap;
  }
  export function cfgCardHead(card: HTMLElement, title: string, kind: string, sub?: string, iconUrl?: string) {
    const head = HOST.document.createElement('div');
    head.className = 'cfg-card-head';
    const left = HOST.document.createElement('div');
    left.className = 'cfg-card-head-l';
    const trow = HOST.document.createElement('div');
    trow.className = 'cfg-card-title';
    // 传入 iconUrl（含空串）时展示头像：有链接用图片，留空或加载失败回退默认图标
    if (iconUrl !== undefined) trow.appendChild(cfgIcon(iconUrl));
    const t = HOST.document.createElement('span');
    t.className = 'cfg-card-name';
    t.textContent = title;
    trow.appendChild(t);
    if (kind) { const k = HOST.document.createElement('span'); k.className = 'cfg-chip type'; k.textContent = kind; trow.appendChild(k); }
    left.appendChild(trow);
    if (sub) {
      const s = HOST.document.createElement('div');
      s.className = 'cfg-card-sub';
      s.textContent = sub;
      left.appendChild(s);
    }
    head.appendChild(left);
    const right = HOST.document.createElement('div');
    right.className = 'cfg-card-act';
    head.appendChild(right);
    card.appendChild(head);
    return { head: head, right: right, left: left, titleRow: trow };
  }

  // ---- model：三角色卡片（每个角色直接平铺展示编辑表单，无展开/收起）----
  export function modelList(data: Record<string, any>, cat: string) {
    return (data && data[cat] && typeof data[cat] === 'object') ? Object.keys(data[cat]) : [];
  }
  // 由已有条目构造编辑表单（无条目时给出空白表单，模型名留空）
  export function modelFormOf(entry: any, entryKey: string): Record<string, any> {
    const e = entry || {};
    const idx = entryKey.indexOf(':');
    const sdk = idx >= 0 ? entryKey.slice(0, idx) : 'openai';
    const modelName = idx >= 0 ? entryKey.slice(idx + 1) : entryKey;
    return {
      sdk: sdk || 'openai',
      modelName: modelName,
      apiKey: (Array.isArray(e.api_keys) && e.api_keys[0]) ? e.api_keys[0] : '',
      baseUrl: e.base_url || '',
      rpm: e.rpm != null ? String(e.rpm) : '60',
      tpm: e.tpm != null ? String(e.tpm) : '1000000',
      concurrency: e.concurrency != null ? String(e.concurrency) : '3',
      maxToken: e.max_token != null ? String(e.max_token) : '500000',
      vision: !!e.vision,
    };
  }
  export function modelField(grid: HTMLElement, label: string, input: HTMLInputElement) {
    const f = HOST.document.createElement('div');
    f.className = 'cfg-field';
    const lb = HOST.document.createElement('label');
    lb.className = 'cfg-label';
    lb.textContent = label;
    f.appendChild(lb);
    input.className = 'cfg-input';
    f.appendChild(input);
    grid.appendChild(f);
  }
  export function renderModelCards(main: HTMLElement, key: string) {
    cfgData(key).then(function (data) {
      MODEL_CATS.forEach(function (cat) {
        const card = cfgCard(main);
        const head = cfgCardHead(card, cat.title, 'model');
        if (!data[cat.key] || typeof data[cat.key] !== 'object') data[cat.key] = {};
        const keys = modelList(data, cat.key);
        // 无已配置条目时也平铺一个空白表单，直接填写即可
        (keys.length ? keys : ['']).forEach(function (entryKey) {
          renderModelForm(card, key, data, cat.key, entryKey, head.right);
        });
      });
    });
  }
  // 角色下的单个模型表单：直接平铺展示，保存后写回并热重载
  export function renderModelForm(card: HTMLElement, key: string, data: Record<string, any>, cat: string, entryKey: string, act: HTMLElement) {
    const main = card.parentNode as HTMLElement;   // 所属配置页容器，保存成功后整页重绘
    const f = modelFormOf((data[cat] || {})[entryKey], entryKey);
    const body = HOST.document.createElement('div');
    body.className = 'cfg-card-body';
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid';
    const mk = HOST.document.createElement('input'); mk.type = 'text'; mk.value = f.modelName; mk.addEventListener('input', function () { f.modelName = mk.value; });
    modelField(grid, '模型名 (key 后缀)', mk);
    const ak = HOST.document.createElement('input'); ak.type = 'password'; ak.value = f.apiKey; ak.placeholder = 'sk-...'; ak.spellcheck = false; ak.addEventListener('input', function () { f.apiKey = ak.value; });
    modelField(grid, 'API KEY', ak);
    const bu = HOST.document.createElement('input'); bu.type = 'text'; bu.value = f.baseUrl; bu.placeholder = 'https://api.deepseek.com'; bu.spellcheck = false; bu.addEventListener('input', function () { f.baseUrl = bu.value; });
    modelField(grid, 'BASE URL', bu);
    if (cat !== 'vision') {
      [['rpm', 'RPM'], ['tpm', 'TPM'], ['concurrency', '并发数'], ['maxToken', 'MAX TOKEN']].forEach(function (pair) {
        const e2 = HOST.document.createElement('input'); e2.type = 'number'; e2.value = f[pair[0]]; e2.addEventListener('input', function () { f[pair[0]] = e2.value; });
        modelField(grid, pair[1], e2);
      });
    }
    body.appendChild(grid);
    if (cat !== 'vision') {
      const swRow = HOST.document.createElement('div');
      swRow.className = 'cfg-field switch-row';
      const swl = HOST.document.createElement('label');
      swl.textContent = '视觉直注（把图片直接注入上下文）';
      swRow.appendChild(swl);
      const sw = HOST.document.createElement('label');
      sw.className = 'switch';
      sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
      sw.querySelector('input')!.checked = f.vision; // innerHTML 刚写入，input 必然存在
      sw.querySelector('input')!.addEventListener('change', function (e2) { f.vision = (e2.target as HTMLInputElement).checked; }); // 同上：innerHTML 刚写入，input 必然存在
      swRow.appendChild(sw);
      body.appendChild(swRow);
    }
    const save = HOST.document.createElement('button');
    save.className = 'btn cfg-save';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      const nm = f.modelName.trim();
      if (!nm) { HOST.alert('请填写模型名'); return; }
      const newKey = (f.sdk || 'openai') + ':' + nm;
      const obj: Record<string, any> = { api_keys: [f.apiKey.trim()], base_url: f.baseUrl.trim() };
      if (cat !== 'vision') {
        obj.rpm = Number(f.rpm) || 60; obj.tpm = Number(f.tpm) || 1000000; obj.concurrency = Number(f.concurrency) || 3; obj.max_token = Number(f.maxToken) || 500000; obj.vision = f.vision;
      }
      if (entryKey && newKey !== entryKey) delete data[cat][entryKey];
      data[cat][newKey] = obj;
      putCfg(key, data).then(function () { rerenderConfig(main, key); HOST.alert('模型已保存并热重载。'); }).catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
    });
    (act || card).appendChild(save);
    card.appendChild(body);
  }

  // ---- mcp：服务器卡片 ----
  const MCP_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/></svg>';

  export function renderMcpCards(main: HTMLElement, key: string) {
    cfgData(key).then(function (data) {
      // mcp_config.json 的结构为 { mcpServers: { 服务器名: 配置 } }，需先解包这一层
      if (!data || typeof data !== 'object' || Array.isArray(data)) data = {};
      if (!data.mcpServers || typeof data.mcpServers !== 'object' || Array.isArray(data.mcpServers)) data.mcpServers = {};
      cfgState.data[key] = data;
      const servers = data.mcpServers;
      const names = Object.keys(servers);
      if (names.length === 0) {
        const empty = HOST.document.createElement('div'); empty.className = 'cfg-empty'; empty.textContent = '暂无 MCP 服务器'; main.appendChild(empty);
        return;
      }
      const grid = HOST.document.createElement('div');
      grid.className = 'entry-grid';
      main.appendChild(grid);
      names.forEach(function (name) {
        const isOpen = cfgState.openKey[key] === name;
        const val = servers[name];
        const isObj = !!val && typeof val === 'object' && !Array.isArray(val);
        const kind = isObj ? (val.url ? 'http' : (val.command ? 'stdio' : 'object')) : (Array.isArray(val) ? 'array' : typeof val);
        const envCount = isObj && val.env && typeof val.env === 'object' ? Object.keys(val.env).length : 0;
        const card = HOST.document.createElement('div');
        card.className = 'entry-card' + (isOpen ? ' is-open' : '');

        const head = HOST.document.createElement('div');
        head.className = 'entry-card-head';
        const icon = HOST.document.createElement('span');
        icon.className = 'cfg-card-icon';
        icon.innerHTML = MCP_ICON;
        head.appendChild(icon);

        const info = HOST.document.createElement('div');
        info.className = 'entry-card-info';
        const titleRow = HOST.document.createElement('div');
        titleRow.className = 'entry-card-title';
        const nm = HOST.document.createElement('span');
        nm.className = 'entry-card-name';
        nm.textContent = name;
        nm.title = name;
        titleRow.appendChild(nm);
        const badge = HOST.document.createElement('span');
        badge.className = 'cfg-chip type';
        badge.textContent = kind;
        titleRow.appendChild(badge);
        const meta = HOST.document.createElement('div');
        meta.className = 'entry-card-meta';
        meta.textContent = (isObj && val.url ? String(val.url) : (isObj && val.command ? String(val.command) : '未配置启动命令')) + (envCount ? ' · ' + envCount + ' 个环境变量' : '');
        info.appendChild(titleRow);
        info.appendChild(meta);
        head.appendChild(info);

        const act = HOST.document.createElement('div');
        act.className = 'entry-card-act';
        const reload = entryIconBtn('restart', '刷新到内存');
        reload.addEventListener('click', function () {
          reload.disabled = true;
          reload.classList.add('spinning');
          reloadRuntime(key)
            .then(function () { reload.classList.remove('spinning'); reload.disabled = false; })
            .catch(function (e) { reload.classList.remove('spinning'); reload.disabled = false; HOST.alert('刷新失败：' + (e && e.message || '')); });
        });
        const edit = entryIconBtn('edit', isOpen ? '收起' : '编辑');
        if (isOpen) edit.classList.add('active');
        edit.addEventListener('click', function () {
          if (isOpen) delete cfgState.openKey[key];
          else { cfgState.openKey[key] = name; cfgState.editStr[key + '::' + name] = JSON.stringify(val, null, 2); }
          rerenderConfig(main, key);
        });
        const del = entryIconBtn('trash', '删除', true);
        del.addEventListener('click', function () {
          if (!HOST.confirm('删除 MCP 服务器 "' + name + '"？')) return;
          delete servers[name];
          delete cfgState.openKey[key];
          putCfg(key, data).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('删除失败：' + (e && e.message || '')); });
        });
        act.appendChild(reload);
        act.appendChild(edit);
        act.appendChild(del);
        head.appendChild(act);
        card.appendChild(head);

        if (isOpen) {
          const body = HOST.document.createElement('div');
          body.className = 'entry-card-body';
          const ta = HOST.document.createElement('textarea');
          ta.className = 'settings-json';
          ta.style.minHeight = '150px';
          ta.value = cfgState.editStr[key + '::' + name] || JSON.stringify(val, null, 2);
          ta.addEventListener('input', function () { cfgState.editStr[key + '::' + name] = ta.value; });
          body.appendChild(ta);
          const save = HOST.document.createElement('button');
          save.className = 'btn cfg-save entry-save';
          save.textContent = '保存并刷新';
          save.addEventListener('click', function () {
            let obj;
            try { obj = JSON.parse(cfgState.editStr[key + '::' + name]); } catch (e) { HOST.alert('JSON 解析失败：' + (e as Error).message); return; }
            servers[name] = obj;
            delete cfgState.openKey[key];
            save.disabled = true;
            save.textContent = '保存中…';
            putCfg(key, data)
              .then(function () { rerenderConfig(main, key); })
              .catch(function (e) { save.disabled = false; save.textContent = '保存并刷新'; HOST.alert('保存失败：' + (e && e.message || '')); });
          });
          body.appendChild(save);
          card.appendChild(body);
        }
        grid.appendChild(card);
      });
    });
  }

  // ---- 文件权限 ----
  const FILE_PERM_MODES = [
    { value: 'readonly', label: '只读' },
    { value: 'writeonly', label: '只写' },
    { value: 'readwrite', label: '读写' },
    { value: 'blocked', label: '禁止读写' },
  ];

  function normalizeFilePerm(raw: any) {
    const src = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    let def = String(src.default_permission || 'readonly');
    if (def === 'writable') def = 'readwrite';
    if (def === 'none') def = 'blocked';
    if (['readonly', 'writeonly', 'readwrite', 'blocked'].indexOf(def) < 0) def = 'readonly';
    const p = src.permissions && typeof src.permissions === 'object' && !Array.isArray(src.permissions) ? src.permissions : {};
    const list = function (v: any) { return Array.isArray(v) ? v.map(String).filter(Boolean) : []; };
    return {
      default_permission: def,
      permissions: { blocked: list(p.blocked), readonly: list(p.readonly), writable: list(p.writable) },
    };
  }

  function saveFilePerm(main: HTMLElement, key: string, data: any) {
    return putCfg(key, data)
      .then(function () { rerenderConfig(main, key); })
      .catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
  }

  function pickPermPaths(directory: boolean): Promise<string[]> {
    const pc = HOST.purrcat;
    if (!pc || !pc.openDialog) return Promise.reject(new Error('文件选择仅在桌面端可用'));
    return pc.openDialog({
      directory: directory,
      properties: directory ? ['openDirectory', 'multiSelections'] : ['openFile', 'multiSelections'],
    }).then(function (r) {
      return Array.isArray(r) ? r.map(String).filter(Boolean) : [];
    });
  }

  function appendPermSection(
    wrap: HTMLElement,
    opt: { title: string; desc: string; paths: string[]; onAdd: (directory: boolean) => void; onRemove: (path: string) => void }
  ) {
    const sec = HOST.document.createElement('section');
    sec.className = 'perm-section';
    const head = HOST.document.createElement('div');
    head.className = 'perm-section-head';
    const txt = HOST.document.createElement('div');
    txt.className = 'perm-section-text';
    const title = HOST.document.createElement('h3');
    title.className = 'perm-section-title';
    title.textContent = opt.title;
    const desc = HOST.document.createElement('p');
    desc.className = 'perm-section-desc';
    desc.textContent = opt.desc;
    txt.appendChild(title);
    txt.appendChild(desc);
    const actions = HOST.document.createElement('div');
    actions.className = 'perm-actions';
    const addFile = entryIconBtn('filePlus', '添加文件');
    addFile.addEventListener('click', function () { opt.onAdd(false); });
    const addFolder = entryIconBtn('folderPlus', '添加文件夹');
    addFolder.addEventListener('click', function () { opt.onAdd(true); });
    actions.appendChild(addFile);
    actions.appendChild(addFolder);
    head.appendChild(txt);
    head.appendChild(actions);

    const group = HOST.document.createElement('div');
    group.className = 'perm-group';
    if (opt.paths.length === 0) {
      const empty = HOST.document.createElement('div');
      empty.className = 'perm-empty';
      empty.textContent = '暂无路径';
      group.appendChild(empty);
    } else {
      opt.paths.forEach(function (path) {
        const row = HOST.document.createElement('div');
        row.className = 'perm-row';
        const text = HOST.document.createElement('span');
        text.className = 'perm-path';
        text.textContent = path;
        text.title = path;
        const del = entryIconBtn('trash', '移除', true);
        del.addEventListener('click', function () { opt.onRemove(path); });
        row.appendChild(text);
        row.appendChild(del);
        group.appendChild(row);
      });
    }
    sec.appendChild(head);
    sec.appendChild(group);
    wrap.appendChild(sec);
  }

  export function renderFilePermissions(main: HTMLElement, key: string) {
    cfgData(key).then(function (raw) {
      const data = normalizeFilePerm(raw);
      cfgState.data[key] = data;
      const readAllowed = data.default_permission === 'readonly' || data.default_permission === 'readwrite';
      const writeAllowed = data.default_permission === 'writeonly' || data.default_permission === 'readwrite';
      const wrap = HOST.document.createElement('div');
      wrap.className = 'perm-page';

      const defSec = HOST.document.createElement('section');
      defSec.className = 'perm-section';
      const defTitle = HOST.document.createElement('h3');
      defTitle.className = 'perm-section-title';
      defTitle.textContent = '默认权限';
      const defGroup = HOST.document.createElement('div');
      defGroup.className = 'perm-group';
      const defRow = HOST.document.createElement('div');
      defRow.className = 'perm-row';
      const defTxt = HOST.document.createElement('div');
      defTxt.className = 'perm-row-text';
      const defLabel = HOST.document.createElement('div');
      defLabel.className = 'perm-row-label';
      defLabel.textContent = '全局默认权限';
      const defDesc = HOST.document.createElement('div');
      defDesc.className = 'perm-row-desc';
      defDesc.textContent = '未命中任意路径规则时使用的读写策略';
      defTxt.appendChild(defLabel);
      defTxt.appendChild(defDesc);
      const select = HOST.document.createElement('select');
      select.className = 'cfg-input perm-select';
      FILE_PERM_MODES.forEach(function (m) {
        const o = HOST.document.createElement('option');
        o.value = m.value;
        o.textContent = m.label;
        select.appendChild(o);
      });
      select.value = data.default_permission;
      select.addEventListener('change', function () {
        data.default_permission = select.value;
        saveFilePerm(main, key, data);
      });
      defRow.appendChild(defTxt);
      defRow.appendChild(select);
      defGroup.appendChild(defRow);
      defSec.appendChild(defTitle);
      defSec.appendChild(defGroup);
      wrap.appendChild(defSec);

      if (!writeAllowed) {
        appendPermSection(wrap, {
          title: '可写白名单',
          desc: '全局默认权限不包含写入时，允许写入的路径',
          paths: data.permissions.writable,
          onAdd: function (directory) {
            pickPermPaths(directory).then(function (paths) {
              if (!paths.length) return;
              paths.forEach(function (p) { if (data.permissions.writable.indexOf(p) < 0) data.permissions.writable.push(p); });
              saveFilePerm(main, key, data);
            }).catch(function (e) { HOST.alert(e && e.message || '选择失败'); });
          },
          onRemove: function (path) {
            data.permissions.writable = data.permissions.writable.filter(function (p) { return p !== path; });
            saveFilePerm(main, key, data);
          },
        });
      }

      if (!readAllowed) {
        appendPermSection(wrap, {
          title: '可读白名单',
          desc: '全局默认权限不包含读取时，允许读取的路径',
          paths: data.permissions.readonly,
          onAdd: function (directory) {
            pickPermPaths(directory).then(function (paths) {
              if (!paths.length) return;
              paths.forEach(function (p) { if (data.permissions.readonly.indexOf(p) < 0) data.permissions.readonly.push(p); });
              saveFilePerm(main, key, data);
            }).catch(function (e) { HOST.alert(e && e.message || '选择失败'); });
          },
          onRemove: function (path) {
            data.permissions.readonly = data.permissions.readonly.filter(function (p) { return p !== path; });
            saveFilePerm(main, key, data);
          },
        });
      }

      appendPermSection(wrap, {
        title: '最高优先级拦截',
        desc: '最先判定，命中后无论全局默认权限如何都禁止读写',
        paths: data.permissions.blocked,
        onAdd: function (directory) {
          pickPermPaths(directory).then(function (paths) {
            if (!paths.length) return;
            paths.forEach(function (p) { if (data.permissions.blocked.indexOf(p) < 0) data.permissions.blocked.push(p); });
            saveFilePerm(main, key, data);
          }).catch(function (e) { HOST.alert(e && e.message || '选择失败'); });
        },
        onRemove: function (path) {
          data.permissions.blocked = data.permissions.blocked.filter(function (p) { return p !== path; });
          saveFilePerm(main, key, data);
        },
      });

      main.appendChild(wrap);
    });
  }

  // ---- 通用 key-value（sensor/file/app）----
  export function coerceVal(str: string, orig: any) {
    if (orig === null || orig === undefined) return str;
    const t = Array.isArray(orig) ? 'array' : typeof orig;
    if (t === 'number') return Number(str);
    if (t === 'boolean') return (str === 'true' || str === '1' || str === '是');
    if (t === 'object') { try { return JSON.parse(str); } catch (e) { return orig; } }
    return str;
  }
  // sensor 后台进程表：name -> {pid, alive}（配置页展示「运行中/未运行」与停止按钮）
  export function sensorRuntimeMap() {
    return fetch('/api/config/sensor/runtime')
      .then(function (r) { return r.json(); })
      .then(function (d) { const m: Record<string, any> = {}; ((d && d.running) || []).forEach(function (s: any) { m[s.name] = s; }); return m; })
      .catch(function () { return {}; });
  }
  // ---- sensor 字段表单：按 config.json 的可选 fields 声明渲染 ----
  // 所有值最终都落进 env（环境变量只能是字符串）：
  //   number/switch -> "123" / "true"；kv/list -> JSON 字符串，sensor 侧 json.loads 读取。
  // fields 只是"声明"，不执行任何脚本；无 fields 的 sensor 仍走原始 JSON 编辑。
  export function sensorJsonValue(raw: string, fallback: any) {
    if (!raw) return fallback;
    try {
      const v = JSON.parse(raw);
      return (v && typeof v === 'object') ? v : fallback;
    } catch (e) { return fallback; }
  }
  export function sensorFieldLabel(text: string) {
    const lb = HOST.document.createElement('label');
    lb.className = 'cfg-label';
    lb.textContent = text;
    return lb;
  }
  export function sensorMiniBtn(text: string, title: string, onClick: EventListener, cls?: string) {
    const b = HOST.document.createElement('button');
    b.type = 'button';
    b.className = 'btn sm' + (cls ? ' ' + cls : '');
    b.textContent = text;
    if (title) b.title = title;
    b.addEventListener('click', onClick);
    return b;
  }
  export function renderSensorFields(body: HTMLElement, sensorCfg: Record<string, any>, save: (nextEnv: Record<string, any>) => void) {
    const fields = Array.isArray(sensorCfg.fields) ? sensorCfg.fields : [];
    const env = (sensorCfg.env && typeof sensorCfg.env === 'object') ? sensorCfg.env : {};
    const grid = HOST.document.createElement('div');
    grid.className = 'cfg-grid';
    const readers: Array<{ field: any; key: string; read: () => string }> = [];

    fields.forEach(function (field: any) {
      const key = field.key;
      if (!key) return;
      const type = field.type || 'text';
      const raw = env[key] == null ? '' : String(env[key]);
      const label = field.label || key;
      let read = function () { return raw; };

      if (type === 'switch') {
        const f = HOST.document.createElement('div');
        f.className = 'cfg-field';
        const row = HOST.document.createElement('div');
        row.className = 'switch-row';
        row.appendChild(sensorFieldLabel(label));
        const sw = HOST.document.createElement('label');
        sw.className = 'switch';
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector('input') as HTMLInputElement; // innerHTML 刚写入，input 必然存在
        let on = raw === 'true' || raw === '1';
        chk.checked = on;
        chk.addEventListener('change', function () { on = chk.checked; });
        row.appendChild(sw);
        f.appendChild(row);
        if (field.help) {
          const hint = HOST.document.createElement('div');
          hint.className = 'pk-hint';
          hint.textContent = field.help;
          f.appendChild(hint);
        }
        grid.appendChild(f);
        read = function () { return on ? 'true' : 'false'; };
      } else {
        const f = HOST.document.createElement('div');
        f.className = 'cfg-field' + ((type === 'kv' || type === 'list' || type === 'textarea') ? ' wide' : '');
        f.appendChild(sensorFieldLabel(label));

        if (type === 'select') {
          const sel = HOST.document.createElement('select');
          sel.className = 'cfg-input';
          (field.options || []).forEach(function (op: any) {
            const o = HOST.document.createElement('option');
            const val = (op && typeof op === 'object') ? op.value : op;
            o.value = String(val);
            o.textContent = (op && typeof op === 'object') ? (op.label || val) : op;
            sel.appendChild(o);
          });
          const init = raw || (field.default != null ? String(field.default) : '');
          sel.value = init;
          sel.addEventListener('change', function () { read = function () { return sel.value; }; });
          read = function () { return sel.value; };
          f.appendChild(sel);
        } else if (type === 'number' || type === 'slider') {
          const min = field.min != null ? Number(field.min) : 0;
          const max = field.max != null ? Number(field.max) : 100;
          const step = field.step != null ? Number(field.step) : 1;
          let init = raw === '' ? (field.default != null ? Number(field.default) : min) : Number(raw);
          if (!isFinite(init)) init = min;
          if (type === 'slider') {
            const rng = HOST.document.createElement('input');
            rng.type = 'range';
            rng.className = 'cfg-range';
            rng.min = String(min); rng.max = String(max); rng.step = String(step); rng.value = String(init);
            const valEl = HOST.document.createElement('div');
            valEl.className = 'range-val';
            const paint = function () {
              const span = (max - min) || 1;
              const pct = Math.max(0, Math.min(100, (Number(rng.value) - min) / span * 100));
              rng.style.background = 'linear-gradient(90deg, var(--wm-accent) 0 ' + pct + '%, #fff ' + pct + '% 100%)';
              valEl.textContent = rng.value + (field.unit ? ' ' + field.unit : '');
            };
            rng.addEventListener('input', function () { paint(); read = function () { return String(Number(rng.value)); }; });
            read = function () { return String(Number(rng.value)); };
            paint();
            f.appendChild(rng);
            f.appendChild(valEl);
          } else {
            const num = HOST.document.createElement('input');
            num.type = 'number';
            num.className = 'cfg-input';
            num.min = String(min); num.max = String(max); num.step = String(step);
            num.value = raw === '' ? (field.default != null ? field.default : '') : raw;
            read = function () {
              if (num.value === '' && field.default != null) return String(field.default);
              return num.value;
            };
            f.appendChild(num);
          }
        } else if (type === 'kv') {
          const dict = sensorJsonValue(raw, {});
          const rows = Object.keys(dict).map(function (k) {
            return { k: k, v: dict[k] == null ? '' : String(dict[k]) };
          });
          const wrap = HOST.document.createElement('div');
          wrap.className = 'sensor-rows';
          function draw() {
            wrap.innerHTML = '';
            rows.forEach(function (row, i) {
              const line = HOST.document.createElement('div');
              line.className = 'sensor-row';
              const ki = HOST.document.createElement('input');
              ki.className = 'cfg-input';
              ki.placeholder = field.key_label || '键';
              ki.value = row.k;
              ki.addEventListener('input', function () { row.k = ki.value; });
              const vi = HOST.document.createElement('input');
              vi.className = 'cfg-input';
              vi.placeholder = field.value_label || '值';
              vi.value = row.v;
              vi.addEventListener('input', function () { row.v = vi.value; });
              line.appendChild(ki);
              line.appendChild(vi);
              line.appendChild(sensorMiniBtn('×', '删除这条', function () { rows.splice(i, 1); draw(); }, 'sensor-del'));
              wrap.appendChild(line);
            });
            if (!rows.length) {
              const emp = HOST.document.createElement('div');
              emp.className = 'pk-hint';
              emp.textContent = '还没有条目';
              wrap.appendChild(emp);
            }
            wrap.appendChild(sensorMiniBtn('+ 添加', '', function () { rows.push({ k: '', v: '' }); draw(); }, 'sensor-add'));
          }
          draw();
          f.appendChild(wrap);
          read = function () {
            const out: Record<string, any> = {};
            rows.forEach(function (row) {
              const k = String(row.k).trim();
              if (k) out[k] = row.v;
            });
            return JSON.stringify(out);
          };
        } else if (type === 'list') {
          const itemFields = Array.isArray(field.item_fields) ? field.item_fields : null;
          const arr = sensorJsonValue(raw, []);
          const rows = arr.map(function (item: any) {
            if (itemFields) {
              const obj = (item && typeof item === 'object') ? item : {};
              return { vals: itemFields.map(function (sub: any) { return obj[sub.key] == null ? '' : String(obj[sub.key]); }) };
            }
            return { vals: [String(item == null ? '' : item)] };
          });
          const wrap = HOST.document.createElement('div');
          wrap.className = 'sensor-rows';
          function draw() {
            wrap.innerHTML = '';
            rows.forEach(function (row: any, i: number) {
              const line = HOST.document.createElement('div');
              line.className = 'sensor-row';
              const subs = itemFields || [{ key: '', placeholder: field.item_placeholder || '值' }];
              subs.forEach(function (sub: any, j: number) {
                const inp = HOST.document.createElement('input');
                inp.className = 'cfg-input';
                inp.placeholder = sub.placeholder || sub.label || sub.key || '值';
                inp.value = row.vals[j] || '';
                inp.addEventListener('input', function () { row.vals[j] = inp.value; });
                line.appendChild(inp);
              });
              line.appendChild(sensorMiniBtn('×', '删除这条', function () { rows.splice(i, 1); draw(); }, 'sensor-del'));
              wrap.appendChild(line);
            });
            if (!rows.length) {
              const emp = HOST.document.createElement('div');
              emp.className = 'pk-hint';
              emp.textContent = '还没有条目';
              wrap.appendChild(emp);
            }
            wrap.appendChild(sensorMiniBtn('+ 添加', '', function () {
              rows.push({ vals: (itemFields || [1]).map(function () { return ''; }) });
              draw();
            }, 'sensor-add'));
          }
          draw();
          f.appendChild(wrap);
          read = function () {
            const out: any[] = [];
            rows.forEach(function (row: any) {
              if (itemFields) {
                const obj: Record<string, any> = {};
                let any = false;
                itemFields.forEach(function (sub: any, j: number) {
                  const v = row.vals[j] || '';
                  obj[sub.key] = v;
                  if (v.trim()) any = true;
                });
                if (any) out.push(obj);
              } else if ((row.vals[0] || '').trim()) {
                out.push(row.vals[0]);
              }
            });
            return JSON.stringify(out);
          };
        } else if (type === 'textarea') {
          const ta = HOST.document.createElement('textarea');
          ta.className = 'cfg-input settings-json';
          ta.style.minHeight = '96px';
          ta.value = raw;
          ta.addEventListener('input', function () { read = function () { return ta.value; }; });
          read = function () { return ta.value; };
          f.appendChild(ta);
        } else {
          const inp = HOST.document.createElement('input');
          inp.type = (type === 'password') ? 'password' : (type === 'url' ? 'url' : 'text');
          inp.className = 'cfg-input';
          inp.spellcheck = false;
          inp.placeholder = field.placeholder || '';
          inp.value = raw === '' && field.default != null ? String(field.default) : raw;
          inp.addEventListener('input', function () { read = function () { return inp.value; }; });
          read = function () { return inp.value; };
          if (type === 'password') {
            const wrap = HOST.document.createElement('div');
            wrap.className = 'cfg-secret';
            wrap.appendChild(inp);
            const eye = HOST.document.createElement('button');
            eye.type = 'button';
            eye.className = 'cfg-inline-icon';
            eye.title = '显示明文';
            eye.setAttribute('aria-label', '显示明文');
            eye.innerHTML = EYE_SVG;
            eye.addEventListener('click', function () {
              const show = inp.type === 'password';
              inp.type = show ? 'text' : 'password';
              eye.innerHTML = show ? EYE_OFF_SVG : EYE_SVG;
              eye.title = show ? '隐藏' : '显示明文';
            });
            const copy = HOST.document.createElement('button');
            copy.type = 'button';
            copy.className = 'cfg-inline-icon';
            copy.title = '复制';
            copy.setAttribute('aria-label', '复制');
            copy.innerHTML = COPY_SVG;
            copy.addEventListener('click', function () {
              const done = function () {
                copy.title = '已复制';
                setTimeout(function () { copy.title = '复制'; }, 1200);
              };
              if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(inp.value).then(done).catch(function () { inp.select(); HOST.document.execCommand('copy'); done(); });
              } else {
                inp.select();
                HOST.document.execCommand('copy');
                done();
              }
            });
            wrap.appendChild(eye);
            wrap.appendChild(copy);
            f.appendChild(wrap);
          } else {
            f.appendChild(inp);
          }
        }

        if (field.help) {
          const hint = HOST.document.createElement('div');
          hint.className = 'pk-hint';
          hint.textContent = field.help;
          f.appendChild(hint);
        }
        grid.appendChild(f);
      }

      readers.push({ field: field, key: key, read: read });
    });

    body.appendChild(grid);

    const saveBtn = HOST.document.createElement('button');
    saveBtn.className = 'btn cfg-save entry-save';
    saveBtn.textContent = '保存并刷新';
    saveBtn.addEventListener('click', function () {
      const nextEnv = Object.assign({}, env);
      for (var i = 0; i < readers.length; i++) {
        const r = readers[i];
        const v = r.read();
        if (r.field.required && !String(v).trim()) {
          HOST.alert('请填写：' + (r.field.label || r.key));
          return;
        }
        nextEnv[r.key] = v;
      }
      save(nextEnv);
    });
    body.appendChild(saveBtn);
  }

  export function renderGenericCards(main: HTMLElement, key: string) {
    cfgData(key).then(function (loaded) {
      const obj: Record<string, any> = loaded || {};
      const keys = Object.keys(obj).filter(function (k) { return k !== '__ARRAY_WRAPPER__'; });
      if (keys.length === 0) { const e = HOST.document.createElement('div'); e.className = 'cfg-empty'; e.textContent = '暂无配置项'; main.appendChild(e); }
      keys.forEach(function (k) {
        const val = obj[k];
        const isOpen = cfgState.openKey[key] === k;
        const card = cfgCard(main);
        const raw = (typeof val === 'object') ? JSON.stringify(val) : String(val);
        // 卡片不展示配置内容，其值只在展开编辑时才呈现
        const sub = raw.slice(0, 90) + (raw.length > 90 ? '…' : '');
        const h = cfgCardHead(card, k, (Array.isArray(val) ? 'array' : typeof val), sub);
        const edit = HOST.document.createElement('button');
        edit.className = 'btn cfg-edit';
        edit.textContent = isOpen ? '关闭' : '编辑';
        edit.addEventListener('click', function () {
          if (isOpen) delete cfgState.openKey[key]; else { cfgState.openKey[key] = k; cfgState.editStr[key + '::' + k] = (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val)); }
          rerenderConfig(main, key);
        });
        h.right.appendChild(edit);
        const del = HOST.document.createElement('button');
        del.className = 'btn cfg-del';
        del.textContent = '删除';
        del.addEventListener('click', function () {
          if (!HOST.confirm('删除配置项 "' + k + '"？')) return;
          delete obj[k];
          delete cfgState.openKey[key];
          putCfg(key, obj).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('删除失败：' + (e && e.message || '')); });
        });
        h.right.appendChild(del);
        if (!isOpen) return;
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        const ta = HOST.document.createElement('textarea');
        ta.className = 'settings-json';
        ta.style.minHeight = '140px';
        ta.value = cfgState.editStr[key + '::' + k] || (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val));
        ta.addEventListener('input', function () { cfgState.editStr[key + '::' + k] = ta.value; });
        body.appendChild(ta);
        const save = HOST.document.createElement('button');
        save.className = 'btn cfg-save';
        save.textContent = '保存该配置项';
        save.addEventListener('click', function () {
          let newVal;
          try { newVal = coerceVal(cfgState.editStr[key + '::' + k], val); } catch (e) { HOST.alert((e as Error).message); return; }
          obj[k] = newVal;
          delete cfgState.openKey[key];
          putCfg(key, obj).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
        });
        body.appendChild(save);
        card.appendChild(body);
      });
    });
  }

  // ---- sensor：卡片网格 ----
  const ENTRY_ACTION_ICON: Record<string, string> = {
    restart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 6.1"/><path d="M20 4v7h-7"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M9 7V5h6v2"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v5M14 11v5"/></svg>',
    filePlus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6M9 15h6"/></svg>',
    folderPlus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v6M9 14h6"/></svg>',
  };

  function entryIconBtn(name: string, title: string, danger?: boolean) {
    const b = HOST.document.createElement('button');
    b.type = 'button';
    b.className = 'entry-icon-btn' + (danger ? ' danger' : '');
    b.title = title;
    b.setAttribute('aria-label', title);
    b.innerHTML = ENTRY_ACTION_ICON[name] || '';
    return b;
  }

  export function renderSensorCards(main: HTMLElement, key: string) {
    Promise.all([cfgData(key), sensorRuntimeMap()]).then(function (res) {
      const obj: Record<string, any> = res[0] || {};
      const runMap: Record<string, any> = res[1] || {};
      const names = Object.keys(obj).filter(function (k) { return k !== '__ARRAY_WRAPPER__'; });
      if (names.length === 0) {
        const empty = HOST.document.createElement('div');
        empty.className = 'cfg-empty';
        empty.textContent = '暂无传感器';
        main.appendChild(empty);
        return;
      }
      const grid = HOST.document.createElement('div');
      grid.className = 'entry-grid';
      main.appendChild(grid);

      names.forEach(function (name) {
        const val = obj[name];
        const isOpen = cfgState.openKey[key] === name;
        const rt = runMap[name];
        const running = !!(rt && rt.alive);
        const fieldCount = (val && Array.isArray(val.fields)) ? val.fields.length : 0;
        const card = HOST.document.createElement('div');
        card.className = 'entry-card' + (isOpen ? ' is-open' : '');

        const head = HOST.document.createElement('div');
        head.className = 'entry-card-head';
        head.appendChild(cfgIcon((val && typeof val === 'object') ? (val.icon || '') : ''));

        const info = HOST.document.createElement('div');
        info.className = 'entry-card-info';
        const titleRow = HOST.document.createElement('div');
        titleRow.className = 'entry-card-title';
        const nm = HOST.document.createElement('span');
        nm.className = 'entry-card-name';
        nm.textContent = name;
        nm.title = name;
        const st = HOST.document.createElement('span');
        st.className = 'cfg-chip ' + (running ? 'on' : 'off');
        st.textContent = running ? '运行中' : '未运行';
        if (running && rt.pid) st.title = 'PID ' + rt.pid;
        titleRow.appendChild(nm);
        titleRow.appendChild(st);
        const meta = HOST.document.createElement('div');
        meta.className = 'entry-card-meta';
        meta.textContent = (val && val.source === 'remote' ? '远程' : '本地') + ' · ' + (fieldCount ? fieldCount + ' 个配置字段' : '无字段声明');
        info.appendChild(titleRow);
        info.appendChild(meta);
        head.appendChild(info);

        const act = HOST.document.createElement('div');
        act.className = 'entry-card-act';
        const power = entryIconBtn(running ? 'stop' : 'restart', running ? '停止' : '重启', running);
        power.addEventListener('click', function () {
          const verb = running ? '停止' : '重启';
          if (!HOST.confirm(verb + ' Sensor "' + name + '"？')) return;
          power.disabled = true;
          fetch('/api/config/sensor/' + encodeURIComponent(name) + (running ? '/stop' : '/restart'), { method: 'POST' })
            .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
            .then(function (b) {
              delete cfgState.data[key];
              delete cfgState.openKey[key];
              rerenderConfig(main, key);
              if (!running && b && b.started === false) HOST.alert('重启未成功：' + ((b && b.message) || ('请检查本地 ' + name + '.py 与 uv')));
            })
            .catch(function (e) { power.disabled = false; HOST.alert(verb + '失败：' + (e && e.message || '')); });
        });
        const edit = entryIconBtn('edit', isOpen ? '收起' : '编辑');
        if (isOpen) edit.classList.add('active');
        edit.addEventListener('click', function () {
          if (isOpen) delete cfgState.openKey[key];
          else {
            cfgState.openKey[key] = name;
            cfgState.editStr[key + '::' + name] = (val && typeof val === 'object') ? JSON.stringify(val, null, 2) : String(val);
          }
          rerenderConfig(main, key);
        });
        const del = entryIconBtn('trash', '删除', true);
        del.addEventListener('click', function (ev) {
          ev.stopPropagation();
          const owner = 'sensor-' + name;
          const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + owner + '"]');
          closeSettingsMenus();
          if (wasOpen) return;
          const menu = HOST.document.createElement('div');
          menu.className = 'settings-card-menu';
          menu.setAttribute('data-owner', owner);
          const conf = HOST.document.createElement('button');
          conf.className = 'settings-menu-btn';
          conf.textContent = '删除配置';
          conf.addEventListener('click', function () {
            closeSettingsMenus();
            if (!HOST.confirm('删除 Sensor "' + name + '" 的配置？')) return;
            delete obj[name];
            delete cfgState.openKey[key];
            putCfg(key, obj)
              .then(function () { delete cfgState.data[key]; rerenderConfig(main, key); })
              .catch(function (e) { HOST.alert('删除失败：' + (e && e.message || '')); });
          });
          const purge = HOST.document.createElement('button');
          purge.className = 'settings-menu-btn danger';
          purge.textContent = '彻底删除（含文件）';
          purge.addEventListener('click', function () {
            closeSettingsMenus();
            if (!HOST.confirm('彻底删除 Sensor "' + name + '"？将杀死其进程、删除正式文件 ' + name + '.py 并从配置移除，不可恢复。')) return;
            fetch('/api/config/sensor/' + encodeURIComponent(name) + '/purge', { method: 'POST' })
              .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
              .then(function () { delete cfgState.data[key]; delete cfgState.openKey[key]; rerenderConfig(main, key); })
              .catch(function (e) { HOST.alert('彻底删除失败：' + (e && e.message || '')); });
          });
          menu.appendChild(conf);
          menu.appendChild(purge);
          HOST.document.body.appendChild(menu);
          const b = del.getBoundingClientRect();
          menu.style.right = (HOST.innerWidth - b.right) + 'px';
          menu.style.top = (b.bottom + 4) + 'px';
          syncNativeCover();
        });
        act.appendChild(power);
        act.appendChild(edit);
        act.appendChild(del);
        head.appendChild(act);
        card.appendChild(head);

        if (isOpen) {
          const body = HOST.document.createElement('div');
          body.className = 'entry-card-body';
          const hasSchema = val && typeof val === 'object' && Array.isArray(val.fields) && val.fields.length > 0;
          const saveCfg = function (next: any, btn?: HTMLButtonElement) {
            obj[name] = next;
            if (btn) { btn.disabled = true; btn.textContent = '保存中…'; }
            putCfg(key, obj)
              .then(function () { return fetch('/api/config/sensor/reload', { method: 'POST' }); })
              .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                delete cfgState.data[key];
                rerenderConfig(main, key);
              })
              .catch(function (e) {
                if (btn) { btn.disabled = false; btn.textContent = '保存并刷新'; }
                HOST.alert('保存失败：' + (e && e.message || ''));
              });
          };
          if (hasSchema) {
            renderSensorFields(body, val, function (nextEnv: Record<string, any>) {
              val.env = nextEnv;
              cfgState.editStr[key + '::' + name] = JSON.stringify(val, null, 2);
              saveCfg(val);
            });
          } else {
            const ta = HOST.document.createElement('textarea');
            ta.className = 'settings-json';
            ta.style.minHeight = '140px';
            ta.value = cfgState.editStr[key + '::' + name] || (typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val));
            ta.addEventListener('input', function () { cfgState.editStr[key + '::' + name] = ta.value; });
            body.appendChild(ta);
            const save = HOST.document.createElement('button');
            save.className = 'btn cfg-save entry-save';
            save.textContent = '保存并刷新';
            save.addEventListener('click', function () {
              let next;
              try { next = coerceVal(cfgState.editStr[key + '::' + name], val); } catch (e) { HOST.alert((e as Error).message); return; }
              saveCfg(next, save);
            });
            body.appendChild(save);
          }
          card.appendChild(body);
        }
        grid.appendChild(card);
      });
    });
  }

  // ---- acp：接入卡片 ----
  export function renderAcpCard(main: HTMLElement) {
    const sec = makeSection('ACP 接入', main);
    const card = cfgCard(sec);
    const h = cfgCardHead(card, 'ACP 编辑器接入', 'relay');
    fetch('/api/config/acp').then(function (r) { return r.json(); }).then(function (d) {
      const sub = HOST.document.createElement('div');
      sub.className = 'cfg-card-sub';
      sub.textContent = 'relay 已部署:' + (d.relay_deployed ? '是' : '否') + ' · 与源一致:' + (d.relay_matches_source ? '是' : '否') + ' · uv:' + (d.uv_found ? '可用' : '缺失')
        + (d.actual_port ? ' · 实际端口:' + d.actual_port + (d.port_mismatch ? '（与设置不一致，relay 生效的是实际端口）' : '') : '');
      h.left.appendChild(sub);
      const body = HOST.document.createElement('div');
      body.className = 'cfg-card-body';
      const grid = HOST.document.createElement('div');
      grid.className = 'cfg-grid';
      const portF = HOST.document.createElement('div');
      portF.className = 'cfg-field';
      const plb = HOST.document.createElement('label'); plb.className = 'cfg-label'; plb.textContent = '端口';
      portF.appendChild(plb);
      const port = HOST.document.createElement('input'); port.type = 'number'; port.className = 'cfg-input'; if (d.port) port.value = d.port;
      portF.appendChild(port);
      grid.appendChild(portF);
      body.appendChild(grid);
      const ops = HOST.document.createElement('div');
      ops.className = 'settings-actions';
      const enact = HOST.document.createElement('button'); enact.className = 'btn'; enact.textContent = '保存端口';
      enact.addEventListener('click', function () { fetch('/api/config/acp', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ port: Number(port.value) }) }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('端口已更新'); }).catch(function () { HOST.alert('保存失败'); }); });
      ops.appendChild(enact);
      const red = HOST.document.createElement('button'); red.className = 'btn'; red.textContent = '重新部署 relay';
      red.addEventListener('click', function () { fetch('/api/config/acp/redeploy', { method: 'POST' }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('已重新部署'); }).catch(function () { HOST.alert('部署失败'); }); });
      ops.appendChild(red);
      const rtk = HOST.document.createElement('button'); rtk.className = 'btn'; rtk.textContent = '重置 token';
      rtk.addEventListener('click', function () { fetch('/api/config/acp/reset-token', { method: 'POST' }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('token 已重置，relay 需重启重连'); }).catch(function () { HOST.alert('重置失败'); }); });
      ops.appendChild(rtk);
      body.appendChild(ops);
      card.appendChild(body);
    }).catch(function () {});
    sec.appendChild(card);
  }

  // ---- deploy：四步线性列表 + 状态指示灯 ----
  export function deployState(it: string, ov: any) {
    const item = (ov && ov.items) ? ov.items[it] : null;
    const task = (ov && ov.tasks) ? ov.tasks[it] : null;
    const running = task && task.state === 'running';
    let state;
    if (running) state = 'running';
    else if (task && task.state === 'success') state = 'installed';
    else if (task && task.state === 'failed') state = 'failed';
    else if (item && item.ready) state = 'ready';
    else state = 'missing';
    const clickable = state === 'missing' || state === 'failed';
    const text = state === 'missing' ? '一键部署' : state === 'failed' ? '重新部署' : state === 'running' ? '部署中…' : state === 'installed' ? '已安装待重启' : '已就绪';
    return { state: state, clickable: clickable, text: text, item: item, task: task };
  }
  export function renderDeployCards(main: HTMLElement) {
    const sec = makeSection('部署中心', main);
    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '安装完成后需重启应用生效，建议网络稳定。';
    sec.appendChild(tip);
    const list = HOST.document.createElement('div');
    list.className = 'cfg-deploy-grid';
    sec.appendChild(list);
    // 磁盘维护卡片：只读展示 vhdx 空洞，用户点按钮才执行回收
    const diskTitle = HOST.document.createElement('div');
    diskTitle.className = 'settings-subgroup';
    diskTitle.textContent = '磁盘维护';
    sec.appendChild(diskTitle);
    const diskWrap = HOST.document.createElement('div');
    sec.appendChild(diskWrap);
    function fmtBytes(n: any) {
      n = Number(n) || 0;
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let i = 0;
      while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
      return (i === 0 ? Math.round(n) : n.toFixed(2)) + ' ' + units[i];
    }
    function diskAction(path: string, btn: HTMLButtonElement) {
      btn.disabled = true;
      fetch('/api/config/' + path, { method: 'POST' }).then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '操作冲突'); });
        return r.json().catch(function () { return {}; });
      }).then(function (d) {
        delete cfgState.data.deploy;
        draw();
        if (d && d.message) HOST.alert(d.message);
      }).catch(function (e) { btn.disabled = false; HOST.alert('失败：' + (e && e.message || '')); });
    }
    function renderDisk(d: any) {
      diskWrap.innerHTML = '';
      if (!d) return;
      const card = HOST.document.createElement('div');
      card.className = 'cfg-card';
      const head = HOST.document.createElement('div');
      head.className = 'cfg-card-head';
      const left = HOST.document.createElement('div');
      left.className = 'cfg-card-head-l';
      const title = HOST.document.createElement('div');
      title.className = 'cfg-card-title';
      const nm = HOST.document.createElement('div');
      nm.className = 'cfg-card-name';
      nm.textContent = 'Docker 数据盘';
      title.appendChild(nm);
      const chip = HOST.document.createElement('span');
      if (!d.supported) {
        chip.className = 'cfg-chip bad';
        chip.textContent = '不可用';
      } else if (d.dead_ratio == null) {
        chip.className = 'cfg-chip off';
        chip.textContent = '待检测';
      } else {
        chip.className = 'cfg-chip ' + (d.needs_compact ? 'warn' : 'ok');
        chip.textContent = '空洞 ' + Math.round(d.dead_ratio * 100) + '%';
      }
      title.appendChild(chip);
      left.appendChild(title);
      const sub = HOST.document.createElement('div');
      sub.className = 'cfg-card-sub';
      sub.textContent = d.detail || '';
      left.appendChild(sub);
      if (d.sandbox && d.sandbox.age_days != null) {
        const sub2 = HOST.document.createElement('div');
        sub2.className = 'cfg-card-sub';
        sub2.textContent = '沙盒容器已使用 ' + d.sandbox.age_days + ' 天' +
          (d.sandbox.age_days >= 14 ? '（使用较久，建议重建一次释放可写层）' : '');
        left.appendChild(sub2);
      }
      head.appendChild(left);

      const taskRunning = d.task && d.task.state === 'running';
      const act = HOST.document.createElement('div');
      act.className = 'cfg-card-act';

      const cp = HOST.document.createElement('button');
      cp.className = 'btn cfg-deploy-btn ' + (taskRunning ? 'running' : 'missing');
      cp.disabled = !d.supported || taskRunning;
      cp.textContent = (taskRunning && d.task.kind === 'compact') ? '回收中…' : '一键回收';
      cp.title = '停止 Docker/WSL 后用 diskpart 压缩 vhdx，需要一次管理员授权（UAC）';
      cp.addEventListener('click', function () {
        if (!HOST.confirm('一键回收会短暂停止 Docker 与 WSL，并弹出一次管理员授权（UAC）。现在执行？')) return;
        diskAction('deploy/disk/compact', cp);
      });
      act.appendChild(cp);

      const pr = HOST.document.createElement('button');
      pr.className = 'btn cfg-deploy-btn missing';
      pr.disabled = !d.docker_running || taskRunning;
      pr.textContent = (taskRunning && d.task.kind === 'prune') ? '清理中…' : '清理构建缓存';
      pr.addEventListener('click', function () { diskAction('deploy/disk/prune', pr); });
      act.appendChild(pr);

      const rb = HOST.document.createElement('button');
      rb.className = 'btn cfg-deploy-btn failed';
      rb.disabled = !d.docker_running || taskRunning;
      rb.textContent = '重建沙盒';
      rb.title = '删除沙盒容器（可写层与容器内缓存清空），下次工具调用自动重建';
      rb.addEventListener('click', function () {
        if (!HOST.confirm('重建沙盒容器？容器内 apt/pip 装过的依赖与缓存会丢失，工作目录内的文件不受影响。')) return;
        diskAction('deploy/disk/rebuild', rb);
      });
      act.appendChild(rb);

      head.appendChild(act);
      card.appendChild(head);

      const needBody = d.needs_compact || taskRunning || (d.task && d.task.state !== 'idle' && d.task.log && d.task.log.length);
      if (needBody) {
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        if (d.needs_compact) {
          const tip = HOST.document.createElement('div');
          tip.className = 'cfg-tip';
          tip.style.margin = '0';
          tip.textContent = '空洞占比已超过 ' + Math.round((d.threshold || 0.3) * 100) +
            '%（约 ' + fmtBytes(d.dead_bytes) + '），建议执行一次「一键回收」，压缩后 Docker 会自动恢复运行。';
          body.appendChild(tip);
        }
        if (d.task && d.task.log && d.task.log.length) {
          const tg = HOST.document.createElement('button');
          tg.className = 'cfg-log-toggle';
          tg.textContent = cfgState.diskLogOpen ? '收起维护日志 ▾' : '查看维护日志 ▸';
          tg.addEventListener('click', function () { cfgState.diskLogOpen = !cfgState.diskLogOpen; renderDisk(d); });
          body.appendChild(tg);
          if (cfgState.diskLogOpen) {
            const lg = HOST.document.createElement('pre');
            lg.className = 'settings-log';
            lg.style.minHeight = '80px';
            lg.textContent = d.task.log.join('\n');
            body.appendChild(lg);
          }
        }
        card.appendChild(body);
      }
      diskWrap.appendChild(card);
    }
    function draw() {
      cfgData('deploy').then(function (ov) {
        list.innerHTML = '';
        DEPLOY_ITEMS.forEach(function (it) {
          const st = deployState(it, ov);
          const card = HOST.document.createElement('div');
          card.className = 'cfg-card cfg-deploy-card';
          const head = HOST.document.createElement('div');
          head.className = 'cfg-card-head';
          const left = HOST.document.createElement('div');
          left.className = 'cfg-card-head-l';
          const title = HOST.document.createElement('div');
          title.className = 'cfg-card-title';
          const nm = HOST.document.createElement('div');
          nm.className = 'cfg-card-name';
          nm.textContent = DEPLOY_LABEL[it];
          let chipText = DEPLOY_CHIP[st.state];
          let chipTone = st.state === 'ready' ? 'ok' : st.state === 'failed' || st.state === 'missing' ? 'bad' : 'warn';
          if (it === 'sandbox' && st.item && st.state !== 'running' && st.state !== 'failed') {
            if (!st.item.docker_installed) {
              chipText = 'Docker 缺';
              chipTone = 'bad';
            } else if (!st.item.image_ready) {
              chipText = '镜像缺';
              chipTone = 'warn';
            } else {
              chipText = '已就绪';
              chipTone = 'ok';
            }
          }
          const chip = HOST.document.createElement('span');
          chip.className = 'cfg-chip ' + chipTone;
          chip.textContent = chipText;
          title.appendChild(nm);
          title.appendChild(chip);
          left.appendChild(title);
          const sub = HOST.document.createElement('div');
          sub.className = 'cfg-card-sub';
          sub.textContent = (st.item && st.item.detail) || DEPLOY_DESC[it];
          left.appendChild(sub);

          const act = HOST.document.createElement('div');
          act.className = 'cfg-card-act';
          const btn = HOST.document.createElement('button');
          btn.className = 'btn cfg-deploy-btn ' + st.state;
          btn.disabled = !st.clickable;
          btn.textContent = (st.state === 'running' ? '··· ' : '') + st.text;
          btn.addEventListener('click', function () {
            if (!st.clickable) return;
            fetch('/api/config/deploy/' + it, { method: 'POST' }).then(function (r) { if (!r.ok) return r.json().then(function (d2) { throw new Error(d2.detail || '部署冲突'); }); }).then(function () { delete cfgState.data.deploy; draw(); }).catch(function (e) { HOST.alert('失败：' + (e && e.message || '')); });
          });
          act.appendChild(btn);
          head.appendChild(left);
          head.appendChild(act);
          card.appendChild(head);

          const foot = HOST.document.createElement('div');
          foot.className = 'cfg-deploy-card-foot';
          const lgToggle = HOST.document.createElement('button');
          lgToggle.className = 'cfg-log-toggle';
          lgToggle.textContent = (cfgState.deployLogOpen[it] ? '收起日志 ▾' : '查看日志 ▸');
          lgToggle.addEventListener('click', function () { cfgState.deployLogOpen[it] = !cfgState.deployLogOpen[it]; draw(); });
          foot.appendChild(lgToggle);
          card.appendChild(foot);
          if (cfgState.deployLogOpen[it]) {
            const lgr = HOST.document.createElement('pre');
            lgr.className = 'settings-log cfg-deploy-log';
            lgr.style.minHeight = '80px';
            lgr.textContent = (st.task && st.task.log && st.task.log.length) ? st.task.log.join('\n') : '（暂无日志）';
            card.appendChild(lgr);
          }
          list.appendChild(card);
        });
        renderDisk(ov && ov.disk);
      });
    }
    draw();
    if (deployPollT) clearInterval(deployPollT);
    setDeployPollT(setInterval(function () {
      if (!HOST.document.body.classList.contains('settings-open')) return;
      delete cfgState.data.deploy;   // 失效缓存
      // 聚焦于列表内输入（如镜像源）时不打断编辑，下个 tick 再重建
      if (HOST.document.activeElement && list.contains(HOST.document.activeElement)) return;
      draw();
    }, 3000));
  }

