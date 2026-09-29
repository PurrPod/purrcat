"""UI 插件工厂：在 AgentVM 沙盒里生成 web-minimal 插件的文件框架。

与 Skill / MCP / Sensor 工厂不同，UI 插件不需要 UUID 工作区与 Git 流程：
宿主（src/server/api/webmin.py）把 ``AGENT_VM_DIR/ui-plugin/*`` 直接当作一个插件根目录
扫描，所以这里写下的文件就是"已安装的插件"，改完让用户刷新页面即可看到。
"""

import html
import json
import os
import re

from src.evolve.ui_plugin.guide_generator import generate_ui_plugin_guide
from src.utils.config import AGENT_VM_DIR

UI_PLUGIN_DIR = os.path.join(AGENT_VM_DIR, "ui-plugin")

# 生成时的默认区域：panel 只是"不改就能跑"的保守起点，
# 要入驻其它区域（sidebar / input / pet / popup ...）直接改 plugin.json 的 slot.area 即可。
DEFAULT_AREA = "panel"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

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


def _plugin_json(plugin_id: str, name: str, area: str, goal: str) -> str:
    doc = {
        "id": plugin_id,
        "name": name,
        "description": goal or f"{name}（极简模式 UI 插件）",
        "icon": "panel-left",
        "slot": {"area": area},
        "entry": "index.html",
        "configSchema": [
            {"key": "title", "label": "标题", "type": "text", "default": name},
            {"key": "compact", "label": "紧凑模式", "type": "switch", "default": False},
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def ui_plugin_init(
    target: str, name: str = "", goal: str = ""
) -> tuple[str, str | None]:
    """生成 UI 插件文件框架。

    Args:
        target: 插件 id（目录名，也是 plugin.json 的 id）
        name:   显示名，缺省用插件 id
        goal:   本次开发目标，写进插件描述与指南

    Returns:
        (给 Agent 的说明文本, 插件目录绝对路径)；参数非法/目录已存在时目录为 None。
    """
    plugin_id = (target or "").strip()
    if not _ID_RE.match(plugin_id):
        return (
            "❌ 插件 id 非法：只能用小写字母、数字、'-'、'_'，且以字母或数字开头"
            f"（当前为 {target!r}）。换个名字再来。",
            None,
        )

    plugin_name = (name or "").strip() or plugin_id
    plugin_dir = os.path.join(UI_PLUGIN_DIR, plugin_id)
    if os.path.exists(plugin_dir):
        return (
            f"❌ 目标目录已存在：{plugin_dir}\n"
            "同一 id 只能有一份框架；要改代码请直接编辑它，要重建请先删掉整个目录。",
            None,
        )

    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
        f.write(_plugin_json(plugin_id, plugin_name, DEFAULT_AREA, goal))
    index_html = (
        INDEX_HTML_TPL.replace("__ID_JSON__", json.dumps(plugin_id))
        .replace("__NAME_JS__", plugin_name.replace("\\", "\\\\").replace("'", "\\'"))
        .replace("__NAME__", html.escape(plugin_name))
        .replace("__ID__", html.escape(plugin_id))
    )
    with open(os.path.join(plugin_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    guide = generate_ui_plugin_guide(
        plugin_id, plugin_name, DEFAULT_AREA, plugin_dir, goal
    )
    return guide, plugin_dir
