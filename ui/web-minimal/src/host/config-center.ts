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
  export const DEPLOY_LABEL: Record<string, string> = { uv: 'uv', node: 'node', sandbox: 'sandbox / Docker 沙盒', embedding: 'embedding' };
  export const cfgState: {
    data: Record<string, any>;
    mode: Record<string, string>;
    openKey: Record<string, string>;
    editStr: Record<string, string>;
    sandboxRegistry: string;
    deployLogOpen: Record<string, boolean>;
    diskLogOpen: boolean;
    rawSensor: Record<string, boolean>;
  } = {
    data: {},         // tab -> 已加载的配置对象（GET /api/config/{tab}）
    mode: {},         // tab -> 'cards'|'json'
    openKey: {},      // tab -> 处于展开态的顶级 key
    editStr: {},      // tab+'::'+key -> 编辑区文本
    sandboxRegistry: '',
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
    // sensor/mcp：手动强制重载（改了 ~/.purrcat 下的代码或外部配置文件时用）
    if (RELOAD_EP[key]) {
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

  export function renderConfigSection(main: HTMLElement, key: string) {
    if (key === 'acp') return renderAcpCard(main);
    if (key === 'deploy') return renderDeployCards(main);
    if (key === 'soul') return renderSoulEditor(main);
    cfgToolbar(main, key);
    if ((cfgState.mode[key] || 'cards') === 'json') {
      renderRawJson(main, key);
    } else if (key === 'model') {
      renderModelCards(main, key);
    } else if (key === 'mcp') {
      renderMcpCards(main, key);
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

  // ---- mcp：服务器卡片（按单服务器拆分）----
  export function renderMcpCards(main: HTMLElement, key: string) {
    cfgData(key).then(function (data) {
      // mcp_config.json 的结构为 { mcpServers: { 服务器名: 配置 } }，需先解包这一层
      if (!data || typeof data !== 'object' || Array.isArray(data)) data = {};
      if (!data.mcpServers || typeof data.mcpServers !== 'object' || Array.isArray(data.mcpServers)) data.mcpServers = {};
      cfgState.data[key] = data;
      const servers = data.mcpServers;
      const names = Object.keys(servers);
      if (names.length === 0) {
        const empty = HOST.document.createElement('div'); empty.className = 'p-tag'; empty.textContent = '（暂无 MCP 服务器）'; main.appendChild(empty);
      }
      names.forEach(function (name) {
        const isOpen = cfgState.openKey[key] === name;
        const val = servers[name];
        const card = cfgCard(main);
        const preview = JSON.stringify(val);
        const h = cfgCardHead(card, name, (Array.isArray(val) ? 'array' : typeof val), preview.slice(0, 90) + (preview.length > 90 ? '…' : ''));
        const edit = HOST.document.createElement('button');
        edit.className = 'btn cfg-edit';
        edit.textContent = isOpen ? '关闭' : '编辑';
        edit.addEventListener('click', function () {
          if (isOpen) delete cfgState.openKey[key]; else { cfgState.openKey[key] = name; cfgState.editStr[key + '::' + name] = JSON.stringify(val, null, 2); }
          rerenderConfig(main, key);
        });
        h.right.appendChild(edit);
        const del = HOST.document.createElement('button');
        del.className = 'btn cfg-del';
        del.textContent = '删除';
        del.addEventListener('click', function () {
          if (!HOST.confirm('删除 MCP 服务器 "' + name + '"？')) return;
          delete servers[name];
          delete cfgState.openKey[key];
          putCfg(key, data).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('删除失败：' + (e && e.message || '')); });
        });
        h.right.appendChild(del);
        if (!isOpen) return;
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        const ta = HOST.document.createElement('textarea');
        ta.className = 'settings-json';
        ta.style.minHeight = '150px';
        ta.value = cfgState.editStr[key + '::' + name] || JSON.stringify(val, null, 2);
        ta.addEventListener('input', function () { cfgState.editStr[key + '::' + name] = ta.value; });
        body.appendChild(ta);
        const save = HOST.document.createElement('button');
        save.className = 'btn cfg-save';
        save.textContent = '保存该服务器';
        save.addEventListener('click', function () {
          let obj;
          try { obj = JSON.parse(cfgState.editStr[key + '::' + name]); } catch (e) { HOST.alert('JSON 解析失败：' + (e as Error).message); return; }
          servers[name] = obj;
          delete cfgState.openKey[key];
          putCfg(key, data).then(function () { rerenderConfig(main, key); }).catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
        });
        body.appendChild(save);
        card.appendChild(body);
      });
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
        const row = HOST.document.createElement('div');
        row.className = 'cfg-field switch-row';
        row.appendChild(sensorFieldLabel(label));
        const sw = HOST.document.createElement('label');
        sw.className = 'switch';
        sw.innerHTML = '<input type="checkbox"><span class="slider"></span>';
        const chk = sw.querySelector('input') as HTMLInputElement; // innerHTML 刚写入，input 必然存在
        let on = raw === 'true' || raw === '1';
        chk.checked = on;
        chk.addEventListener('change', function () { on = chk.checked; });
        row.appendChild(sw);
        grid.appendChild(row);
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
          f.appendChild(inp);
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
    saveBtn.className = 'btn cfg-save';
    saveBtn.textContent = '保存';
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

    const tip = HOST.document.createElement('div');
    tip.className = 'cfg-tip';
    tip.textContent = '保存后会自动重载 sensor 进程；若仍未生效，可点顶部「重载到内存」再试。';
    body.appendChild(tip);
  }

  export function renderGenericCards(main: HTMLElement, key: string) {
    const isSensor = key === 'sensor';
    Promise.all([cfgData(key), isSensor ? sensorRuntimeMap() : Promise.resolve({})]).then(function (res) {
      const obj: Record<string, any> = res[0] || {};
      const runMap: Record<string, any> = res[1] || {};
      const keys = Object.keys(obj).filter(function (k) { return k !== '__ARRAY_WRAPPER__'; });
      if (keys.length === 0) { const e = HOST.document.createElement('div'); e.className = 'p-tag'; e.textContent = '（空配置）'; main.appendChild(e); }
      keys.forEach(function (k) {
        const val = obj[k];
        const isOpen = cfgState.openKey[key] === k;
        const card = cfgCard(main);
        const raw = (typeof val === 'object') ? JSON.stringify(val) : String(val);
        const rt = isSensor ? runMap[k] : null;
        const running = !!(rt && rt.alive);
        // sensor：卡片头展示 icon（config 里的 icon 链接，留空/失效回退默认图标）
        const iconArg = (isSensor && val && typeof val === 'object') ? (val.icon || '') : undefined;
        // 卡片不展示配置内容（env 等含凭证），其值只在展开编辑时才呈现
        const sub = isSensor ? '' : (raw.slice(0, 90) + (raw.length > 90 ? '…' : ''));
        const h = cfgCardHead(card, k, (Array.isArray(val) ? 'array' : typeof val), sub, iconArg);
        if (isSensor) {
          const st = HOST.document.createElement('span');
          st.className = 'cfg-chip ' + (running ? 'on' : 'off');
          st.textContent = running ? '运行中' : '未运行';
          if (running && rt.pid) st.title = 'PID ' + rt.pid;
          h.titleRow.appendChild(st);
        }
        // 运行中的 sensor 可直接停止：杀进程 + 置 enabled=false
        if (isSensor && running) {
          const stopBtn = HOST.document.createElement('button');
          stopBtn.className = 'btn cfg-stop';
          stopBtn.textContent = '停止';
          stopBtn.title = '杀死该 Sensor 后台进程，并在配置里置为 enabled=false';
          stopBtn.addEventListener('click', function () {
            if (!HOST.confirm('停止 Sensor "' + k + '"？将杀死其后台进程并置为 enabled=false。')) return;
            stopBtn.disabled = true;
            stopBtn.textContent = '停止中…';
            fetch('/api/config/sensor/' + encodeURIComponent(k) + '/stop', { method: 'POST' })
              .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
              .then(function () { delete cfgState.data[key]; delete cfgState.openKey[key]; rerenderConfig(main, key); })
              .catch(function (e) { stopBtn.disabled = false; stopBtn.textContent = '停止'; HOST.alert('停止失败：' + (e && e.message || '')); });
          });
          h.right.appendChild(stopBtn);
        } else if (isSensor) {
          // 未运行（被停止或启动失败）时才给「重启」：置 enabled=true 后重新拉起进程
          const restartBtn = HOST.document.createElement('button');
          restartBtn.className = 'btn cfg-restart';
          restartBtn.textContent = '重启';
          restartBtn.title = '置为 enabled=true 并重新拉起该 Sensor 后台进程';
          restartBtn.addEventListener('click', function () {
            if (!HOST.confirm('重启 Sensor "' + k + '"？将置为 enabled=true 并重新拉起后台进程。')) return;
            restartBtn.disabled = true;
            restartBtn.textContent = '重启中…';
            fetch('/api/config/sensor/' + encodeURIComponent(k) + '/restart', { method: 'POST' })
              .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
              .then(function (b) {
                delete cfgState.data[key]; delete cfgState.openKey[key];
                rerenderConfig(main, key);
                if (b && b.started === false) HOST.alert('重启未成功：' + ((b && b.message) || '请检查本地 <name>.py 与 uv'));
              })
              .catch(function (e) { restartBtn.disabled = false; restartBtn.textContent = '重启'; HOST.alert('重启失败：' + (e && e.message || '')); });
          });
          h.right.appendChild(restartBtn);
        }
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
        // sensor：删除键旁再挂一个箭头，展开下拉提供「彻底删除」（连正式文件一起删）
        if (isSensor) {
          const more = HOST.document.createElement('button');
          more.className = 'btn cfg-caret';
          more.textContent = '▾';
          more.title = '更多删除选项';
          more.addEventListener('click', function (ev) {
            ev.stopPropagation();   // 别让全局 click 把刚弹出的菜单立刻收掉
            const owner = 'cfg-' + k;
            const wasOpen = !!HOST.document.querySelector('.settings-card-menu[data-owner="' + owner + '"]');
            closeSettingsMenus();
            if (wasOpen) return;   // 再点一次同一个箭头 = 收起
            const menu = HOST.document.createElement('div');
            menu.className = 'settings-card-menu';
            menu.setAttribute('data-owner', owner);
            const purge = HOST.document.createElement('button');
            purge.className = 'settings-menu-btn danger';
            purge.textContent = '彻底删除（连文件）';
            purge.addEventListener('click', function () {
              closeSettingsMenus();
              if (!HOST.confirm('彻底删除 Sensor "' + k + '"？将杀死其进程、删除正式文件 ' + k + '.py 并从配置移除，不可恢复。')) return;
              fetch('/api/config/sensor/' + encodeURIComponent(k) + '/purge', { method: 'POST' })
                .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error((b && b.detail) || ('HTTP ' + r.status)); return b; }); })
                .then(function () { delete cfgState.data[key]; delete cfgState.openKey[key]; rerenderConfig(main, key); })
                .catch(function (e) { HOST.alert('彻底删除失败：' + (e && e.message || '')); });
            });
            menu.appendChild(purge);
            HOST.document.body.appendChild(menu);
            const b = more.getBoundingClientRect();
            menu.style.right = (HOST.innerWidth - b.right) + 'px';
            menu.style.top = (b.bottom + 4) + 'px';
            syncNativeCover();
          });
          h.right.appendChild(more);
        }
        if (!isOpen) return;
        const body = HOST.document.createElement('div');
        body.className = 'cfg-card-body';
        const rawModeMap = cfgState.rawSensor || (cfgState.rawSensor = {});
        const hasSchema = isSensor && val && typeof val === 'object'
          && Array.isArray(val.fields) && val.fields.length > 0;

        // 有 fields 声明：渲染成表单；否则（或切到原始模式）走 JSON 文本域
        if (hasSchema && !rawModeMap[k]) {
          renderSensorFields(body, val, function (nextEnv: Record<string, any>) {
            val.env = nextEnv;
            cfgState.editStr[key + '::' + k] = JSON.stringify(val, null, 2);
            putCfg(key, obj)
              .then(function () { delete cfgState.data[key]; HOST.alert('已保存'); rerenderConfig(main, key); })
              .catch(function (e) { HOST.alert('保存失败：' + (e && e.message || '')); });
          });
          body.appendChild(sensorMiniBtn('编辑原始 JSON', '字段表单覆盖不到的高级项可切到原始 JSON', function () {
            cfgState.editStr[key + '::' + k] = JSON.stringify(val, null, 2);
            rawModeMap[k] = true;
            rerenderConfig(main, key);
          }, 'sensor-raw'));
          card.appendChild(body);
          return;
        }

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
        if (hasSchema) {
          body.appendChild(sensorMiniBtn('返回字段表单', '', function () {
            rawModeMap[k] = false;
            rerenderConfig(main, key);
          }, 'sensor-form'));
        }
        card.appendChild(body);
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
    tip.textContent = '按顺序逐步安装依赖：uv → node → sandbox → embedding。需重启应用生效，建议网络稳定。';
    sec.appendChild(tip);
    const list = HOST.document.createElement('div');
    list.className = 'cfg-stepper';
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
    if (!cfgState.sandboxRegistry) {
      fetch('/api/config/sandbox-registry').then(function (r) { return r.json(); }).then(function (d) { if (d) cfgState.sandboxRegistry = d.sandbox_registry || 'ghcr.io/purrpod'; }).catch(function () { cfgState.sandboxRegistry = 'ghcr.io/purrpod'; });
    }
    function draw() {
      cfgData('deploy').then(function (ov) {
        list.innerHTML = '';
        DEPLOY_ITEMS.forEach(function (it, idx) {
          const st = deployState(it, ov);
          const row = HOST.document.createElement('div');
          row.className = 'cfg-step';
          const rail = HOST.document.createElement('div');
          rail.className = 'cfg-step-rail';
          const dot = HOST.document.createElement('div');
          dot.className = 'cfg-step-dot ' + st.state;
          dot.textContent = String(idx + 1);
          rail.appendChild(dot);
          if (idx < DEPLOY_ITEMS.length - 1) { const line = HOST.document.createElement('div'); line.className = 'cfg-step-line'; rail.appendChild(line); }
          row.appendChild(rail);
          const body = HOST.document.createElement('div');
          body.className = 'cfg-step-body';
          const head = HOST.document.createElement('div');
          head.className = 'cfg-step-head';
          const nm = HOST.document.createElement('div');
          nm.className = 'cfg-step-title';
          nm.textContent = DEPLOY_LABEL[it];
          head.appendChild(nm);
          const act = HOST.document.createElement('div');
          act.className = 'cfg-step-act';
          if (it === 'sandbox' && st.item) {
            const docker = HOST.document.createElement('span');
            docker.className = 'cfg-chip ' + (st.item.docker_installed ? 'ok' : 'bad');
            docker.textContent = 'Docker ' + (st.item.docker_installed ? '✓' : '✗');
            act.appendChild(docker);
            const img = HOST.document.createElement('span');
            img.className = 'cfg-chip ' + (st.item.image_ready ? 'ok' : 'warn');
            img.textContent = '镜像 ' + (st.item.image_ready ? '✓' : '✗');
            act.appendChild(img);
          }
          const btn = HOST.document.createElement('button');
          btn.className = 'btn cfg-deploy-btn ' + st.state;
          btn.disabled = !st.clickable;
          btn.textContent = (st.state === 'running' ? '··· ' : '') + st.text;
          btn.addEventListener('click', function () {
            if (!st.clickable) return;
            fetch('/api/config/deploy/' + it, { method: 'POST' }).then(function (r) { if (!r.ok) return r.json().then(function (d2) { throw new Error(d2.detail || '部署冲突'); }); }).then(function () { delete cfgState.data.deploy; draw(); }).catch(function (e) { HOST.alert('失败：' + (e && e.message || '')); });
          });
          act.appendChild(btn);
          head.appendChild(act);
          body.appendChild(head);
          if (it === 'sandbox') {
            const reg = HOST.document.createElement('div');
            reg.className = 'cfg-registry-row';
            const inp = HOST.document.createElement('input');
            inp.type = 'text'; inp.placeholder = 'ghcr.io/…（默认 ghcr.io/purrpod）'; inp.value = cfgState.sandboxRegistry;
            inp.addEventListener('input', function () { cfgState.sandboxRegistry = inp.value; });
            const rs = HOST.document.createElement('button');
            rs.className = 'btn'; rs.textContent = '保存镜像源';
            rs.addEventListener('click', function () { cfgData('deploy'); fetch('/api/config/sandbox-registry', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sandbox_registry: cfgState.sandboxRegistry }) }).then(function (r) { if (!r.ok) throw new Error(''); HOST.alert('镜像源已保存'); }).catch(function () { HOST.alert('保存失败'); }); });
            reg.appendChild(inp);
            reg.appendChild(rs);
            body.appendChild(reg);
          }
          if (st.item && st.item.detail) { const det = HOST.document.createElement('div'); det.className = 'cfg-card-sub'; det.textContent = st.item.detail; body.appendChild(det); }
          const lgToggle = HOST.document.createElement('button');
          lgToggle.className = 'cfg-log-toggle';
          lgToggle.textContent = (cfgState.deployLogOpen[it] ? '收起日志 ▾' : '查看日志 ▸');
          lgToggle.addEventListener('click', function () { cfgState.deployLogOpen[it] = !cfgState.deployLogOpen[it]; draw(); });
          body.appendChild(lgToggle);
          if (cfgState.deployLogOpen[it]) {
            const lgr = HOST.document.createElement('pre');
            lgr.className = 'settings-log';
            lgr.style.minHeight = '80px';
            lgr.textContent = (st.task && st.task.log && st.task.log.length) ? st.task.log.join('\n') : '（暂无日志）';
            body.appendChild(lgr);
          }
          row.appendChild(body);
          list.appendChild(row);
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

