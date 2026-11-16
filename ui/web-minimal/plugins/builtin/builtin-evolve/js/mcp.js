/* ============================================================================
 * 「MCP」标签：详情页只展示测试报告；文件与合并动作由宿主详情顶栏提供
 * ========================================================================== */
(function () {
  'use strict';
  var EV = window.EV;

  var state = {
    workplaces: [],
    activeWp: null,
    evalsContent: '',
    iterations: [],
    activeIteration: null,
    reportHtml: '',
    running: false
  };

  var sideBodyEl, bodyEl;
  var pollTimer = null;

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
      state.reportHtml = '';
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
      state.reportHtml = data.report_html || '';
    } catch (e) {
      state.reportHtml = '';
      EV.toast('获取报告失败：' + e.message, true);
    }
    renderBody();
  }

  function runTest() {
    if (!state.activeWp || state.running) return;
    var before = state.iterations.length;
    state.running = true;
    renderMain();
    EV.api.post('/api/evolve/test/run', {
      type: 'mcp', workplace_id: state.activeWp.workplace_id, name: state.activeWp.name
    }).then(function () {
      EV.toast('已在宿主机触发语义竞争与执行测试，完成后自动跳转到对应迭代');
      pollNewIteration(before);
    }).catch(function (e) {
      state.running = false;
      renderMain();
      EV.toast('触发测试失败：' + e.message, true);
    });
  }

  function stopPoll() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // 测试耗时较长（真实并发执行用例），故轮询等待新迭代目录出现并自动切过去
  function pollNewIteration(before) {
    stopPoll();
    var wp = state.activeWp;
    if (!wp) { state.running = false; renderMain(); return; }
    var tries = 0;
    pollTimer = setInterval(function () {
      if (!state.activeWp || state.activeWp.workplace_id !== wp.workplace_id) {
        stopPoll(); state.running = false; renderMain(); return;
      }
      tries += 1;
      EV.api.get('/api/evolve/test/iterations' + EV.qs({
        workplace_id: wp.workplace_id, type: 'mcp'
      })).then(function (iters) {
        iters = iters || [];
        if (iters.length > before) {
          stopPoll();
          state.running = false;
          EV.toast('测试完成，已载入 Iteration ' + iters[iters.length - 1]);
          loadIterations();
        } else if (tries >= 60) {
          stopPoll();
          state.running = false;
          EV.toast('测试仍在后台运行，可稍后点刷新查看', true);
          loadIterations();
        }
      }).catch(function () {
        if (tries >= 60) { stopPoll(); state.running = false; renderMain(); }
      });
    }, 5000);
  }

  async function loadEvalsJson() {
    if (!state.activeWp) return;
    try {
      var data = await EV.api.get('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name,
        filename: 'evals/evals.json', type: 'mcp'
      }));
      state.evalsContent = data.content || '';
    } catch (e) {
      state.evalsContent = '// 加载失败：' + e.message;
    }
  }

  async function saveEvalsJson() {
    if (!state.activeWp) return;
    try {
      await EV.api.put('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name,
        filename: 'evals/evals.json', type: 'mcp'
      }), { content: state.evalsContent });
      EV.toast('evals.json 已保存');
    } catch (e) {
      EV.toast('保存失败：' + e.message, true);
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

  function selectWorkplace(wp) {
    if (!wp) return;
    if (state.activeWp && state.activeWp.workplace_id === wp.workplace_id) return;
    state.activeWp = wp;
    state.iterations = []; state.activeIteration = null; state.reportHtml = '';
    state.running = false;
    renderSide();
    renderMain();
    loadIterations();
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
      item.onclick = function () { selectWorkplace(wp); };
      sideBodyEl.appendChild(item);
    });
  }

  function renderBody() {
    bodyEl.innerHTML = '';
    if (!state.activeWp) {
      var c = EV.el('div', 'center');
      c.innerHTML = EV.icon('server', 36);
      c.appendChild(EV.el('div', 'big', '从左侧选择一个加工中的 MCP 沙盒'));
      c.appendChild(EV.el('div', 'sub', '沙盒由 Agent 在进化工厂中生成。选中后可直接运行测试、在顶栏打开文件目录并批准合并。'));
      bodyEl.appendChild(c);
      return;
    }

    var wrap = EV.el('div', 'pane');
    var left = EV.el('div', 'side');
    left.style.width = '190px';
    var head = EV.el('div', 'side-head');
    head.appendChild(EV.el('span', null, '测试存档'));
    head.appendChild(EV.el('span', 'spacer'));
    var runBtn = EV.el('button', 'ibtn');
    runBtn.innerHTML = EV.icon('play', 13);
    runBtn.title = state.running ? '测试进行中…' : '运行测试';
    runBtn.disabled = !state.activeWp || state.running;
    runBtn.onclick = runTest;
    head.appendChild(runBtn);
    var refresh = EV.el('button', 'ibtn');
    refresh.innerHTML = EV.icon('refresh', 13);
    refresh.title = '刷新存档列表';
    refresh.disabled = !state.activeWp;
    refresh.classList.toggle('spin', state.running);
    refresh.onclick = loadIterations;
    head.appendChild(refresh);
    var evalsBtn = EV.el('button', 'ibtn');
    evalsBtn.innerHTML = EV.icon('edit', 13);
    evalsBtn.title = '编辑 evals.json';
    evalsBtn.disabled = !state.activeWp;
    evalsBtn.onclick = openEvalsModal;
    head.appendChild(evalsBtn);
    left.appendChild(head);

    var lb = EV.el('div', 'side-body');
    if (!state.iterations.length) lb.appendChild(EV.el('div', 'hint', '暂无测试存档。\n点击上方播放按钮启动流水线。'));
    state.iterations.forEach(function (iter) {
      var it = EV.el('div', 'item' + (state.activeIteration === iter ? ' on' : ''));
      it.appendChild(EV.el('div', 'item-name', 'Iteration ' + iter));
      it.onclick = function () { selectIteration(iter); };
      lb.appendChild(it);
    });
    left.appendChild(lb);

    var right = EV.el('div', 'main');
    if (!state.reportHtml) {
      right.appendChild(EV.el('div', 'hint', '此轮次尚未生成测试报告。\n点击上方播放按钮启动流水线。'));
    } else {
      var frame = EV.el('iframe', 'report-frame');
      frame.setAttribute('sandbox', '');
      frame.setAttribute('title', 'MCP 测试报告');
      frame.srcdoc = state.reportHtml;
      right.appendChild(frame);
    }
    wrap.appendChild(left);
    wrap.appendChild(right);
    bodyEl.appendChild(wrap);
  }

  function renderMain() {
    renderBody();
  }

  /* ---------------- 弹窗 ---------------- */
  function openEvalsModal() {
    loadEvalsJson().then(function () {
      var textarea = EV.el('textarea', 'editor-area');
      textarea.style.minHeight = '300px';
      textarea.style.whiteSpace = 'pre';
      textarea.value = state.evalsContent;
      textarea.spellcheck = false;
      textarea.oninput = function () { state.evalsContent = textarea.value; };
      EV.modal({
        title: 'evals.json — 测试用例',
        width: '720px',
        flush: true,
        node: textarea,
        actions: [
          { label: '取消' },
          { label: '保存', kind: 'primary', onClick: function (h) { saveEvalsJson(); h.close(); } }
        ]
      });
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
      bodyEl = EV.el('div', 'main');
      bodyEl.style.flex = '1';
      bodyEl.style.minHeight = '0';
      main.appendChild(bodyEl);
      root.appendChild(main);

      renderMain();
      loadWorkplaces();
    },
    onShow: function () { loadWorkplaces(); },
    openDetail: selectWorkplace
  });
})();