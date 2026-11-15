/* PurrCat GenUI —— 对外接口与挂载运行时 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};

  function allFunctions() {
    var out = {};
    Object.keys(G.functions || {}).forEach(function (k) { out[k] = G.functions[k]; });
    Object.keys(G.actions || {}).forEach(function (k) { out[k] = G.actions[k]; });
    return out;
  }

  function renderHTML(source, state) {
    var doc = G.parse(String(source == null ? '' : source));
    var evaluated = G.evaluate(doc, state || {}, { functions: allFunctions(), components: G.components });
    if (evaluated.root == null) return '<div class="gui-empty">没有可渲染的内容（缺少 root）</div>';
    var ctx = { runtime: {}, formStack: [] };
    return G.toHTML(G.value(evaluated.root, ctx));
  }

  function mount(el, source, options) {
    options = options || {};
    var doc;
    try {
      doc = G.parse(String(source == null ? '' : source));
    } catch (err) {
      el.innerHTML = '<div class="gui-error">DSL 解析失败：' + G.esc(err && err.message ? err.message : String(err)) + '</div>';
      return null;
    }
    var state = options.state || {};
    var runtime = {};
    var cleanups = [];
    var scheduled = null;
    var destroyed = false;

    var ctx = {
      runtime: runtime,
      formStack: [],
      collect: null,
      getState: function () { return state; },
      schedule: schedule,
      setState: function (name, value) { if (name) { state[name] = value; schedule(); } },
      resetState: function (names) {
        var targets = names && names.length ? names : Array.from(doc.stateDefs.keys());
        targets.forEach(function (name) { delete state[name]; });
        schedule();
      },
      onMessage: options.onMessage,
      onOpenUrl: options.onOpenUrl,
      onCopy: options.onCopy
    };

    function clearRefs() {
      cleanups.forEach(function (fn) { try { fn(); } catch (e) { /* 忽略清理异常 */ } });
      cleanups = [];
    }

    function render() {
      if (destroyed) return;
      var active = typeof document !== 'undefined' ? document.activeElement : null;
      var bindName = active && active.getAttribute ? active.getAttribute('data-bind') : null;
      var selStart = null, selEnd = null;
      if (bindName && active && typeof active.selectionStart === 'number') {
        try { selStart = active.selectionStart; selEnd = active.selectionEnd; } catch (e) { selStart = null; }
      }
      var evaluated;
      try {
        evaluated = G.evaluate(doc, state, { functions: allFunctions(), components: G.components });
      } catch (err) {
        el.innerHTML = '<div class="gui-error">DSL 求值失败：' + G.esc(err && err.message ? err.message : String(err)) + '</div>';
        return;
      }
      clearRefs();
      ctx.collect = cleanups;
      ctx.formStack = [];
      var vnode = G.value(evaluated.root, ctx);
      var dom = G.toDOM(vnode, ctx);
      while (el.firstChild) el.removeChild(el.firstChild);
      if (dom) el.appendChild(dom);
      if (!el.firstChild) {
        el.innerHTML = '<div class="gui-empty">没有可渲染的内容（缺少 root）</div>';
        return;
      }
      if (bindName) {
        var escaped = String(bindName).replace(/"/g, '\\"');
        var next = el.querySelector('[data-bind="' + escaped + '"]');
        if (next && typeof next.focus === 'function') {
          next.focus();
          if (selStart != null && typeof next.setSelectionRange === 'function') {
            try { next.setSelectionRange(selStart, selEnd); } catch (e) { /* 部分输入类型不支持选区 */ }
          }
        }
      }
    }

    function schedule() {
      if (scheduled || destroyed) return;
      scheduled = setTimeout(function () { scheduled = null; render(); }, 160);
    }

    render();

    return {
      rerender: render,
      destroy: function () {
        destroyed = true;
        if (scheduled) { clearTimeout(scheduled); scheduled = null; }
        clearRefs();
        while (el.firstChild) el.removeChild(el.firstChild);
      },
      getState: function () { return state; }
    };
  }

  G.renderHTML = renderHTML;
  G.mount = mount;
  G.version = '1.0.0';
})(typeof globalThis !== 'undefined' ? globalThis : this);
