/* ============================================================
   web-minimal 宿主核心（白灰改造版）
   - 加载 /api/webmin/manifest 拿到插件清单 + configSchema + config
   - 按 slot 把插件渲染为 iframe；每个 slot 挂载首个匹配插件
   - callAction 动作总线：
       * 聊天/会话/配置/引用/枚举 → 直接同源 fetch 现有 /api/*
       * 本地 Electron 能力（对话框/窗口控制/壁纸选择）→ 仅在宿主访问 window.purrcat
   - 配置管理：manifest → effective() 合并 schema 默认值+已存值，
     通过 config.get / config.set / configApply 注入插件
   - 广播事件：动作后向相关 slot 广播 {type:'event', event, data}
   ============================================================ */

import { HOST } from './state.js';
import './layout.js';
import './icons.js';
import './rail.js';
import './areas.js';
import './utils.js';
import './sessions.js';
import './settings-appearance.js';
import './settings-cards.js';
import './settings-tabs.js';
import './config-center.js';
import './config-apply.js';
import './dialog.js';
import './actions.js';
import './bus.js';
import './float.js';
import './panel.js';
import './tile.js';
import './links.js';
import './mount.js';
import './manifest.js';
import './app.js';
import { callAction } from './bus.js';
import { boot } from './app.js';

// 宿主侧脚本接口
// 全局声明的 purrcatWebmin 面向插件调试、参数类型比 callAction 更宽松，这里仅做类型适配
HOST.purrcatWebmin = { callAction } as unknown as typeof HOST.purrcatWebmin;

// 入口：DOM 就绪后启动
if (HOST.document.readyState === 'loading') {
  HOST.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
