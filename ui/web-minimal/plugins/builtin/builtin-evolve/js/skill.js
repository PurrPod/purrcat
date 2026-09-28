/* ============================================================================
 * 「技能」标签：与完整模式 EvolvePage 的 Skill 工厂对齐
 *   文件编辑（FILES）→ 评测迭代（EVALS）→ 合并审查（MERGE）
 * ========================================================================== */
(function () {
  'use strict';
  var EV = window.EV;

  var state = {
    workplaces: [],
    activeWp: null,
    step: 'files',
    files: [],
    activeFile: '',
    fileContent: '',
    evalsContent: '',
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
      var list = await EV.api.get('/api/evolve/list?type=skill');
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

  async function loadFiles() {
    if (!state.activeWp) return;
    try {
      var data = await EV.api.get('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, type: 'skill'
      }));
      state.files = (data.attachments || []).filter(function (f) { return f.indexOf('evals') !== 0; });
      var def = '';
      if (state.files.indexOf('SKILL.md') >= 0) def = 'SKILL.md';
      else if (state.files.length) def = state.files[0];
      state.activeFile = def;
      state.fileContent = '';
      if (def) await loadFile(def);
      renderBody();
    } catch (e) {
      EV.toast('加载沙盒文件失败：' + e.message, true);
    }
  }

  async function loadFile(name) {
    if (!state.activeWp || !name) { state.fileContent = ''; return; }
    try {
      var data = await EV.api.get('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, filename: name, type: 'skill'
      }));
      state.fileContent = data.content || '';
    } catch (e) {
      state.fileContent = '加载失败：' + e.message;
    }
  }

  async function saveFile() {
    if (!state.activeWp || !state.activeFile) return;
    try {
      await EV.api.put('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, filename: state.activeFile, type: 'skill'
      }), { content: state.fileContent });
      EV.toast('[' + state.activeFile + '] 已写入沙盒磁盘');
    } catch (e) {
      EV.toast('写入失败：' + e.message, true);
    }
  }

  async function loadIterations() {
    if (!state.activeWp) return;
    try {
      var iters = await EV.api.get('/api/evolve/test/iterations' + EV.qs({
        workplace_id: state.activeWp.workplace_id, type: 'skill'
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
    if (!skipRender) { renderBody(); }
    try {
      var data = await EV.api.get('/api/evolve/test/report' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, iteration: iter, type: 'skill'
      }));
      state.reportMd = data.report_md || '*此轮次尚未生成评测报告。*';
    } catch (e) {
      state.reportMd = '*获取报告失败：' + e.message + '*';
    }
    renderBody();
  }

  async function runTest() {
    if (!state.activeWp) return;
    try {
      await EV.api.post('/api/evolve/test/run', {
        type: 'skill', workplace_id: state.activeWp.workplace_id, name: state.activeWp.name
      });
      EV.toast('后台测试流水线已启动，稍后点击刷新获取报告');
      setTimeout(loadIterations, 1500);
    } catch (e) {
      EV.toast('触发测试失败：' + e.message, true);
    }
  }

  async function loadEvalsJson() {
    if (!state.activeWp) return;
    try {
      var data = await EV.api.get('/api/evolve/file' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, filename: 'evals/evals.json', type: 'skill'
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
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, filename: 'evals/evals.json', type: 'skill'
      }), { content: state.evalsContent });
      EV.toast('evals.json 已保存');
    } catch (e) {
      EV.toast('保存失败：' + e.message, true);
    }
  }

  async function loadDiff() {
    if (!state.activeWp) return;
    state.diffLoading = true;
    state.step = 'merge';
    renderMain();
    try {
      var data = await EV.api.get('/api/evolve/diff' + EV.qs({
        workplace_id: state.activeWp.workplace_id, name: state.activeWp.name, type: 'skill'
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
        type: 'skill', workplace_id: state.activeWp.workplace_id,
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
      message: '危险操作：确定要把主库的「' + state.activeWp.name + '」强制回滚到上一次 Git 提交版本吗？\n此操作无法撤销，未被记录的修改将被永久丢弃。',
      okLabel: '执行回滚', danger: true
    });
    if (!ok) return;
    try {
      var data = await EV.api.post('/api/evolve/rollback', { type: 'skill', name: state.activeWp.name });
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
      await EV.api.del('/api/evolve/workplace/' + encodeURIComponent(wp.workplace_id) + '?type=skill');
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
      sideBodyEl.appendChild(EV.el('div', 'hint', '暂无加工中的技能沙盒。\n让 Agent 在进化工厂中启动一次技能构建后，沙盒会出现在这里。'));
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
        state.activeFile = ''; state.fileContent = '';
        state.iterations = []; state.activeIteration = null; state.reportMd = '';
        state.diffContent = ''; state.step = 'files';
        renderSide();
        renderMain();
        loadFiles();
        loadIterations();
      };
      sideBodyEl.appendChild(item);
    });
  }

  function renderSubtabs() {
    subtabsEl.innerHTML = '';
    [
      { id: 'files', label: '文件编辑' },
      { id: 'evals', label: '评测迭代' },
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
        if (t.id === 'evals') loadIterations();
      };
      subtabsEl.appendChild(b);
    });
  }

  function renderToolbar() {
    toolbarEl.innerHTML = '';
    toolbarEl.appendChild(EV.el('span', 'spacer'));

    if (state.step === 'files') {
      var note = EV.el('span', 'note');
      note.textContent = state.activeWp ? (state.activeFile || '未选择文件') : '';
      toolbarEl.appendChild(note);
      var save = EV.el('button', 'btn primary');
      save.innerHTML = EV.icon('save', 14);
      save.appendChild(EV.el('span', null, '保存'));
      save.disabled = !(state.activeWp && state.activeFile);
      save.onclick = saveFile;
      toolbarEl.appendChild(save);
    } else if (state.step === 'evals') {
      var runBtn = EV.el('button', 'btn primary');
      runBtn.innerHTML = EV.icon('play', 14);
      runBtn.appendChild(EV.el('span', null, '运行评测'));
      runBtn.disabled = !state.activeWp;
      runBtn.onclick = runTest;
      toolbarEl.appendChild(runBtn);
      var evalsBtn = EV.el('button', 'btn');
      evalsBtn.innerHTML = EV.icon('edit', 14);
      evalsBtn.appendChild(EV.el('span', null, '编辑 evals.json'));
      evalsBtn.disabled = !state.activeWp;
      evalsBtn.onclick = openEvalsModal;
      toolbarEl.appendChild(evalsBtn);
      var refresh = EV.el('button', 'ibtn');
      refresh.innerHTML = EV.icon('refresh', 14);
      refresh.title = '刷新迭代列表';
      refresh.disabled = !state.activeWp;
      refresh.onclick = loadIterations;
      toolbarEl.appendChild(refresh);
    } else if (state.step === 'merge') {
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

  function emptyCenter() {
    var c = EV.el('div', 'center');
    c.innerHTML = EV.icon('flask', 36);
    c.appendChild(EV.el('div', 'big', '从左侧选择一个加工中的技能沙盒'));
    c.appendChild(EV.el('div', 'sub', '沙盒由 Agent 在进化工厂中生成。选中后可直接修改沙盒文件、运行评测、审查 Diff 并合并回主库。'));
    return c;
  }

  function renderBody() {
    bodyEl.innerHTML = '';
    if (!state.activeWp) { bodyEl.appendChild(emptyCenter()); return; }

    if (state.step === 'files') {
      var wrap = EV.el('div', 'pane');
      var flist = EV.el('div', 'side');
      flist.style.width = '170px';
      flist.appendChild(EV.el('div', 'side-head', '沙盒文件'));
      var fbody = EV.el('div', 'side-body');
      if (!state.files.length) fbody.appendChild(EV.el('div', 'hint', '沙盒中暂无可见文件。'));
      state.files.forEach(function (f) {
        var it = EV.el('div', 'item' + (state.activeFile === f ? ' on' : ''));
        var nm = EV.el('div', 'item-name');
        nm.innerHTML = EV.icon('file', 14);
        nm.appendChild(EV.el('span', 'nm', f));
        it.appendChild(nm);
        it.onclick = function () {
          if (state.activeFile === f) return;
          state.activeFile = f;
          state.fileContent = '';
          renderBody();
          loadFile(f).then(renderBody);
        };
        fbody.appendChild(it);
      });
      flist.appendChild(fbody);

      var editorPane = EV.el('div', 'main');
      if (!state.activeFile) {
        editorPane.appendChild(EV.el('div', 'hint', '请选择左侧文件进行编辑。'));
      } else {
        var textarea = EV.el('textarea', 'editor-area');
        textarea.value = state.fileContent;
        textarea.spellcheck = false;
        textarea.oninput = function () { state.fileContent = textarea.value; };
        textarea.onkeydown = function (e) {
          if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveFile(); }
        };
        editorPane.appendChild(textarea);
      }
      wrap.appendChild(flist);
      wrap.appendChild(editorPane);
      bodyEl.appendChild(wrap);
    } else if (state.step === 'evals') {
      var wrap2 = EV.el('div', 'pane');
      var left = EV.el('div', 'side');
      left.style.width = '170px';
      left.appendChild(EV.el('div', 'side-head', '评测存档'));
      var lb = EV.el('div', 'side-body');
      if (!state.iterations.length) lb.appendChild(EV.el('div', 'hint', '暂无评测存档。\n点击右上角「运行评测」启动流水线。'));
      state.iterations.forEach(function (iter) {
        var it = EV.el('div', 'item' + (state.activeIteration === iter ? ' on' : ''));
        it.appendChild(EV.el('div', 'item-name', 'Iteration ' + iter));
        it.onclick = function () { selectIteration(iter); };
        lb.appendChild(it);
      });
      left.appendChild(lb);

      var right = EV.el('div', 'main');
      var sc = EV.el('div', 'scroll pad');
      var mdEl = EV.el('div', 'md');
      mdEl.innerHTML = EV.md(state.reportMd);
      sc.appendChild(mdEl);
      right.appendChild(sc);
      wrap2.appendChild(left);
      wrap2.appendChild(right);
      bodyEl.appendChild(wrap2);
    } else {
      var sc2 = EV.el('div', 'scroll pad');
      if (state.diffLoading) {
        sc2.appendChild(EV.el('div', 'hint', '正在生成 Diff…'));
      } else if (!state.diffContent) {
        sc2.appendChild(EV.el('div', 'hint', '点击右上角刷新按钮生成 Diff。'));
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
        sc2.appendChild(diff);
      }
      bodyEl.appendChild(sc2);
    }
  }

  function renderMain() {
    renderSubtabs();
    renderToolbar();
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
        title: 'evals.json — 评测用例',
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

  function openRejectModal() {
    var wrap = EV.el('div');
    wrap.appendChild(EV.el('div', 'hint', '打回加工会把该意见写入沙盒的 REJECT_REASON.md，Agent 可读取后继续调整。'));
    var ta = EV.el('textarea', 'textarea');
    ta.rows = 5;
    ta.placeholder = '如果不满意，请在这里写下指导意见，发回给 Agent 重做…';
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

  /* ---------------- 入口 ---------------- */
  EV.defineTab('skill', '技能', {
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

      state.step = 'files';
      renderMain();
      loadWorkplaces();
    },
    onShow: function () { loadWorkplaces(); }
  });
})();