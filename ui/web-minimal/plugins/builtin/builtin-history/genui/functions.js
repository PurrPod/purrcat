/* PurrCat GenUI —— 内置函数与动作步骤 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var Binding = G.Binding;
  var same = G.same;

  function list(v) { return Array.isArray(v) ? v : []; }
  function finite(v) { return typeof v === 'number' && isFinite(v) ? v : 0; }
  function num(v) { return typeof v === 'number' && isFinite(v) ? v : (typeof v === 'string' && v.trim() ? Number(v) : NaN); }
  function read(v, field) {
    if (!field) return v;
    var parts = String(field).split('.');
    var cur = v;
    for (var i = 0; i < parts.length; i++) {
      if (cur == null) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }
  function toDate(v) {
    var normalized = v;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      var keys = ['date', 'timestamp', 'datetime', 'createdAt', 'updatedAt', 'time', 'value'];
      for (var i = 0; i < keys.length; i++) {
        if (typeof v[keys[i]] === 'string' || typeof v[keys[i]] === 'number') { normalized = v[keys[i]]; break; }
      }
      if (normalized === v && ['year', 'month', 'day'].every(function (k) { return typeof v[k] === 'number' && isFinite(v[k]); })) {
        var month = v.month >= 1 && v.month <= 12 ? v.month : v.month + 1;
        normalized = String(v.year).padStart(4, '0') + '-' + String(month).padStart(2, '0') + '-' + String(v.day).padStart(2, '0');
      }
    }
    var parsed = typeof normalized === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(normalized)
      ? new Date(normalized + 'T00:00:00Z') : new Date(normalized);
    return parsed;
  }
  function isoDay(d) { return d.toISOString().slice(0, 10); }
  function agg(rows, field, kind, defaultKind) {
    kind = kind || defaultKind || (field ? 'sum' : 'count');
    if (kind === 'count') return rows.length;
    var values = rows.map(function (r) { return num(read(r, field)); }).filter(isFinite);
    if (!values.length) return 0;
    if (kind === 'avg') return values.reduce(function (a, b) { return a + b; }, 0) / values.length;
    if (kind === 'min') return Math.min.apply(null, values);
    if (kind === 'max') return Math.max.apply(null, values);
    return values.reduce(function (a, b) { return a + b; }, 0);
  }
  function locale() {
    try { return (g.navigator && g.navigator.language) || 'en-US'; } catch (e) { return 'en-US'; }
  }

  var functions = {};

  functions.Count = function (v) { return list(v).length; };
  functions.First = function (v) { return list(v)[0] == null ? null : list(v)[0]; };
  functions.Last = function (v) { var l = list(v); return l.length ? l[l.length - 1] : null; };
  functions.Sum = function (v) { return list(v).reduce(function (t, i) { return t + (num(i) || 0); }, 0); };
  functions.Avg = function (v) { var a = list(v).map(num).filter(isFinite); return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; };
  functions.Min = function (v) { var a = list(v).map(num).filter(isFinite); return a.length ? Math.min.apply(null, a) : 0; };
  functions.Max = function (v) { var a = list(v).map(num).filter(isFinite); return a.length ? Math.max.apply(null, a) : 0; };
  functions.Sort = function (v, field, dir) {
    return list(v).slice().sort(function (a, b) {
      var av = field ? read(a, field) : a, bv = field ? read(b, field) : b;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * (dir === 'desc' ? -1 : 1);
      av = String(av); bv = String(bv);
      return (av < bv ? -1 : av > bv ? 1 : 0) * (dir === 'desc' ? -1 : 1);
    });
  };
  functions.Filter = function (v, field, op, target) {
    return list(v).filter(function (item) {
      var actual = field ? read(item, field) : item;
      switch (op) {
        case '==': return same(actual, target);
        case '!=': return !same(actual, target);
        case '>': return Number(actual) > Number(target);
        case '<': return Number(actual) < Number(target);
        case '>=': return Number(actual) >= Number(target);
        case '<=': return Number(actual) <= Number(target);
        case 'contains': return String(actual == null ? '' : actual).toLowerCase().indexOf(String(target == null ? '' : target).toLowerCase()) >= 0;
        default: return false;
      }
    });
  };
  functions.Round = function (v, decimals) {
    var scale = Math.pow(10, Math.max(0, Math.min(10, Math.trunc(Number(decimals) || 0))));
    return Math.round(Number(v) * scale) / scale;
  };
  functions.Abs = function (v) { return Math.abs(Number(v)); };
  functions.Floor = function (v) { return Math.floor(Number(v)); };
  functions.Ceil = function (v) { return Math.ceil(Number(v)); };
  functions.Append = function (v, item) { return list(v).concat([item]); };
  functions.Prepend = function (v, item) { return [item].concat(list(v)); };
  functions.Concat = function (v, more) { return list(v).concat(list(more)); };
  functions.Remove = function (v, field, target) { return list(v).filter(function (i) { return !same(field ? read(i, field) : i, target); }); };
  functions.RemoveAt = function (v, index) {
    var l = list(v), n = Number(index);
    return l.filter(function (_i, idx, all) { return idx !== (n < 0 ? all.length + n : n); });
  };
  functions.Update = function (v, field, target, setField, setValue) {
    return list(v).map(function (item) {
      if (same(field ? read(item, field) : item, target) && item && typeof item === 'object') {
        var copy = {};
        Object.keys(item).forEach(function (k) { copy[k] = item[k]; });
        copy[setField] = setValue;
        return copy;
      }
      return item;
    });
  };
  functions.Toggle = function (v, item) {
    var found = list(v).some(function (e) { return same(e, item); });
    return found ? list(v).filter(function (e) { return !same(e, item); }) : list(v).concat([item]);
  };
  functions.Includes = function (v, item) {
    if (typeof v === 'string') return v.indexOf(String(item)) >= 0;
    return list(v).some(function (e) { return same(e, item); });
  };
  functions.Find = function (v, field, target) {
    var hit = list(v).filter(function (item) { return same(field ? read(item, field) : item, target); })[0];
    return hit == null ? null : hit;
  };
  functions.IndexOf = function (v, item) { return list(v).findIndex(function (e) { return same(e, item); }); };
  functions.Take = function (v, n) { return Number(n) < 0 ? list(v).slice(Number(n)) : list(v).slice(0, Number(n)); };
  functions.Slice = function (v, start, end) {
    if (typeof v === 'string') return v.slice(Number(start), end == null ? undefined : Number(end));
    return list(v).slice(Number(start), end == null ? undefined : Number(end));
  };
  functions.Unique = function (v) {
    return list(v).filter(function (item, idx, all) {
      return all.findIndex(function (other) { return same(other, item); }) === idx;
    });
  };
  functions.Reverse = function (v) { return list(v).slice().reverse(); };
  functions.Range = function (start, end, step) {
    var out = [], s = Number(step == null ? 1 : step);
    if (!s) return out;
    for (var v = Number(start); s > 0 ? v < Number(end) : v > Number(end); v += s) out.push(Number(v.toPrecision(12)));
    return out;
  };
  functions.Pick = function (v) { var l = list(v); return l.length ? l[Math.floor(Math.random() * l.length)] : null; };
  functions.Shuffle = function (v) {
    var out = list(v).slice();
    for (var i = out.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = out[i]; out[i] = out[j]; out[j] = tmp;
    }
    return out;
  };
  functions.Flatten = function (v) { return list(v).reduce(function (acc, i) { return acc.concat(Array.isArray(i) ? i : [i]); }, []); };
  functions.Chunk = function (v, size) {
    var out = [], n = Math.max(1, Math.trunc(Number(size) || 1)), src = list(v);
    for (var i = 0; i < src.length; i += n) out.push(src.slice(i, i + n));
    return out;
  };
  functions.Pow = function (a, b) { return finite(Math.pow(Number(a), Number(b))); };
  functions.Sqrt = function (v) { return Number(v) < 0 ? null : Math.sqrt(Number(v)); };
  functions.Sin = function (v) { return Math.sin(Number(v)); };
  functions.Cos = function (v) { return Math.cos(Number(v)); };
  functions.Tan = function (v) { return Math.tan(Number(v)); };
  functions.Random = function (min, max, integer) {
    var lo = Math.min(Number(min), Number(max)), hi = Math.max(Number(min), Number(max));
    return integer ? Math.floor(lo) + Math.floor(Math.random() * (Math.floor(hi) - Math.ceil(lo) + 1)) : lo + Math.random() * (hi - lo);
  };
  functions.Clamp = function (v, min, max) {
    var lo = Math.min(Number(min), Number(max)), hi = Math.max(Number(min), Number(max));
    return Math.min(Math.max(Number(v), lo), hi);
  };
  functions.Percent = function (part, total) { return Number(total) ? Number(part) / Number(total) * 100 : 0; };
  functions.Lerp = function (a, b, t) { return Number(a) + (Number(b) - Number(a)) * Number(t); };
  functions.Allocate = function (total, weights, decimals) {
    var ws = list(weights).map(Number), sum = ws.reduce(function (a, b) { return a + b; }, 0);
    var scale = Math.pow(10, Math.max(0, Math.min(6, Math.round(Number(decimals == null ? 2 : decimals)))));
    if (!sum) return ws.map(function () { return 0; });
    var raw = ws.map(function (w) { return Math.abs(Number(total)) * scale * w / sum; });
    var floor = raw.map(Math.floor);
    var left = Math.round(Math.abs(Number(total)) * scale) - floor.reduce(function (a, b) { return a + b; }, 0);
    raw.map(function (v, i) { return { i: i, rest: v - Math.floor(v) }; })
      .sort(function (a, b) { return b.rest - a.rest; })
      .forEach(function (x) { if (left-- > 0) floor[x.i]++; });
    return floor.map(function (v) { return (Number(total) < 0 ? -v : v) / scale; });
  };
  functions.Payment = function (principal, rate, periods) {
    var p = Number(principal), n = Number(periods), r = Number(rate) / 100;
    return r ? p * r / (1 - Math.pow(1 + r, -n)) : p / n;
  };
  functions.Convert = function (value, from, to) {
    var units = {
      mm: ['length', 0.001], cm: ['length', 0.01], m: ['length', 1], km: ['length', 1000],
      'in': ['length', 0.0254], ft: ['length', 0.3048], yd: ['length', 0.9144], mi: ['length', 1609.344],
      mg: ['mass', 1e-6], g: ['mass', 0.001], kg: ['mass', 1], oz: ['mass', 0.0283495], lb: ['mass', 0.453592], st: ['mass', 6.35029],
      ml: ['volume', 0.001], l: ['volume', 1], tsp: ['volume', 0.00492892], tbsp: ['volume', 0.0147868],
      floz: ['volume', 0.0295735], cup: ['volume', 0.236588], pt: ['volume', 0.473176], qt: ['volume', 0.946353], gal: ['volume', 3.78541],
      'm/s': ['speed', 1], 'km/h': ['speed', 1 / 3.6], mph: ['speed', 0.44704], kn: ['speed', 0.514444],
      m2: ['area', 1], km2: ['area', 1e6], ft2: ['area', 0.092903], ha: ['area', 10000], acre: ['area', 4046.86]
    };
    var a = String(from).toLowerCase(), b = String(to).toLowerCase();
    if (['c', 'f', 'k'].indexOf(a) >= 0 && ['c', 'f', 'k'].indexOf(b) >= 0) {
      var c = a === 'f' ? (Number(value) - 32) * 5 / 9 : a === 'k' ? Number(value) - 273.15 : Number(value);
      return b === 'f' ? c * 9 / 5 + 32 : b === 'k' ? c + 273.15 : c;
    }
    if (!units[a] || !units[b] || units[a][0] !== units[b][0]) return Number(value);
    return Number(value) * units[a][1] / units[b][1];
  };
  functions.Format = function (value, kind, decimals, currency) {
    var n = Number(value);
    var digits = decimals == null ? undefined : Math.max(0, Math.min(10, Math.trunc(Number(decimals))));
    var opts = digits == null ? {} : { minimumFractionDigits: kind === 'currency' ? digits : 0, maximumFractionDigits: digits };
    if (kind === 'currency') {
      opts.style = 'currency';
      var code = String(currency == null ? 'USD' : currency).toUpperCase();
      opts.currency = /^[A-Z]{3}$/.test(code) ? code : 'USD';
    } else if (kind === 'compact') {
      opts.notation = 'compact';
    }
    var text;
    try { text = new Intl.NumberFormat(locale(), opts).format(n); }
    catch (e) { text = String(n); }
    return text + (kind === 'percent' ? '%' : '');
  };
  functions.Join = function (v, sep, field) {
    return list(v).map(function (item) { return field ? read(item, field) : item; })
      .filter(function (item) { return item != null; })
      .map(function (item) { return typeof item === 'object' ? JSON.stringify(item) : String(item); })
      .join(sep == null ? ', ' : String(sep));
  };
  functions.Plural = function (n, word, plural) {
    return n + ' ' + (Math.abs(Number(n)) === 1 ? word : (plural == null ? word + 's' : plural));
  };
  functions.Pad = function (v, length, ch) { return String(v).padStart(Math.max(0, Math.trunc(Number(length))), String(ch || '0')); };
  functions.Upper = function (v) { return String(v).toUpperCase(); };
  functions.Lower = function (v) { return String(v).toLowerCase(); };
  functions.Trim = function (v) { return String(v).trim(); };
  functions.Capitalize = function (v) {
    return String(v).replace(/(^|[\s\-(/"])(\p{L})/gu, function (_m, before, letter) { return before + letter.toUpperCase(); });
  };
  functions.Split = function (v, sep) {
    return String(v).split(String(sep == null ? ',' : sep)).map(function (p) { return p.trim(); }).filter(Boolean);
  };
  functions.Replace = function (v, find, replacement) { return String(v).split(String(find)).join(String(replacement)); };
  functions.Duration = function (seconds, style) {
    var total = Math.max(0, Math.floor(Number(seconds)));
    var h = Math.floor(total / 3600), m = Math.floor(total % 3600 / 60), s = total % 60;
    if (style === 'clock') return (h ? h + ':' : '') + String(m).padStart(h ? 2 : 1, '0') + ':' + String(s).padStart(2, '0');
    return (h ? h + 'h ' : '') + (m ? m + 'm ' : '') + s + 's';
  };
  functions.Default = function (v, fallback) {
    return v == null || v === '' || (typeof v === 'number' && !isFinite(v)) ? fallback : v;
  };
  functions.MixColor = function (from, to, t) {
    function parse(color) {
      var hex = String(color).replace('#', '');
      var full = hex.length === 3 ? hex.split('').map(function (c) { return c + c; }).join('') : hex;
      return [0, 2, 4].map(function (i) { return parseInt(full.slice(i, i + 2), 16); });
    }
    var a = parse(from), b = parse(to), k = Math.max(0, Math.min(1, Number(t)));
    return '#' + a.map(function (v, i) {
      return Math.round(v + (b[i] - v) * k).toString(16).padStart(2, '0');
    }).join('');
  };
  functions.Now = function () { return new Date().toISOString(); };
  functions.Today = function () { return isoDay(new Date()); };
  functions.FormatDate = function (value, style) {
    var d = toDate(value);
    if (isNaN(d.getTime())) return '';
    if (style === 'iso') return isoDay(d);
    var formats = {
      date: { month: 'short', day: 'numeric', year: 'numeric' },
      short: { month: 'short', day: 'numeric' },
      long: { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' },
      weekday: { weekday: 'short' },
      month: { month: 'short', year: 'numeric' },
      time: { hour: 'numeric', minute: '2-digit' },
      datetime: { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
    };
    try { return new Intl.DateTimeFormat(locale(), formats[style] || formats.date).format(d); }
    catch (e) { return isoDay(d); }
  };
  functions.AddDays = function (value, days) {
    var d = toDate(value); d.setUTCDate(d.getUTCDate() + Math.trunc(Number(days))); return isoDay(d);
  };
  functions.AddMonths = function (value, months) {
    var d = toDate(value), day = d.getUTCDate();
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + Math.trunc(Number(months)));
    d.setUTCDate(Math.min(day, new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()));
    return isoDay(d);
  };
  functions.DaysBetween = function (from, to) {
    return Math.round((toDate(to).getTime() - toDate(from).getTime()) / 86400000);
  };
  functions.MonthsBetween = function (from, to) {
    var a = toDate(from), b = toDate(to);
    var months = (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth();
    if (months > 0 && b.getUTCDate() < a.getUTCDate()) months--;
    if (months < 0 && b.getUTCDate() > a.getUTCDate()) months++;
    return months;
  };
  functions.StartOf = function (value, unit) {
    var d = toDate(value);
    if (unit === 'year') return d.getUTCFullYear() + '-01-01';
    if (unit === 'month') return d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0') + '-01';
    var day = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - day);
    return isoDay(d);
  };
  functions.GroupBy = function (rows, key, field, kind) {
    var groups = new Map();
    list(rows).forEach(function (row) {
      var raw = read(row, key);
      var k = typeof raw === 'number' ? raw : raw == null || raw === '' ? 'Unknown' : String(raw);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(row);
    });
    var out = [];
    groups.forEach(function (members, k) { out.push({ key: k, value: agg(members, field, kind) }); });
    return out;
  };
  functions.Pivot = function (rows, rowKey, colKey, field, kind) {
    var cols = [];
    list(rows).forEach(function (row) {
      var c = String(read(row, colKey));
      if (cols.indexOf(c) < 0) cols.push(c);
    });
    var groups = new Map();
    list(rows).forEach(function (row) {
      var k = String(read(row, rowKey));
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(row);
    });
    var out = [];
    groups.forEach(function (members, k) {
      var entry = { key: k };
      cols.forEach(function (col) {
        entry[col] = agg(members.filter(function (row) { return String(read(row, colKey)) === col; }), field, kind);
      });
      out.push(entry);
    });
    return out;
  };
  functions.Top = function (rows, field, n, dir) {
    return list(rows).slice().sort(function (a, b) {
      return (Number(read(b, field)) - Number(read(a, field))) * (dir === 'asc' ? -1 : 1);
    }).slice(0, Math.max(0, Math.trunc(Number(n))));
  };
  functions.Between = function (rows, field, min, max) {
    return list(rows).filter(function (row) {
      var v = read(row, field);
      return v != null && (min == null || String(v) >= String(min)) && (max == null || String(v) <= String(max));
    });
  };
  functions.Bucket = function (rows, dateField, unit, field, kind) {
    var buckets = new Map();
    list(rows).forEach(function (row) {
      var d = toDate(read(row, dateField));
      var key = isoDay(d);
      if (unit === 'month') key = key.slice(0, 7);
      if (unit === 'week') { var day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); key = isoDay(d); }
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(row);
    });
    return Array.from(buckets.keys()).sort().map(function (key) {
      return { key: key, value: agg(buckets.get(key), field, kind) };
    });
  };
  functions.Cumulative = function (rows, field) {
    var total = 0;
    return list(rows).map(function (row) {
      total += Number(read(row, field) || 0);
      if (!field) return total;
      var copy = {};
      Object.keys(row).forEach(function (k) { copy[k] = row[k]; });
      copy[field] = total;
      return copy;
    });
  };
  functions.MovingAvg = function (rows, field, window) {
    var src = list(rows);
    return src.map(function (_row, index) {
      var slice = src.slice(Math.max(0, index - Math.trunc(Number(window)) + 1), index + 1);
      var avg = slice.reduce(function (a, item) { return a + Number(read(item, field) || 0); }, 0) / slice.length;
      if (!field) return avg;
      var copy = {};
      Object.keys(src[index]).forEach(function (k) { copy[k] = src[index][k]; });
      copy[field] = avg;
      return copy;
    });
  };
  functions.Change = function (current, previous) {
    return Number(previous) === 0 ? null : (Number(current) - Number(previous)) / Math.abs(Number(previous)) * 100;
  };
  functions.Histogram = function (values, bins, min, max) {
    var nums = list(values).map(Number).filter(isFinite);
    var count = Math.max(1, Math.trunc(Number(bins) || 1));
    var lo = min == null ? Math.min.apply(null, nums.concat([0])) : Number(min);
    var hi = max == null ? Math.max.apply(null, nums.concat([1])) : Number(max);
    var width = (hi > lo ? hi - lo : 1) / count;
    return Array.from({ length: count }, function (_v, index) {
      var start = lo + index * width;
      return {
        key: String(start),
        value: nums.filter(function (v) { return v >= start && (index === count - 1 ? v <= start + width : v < start + width); }).length,
        start: start,
        end: start + width
      };
    });
  };
  functions.Stats = function (values) {
    var nums = list(values).map(Number).filter(isFinite).sort(function (a, b) { return a - b; });
    var count = nums.length;
    var mean = count ? nums.reduce(function (a, b) { return a + b; }, 0) / count : 0;
    var median = count ? (count % 2 ? nums[Math.floor(count / 2)] : (nums[count / 2 - 1] + nums[count / 2]) / 2) : 0;
    var stdev = count ? Math.sqrt(nums.reduce(function (sum, v) { return sum + Math.pow(v - mean, 2); }, 0) / count) : 0;
    return { count: count, min: count ? nums[0] : 0, max: count ? nums[count - 1] : 0, mean: mean, median: median, stdev: stdev };
  };
  functions.Each = function () { return []; };

  var actions = {};
  actions.ToAssistant = function (message, context) {
    return { __step: 'ToAssistant', text: G.formatValue(message), context: context };
  };
  actions.OpenUrl = function (url) { return { __step: 'OpenUrl', url: G.formatValue(url) }; };
  actions.Set = function (target, value) {
    return { __step: 'Set', name: target instanceof Binding ? target.name : null, value: value };
  };
  actions.Reset = function () {
    var names = Array.prototype.slice.call(arguments).map(function (v) { return v instanceof Binding ? v.name : null; })
      .filter(Boolean);
    return { __step: 'Reset', names: names };
  };
  actions.CopyToClipboard = function (text) { return { __step: 'CopyToClipboard', text: G.formatValue(text) }; };

  G.functions = functions;
  G.actions = actions;
  G.builtinFunctions = functions;
})(typeof globalThis !== 'undefined' ? globalThis : this);
