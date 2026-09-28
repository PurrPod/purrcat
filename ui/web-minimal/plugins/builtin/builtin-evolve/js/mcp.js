/* ============================================================================
 * 「MCP」标签：与完整模式 EvolvePage 的 MCP 工厂对齐
 *   工具清单（TOOLS）→ 测试报告（REPORT）→ 合并审查（MERGE）
 * ========================================================================== */
(function () {
  'use strict';
  var EV = window.EV;

  var state = {
    workplaces: [],
    activeWp: null,
    step: 'tools',          // tools | report | merge
    tools: null,            // schema_dump.json 解析结果（null = 未生成）
    toolsError: '',
    iterations: [],
    activeIteration: null,
    reportMd: '',
    diffContent: '',
    diffLoading: false
  };

  var sideBodyEl, subtabsEl, toolbarEl, bodyEl;

  /* ---------------- 数据 ---------------- */
  async function loadWorkplaces() {
    try {
      var list = await EV.api.get('/api/evolve/list?type=mcp');
      state.workplaces = Array.isArray(list) ? list : [];
    } catch (e) {
      state.workplaces = [];
    }
    if (state.activeWp && !state.workplaces.some(function (w) { return w.workplace_id === state.activeWp.workplace_id; })) {
      state.activeWp = null;
    }
    renderSide();
    renderMain();
  }

  async function loadTools() {
    if (!state.activeWp) return;
    state.toolsError = '';
    try {
      var data = await EV.api.get('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name,
        filename: 'evals/outputs/schema_dump.json', type: 'mcp'
      }));
      var content = (data && data.content) || '';
      state.tools = content ? JSON.parse(content) : null;
    } catch (e) {
      state.tools = null;
      state.toolsError = e.message;
    }
    renderBody();
  }

  async function loadIterations() {
    if (!state.activeWp) return;
    try {
      var iters = await EV.api.get('/api/evolve/test/iterations' + EV.qs({
        workplace_id: state.activeWp.workplace_id, type: 'mcp'
      }));
      state.iterations = iters || [];
      if (state.iterations.length) {
        await selectIteration(state.iterations[state.iterations.length - 1], true);
        return;
      }
      state.activeIteration = null;
      state.reportMd = '';
      renderBody();
    } catch (e) { /* noop */ }
  }

  async function selectIteration(iter, skipRender) {
    state.activeIteration = iter;
    if (!skipRender) renderBody();
    try {
      var data = await EV.api.get('/api/evolve/test/report' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, iteration: iter, type: 'mcp'
      }));
      state.reportMd = data.report_md || '*此轮次尚未生成测试报告。*';
    } catch (e) {
      state.reportMd = '*获取报告失败：' + e.message + '*';
    }
    renderBody();
  }

  async function runTest() {
    if (!state.activeWp) return;
    try {
      await EV.api.post('/api/evolve/test/run', {
        type: 'mcp', workplace_id: state.activeWp.workplace_id, name: state.activeWp.name
      });
      EV.toast('已在宿主机触发语义竞争与执行测试，稍后刷新查看报告');
      setTimeout(loadIterations, 1500);
    } catch (e) {
      EV.toast('触发测试失败：' + e.message, true);
    }
  }

  async function loadDiff() {
    if (!state.activeWp) return;
    state.diffLoading = true;
    state.step = 'merge';
    renderMain();
    try {
      var data = await EV.api.get('/api/evolve/diff' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, type: 'mcp'
      }));
      state.diffContent = data.diff_content || '文件内容没有任何改变。';
    } catch (e) {
      state.diffContent = '获取差异信息失败：' + e.message;
    } finally {
      state.diffLoading = false;
      renderMain();
    }
  }

  async function handleMerge(approved, rejectReason) {
    if (!state.activeWp) return;
    if (!approved && !(rejectReason || '').trim()) { EV.toast('打回加工必须填写拒绝理由！', true); return; }
    try {
      var data = await EV.api.post('/api/evolve/handle', {
        type: 'mcp', workplace_id: state.activeWp.workplace_id,
        name: state.activeWp.name, is_approved: approved, reject_reason: (rejectReason || '').trim()
      });
      EV.toast(data.message || (approved ? '已并入主库！' : '意见已送达'));
      if (approved) { state.activeWp = null; await loadWorkplaces(); }
    } catch (e) {
      EV.toast('操作失败：' + e.message, true);
    }
  }

  async function rollback() {
    if (!state.activeWp) return;
    var ok = await EV.confirm({
      title: '回滚确认',
      message: '危险操作：确定要把主库的 MCP「' + state.activeWp.name + '」强制回滚到上一次 Git 提交版本吗？\n此操作无法撤销。',
      okLabel: '执行回滚', danger: true
    });
    if (!ok) return;
    try {
      var data = await EV.api.post('/api/evolve/rollback', { type: 'mcp', name: state.activeWp.name });
      EV.toast(data.message || '回滚完成');
    } catch (e) {
      EV.toast('回滚失败：' + e.message, true);
    }
  }

  async function deleteWorkplace(wp) {
    var ok = await EV.confirm({
      title: '清理沙盒',
      message: '确定要彻底清理「' + wp.name + '」的沙盒工作区吗？\n此操作不可逆；已合并成功的沙盒清理不会影响正式库。',
      okLabel: '彻底清理', danger: true
    });
    if (!ok) return;
    try {
      await EV.api.del('/api/evolve/workplace/' + encodeURIComponent(wp.workplace_id) + '?type=mcp');
      EV.toast('沙盒已彻底清理');
      if (state.activeWp && state.activeWp.workplace_id === wp.workplace_id) state.activeWp = null;
      await loadWorkplaces();
    } catch (e) {
      EV.toast('清理失败：' + e.message, true);
    }
  }

  /* ---------------- 渲染 ---------------- */
  function renderSide() {
    sideBodyEl.innerHTML = '';
    if (!state.workplaces.length) {
      sideBodyEl.appendChild(EV.el('div', 'hint', '暂无加工中的 MCP 沙盒。\n让 Agent 在进化工厂中启动一次 MCP 构建后，沙盒会出现在这里。'));
      return;
    }
    state.workplaces.forEach(function (wp) {
      var sel = state.activeWp && state.activeWp.workplace_id === wp.workplace_id;
      var item = EV.el('div', 'item' + (sel ? ' on' : ''));
      var nm = EV.el('div', 'item-name');
      nm.appendChild(EV.el('span', 'nm', wp.name));
      item.appendChild(nm);
      item.appendChild(EV.el('div', 'item-sub', wp.workplace_id));
      var x = EV.el('button', 'item-x');
      x.title = '清理沙盒';
      x.innerHTML = EV.icon('trash', 14);
      x.onclick = function (e) { e.stopPropagation(); deleteWorkplace(wp); };
      item.appendChild(x);
      item.onclick = function () {
        if (state.activeWp && state.activeWp.workplace_id === wp.workplace_id) return;
        state.activeWp = wp;
        state.step = 'tools';
        state.tools = null; state.toolsError = '';
        state.iterations = []; state.activeIteration = null; state.reportMd = '';
        state.diffContent = '';
        renderSide();
        renderMain();
        loadTools();
        loadIterations();
      };
      sideBodyEl.appendChild(item);
    });
  }

  function renderSubtabs() {
    subtabsEl.innerHTML = '';
    [
      { id: 'tools', label: '工具清单' },
      { id: 'report', label: '测试报告' },
      { id: 'merge', label: '合并审查' }
    ].forEach(function (t) {
      var b = EV.el('button', 'subtab' + (state.step === t.id ? ' on' : ''), t.label);
      b.disabled = !state.activeWp;
      b.style.opacity = state.activeWp ? '' : '.5';
      b.onclick = function () {
        if (!state.activeWp) return;
        if (t.id === 'merge') { loadDiff(); return; }
        state.step = t.id;
        renderMain();
        if (t.id === 'tools') loadTools();
        if (t.id === 'report') loadIterations();
      };
      subtabsEl.appendChild(b);
    });
  }

  function renderToolbar() {
    toolbarEl.innerHTML = '';
    toolbarEl.appendChild(EV.el('span', 'spacer'));
    if (state.step === 'tools') {
      var note = EV.el('span', 'note', state.activeWp ? state.activeWp.name : '');
      toolbarEl.appendChild(note);
      var rf = EV.el('button', 'ibtn');
      rf.innerHTML = EV.icon('refresh', 14);
      rf.title = '重新读取 schema_dump.json';
      rf.disabled = !state.activeWp;
      rf.onclick = loadTools;
      toolbarEl.appendChild(rf);
    } else if (state.step === 'report') {
      var runBtn = EV.el('button', 'btn primary');
      runBtn.innerHTML = EV.icon('play', 14);
      runBtn.appendChild(EV.el('span', null, '运行测试'));
      runBtn.disabled = !state.activeWp;
      runBtn.onclick = runTest;
      toolbarEl.appendChild(runBtn);
      var refresh = EV.el('button', 'ibtn');
      refresh.innerHTML = EV.icon('refresh', 14);
      refresh.title = '刷新存档列表';
      refresh.disabled = !state.activeWp;
      refresh.onclick = loadIterations;
      toolbarEl.appendChild(refresh);
    } else {
      var reload = EV.el('button', 'ibtn');
      reload.innerHTML = EV.icon('refresh', 14);
      reload.title = '重新生成 Diff';
      reload.classList.toggle('spin', state.diffLoading);
      reload.onclick = loadDiff;
      toolbarEl.appendChild(reload);
      var roll = EV.el('button', 'ibtn danger');
      roll.innerHTML = EV.icon('undo', 14);
      roll.title = '回滚主库到上一版本';
      roll.onclick = rollback;
      toolbarEl.appendChild(roll);
      var reject = EV.el('button', 'btn danger');
      reject.innerHTML = EV.icon('x', 14);
      reject.appendChild(EV.el('span', null, '打回'));
      reject.onclick = openRejectModal;
      toolbarEl.appendChild(reject);
      var approve = EV.el('button', 'btn primary');
      approve.innerHTML = EV.icon('check', 14);
      approve.appendChild(EV.el('span', null, '批准合并'));
      approve.onclick = function () { handleMerge(true, ''); };
      toolbarEl.appendChild(approve);
    }
  }

  // 把 description 中的 "Args:" 段落拆成 {参数名: 说明}
  function splitArgs(desc) {
    var out = { main: desc || '', map: {} };
    if (!desc || desc.indexOf('Args:') < 0) return out;
    var parts = desc.split(/Args:\s*/);
    out.main = (parts[0] || '').trim();
    var lines = (parts[1] || '').split('\n');
    var cur = '';
    lines.forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var m = line.match(/^([a-zA-Z0-9_]+)\s*:\s*(.*)/);
      if (m) { cur = m[1]; out.map[cur] = m[2]; }
      else if (cur) out.map[cur] += ' ' + line;
    });
    return out;
  }

  function renderToolCard(tool) {
    var schema = tool.inputSchema || {};
    var props = schema.properties || {};
    var required = schema.required || [];
    var parsed = splitArgs(tool.description || '');

    var card = EV.el('div', 'card');
    var head = EV.el('div', 'card-head');
    head.innerHTML = EV.icon('zap', 16);
    head.appendChild(EV.el('span', 'card-title', tool.name || '(未命名工具)'));
    card.appendChild(head);

    var desc = EV.el('div', 'hint');
    desc.style.padding = '0 0 10px';
    desc.textContent = parsed.main || '暂无工具描述（缺少 Docstring 第一行）';
    if (!parsed.main) desc.style.fontStyle = 'italic';
    card.appendChild(desc);

    var keys = Object.keys(props);
    if (!keys.length) {
      var none = EV.el('div', 'hint');
      none.style.padding = '4px 0';
      none.textContent = '此工具不需要任何参数。';
      card.appendChild(none);
      return card;
    }

    var tbl = EV.el('table', 'tbl');
    var thead = EV.el('thead');
    var trh = EV.el('tr');
    ['参数名', '类型', '说明', '必填'].forEach(function (h) { trh.appendChild(EV.el('th', null, h)); });
    thead.appendChild(trh);
    tbl.appendChild(thead);
    var tbody = EV.el('tbody');
    keys.forEach(function (k) {
      var val = props[k] || {};
      var tr = EV.el('tr');
      var td1 = EV.el('td');
      td1.appendChild(EV.el('code', null, k));
      tr.appendChild(td1);
      tr.appendChild(EV.el('td', null, val.type || 'any'));
      var d = val.description || parsed.map[k] || '';
      var td3 = EV.el('td');
      if (d) td3.textContent = d;
      else { td3.style.color = 'var(--dim)'; td3.style.fontStyle = 'italic'; td3.textContent = '未提供描述'; }
      tr.appendChild(td3);
      var td4 = EV.el('td');
      if (required.indexOf(k) >= 0) {
        td4.appendChild(EV.el('span', 'chip warn', '必填'));
      } else {
        var label = '可选' + (val.default !== undefined ? '（默认 ' + JSON.stringify(val.default) + '）' : '');
        td4.appendChild(EV.el('span', 'chip mute', label));
      }
      tr.appendChild(td4);
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody);
    card.appendChild(tbl);
    return card;
  }

  function renderBody() {
    bodyEl.innerHTML = '';
    if (!state.activeWp) {
      var c = EV.el('div', 'center');
      c.innerHTML = EV.icon('server', 36);
      c.appendChild(EV.el('div', 'big', '从左侧选择一个加工中的 MCP 沙盒'));
      c.appendChild(EV.el('div', 'sub', '选中后可查看工具导出清单、运行测试、审查 Diff 并合并回主库。'));
      bodyEl.appendChild(c);
      return;
    }

    if (state.step === 'tools') {
      var sc = EV.el('div', 'scroll pad');
      if (state.tools && state.tools.length) {
        state.tools.forEach(function (tool) { sc.appendChild(renderToolCard(tool)); });
      } else {
        var box = EV.el('div', 'center');
        box.innerHTML = EV.icon('flask', 34);
        box.appendChild(EV.el('div', 'big', state.toolsError ? '读取工具清单失败' : '沙盒中未找到 schema_dump.json 产物'));
        var sub = EV.el('div', 'sub');
        sub.textContent = state.toolsError
          ? state.toolsError
          : '说明：代码编写完毕后尚未在沙盒环境中执行过基础测试逻辑。请引导 Agent 执行 python scripts/evaluation.py 生成工具导出清单，或直接到「测试报告」页运行完整测试。';
        box.appendChild(sub);
        sc.appendChild(box);
      }
      bodyEl.appendChild(sc);
    } else if (state.step === 'report') {
      var wrap2 = EV.el('div', 'pane');
      var left = EV.el('div', 'side');
      left.style.width = '170px';
      left.appendChild(EV.el('div', 'side-head', '测试存档'));
      var lb = EV.el('div', 'side-body');
      if (!state.iterations.length) lb.appendChild(EV.el('div', 'hint', '暂无测试存档。\n点击右上角「运行测试」启动流水线。'));
      state.iterations.forEach(function (iter) {
        var it = EV.el('div', 'item' + (state.activeIteration === iter ? ' on' : ''));
        it.appendChild(EV.el('div', 'item-name', 'Iteration ' + iter));
        it.onclick = function () { selectIteration(iter); };
        lb.appendChild(it);
      });
      left.appendChild(lb);

      var right = EV.el('div', 'main');
      var sc2 = EV.el('div', 'scroll pad');
      var mdEl = EV.el('div', 'md');
      mdEl.innerHTML = EV.md(state.reportMd);
      sc2.appendChild(mdEl);
      right.appendChild(sc2);
      wrap2.appendChild(left);
      wrap2.appendChild(right);
      bodyEl.appendChild(wrap2);
    } else {
      var sc3 = EV.el('div', 'scroll pad');
      if (state.diffLoading) {
        sc3.appendChild(EV.el('div', 'hint', '正在生成 Diff…'));
      } else if (!state.diffContent) {
        sc3.appendChild(EV.el('div', 'hint', '点击右上角刷新按钮生成 Diff。'));
      } else {
        var diff = EV.el('div', 'diff');
        state.diffContent.split('\n').forEach(function (line) {
          var d = EV.el('div', 'ln');
          if (line.indexOf('diff --git') === 0 || line.indexOf('index ') === 0 || line.indexOf('---') === 0 || line.indexOf('+++') === 0) d.classList.add('hd');
          else if (line.indexOf('+') === 0) d.classList.add('add');
          else if (line.indexOf('-') === 0) d.classList.add('del');
          d.textContent = line || '\u00A0';
          diff.appendChild(d);
        });
        sc3.appendChild(diff);
      }
      bodyEl.appendChild(sc3);
    }
  }

  function renderMain() {
    renderSubtabs();
    renderToolbar();
    renderBody();
  }

  function openRejectModal() {
    var wrap = EV.el('div');
    wrap.appendChild(EV.el('div', 'hint', '打回加工会把该意见写入沙盒的 REJECT_REASON.md，Agent 可读取后继续调整。'));
    var ta = EV.el('textarea', 'textarea');
    ta.rows = 5;
    ta.placeholder = '写下指导意见，发回给 Agent 重做…';
    wrap.appendChild(ta);
    EV.modal({
      title: '打回加工 — 指导意见',
      width: '480px',
      node: wrap,
      actions: [
        { label: '取消' },
        {
          label: '发送意见', kind: 'danger',
          onClick: function (h) {
            if (!ta.value.trim()) { EV.toast('必须填写指导意见！', true); return; }
            handleMerge(false, ta.value);
            h.close();
          }
        }
      ]
    });
  }

  EV.defineTab('mcp', 'MCP', {
    mount: function (root) {
      var side = EV.el('div', 'side');
      var sideHead = EV.el('div', 'side-head');
      sideHead.appendChild(EV.el('span', null, '加工沙盒'));
      sideHead.appendChild(EV.el('span', 'spacer'));
      EV.attachSideToggle(side, sideHead);
      side.appendChild(sideHead);
      sideBodyEl = EV.el('div', 'side-body');
      side.appendChild(sideBodyEl);
      root.appendChild(side);

      var main = EV.el('div', 'main');
      subtabsEl = EV.el('div', 'subtabs');
      toolbarEl = EV.el('div', 'toolbar');
      bodyEl = EV.el('div', 'main');
      bodyEl.style.flex = '1';
      bodyEl.style.minHeight = '0';
      main.appendChild(subtabsEl);
      main.appendChild(toolbarEl);
      main.appendChild(bodyEl);
      root.appendChild(main);

      state.step = 'tools';
      renderMain();
      loadWorkplaces();
    },
    onShow: function () { loadWorkplaces(); }
  });
})();