/* PurrCat GenUI —— 绘图、播放与自定义 HTML */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var h = G.h, t = G.t, raw = G.raw, U = G.util, C = G.components;

  function paint(v, fallback) {
    if (v == null || v === '') return fallback;
    var c = G.color(v);
    return c || fallback;
  }

  C.Svg = function (args, ctx) {
    var width = U.numArg(U.arg(args, 1), 0);
    var height = U.numArg(U.arg(args, 2), 0);
    var s = { display: 'block', width: '100%', maxWidth: width > 0 ? width + 'px' : '100%', height: 'auto' };
    var attrs = {
      viewBox: '0 0 ' + (width > 0 ? width : 320) + ' ' + (height > 0 ? height : 200),
      preserveAspectRatio: 'xMidYMid meet',
      role: 'img'
    };
    return h('svg', { cls: 'gui-svg', style: s, attrs: attrs }, U.children(args[0], ctx));
  };

  C.G = function (args, ctx) {
    var attrs = {};
    if (args[1] != null) attrs.transform = U.str(args[1]);
    var fill = paint(U.arg(args, 2), undefined);
    var stroke = paint(U.arg(args, 3), undefined);
    if (fill) attrs.fill = fill;
    if (stroke) attrs.stroke = stroke;
    return h('g', { attrs: attrs }, U.children(args[0], ctx));
  };

  C.Circle = function (args) {
    return h('circle', { attrs: {
      cx: U.numArg(U.arg(args, 0), 0), cy: U.numArg(U.arg(args, 1), 0), r: U.numArg(U.arg(args, 2), 0),
      fill: paint(U.arg(args, 3), 'var(--gui-chart-1)')
    } });
  };

  C.Ellipse = function (args) {
    return h('ellipse', { attrs: {
      cx: U.numArg(U.arg(args, 0), 0), cy: U.numArg(U.arg(args, 1), 0),
      rx: U.numArg(U.arg(args, 2), 0), ry: U.numArg(U.arg(args, 3), 0),
      fill: paint(U.arg(args, 4), 'var(--gui-chart-1)')
    } });
  };

  C.Rect = function (args) {
    var attrs = {
      x: U.numArg(U.arg(args, 0), 0), y: U.numArg(U.arg(args, 1), 0),
      width: U.numArg(U.arg(args, 2), 0), height: U.numArg(U.arg(args, 3), 0),
      fill: paint(U.arg(args, 5), 'var(--gui-chart-1)')
    };
    var rx = U.numArg(U.arg(args, 4), 0);
    if (rx) attrs.rx = rx;
    return h('rect', { attrs: attrs });
  };

  C.Line = function (args) {
    return h('line', { attrs: {
      x1: U.numArg(U.arg(args, 0), 0), y1: U.numArg(U.arg(args, 1), 0),
      x2: U.numArg(U.arg(args, 2), 0), y2: U.numArg(U.arg(args, 3), 0),
      stroke: paint(U.arg(args, 4), 'var(--gui-ink)'), 'stroke-width': U.numArg(U.arg(args, 5), 2)
    } });
  };

  C.Path = function (args) {
    return h('path', { attrs: {
      d: U.str(args[0]), fill: paint(U.arg(args, 1), 'none'), stroke: paint(U.arg(args, 2), 'none'),
      'stroke-width': U.numArg(U.arg(args, 3), 2), 'stroke-linejoin': 'round', 'stroke-linecap': 'round'
    } });
  };

  C.Polyline = function (args) {
    return h('polyline', { attrs: {
      points: U.str(args[0]), fill: paint(U.arg(args, 1), 'none'), stroke: paint(U.arg(args, 2), 'var(--gui-accent)'),
      'stroke-width': U.numArg(U.arg(args, 3), 2), 'stroke-linejoin': 'round', 'stroke-linecap': 'round'
    } });
  };

  C.Polygon = function (args) {
    return h('polygon', { attrs: {
      points: U.str(args[0]), fill: paint(U.arg(args, 1), 'var(--gui-chart-2)'), stroke: paint(U.arg(args, 2), 'none')
    } });
  };

  C.SvgText = function (args) {
    return h('text', { attrs: {
      x: U.numArg(U.arg(args, 1), 0), y: U.numArg(U.arg(args, 2), 0),
      'font-size': U.numArg(U.arg(args, 3), 14), fill: paint(U.arg(args, 4), 'var(--gui-ink)'),
      'text-anchor': U.str(args[5]) || 'start'
    } }, [t(U.str(args[0]))]);
  };

  C.Flashcard = function (args, ctx) {
    var front = args[0], back = args[1], hint = U.str(args[2]);
    ctx.runtime = ctx.runtime || {};
    var wrap = h('div', {
      cls: 'gui-flashcard',
      ref: function (el) {
        var card = el.querySelector('.gui-flashcard-inner');
        var flipped = false;
        el.addEventListener('click', function () {
          flipped = !flipped;
          card.classList.toggle('flipped', flipped);
        });
        return function () {};
      }
    }, [
      h('div', { cls: 'gui-flashcard-inner' }, [
        h('div', { cls: 'gui-flashcard-face front' }, [
          h('div', { cls: 'gui-flashcard-label' }, [t('正面')]),
          h('div', { cls: 'gui-flashcard-body' }, U.children(front, ctx)),
          hint ? h('div', { cls: 'gui-flashcard-hint' }, [t(hint)]) : null
        ]),
        h('div', { cls: 'gui-flashcard-face back' }, [
          h('div', { cls: 'gui-flashcard-label' }, [t('背面')]),
          h('div', { cls: 'gui-flashcard-body' }, U.children(back, ctx))
        ])
      ]),
      h('div', { cls: 'gui-flashcard-tip' }, [t('点击卡片翻转')])
    ]);
    return wrap;
  };

  C.Celebration = function (args, ctx) {
    if (!U.truthy(args[0])) return null;
    var count = Math.max(12, Math.min(80, U.numArg(U.arg(args, 1), 40)));
    var pieces = [];
    for (var i = 0; i < count; i++) {
      pieces.push(h('span', {
        cls: 'gui-confetti-piece',
        style: {
          left: (Math.random() * 100).toFixed(2) + '%',
          background: 'var(--gui-chart-' + ((i % 6) + 1) + ')',
          animationDelay: (Math.random() * 0.9).toFixed(2) + 's',
          animationDuration: (1.8 + Math.random() * 1.6).toFixed(2) + 's',
          transform: 'rotate(' + Math.floor(Math.random() * 360) + 'deg)'
        }
      }));
    }
    return h('div', { cls: 'gui-confetti' }, pieces);
  };

  C.HtmlView = function (args) {
    var html = U.str(args[0]);
    var height = U.numArg(U.arg(args, 1), 300) || 300;
    var title = U.str(args[2]) || '自定义视图';
    return h('div', { cls: 'gui-htmlview' }, [
      h('div', { cls: 'gui-htmlview-head' }, [t(title)]),
      h('iframe', {
        cls: 'gui-htmlview-frame',
        style: { height: Math.max(120, Math.min(900, height)) + 'px' },
        attrs: { sandbox: 'allow-scripts allow-forms', title: title, loading: 'lazy', srcdoc: html }
      })
    ]);
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
