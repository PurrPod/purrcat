/* ============================================================================
 * 「Graph」标签：与完整模式 EditorPage(workflow) 对齐
 *   原生画布：节点目录 → 拖拽/连线/缩放 → 节点配置 → 自动布局 → 校验 → 保存
 * ========================================================================== */
(function () {
  'use strict';
  var EV = window.EV;

  var PORT_W = 11;

  var state = {
    catalog: [],
    files: [],
    nodes: [],          // {id, type, name, x, y, config}
    edges: [],          // {id, source, target, sourceHandle, targetHandle}
    selectedId: null,
    selectedEdgeId: null,
    view: { x: 60, y: 60, s: 1 },
    extras: null,       // {env}
    graphName: '',
    description: '',
    dirty: false,
    workplaces: [],                         // 沙盒内（Graph 工厂加工中的产物）
    sandboxCtx: null,                       // 当前编辑的是沙盒产物时为 {workplace_id, name, raw}；否则 null
    drawers: { sandbox: true, files: true, nodes: true }   // 左侧分类抽屉的展开状态
  };

  var sideBodyEl, canvasEl, worldEl, svgEl, toolbarEl, hintEl;
  var palettePanel, paletteBodyEl, zoomPctEl;
  var drag = null;      // {kind:'node'|'pan'|'link', ...}
  var linkPreview = null;

  function clone(v) { return JSON.parse(JSON.stringify(v)); }
  function rand6() { return Math.random().toString(36).substring(2, 8); }
  function defOf(type) {
    for (var i = 0; i < state.catalog.length; i++) if (state.catalog[i].type === type) return state.catalog[i];
    return null;
  }
  function nodeById(id) {
    for (var i = 0; i < state.nodes.length; i++) if (state.nodes[i].id === id) return state.nodes[i];
    return null;
  }

  /* ---------------- 端口推导 ---------------- */
  // 取「被 watch 的字段」当前值：优先读节点配置；配置为空时沿连线取上游节点的输出内容。
  // 对齐完整模式 CustomNode.getUpstreamPortValue —— 模板类节点的正文常通过连线传入
  // （string → template），只有读到模板正文才能用正则推导出 {{变量}} 动态端口。
  function resolveWatchValue(node, key) {
    var v = (node && node.config) ? node.config[key] : undefined;
    if (v !== undefined && v !== null && v !== '') return v;
    var edge = null;
    for (var i = 0; i < state.edges.length; i++) {
      var e = state.edges[i];
      if (e.target === node.id && e.targetHandle === key) { edge = e; break; }
    }
    if (!edge) return v;
    var src = nodeById(edge.source);
    if (!src || !src.config) return v;
    var up = src.config.value;
    return (up !== undefined && up !== null && up !== '') ? up : v;
  }

  function portList(def, dir, node) {
    var src = (dir === 'in' ? def.inputs : def.outputs) || [];
    var listFields = {}, fieldByName = {};
    ((def.config) || []).forEach(function (f) {
      fieldByName[f.name] = f;
      if (f.type === 'list') listFields[f.name] = 1;
    });
    var out = [];
    src.forEach(function (p) {
      if (p.port_type !== 'dynamic') {
        out.push({ name: p.name, type: p.type || 'any', dynamic: false });
        return;
      }
      var rules = p.dynamic_rules || {};
      var key = rules.watch_config;
      if (!key) return;
      // 列表型动态端口（全局输入/输出、环境变量、JSON 键值…）：一个配置项对应一组端口，
      // 整组交给 listBlock 渲染（即使列表为空也要出「+」新增入口），故携带 field/dir。
      if (listFields[key]) {
        out.push({ name: key, type: 'any', dynamic: true, listBacked: true, field: fieldByName[key], dir: dir });
        return;
      }
      var val = node ? resolveWatchValue(node, key) : undefined;
      if (rules.method === 'regex') {
        if (typeof val !== 'string' || !rules.pattern) return;
        var re;
        try { re = new RegExp(rules.pattern, 'g'); } catch (e) { return; }
        var m, seen = {};
        while ((m = re.exec(val)) !== null) {
          var nm = m[1] || m[0];
          if (nm && !seen[nm]) { seen[nm] = 1; out.push({ name: String(nm), type: 'any', dynamic: true }); }
          if (re.lastIndex === m.index) re.lastIndex++;
        }
      } else if (Array.isArray(val)) {
        val.forEach(function (it) {
          var nm = (it && typeof it === 'object') ? (it.name || it.key) : it;
          if (!nm) return;
          var tp = (it && typeof it === 'object' && it.type) ? it.type : 'any';
          out.push({ name: String(nm), type: tp, dynamic: true });
        });
      }
    });
    return out;
  }

  /* ---------------- 自动布局（与完整模式同一套算法） ---------------- */
  function inferAutoLayout(nodes, edges) {
    var depth = {};
    nodes.forEach(function (n) { depth[n.id] = 0; });
    for (var r = 0; r <= nodes.length; r++) {
      var changed = false;
      edges.forEach(function (e) {
        var d = (depth[e.source] || 0) + 1;
        if ((depth[e.target] || 0) < d) { depth[e.target] = d; changed = true; }
      });
      if (!changed) break;
    }
    var succsOf = {}, predsOf = {};
    edges.forEach(function (e) {
      (succsOf[e.source] = succsOf[e.source] || []).push(e.target);
      (predsOf[e.target] = predsOf[e.target] || []).push(e.source);
    });
    for (var r2 = 0; r2 <= nodes.length; r2++) {
      var changed2 = false;
      var order = nodes.slice().sort(function (a, b) { return (depth[b.id] || 0) - (depth[a.id] || 0); });
      order.forEach(function (n) {
        var succs = succsOf[n.id] || [];
        if (!succs.length) return;
        var minSucc = Math.min.apply(null, succs.map(function (s) { return depth[s] || 0; }));
        var preds = predsOf[n.id] || [];
        var lower = preds.length ? Math.max.apply(null, preds.map(function (p) { return (depth[p] || 0) + 1; })) : 0;
        var target = Math.max(minSucc - 1, lower);
        if (target > (depth[n.id] || 0) && target < minSucc) { depth[n.id] = target; changed2 = true; }
      });
      if (!changed2) break;
    }
    var COL = 480, ROW = 480, PAD = 100;
    var buckets = {};
    nodes.forEach(function (n) {
      var d = Math.min(depth[n.id] || 0, Math.max(nodes.length - 1, 0));
      (buckets[d] = buckets[d] || []).push(n.id);
    });
    var pos = {};
    Object.keys(buckets).forEach(function (d) {
      buckets[d].forEach(function (id, i) { pos[id] = { x: PAD + Number(d) * COL, y: PAD + i * ROW }; });
    });
    return pos;
  }

  /* ---------------- 数据 ---------------- */
  async function loadCatalog() {
    try {
      var data = await EV.api.get('/api/graphs/nodes');
      state.catalog = Array.isArray(data) ? data : [];
    } catch (e) {
      state.catalog = [];
      EV.toast('加载节点目录失败：' + e.message, true);
    }
    renderSide();
    renderPalette();
  }

  async function loadFileList() {
    try {
      var data = await EV.api.get('/api/graphs');
      state.files = Array.isArray(data) ? data : [];
    } catch (e) {
      state.files = [];
    }
    renderSide();
  }

  // 沙盒内：列出 Graph 工厂加工中的产物（点击载入可视化画布编辑）
  async function loadWorkplaces() {
    state.workplaces = await EV.sandboxList('graph');
    renderSide();
  }

  // 彻底清理沙盒工作区（不可逆；不影响正式库）
  async function deleteWorkplace(wp) {
    var ok = await EV.confirm({
      title: '清理沙盒',
      message: '确定要彻底清理「' + wp.name + '」的沙盒工作区吗？\n此操作不可逆；已合并成功的沙盒清理不会影响正式库。',
      okLabel: '彻底清理', danger: true
    });
    if (!ok) return;
    try {
      await EV.api.del('/api/evolve/workplace/' + encodeURIComponent(wp.workplace_id) + '?type=graph');
      EV.toast('沙盒已彻底清理');
      if (state.sandboxCtx && state.sandboxCtx.workplace_id === wp.workplace_id) {
        state.sandboxCtx = null;
        state.graphName = '';
        state.dirty = false;
        renderToolbar();
      }
      await loadWorkplaces();
    } catch (e) {
      EV.toast('清理失败：' + e.message, true);
    }
  }

  // 打开沙盒内 Graph 产物：直接载入可视化画布（可编辑，保存回写沙盒 graph.json）
  async function openSandboxGraph(wp) {
    try {
      if (!state.catalog.length) await loadCatalog();
      var d = await EV.api.get('/api/evolve/file' + EV.qs({
        workplace_id: wp.workplace_id, name: wp.name, type: 'graph', filename: 'graph.json'
      }));
      var data = JSON.parse((d && d.content) || '{}');
      loadGraphData(data);
      state.graphName = wp.name;
      state.description = data.description || '';
      state.sandboxCtx = { workplace_id: wp.workplace_id, name: wp.name, raw: data };
      state.dirty = false;
      state.selectedId = null;
      state.selectedEdgeId = null;
      renderAll();
      fitView();
      EV.toast('已载入沙盒产物 ' + wp.name);
    } catch (e) {
      EV.toast('载入沙盒产物失败：' + e.message, true);
    }
  }

  async function openGraph(name) {
    try {
      var data = await EV.api.get('/api/graphs/' + encodeURIComponent(name));
      loadGraphData(data);
      state.graphName = name;
      state.description = data.description || '';
      state.sandboxCtx = null;
      state.dirty = false;
      state.selectedId = null;
      state.selectedEdgeId = null;
      renderAll();
      fitView();
      EV.toast('已加载 ' + name);
    } catch (e) {
      EV.toast('加载图谱失败：' + e.message, true);
    }
  }

  function loadGraphData(data) {
    if (!state.catalog.length) {
      state.nodes = [];
      return;
    }
    state.extras = { env: data.env };
    var rawNodes = data.nodes || [];
    var rawEdges = data.edges || [];
    var autoPos = inferAutoLayout(rawNodes, rawEdges);
    var nodes = [];
    rawNodes.forEach(function (n) {
      var def = defOf(n.type);
      if (!def) return;
      var x, y;
      if (Array.isArray(n.position)) { x = n.position[0]; y = n.position[1]; }
      else if (n.position && n.position.x !== undefined) { x = n.position.x; y = n.position.y; }
      else { var p = autoPos[n.id] || { x: 100, y: 100 }; x = p.x; y = p.y; }
      var cfg = clone(n.config || {});
      // 旧图文件里 task_output 会内嵌导出时派生的 exposed_keys；只有当节点定义本身
      // 不声明该配置项时才剔除，否则会误删 env_loader 自己的 exposed_keys 配置
      var declaresExposedKeys = (def.config || []).some(function (f) { return f.name === 'exposed_keys'; });
      if (!declaresExposedKeys) delete cfg.exposed_keys;
      (def.config || []).forEach(function (f) {
        if (!(f.name in cfg)) cfg[f.name] = f.type === 'list' ? (f.default || []) : f.default;
      });
      nodes.push({ id: n.id, type: n.type, name: n.name || def.name, x: x, y: y, config: cfg });
    });
    state.nodes = nodes;
    state.edges = rawEdges.map(function (e, i) {
      return {
        id: 'e' + i + '_' + e.source + '_' + e.target,
        source: e.source, target: e.target,
        sourceHandle: e.sourceHandle || 'default',
        targetHandle: e.targetHandle || 'default'
      };
    });
  }

  function exportGraph(name, keepIds) {
    var taskInput = null;
    state.nodes.forEach(function (n) { if (n.type === 'task_input') taskInput = n; });
    var globalSchema = {};
    if (taskInput && Array.isArray(taskInput.config.global_vars)) {
      taskInput.config.global_vars.forEach(function (item) {
        var varName = (item && typeof item === 'object') ? (item.name || item.key) : item;
        var varType = (item && typeof item === 'object' && item.type) ? item.type : 'any';
        if (!varName) return;
        globalSchema[varName] = {
          type: varType,
          required: (item && typeof item === 'object' && item.required !== undefined) ? item.required : true,
          description: (item && typeof item === 'object' && item.description) ? item.description : ('动态注入全局参数: ' + varName)
        };
      });
    }
    var idMap = {};
    state.nodes.forEach(function (n) { idMap[n.id] = keepIds ? n.id : n.type + '_' + rand6(); });
    var out = {
      version: '2.0',
      name: name,
      description: state.description || 'PurrCat Web Export - V2',
      global_schema: globalSchema
    };
    if (state.extras && state.extras.env) out.env = state.extras.env;
    out.nodes = state.nodes.map(function (n) {
      var cfg = clone(n.config);
      if (n.type === 'task_output' && Array.isArray(cfg.target_vars)) {
        cfg.exposed_keys = cfg.target_vars.map(function (v) { return (v && typeof v === 'object') ? (v.name || v.key) : v; });
      }
      return { id: idMap[n.id], type: n.type, name: n.name, position: [Math.round(n.x), Math.round(n.y)], config: cfg };
    });
    out.edges = state.edges.map(function (e) {
      return {
        source: idMap[e.source] || e.source,
        target: idMap[e.target] || e.target,
        sourceHandle: e.sourceHandle || 'default',
        targetHandle: e.targetHandle || 'default'
      };
    });
    return out;
  }

  /* ---------------- 校验 ---------------- */
  function validate() {
    var errors = [];
    state.nodes.forEach(function (n) {
      var linked = state.edges.some(function (e) { return e.source === n.id || e.target === n.id; });
      if (!linked) errors.push('节点 [' + n.name + '] 尚未连接任何路径');
    });
    return errors;
  }

  function normalizeType(t) {
    if (!t) return 'any';
    var map = { MessageList: 'list', ToolList: 'list', integer: 'number', float: 'number', LLMResponse: 'object', filepath: 'file', File: 'file' };
    return map[t] || String(t).toLowerCase();
  }
  function isCompatible(a, b) {
    if (a === b) return true;
    var soft = [['jsonstring', 'string'], ['jsonstring', 'any']];
    for (var i = 0; i < soft.length; i++) {
      if ((soft[i][0] === a && soft[i][1] === b) || (soft[i][0] === b && soft[i][1] === a)) return true;
    }
    return false;
  }
  function portTypeOf(node, handleName, dir) {
    var def = defOf(node.type);
    if (!def) return 'any';
    var ports = portList(def, dir, node);
    for (var i = 0; i < ports.length; i++) if (ports[i].name === handleName) return ports[i].type;
    return 'any';
  }
  function hasPath(fromId, toId) {
    // 从 toId 出发能否走回 fromId（形成环）
    var seen = {};
    var stack = [toId];
    while (stack.length) {
      var cur = stack.pop();
      if (cur === fromId) return true;
      if (seen[cur]) continue;
      seen[cur] = 1;
      state.edges.forEach(function (e) { if (e.source === cur) stack.push(e.target); });
    }
    return false;
  }

  /* ---------------- 视图 ---------------- */
  function applyView() {
    worldEl.style.transform = 'translate(' + state.view.x + 'px,' + state.view.y + 'px) scale(' + state.view.s + ')';
  }

  function toWorld(clientX, clientY) {
    var r = canvasEl.getBoundingClientRect();
    return { x: (clientX - r.left - state.view.x) / state.view.s, y: (clientY - r.top - state.view.y) / state.view.s };
  }

  function portCenter(el) {
    var wr = worldEl.getBoundingClientRect();
    var r = el.getBoundingClientRect();
    return { x: (r.left + r.width / 2 - wr.left) / state.view.s, y: (r.top + r.height / 2 - wr.top) / state.view.s };
  }

  function fitView() {
    if (!state.nodes.length) {
      state.view = { x: 60, y: 60, s: 1 };
      applyView();
      drawEdges();
      syncZoomPct();
      return;
    }
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    state.nodes.forEach(function (n) {
      minX = Math.min(minX, n.x); minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + 240); maxY = Math.max(maxY, n.y + 200);
    });
    var cw = canvasEl.clientWidth || 800, ch = canvasEl.clientHeight || 600;
    var pad = 60;
    var s = Math.min((cw - pad * 2) / Math.max(maxX - minX, 1), (ch - pad * 2) / Math.max(maxY - minY, 1), 1);
    s = Math.max(0.25, Math.min(s, 1.2));
    state.view.s = s;
    state.view.x = (cw - (maxX - minX) * s) / 2 - minX * s;
    state.view.y = (ch - (maxY - minY) * s) / 2 - minY * s;
    applyView();
    drawEdges();
    syncZoomPct();
  }

  /* ---------------- 渲染 ---------------- */
  function renderSide() {
    sideBodyEl.innerHTML = '';

    // 最上方：新建画布
    var newBtn = EV.el('button', 'btn sm');
    newBtn.innerHTML = EV.icon('plus', 13);
    newBtn.appendChild(EV.el('span', null, '新建画布'));
    newBtn.style.margin = '2px 4px 8px';
    newBtn.style.width = 'calc(100% - 8px)';
    newBtn.style.justifyContent = 'center';
    newBtn.onclick = function () {
      state.nodes = []; state.edges = []; state.selectedId = null; state.selectedEdgeId = null;
      state.graphName = ''; state.description = ''; state.extras = null; state.dirty = false;
      state.sandboxCtx = null;
      renderAll(); fitView();
    };
    sideBodyEl.appendChild(newBtn);

    // 抽屉 1：沙盒内（Graph 工厂加工中的产物）
    var sandboxDrawer = EV.drawer(
      '沙盒内', state.workplaces.length, state.drawers.sandbox,
      function (open) { state.drawers.sandbox = open; },
      function (body) { renderSandboxList(body); }
    );
    sideBodyEl.appendChild(sandboxDrawer);

    // 抽屉 2：打开已有图谱
    sideBodyEl.appendChild(EV.drawer(
      '打开已有图谱', state.files.length, state.drawers.files,
      function (open) { state.drawers.files = open; },
      function (body) {
        if (!state.files.length) {
          body.appendChild(EV.el('div', 'hint', '暂无已保存的图谱。'));
          return;
        }
        state.files.forEach(function (f) {
          var it = EV.el('div', 'item' + (state.graphName === f.name ? ' on' : ''));
          var nm = EV.el('div', 'item-name');
          nm.innerHTML = EV.icon('graph', 14);
          nm.appendChild(EV.el('span', 'nm', f.name));
          it.appendChild(nm);
          it.onclick = function () { openGraph(f.name); };
          body.appendChild(it);
        });
      }
    ));

    // 抽屉 3：添加节点
    sideBodyEl.appendChild(EV.drawer(
      '添加节点', state.catalog.length, state.drawers.nodes,
      function (open) { state.drawers.nodes = open; },
      function (body) {
        if (!state.catalog.length) {
          body.appendChild(EV.el('div', 'hint', '正在加载节点目录…'));
          return;
        }
        state.catalog.forEach(function (def) {
          var it = EV.el('div', 'item');
          var nm = EV.el('div', 'item-name');
          var dot = EV.el('span');
          dot.style.width = '9px'; dot.style.height = '9px';
          dot.style.borderRadius = '3px'; dot.style.flex = 'none';
          dot.style.background = def.color || '#9aa5b1';
          nm.appendChild(dot);
          nm.appendChild(EV.el('span', 'nm', def.name));
          it.appendChild(nm);
          if (def.description) it.appendChild(EV.el('div', 'item-sub', def.description));
          it.title = '点击添加到画布中心，或直接拖拽进画布';
          it.onclick = function () { addNode(def.type); };
          // 支持从左侧列表拖拽节点进画布
          it.draggable = true;
          it.addEventListener('dragstart', function (e) {
            e.dataTransfer.effectAllowed = 'copy';
            e.dataTransfer.setData('text/plain', def.type);
          });
          body.appendChild(it);
        });
      }
    ));
  }

  // 画布左上角的节点面板（默认折叠，展开后可从列表拖节点进画布）
  function renderPalette() {
    if (!paletteBodyEl) return;
    paletteBodyEl.innerHTML = '';
    if (!state.catalog.length) {
      paletteBodyEl.appendChild(EV.el('div', 'g-pal-empty', '正在加载节点目录…'));
      return;
    }
    state.catalog.forEach(function (def) {
      var it = EV.el('div', 'g-pal-item');
      var dot = EV.el('span', 'g-pal-dot');
      dot.style.background = def.color || '#9aa5b1';
      it.appendChild(dot);
      it.appendChild(EV.el('span', 'nm', def.name));
      it.title = '点击添加到画布中心，或直接拖拽进画布';
      it.draggable = true;
      it.onclick = function () { addNode(def.type); };
      it.addEventListener('dragstart', function (e) {
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('text/plain', def.type);
      });
      paletteBodyEl.appendChild(it);
    });
  }

  function togglePalette() {
    if (!palettePanel) return;
    var open = palettePanel.style.display === 'none';
    palettePanel.style.display = open ? 'flex' : 'none';
    var btn = palettePanel.parentNode.querySelector('.g-pal-toggle');
    if (btn) btn.classList.toggle('on', open);
  }

  function syncZoomPct() {
    if (zoomPctEl) zoomPctEl.textContent = Math.round(state.view.s * 100) + '%';
  }

  // 沙盒内：列出 Graph 工厂加工中的产物（点击直接载入可视化画布编辑）
  function renderSandboxList(body) {
    if (!state.workplaces.length) {
      body.appendChild(EV.el('div', 'hint', '沙盒内暂无正在加工的 Graph 产物。'));
      return;
    }
    state.workplaces.forEach(function (wp) {
      var on = state.sandboxCtx && state.sandboxCtx.workplace_id === wp.workplace_id;
      var item = EV.el('div', 'item' + (on ? ' on' : ''));
      var nm = EV.el('div', 'item-name');
      nm.innerHTML = EV.icon('graph', 14);
      nm.appendChild(EV.el('span', 'nm', wp.name));
      item.appendChild(nm);
      item.appendChild(EV.el('div', 'item-sub', '沙盒 ' + wp.workplace_id));
      var x = EV.el('button', 'item-x');
      x.title = '清理沙盒';
      x.innerHTML = EV.icon('trash', 14);
      x.onclick = function (e) { e.stopPropagation(); deleteWorkplace(wp); };
      item.appendChild(x);
      item.title = '在画布中打开沙盒产物，编辑后保存回写 graph.json';
      item.onclick = function () { openSandboxGraph(wp); };
      body.appendChild(item);
    });
  }

  function addNode(type, at) {
    var def = defOf(type);
    if (!def) return;
    var cfg = {};
    (def.config || []).forEach(function (f) {
      cfg[f.name] = f.type === 'list' ? clone(f.default || []) : (f.default === undefined ? '' : f.default);
    });
    var pos;
    if (at) {
      pos = at;   // 拖拽落点
    } else {
      var center = toWorld(
        canvasEl.getBoundingClientRect().left + canvasEl.clientWidth / 2,
        canvasEl.getBoundingClientRect().top + canvasEl.clientHeight / 2
      );
      // 稍微错开，避免重叠
      var off = state.nodes.length % 6;
      pos = { x: center.x + off * 24, y: center.y + off * 24 };
    }
    var node = {
      id: type + '_' + rand6(),
      type: type,
      name: def.name,
      x: Math.round(pos.x - 120),
      y: Math.round(pos.y - 60),
      config: cfg
    };
    state.nodes.push(node);
    state.selectedId = node.id;
    state.selectedEdgeId = null;
    state.dirty = true;
    renderAll();
    paintSelection();
  }

  function renderCanvas() {
    // 节点
    Array.prototype.slice.call(worldEl.querySelectorAll('.g-node')).forEach(function (n) { n.remove(); });
    state.nodes.forEach(function (n) {
      var def = defOf(n.type);
      var el = EV.el('div', 'g-node');
      el.dataset.id = n.id;
      el.style.left = n.x + 'px';
      el.style.top = n.y + 'px';

      var head = EV.el('div', 'g-node-h');
      var dot = EV.el('span', 'g-node-dot');
      dot.style.background = (def && def.color) || '#9aa5b1';
      head.appendChild(dot);
      var nameEl = EV.el('span', 'nm', n.name);
      nameEl.style.flex = '1';
      head.appendChild(nameEl);
      // 重命名入口（头部 pointerdown 已用于拖拽，故用独立按钮而非双击）
      var editBtn = EV.el('button', 'g-node-edit');
      editBtn.innerHTML = EV.icon('edit', 12);
      editBtn.title = '重命名';
      editBtn.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
      editBtn.onclick = function (e) { e.stopPropagation(); startRename(n, nameEl, head); };
      head.appendChild(editBtn);
      // 删除节点入口（连带其两端连线），同样常驻头部右上角
      var delBtn = EV.el('button', 'g-node-del');
      delBtn.innerHTML = EV.icon('trash', 12);
      delBtn.title = '删除节点';
      delBtn.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
      delBtn.onclick = function (e) { e.stopPropagation(); deleteNode(n.id); };
      head.appendChild(delBtn);
      head.style.overflow = 'hidden';
      nameEl.style.overflow = 'hidden';
      nameEl.style.textOverflow = 'ellipsis';
      nameEl.style.whiteSpace = 'nowrap';
      el.appendChild(head);

      // 配置项直接落在节点卡片上编辑（对齐完整模式 CustomNode）
      renderCfgInto(el, n, def);
      renderPortsInto(n, def, el);

      head.addEventListener('pointerdown', function (e) { startNodeDrag(e, n, el); });
      el.addEventListener('pointerdown', function () {
        state.selectedId = n.id;
        state.selectedEdgeId = null;
        paintSelection();
      });
      worldEl.appendChild(el);
    });
    drawEdges();
  }

  // 删除节点：连带其两端连线一并移除，并清理已失效的选中态
  function deleteNode(id) {
    state.nodes = state.nodes.filter(function (n) { return n.id !== id; });
    state.edges = state.edges.filter(function (e) { return e.source !== id && e.target !== id; });
    if (state.selectedId === id) state.selectedId = null;
    if (state.selectedEdgeId && !state.edges.some(function (e) { return e.id === state.selectedEdgeId; })) {
      state.selectedEdgeId = null;
    }
    state.dirty = true;
    renderCanvas();
    renderToolbar();
  }

  // 头部名称：就地改名
  function startRename(node, nameEl, head) {
    var inp = EV.el('input', 'g-node-rename');
    inp.value = node.name;
    inp.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
    nameEl.style.display = 'none';
    head.appendChild(inp);
    inp.focus();
    inp.select();
    var done = false;
    function commit(save) {
      if (done) return;
      done = true;
      if (save) {
        var v = inp.value.trim();
        if (v && v !== node.name) { node.name = v; state.dirty = true; }
      }
      inp.remove();
      nameEl.textContent = node.name;
      nameEl.style.display = '';
      renderToolbar();
    }
    inp.onblur = function () { commit(true); };
    inp.onkeydown = function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(true); }
      else if (e.key === 'Escape') { e.preventDefault(); commit(false); }
    };
  }

  // 卡片配置区：非列表项逐一渲染为内联控件；未被端口区 watch_config 消费的列表项
  // （如 skill_info / mcp_info 的知识包）也在卡片内提供条目与「+」新增入口
  function renderCfgInto(nodeEl, node, def) {
    var old = nodeEl.querySelector('.g-cfg');
    if (old) old.remove();
    var cfgEl = EV.el('div', 'g-cfg');
    var listBacked = {};
    portList(def, 'in', node).concat(portList(def, 'out', node)).forEach(function (p) {
      if (p.listBacked && p.field) listBacked[p.field.name] = 1;
    });
    ((def && def.config) || []).forEach(function (f) {
      if (f.type === 'list') {
        if (!listBacked[f.name]) cfgEl.appendChild(configListField(node, f, nodeEl, def));
        return;
      }
      cfgEl.appendChild(inlineField(node, f));
    });
    if (!cfgEl.childNodes.length) return;
    var head = nodeEl.querySelector('.g-node-h');
    nodeEl.insertBefore(cfgEl, head.nextSibling);
    Array.prototype.slice.call(cfgEl.querySelectorAll('textarea')).forEach(autoGrow);
  }

  // 卡片内列表配置：展示已添加条目（可删），「+」复用统一的新增弹层
  function configListField(node, f, nodeEl, def) {
    var wrap = EV.el('div', 'g-cfgf g-cfglist');
    wrap.appendChild(EV.el('span', 'g-cfgl', f.label || f.name));
    var items = Array.isArray(node.config[f.name]) ? node.config[f.name] : [];
    if (!items.length) {
      wrap.appendChild(EV.el('div', 'g-cfgempty', '尚未添加，点击下方 + 新增'));
    }
    items.forEach(function (it, idx) {
      var nm = (it && typeof it === 'object') ? (it.name || it.key) : it;
      var desc = (it && typeof it === 'object' && it.description) ? String(it.description) : '';
      var row = EV.el('div', 'g-cfgitem');
      row.title = desc || String(nm || '');
      row.appendChild(EV.el('span', 'nm', nm ? String(nm) : '（空）'));
      var del = EV.el('button', 'ibtn g-cfgdel');
      del.type = 'button';
      del.innerHTML = EV.icon('trash', 11);
      del.title = '删除该条目';
      del.onclick = function (ev) {
        ev.stopPropagation();
        items.splice(idx, 1);
        state.dirty = true;
        renderCfgInto(nodeEl, node, def);
        refreshConfigDeps(node);
      };
      row.appendChild(del);
      wrap.appendChild(row);
    });
    var add = EV.el('button', 'ibtn g-ladd');
    add.type = 'button';
    add.innerHTML = EV.icon('plus', 12);
    add.title = '新增一个「' + (f.label || f.name) + '」';
    add.onclick = function (ev) {
      ev.stopPropagation();
      addListItem(node, f, function () {
        renderCfgInto(nodeEl, node, def);
        refreshConfigDeps(node);
      });
    };
    wrap.appendChild(add);
    return wrap;
  }

  function inlineField(node, f) {
    var wrap = EV.el('div', 'g-cfgf');
    wrap.appendChild(EV.el('span', 'g-cfgl', f.label || f.name));
    var expBtn = null;
    var ctrl;

    if (f.type === 'select') {
      ctrl = EV.el('select', 'g-cfgin');
      ctrl.dataset.cfg = f.name;
      var empty = EV.el('option', null, '（未设置）');
      empty.value = '';
      ctrl.appendChild(empty);
      (f.options || []).forEach(function (o) {
        var val = (o && typeof o === 'object') ? (o.value !== undefined ? o.value : o) : o;
        var lab = (o && typeof o === 'object' && o.label) ? o.label : val;
        var op = EV.el('option', null, String(lab));
        op.value = String(val);
        ctrl.appendChild(op);
      });
      var cv = node.config[f.name];
      ctrl.value = cv === undefined || cv === null ? '' : String(cv);
      ctrl.onchange = function () {
        if (ctrl.value === '') delete node.config[f.name];
        else node.config[f.name] = ctrl.value;
        state.dirty = true;
        refreshConfigDeps(node);
      };
    } else {
      ctrl = EV.el('textarea', 'g-cfgin mono');
      ctrl.dataset.cfg = f.name;
      ctrl.rows = 1;
      ctrl.spellcheck = false;
      var curv = node.config[f.name];
      ctrl.value = curv === undefined || curv === null ? '' : (typeof curv === 'string' ? curv : JSON.stringify(curv, null, 2));
      ctrl.oninput = function () {
        node.config[f.name] = ctrl.value;
        state.dirty = true;
        autoGrow(ctrl);
        // 动态端口（如模板渲染器按 {{变量}} 生成输入端口）随输入实时重算
        debouncedConfigDeps(node);
      };
      ctrl.onchange = function () { refreshConfigDeps(node); };
      // 长内容在卡片上不易读，悬浮出现放大按钮，改到大窗口编辑
      expBtn = EV.el('button', 'g-cfgexp');
      expBtn.type = 'button';
      expBtn.innerHTML = EV.icon('expand', 13);
      expBtn.title = '在放大窗口中编辑';
      expBtn.onpointerdown = function (e) { e.stopPropagation(); };
      expBtn.onclick = function (e) {
        e.stopPropagation();
        e.preventDefault();
        openBigEditor(node, f, wrap);
      };
    }
    wrap.appendChild(ctrl);
    if (expBtn) wrap.appendChild(expBtn);
    return wrap;
  }

  // 放大编辑：大文本弹窗里改配置（卡片输入框只做速览）
  function openBigEditor(node, f, scopeEl) {
    var ta = EV.el('textarea', 'g-bigta mono');
    ta.spellcheck = false;
    var curv = node.config[f.name];
    ta.value = curv === undefined || curv === null ? '' : (typeof curv === 'string' ? curv : JSON.stringify(curv, null, 2));
    ta.oninput = function () {
      node.config[f.name] = ta.value;
      state.dirty = true;
      setCfgValue(scopeEl, f.name, ta.value);   // 回填卡片上的同名控件（未在编辑时）
      // 弹窗内持续输入时不整画布重绘，避免丢失焦点
      debouncedConfigDeps(node);
    };
    EV.modal({
      title: (f.label || f.name) + ' · ' + node.name,
      node: ta,
      width: '720px',
      onClose: function () {
        var c = scopeEl.querySelector('[data-cfg="' + cssEsc(f.name) + '"]');
        if (c && c.tagName === 'TEXTAREA') autoGrow(c);
        refreshConfigDeps(node);
      }
    });
  }

  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.max(26, ta.scrollHeight) + 'px';
  }

  // 把值同步到另一个编辑面（卡片 ↔ 放大弹窗），不打断正在输入的控件
  function setCfgValue(scopeEl, name, value) {
    if (!scopeEl) return;
    var c = scopeEl.querySelector('[data-cfg="' + cssEsc(name) + '"]');
    if (!c || c === document.activeElement) return;
    c.value = value === undefined || value === null ? '' : String(value);
  }

  var cfgDepsTimer = null;
  function debouncedConfigDeps(node) {
    if (cfgDepsTimer) clearTimeout(cfgDepsTimer);
    cfgDepsTimer = setTimeout(function () { cfgDepsTimer = null; refreshConfigDeps(node); }, 220);
  }

  // 配置变化后：重绘端口（动态端口按新值生成/回收）+ 刷新下游与连线
  function refreshConfigDeps(node) {
    var el = worldEl.querySelector('.g-node[data-id="' + cssEsc(node.id) + '"]');
    if (el) renderPorts(node, el);
    refreshDownstream(node);
    renderToolbar();
  }

  function portEl(node, port, dir) {
    var row = EV.el('div', 'g-port ' + (dir === 'in' ? 'l' : 'r'));
    if (dir === 'in') {
      var d1 = dotEl(node, port, dir);
      row.appendChild(d1);
      row.appendChild(EV.el('span', 'nm', port.name));
    } else {
      row.appendChild(EV.el('span', 'nm', port.name));
      var d2 = dotEl(node, port, dir);
      row.appendChild(d2);
    }
    row.title = port.name + ' : ' + port.type + (port.dynamic ? '（动态）' : '');
    return row;
  }
  function dotEl(node, port, dir) {
    var d = EV.el('span', 'dot');
    d.dataset.node = node.id;
    d.dataset.port = port.name;
    d.dataset.dir = dir;
    d.dataset.type = port.type;
    if (dir === 'out') {
      d.addEventListener('pointerdown', function (e) {
        e.stopPropagation();
        e.preventDefault();
        startLink(e, node, port);
      });
    }
    return d;
  }

  function paintSelection() {
    Array.prototype.slice.call(worldEl.querySelectorAll('.g-node')).forEach(function (el) {
      el.classList.toggle('on', el.dataset.id === state.selectedId);
    });
    Array.prototype.slice.call(svgEl.querySelectorAll('.g-edge-group')).forEach(function (g) {
      g.querySelector('.g-edge').classList.toggle('on', g.dataset.id === state.selectedEdgeId);
    });
  }

  /* ---------------- 连线绘制 ---------------- */
  function drawEdges() {
    if (!worldEl) return;
    svgEl.innerHTML = '';
    state.edges.forEach(function (e) {
      var sEl = worldEl.querySelector('.g-port .dot[data-node="' + cssEsc(e.source) + '"][data-port="' + cssEsc(e.sourceHandle) + '"][data-dir="out"]');
      var tEl = worldEl.querySelector('.g-port .dot[data-node="' + cssEsc(e.target) + '"][data-port="' + cssEsc(e.targetHandle) + '"][data-dir="in"]');
      if (!sEl || !tEl) return;
      var a = portCenter(sEl), b = portCenter(tEl);
      var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'g-edge-group');
      g.dataset.id = e.id;
      var hit = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      hit.setAttribute('class', 'g-edge-hit');
      hit.setAttribute('d', curve(a, b));
      hit.addEventListener('click', function (ev) {
        ev.stopPropagation();
        state.selectedEdgeId = e.id;
        state.selectedId = null;
        drawEdges();          // 重绘以在连线中点生成 ✕ 删除按钮
        paintSelection();
      });
      var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('class', 'g-edge');
      p.setAttribute('d', curve(a, b));
      g.appendChild(hit);
      g.appendChild(p);
      if (state.selectedEdgeId === e.id) {
        var bx = (a.x + b.x) / 2, by = (a.y + b.y) / 2;
        var del = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', bx); circle.setAttribute('cy', by); circle.setAttribute('r', 9);
        circle.setAttribute('fill', '#fff');
        circle.setAttribute('stroke', '#16191d');
        circle.setAttribute('stroke-width', '1.2');
        circle.style.cursor = 'pointer';
        circle.style.pointerEvents = 'all';
        circle.addEventListener('click', function (ev) {
          ev.stopPropagation();
          state.edges = state.edges.filter(function (x) { return x.id !== e.id; });
          state.selectedEdgeId = null;
          state.dirty = true;
          renderAll();
        });
        var txt = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        txt.setAttribute('d', 'M' + (bx - 3.5) + ' ' + (by - 3.5) + ' l7 7 M' + (bx + 3.5) + ' ' + (by - 3.5) + ' l-7 7');
        txt.setAttribute('stroke', '#16191d');
        txt.setAttribute('stroke-width', '1.4');
        txt.setAttribute('fill', 'none');
        txt.style.pointerEvents = 'none';
        del.appendChild(circle);
        del.appendChild(txt);
        g.appendChild(del);
      }
      svgEl.appendChild(g);
    });
    if (linkPreview) {
      var p2 = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p2.setAttribute('class', 'g-edge');
      p2.setAttribute('stroke-dasharray', '5 4');
      p2.setAttribute('d', curve(linkPreview.a, linkPreview.b));
      svgEl.appendChild(p2);
    }
  }
  function curve(a, b) {
    var dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
    return 'M' + a.x + ' ' + a.y + ' C' + (a.x + dx) + ' ' + a.y + ', ' + (b.x - dx) + ' ' + b.y + ', ' + b.x + ' ' + b.y;
  }
  function cssEsc(s) {
    return String(s).replace(/["\\]/g, '\\$&');
  }

  /* ---------------- 交互 ---------------- */
  function startNodeDrag(e, node, el) {
    if (e.button !== 0) return;
    e.preventDefault();
    try { el.setPointerCapture(e.pointerId); } catch (err) { /* noop */ }
    var start = { mx: e.clientX, my: e.clientY, x: node.x, y: node.y };
    drag = { kind: 'node', node: node, el: el, start: start };
    el.style.cursor = 'grabbing';
    var move = function (ev) {
      node.x = Math.round(start.x + (ev.clientX - start.mx) / state.view.s);
      node.y = Math.round(start.y + (ev.clientY - start.my) / state.view.s);
      el.style.left = node.x + 'px';
      el.style.top = node.y + 'px';
      drawEdges();
    };
    var up = function () {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      el.style.cursor = '';
      state.dirty = true;
      drag = null;
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
  }

  function startLink(e, node, port) {
    var startEl = e.target;
    var a = portCenter(startEl);
    linkPreview = { a: a, b: a, from: node, port: port };
    var move = function (ev) {
      var w = toWorld(ev.clientX, ev.clientY);
      linkPreview.b = w;
      drawEdges();
    };
    var up = function (ev) {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      var target = document.elementFromPoint(ev.clientX, ev.clientY);
      linkPreview = null;
      if (target && target.classList && target.classList.contains('dot') && target.dataset.dir === 'in') {
        tryConnect(node.id, port.name, target.dataset.node, target.dataset.port);
      }
      drawEdges();
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
  }

  function tryConnect(sourceId, sourceHandle, targetId, targetHandle) {
    if (sourceId === targetId) { EV.toast('不能连接到自身', true); return; }
    if (hasPath(sourceId, targetId)) { EV.toast('禁止形成循环连线！', true); return; }
    var sNode = nodeById(sourceId), tNode = nodeById(targetId);
    if (!sNode || !tNode) return;
    var st = portTypeOf(sNode, sourceHandle, 'out');
    var tt = portTypeOf(tNode, targetHandle, 'in');
    var sNorm = normalizeType(st), tNorm = normalizeType(tt);
    if (sNorm !== 'any' && tNorm !== 'any' && !isCompatible(sNorm, tNorm)) {
      EV.toast('类型不兼容：无法将 [' + st + '] 连到 [' + tt + ']', true);
      return;
    }
    state.edges = state.edges.filter(function (x) {
      return !(x.target === targetId && x.targetHandle === targetHandle);
    });
    state.edges.push({
      id: 'e' + rand6(),
      source: sourceId, target: targetId,
      sourceHandle: sourceHandle, targetHandle: targetHandle
    });
    state.dirty = true;
    renderAll();
    paintSelection();
  }

  function bindCanvas() {
    canvasEl.addEventListener('pointerdown', function (e) {
      if (e.target !== canvasEl && e.target !== svgEl && e.target !== worldEl) return;
      state.selectedId = null;
      state.selectedEdgeId = null;
      drawEdges();            // 取消连线选中后同步移除 ✕ 删除按钮
      paintSelection();
      var start = { mx: e.clientX, my: e.clientY, x: state.view.x, y: state.view.y };
      canvasEl.style.cursor = 'grabbing';
      var move = function (ev) {
        state.view.x = start.x + (ev.clientX - start.mx);
        state.view.y = start.y + (ev.clientY - start.my);
        applyView();
      };
      var up = function () {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        canvasEl.style.cursor = '';
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
    });

    canvasEl.addEventListener('wheel', function (e) {
      if (e.target.closest && e.target.closest('.g-pal')) return;   // 面板内滚动交给原生
      e.preventDefault();
      var r = canvasEl.getBoundingClientRect();
      var mx = e.clientX - r.left, my = e.clientY - r.top;
      var wx = (mx - state.view.x) / state.view.s;
      var wy = (my - state.view.y) / state.view.s;
      var factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      var ns = Math.max(0.2, Math.min(2.5, state.view.s * factor));
      state.view.s = ns;
      state.view.x = mx - wx * ns;
      state.view.y = my - wy * ns;
      applyView();
      drawEdges();
      syncZoomPct();
    }, { passive: false });

    window.addEventListener('resize', EV.debounce(function () { drawEdges(); }, 120));

    // 从左侧「添加节点」抽屉拖拽入画布
    canvasEl.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    });
    canvasEl.addEventListener('drop', function (e) {
      e.preventDefault();
      var type = e.dataTransfer.getData('text/plain');
      if (!type || !defOf(type)) return;
      addNode(type, toWorld(e.clientX, e.clientY));
    });
  }

  // 配置数据变化后：把 node.config 回填到卡片控件（未在编辑时），再重绘端口/下游
  function refreshSummary(node) {
    var el = worldEl.querySelector('.g-node[data-id="' + cssEsc(node.id) + '"]');
    ((defOf(node.type) || {}).config || []).forEach(function (f) {
      if (f.type === 'list') return;
      var v = node.config[f.name];
      setCfgValue(el, f.name, v === undefined || v === null ? '' : (typeof v === 'string' ? v : JSON.stringify(v, null, 2)));
    });
    refreshConfigDeps(node);
  }

  // 上游内容变了（如「自定义输入」正文），下游节点按正则推导的动态端口要跟着重算
  // —— 对齐完整模式 CustomNode 订阅全量 nodes 的联动刷新
  function refreshDownstream(node) {
    var ids = {};
    state.edges.forEach(function (e) { if (e.source === node.id) ids[e.target] = 1; });
    Object.keys(ids).forEach(function (id) {
      var target = nodeById(id);
      if (!target) return;
      var el = worldEl.querySelector('.g-node[data-id="' + cssEsc(id) + '"]');
      if (el) renderPorts(target, el);
    });
  }

  function renderPorts(node, nodeEl) {
    renderPortsInto(node, defOf(node.type), nodeEl);
  }

  function renderPortsInto(node, def, nodeEl) {
    var old = nodeEl.querySelector('.g-ports');
    if (old) old.remove();
    var ports = EV.el('div', 'g-ports');
    var left = EV.el('div', 'g-pcol');
    var right = EV.el('div', 'g-pcol r');
    var listsIn = [], listsOut = [];
    portList(def, 'in', node).forEach(function (p) {
      if (p.listBacked) { listsIn.push(p); return; }
      left.appendChild(portEl(node, p, 'in'));
    });
    portList(def, 'out', node).forEach(function (p) {
      if (p.listBacked) { listsOut.push(p); return; }
      right.appendChild(portEl(node, p, 'out'));
    });
    // 列表型动态端口（全局输入/输出、环境变量、JSON 键值…）：列表每一项占一行并带端口点，
    // 行尾提供「+」新增入口 —— 对齐完整模式卡片上 list 项直接出引脚 + ADD 按钮的交互
    listsIn.forEach(function (p) { left.appendChild(listBlock(node, p)); });
    listsOut.forEach(function (p) { right.appendChild(listBlock(node, p)); });
    ports.appendChild(left);
    ports.appendChild(right);
    nodeEl.appendChild(ports);
    drawEdges();
  }

  function listBlock(node, p) {
    var block = EV.el('div', 'g-lblock' + (p.dir === 'out' ? ' r' : ''));
    // 兜底：动态端口未携带 field 时退化为「以端口名当配置项名」，绝不让属性读取抛错中断整张图的加载
    var field = p.field || { name: p.name, label: p.name, item_schema: [] };
    var cfg = node.config || {};
    var items = Array.isArray(cfg[field.name]) ? cfg[field.name] : [];
    items.forEach(function (it) {
      var nm = (it && typeof it === 'object') ? (it.name || it.key) : it;
      if (!nm) return;
      var tp = (it && typeof it === 'object' && it.type) ? it.type : 'any';
      var row = portEl(node, { name: String(nm), type: tp, dynamic: true }, p.dir);
      row.classList.add('g-lrow');
      row.title = String(nm) + ' : ' + tp + '　来自「' + (field.label || field.name) + '」';
      block.appendChild(row);
    });
    var add = EV.el('button', 'ibtn g-ladd');
    add.innerHTML = EV.icon('plus', 12);
    add.title = '新增一个「' + (field.label || field.name) + '」端口';
    add.onclick = function (ev) { ev.stopPropagation(); addListItem(node, field); };
    block.appendChild(add);
    return block;
  }

  // 新增列表项 = 新增一个动态端口。按 item_schema 生成表单弹层（自由文本型列表则直接输入内容）
  function addListItem(node, field, onAdded) {
    var schema = field.item_schema || [];
    var vals = {};
    schema.forEach(function (sub) {
      if (!sub.name) return;
      vals[sub.name] = sub.default !== undefined ? sub.default : (sub.type === 'boolean' ? false : '');
    });
    var freeText = '';

    var wrap = EV.el('div');
    if (!schema.length) {
      var ta = EV.el('textarea', 'textarea mono');
      ta.rows = 3;
      ta.placeholder = '输入内容，内容本身即为端口名';
      ta.oninput = function () { freeText = ta.value; };
      wrap.appendChild(ta);
      wrap.appendChild(EV.el('div', 'hint', '例如：user_query'));
    } else {
      schema.forEach(function (sub) {
        var f = EV.el('div', 'field');
        f.appendChild(EV.el('label', null, sub.label || sub.name));
        if (sub.type === 'boolean') {
          var cb = EV.el('input');
          cb.type = 'checkbox';
          cb.checked = !!vals[sub.name];
          cb.onchange = function () { vals[sub.name] = cb.checked; };
          f.appendChild(cb);
        } else {
          var inp = EV.el('input', 'input');
          inp.value = vals[sub.name] === undefined || vals[sub.name] === null ? '' : String(vals[sub.name]);
          inp.placeholder = sub.label || sub.name;
          inp.oninput = function () { vals[sub.name] = inp.value; };
          f.appendChild(inp);
        }
        wrap.appendChild(f);
      });
    }

    EV.modal({
      title: '新增「' + (field.label || field.name) + '」',
      width: '420px',
      node: wrap,
      actions: [
        { label: '取消' },
        {
          label: '添加', kind: 'primary',
          onClick: function (h) {
            var item;
            if (!schema.length) {
              var txt = freeText.trim();
              if (!txt) { EV.toast('内容不能为空', true); return; }
              item = txt;
            } else {
              var nm = vals.name === undefined || vals.name === null ? '' : String(vals.name).trim();
              if (!nm) { EV.toast('请填写变量名', true); return; }
              item = {};
              Object.keys(vals).forEach(function (k) { item[k] = vals[k]; });
              item.name = nm;
              if (item.type === '' || item.type === undefined) delete item.type;
            }
            if (!Array.isArray(node.config[field.name])) node.config[field.name] = [];
            var portName = (item && typeof item === 'object') ? item.name : item;
            var exists = node.config[field.name].some(function (it) {
              return ((it && typeof it === 'object') ? (it.name || it.key) : it) === portName;
            });
            if (exists) { EV.toast('已存在同名条目：' + portName, true); return; }
            node.config[field.name].push(item);
            state.dirty = true;
            if (onAdded) onAdded();
            else refreshSummary(node);
            h.close();
          }
        }
      ]
    });
  }

  /* ---------------- 工具栏 ---------------- */
  function renderToolbar() {
    toolbarEl.innerHTML = '';
    var readonly = state.graphName === 'default' && !state.sandboxCtx;
    if (state.dirty) toolbarEl.appendChild(EV.el('span', 'chip warn', '未保存'));
    if (readonly) toolbarEl.appendChild(EV.el('span', 'chip', '内置图 · 只读'));
    toolbarEl.appendChild(EV.el('span', 'spacer'));

    function tbtn(icon, title, fn, cls) {
      var b = EV.el('button', 'ibtn' + (cls ? ' ' + cls : ''));
      b.innerHTML = EV.icon(icon, 14);
      b.title = title;
      b.onclick = fn;
      toolbarEl.appendChild(b);
      return b;
    }
    tbtn('layout', '自动布局（拓扑分层）', function () {
      var pos = inferAutoLayout(state.nodes, state.edges);
      state.nodes.forEach(function (n) {
        if (pos[n.id]) { n.x = pos[n.id].x; n.y = pos[n.id].y; }
      });
      state.dirty = true;
      renderCanvas();
      paintSelection();
      fitView();
      EV.toast('已重新自动布局');
    });
    tbtn('check', '校验画布', function () {
      var errors = validate();
      if (errors.length) errors.forEach(function (e) { EV.toast(e, true); });
      else EV.toast('校验通过！工作流结构合法。');
    });

    var save = EV.el('button', 'btn primary');
    save.innerHTML = EV.icon('save', 14);
    save.appendChild(EV.el('span', null, '保存'));
    save.onclick = saveGraph;
    if (readonly) {
      save.disabled = true;
      save.title = 'default 是内置图，不能保存；请修改仓库模板';
    }
    toolbarEl.appendChild(save);
  }

  function zoomBy(f) {
    var cw = canvasEl.clientWidth / 2, ch = canvasEl.clientHeight / 2;
    var wx = (cw - state.view.x) / state.view.s;
    var wy = (ch - state.view.y) / state.view.s;
    var ns = Math.max(0.2, Math.min(2.5, state.view.s * f));
    state.view.s = ns;
    state.view.x = cw - wx * ns;
    state.view.y = ch - wy * ns;
    applyView();
    drawEdges();
    syncZoomPct();
  }

  async function saveGraph() {
    // default 是随包分发的内置图，启动时会按模板修复，画布只读。
    if (state.graphName === 'default' && !state.sandboxCtx) {
      EV.toast('default 是内置图，不能保存；请修改仓库模板', true);
      return;
    }
    var errors = validate();
    if (errors.length) {
      EV.toast(errors.join('\n'), true);
      var go = await EV.confirm({
        title: '校验未通过',
        message: errors.join('\n') + '\n\n存在未连接任何路径的节点，仍要保存吗？',
        okLabel: '仍要保存'
      });
      if (!go) return;
    }

    // 沙盒模式：保持名称与文件夹一致，直接把编辑结果回写沙盒 graph.json
    if (state.sandboxCtx) {
      var ctx = state.sandboxCtx;
      try {
        var g = exportGraph(ctx.name, true);
        if (ctx.raw) g = Object.assign({}, ctx.raw, g);   // 保留 description-zh / core 等未在画布中编辑的字段
        await EV.api.put('/api/evolve/file' + EV.qs({
          workplace_id: ctx.workplace_id, name: ctx.name, type: 'graph', filename: 'graph.json'
        }), { content: JSON.stringify(g, null, 2) });
        state.graphName = ctx.name;
        state.dirty = false;
        renderAll();
        EV.toast('已保存到沙盒：' + ctx.name);
      } catch (e) {
        EV.toast('保存到沙盒失败：' + e.message, true);
      }
      return;
    }

    var name = await EV.prompt({
      title: '保存工作流',
      label: '图谱名称',
      value: state.graphName || 'my_awesome_flow',
      placeholder: 'e.g. data_pipeline',
      okLabel: '保存'
    });
    if (!name) return;
    var desc = await EV.prompt({
      title: '工作流描述',
      label: '描述（可留空）',
      value: state.description || '',
      placeholder: 'Describe what this workflow does...',
      allowEmpty: true,
      okLabel: '保存'
    });
    if (desc === null) desc = state.description || '';
    state.description = desc;
    try {
      var graph = exportGraph(name);
      await EV.api.post('/api/graphs/' + encodeURIComponent(name), graph);
      state.graphName = name;
      state.dirty = false;
      renderAll();
      EV.toast('保存成功：' + name);
      loadFileList();
    } catch (e) {
      EV.toast('保存失败：' + e.message, true);
    }
  }

  /* ---------------- 汇总渲染 ---------------- */
  function renderAll() {
    renderSide();
    renderToolbar();
    renderCanvas();
    paintSelection();
  }

  function injectStyle() {
    var css = ''
      + '.g-shell{flex:1;display:flex;min-height:0}'
      + '.g-canvas{position:relative;flex:1;min-width:0;overflow:hidden;cursor:default;'
      + 'background:radial-gradient(circle at 1px 1px, rgba(15,17,21,.10) 1px, transparent 0) 0 0/16px 16px, #fbfcfd}'
      + '.g-world{position:absolute;left:0;top:0;transform-origin:0 0}'
      + '.g-svg{position:absolute;left:0;top:0;width:1px;height:1px;overflow:visible;pointer-events:none}'
      + '.g-edge{fill:none;stroke:#9aa5b1;stroke-width:1.6}'
      + '.g-edge.on{stroke:#16191d;stroke-width:2.2}'
      + '.g-edge-hit{fill:none;stroke:transparent;stroke-width:12;pointer-events:stroke;cursor:pointer}'
      + '.g-node{position:absolute;width:240px;background:#fff;border:1px solid rgba(15,17,21,.10);border-radius:10px;'
      + 'box-shadow:0 1px 2px rgba(15,17,21,.06),0 8px 20px rgba(15,17,21,.06);user-select:none}'
      + '.g-node.on{border-color:#16191d;box-shadow:0 0 0 2px rgba(22,25,29,.14),0 10px 24px rgba(15,17,21,.12)}'
      + '.g-node-h{display:flex;align-items:center;gap:7px;padding:8px 10px;border-bottom:1px solid rgba(15,17,21,.08);'
      + 'font-size:12px;font-weight:600;cursor:grab;overflow:hidden}'
      + '.g-node-dot{width:9px;height:9px;border-radius:3px;flex:none}'
      // 卡片内联配置区（直接编辑；长内容用右侧放大按钮进大窗口改）
      + '.g-cfg{display:flex;flex-direction:column;gap:6px;padding:7px 10px 3px}'
      + '.g-cfgf{display:flex;flex-direction:column;gap:3px;position:relative}'
      + '.g-cfgl{font-size:9.5px;font-weight:700;letter-spacing:.05em;color:#8b96a3;text-transform:uppercase}'
      + '.g-cfgin{width:100%;font-family:inherit;font-size:11.5px;color:#16191d;background:#f7f8fa;'
      + 'border:1px solid rgba(15,17,21,.10);border-radius:6px;padding:5px 7px;outline:none;resize:none;line-height:1.55}'
      + '.g-cfgin:focus{border-color:#16191d;background:#fff}'
      + '.g-cfgin.mono{font-family:ui-monospace,Consolas,monospace;font-size:11px;white-space:pre-wrap;word-break:break-word;overflow:hidden}'
      + '.g-cfgexp{display:none;position:absolute;top:0;right:0;width:18px;height:16px;align-items:center;'
      + 'justify-content:center;border:none;border-radius:5px;background:#eef1f4;color:#5c6672;cursor:pointer}'
      + '.g-cfgf:hover .g-cfgexp{display:inline-flex}'
      + '.g-cfgexp:hover{background:#16191d;color:#fff}'
      // 放大编辑弹窗的大文本框
      + '.g-bigta{width:100%;height:60vh;box-sizing:border-box;font-size:12px;line-height:1.7;padding:10px 12px;'
      + 'border:1px solid rgba(15,17,21,.14);border-radius:8px;background:#fff;color:#16191d;resize:vertical}'
      + '.g-cfg textarea,.g-cfg select,.g-node-rename{user-select:text}'
      + '.g-cfgitem{display:flex;align-items:center;gap:6px;padding:2px 3px 2px 8px;'
      + 'background:#f7f8fa;border:1px solid #e3e6ea;border-radius:6px}'
      + '.g-cfgitem .nm{flex:1;min-width:0;font-family:ui-monospace,Consolas,monospace;'
      + 'font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
      + '.g-cfgitem .g-cfgdel{flex:none;width:18px;height:18px}'
      + '.g-cfgempty{font-size:10.5px;color:#9aa5b1}'
      + '.g-node-rename{flex:1;min-width:0;font:inherit;font-size:12px;font-weight:600;color:#16191d;'
      + 'background:#f7f8fa;border:1px solid rgba(15,17,21,.16);border-radius:6px;padding:2px 6px;outline:none}'
      + '.g-node-edit{display:none;flex:none;width:18px;height:18px;align-items:center;justify-content:center;'
      + 'border:none;border-radius:5px;background:transparent;color:#8b96a3;cursor:pointer}'
      + '.g-node:hover .g-node-edit{display:inline-flex}'
      + '.g-node-edit:hover{background:#e9edf1;color:#16191d}'
      + '.g-node-del{flex:none;width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;'
      + 'border:none;border-radius:5px;background:transparent;color:#a7b0bb;cursor:pointer}'
      + '.g-node-del:hover{background:#fdeceb;color:#c0392b}'
      + '.g-ports{display:flex;justify-content:space-between;padding:2px 0 8px}'
      + '.g-pcol{display:flex;flex-direction:column;gap:6px;min-width:0}'
      + '.g-pcol.r{align-items:flex-end}'
      + '.g-port{display:flex;align-items:center;gap:5px;font-size:10.5px;color:#4c5560;padding:0 7px;max-width:100%}'
      + '.g-port .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
      + '.g-port .dot{width:11px;height:11px;border-radius:999px;border:1.5px solid #8b96a3;background:#fff;cursor:crosshair;flex:none}'
      + '.g-port .dot:hover{background:#16191d;border-color:#16191d}'
      + '.g-port.l .dot{margin-left:-13px}'
      + '.g-port.r .dot{margin-right:-13px}'
      + '.g-lblock{display:flex;flex-direction:column;gap:5px;width:100%;margin:1px 0 3px}'
      + '.g-lblock.r .g-port{justify-content:flex-end}'
      + '.g-lrow .nm{font-style:italic}'
      + '.g-ladd{align-self:flex-start;margin-left:6px}'
      + '.g-lblock.r .g-ladd{align-self:flex-end;margin-left:0;margin-right:6px}'
      // 画布左上角节点面板（默认折叠）
      + '.g-pal-toggle{position:absolute;left:10px;top:10px;z-index:6;background:#fff;'
      + 'border:1px solid rgba(15,17,21,.10);box-shadow:0 1px 2px rgba(15,17,21,.06)}'
      + '.g-pal-toggle.on{background:#16191d;border-color:#16191d;color:#fff}'
      + '.g-pal{position:absolute;left:10px;top:46px;bottom:12px;width:208px;z-index:5;display:none;'
      + 'flex-direction:column;background:#fff;border:1px solid rgba(15,17,21,.10);border-radius:10px;'
      + 'box-shadow:0 8px 24px rgba(15,17,21,.10);overflow:hidden}'
      + '.g-pal-h{padding:8px 10px;font-size:10.5px;font-weight:700;letter-spacing:.05em;color:#8b96a3;'
      + 'text-transform:uppercase;border-bottom:1px solid rgba(15,17,21,.08)}'
      + '.g-pal-b{flex:1;min-height:0;overflow:auto;padding:6px;display:flex;flex-direction:column;gap:2px}'
      + '.g-pal-item{display:flex;align-items:center;gap:7px;padding:6px 7px;border-radius:7px;'
      + 'font-size:12px;color:#16191d;cursor:grab;user-select:none}'
      + '.g-pal-item:hover{background:#f2f4f7}'
      + '.g-pal-item .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
      + '.g-pal-dot{width:9px;height:9px;border-radius:3px;flex:none}'
      + '.g-pal-empty{padding:8px 6px;font-size:11.5px;color:#8b96a3}'
      // 画布右下角缩放条
      + '.g-zoom{position:absolute;right:12px;bottom:12px;z-index:6;display:flex;align-items:center;gap:2px;'
      + 'padding:3px;background:#fff;border:1px solid rgba(15,17,21,.10);border-radius:9px;'
      + 'box-shadow:0 2px 8px rgba(15,17,21,.07)}'
      + '.g-zoom .ibtn{width:26px;height:26px}'
      + '.g-zoom-pct{min-width:42px;text-align:center;font-size:11px;font-weight:700;color:#4c5560;'
      + 'cursor:pointer;user-select:none}'
      // 画布右上角操作条（布局 / 校验 / 保存）
      + '.g-actions{position:absolute;right:12px;top:10px;z-index:6;display:flex;align-items:center;gap:2px;'
      + 'padding:3px 5px;background:#fff;border:1px solid rgba(15,17,21,.10);border-radius:9px;'
      + 'box-shadow:0 2px 8px rgba(15,17,21,.07)}'
      + '.g-actions .btn{height:26px}';
    var st = EV.el('style');
    st.textContent = css;
    document.head.appendChild(st);
  }

  EV.defineTab('graph', 'Graph', {
    mount: function (root) {
      injectStyle();

      var side = EV.el('div', 'side');
      var sideHead = EV.el('div', 'side-head');
      sideHead.appendChild(EV.el('span', null, '图谱'));
      sideHead.appendChild(EV.el('span', 'spacer'));
      EV.attachSideToggle(side, sideHead);
      side.appendChild(sideHead);
      sideBodyEl = EV.el('div', 'side-body');
      side.appendChild(sideBodyEl);
      root.appendChild(side);

      var main = EV.el('div', 'main');
      toolbarEl = EV.el('div', 'g-actions');

      var shell = EV.el('div', 'g-shell');
      canvasEl = EV.el('div', 'g-canvas');
      worldEl = EV.el('div', 'g-world');
      svgEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svgEl.setAttribute('class', 'g-svg');
      worldEl.appendChild(svgEl);
      canvasEl.appendChild(worldEl);

      // 左上角：节点面板开关（默认折叠）
      var palBtn = EV.el('button', 'ibtn g-pal-toggle');
      palBtn.innerHTML = EV.icon('menu', 14);
      palBtn.title = '节点列表';
      palBtn.onclick = togglePalette;
      palettePanel = EV.el('div', 'g-pal');
      palettePanel.style.display = 'none';
      palettePanel.appendChild(EV.el('div', 'g-pal-h', '节点列表'));
      paletteBodyEl = EV.el('div', 'g-pal-b');
      palettePanel.appendChild(paletteBodyEl);

      // 右下角：缩放与定位
      var zoomDock = EV.el('div', 'g-zoom');
      var zOut = EV.el('button', 'ibtn');
      zOut.innerHTML = EV.icon('zoomOut', 14);
      zOut.title = '缩小';
      zOut.onclick = function () { zoomBy(1 / 1.2); };
      zoomDock.appendChild(zOut);
      zoomPctEl = EV.el('span', 'g-zoom-pct', Math.round(state.view.s * 100) + '%');
      zoomPctEl.title = '恢复 100%';
      zoomPctEl.onclick = function () {
        state.view.s = 1;
        applyView();
        drawEdges();
        syncZoomPct();
      };
      zoomDock.appendChild(zoomPctEl);
      var zIn = EV.el('button', 'ibtn');
      zIn.innerHTML = EV.icon('zoomIn', 14);
      zIn.title = '放大';
      zIn.onclick = function () { zoomBy(1.2); };
      zoomDock.appendChild(zIn);
      var zFit = EV.el('button', 'ibtn');
      zFit.innerHTML = EV.icon('fit', 14);
      zFit.title = '适应画布';
      zFit.onclick = fitView;
      zoomDock.appendChild(zFit);

      canvasEl.appendChild(palBtn);
      canvasEl.appendChild(palettePanel);
      canvasEl.appendChild(zoomDock);
      canvasEl.appendChild(toolbarEl);
      shell.appendChild(canvasEl);

      main.appendChild(shell);
      root.appendChild(main);

      bindCanvas();
      renderToolbar();
      applyView();
      renderSide();

      loadCatalog().then(loadFileList);
      loadWorkplaces();
    },
    onShow: function () {
      renderToolbar();
      drawEdges();
      loadWorkplaces();
    },
    openDetail: openSandboxGraph
  });
})();