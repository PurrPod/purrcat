/* PurrCat GenUI —— 图标、图片、表格与媒体组件 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};
  var h = G.h, t = G.t, raw = G.raw, U = G.util, C = G.components;

  var ICONS = {
    pin: '<path d="M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    'map-pin': '<path d="M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/>',
    timer: '<circle cx="12" cy="13" r="8"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="9" y1="2" x2="15" y2="2"/>',
    search: '<circle cx="11" cy="11" r="7"/><line x1="20" y1="20" x2="16.2" y2="16.2"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    'check-circle': '<circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16 9"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    'x-circle': '<circle cx="12" cy="12" r="9"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    star: '<polygon points="12 3 14.9 9 21.4 9.8 16.7 14.4 17.9 20.8 12 17.7 6.1 20.8 7.3 14.4 2.6 9.8 9.1 9"/>',
    heart: '<path d="M20.8 5.6a5.2 5.2 0 0 0-7.4 0L12 7l-1.4-1.4a5.2 5.2 0 0 0-7.4 7.4L12 21l8.8-8a5.2 5.2 0 0 0 0-7.4z"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2 21c0-3.6 3.1-6 7-6s7 2.4 7 6"/><path d="M17 5a3.5 3.5 0 0 1 0 7"/><path d="M22 21c0-3-1.8-5.2-4.5-5.8"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14 3h-4l-.6 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2L10 21h4l.6-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><polyline points="14 3 14 8 19 8"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    download: '<path d="M12 3v12"/><polyline points="7 10 12 15 17 10"/><path d="M4 19h16"/>',
    upload: '<path d="M12 21V9"/><polyline points="7 14 12 9 17 14"/><path d="M4 5h16"/>',
    play: '<polygon points="6 4 20 12 6 20"/>',
    pause: '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    minus: '<line x1="5" y1="12" x2="19" y2="12"/>',
    'arrow-right': '<line x1="4" y1="12" x2="20" y2="12"/><polyline points="14 6 20 12 14 18"/>',
    'arrow-left': '<line x1="20" y1="12" x2="4" y2="12"/><polyline points="10 6 4 12 10 18"/>',
    'arrow-up': '<line x1="12" y1="20" x2="12" y2="4"/><polyline points="6 10 12 4 18 10"/>',
    'arrow-down': '<line x1="12" y1="4" x2="12" y2="20"/><polyline points="6 14 12 20 18 14"/>',
    'chevron-down': '<polyline points="6 9 12 15 18 9"/>',
    'chevron-up': '<polyline points="6 15 12 9 18 15"/>',
    'chevron-right': '<polyline points="9 6 15 12 9 18"/>',
    'chevron-left': '<polyline points="15 6 9 12 15 18"/>',
    info: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><circle cx="12" cy="8" r="0.6" fill="currentColor"/>',
    'alert-circle': '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="13"/><circle cx="12" cy="16.5" r="0.6" fill="currentColor"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    home: '<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><polyline points="3 7 12 13 21 7"/>',
    phone: '<path d="M6 3h3l2 5-2.5 1.5a12 12 0 0 0 6 6L16 13l5 2v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5a2 2 0 0 1 2-2z"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7L11.5 7"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7L12.5 17"/>',
    'external-link': '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><polyline points="20 4 20 9 15 9"/>',
    trash: '<polyline points="4 7 20 7"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
    edit: '<path d="M4 20h4l11-11-4-4L4 16z"/><line x1="14" y1="5" x2="19" y2="10"/>',
    globe: '<circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><polyline points="4 18 9 13 13 17 16 14 20 18"/>',
    code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    database: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    cpu: '<rect x="7" y="7" width="10" height="10" rx="2"/><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>',
    zap: '<polygon points="13 2 4 14 11 14 10 22 20 10 13 10"/>',
    activity: '<polyline points="3 12 8 12 11 5 14 19 17 12 21 12"/>',
    'trending-up': '<polyline points="3 17 9 11 13 15 21 7"/><polyline points="15 7 21 7 21 13"/>',
    'trending-down': '<polyline points="3 7 9 13 13 9 21 17"/><polyline points="15 17 21 17 21 11"/>',
    dollar: '<line x1="12" y1="2" x2="12" y2="22"/><path d="M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 7s2.2 3.3 5 3.7 5 1.3 5 3.6-2.2 3.2-5 3.2-5-1.1-5-3"/>',
    cart: '<circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/><path d="M2 3h3l2.4 12h11L21 6H6"/>',
    package: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><polyline points="3 8 12 13 21 8"/><line x1="12" y1="13" x2="12" y2="21"/>',
    coffee: '<path d="M4 8h12v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z"/><path d="M16 9h2a2.5 2.5 0 0 1 0 5h-2"/><line x1="4" y1="22" x2="16" y2="22"/>',
    book: '<path d="M4 4h6a3 3 0 0 1 3 3v13a3 3 0 0 0-3-3H4z"/><path d="M20 4h-6a3 3 0 0 0-3 3v13a3 3 0 0 1 3-3h6z"/>',
    music: '<circle cx="7" cy="18" r="3"/><circle cx="18" cy="16" r="3"/><path d="M10 18V6l11-2v12"/>',
    camera: '<path d="M3 8h3l2-3h8l2 3h3v11H3z"/><circle cx="12" cy="13" r="3.5"/>',
    lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    unlock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7-2.6"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    filter: '<polygon points="3 5 21 5 14 13 14 20 10 18 10 13"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
    more: '<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
    send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9"/>',
    share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="10.6" x2="15.4" y2="6.4"/><line x1="8.6" y1="13.4" x2="15.4" y2="17.6"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    bell: '<path d="M18 8a6 6 0 1 0-12 0c0 6-3 7-3 7h18s-3-1-3-7"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    bookmark: '<path d="M6 3h12v18l-6-4-6 4z"/>',
    briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="3" y1="12" x2="21" y2="12"/>',
    navigation: '<polygon points="3 11 22 2 13 21 11 13"/>',
    map: '<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>',
    'thumbs-up': '<path d="M7 22H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3"/><path d="M7 11l4-8a2 2 0 0 1 2 2v5h5a2 2 0 0 1 2 2.3l-1.3 7A2 2 0 0 1 16.7 21H7z"/>',
    smile: '<circle cx="12" cy="12" r="9"/><path d="M8 14a5 5 0 0 0 8 0"/><circle cx="9" cy="10" r="0.7" fill="currentColor"/><circle cx="15" cy="10" r="0.7" fill="currentColor"/>',
    gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8"/><line x1="12" y1="8" x2="12" y2="21"/><path d="M12 8C12 5 10.5 3 8.5 3S6 4.5 6 6s1.5 2 2.5 2z"/><path d="M12 8c0-3 1.5-5 3.5-5S18 4.5 18 6s-1.5 2-2.5 2z"/>',
    lightbulb: '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 1 3.5 10.9c-.6.5-.9 1.2-.9 2.1H9.4c0-.9-.3-1.6-.9-2.1A6 6 0 0 1 12 3z"/>',
    rocket: '<path d="M5 15c-1 3 0 5 0 5s2 1 5 0"/><path d="M14 4c4 0 6 2 6 6 0 4-4 8-8 10l-4-4C10 12 10 4 14 4z"/><circle cx="15" cy="9" r="1.6"/>',
    server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><circle cx="7" cy="7.5" r="0.8" fill="currentColor"/><circle cx="7" cy="16.5" r="0.8" fill="currentColor"/>',
    terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><polyline points="7 9 10 12 7 15"/><line x1="12" y1="15" x2="17" y2="15"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/>',
    award: '<circle cx="12" cy="9" r="6"/><path d="M8.5 14 7 22l5-3 5 3-1.5-8"/>',
    flag: '<path d="M5 3v18"/><path d="M5 4h13l-2.5 4L18 12H5"/>',
    tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/>',
    sparkles: '<path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z"/><path d="M18.5 15l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>'
  };

  var ICON_SIZE = { sm: 14, md: 18, lg: 24, xl: 32 };

  C.Icon = function (args) {
    var name = U.str(args[0]) || 'info';
    var size = U.arg(args, 1) || 'md';
    var px = ICON_SIZE[size] || (Number(size) || 18);
    var color = U.arg(args, 2);
    var body = ICONS[name] || ICONS.info;
    var style = { width: px + 'px', height: px + 'px' };
    var css = G.color(color);
    if (css) style.color = css;
    return h('span', {
      cls: 'gui-icon',
      style: style,
      attrs: { 'data-icon': name, title: name },
      html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + body + '</svg>'
    });
  };

  function genImage(query, aspectRatio) {
    var size = 'landscape_4_3';
    if (aspectRatio && aspectRatio < 1) size = 'portrait_4_3';
    else if (aspectRatio && aspectRatio >= 1.5) size = 'landscape_16_9';
    var prompt = String(query || 'abstract') + ', high quality photograph, natural light, realistic';
    return 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=' + encodeURIComponent(prompt) + '&image_size=' + size;
  }

  function imageBox(src, alt, args, ctx) {
    var aspect = U.numArg(U.arg(args, 2), 0);
    var fit = U.arg(args, 3) === 'contain' ? 'contain' : 'cover';
    var s = { aspectRatio: aspect > 0 ? String(aspect) : '16 / 9', borderRadius: G.radius(args[4]) || '10px', objectFit: fit, width: '100%', display: 'block' };
    return h('img', {
      cls: 'gui-image',
      style: s,
      attrs: { src: src, alt: alt || '', loading: 'lazy', referrerpolicy: 'no-referrer' },
      ref: function (el) {
        var tried = false;
        el.addEventListener('error', function () {
          if (tried) { el.style.opacity = '0.35'; return; }
          tried = true;
          el.src = genImage(alt || 'image', aspect);
        });
        return function () {};
      }
    });
  }

  C.Image = function (args, ctx) {
    return imageBox(U.str(args[0]), U.str(args[1]), args, ctx);
  };

  C.SearchImage = function (args, ctx) {
    var query = U.str(args[0]);
    return imageBox(genImage(query, U.numArg(U.arg(args, 1), 1.4)), query, args, ctx);
  };

  function cellValue(v, ctx) {
    if (v && typeof v === 'object' && v.__node) return G.value(v, ctx);
    if (v === null) return '—';
    if (typeof v === 'number') return String(v);
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    return v == null ? '' : String(v);
  }

  C.Table = function (args, ctx) {
    var columns = U.arr(args[0]).map(function (c) { return String(c); });
    var rows = U.arr(args[1]);
    var head = h('thead', {}, [h('tr', {}, columns.map(function (c) { return h('th', {}, [t(c)]); }))]);
    var body = h('tbody', {}, rows.map(function (row) {
      var cells = Array.isArray(row) ? row : columns.map(function (c) { return row ? row[c] : null; });
      return h('tr', {}, cells.map(function (cell, i) {
        var isNum = typeof cell === 'number';
        var content = cellValue(cell, ctx);
        return h('td', { cls: isNum ? 'num' : '' }, [typeof content === 'string' ? t(content) : content]);
      }));
    }));
    return h('div', { cls: 'gui-table-wrap' }, [h('table', { cls: 'gui-table' }, [head, body])]);
  };

  C.Audio = function (args) {
    var src = U.str(args[0]);
    var url = G.media ? G.media.resolve(src) : src;
    var name = U.str(args[1]) || (G.media ? G.media.fileName(src) : src);
    var sub = U.str(args[2]);
    return h('div', { cls: 'gui-media gui-audio' }, [
      h('div', { cls: 'gui-media-head' }, [
        h('span', { cls: 'gui-media-ico', html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"/></svg>' }),
        h('div', { cls: 'gui-media-title' }, [
          h('span', { cls: 'gui-media-name' }, [t(name)]),
          sub ? h('span', { cls: 'gui-media-sub' }, [t(sub)]) : null
        ])
      ]),
      h('audio', { attrs: { controls: true, preload: 'metadata', src: url } })
    ]);
  };

  C.Video = function (args) {
    var src = U.str(args[0]);
    var url = G.media ? G.media.resolve(src) : src;
    var poster = U.str(args[1]);
    var name = U.str(args[2]) || (G.media ? G.media.fileName(src) : src);
    var ratio = U.str(args[3]);
    return h('div', { cls: 'gui-media gui-media-video' }, [
      h('div', { cls: 'gui-media-head' }, [
        h('span', { cls: 'gui-media-ico', html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m22 8-6 4 6 4V8ZM2 6h14v12H2z"/></svg>' }),
        h('span', { cls: 'gui-media-name' }, [t(name)])
      ]),
      h('video', {
        cls: 'gui-media-player',
        style: ratio ? { aspectRatio: String(ratio) } : null,
        attrs: {
          controls: true, preload: 'metadata', playsinline: true,
          src: url, poster: poster || null
        }
      })
    ]);
  };

  C.YouTube = function (args) {
    var id = U.str(args[0]);
    var m = /(?:v=|youtu\.be\/|embed\/|shorts\/)([\w-]{6,})/.exec(id);
    if (m) id = m[1];
    return h('div', { cls: 'gui-video' }, [
      h('iframe', {
        attrs: {
          src: 'https://www.youtube.com/embed/' + encodeURIComponent(id),
          title: U.str(args[1]) || 'YouTube',
          frameborder: '0',
          allow: 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture',
          allowfullscreen: true,
          loading: 'lazy'
        }
      })
    ]);
  };

  G.Icons = ICONS;
})(typeof globalThis !== 'undefined' ? globalThis : this);
