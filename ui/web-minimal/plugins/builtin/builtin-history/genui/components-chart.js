/* PurrCat GenUI —— 图表与地图组件 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var h = G.h, t = G.t, raw = G.raw, U = G.util, C = G.components;
  var esc = G.esc;

  var SERIES_COLORS = ['var(--gui-chart-1)', 'var(--gui-chart-2)', 'var(--gui-chart-3)', 'var(--gui-chart-4)', 'var(--gui-chart-5)', 'var(--gui-chart-6)'];

  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  function abbr(n) {
    if (!isFinite(n)) return '';
    var abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(abs >= 1e10 ? 0 : 1) + 'B';
    if (abs >= 1e6) return (n / 1e6).toFixed(abs >= 1e7 ? 0 : 1) + 'M';
    if (abs >= 1e4) return (n / 1e3).toFixed(abs >= 1e5 ? 0 : 1) + 'k';
    if (abs > 0 && abs < 1) return String(Number(n.toFixed(2)));
    return String(Math.round(n));
  }

  function fmtValue(n, format, currency, decimals) {
    if (!isFinite(n)) return '—';
    if (format === 'currency') {
      try {
        return new Intl.NumberFormat(undefined, {
          style: 'currency', currency: String(currency || 'USD').toUpperCase(),
          maximumFractionDigits: decimals == null ? 2 : decimals
        }).format(n);
      } catch (e) { return '$' + n.toFixed(decimals == null ? 2 : decimals); }
    }
    if (format === 'percent') return (n <= 1 && n >= -1 ? n * 100 : n).toFixed(decimals == null ? 1 : decimals) + '%';
    if (format === 'compact') return abbr(n);
    if (decimals != null) return n.toFixed(decimals);
    return abbr(n);
  }

  function buildRows(data, xKey, series) {
    var rows = Array.isArray(data) ? data.filter(function (r) { return r && typeof r === 'object'; }) : [];
    var keys = Object.keys(rows[0] || {});
    var x = xKey || keys.filter(function (k) { return !isNum(rows[0][k]); })[0] || keys[0] || '';
    var s = (series && series.length ? series : keys.filter(function (k) {
      return k !== x && rows.some(function (r) { return isNum(r[k]); });
    }));
    return { rows: rows, x: x, series: s.slice(0, 6) };
  }

  function svgShell(W, H, inner) {
    return '<svg class="gui-chart-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet" role="img">' + inner + '</svg>';
  }

  function axes(W, H, pad, min, max, format, currency, decimals) {
    var out = '';
    var ticks = 5;
    for (var i = 0; i <= ticks; i++) {
      var value = min + (max - min) * i / ticks;
      var y = pad.top + (H - pad.top - pad.bottom) * (1 - i / ticks);
      out += '<line x1="' + pad.left + '" y1="' + y.toFixed(1) + '" x2="' + (W - pad.right) + '" y2="' + y.toFixed(1) + '" class="gui-chart-grid"/>';
      out += '<text x="' + (pad.left - 8) + '" y="' + (y + 3.5).toFixed(1) + '" class="gui-chart-axis" text-anchor="end">' + esc(fmtValue(value, format, currency, decimals)) + '</text>';
    }
    return out;
  }

  function xLabels(W, H, pad, categories) {
    if (!categories.length) return '';
    var innerW = W - pad.left - pad.right;
    var step = innerW / Math.max(1, categories.length - 1);
    var every = Math.ceil(categories.length / 12);
    var out = '';
    categories.forEach(function (label, i) {
      if (i % every !== 0) return;
      var x = pad.left + step * i;
      var text = String(label == null ? '' : label);
      if (text.length > 12) text = text.slice(0, 11) + '…';
      out += '<text x="' + x.toFixed(1) + '" y="' + (H - pad.bottom + 18) + '" class="gui-chart-axis" text-anchor="middle">' + esc(text) + '</text>';
    });
    return out;
  }

  function legend(series) {
    if (series.length <= 1) return null;
    return h('div', { cls: 'gui-chart-legend' }, series.map(function (name, i) {
      return h('span', { cls: 'gui-chart-legend-item' }, [
        h('span', { cls: 'gui-chart-dot', style: { background: SERIES_COLORS[i % SERIES_COLORS.length] } }),
        t(name)
      ]);
    }));
  }

  function barChart(W, H, data, stacked, format, currency, decimals) {
    var pad = { left: 56, right: 16, top: 18, bottom: 30 };
    var max = 0, min = 0;
    data.rows.forEach(function (row) {
      if (stacked) {
        var sumPos = 0, sumNeg = 0;
        data.series.forEach(function (s) { var v = Number(row[s]) || 0; if (v >= 0) sumPos += v; else sumNeg += v; });
        max = Math.max(max, sumPos); min = Math.min(min, sumNeg);
      } else {
        data.series.forEach(function (s) { var v = Number(row[s]) || 0; max = Math.max(max, v); min = Math.min(min, v); });
      }
    });
    if (max === min) max = min + 1;
    if (max > 0) max = max * 1.08;
    if (min < 0) min = min * 1.08;
    var plotW = W - pad.left - pad.right, plotH = H - pad.top - pad.bottom;
    var y = function (v) { return pad.top + plotH * (1 - (v - min) / (max - min)); };
    var band = plotW / Math.max(1, data.rows.length);
    var groupW = band * 0.68;
    var barW = stacked ? groupW : groupW / Math.max(1, data.series.length);
    var inner = axes(W, H, pad, min, max, format, currency, decimals);
    data.rows.forEach(function (row, i) {
      var baseX = pad.left + band * i + (band - groupW) / 2;
      var accPos = 0, accNeg = 0;
      data.series.forEach(function (s, si) {
        var v = Number(row[s]) || 0;
        var x0 = baseX + (stacked ? 0 : barW * si);
        var y0, barH;
        if (stacked) {
          var start = v >= 0 ? accPos : accNeg;
          var end = start + v;
          y0 = y(Math.max(start, end)); barH = Math.abs(y(start) - y(end));
          if (v >= 0) accPos = end; else accNeg = end;
        } else {
          y0 = y(Math.max(0, v)); barH = Math.abs(y(v) - y(0));
        }
        inner += '<rect x="' + x0.toFixed(1) + '" y="' + y0.toFixed(1) + '" width="' + Math.max(1, barW - 2).toFixed(1) + '" height="' + Math.max(0.5, barH).toFixed(1) + '" rx="3" fill="' + SERIES_COLORS[si % SERIES_COLORS.length] + '" opacity="0.92"><title>' + esc(String(row[data.x])) + ' · ' + esc(s) + ': ' + esc(fmtValue(v, format, currency, decimals)) + '</title></rect>';
      });
    });
    inner += xLabels(W, H, pad, data.rows.map(function (r) { return r[data.x]; }));
    return svgShell(W, H, inner);
  }

  function lineChart(W, H, data, area, format, currency, decimals) {
    var pad = { left: 56, right: 16, top: 18, bottom: 30 };
    var max = 0, min = 0;
    data.rows.forEach(function (row) {
      data.series.forEach(function (s) { var v = Number(row[s]) || 0; max = Math.max(max, v); min = Math.min(min, v); });
    });
    if (max === min) max = min + 1;
    if (max > 0) max = max * 1.08;
    if (min < 0) min = min * 1.08;
    var plotW = W - pad.left - pad.right, plotH = H - pad.top - pad.bottom;
    var y = function (v) { return pad.top + plotH * (1 - (v - min) / (max - min)); };
    var x = function (i) { return pad.left + (data.rows.length <= 1 ? plotW / 2 : plotW * i / (data.rows.length - 1)); };
    var inner = axes(W, H, pad, min, max, format, currency, decimals);
    data.series.forEach(function (s, si) {
      var points = data.rows.map(function (row, i) { return { x: x(i), y: y(Number(row[s]) || 0), v: Number(row[s]) || 0 }; });
      var line = points.map(function (p) { return p.x.toFixed(1) + ',' + p.y.toFixed(1); }).join(' ');
      if (area && points.length) {
        var zero = y(Math.max(min, 0));
        inner += '<polygon points="' + points[0].x.toFixed(1) + ',' + zero.toFixed(1) + ' ' + line + ' ' + points[points.length - 1].x.toFixed(1) + ',' + zero.toFixed(1) + '" fill="' + SERIES_COLORS[si % SERIES_COLORS.length] + '" opacity="0.14"/>';
      }
      inner += '<polyline points="' + line + '" fill="none" stroke="' + SERIES_COLORS[si % SERIES_COLORS.length] + '" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>';
      points.forEach(function (p, i) {
        inner += '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="2.8" fill="' + SERIES_COLORS[si % SERIES_COLORS.length] + '"><title>' + esc(String(data.rows[i][data.x])) + ' · ' + esc(s) + ': ' + esc(fmtValue(p.v, format, currency, decimals)) + '</title></circle>';
      });
    });
    inner += xLabels(W, H, pad, data.rows.map(function (r) { return r[data.x]; }));
    return svgShell(W, H, inner);
  }

  function pieChart(W, H, data, donut, format, currency, decimals) {
    var values = data.rows.map(function (row) { return Math.max(0, Number(row[data.series[0]]) || 0); });
    var total = values.reduce(function (a, b) { return a + b; }, 0);
    var cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 26;
    var innerR = donut ? r * 0.58 : 0;
    var angle = -Math.PI / 2;
    var inner = '';
    values.forEach(function (v, i) {
      if (total <= 0) return;
      var sweep = v / total * Math.PI * 2;
      var end = angle + sweep;
      var large = sweep > Math.PI ? 1 : 0;
      var x0 = cx + r * Math.cos(angle), y0 = cy + r * Math.sin(angle);
      var x1 = cx + r * Math.cos(end), y1 = cy + r * Math.sin(end);
      var path;
      if (donut) {
        var ix1 = cx + innerR * Math.cos(end), iy1 = cy + innerR * Math.sin(end);
        var ix0 = cx + innerR * Math.cos(angle), iy0 = cy + innerR * Math.sin(angle);
        path = 'M' + x0 + ' ' + y0 + 'A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x1 + ' ' + y1 +
          'L' + ix1 + ' ' + iy1 + 'A' + innerR + ' ' + innerR + ' 0 ' + large + ' 0 ' + ix0 + ' ' + iy0 + 'Z';
      } else {
        path = 'M' + cx + ' ' + cy + 'L' + x0 + ' ' + y0 + 'A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x1 + ' ' + y1 + 'Z';
      }
      inner += '<path d="' + path + '" fill="' + SERIES_COLORS[i % SERIES_COLORS.length] + '" opacity="0.94"><title>' + esc(String(data.rows[i][data.x])) + ': ' + esc(fmtValue(v, format, currency, decimals)) + '</title></path>';
      angle = end;
    });
    if (donut && total > 0) {
      inner += '<text x="' + cx + '" y="' + (cy + 5) + '" text-anchor="middle" class="gui-chart-total">' + esc(fmtValue(total, format, currency, decimals)) + '</text>';
    }
    return svgShell(W, H, inner);
  }

  function scatterChart(W, H, data, format, currency, decimals) {
    var pad = { left: 56, right: 16, top: 18, bottom: 30 };
    var xs = data.rows.map(function (r) { return Number(r[data.x]); }).filter(isFinite);
    var ys = [];
    data.rows.forEach(function (r) { data.series.forEach(function (s) { if (isNum(r[s])) ys.push(r[s]); }); });
    var minX = xs.length ? Math.min.apply(null, xs) : 0, maxX = xs.length ? Math.max.apply(null, xs) : 1;
    var minY = ys.length ? Math.min.apply(null, ys) : 0, maxY = ys.length ? Math.max.apply(null, ys) : 1;
    if (minX === maxX) maxX = minX + 1;
    if (minY === maxY) maxY = minY + 1;
    var plotW = W - pad.left - pad.right, plotH = H - pad.top - pad.bottom;
    var px = function (v) { return pad.left + plotW * (v - minX) / (maxX - minX); };
    var py = function (v) { return pad.top + plotH * (1 - (v - minY) / (maxY - minY)); };
    var inner = axes(W, H, pad, minY, maxY, format, currency, decimals);
    data.series.forEach(function (s, si) {
      data.rows.forEach(function (row, i) {
        if (!isNum(Number(row[data.x])) || !isNum(row[s])) return;
        inner += '<circle cx="' + px(Number(row[data.x])).toFixed(1) + '" cy="' + py(row[s]).toFixed(1) + '" r="4" fill="' + SERIES_COLORS[si % SERIES_COLORS.length] + '" opacity="0.85"><title>' + esc(String(row[data.x])) + ', ' + esc(s) + ': ' + esc(fmtValue(row[s], format, currency, decimals)) + '</title></circle>';
      });
    });
    return svgShell(W, H, inner);
  }

  C.Chart = function (args) {
    var type = U.arg(args, 0) || 'bar';
    var data = buildRows(G.plain(args[1]), U.arg(args, 2), U.arr(args[3]));
    var format = U.arg(args, 4);
    var currency = U.arg(args, 5);
    var stacked = U.truthy(args[6]);
    var height = U.numArg(U.arg(args, 7), 260) || 260;
    var W = 640, H = Math.max(140, Math.min(720, height));
    var svg;
    if (!data.rows.length) return h('div', { cls: 'gui-chart-empty' }, [t('暂无数据')]);
    if (type === 'line' || type === 'area') svg = lineChart(W, H, data, type === 'area', format, currency);
    else if (type === 'pie' || type === 'donut') svg = pieChart(W, H, data, type === 'donut', format, currency);
    else if (type === 'scatter') svg = scatterChart(W, H, data, format, currency);
    else svg = barChart(W, H, data, stacked, format, currency);
    return h('div', { cls: 'gui-chart' }, [raw(svg), legend(data.series)]);
  };

  function hashColor(label) {
    var sum = 0;
    for (var i = 0; i < String(label).length; i++) sum = (sum * 31 + String(label).charCodeAt(i)) % 997;
    return SERIES_COLORS[sum % SERIES_COLORS.length];
  }

  function mapProjection(markers, W, H) {
    var pad = 34;
    var lats = markers.map(function (m) { return Number(m.lat); }).filter(isFinite);
    var lngs = markers.map(function (m) { return Number(m.lng); }).filter(isFinite);
    var minLat = Math.min.apply(null, lats.length ? lats : [0]);
    var maxLat = Math.max.apply(null, lats.length ? lats : [1]);
    var minLng = Math.min.apply(null, lngs.length ? lngs : [0]);
    var maxLng = Math.max.apply(null, lngs.length ? lngs : [1]);
    if (maxLat - minLat < 0.05) { minLat -= 0.03; maxLat += 0.03; }
    if (maxLng - minLng < 0.05) { minLng -= 0.03; maxLng += 0.03; }
    var spanLat = maxLat - minLat, spanLng = maxLng - minLng;
    var scale = Math.min((W - pad * 2) / spanLng, (H - pad * 2) / spanLat);
    var offsetX = (W - spanLng * scale) / 2, offsetY = (H - spanLat * scale) / 2;
    return {
      x: function (lng) { return offsetX + (Number(lng) - minLng) * scale; },
      y: function (lat) { return offsetY + (maxLat - Number(lat)) * scale; }
    };
  }

  C.Map = function (args, ctx) {
    var markers = U.arr(args[0]).map(function (m) {
      if (m && m.__node) return G.value(m, ctx);
      return m;
    }).map(function (m) {
      if (!m || !m.__marker) return m;
      return { label: m.label, lat: m.lat, lng: m.lng, description: m.description, category: m.category };
    }).filter(function (m) { return m && m.lat != null && m.lng != null; });
    var route = U.truthy(args[1]);
    var binding = U.bindArg(args[2]);
    var height = U.numArg(U.arg(args, 3), 300) || 300;
    var W = 640, H = Math.max(160, Math.min(640, height));
    if (!markers.length) return h('div', { cls: 'gui-map-empty' }, [t('暂无地点')]);
    var proj = mapProjection(markers, W, H);
    var current = String(G.plain(args[2]) == null ? '' : G.plain(args[2]));
    var nodes = [];
    nodes.push(h('rect', { attrs: { x: 0, y: 0, width: W, height: H, rx: 12, fill: 'var(--gui-map-bg)' } }));
    for (var gi = 1; gi < 4; gi++) {
      nodes.push(h('line', { attrs: { x1: 0, y1: H * gi / 4, x2: W, y2: H * gi / 4, stroke: 'var(--gui-map-grid)', 'stroke-width': 1, 'stroke-dasharray': '4 6' } }));
      nodes.push(h('line', { attrs: { x1: W * gi / 4, y1: 0, x2: W * gi / 4, y2: H, stroke: 'var(--gui-map-grid)', 'stroke-width': 1, 'stroke-dasharray': '4 6' } }));
    }
    if (route && markers.length > 1) {
      var points = markers.map(function (m) { return proj.x(m.lng).toFixed(1) + ',' + proj.y(m.lat).toFixed(1); }).join(' ');
      nodes.push(h('polyline', { attrs: { points: points, fill: 'none', stroke: 'var(--gui-accent)', 'stroke-width': 2, 'stroke-dasharray': '5 5', opacity: 0.55 } }));
    }
    markers.forEach(function (m, i) {
      var label = String(m.label == null ? '地点 ' + (i + 1) : m.label);
      var selected = current === label;
      var color = m.category ? hashColor(m.category) : SERIES_COLORS[i % SERIES_COLORS.length];
      nodes.push(h('circle', {
        attrs: {
          cx: proj.x(m.lng).toFixed(1), cy: proj.y(m.lat).toFixed(1), r: selected ? 9 : 6.5,
          fill: color, stroke: 'var(--gui-surface)', 'stroke-width': selected ? 3 : 2
        },
        ref: function (el) {
          el.style.cursor = 'pointer';
          el.addEventListener('click', function () {
            if (binding) binding.set(label);
            if (ctx && ctx.schedule) ctx.schedule();
          });
          return function () {};
        }
      }, [h('title', {}, [t(label + (m.description ? ' · ' + m.description : ''))])]));
      if (markers.length <= 14) {
        nodes.push(h('text', {
          attrs: {
            x: proj.x(m.lng).toFixed(1), y: (proj.y(m.lat) + 20).toFixed(1),
            'text-anchor': 'middle', fill: 'var(--gui-muted)', 'font-size': 11
          }
        }, [t(label.length > 14 ? label.slice(0, 13) + '…' : label)]));
      }
    });
    return h('div', { cls: 'gui-map' }, [h('svg', {
      attrs: { viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'xMidYMid meet', role: 'img' },
      style: { width: '100%', height: 'auto', display: 'block' }
    }, nodes), route ? h('div', { cls: 'gui-map-caption' }, [t(markers.length + ' 个地点 · 已连线')]) : null]);
  };

  /* 供 Map 使用的标记描述；单独出现在 children 里会被忽略 */
  C.MapMarker = function (args) {
    return {
      __marker: true,
      label: U.str(args[0]),
      lat: U.numArg(U.arg(args, 1), NaN),
      lng: U.numArg(U.arg(args, 2), NaN),
      description: U.str(args[3]) || undefined,
      category: U.str(args[4]) || undefined
    };
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
