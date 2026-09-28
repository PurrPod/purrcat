/* ============================================================================
 * 「Agent Loop」标签：与完整模式 AgentLoopEditor 对齐
 *   paradigm（~/.purrcat/paradigms/*.yaml）的查看与编辑：
 *   基础信息 + 五个 Hook 的动作编排（含触发时机 / 退出期望 / 参数约束 / 技能选择）
 * ========================================================================== */
(function () {
  'use strict';
  var EV = window.EV;

  var HOOK_META = [
    { key: 'on_build_system_prompt', color: '#FFD27D', label: '构建系统提示词时' },
    { key: 'on_loop_start', color: '#7FB8E6', label: '循环开始时' },
    { key: 'on_loop_epoch', color: '#8CC98F', label: '每轮循环迭代时' },
    { key: 'on_loop_end', color: '#E8909A', label: '循环结束时' },
    { key: 'on_tool_calling', color: '#B597E0', label: '工具调用时' }
  ];
  var HOOK_KEYS = HOOK_META.map(function (h) { return h.key; });
  var HOOK_KEY_SET = {};
  HOOK_KEYS.forEach(function (k) { HOOK_KEY_SET[k] = true; });

  var ACTION_TYPES = [
    { type: 'injection', label: '提示注入' },
    { type: 'file_operation', label: '文件操作' },
    { type: 'skill_info', label: '技能注入' },
    { type: 'memo_injection', label: '记忆注入' },
    { type: 'tool_use_check', label: '工具使用检查' },
    { type: 'command_run', label: '命令执行' },
    { type: 'command_on', label: '命令执行（旧版 command_on）' }
  ];
  function actionLabel(type) {
    for (var i = 0; i < ACTION_TYPES.length; i++) if (ACTION_TYPES[i].type === type) return ACTION_TYPES[i].label;
    return type;
  }

  var FIELD_SCHEMA = {
    injection: [
      { key: 'content', label: '注入内容', kind: 'textarea', ph: '注入给 Agent 的提示文本' }
    ],
    file_operation: [
      { key: 'action', label: '操作', kind: 'select', options: ['read', 'exist_check', 'write_in', 'add_in', 'delete'] },
      { key: 'path', label: '路径', kind: 'text', ph: '例如 @RULES / @SYS（系统信息）/ agent_vm/xxx.txt' },
      { key: 'content', label: '写入内容', kind: 'textarea', ph: 'write_in / add_in 时写入的内容', when: { key: 'action', in: ['write_in', 'add_in'] } },
      { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' }
    ],
    skill_info: [
      { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' }
    ],
    memo_injection: [
      { key: 'type', label: '记忆类型', kind: 'text', ph: 'full / light / 其它键名' },
      { key: 'count', label: '条数 count', kind: 'number' }
    ],
    tool_use_check: [
      { key: 'name', label: '工具名 name', kind: 'text', ph: '例如 Memo / ComputerUse' },
      { key: 'successed_prompt', label: '成功提示 successed_prompt', kind: 'text' },
      { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' }
    ],
    command_run: [
      { key: 'command', label: '命令', kind: 'text', ph: '要执行的 shell 命令' },
      { key: 'return_log', label: '回传输出 return_log', kind: 'bool' },
      { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' }
    ]
  };
  FIELD_SCHEMA.command_on = FIELD_SCHEMA.command_run;

  function isPlainObject(v) { return !!v && typeof v === 'object' && !Array.isArray(v); }
  function clone(v) { return JSON.parse(JSON.stringify(v)); }
  function parseScalar(text) {
    var t = String(text).trim();
    if (t === 'true') return true;
    if (t === 'false') return false;
    if (t !== '' && !isNaN(Number(t))) return Number(t);
    return t;
  }

  var state = {
    files: [],
    defaultName: 'PARADIGM',
    activeName: '',
    rootMeta: {},
    hooks: emptyHooks(),
    extraHooks: {},
    baseline: '',
    dirty: false,
    extraRootText: '{}',
    extraRootErr: false
  };

  var sideBodyEl, toolbarEl, bodyEl;

  function emptyHooks() {
    var h = {};
    HOOK_KEYS.forEach(function (k) { h[k] = []; });
    return h;
  }
  function makeActionId(hookKey) {
    return hookKey + '-' + Math.random().toString(36).slice(2, 9);
  }
  function toActions(hookKey, arr) {
    if (!Array.isArray(arr)) return [];
    var out = [];
    arr.forEach(function (item, i) {
      if (!isPlainObject(item)) return;
      var keys = Object.keys(item);
      if (!keys.length) return;
      var type = keys[0];
      var cfg = item[type];
      out.push({ id: hookKey + '-' + i + '-' + type, type: type, config: isPlainObject(cfg) ? clone(cfg) : {} });
    });
    return out;
  }

  function buildDoc() {
    var doc = {};
    Object.keys(state.rootMeta).forEach(function (k) { doc[k] = state.rootMeta[k]; });
    var hooks = {};
    Object.keys(state.extraHooks).forEach(function (k) { hooks[k] = state.extraHooks[k]; });
    HOOK_KEYS.forEach(function (k) {
      hooks[k] = (state.hooks[k] || []).map(function (a) {
        var o = {};
        o[a.type] = a.config;
        return o;
      });
    });
    doc.hooks = hooks;
    return doc;
  }
  function applyDoc(data) {
    data = data || {};
    state.rootMeta = {};
    state.extraHooks = {};
    state.hooks = emptyHooks();
    Object.keys(data).forEach(function (k) {
      if (k === 'hooks') return;
      state.rootMeta[k] = data[k];
    });
    var hooks = data.hooks;
    if (isPlainObject(hooks)) {
      Object.keys(hooks).forEach(function (k) {
        if (HOOK_KEY_SET[k]) state.hooks[k] = toActions(k, hooks[k]);
        else state.extraHooks[k] = hooks[k];
      });
    }
  }
  function refreshExtraRoot() {
    var rest = {};
    Object.keys(state.rootMeta).forEach(function (k) {
      if (['name', 'description', 'path', 'loop_end_max_retry'].indexOf(k) < 0) rest[k] = state.rootMeta[k];
    });
    state.extraRootText = JSON.stringify(rest, null, 2);
    state.extraRootErr = false;
  }
  function refreshDirty() {
    state.dirty = JSON.stringify(buildDoc()) !== state.baseline;
  }
  function touch() { refreshDirty(); renderToolbar(); }
  function commitExtraRoot() {
    var parsed;
    try { parsed = JSON.parse(state.extraRootText || '{}'); }
    catch (e) { state.extraRootErr = true; renderBody(); return; }
    if (!isPlainObject(parsed)) { state.extraRootErr = true; renderBody(); return; }
    // 移除旧的附加键，再写回新的
    Object.keys(state.rootMeta).forEach(function (k) {
      if (['name', 'description', 'path', 'loop_end_max_retry'].indexOf(k) < 0) delete state.rootMeta[k];
    });
    Object.keys(parsed).forEach(function (k) { state.rootMeta[k] = parsed[k]; });
    state.extraRootErr = false;
    touch();
    renderBody();
  }

  /* ---------------- 数据 ---------------- */
  async function loadFileList() {
    try {
      var data = await EV.api.get('/api/paradigms');
      state.files = (data && data.files) || [];
      if (data && data.default) state.defaultName = data.default;
    } catch (e) {
      state.files = [];
      EV.toast('获取 paradigm 列表失败：' + e.message, true);
    }
    if (state.activeName && !state.files.some(function (f) { return f.name === state.activeName; })) {
      state.activeName = '';
    }
    renderSide();
    renderMain();
  }

  async function openFile(name) {
    if (state.dirty) {
      var ok = await EV.confirm({
        title: '未保存的修改',
        message: '当前文件有未保存的修改，切换到「' + name + '」将丢弃这些修改。确定继续吗？',
        okLabel: '继续切换'
      });
      if (!ok) return;
    }
    try {
      var data = await EV.api.get('/api/paradigms/' + encodeURIComponent(name));
      applyDoc(data && data.data);
      refreshExtraRoot();
      state.activeName = name;
      state.baseline = JSON.stringify(buildDoc());
      state.dirty = false;
      renderSide();
      renderMain();
    } catch (e) {
      EV.toast('加载失败：' + e.message, true);
    }
  }

  async function save() {
    if (!state.activeName) return;
    // 未提交的“其它顶层字段”先落盘
    var parsed;
    try { parsed = JSON.parse(state.extraRootText || '{}'); }
    catch (e) { EV.toast('「其它顶层字段」JSON 格式不合法，无法保存', true); return; }
    Object.keys(state.rootMeta).forEach(function (k) {
      if (['name', 'description', 'path', 'loop_end_max_retry'].indexOf(k) < 0) delete state.rootMeta[k];
    });
    Object.keys(parsed || {}).forEach(function (k) { state.rootMeta[k] = parsed[k]; });

    try {
      await EV.api.post('/api/paradigms/' + encodeURIComponent(state.activeName), { data: buildDoc() });
      state.baseline = JSON.stringify(buildDoc());
      state.dirty = false;
      renderToolbar();
      renderBody();
      EV.toast('已保存 ' + state.activeName + '.yaml');
    } catch (e) {
      EV.toast('保存失败：' + e.message, true);
    }
  }

  async function createFile() {
    var name = await EV.prompt({
      title: '新建 Paradigm',
      label: '文件名（将创建 ~/.purrcat/paradigms/{名称}.yaml）',
      placeholder: '例如 my_agent_loop',
      okLabel: '创建'
    });
    if (!name) return;
    var hooks = {};
    HOOK_KEYS.forEach(function (k) { hooks[k] = []; });
    var doc = { name: name, description: '新的主循环', path: 'agent_vm', hooks: hooks };
    try {
      await EV.api.post('/api/paradigms/' + encodeURIComponent(name), { data: doc });
      EV.toast('已新建 ' + name + '.yaml');
      state.dirty = false;
      await loadFileList();
      await openFile(name);
    } catch (e) {
      EV.toast('新建失败：' + e.message, true);
    }
  }

  async function deleteFile(name) {
    var ok = await EV.confirm({
      title: '删除 Paradigm',
      message: '确定要删除 paradigm「' + name + '」？该操作不可恢复！',
      okLabel: '删除', danger: true
    });
    if (!ok) return;
    try {
      await EV.api.del('/api/paradigms/' + encodeURIComponent(name));
      EV.toast('已删除 ' + name);
      if (state.activeName === name) {
        state.activeName = '';
        state.hooks = emptyHooks();
        state.rootMeta = {};
        state.extraHooks = {};
        state.baseline = '';
        state.dirty = false;
        refreshExtraRoot();
      }
      await loadFileList();
      renderMain();
    } catch (e) {
      EV.toast('删除失败：' + e.message, true);
    }
  }

  /* ---------------- 渲染：左列表 ---------------- */
  function renderSide() {
    sideBodyEl.innerHTML = '';
    if (!state.files.length) {
      sideBodyEl.appendChild(EV.el('div', 'hint', '暂无 paradigm 文件。'));
      return;
    }
    state.files.forEach(function (f) {
      var item = EV.el('div', 'item' + (state.activeName === f.name ? ' on' : ''));
      var nm = EV.el('div', 'item-name');
      nm.appendChild(EV.el('span', 'nm', f.name));
      if (f.is_default) nm.appendChild(EV.el('span', 'chip', '默认'));
      item.appendChild(nm);
      item.appendChild(EV.el('div', 'item-sub', '~/.purrcat/paradigms/' + f.name + '.yaml'));
      if (!f.is_default) {
        var x = EV.el('button', 'item-x');
        x.title = '删除 ' + f.name;
        x.innerHTML = EV.icon('trash', 14);
        x.onclick = function (e) { e.stopPropagation(); deleteFile(f.name); };
        item.appendChild(x);
      }
      item.onclick = function () { if (state.activeName !== f.name) openFile(f.name); };
      sideBodyEl.appendChild(item);
    });
  }

  /* ---------------- 渲染：工具栏 ---------------- */
  function renderToolbar() {
    toolbarEl.innerHTML = '';
    var nameWrap = EV.el('div', 'row');
    nameWrap.style.gap = '6px';
    var label = EV.el('span', 'note');
    label.textContent = state.activeName ? state.activeName + '.yaml' : '未打开文件';
    nameWrap.appendChild(label);
    if (state.dirty) {
      var dot = EV.el('span', 'chip warn', '未保存');
      nameWrap.appendChild(dot);
    }
    toolbarEl.appendChild(nameWrap);
    toolbarEl.appendChild(EV.el('span', 'spacer'));

    var create = EV.el('button', 'btn');
    create.innerHTML = EV.icon('plus', 14);
    create.appendChild(EV.el('span', null, '新建'));
    create.onclick = createFile;
    toolbarEl.appendChild(create);

    var saveBtn = EV.el('button', 'btn primary');
    saveBtn.innerHTML = EV.icon('save', 14);
    saveBtn.appendChild(EV.el('span', null, state.dirty ? '保存 *' : '保存'));
    saveBtn.disabled = !state.activeName;
    saveBtn.onclick = save;
    toolbarEl.appendChild(saveBtn);
  }

  /* ---------------- 渲染：字段控件 ---------------- */
  function fieldRow(labelText, control, desc) {
    var f = EV.el('div', 'field');
    f.appendChild(EV.el('label', null, labelText));
    f.appendChild(control);
    if (desc) f.appendChild(EV.el('div', 'desc', desc));
    return f;
  }

  function commitField(action, key, value) {
    if (value === '' || value === undefined || value === null) delete action.config[key];
    else action.config[key] = value;
    touch();
  }

  function fieldControl(action, def) {
    var val = action.config[def.key];
    if (def.kind === 'select' || def.kind === 'bool') {
      var sel = EV.el('select', 'select');
      var empty = EV.el('option', null, '（未设置）');
      empty.value = '';
      sel.appendChild(empty);
      if (def.kind === 'bool') {
        [['true', '是'], ['false', '否']].forEach(function (o) {
          var op = EV.el('option', null, o[1]); op.value = o[0]; sel.appendChild(op);
        });
      } else {
        (def.options || []).forEach(function (o) {
          var op = EV.el('option', null, o); op.value = o; sel.appendChild(op);
        });
      }
      sel.value = val === undefined || val === null ? '' : String(val);
      sel.onchange = function () { commitField(action, def.key, sel.value); renderBody(); };
      return sel;
    }
    if (def.kind === 'textarea') {
      var ta = EV.el('textarea', 'textarea');
      ta.rows = 3;
      ta.placeholder = def.ph || '';
      ta.value = (val === undefined || val === null) ? '' : String(val);
      ta.onchange = function () { commitField(action, def.key, ta.value); };
      return ta;
    }
    var input = EV.el('input', 'input');
    input.type = def.kind === 'number' ? 'number' : 'text';
    input.placeholder = def.ph || '';
    input.value = (val === undefined || val === null) ? '' : String(val);
    input.onchange = function () {
      commitField(action, def.key, def.kind === 'number' ? (input.value === '' ? '' : Number(input.value)) : input.value);
    };
    return input;
  }

  function isVisible(def, cfg) {
    if (!def.when) return true;
    var v = cfg[def.when.key];
    if (def.when.in) return def.when.in.indexOf(v) >= 0;
    return v === def.when.value;
  }

  /* ---------------- 渲染：特殊控件 ---------------- */
  function timingEditor(hookKey, action) {
    var cfg = action.config;
    var box = EV.el('div', 'card');
    box.style.margin = '6px 0 0';
    box.style.background = 'transparent';
    box.style.borderStyle = 'dashed';

    var timingOn = Object.prototype.hasOwnProperty.call(cfg, 'interval');
    var row = EV.el('div', 'row');
    row.appendChild(EV.el('span', null, '触发时机'));
    var toggle = EV.el('button', 'btn sm');
    toggle.textContent = timingOn ? '间隔触发' : '延迟触发';
    toggle.title = timingOn ? '当前：间隔触发，点击切换为延迟' : '当前：延迟触发，点击切换为间隔';
    toggle.onclick = function () {
      var cur = timingOn ? cfg.interval : cfg.delay;
      delete cfg.delay; delete cfg.interval;
      var key = timingOn ? 'delay' : 'interval';
      if (cur !== undefined && cur !== null && cur !== '') cfg[key] = cur;
      touch();
      renderBody();
    };
    row.appendChild(toggle);
    var num = EV.el('input', 'input');
    num.type = 'number';
    num.style.width = '120px';
    num.placeholder = timingOn ? '每隔 N 轮触发一次' : '仅在第 N 轮触发一次';
    num.value = (timingOn ? cfg.interval : cfg.delay) === undefined ? '' : String(timingOn ? cfg.interval : cfg.delay);
    num.onchange = function () {
      var key = timingOn ? 'interval' : 'delay';
      delete cfg.delay; delete cfg.interval;
      if (num.value !== '') cfg[key] = Number(num.value);
      touch();
    };
    row.appendChild(num);
    row.appendChild(EV.el('span', 'note', timingOn ? 'interval' : 'delay'));
    box.appendChild(row);
    box.appendChild(EV.el('div', 'desc', '仅「每轮循环迭代时」可配置：延迟 = 仅在第 N 轮触发一次；间隔 = 每隔 N 轮触发一次。'));
    return box;
  }

  function expectEditor(action) {
    var cfg = action.config;
    var box = EV.el('div', 'card');
    box.style.margin = '6px 0 0';
    box.style.background = 'transparent';
    box.style.borderStyle = 'dashed';
    var row = EV.el('div', 'row');
    row.appendChild(EV.el('span', null, '退出期望（决定能否跳出循环）'));
    var sel = EV.el('select', 'select');
    sel.style.width = '140px';
    [['', '（未设置）'], ['true', '期望成功'], ['false', '期望失败']].forEach(function (o) {
      var op = EV.el('option', null, o[1]); op.value = o[0]; sel.appendChild(op);
    });
    sel.value = cfg.expect === undefined || cfg.expect === null ? '' : String(cfg.expect);
    sel.onchange = function () {
      if (sel.value === '') delete cfg.expect;
      else cfg.expect = sel.value === 'true';
      touch();
    };
    row.appendChild(sel);
    box.appendChild(row);
    box.appendChild(EV.el('div', 'desc', '期望「失败」= 该条件未满足才算通过，允许结束本轮。仅「循环结束时」可配置。'));
    return box;
  }

  function paramCheckEditor(action) {
    var cfg = action.config;
    var box = EV.el('div', 'card');
    box.style.margin = '6px 0 0';
    box.style.background = 'transparent';
    box.style.borderStyle = 'dashed';
    box.appendChild(EV.el('label', null, '参数约束 parameter_check'));
    box.appendChild(EV.el('div', 'desc', '任一项匹配即算使用该工具；一项内多个条件需同时满足。'));

    var items = Array.isArray(cfg.parameter_check) ? cfg.parameter_check.map(function (it) {
      return isPlainObject(it) ? clone(it) : {};
    }) : [];

    function commit() {
      if (items.length) cfg.parameter_check = items;
      else delete cfg.parameter_check;
      touch();
    }

    items.forEach(function (item, idx) {
      var group = EV.el('div', 'card');
      group.style.background = 'var(--field-soft)';
      var gh = EV.el('div', 'card-head');
      gh.appendChild(EV.el('span', 'card-title', '检查项 ' + (idx + 1)));
      gh.appendChild(EV.el('span', null, ''));
      gh.lastChild.style.flex = '1';
      var del = EV.el('button', 'ibtn danger');
      del.innerHTML = EV.icon('trash', 13);
      del.title = '删除该检查项';
      del.onclick = function () { items.splice(idx, 1); commit(); renderBody(); };
      gh.appendChild(del);
      group.appendChild(gh);

      Object.keys(item).forEach(function (k) {
        var row = EV.el('div', 'row');
        row.style.marginBottom = '6px';
        var ki = EV.el('input', 'input');
        ki.style.flex = '0 0 42%';
        ki.value = k;
        var vi = EV.el('input', 'input');
        vi.style.flex = '1';
        vi.value = item[k] === undefined || item[k] === null ? '' : String(item[k]);
        function renameKey() {
          var nk = ki.value.trim();
          if (!nk) return;
          var nv = vi.value;
          delete item[k];
          item[nk] = parseScalar(nv);
          k = nk;
          commit();
        }
        ki.onblur = renameKey;
        vi.onblur = function () { item[k] = parseScalar(vi.value); commit(); };
        var rm = EV.el('button', 'ibtn danger');
        rm.innerHTML = EV.icon('x', 13);
        rm.title = '移除该条件';
        rm.onclick = function () { delete item[k]; commit(); renderBody(); };
        row.appendChild(ki); row.appendChild(vi); row.appendChild(rm);
        group.appendChild(row);
      });

      var addCond = EV.el('button', 'btn sm');
      addCond.innerHTML = EV.icon('plus', 13);
      addCond.appendChild(EV.el('span', null, '新增参数条件'));
      addCond.onclick = function () {
        var n = 1;
        while (Object.prototype.hasOwnProperty.call(item, 'param' + n)) n++;
        item['param' + n] = '';
        commit();
        renderBody();
      };
      group.appendChild(addCond);
      box.appendChild(group);
    });

    var addItem = EV.el('button', 'btn sm');
    addItem.innerHTML = EV.icon('plus', 13);
    addItem.appendChild(EV.el('span', null, '添加检查项'));
    addItem.onclick = function () {
      items.push({ param: '' });
      commit();
      renderBody();
    };
    box.appendChild(addItem);
    return box;
  }

  function skillsEditor(action) {
    var cfg = action.config;
    var box = EV.el('div', 'card');
    box.style.margin = '6px 0 0';
    box.style.background = 'transparent';
    box.style.borderStyle = 'dashed';
    box.appendChild(EV.el('label', null, '技能选择 skills'));

    var selected = Array.isArray(cfg.skills) ? cfg.skills.map(String) : [];
    if (selected.length) {
      var chips = EV.el('div', 'row');
      chips.style.flexWrap = 'wrap';
      chips.style.gap = '6px';
      chips.style.margin = '6px 0';
      selected.forEach(function (name) {
        var chip = EV.el('span', 'chip', '⚡ ' + name);
        chip.style.cursor = 'pointer';
        chip.title = '点击移除';
        chip.onclick = function () {
          var next = selected.filter(function (s) { return s !== name; });
          if (next.length) cfg.skills = next; else delete cfg.skills;
          touch();
          renderBody();
        };
        chips.appendChild(chip);
      });
      box.appendChild(chips);
    }

    var addBtn = EV.el('button', 'btn sm');
    addBtn.innerHTML = EV.icon('plus', 13);
    addBtn.appendChild(EV.el('span', null, '从主库勾选技能'));
    addBtn.onclick = function () { openSkillPicker(selected, action); };
    box.appendChild(addBtn);
    return box;
  }

  function openSkillPicker(selected, action) {
    var wrap = EV.el('div');
    wrap.style.display = 'flex';
    wrap.style.flexDirection = 'column';
    wrap.style.minHeight = '0';
    wrap.style.height = '100%';
    var search = EV.el('input', 'input');
    search.placeholder = '搜索技能关键词…';
    wrap.appendChild(search);
    var listBox = EV.el('div');
    listBox.style.flex = '1';
    listBox.style.minHeight = '260px';
    listBox.style.maxHeight = '46vh';
    listBox.style.overflowY = 'auto';
    listBox.style.marginTop = '10px';
    wrap.appendChild(listBox);

    var checked = {};
    selected.forEach(function (s) { checked[s] = true; });
    var library = [];
    var h = null;

    function paint() {
      listBox.innerHTML = '';
      var kw = search.value.trim().toLowerCase();
      var filtered = library.filter(function (s) {
        return !kw || String(s.name).toLowerCase().indexOf(kw) >= 0 || String(s.description || '').toLowerCase().indexOf(kw) >= 0;
      });
      if (!filtered.length) {
        listBox.appendChild(EV.el('div', 'hint', library.length ? '无匹配的技能' : '主库暂无技能'));
        return;
      }
      filtered.forEach(function (s) {
        var row = EV.el('div', 'item');
        var nm = EV.el('div', 'item-name');
        var cb = EV.el('input');
        cb.type = 'checkbox';
        cb.checked = !!checked[s.name];
        cb.onchange = function () { checked[s.name] = cb.checked; };
        nm.appendChild(cb);
        nm.appendChild(EV.el('span', 'nm', s.name));
        row.appendChild(nm);
        if (s.description) row.appendChild(EV.el('div', 'item-sub', s.description));
        row.onclick = function (e) {
          if (e.target === cb) return;
          cb.checked = !cb.checked;
          checked[s.name] = cb.checked;
        };
        listBox.appendChild(row);
      });
    }

    listBox.appendChild(EV.el('div', 'hint', '正在加载技能…'));
    search.oninput = EV.debounce(paint, 120);

    h = EV.modal({
      title: '从主库勾选技能',
      width: '560px',
      node: wrap,
      actions: [
        { label: '取消' },
        {
          label: '确定', kind: 'primary',
          onClick: function (m) {
            var next = Object.keys(checked).filter(function (k) { return checked[k]; });
            if (next.length) action.config.skills = next;
            else delete action.config.skills;
            touch();
            renderBody();
            m.close();
          }
        }
      ]
    });

    EV.api.get('/api/tools/skills').then(function (data) {
      library = Array.isArray(data) ? data : [];
      paint();
    }).catch(function (e) {
      listBox.innerHTML = '';
      listBox.appendChild(EV.el('div', 'hint err', '获取技能列表失败：' + e.message));
    });
  }

  function extraFieldsEditor(action, schemaKeys, specialKeys) {
    var cfg = action.config;
    var extra = {};
    Object.keys(cfg).forEach(function (k) {
      if (schemaKeys[k] || specialKeys[k]) return;
      extra[k] = cfg[k];
    });
    var keys = Object.keys(extra);
    var details = EV.el('details');
    details.style.marginTop = '6px';
    var summary = EV.el('summary');
    summary.style.cursor = 'pointer';
    summary.style.fontSize = '11.5px';
    summary.style.color = 'var(--dim)';
    summary.textContent = '其它字段（' + keys.length + '）';
    details.appendChild(summary);

    var ta = EV.el('textarea', 'textarea mono');
    ta.rows = 4;
    ta.placeholder = 'JSON 文本（留空则清除这些字段）';
    ta.value = keys.length ? JSON.stringify(extra, null, 2) : '';
    ta.onchange = function () {
      var parsed = null;
      if (ta.value.trim()) {
        try { parsed = JSON.parse(ta.value); }
        catch (e) { EV.toast('JSON 格式有误，未保存', true); ta.style.borderColor = 'var(--err)'; return; }
        if (!isPlainObject(parsed)) { EV.toast('必须是 JSON 对象', true); return; }
      }
      ta.style.borderColor = '';
      Object.keys(cfg).forEach(function (k) {
        if (!schemaKeys[k] && !specialKeys[k]) delete cfg[k];
      });
      Object.keys(parsed || {}).forEach(function (k) { cfg[k] = parsed[k]; });
      touch();
      renderBody();
    };
    details.appendChild(ta);
    return details;
  }

  function renderActionCard(hookKey, action, index) {
    var schema = FIELD_SCHEMA[action.type] || [];
    var schemaKeys = {};
    schema.forEach(function (f) { schemaKeys[f.key] = true; });
    var allowTiming = hookKey === 'on_loop_epoch';
    var allowExpect = hookKey === 'on_loop_end';
    var isParamCheck = action.type === 'tool_use_check';
    var isSkills = action.type === 'skill_info';
    var special = {};
    if (allowTiming) { special.delay = true; special.interval = true; }
    if (allowExpect) special.expect = true;
    if (isParamCheck) special.parameter_check = true;
    if (isSkills) special.skills = true;

    var card = EV.el('div', 'card');
    var head = EV.el('div', 'card-head');
    var dot = EV.el('span', 'chip');
    dot.style.background = 'rgba(15,17,21,.08)';
    dot.style.color = 'var(--ink-2)';
    dot.textContent = '#' + (index + 1);
    head.appendChild(dot);
    head.appendChild(EV.el('span', 'card-title', actionLabel(action.type)));
    var fill = EV.el('span');
    fill.style.flex = '1';
    head.appendChild(fill);
    var del = EV.el('button', 'ibtn danger');
    del.innerHTML = EV.icon('trash', 13);
    del.title = '删除该动作';
    del.onclick = function () {
      var arr = state.hooks[hookKey];
      var i = arr.indexOf(action);
      if (i >= 0) arr.splice(i, 1);
      touch();
      renderBody();
    };
    head.appendChild(del);
    card.appendChild(head);

    if (allowTiming) card.appendChild(timingEditor(hookKey, action));

    schema.filter(function (f) { return isVisible(f, action.config); }).forEach(function (f) {
      card.appendChild(fieldRow(f.label, fieldControl(action, f)));
    });

    if (isSkills) card.appendChild(skillsEditor(action));
    if (isParamCheck) card.appendChild(paramCheckEditor(action));
    if (allowExpect) card.appendChild(expectEditor(action));

    card.appendChild(extraFieldsEditor(action, schemaKeys, special));
    return card;
  }

  function renderHookCard(meta, hooks, loose) {
    var card = EV.el('div', 'card');
    var head = EV.el('div', 'card-head');
    var dot = EV.el('span');
    dot.style.width = '9px';
    dot.style.height = '9px';
    dot.style.borderRadius = '999px';
    dot.style.background = meta.color;
    dot.style.flex = 'none';
    head.appendChild(dot);
    head.appendChild(EV.el('span', 'card-title', meta.label));
    head.appendChild(EV.el('span', 'chip mute', meta.key));
    var fill = EV.el('span');
    fill.style.flex = '1';
    head.appendChild(fill);

    if (!loose) {
      var add = EV.el('button', 'btn sm');
      add.innerHTML = EV.icon('plus', 13);
      add.appendChild(EV.el('span', null, '添加动作'));
      add.onclick = function () { openAddAction(meta.key); };
      head.appendChild(add);
    }
    card.appendChild(head);

    if (hooks.length === 0) {
      card.appendChild(EV.el('div', 'hint', loose ? '（无）' : '暂无动作，点击右上角「添加动作」。'));
      return card;
    }
    hooks.forEach(function (a, i) {
      if (loose) {
        var row = EV.el('div', 'item-sub');
        row.style.marginTop = '4px';
        row.textContent = '• ' + actionLabel(a.type);
        card.appendChild(row);
      } else {
        card.appendChild(renderActionCard(meta.key, a, i));
      }
    });
    return card;
  }

  function openAddAction(hookKey) {
    var wrap = EV.el('div');
    ACTION_TYPES.forEach(function (at) {
      var row = EV.el('div', 'item');
      var nm = EV.el('div', 'item-name', at.label);
      row.appendChild(nm);
      row.appendChild(EV.el('div', 'item-sub', at.type));
      row.onclick = function () {
        state.hooks[hookKey].push({ id: makeActionId(hookKey), type: at.type, config: {} });
        touch();
        renderBody();
        h.close();
      };
      wrap.appendChild(row);
    });
    var h = EV.modal({ title: '添加动作到「' + hookLabel(hookKey) + '」', width: '420px', node: wrap });
  }
  function hookLabel(key) {
    for (var i = 0; i < HOOK_META.length; i++) if (HOOK_META[i].key === key) return HOOK_META[i].label;
    return key;
  }

  /* ---------------- 渲染：主体 ---------------- */
  function renderBody() {
    bodyEl.innerHTML = '';
    if (!state.activeName) {
      var c = EV.el('div', 'center');
      c.innerHTML = EV.icon('loop', 36);
      c.appendChild(EV.el('div', 'big', '从左侧选择一个 paradigm，或新建一个'));
      c.appendChild(EV.el('div', 'sub', 'paradigm 定义了 Agent 主循环在各 Hook 上的动作编排（提示注入、文件操作、技能注入、记忆注入、工具检查、命令执行）。'));
      bodyEl.appendChild(c);
      return;
    }
    var sc = EV.el('div', 'scroll pad');

    // 基础信息
    var base = EV.el('div', 'card');
    var bh = EV.el('div', 'card-head');
    bh.innerHTML = EV.icon('edit', 15);
    bh.appendChild(EV.el('span', 'card-title', '基础信息'));
    base.appendChild(bh);
    [
      { key: 'name', label: '名称 name', kind: 'text' },
      { key: 'description', label: '描述 description', kind: 'text' },
      { key: 'path', label: '工作路径 path', kind: 'text', ph: '例如 agent_vm' },
      { key: 'loop_end_max_retry', label: '循环最大重试 loop_end_max_retry', kind: 'number' }
    ].forEach(function (f) {
      var input = EV.el('input', 'input');
      input.type = f.kind === 'number' ? 'number' : 'text';
      input.placeholder = f.ph || '';
      input.value = state.rootMeta[f.key] === undefined || state.rootMeta[f.key] === null ? '' : String(state.rootMeta[f.key]);
      input.onchange = function () {
        if (input.value === '') delete state.rootMeta[f.key];
        else state.rootMeta[f.key] = f.kind === 'number' ? Number(input.value) : input.value;
        touch();
      };
      base.appendChild(fieldRow(f.label, input));
    });
    sc.appendChild(base);

    // 五个标准 Hook
    HOOK_KEYS.forEach(function (k) {
      var meta = null;
      HOOK_META.forEach(function (m) { if (m.key === k) meta = m; });
      sc.appendChild(renderHookCard(meta, state.hooks[k] || [], false));
    });

    // 附加 Hook（原样保留）
    var extraKeys = Object.keys(state.extraHooks);
    if (extraKeys.length) {
      var ex = EV.el('div', 'card');
      var exHead = EV.el('div', 'card-head');
      exHead.innerHTML = EV.icon('file', 15);
      exHead.appendChild(EV.el('span', 'card-title', '附加 Hook（非标准键，原样保留）'));
      ex.appendChild(exHead);
      extraKeys.forEach(function (k) {
        ex.appendChild(EV.el('div', 'item-sub', k));
      });
      sc.appendChild(ex);
    }

    // 其它顶层字段
    var other = EV.el('div', 'card');
    var oh = EV.el('div', 'card-head');
    oh.innerHTML = EV.icon('file', 15);
    oh.appendChild(EV.el('span', 'card-title', '其它顶层字段（如 trigger）'));
    other.appendChild(oh);
    other.appendChild(EV.el('div', 'desc', '直接编辑 JSON，保存时整体写回。留空表示无附加字段。'));
    var ta = EV.el('textarea', 'textarea mono');
    ta.rows = 8;
    ta.value = state.extraRootText;
    if (state.extraRootErr) ta.style.borderColor = 'var(--err)';
    ta.onchange = function () { state.extraRootText = ta.value; commitExtraRoot(); };
    other.appendChild(ta);
    if (state.extraRootErr) other.appendChild(EV.el('div', 'desc', 'JSON 格式不合法，未应用。'));
    sc.appendChild(other);

    bodyEl.appendChild(sc);
  }

  function renderMain() {
    renderToolbar();
    renderBody();
  }

  EV.defineTab('agentloop', 'Agent Loop', {
    mount: function (root) {
      var side = EV.el('div', 'side');
      side.appendChild(EV.el('div', 'side-head', 'Paradigm 文件'));
      sideBodyEl = EV.el('div', 'side-body');
      side.appendChild(sideBodyEl);
      root.appendChild(side);

      var main = EV.el('div', 'main');
      toolbarEl = EV.el('div', 'toolbar');
      bodyEl = EV.el('div', 'main');
      bodyEl.style.flex = '1';
      bodyEl.style.minHeight = '0';
      main.appendChild(toolbarEl);
      main.appendChild(bodyEl);
      root.appendChild(main);

      refreshExtraRoot();
      renderMain();
      loadFileList();
    },
    onShow: function () { loadFileList(); }
  });
})();