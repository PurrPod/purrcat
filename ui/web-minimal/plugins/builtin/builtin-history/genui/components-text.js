/* PurrCat GenUI —— 布局与文本组件 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var h = G.h, t = G.t, raw = G.raw, U = G.util;
  var C = G.components;

  function gp(v) { return G.gap(v); }

  C.Col = function (args, ctx) {
    var s = U.stackStyle(args[1], U.arg(args, 2));
    return h('div', { cls: 'gui-col', style: s }, U.children(args[0], ctx));
  };

  C.Row = function (args, ctx) {
    var s = U.stackStyle(args[1], U.arg(args, 2));
    var justify = U.arg(args, 3);
    if (justify) s.justifyContent = G.JUSTIFY[justify] || justify;
    if (U.truthy(args[4])) s.flexWrap = 'wrap';
    s.display = 'flex';
    s.flexDirection = 'row';
    return h('div', { cls: 'gui-row', style: s }, U.children(args[0], ctx));
  };

  C.Box = function (args, ctx) {
    var s = U.stackStyle(args[2], U.arg(args, 7));
    s.display = 'flex';
    s.flexDirection = U.arg(args, 1) === 'row' ? 'row' : 'column';
    var padding = gp(args[3]); if (padding) s.padding = padding;
    var bg = G.color(U.arg(args, 4), true); if (bg) s.background = bg;
    var rd = G.radius(args[5]); if (rd) s.borderRadius = rd;
    if (U.truthy(args[6])) s.border = '1px solid var(--gui-border)';
    var width = G.len(args[7]); if (width) s.width = width;
    var height = G.len(args[8]); if (height) s.height = height;
    var flex = U.arg(args, 9); if (flex != null) s.flex = String(flex);
    var justify = U.arg(args, 10);
    if (justify) s.justifyContent = G.JUSTIFY[justify] || justify;
    if (U.truthy(args[11])) s.flexWrap = 'wrap';
    if (rd) s.overflow = 'hidden';
    return h('div', { cls: 'gui-box', style: s }, U.children(args[0], ctx));
  };

  C.Grid = function (args, ctx) {
    var columns = Math.max(1, Math.min(12, U.numArg(U.arg(args, 1), 2) || 2));
    var minChild = U.numArg(U.arg(args, 2), 0);
    var s = { display: 'grid', gap: gp(args[3]) || '12px' };
    if (minChild > 0) s.gridTemplateColumns = 'repeat(auto-fit, minmax(' + minChild + 'px, 1fr))';
    else s.gridTemplateColumns = 'repeat(' + columns + ', minmax(0, 1fr))';
    return h('div', { cls: 'gui-grid', style: s }, U.children(args[0], ctx));
  };

  C.Card = function (args, ctx) {
    var variant = U.arg(args, 1) === 'soft' ? ' soft' : ' outline';
    var s = U.stackStyle(args[3], null);
    var padding = gp(args[2]); if (padding) s.padding = padding;
    return h('div', { cls: 'gui-card' + variant, style: s }, U.children(args[0], ctx));
  };

  C.Carousel = function (args, ctx) {
    var itemWidth = U.numArg(U.arg(args, 1), 240) || 240;
    var s = { gap: gp(args[2]) || '12px' };
    var items = U.children(args[0], ctx).map(function (child) {
      return h('div', { cls: 'gui-carousel-item', style: { width: itemWidth + 'px' } }, [child]);
    });
    return h('div', { cls: 'gui-carousel', style: s }, items);
  };

  C.Popover = function (args, ctx) {
    var trigger = args[0];
    var content = args[1];
    var triggerNode = (typeof trigger === 'string' || typeof trigger === 'number')
      ? h('button', { cls: 'gui-popover-trigger', attrs: { type: 'button' } }, [t(trigger)])
      : h('span', { cls: 'gui-popover-trigger' }, U.children(trigger, ctx));
    var panel = h('div', { cls: 'gui-popover-panel' }, U.children(content, ctx));
    var wrap = h('span', {
      cls: 'gui-popover',
      ref: function (el) {
        function onClick(e) {
          e.preventDefault();
          e.stopPropagation();
          el.classList.toggle('open');
        }
        el.firstChild.addEventListener('click', onClick);
        function onDoc(e) { if (!el.contains(e.target)) el.classList.remove('open'); }
        if (typeof document !== 'undefined') document.addEventListener('click', onDoc);
        return function () {
          el.firstChild && el.firstChild.removeEventListener('click', onClick);
          if (typeof document !== 'undefined') document.removeEventListener('click', onDoc);
        };
      }
    }, [triggerNode, panel]);
    return wrap;
  };

  C.Divider = function () { return h('div', { cls: 'gui-divider', attrs: { role: 'separator' } }); };
  C.Spacer = function () { return h('div', { cls: 'gui-spacer' }); };

  var TITLE_SIZE = { sm: '15px', md: '17px', lg: '20px', xl: '24px', '2xl': '30px', '3xl': '38px' };
  var TEXT_SIZE = { xs: '11px', sm: '12.5px', md: '14px', lg: '16px' };
  var WEIGHT = { normal: '400', medium: '500', semibold: '600' };

  C.Title = function (args, ctx) {
    var size = U.arg(args, 1) || 'lg';
    var s = { fontSize: TITLE_SIZE[size] || size };
    var color = G.color(U.arg(args, 2));
    if (color) s.color = color;
    return h('div', { cls: 'gui-title', style: s }, U.textNodes(args[0], ctx));
  };

  C.Text = function (args, ctx) {
    var size = U.arg(args, 1) || 'md';
    var s = { fontSize: TEXT_SIZE[size] || size };
    var color = G.color(U.arg(args, 2));
    if (color) s.color = color;
    var weight = U.arg(args, 3);
    if (weight) s.fontWeight = WEIGHT[weight] || weight;
    if (U.truthy(args[4])) s.fontStyle = 'italic';
    if (U.truthy(args[5])) s.textDecoration = 'line-through';
    if (U.truthy(args[6])) s.fontVariantNumeric = 'tabular-nums';
    var maxLines = U.numArg(U.arg(args, 7), 0);
    if (maxLines > 0) {
      s.display = '-webkit-box';
      s.WebkitLineClamp = String(maxLines);
      s.WebkitBoxOrient = 'vertical';
      s.overflow = 'hidden';
    }
    return h('div', { cls: 'gui-text', style: s }, U.textNodes(args[0], ctx));
  };

  C.Caption = function (args) {
    var s = {};
    var color = G.color(U.arg(args, 1)) || 'var(--gui-muted)';
    s.color = color;
    return h('div', { cls: 'gui-caption', style: s }, U.textNodes(args[0], null));
  };

  C.Label = function (args) { return h('div', { cls: 'gui-label' }, U.textNodes(args[0], null)); };

  C.Badge = function (args) {
    var color = U.arg(args, 1) || 'neutral';
    return h('span', { cls: 'gui-badge gui-badge-' + String(color) }, [t(U.str(args[0]))]);
  };

  C.Link = function (args) {
    return h('a', { cls: 'gui-link', attrs: { href: U.str(args[1]), target: '_blank', rel: 'noopener noreferrer' } }, [t(U.str(args[0]))]);
  };

  C.List = function (args, ctx) {
    var marker = U.arg(args, 1) || 'bullet';
    var timeline = U.truthy(args[2]);
    var items = U.arr(args[0]);
    var children = items.map(function (item, i) {
      var content;
      if (item && typeof item === 'object' && item.__node && item.type === 'ListItem') content = G.value(item, ctx);
      else content = h('div', { cls: 'gui-list-text' }, U.textNodes(item, ctx));
      var mark = marker === 'number' ? h('span', { cls: 'gui-list-mark num' }, [t(String(i + 1))])
        : marker === 'none' ? null : h('span', { cls: 'gui-list-mark dot' }, [t('•')]);
      return h('div', { cls: 'gui-list-row' + (timeline ? ' timeline' : '') }, [mark, h('div', { cls: 'gui-list-body' }, [content])]);
    });
    return h('div', { cls: 'gui-list marker-' + marker + (timeline ? ' is-timeline' : '') }, children);
  };

  C.ListItem = function (args, ctx) {
    // 第三参是自定义标记文本；none/bullet/number 属于 List 的标记样式，不应显示出来
    var marker = U.arg(args, 2);
    var mark = marker == null ? '' : String(marker);
    if (mark === 'none' || mark === 'bullet' || mark === 'number') mark = '';
    var head = h('div', { cls: 'gui-list-title' }, [
      mark ? h('span', { cls: 'gui-list-item-mark' }, [t(mark)]) : null,
      h('span', {}, U.textNodes(args[0], ctx))
    ]);
    var desc = args[1] != null ? h('div', { cls: 'gui-list-desc' }, U.textNodes(args[1], ctx)) : null;
    var extra = U.children(args[3], ctx);
    return h('div', { cls: 'gui-list-item' }, [head, desc, extra.length ? h('div', { cls: 'gui-list-extra' }, extra) : null]);
  };

  C.Markdown = function (args) {
    return h('div', { cls: 'gui-md', html: U.markdownToHTML(U.arg(args, 0)) });
  };

  C.Quote = function (args) {
    var text = U.arg(args, 0);
    var content = (text && typeof text === 'object') ? U.children(text, null) : U.textNodes(text, null);
    var cite = U.str(args[1]);
    return h('blockquote', { cls: 'gui-quote' }, [h('div', { cls: 'gui-quote-body' }, content), cite ? h('div', { cls: 'gui-quote-cite' }, [t('— ' + cite)]) : null]);
  };

  C.Code = function (args) {
    var code = U.str(args[0]);
    var language = U.str(args[1]);
    var copyBtn = h('button', {
      cls: 'gui-code-copy', attrs: { type: 'button', title: '复制' },
      ref: function (el) {
        el.addEventListener('click', function () {
          var done = function () {
            el.textContent = '已复制';
            setTimeout(function () { el.textContent = '复制'; }, 1200);
          };
          if (g.navigator && g.navigator.clipboard) g.navigator.clipboard.writeText(code).then(done, function () {});
        });
        return function () {};
      }
    }, [t('复制')]);
    var codeEl = h('code', { cls: language ? 'language-' + language : '' }, [t(code)]);
    var pre = h('pre', {
      cls: 'gui-code',
      ref: function (el) {
        if (g.hljs && language && g.hljs.getLanguage && g.hljs.getLanguage(language)) {
          try {
            var target = el.querySelector('code');
            target.innerHTML = g.hljs.highlight(code, { language: language }).value;
          } catch (e) { /* 保留纯文本 */ }
        }
        return function () {};
      }
    }, [codeEl]);
    return h('div', { cls: 'gui-code-block' }, [
      h('div', { cls: 'gui-code-head' }, [h('span', { cls: 'gui-code-lang' }, [t(language || 'code')]), copyBtn]),
      pre
    ]);
  };

  C.Math = function (args) {
    var tex = U.str(args[0]);
    var inline = U.truthy(args[1]);
    if (g.katex && typeof g.katex.renderToString === 'function') {
      try {
        return h(inline ? 'span' : 'div', { cls: 'gui-math', html: g.katex.renderToString(tex, { displayMode: !inline, throwOnError: false }) });
      } catch (e) { /* 回退 */ }
    }
    return h(inline ? 'code' : 'pre', { cls: 'gui-math-fallback' }, [t(tex)]);
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
