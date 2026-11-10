"""UI 插件骨架文件模板（从 factory 逐字搬移）。"""

INDEX_HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>__NAME__</title>
<style>
  /* 宿主 CSS 变量不跨 iframe 继承：自带 token 并 fallback */
  :root {
    --ink: var(--wm-label, #16191d);
    --ink-2: var(--wm-label-2nd, #4c5560);
    --dim: var(--wm-label-dim, #8b96a3);
    --field: var(--wm-bg-input, #f2f4f7);
    --line: var(--wm-border, rgba(15, 17, 21, .08));
    --accent: var(--wm-accent, #16191d);
    --mono: var(--wm-mono, ui-monospace, Consolas, monospace);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: var(--wm-font, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif);
    font-size: 13px; color: var(--ink); background: var(--wm-bg-panel, #fff);
    display: flex; flex-direction: column; gap: 10px; padding: 14px; overflow: auto;
  }
  body.compact { padding: 8px; gap: 6px; }
  h1 { font-size: 14px; font-weight: 600; }
  .card { padding: 12px; border: 1px solid var(--line); border-radius: var(--wm-radius-sm, 8px); }
  .hint { font-size: 11.5px; color: var(--dim); line-height: 1.7; }
  button {
    font: inherit; height: 30px; padding: 0 12px; border-radius: 8px;
    border: 1px solid var(--line); background: #fff; color: var(--ink-2); cursor: pointer;
  }
  button:hover { background: var(--wm-bg-hover, #e9edf1); }
  button.primary { background: var(--accent); border-color: transparent; color: #fff; }
  pre { font-family: var(--mono); font-size: 11.5px; color: var(--dim); white-space: pre-wrap; word-break: break-all; }
</style>
</head>
<body>
  <h1 id="title">__NAME__</h1>
  <div class="card">
    <div class="hint">这是 __ID__ 插件的内容区。改完本文件后，让用户按 Ctrl+R 刷新页面即可看到效果。</div>
  </div>
  <div>
    <button class="primary" id="probe">调一次宿主 callAction</button>
  </div>
  <pre id="out">（未调用）</pre>
<script>
(function () {
  'use strict';
  var PLUGIN_ID = __ID_JSON__;

  /* ---- 宿主桥：插件在 iframe 内，只能通过 postMessage 与宿主通信 ---- */
  var seq = 0, pending = {};
  function callAction(actionId, payload) {
    return new Promise(function (resolve, reject) {
      var id = ++seq;
      pending[id] = { resolve: resolve, reject: reject };
      window.parent.postMessage({ type: 'callAction', id: id, actionId: actionId, payload: payload || {} }, '*');
    });
  }
  window.addEventListener('message', function (e) {
    var m = e.data;
    if (!m || typeof m !== 'object') return;
    if (m.type === 'callActionResult' && pending[m.id]) {
      var p = pending[m.id];
      delete pending[m.id];
      if (m.ok) p.resolve(m.data); else p.reject(new Error(m.error || 'callAction 失败'));
    } else if (m.type === 'configApply') {
      applyConfig(m.config);              // 用户在设置面板改配置 → 实时下发
    } else if (m.type === 'event' && m.event === 'host.unmount') {
      /* iframe 即将卸载：关掉自己开的外部资源（定时器、原生视图等） */
    }
  });

  /* ---- 配置：与 plugin.json 的 configSchema 对应 ---- */
  var config = {};
  function applyConfig(c) {
    config = c || {};
    document.getElementById('title').textContent = config.title || '__NAME_JS__';
    document.body.classList.toggle('compact', !!config.compact);
  }

  var out = document.getElementById('out');
  document.getElementById('probe').addEventListener('click', function () {
    callAction('state.get', {})
      .then(function (data) { out.textContent = JSON.stringify(data, null, 2); })
      .catch(function (err) { out.textContent = '调用失败：' + err.message; });
  });

  callAction('config.get', { plugin_id: PLUGIN_ID }).then(applyConfig).catch(function () {});
})();
</script>
</body>
</html>
"""
