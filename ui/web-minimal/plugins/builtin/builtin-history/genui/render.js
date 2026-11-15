/* PurrCat GenUI —— 虚拟节点、动作执行与挂载 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function flatten(children) {
    var out = [];
    (children || []).forEach(function (c) {
      if (c == null || c === false) return;
      if (Array.isArray(c)) out = out.concat(flatten(c));
      else out.push(c);
    });
    return out;
  }

  function h(tag, props, children) {
    var v = { tag: tag, cls: '', style: null, attrs: null, text: null, html: null, on: null, ref: null };
    props = props || {};
    Object.keys(props).forEach(function (k) { v[k] = props[k]; });
    v.children = flatten(children);
    return v;
  }

  function t(text) { return { tag: '#text', text: String(text == null ? '' : text) }; }
  function raw(html) { return { tag: '#raw', html: String(html == null ? '' : html) }; }
  function frag(children) { return h('#frag', {}, children); }

  var VOID = { img: 1, br: 1, hr: 1, input: 1, circle: 1, ellipse: 1, rect: 1, line: 1, path: 1, polyline: 1, polygon: 1, use: 1 };
  var SVG_TAGS = { svg: 1, g: 1, circle: 1, ellipse: 1, rect: 1, line: 1, path: 1, polyline: 1, polygon: 1, text: 1, tspan: 1, defs: 1, linearGradient: 1, radialGradient: 1, stop: 1, use: 1, mask: 1, clipPath: 1 };

  function createEl(tag) {
    if (typeof document !== 'undefined' && SVG_TAGS[tag]) return document.createElementNS('http://www.w3.org/2000/svg', tag);
    return document.createElement(tag);
  }

  function styleText(style) {
    if (!style) return '';
    return Object.keys(style).filter(function (k) { return style[k] != null && style[k] !== ''; }).map(function (k) {
      var name = k.replace(/[A-Z]/g, function (m) { return '-' + m.toLowerCase(); });
      return name + ':' + style[k];
    }).join(';');
  }

  function toHTML(v) {
    if (v == null || v === false) return '';
    if (typeof v === 'string' || typeof v === 'number') return esc(v);
    if (Array.isArray(v)) return v.map(toHTML).join('');
    if (v.tag === '#text') return esc(v.text);
    if (v.tag === '#raw') return v.html;
    if (v.tag === '#frag') return toHTML(v.children);
    var attrs = '';
    if (v.cls) attrs += ' class="' + esc(v.cls) + '"';
    if (v.style) attrs += ' style="' + esc(styleText(v.style)) + '"';
    if (v.attrs) {
      Object.keys(v.attrs).forEach(function (k) {
        var val = v.attrs[k];
        if (val == null || val === false) return;
        attrs += ' ' + k + (val === true ? '' : '="' + esc(val) + '"');
      });
    }
    var inner = v.html != null ? v.html : (v.text != null ? esc(v.text) : toHTML(v.children));
    if (SVG_TAGS[v.tag]) {
      if (!inner) return '<' + v.tag + attrs + ' />';
      return '<' + v.tag + attrs + '>' + inner + '</' + v.tag + '>';
    }
    if (VOID[v.tag]) return '<' + v.tag + attrs + '>';
    return '<' + v.tag + attrs + '>' + inner + '</' + v.tag + '>';
  }

  function toDOM(v, ctx) {
    if (v == null || v === false) return null;
    if (typeof v === 'string' || typeof v === 'number') return document.createTextNode(String(v));
    if (Array.isArray(v)) {
      var box = document.createDocumentFragment();
      v.forEach(function (item) { var el = toDOM(item, ctx); if (el) box.appendChild(el); });
      return box;
    }
    if (v.tag === '#text') return document.createTextNode(v.text);
    if (v.tag === '#raw') {
      var rawBox = document.createElement('div');
      rawBox.innerHTML = v.html;
      if (rawBox.childNodes.length === 1) return rawBox.firstChild;
      var fragEl = document.createDocumentFragment();
      while (rawBox.firstChild) fragEl.appendChild(rawBox.firstChild);
      return fragEl;
    }
    if (v.tag === '#frag') {
      var f = document.createDocumentFragment();
      (v.children || []).forEach(function (item) { var el = toDOM(item, ctx); if (el) f.appendChild(el); });
      return f;
    }
    var el = createEl(v.tag);
    if (v.cls) {
      if (SVG_TAGS[v.tag]) el.setAttribute('class', v.cls);
      else el.className = v.cls;
    }
    if (v.style) Object.keys(v.style).forEach(function (k) {
      if (v.style[k] != null && v.style[k] !== '') el.style[k] = v.style[k];
    });
    if (v.attrs) Object.keys(v.attrs).forEach(function (k) {
      var val = v.attrs[k];
      if (val == null || val === false) return;
      if (k === 'value') { el.value = val; return; }
      if (k === 'checked') { el.checked = !!val; return; }
      el.setAttribute(k, val === true ? '' : String(val));
    });
    if (v.html != null) el.innerHTML = v.html;
    else if (v.text != null) el.textContent = v.text;
    else (v.children || []).forEach(function (child) {
      var c = toDOM(child, ctx);
      if (c) el.appendChild(c);
    });
    if (v.on && ctx) Object.keys(v.on).forEach(function (ev) { el.addEventListener(ev, v.on[ev]); });
    if (v.ref && ctx && ctx.collect) {
      try {
        var cleanup = v.ref(el, ctx);
        if (typeof cleanup === 'function') ctx.collect.push(cleanup);
      } catch (e) { /* 组件自身的挂载失败不应中断整棵树 */ }
    }
    return el;
  }

  var COLOR_VARS = {
    ink: 'var(--gui-ink)', muted: 'var(--gui-muted)', faint: 'var(--gui-faint)',
    surface: 'var(--gui-surface)', info: 'var(--gui-info)', success: 'var(--gui-success)',
    warning: 'var(--gui-warning)', danger: 'var(--gui-danger)', purple: 'var(--gui-purple)',
    pink: 'var(--gui-pink)', primary: 'var(--gui-accent)', accent: 'var(--gui-accent)',
    chart1: 'var(--gui-chart-1)', chart2: 'var(--gui-chart-2)', chart3: 'var(--gui-chart-3)',
    chart4: 'var(--gui-chart-4)', chart5: 'var(--gui-chart-5)', chart6: 'var(--gui-chart-6)'
  };
  var TINT_VARS = {
    info: 'var(--gui-info-soft)', success: 'var(--gui-success-soft)', warning: 'var(--gui-warning-soft)',
    danger: 'var(--gui-danger-soft)', purple: 'var(--gui-purple-soft)', pink: 'var(--gui-pink-soft)',
    surface: 'var(--gui-surface)', ink: 'var(--gui-ink-soft)'
  };

  function color(name, tint) {
    if (name == null || name === '') return null;
    var key = String(name);
    if (Object.prototype.hasOwnProperty.call(COLOR_VARS, key)) return (tint && TINT_VARS[key]) || COLOR_VARS[key];
    return key;
  }

  function gap(v) {
    if (v == null || v === '') return null;
    var n = Number(v);
    return isFinite(n) ? (n * 4) + 'px' : String(v);
  }

  function len(v) {
    if (v == null || v === '') return null;
    var n = Number(v);
    return isFinite(n) ? n + 'px' : String(v);
  }

  var RADIUS = { sm: '6px', md: '10px', lg: '14px', xl: '20px', full: '999px' };
  function radius(v) {
    if (v == null || v === '') return null;
    return RADIUS[String(v)] || len(v);
  }

  var ALIGN = { start: 'flex-start', center: 'center', end: 'flex-end', stretch: 'stretch' };
  var JUSTIFY = { start: 'flex-start', center: 'center', end: 'flex-end', between: 'space-between', around: 'space-around', evenly: 'space-evenly' };

  function runAction(action, ctx) {
    if (!action) return;
    var steps = action.__action ? action.__action : (Array.isArray(action) ? action : [action]);
    steps.forEach(function (step) {
      if (!step || !step.__step) return;
      try {
        if (step.__step === 'ToAssistant') {
          var payload = step.context;
          if (ctx.formValues) {
            var values = ctx.formValues();
            if (values && Object.keys(values).length) payload = Object.assign({}, payload || {}, { values: values });
          }
          if (ctx.onMessage) ctx.onMessage(step.text, payload);
        } else if (step.__step === 'OpenUrl') {
          if (ctx.onOpenUrl) ctx.onOpenUrl(step.url);
          else if (typeof window !== 'undefined') window.open(step.url, '_blank', 'noopener');
        } else if (step.__step === 'Set') {
          if (step.name && ctx.setState) ctx.setState(step.name, step.value);
        } else if (step.__step === 'Reset') {
          if (ctx.resetState) ctx.resetState(step.names);
        } else if (step.__step === 'CopyToClipboard') {
          if (ctx.onCopy) ctx.onCopy(step.text);
          else if (g.navigator && g.navigator.clipboard) g.navigator.clipboard.writeText(step.text);
        }
      } catch (e) { /* 单个动作失败不影响后续步骤 */ }
    });
  }

  /* 把求值结果转换为 vnode；ctx 由 mount 提供 */
  function value(node, ctx) {
    if (node == null || node === false) return null;
    if (node instanceof G.Binding) return value(node.value, ctx);
    if (Array.isArray(node)) return node.map(function (n) { return value(n, ctx); });
    if (typeof node === 'object' && node.__node) {
      var renderer = G.components[node.type];
      if (!renderer) {
        return h('div', { cls: 'gui-unknown' }, [t('未知组件 ' + node.type)]);
      }
      try { return renderer(node.args || [], ctx || {}); }
      catch (e) { return h('div', { cls: 'gui-error' }, [t(node.type + ': ' + (e && e.message ? e.message : String(e)))]); }
    }
    if (typeof node === 'object') return null;
    if (typeof node === 'boolean') return null;
    return t(node);
  }

  function valueHTML(node, ctx) { return toHTML(value(node, ctx)); }

  G.h = h;
  G.t = t;
  G.raw = raw;
  G.frag = frag;
  G.esc = esc;
  G.toHTML = toHTML;
  G.toDOM = toDOM;
  G.color = color;
  G.gap = gap;
  G.len = len;
  G.radius = radius;
  G.ALIGN = ALIGN;
  G.JUSTIFY = JUSTIFY;
  G.runAction = runAction;
  G.value = value;
  G.valueHTML = valueHTML;
  G.components = G.components || {};
})(typeof globalThis !== 'undefined' ? globalThis : this);
