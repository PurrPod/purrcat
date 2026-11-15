/* PurrCat GenUI —— 输入与表单组件 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var h = G.h, t = G.t, U = G.util;
  var C = G.components;

  function icon(name, size, ctx) {
    if (!name) return null;
    return G.components.Icon ? G.components.Icon([name, size || 'sm'], ctx) : null;
  }

  function collect(ctx, binding) {
    if (!ctx || !ctx.formStack || !binding) return;
    var top = ctx.formStack[ctx.formStack.length - 1];
    if (top && top.indexOf(binding.name) < 0) top.push(binding.name);
  }

  function readBound(v, fallback) {
    var b = U.bindArg(v);
    if (b) return b.value == null ? fallback : b.value;
    var p = G.plain(v);
    return p == null ? fallback : p;
  }

  function wire(el, binding, ctx, transform) {
    if (!binding || !ctx || !ctx.schedule) return;
    function commit() {
      binding.set(transform ? transform(el.value) : el.value);
      ctx.schedule();
    }
    el.addEventListener('input', function (e) { if (!e.isComposing) commit(); });
    el.addEventListener('change', commit);
    el.addEventListener('compositionend', commit);
  }

  function fieldWrap(label, control, extra) {
    if (!label) return control;
    return h('label', { cls: 'gui-field' }, [
      h('span', { cls: 'gui-field-label' }, [t(label)]),
      control,
      extra || null
    ]);
  }

  C.Button = function (args, ctx) {
    var label = U.str(args[0]);
    var action = args[1];
    var variant = U.arg(args, 2) || 'solid';
    var color = U.arg(args, 3) || 'primary';
    var size = U.arg(args, 4) || 'md';
    var block = U.truthy(args[7]);
    var disabled = U.truthy(args[6]);
    var cls = 'gui-btn gui-btn-' + variant + ' gui-btn-color-' + color + ' gui-btn-' + size + (block ? ' gui-btn-block' : '');
    return h('button', {
      cls: cls,
      attrs: { type: 'button', disabled: disabled || null },
      ref: function (el) {
        el.addEventListener('click', function () {
          var local = Object.assign({}, ctx);
          if (ctx.formStack && ctx.formStack.length) {
            var names = ctx.formStack[0] || [];
            local.formValues = function () {
              var state = ctx.getState ? ctx.getState() : {};
              var out = {};
              names.forEach(function (n) { if (state[n] != null) out[n] = state[n]; });
              return out;
            };
          }
          G.runAction(action || { __step: 'ToAssistant', text: label }, local);
        });
        return function () {};
      }
    }, [icon(U.arg(args, 5), 'sm', ctx), h('span', {}, [t(label)])]);
  };

  C.IconButton = function (args, ctx) {
    var name = U.str(args[0]);
    var action = args[1];
    var label = U.str(args[2]);
    var variant = U.arg(args, 3) || 'ghost';
    return h('button', {
      cls: 'gui-icon-btn gui-btn-' + variant,
      attrs: { type: 'button', title: label || name, 'aria-label': label || name },
      ref: function (el) {
        el.addEventListener('click', function () { G.runAction(action, Object.assign({}, ctx)); });
        return function () {};
      }
    }, [icon(name, 'md', ctx)]);
  };

  C.Pressable = function (args, ctx) {
    var s = { padding: G.gap(args[3]) || '8px', borderRadius: G.radius(args[5]) || '10px', cursor: 'pointer' };
    var bg = G.color(U.arg(args, 4), true);
    if (bg) s.background = bg;
    var selected = U.truthy(args[2]);
    return h('div', {
      cls: 'gui-pressable' + (selected ? ' selected' : ''),
      style: s,
      attrs: { role: 'button', tabindex: '0' },
      ref: function (el) {
        el.addEventListener('click', function () { G.runAction(args[1], Object.assign({}, ctx)); });
        return function () {};
      }
    }, U.children(args[0], ctx));
  };

  C.Input = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var type = U.arg(args, 2) === 'number' ? 'number' : 'text';
    var value = readBound(args[0], '');
    var el = h('input', {
      cls: 'gui-input',
      attrs: {
        type: type,
        value: value == null ? '' : String(value),
        placeholder: U.str(args[3]) || null,
        'data-bind': binding ? binding.name : null
      },
      ref: function (node) {
        wire(node, binding, ctx, type === 'number'
          ? function (v) { return v === '' ? null : Number(v); }
          : null);
        return function () {};
      }
    });
    return fieldWrap(U.str(args[1]), el);
  };

  C.TextArea = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var el = h('textarea', {
      cls: 'gui-input gui-textarea',
      attrs: {
        placeholder: U.str(args[2]) || null,
        rows: U.numArg(U.arg(args, 3), 3) || 3,
        'data-bind': binding ? binding.name : null
      }
    }, [t(readBound(args[0], ''))]);
    el.ref = function (node) { wire(node, binding, ctx); return function () {}; };
    return fieldWrap(U.str(args[1]), el);
  };

  function optionPairs(v) {
    return U.arr(v).map(function (o) {
      if (o && typeof o === 'object' && !o.__node) return { value: String(o.value == null ? '' : o.value), label: String(o.label == null ? o.value : o.label), description: o.description };
      return { value: String(o == null ? '' : o), label: String(o == null ? '' : o) };
    });
  }

  C.Select = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var value = readBound(args[0], '');
    var options = optionPairs(args[1]);
    var opts = [];
    if (U.str(args[3])) opts.push(h('option', { attrs: { value: '' } }, [t(U.str(args[3]))]));
    options.forEach(function (o) {
      opts.push(h('option', { attrs: { value: o.value, selected: String(value) === o.value } }, [t(o.label)]));
    });
    var el = h('select', { cls: 'gui-input gui-select', attrs: { 'data-bind': binding ? binding.name : null } }, opts);
    el.ref = function (node) { wire(node, binding, ctx); return function () {}; };
    return fieldWrap(U.str(args[2]), el);
  };

  C.SegmentedControl = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var value = String(readBound(args[0], ''));
    var options = optionPairs(args[1]);
    var block = U.truthy(args[2]);
    var btns = options.map(function (o) {
      return h('button', {
        cls: 'gui-seg' + (String(value) === o.value ? ' active' : ''),
        attrs: { type: 'button' },
        ref: function (el) {
          el.addEventListener('click', function () {
            if (binding) binding.set(o.value);
            if (ctx.schedule) ctx.schedule();
          });
          return function () {};
        }
      }, [t(o.label)]);
    });
    return h('div', { cls: 'gui-segmented' + (block ? ' block' : '') }, btns);
  };

  C.Slider = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var min = U.numArg(U.arg(args, 1), 0) || 0;
    var max = U.numArg(U.arg(args, 2), 100) || 100;
    var step = U.numArg(U.arg(args, 3), 1) || 1;
    var unit = U.str(args[5]);
    var value = Number(readBound(args[0], min));
    var out = h('span', { cls: 'gui-slider-value' }, [t(value + (unit || ''))]);
    var input = h('input', {
      cls: 'gui-slider',
      attrs: {
        type: 'range', min: String(min), max: String(max), step: String(step),
        value: String(value), 'data-bind': binding ? binding.name : null
      },
      ref: function (node) {
        node.addEventListener('input', function () {
          var v = Number(node.value);
          out.textContent = v + (unit || '');
          if (binding) binding.set(v);
        });
        node.addEventListener('change', function () { if (ctx.schedule) ctx.schedule(); });
        return function () {};
      }
    });
    return h('div', { cls: 'gui-field' }, [
      U.str(args[4]) ? h('div', { cls: 'gui-field-row' }, [h('span', { cls: 'gui-field-label' }, [t(U.str(args[4]))]), out]) : null,
      input
    ]);
  };

  C.Checkbox = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var checked = !!readBound(args[0], false);
    var lineThrough = U.truthy(args[3]);
    return h('label', { cls: 'gui-check' + (checked && lineThrough ? ' done' : '') }, [
      h('input', {
        cls: 'gui-checkbox',
        attrs: { type: 'checkbox', checked: checked || null, 'data-bind': binding ? binding.name : null },
        ref: function (el) {
          el.addEventListener('change', function () {
            if (binding) binding.set(el.checked);
            if (ctx.schedule) ctx.schedule();
          });
          return function () {};
        }
      }),
      h('span', { cls: 'gui-check-label' }, U.textNodes(args[1], ctx))
    ]);
  };

  C.RadioGroup = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var value = String(readBound(args[0], ''));
    var options = optionPairs(args[1]);
    var label = U.str(args[2]);
    var variant = U.arg(args, 3) || 'list';
    var items = options.map(function (o) {
      var active = String(value) === o.value;
      return h('label', {
        cls: 'gui-radio gui-radio-' + variant + (active ? ' active' : ''),
        ref: function (el) {
          el.addEventListener('click', function (e) {
            e.preventDefault();
            if (binding) binding.set(o.value);
            if (ctx.schedule) ctx.schedule();
          });
          return function () {};
        }
      }, [
        h('span', { cls: 'gui-radio-dot' }),
        h('span', { cls: 'gui-radio-body' }, [
          h('span', { cls: 'gui-radio-label' }, [t(o.label)]),
          o.description ? h('span', { cls: 'gui-radio-desc' }, [t(String(o.description))]) : null
        ])
      ]);
    });
    var group = h('div', { cls: 'gui-radio-group' }, items);
    return fieldWrap(label, group);
  };

  C.DatePicker = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    collect(ctx, binding);
    var el = h('input', {
      cls: 'gui-input',
      attrs: {
        type: 'date',
        value: String(readBound(args[0], '') || ''),
        min: U.str(args[2]) || null,
        max: U.str(args[3]) || null,
        'data-bind': binding ? binding.name : null
      },
      ref: function (node) { wire(node, binding, ctx); return function () {}; }
    });
    return fieldWrap(U.str(args[1]), el);
  };

  C.Timer = function (args, ctx) {
    var binding = U.bindArg(args[0]);
    var label = U.str(args[1]);
    var total = Number(readBound(args[0], 0)) || 0;
    var key = 'timer:' + (binding ? binding.name : label);
    ctx.runtime = ctx.runtime || {};
    var slot = { running: false, interval: null };
    return h('div', {
      cls: 'gui-timer',
      ref: function (el) {
        var state = ctx.runtime[key] || (ctx.runtime[key] = slot);
        var display = el.querySelector('.gui-timer-value');
        function paint(sec) {
          var s = Math.max(0, Math.floor(sec));
          display.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
        }
        function stop() {
          if (state.interval) { clearInterval(state.interval); state.interval = null; }
          state.running = false;
          el.classList.remove('running');
        }
        function tick() {
          var next = Number(binding ? binding.value : 0) - 1;
          if (next <= 0) {
            if (binding) binding.set(0);
            paint(0);
            stop();
            if (ctx.schedule) ctx.schedule();
            return;
          }
          if (binding) binding.set(next);
          paint(next);
        }
        el.querySelector('.gui-timer-start').addEventListener('click', function () {
          if (state.running) return;
          state.running = true;
          el.classList.add('running');
          state.interval = setInterval(tick, 1000);
        });
        el.querySelector('.gui-timer-pause').addEventListener('click', function () { stop(); });
        el.querySelector('.gui-timer-reset').addEventListener('click', function () {
          stop();
          if (binding) binding.set(total);
          paint(total);
          if (ctx.schedule) ctx.schedule();
        });
        paint(Number(binding ? binding.value : total) || total);
        return stop;
      }
    }, [
      h('div', { cls: 'gui-timer-head' }, [
        h('span', { cls: 'gui-field-label' }, [t(label || '倒计时')]),
        h('span', { cls: 'gui-timer-value' }, [t('0:00')])
      ]),
      h('div', { cls: 'gui-timer-acts' }, [
        h('button', { cls: 'gui-btn gui-btn-soft gui-btn-sm gui-timer-start', attrs: { type: 'button' } }, [t('开始')]),
        h('button', { cls: 'gui-btn gui-btn-ghost gui-btn-sm gui-timer-pause', attrs: { type: 'button' } }, [t('暂停')]),
        h('button', { cls: 'gui-btn gui-btn-ghost gui-btn-sm gui-timer-reset', attrs: { type: 'button' } }, [t('重置')])
      ])
    ]);
  };

  C.Form = function (args, ctx) {
    var names = [];
    var inner = ctx;
    if (ctx) {
      ctx.formStack = ctx.formStack || [];
      ctx.formStack.push(names);
      inner = ctx;
    }
    var children = U.children(args[0], inner);
    if (ctx && ctx.formStack) ctx.formStack.pop();
    return h('div', { cls: 'gui-form' }, children);
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
