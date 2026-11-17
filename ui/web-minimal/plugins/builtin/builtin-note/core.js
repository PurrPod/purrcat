/* builtin-note 纯逻辑：时间线计算、purrcat 块解析与行内编辑用块切分。
   浏览器挂到 globalThis.PurrCatNote，L0 测试直接 require。 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.PurrCatNote = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var FENCE_RE = /^```/;
  var CARD_FENCE_RE = /^```purrcat@/i;
  var LIST_RE = /^\s*([-*+]|\d+\.)\s/;
  var DURATION_RE = /^(\d{1,3})\s*(?:min|mins|m|分钟)$/i;

  function normalize(source) {
    return String(source == null ? '' : source).replace(/\r\n/g, '\n');
  }

  function pad(n) {
    n = Math.round(Number(n) || 0);
    return (n < 10 ? '0' : '') + n;
  }

  function parseHHMM(value) {
    var m = String(value == null ? '' : value).trim().match(/^(\d{1,2})[:：](\d{2})$/);
    if (!m) return null;
    var h = Number(m[1]);
    var min = Number(m[2]);
    if (h > 23 || min > 59) return null;
    return h * 60 + min;
  }

  function fmtHHMM(minutes) {
    var m = ((Math.round(Number(minutes) || 0) % 1440) + 1440) % 1440;
    return pad(Math.floor(m / 60)) + ':' + pad(m % 60);
  }

  function dayWindow(wake, sleep) {
    var w = parseHHMM(wake);
    var s = parseHHMM(sleep);
    if (w == null) w = 8 * 60;
    if (s == null) s = 23 * 60;
    var span = s - w;
    if (span <= 0) span += 1440;
    return { wake: w, sleep: s, span: span, crossing: s <= w };
  }

  function dayProgress(now, wake, sleep) {
    var win = dayWindow(wake, sleep);
    var t = typeof now === 'string' ? parseHHMM(now) : Number(now);
    if (t == null || !isFinite(t)) t = 0;
    t = ((Math.round(t) % 1440) + 1440) % 1440;

    if (win.crossing) {
      var rel = t - win.wake;
      if (rel < 0) rel += 1440;
      if (rel <= 0) return { percent: 0, phase: 'awake' };
      if (rel >= win.span) return { percent: 0, phase: 'before' };
      return { percent: roundPercent(rel / win.span * 100), phase: 'awake' };
    }
    if (t < win.wake) return { percent: 0, phase: 'before' };
    if (t >= win.sleep) return { percent: 100, phase: 'after' };
    return { percent: roundPercent((t - win.wake) / win.span * 100), phase: 'awake' };
  }

  function roundPercent(v) {
    return Math.round(v * 100) / 100;
  }

  function ratioToMinutes(ratio, wake, sleep) {
    var win = dayWindow(wake, sleep);
    var r = Math.max(0, Math.min(1, Number(ratio) || 0));
    return (win.wake + r * win.span) % 1440;
  }

  function minutesToRatio(minutes, wake, sleep) {
    var win = dayWindow(wake, sleep);
    var m = ((Math.round(Number(minutes) || 0) % 1440) + 1440) % 1440;
    var rel = m - win.wake;
    if (rel < 0) rel += 1440;
    return roundPercent(Math.max(0, Math.min(1, rel / win.span)) * 100);
  }

  function buildPurrBlock(opts) {
    opts = opts || {};
    var ref = String(opts.target || 'none').trim() || 'none';
    var title = String(opts.title == null ? '' : opts.title).replace(/\s*\n+\s*/g, ' ').trim();
    if (!title) title = '未命名事项';
    var desc = String(opts.description == null ? '无描述' : opts.description).trim();
    if (!desc) desc = '无描述';
    var todo = '- TODO ' + title;
    if (opts.start != null && opts.end != null) {
      var label = function (minutes) {
        var m = Math.round(Number(minutes) || 0);
        return m >= 1440 ? '24:00' : fmtHHMM(m);
      };
      // 带时间段的卡片：TODO 行放时间与时长，标题交给下面的一级标题行。
      var mins = Math.max(1, Math.round(Number(opts.end) - Number(opts.start)));
      todo = '- TODO ' + label(opts.start) + '~' + label(opts.end) + ' ' + mins + 'min';
    }
    return '```purrcat@' + ref + '\n' + todo + '\n# ' + title + '\n' + desc + '\n```';
  }

  function appendBlock(source, block) {
    var s = normalize(source);
    if (s && !/\n$/.test(s)) s += '\n';
    if (s && !/\n\n$/.test(s)) s += '\n';
    return s + normalize(block) + '\n';
  }

  function splitBlocks(source) {
    var lines = normalize(source).split('\n');
    var blocks = [];
    var i = 0;
    while (i < lines.length) {
      if (!lines[i].trim()) { i += 1; continue; }
      var start = i;
      var kind = 'paragraph';
      if (FENCE_RE.test(lines[i])) {
        kind = CARD_FENCE_RE.test(lines[i]) ? 'card' : 'code';
        i += 1;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) i += 1;
        if (i < lines.length) i += 1;
      } else if (/^#{1,6}\s/.test(lines[i])) {
        kind = 'heading';
        i += 1;
      } else if (LIST_RE.test(lines[i])) {
        kind = 'list';
        i += 1;
        while (i < lines.length && lines[i].trim()) {
          if (FENCE_RE.test(lines[i])) break;
          if (LIST_RE.test(lines[i]) || /^\s{2,}/.test(lines[i])) { i += 1; continue; }
          break;
        }
      } else if (/^>\s?/.test(lines[i])) {
        kind = 'quote';
        i += 1;
        while (i < lines.length && /^>\s?/.test(lines[i])) i += 1;
      } else if (/^\|/.test(lines[i])) {
        kind = 'table';
        i += 1;
        while (i < lines.length && /^\|/.test(lines[i])) i += 1;
      } else {
        i += 1;
        while (i < lines.length && lines[i].trim()) {
          if (FENCE_RE.test(lines[i]) || /^#{1,6}\s/.test(lines[i])) break;
          if (LIST_RE.test(lines[i]) || /^>\s?/.test(lines[i]) || /^\|/.test(lines[i])) break;
          i += 1;
        }
      }
      blocks.push({ start: start, end: i, kind: kind, raw: lines.slice(start, i).join('\n') });
    }
    return { lines: lines, blocks: blocks };
  }

  function splitUnits(source) {
    var lines = normalize(source).split('\n');
    var units = [];
    var i = 0;
    while (i < lines.length) {
      var start = i;
      var kind = 'paragraph';
      if (FENCE_RE.test(lines[i])) {
        kind = CARD_FENCE_RE.test(lines[i]) ? 'card' : 'code';
        i += 1;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) i += 1;
        if (i < lines.length) i += 1;
      } else if (!lines[i].trim()) {
        kind = 'blank';
        i += 1;
      } else if (/^\|/.test(lines[i])) {
        kind = 'table';
        i += 1;
        while (i < lines.length && /^\|/.test(lines[i])) i += 1;
      } else if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(lines[i])) {
        kind = 'rule';
        i += 1;
      } else if (/^#{1,6}\s/.test(lines[i])) {
        kind = 'heading';
        i += 1;
      } else if (LIST_RE.test(lines[i])) {
        kind = 'list';
        i += 1;
      } else if (/^>\s?/.test(lines[i])) {
        kind = 'quote';
        i += 1;
      } else {
        i += 1;
      }
      units.push({ start: start, end: i, kind: kind, raw: lines.slice(start, i).join('\n') });
    }
    return { lines: lines, units: units };
  }

  function unitAt(units, line) {
    var n = Number(line);
    if (!isFinite(n)) return null;
    for (var i = 0; i < (units || []).length; i++) {
      var unit = units[i];
      if (n >= unit.start && n < unit.end) return unit;
    }
    return null;
  }

  function splitLine(lines, index, selStart, selEnd) {
    var src = Array.isArray(lines) ? lines.slice() : normalize(lines).split('\n');
    var at = Math.max(0, Math.min(src.length - 1, Math.round(Number(index) || 0)));
    var raw = src[at] == null ? '' : String(src[at]);
    var a = Math.max(0, Math.min(raw.length, Math.round(Number(selStart) || 0)));
    var b = Number(selEnd);
    if (!isFinite(b)) b = a;
    b = Math.max(a, Math.min(raw.length, Math.round(b)));
    src[at] = raw.slice(0, a);
    src.splice(at + 1, 0, raw.slice(b));
    return { lines: src, start: at + 1, count: 1 };
  }

  function mapRenderedOffset(source, rendered, offset) {
    var s = normalize(source);
    var r = String(rendered == null ? '' : rendered).replace(/\u00a0/g, ' ');
    var limit = Math.max(0, Math.min(r.length, Math.round(Number(offset) || 0)));
    var si = 0;
    var ri = 0;
    while (ri < limit && si < s.length) {
      var sc = s.charAt(si);
      var rc = r.charAt(ri);
      if (sc === rc) { si += 1; ri += 1; continue; }
      if (/\s/.test(sc) && /\s/.test(rc)) { si += 1; ri += 1; continue; }
      if (/\s/.test(sc)) { si += 1; continue; }
      if (/\s/.test(rc)) { ri += 1; continue; }
      si += 1;
    }
    if (limit === 0 && r.length) {
      var first = r.charAt(0);
      while (si < s.length && s.charAt(si) !== first) si += 1;
    }
    return si;
  }

  function edgeMinutes(text) {
    var m = String(text == null ? '' : text).trim().match(/^(\d{1,2})[:：](\d{2})$/);
    if (!m) return null;
    var h = Number(m[1]);
    var min = Number(m[2]);
    if (h > 24 || min > 59 || (h === 24 && min > 0)) return null;
    return h * 60 + min;
  }

  function parseCard(raw) {
    var lines = normalize(raw).split('\n');
    var m = (lines[0] || '').match(/^```purrcat@([^\s]*)\s*$/i);
    if (!m) return null;
    var ref = m[1] || 'none';
    // 引用可写成 target/task_id：task_id 存在时 Note 会监听任务耗时与 token。
    var parts = ref.split('/');
    var target = parts[0] || 'none';
    var taskId = parts[1] || '';
    var title = '';
    var time = '';
    var duration = '';
    var desc = [];
    var state = 'todo';
    var sawTodo = false;
    for (var i = 1; i < lines.length; i++) {
      if (/^```\s*$/.test(lines[i])) continue;
      if (!sawTodo) {
        // 首行关键字跟随执行状态：TODO / WAITING / RUNNING / DONE / ERROR。
        var t = lines[i].match(/^\s*-\s*(?:\[[ xX]\]\s*)?(TODO|WAITING|RUNNING|DONE|ERROR)(?![A-Za-z])[ \t]*(.*)$/i);
        if (t) {
          state = t[1].toLowerCase();
          var rest = t[2].trim();
          var span = rest.match(/^(\d{1,2}[:：]\d{2})\s*[~～\-–]\s*(\d{1,2}[:：]\d{2})\s*(.*)$/);
          if (span) {
            time = span[1].replace('：', ':') + '~' + span[2].replace('：', ':');
            rest = span[3].trim();
          }
          if (rest) {
            // TODO 行末尾可能是时长（60min），旧格式则是标题。
            var dur = rest.match(DURATION_RE);
            if (dur) duration = dur[1] + 'min';
            else title = rest;
          }
          sawTodo = true;
          continue;
        }
      }
      var heading = lines[i].match(/^#{1,6}\s+(.*)$/);
      if (heading) {
        var text = heading[1].trim();
        if (!title) { title = text; continue; }
        if (text === title) continue;
      }
      desc.push(lines[i]);
    }
    if (!duration && time) {
      var edge = time.split('~');
      var a = edgeMinutes(edge[0]);
      var b = edgeMinutes(edge[1]);
      if (a != null && b != null && b > a) duration = (b - a) + 'min';
    }
    return {
      raw: normalize(raw),
      ref: ref,
      target: target,
      taskId: taskId,
      title: title || '未命名事项',
      time: time,
      duration: duration,
      description: desc.join('\n').trim() || '无描述',
      state: state
    };
  }

  function parseCards(source) {
    return splitBlocks(source).blocks
      .filter(function (b) { return b.kind === 'card'; })
      .map(function (b) {
        var card = parseCard(b.raw) || {};
        card.start = b.start;
        card.end = b.end;
        return card;
      });
  }

  function timelineEntries(source) {
    return parseCards(source)
      .map(function (card) {
        if (!card.time) return null;
        var edge = String(card.time).split('~');
        var start = edgeMinutes(edge[0]);
        var end = edgeMinutes(edge[1]);
        if (start == null || end == null) return null;
        if (end <= start) end = Math.min(1440, start + 15);
        return { start: start, end: end, title: card.title };
      })
      .filter(function (entry) { return !!entry; });
  }

  function updateCardRef(source, card, target) {
    var lines = normalize(source).split('\n');
    var start = card && card.start != null ? Number(card.start) : NaN;
    // 行号缺失或不是卡片围栏时原样返回，避免写坏别的行。
    if (!isFinite(start) || start < 0 || start % 1 !== 0 || start >= lines.length) return lines.join('\n');
    if (!/^```purrcat@/i.test(lines[start])) return lines.join('\n');
    var ref = String(target || 'none').trim() || 'none';
    lines[start] = '```purrcat@' + ref;
    return lines.join('\n');
  }

  // 把 task_id 写进围栏引用（purrcat@default/<id>），空值则退回纯 target。
  function updateCardTaskId(source, card, taskId) {
    var lines = normalize(source).split('\n');
    var start = card && card.start != null ? Number(card.start) : NaN;
    if (!isFinite(start) || start < 0 || start % 1 !== 0 || start >= lines.length) return lines.join('\n');
    var m = lines[start].match(/^```purrcat@([^\s/]*)(?:\/\S*)?\s*$/i);
    if (!m) return lines.join('\n');
    var target = m[1] || String((card && card.target) || 'none');
    var id = String(taskId || '').trim().replace(/[^\w.-]/g, '');
    lines[start] = '```purrcat@' + target + (id ? '/' + id : '');
    return lines.join('\n');
  }

  // 只改卡片首行的状态关键字，保留缩进、复选框、时间段与时长。
  function setCardState(source, card, state) {
    var lines = normalize(source).split('\n');
    var start = card && card.start != null ? Number(card.start) : NaN;
    if (!isFinite(start) || start < 0 || start % 1 !== 0 || start >= lines.length) return lines.join('\n');
    if (!/^```purrcat@/i.test(lines[start])) return lines.join('\n');
    var end = card.end != null ? Math.min(Number(card.end), lines.length) : lines.length;
    var word = String(state || 'todo').toUpperCase();
    for (var i = start + 1; i < end; i++) {
      var m = lines[i].match(/^(\s*-\s*(?:\[[ xX]\]\s*)?)(TODO|WAITING|RUNNING|DONE|ERROR)(?![A-Za-z])([ \t]*[\s\S]*)$/i);
      if (!m) continue;
      lines[i] = m[1] + word + m[3];
      break;
    }
    return lines.join('\n');
  }

  function applyBlockEdit(source, start, end, raw) {
    var lines = normalize(source).split('\n');
    var next = normalize(raw).split('\n');
    lines.splice(start, Math.max(0, end - start), ...next);
    return lines.join('\n');
  }

  // Markdown 是状态的最终来源：卡片改回 TODO 视为重新待办，旧的执行记录不再生效。
  function isRunReset(card) {
    return !!card && card.state === 'todo';
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  return {
    parseHHMM: parseHHMM,
    fmtHHMM: fmtHHMM,
    dayWindow: dayWindow,
    dayProgress: dayProgress,
    ratioToMinutes: ratioToMinutes,
    minutesToRatio: minutesToRatio,
    buildPurrBlock: buildPurrBlock,
    appendBlock: appendBlock,
    splitBlocks: splitBlocks,
    splitUnits: splitUnits,
    unitAt: unitAt,
    splitLine: splitLine,
    mapRenderedOffset: mapRenderedOffset,
    parseCard: parseCard,
    parseCards: parseCards,
    timelineEntries: timelineEntries,
    edgeMinutes: edgeMinutes,
    updateCardRef: updateCardRef,
    updateCardTaskId: updateCardTaskId,
    setCardState: setCardState,
    applyBlockEdit: applyBlockEdit,
    isRunReset: isRunReset,
    escapeHtml: escapeHtml
  };
});
