/* ============================================================================
 * 「Agent Loop」标签：与完整模式 AgentLoopEditor 对齐
 *   paradigm（~/.purrcat/paradigms/*.yaml）的查看与编辑：
 *   五个 Hook 的动作编排（含触发时机 / 退出期望 / 参数约束 / 技能选择）
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
    dirty: false
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
  function refreshDirty() {
    state.dirty = JSON.stringify(buildDoc()) !== state.baseline;
  }
  function touch() { refreshDirty(); renderToolbar(); }

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
    var info = await askNewFile();
    if (!info) return;
    var hooks = {};
    HOOK_KEYS.forEach(function (k) { hooks[k] = []; });
    var doc = { name: info.name, description: info.description, path: 'agent_vm', hooks: hooks };
    try {
      await EV.api.post('/api/paradigms/' + encodeURIComponent(info.name), { data: doc });
      EV.toast('已新建 ' + info.name + '.yaml');
      state.dirty = false;
      await loadFileList();
      await openFile(info.name);
    } catch (e) {
      EV.toast('新建失败：' + e.message, true);
    }
  }

  // 新建时只让用户填「名称」与「描述」，其它字段一律使用默认骨架
  function askNewFile() {
    return new Promise(function (resolve) {
      var wrap = EV.el('div');

      var nameField = EV.el('div', 'field');
      nameField.appendChild(EV.el('label', null, '名称（将创建 ~/.purrcat/paradigms/{名称}.yaml）'));
      var nameInput = EV.el('input', 'input');
      nameInput.placeholder = '例如 my_agent_loop';
      nameField.appendChild(nameInput);
      wrap.appendChild(nameField);

      var descField = EV.el('div', 'field');
      descField.appendChild(EV.el('label', null, '描述'));
      var descInput = EV.el('input', 'input');
      descInput.placeholder = '简单描述这个主循环的用途';
      descField.appendChild(descInput);
      wrap.appendChild(descField);

      var answered = false;
      EV.modal({
        title: '新建 Paradigm',
        width: '440px',
        node: wrap,
        actions: [
          { label: '取消', onClick: function (m) { answered = true; resolve(null); m.close(); } },
          {
            label: '创建', kind: 'primary',
            onClick: function (m) {
              var nm = nameInput.value.trim();
              if (!nm) { EV.toast('名称不能为空', true); return; }
              answered = true;
              resolve({ name: nm, description: descInput.value.trim() });
              m.close();
            }
          }
        ],
        onOpen: function () { setTimeout(function () { nameInput.focus(); }, 30); },
        onClose: function () { if (!answered) resolve(null); }
      });
    });
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

    var vizBtn = EV.el('button', 'btn');
    vizBtn.innerHTML = EV.icon('graph', 14);
    vizBtn.appendChild(EV.el('span', null, '可视化'));
    vizBtn.title = '查看当前编排的循环信息流转图';
    vizBtn.disabled = !state.activeName;
    vizBtn.onclick = openVisualize;
    toolbarEl.appendChild(vizBtn);

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

    bodyEl.appendChild(sc);
  }

  function renderMain() {
    renderToolbar();
    renderBody();
  }

  /* ============================================================================
   * 可视化：当前 paradigm 的「循环信息流转图」
   *   对齐完整模式 AgentLoopEditor 的骨架图语义（无 ReactFlow / mermaid，全部手绘 SVG）：
   *     构建系统提示词 → 用户输入 → 循环开始 → 每轮循环迭代 ─┬─(有工具调用)→ 工具调用检查 ─┐
   *                                                        └─(无工具调用)───────────────┴→ 循环结束检查
   *     循环结束检查 ─(失败)→ 回到「每轮循环迭代」；─(成功)→ 结束 → 回到「用户输入」
   * ========================================================================== */
  var VIZ = {
    CW: 268, HEAD_H: 32, ROW_H: 24, PLAIN_H: 52, GAP_V: 54, PAD: 26, X_LEFT: 210
  };
  VIZ.X_RIGHT = VIZ.X_LEFT + 400;
  VIZ.RAIL1 = VIZ.X_LEFT - 62;    // 内轨：结束检查(失败) → 每轮循环迭代
  VIZ.RAIL2 = VIZ.X_LEFT - 124;   // 外轨：结束 → 用户输入
  var VIZ_INK = '#1A1A1A';
  var VIZ_HAND = '"Comic Sans MS", cursive';

  // 卡片高度兜底（DOM 已布局时以实测 offsetHeight 为准）
  function vizStationH(count) {
    return count > 0 ? (VIZ.HEAD_H + count * VIZ.ROW_H + 26) : (VIZ.HEAD_H + 50);
  }

  // 卡片用 DOM 渲染（文字始终原生清晰），画布只让 SVG 承担连线
  var VIZ_CSS = ''
    + '.viz-canvas{position:relative;overflow:hidden;cursor:grab;'
    + 'background:radial-gradient(circle at 1px 1px, rgba(26,26,26,.13) 1px, transparent 0) 0 0/20px 20px, #FDFAF5}'
    + '.viz-canvas.drag{cursor:grabbing}'
    + '.viz-world{position:absolute;left:0;top:0;transform-origin:0 0}'
    + '.viz-edges{position:absolute;left:0;top:0;overflow:visible;pointer-events:none}'
    + '.viz-lbl{font-family:"Comic Sans MS",cursive;font-size:12px;font-weight:700;fill:#1A1A1A;'
    + 'paint-order:stroke;stroke:#FDFAF5;stroke-width:4px;stroke-linejoin:round}'
    + '.viz-card{position:absolute;display:flex;flex-direction:column;background:#fff;'
    + 'border:2px solid #1A1A1A;border-radius:12px;box-shadow:4px 4px 0 rgba(26,26,26,1);overflow:hidden}'
    + '.viz-card.plain{align-items:center;justify-content:center}'
    + '.viz-pt{font-family:"Comic Sans MS",cursive;font-size:15px;font-weight:800;color:#1A1A1A}'
    + '.viz-ch{display:flex;align-items:center;gap:8px;padding:0 10px;border-bottom:2px solid rgba(26,26,26,.16);flex:none}'
    + '.viz-dot{width:12px;height:12px;flex:none;border:2px solid #1A1A1A;border-radius:3px}'
    + '.viz-ct{flex:1;min-width:0;font-family:"Comic Sans MS",cursive;font-size:13px;font-weight:800;color:#1A1A1A;'
    + 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'
    + '.viz-cn{flex:none;font-size:11px;font-weight:800;line-height:16px;padding:0 6px;color:#1A1A1A;'
    + 'background:#F7F3EA;border:2px solid #1A1A1A;border-radius:6px}'
    + '.viz-cb{display:flex;flex-direction:column;gap:4px;padding:5px 10px 6px}'
    + '.viz-row{display:flex;align-items:center;gap:6px;padding:0 6px;background:#F7F3EA;'
    + 'border:1.5px solid rgba(26,26,26,.78);border-radius:6px}'
    + '.viz-ri{flex:none;font-size:10.5px;font-weight:800;color:rgba(26,26,26,.45)}'
    + '.viz-rl{flex:1;min-width:0;font-family:"Comic Sans MS",cursive;font-size:12px;font-weight:800;color:#1A1A1A;'
    + 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}'
    + '.viz-rt{flex:none;font-size:10.5px;color:rgba(26,26,26,.45)}'
    + '.viz-empty{height:20px;display:flex;align-items:center;justify-content:center;'
    + 'border:2px dashed rgba(26,26,26,.28);border-radius:6px;'
    + 'font-family:"Comic Sans MS",cursive;font-size:11px;color:rgba(26,26,26,.42)}'
    + '.viz-ck{padding:0 10px 5px;font-size:10px;color:rgba(26,26,26,.35)}'
    + '.viz-hint{flex:none;padding:8px 14px;border-top:1px solid rgba(15,17,21,.08);'
    + 'font-size:11.5px;line-height:1.7;color:#8b96a3}';

  function vizInjectStyle() {
    if (document.getElementById('viz-style')) return;
    var st = document.createElement('style');
    st.id = 'viz-style';
    st.textContent = VIZ_CSS;
    document.head.appendChild(st);
  }
  function sEl(tag, attrs) {
    var n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function sText(x, y, str, o) {
    o = o || {};
    var t = sEl('text', {
      x: x, y: y,
      fill: o.fill || VIZ_INK,
      'font-size': o.size || 12,
      'font-weight': o.weight || 700,
      'text-anchor': o.anchor || 'start'
    });
    if (o.hand) t.setAttribute('font-family', VIZ_HAND);
    t.textContent = str;
    if (o.bg) {   // 文字压在连线上时用描边留白（等于给文字加白底）
      t.setAttribute('paint-order', 'stroke');
      t.setAttribute('stroke', o.bg);
      t.setAttribute('stroke-width', '4');
      t.setAttribute('stroke-linejoin', 'round');
    }
    return t;
  }

  // 卡片锚点：侧向锚点取「头部中线」（与完整模式一样走顶部固定锚点，保证连线恒为水平）
  function vizAnchor(n, where) {
    var sideY = n.kind === 'plain' ? n.y + n.h / 2 : n.y + VIZ.HEAD_H / 2;
    if (where === 'top') return [n.x + n.w / 2, n.y];
    if (where === 'bottom') return [n.x + n.w / 2, n.y + n.h];
    if (where === 'left') return [n.x, sideY];
    if (where === 'right') return [n.x + n.w, sideY];
    if (where === 'leftTop') return [n.x, n.y + 20];
    if (where === 'rightTop') return [n.x + n.w, n.y + 20];
    if (where === 'leftLow') return [n.x, n.y + n.h - 11];
    return [n.x + n.w, n.y + n.h - 11];   // rightLow
  }

  // measure(n) 由调用方提供：先建卡片再量高度，保证连线锚点与 DOM 实际高度一致
  function buildVizModel(measure) {
    var nodes = [];
    var hOf = measure || function (n) {
      return n.kind === 'station' ? vizStationH(n.items.length) : VIZ.PLAIN_H;
    };
    function station(key, x, y) {
      var actions = state.hooks[key] || [];
      var meta = null;
      HOOK_META.forEach(function (m) { if (m.key === key) meta = m; });
      var n = {
        id: key, kind: 'station', key: key, label: hookLabel(key),
        color: (meta && meta.color) || '#cccccc', items: actions,
        x: x, y: y, w: VIZ.CW, h: 0
      };
      n.h = hOf(n);
      nodes.push(n);
      return n;
    }
    function plain(id, label, x, y) {
      var n = { id: id, kind: 'plain', label: label, x: x, y: y, w: VIZ.CW, h: 0 };
      n.h = hOf(n);
      nodes.push(n);
      return n;
    }

    var cur = VIZ.PAD;
    var b = station('on_build_system_prompt', VIZ.X_LEFT, cur);
    cur += b.h + VIZ.GAP_V;
    var ui = plain('user_input', '用户输入', VIZ.X_LEFT, cur);
    cur += ui.h + VIZ.GAP_V;
    var st = station('on_loop_start', VIZ.X_LEFT, cur);
    cur += st.h + VIZ.GAP_V;

    var ep = station('on_loop_epoch', VIZ.X_LEFT, cur);
    var tc = station('on_tool_calling', VIZ.X_RIGHT, cur);
    var rowBottom = cur + Math.max(ep.h, tc.h);
    var ec = station('on_loop_end', VIZ.X_LEFT, rowBottom + VIZ.GAP_V);
    var end = plain('end', '结束', VIZ.X_LEFT, ec.y + ec.h + VIZ.GAP_V);

    var edges = [];
    function edge(pts, label, labelAt, anchor) {
      edges.push({ pts: pts, label: label, labelAt: labelAt, anchor: anchor });
    }
    // 主干
    edge([vizAnchor(b, 'bottom'), vizAnchor(ui, 'top')]);
    edge([vizAnchor(ui, 'bottom'), vizAnchor(st, 'top')]);
    edge([vizAnchor(st, 'bottom'), vizAnchor(ep, 'top')]);
    // 分支：有工具调用 → 走顶部锚点的水平线；无工具调用 → 直达结束检查
    var rTop = vizAnchor(ep, 'rightTop'), lTop = vizAnchor(tc, 'leftTop');
    edge([rTop, lTop], '有工具调用', [(rTop[0] + lTop[0]) / 2, rTop[1] - 9], 'middle');
    var eBot = vizAnchor(ep, 'bottom'), ecTop = vizAnchor(ec, 'top');
    edge([eBot, ecTop], '无工具调用', [eBot[0] + 9, (eBot[1] + ecTop[1]) / 2]);
    // 工具调用检查通过 → 走底部锚点水平回到「每轮循环迭代」
    edge([vizAnchor(tc, 'leftLow'), vizAnchor(ep, 'rightLow')]);
    // 环 1：结束检查未通过 → 左侧内轨绕回「每轮循环迭代」
    var ecLeft = vizAnchor(ec, 'left'), epLeft = vizAnchor(ep, 'left');
    var p1b = [VIZ.RAIL1, ecLeft[1]], p1t = [VIZ.RAIL1, epLeft[1]];
    edge([ecLeft, p1b, p1t, epLeft], '失败，继续下一轮', [VIZ.RAIL1 - 9, (p1t[1] + p1b[1]) / 2], 'end');
    // 通过 → 结束
    var ecBot = vizAnchor(ec, 'bottom'), endTop = vizAnchor(end, 'top');
    edge([ecBot, endTop], '成功，结束', [ecBot[0] + 9, (ecBot[1] + endTop[1]) / 2]);
    // 环 2：结束后 → 最外侧轨道回到「用户输入」（下一轮任务）
    var endLeft = vizAnchor(end, 'left'), uiLeft = vizAnchor(ui, 'left');
    edge([endLeft, [VIZ.RAIL2, endLeft[1]], [VIZ.RAIL2, uiLeft[1]], uiLeft]);

    return {
      nodes: nodes, edges: edges,
      w: VIZ.X_RIGHT + VIZ.CW + VIZ.PAD,
      h: end.y + end.h + VIZ.PAD
    };
  }

  // Hook 站卡片 / 普通节点卡片：全部用 DOM，文字不参与缩放栅格化
  function vizCardEl(n) {
    var card = EV.el('div', 'viz-card' + (n.kind === 'plain' ? ' plain' : ''));
    card.style.left = n.x + 'px';
    card.style.top = n.y + 'px';
    card.style.width = n.w + 'px';
    if (n.kind === 'plain') {
      card.style.height = n.h + 'px';
      card.appendChild(EV.el('div', 'viz-pt', n.label));
      return card;
    }
    var head = EV.el('div', 'viz-ch');
    head.style.height = VIZ.HEAD_H + 'px';
    var dot = EV.el('span', 'viz-dot');
    dot.style.background = n.color;
    head.appendChild(dot);
    head.appendChild(EV.el('span', 'viz-ct', n.label));
    head.appendChild(EV.el('span', 'viz-cn', String(n.items.length)));
    card.appendChild(head);

    var body = EV.el('div', 'viz-cb');
    if (!n.items.length) {
      body.appendChild(EV.el('div', 'viz-empty', '（无动作）'));
    } else {
      n.items.forEach(function (a, i) {
        var row = EV.el('div', 'viz-row');
        row.style.height = (VIZ.ROW_H - 4) + 'px';
        row.appendChild(EV.el('span', 'viz-ri', String(i + 1)));
        row.appendChild(EV.el('span', 'viz-rl', actionLabel(a.type)));
        row.appendChild(EV.el('span', 'viz-rt', a.type));
        body.appendChild(row);
      });
    }
    card.appendChild(body);
    card.appendChild(EV.el('div', 'viz-ck', n.key));
    return card;
  }

  function vizDrawEdges(svg, model) {
    var defs = sEl('defs');
    var marker = sEl('marker', {
      id: 'viz-arrow', viewBox: '0 0 10 10', refX: '9', refY: '5',
      markerWidth: '5', markerHeight: '5', orient: 'auto-start-reverse'
    });
    marker.appendChild(sEl('path', { d: 'M0 0 L10 5 L0 10 z', fill: VIZ_INK }));
    defs.appendChild(marker);
    svg.appendChild(defs);

    // 直角折线 + 末端箭头（卡片是 DOM 之后绘制，自然遮住穿过的线段）
    model.edges.forEach(function (e) {
      var d = e.pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0] + ' ' + p[1]; }).join(' ');
      svg.appendChild(sEl('path', {
        d: d, fill: 'none', stroke: VIZ_INK, 'stroke-width': 2,
        'stroke-linejoin': 'round', 'marker-end': 'url(#viz-arrow)'
      }));
      if (e.label) {
        var t = sText(e.labelAt[0], e.labelAt[1], e.label,
          { size: 12, hand: true, anchor: e.anchor || 'start' });
        t.setAttribute('class', 'viz-lbl');
        svg.appendChild(t);
      }
    });
  }

  function openVisualize() {
    if (!state.activeName) { EV.toast('请先打开或新建一个 paradigm', true); return; }
    vizInjectStyle();

    var svg = sEl('svg', { 'class': 'viz-edges' });
    var world = EV.el('div', 'viz-world');
    world.appendChild(svg);
    var canvas = EV.el('div', 'viz-canvas');
    // 画布子元素全是绝对定位，必须给一个确定高度，否则弹层会被压塌
    canvas.style.flex = 'none';
    canvas.style.height = 'calc(88vh - 126px)';
    canvas.style.minHeight = '320px';
    canvas.appendChild(world);

    var inner = EV.el('div');
    inner.style.display = 'flex';
    inner.style.flexDirection = 'column';
    inner.style.flex = '1';
    inner.style.minHeight = '0';
    inner.appendChild(canvas);
    inner.appendChild(EV.el('div', 'viz-hint',
      '箭头表示信息流转方向；「有工具调用 / 无工具调用 / 失败 / 成功」为分支条件。'
      + '拖拽平移、滚轮缩放；该图随当前编辑内容实时生成，保存前后皆可预览。'));

    var model = null;
    var view = { x: 20, y: 20, s: 1 };

    var pct = EV.el('button', 'ibtn');
    pct.style.width = 'auto';
    pct.style.padding = '0 7px';
    pct.style.fontSize = '11.5px';
    pct.style.fontWeight = '800';
    pct.title = '恢复 100%（1:1 原尺寸，文字最清晰）';
    pct.onclick = function () { setScale(1); };

    function applyView() {
      world.style.transform = 'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.s + ')';
      pct.textContent = Math.round(view.s * 100) + '%';
    }
    function setScale(s) {
      view.s = Math.max(0.3, Math.min(2, s));
      var cw = canvas.clientWidth || 900;
      view.x = Math.max(20, Math.round((cw - model.w * view.s) / 2));
      view.y = 20;
      applyView();
    }
    function fit() {
      var cw = canvas.clientWidth || 900, ch = canvas.clientHeight || 600;
      view.s = Math.max(0.3, Math.min(1.2, (cw - 40) / model.w, (ch - 40) / model.h));
      view.x = Math.max(20, Math.round((cw - model.w * view.s) / 2));
      view.y = Math.max(20, Math.round((ch - model.h * view.s) / 2));
      applyView();
    }

    var bar = EV.el('div', 'row');
    bar.style.gap = '2px';
    bar.style.marginLeft = 'auto';
    var minus = EV.el('button', 'ibtn');
    minus.innerHTML = EV.icon('zoomOut', 14);
    minus.title = '缩小';
    minus.onclick = function () { setScale(view.s / 1.2); };
    var plus = EV.el('button', 'ibtn');
    plus.innerHTML = EV.icon('zoomIn', 14);
    plus.title = '放大';
    plus.onclick = function () { setScale(view.s * 1.2); };
    var fitBtn = EV.el('button', 'ibtn');
    fitBtn.innerHTML = EV.icon('fit', 14);
    fitBtn.title = '适应窗口';
    fitBtn.onclick = fit;
    bar.appendChild(minus); bar.appendChild(pct); bar.appendChild(plus); bar.appendChild(fitBtn);

    // 空白处按下拖拽平移
    canvas.addEventListener('pointerdown', function (e) {
      if (e.target !== canvas && e.target !== world && e.target !== svg) return;
      canvas.classList.add('drag');
      var sx = e.clientX, sy = e.clientY, ox = view.x, oy = view.y;
      function move(ev) {
        view.x = ox + (ev.clientX - sx);
        view.y = oy + (ev.clientY - sy);
        applyView();
      }
      function up() {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        canvas.classList.remove('drag');
      }
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
    });
    // 滚轮以指针位置为锚点缩放
    canvas.addEventListener('wheel', function (e) {
      e.preventDefault();
      var r = canvas.getBoundingClientRect();
      var mx = e.clientX - r.left, my = e.clientY - r.top;
      var wx = (mx - view.x) / view.s, wy = (my - view.y) / view.s;
      view.s = Math.max(0.3, Math.min(2, view.s * (e.deltaY < 0 ? 1.1 : 1 / 1.1)));
      view.x = mx - wx * view.s;
      view.y = my - wy * view.s;
      applyView();
    }, { passive: false });

    EV.modal({
      title: '循环可视化 — ' + state.activeName + '.yaml',
      width: '1180px',
      flush: true,
      node: inner,
      headExtra: bar,
      onOpen: function () {
        // 卡片先进 DOM 再量高度，坐标与连线锚点才能和实际渲染一致
        model = buildVizModel(function (n) {
          var el = vizCardEl(n);
          world.appendChild(el);
          return el.offsetHeight || (n.kind === 'station' ? vizStationH(n.items.length) : VIZ.PLAIN_H);
        });
        svg.setAttribute('width', model.w);
        svg.setAttribute('height', model.h);
        svg.setAttribute('viewBox', '0 0 ' + model.w + ' ' + model.h);
        vizDrawEdges(svg, model);
        setScale(1);   // 默认 1:1（文字原生清晰），需要总览时再点「适应窗口」
      }
    });
  }

  EV.defineTab('agentloop', 'Agent Loop', {
    mount: function (root) {
      var side = EV.el('div', 'side');
      var sideHead = EV.el('div', 'side-head');
      sideHead.appendChild(EV.el('span', null, 'Paradigm 文件'));
      sideHead.appendChild(EV.el('span', 'spacer'));
      EV.attachSideToggle(side, sideHead);
      side.appendChild(sideHead);
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

      renderMain();
      loadFileList();
    },
    onShow: function () { loadFileList(); }
  });
})();