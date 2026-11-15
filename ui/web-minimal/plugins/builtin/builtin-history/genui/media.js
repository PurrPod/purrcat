/* PurrCat GenUI —— 媒体识别与内嵌播放器 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};

  var IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif'];
  var AUDIO_EXTS = ['mp3', 'wav', 'ogg', 'oga', 'm4a', 'aac', 'flac', 'opus'];
  var VIDEO_EXTS = ['mp4', 'webm', 'ogv', 'mov', 'm4v', 'mkv'];
  var GENUI_EXTS = ['genui', 'openui'];

  function stripQuery(src) {
    return String(src == null ? '' : src).split(/[?#]/)[0];
  }

  function extOf(src) {
    var clean = stripQuery(src).replace(/\\/g, '/');
    var base = clean.slice(clean.lastIndexOf('/') + 1);
    var dot = base.lastIndexOf('.');
    return dot > 0 ? base.slice(dot + 1).toLowerCase() : '';
  }

  function isLocal(src) {
    var s = String(src == null ? '' : src);
    if (!s) return false;
    if (s.indexOf('file://') === 0) return true;
    if (/^(?:\.{0,2}\/)agent_vm(?:\/|$)/.test(s)) return true;
    if (/^[A-Za-z]:[/\\]/.test(s)) return true;
    if (s.indexOf('./') === 0 || s.indexOf('../') === 0) return true;
    return false;
  }

  function localPath(src) {
    var s = String(src == null ? '' : src);
    if (s.indexOf('file://') === 0) {
      var p = s.replace(/^file:\/\//, '');
      if (p.charAt(0) === '/' && p.charAt(2) === ':') p = p.substring(1);
      try { return decodeURIComponent(p); } catch (e) { return p; }
    }
    try { return decodeURIComponent(s); } catch (e) { return s; }
  }

  function kind(src) {
    var ext = extOf(src);
    if (GENUI_EXTS.indexOf(ext) >= 0) return 'genui';
    if (IMAGE_EXTS.indexOf(ext) >= 0) return 'image';
    if (AUDIO_EXTS.indexOf(ext) >= 0) return 'audio';
    if (VIDEO_EXTS.indexOf(ext) >= 0) return 'video';
    return '';
  }

  function previewUrl(path) {
    return '/api/filesystem/preview?path=' + encodeURIComponent(path);
  }

  function readUrl(path) {
    return '/api/filesystem/read?path=' + encodeURIComponent(path);
  }

  function resolve(src) {
    var s = String(src == null ? '' : src);
    return isLocal(s) ? previewUrl(localPath(s)) : s;
  }

  function fileName(src) {
    var clean = stripQuery(String(src == null ? '' : src)).replace(/\\/g, '/');
    var base = clean.slice(clean.lastIndexOf('/') + 1);
    try { return decodeURIComponent(base); } catch (e) { return base; }
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function faceSVG(path) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="' + path + '"/></svg>';
  }

  var ICONS = {
    audio: faceSVG('M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'),
    video: faceSVG('m22 8-6 4 6 4V8ZM2 6h14v12H2z'),
    genui: faceSVG('M4 5h16v14H4zM4 9h16M9 9v10')
  };

  function embedHTML(alt, src, k) {
    var name = alt ? String(alt) : fileName(src);
    if (k === 'image') {
      return '<figure class="media-embed media-image"><img src="' + esc(resolve(src)) + '" alt="' + esc(alt || name) +
        '" loading="lazy" decoding="async"><figcaption>' + esc(name) + '</figcaption></figure>';
    }
    var url = esc(resolve(src));
    var head = '<div class="media-head"><span class="media-ico">' + (ICONS[k] || '') + '</span><span class="media-name" title="' +
      esc(name) + '">' + esc(name) + '</span><a class="media-open" href="' + url +
      '" target="_blank" rel="noopener noreferrer">打开</a></div>';
    if (k === 'audio') {
      return '<div class="media-embed media-audio">' + head +
        '<audio controls preload="metadata" src="' + url + '"></audio></div>';
    }
    return '<div class="media-embed media-video">' + head +
      '<video controls preload="metadata" playsinline src="' + url + '"></video></div>';
  }

  function genuiHTML(alt, src) {
    var path = isLocal(src) ? localPath(src) : String(src == null ? '' : src);
    return '<div class="genui-card gui-scope genui-file" data-genui-file="' + esc(path) + '">' +
      '<div class="genui-body">' + (alt ? esc(alt) : '') + '加载中…</div></div>';
  }

  // 把 Markdown 渲染结果里的 <img> 换成内嵌媒体：本地图片/音视频、.genui 占位卡
  function decorate(root) {
    if (!root || !root.querySelectorAll || typeof document === 'undefined') return root;
    Array.prototype.slice.call(root.querySelectorAll('img')).forEach(function (img) {
      var src = img.getAttribute('src') || '';
      var k = kind(src);
      if (!k) return;
      var local = isLocal(src);
      // 远程图片保持原生 <img>；远程 .genui 无法跨域读取，保持原样
      if ((k === 'image' || k === 'genui') && !local) return;
      var alt = img.getAttribute('alt') || '';
      var box = document.createElement('div');
      box.innerHTML = k === 'genui' ? genuiHTML(alt, src) : embedHTML(alt, src, k);
      var node = box.firstChild;
      if (!node) return;
      var parent = img.parentNode;
      // 独占一段的图片把外层 <p> 一起换掉，避免块级卡片嵌在段落里
      if (parent && parent.tagName === 'P' && parent.childNodes.length === 1 && parent.parentNode) {
        parent.parentNode.replaceChild(node, parent);
      } else if (parent) {
        parent.replaceChild(node, img);
      }
    });
    return root;
  }

  G.media = {
    isLocal: isLocal,
    localPath: localPath,
    kind: kind,
    extOf: extOf,
    previewUrl: previewUrl,
    readUrl: readUrl,
    resolve: resolve,
    fileName: fileName,
    embedHTML: embedHTML,
    genuiHTML: genuiHTML,
    decorate: decorate
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
