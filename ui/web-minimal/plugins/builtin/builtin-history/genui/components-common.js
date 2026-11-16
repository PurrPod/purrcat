/* PurrCat GenUI —— 组件公共辅助 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var h = G.h, t = G.t, esc = G.esc;

  function arg(args, i, fallback) {
    var v = args[i];
    if (v === undefined) return fallback;
    return G.plain(v);
  }
  function bindArg(v) { return v instanceof G.Binding ? v : null; }
  function truthy(v) { return !!G.plain(v); }
  function numArg(v, fallback) {
    var n = Number(G.plain(v));
    return isFinite(n) ? n : fallback;
  }
  function str(v) {
    var p = G.plain(v);
    return p == null ? '' : String(p);
  }
  function arr(v) { var p = G.plain(v); return Array.isArray(p) ? p : (p == null ? [] : [p]); }

  function children(v, ctx) {
    var out = G.value(v, ctx);
    return Array.isArray(out) ? out : (out == null ? [] : [out]);
  }

  function isNodeValue(v) { return !!(v && typeof v === 'object' && v.__node); }

  /* 轻量内联标记：**粗体**、*斜体*、`代码`、[链接](url)、<red>着色</red> */
  var INLINE_TONES = {
    red: 'danger', green: 'success', yellow: 'warning', blue: 'info',
    orange: 'warning', purple: 'purple', pink: 'pink',
    gray: 'muted', grey: 'muted', ink: 'ink', muted: 'muted', faint: 'faint',
    info: 'info', success: 'success', warning: 'warning', danger: 'danger'
  };
  var TONE_NAMES = Object.keys(INLINE_TONES).join('|');

  function inline(text) {
    var src = String(text == null ? '' : text);
    var out = [];
    var re = new RegExp(
      '(<(' + TONE_NAMES + ')>[\\s\\S]*?<\\/\\2>|' +
      '\\*\\*[^*]+\\*\\*|\\*[^*\\n]+\\*|`[^`]+`|\\[[^\\]]+\\]\\([^)\\s]+\\))', 'g'
    );
    var last = 0, m;
    while ((m = re.exec(src))) {
      if (m.index > last) out.push(t(src.slice(last, m.index)));
      var token = m[0];
      if (m[2] && token.charAt(0) === '<') {
        var open = '<' + m[2] + '>';
        var inner = token.slice(open.length, token.length - m[2].length - 3);
        out.push(h('span', {
          cls: 'gui-inline-color',
          style: { color: G.color(INLINE_TONES[m[2]]) }
        }, inline(inner)));
      }
      else if (token.slice(0, 2) === '**') out.push(h('strong', {}, [t(token.slice(2, -2))]));
      else if (token[0] === '`') out.push(h('code', { cls: 'gui-inline-code' }, [t(token.slice(1, -1))]));
      else if (token[0] === '*') out.push(h('em', {}, [t(token.slice(1, -1))]));
      else {
        var mm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token);
        out.push(h('a', { cls: 'gui-link', attrs: { href: mm[2], target: '_blank', rel: 'noopener noreferrer' } }, [t(mm[1])]));
      }
      last = m.index + token.length;
    }
    if (last < src.length) out.push(t(src.slice(last)));
    return out;
  }

  /* text 参数可以是字符串（走内联标记）或组件/数组（原样渲染） */
  function textNodes(v, ctx) {
    if (Array.isArray(v)) {
      var merged = [];
      v.forEach(function (item) {
        if (typeof item === 'string' || typeof item === 'number') merged = merged.concat(inline(item));
        else if (item instanceof G.Binding) merged = merged.concat(textNodes(G.plain(item), ctx));
        else if (isNodeValue(item)) merged.push(G.value(item, ctx));
        else if (item != null && typeof item === 'object') merged.push(t(JSON.stringify(item)));
      });
      return merged;
    }
    if (isNodeValue(v)) return [G.value(v, ctx)];
    if (v instanceof G.Binding) return textNodes(v.value, ctx);
    return inline(v);
  }

  function stackStyle(gapValue, align) {
    var s = {};
    var gp = G.gap(gapValue);
    if (gp) s.gap = gp;
    if (align) s.alignItems = G.ALIGN[align] || align;
    return s;
  }

  function markdownToHTML(src) {
    var text = String(src == null ? '' : src);
    if (g.marked && typeof g.marked.parse === 'function') {
      try { return g.marked.parse(text); } catch (e) { /* 回退到纯文本 */ }
    }
    return text.split(/\n{2,}/).map(function (block) {
      var lines = block.split('\n');
      var heading = /^(#{1,6})\s+(.*)$/.exec(lines[0]);
      if (heading) return '<h' + heading[1].length + '>' + esc(heading[2]) + '</h' + heading[1].length + '>';
      var isList = lines.every(function (l) { return /^\s*[-*+]\s+/.test(l); });
      if (isList) return '<ul>' + lines.map(function (l) { return '<li>' + esc(l.replace(/^\s*[-*+]\s+/, '')) + '</li>'; }).join('') + '</ul>';
      if (/^>\s?/.test(block)) return '<blockquote>' + esc(block.replace(/^>\s?/gm, '')) + '</blockquote>';
      if (/^```/.test(block)) return '<pre><code>' + esc(block.replace(/```\w*\n?/g, '')) + '</code></pre>';
      return '<p>' + esc(block).replace(/\n/g, '<br>') + '</p>';
    }).join('');
  }

  G.util = {
    arg: arg, bindArg: bindArg, truthy: truthy, numArg: numArg, str: str, arr: arr,
    children: children, isNodeValue: isNodeValue, inline: inline, textNodes: textNodes,
    stackStyle: stackStyle, markdownToHTML: markdownToHTML
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
