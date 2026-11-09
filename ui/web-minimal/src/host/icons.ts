// 插件图标绘制（内置 SVG 登记表 / 内联 svg / 文本字形）
import type { PluginDescriptor } from './types.js';

  // ---- 图标集（宿主内置内联 SVG 线性图标，描边跟随 currentColor）----
  // 插件在 plugin.json 的 icon 写这里登记的名字即可；也可内嵌自己的 <svg>…</svg>；
  // 写其它任意字符则按文本字形渲染（兼容只给字符的老插件）。尺寸由宿主 CSS 统一控制。
  // 登记表按任意字符串键索引（插件 icon 字段是自由字符串）
  export const ICON_SVG: Record<string, string> = {
    list: '<path d="M3 6h.01M3 12h.01M3 18h.01"/><path d="M8 6h13M8 12h13M8 18h13"/>',
    pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    'panel-left': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
    'panel-top': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/>',
    'layout-panel-left': '<rect width="7" height="18" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    // sensor 默认图标（配置项未提供 icon 或图标加载失败时回退）
    sensor: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
  };
  export const ICON_SVG_ATTR = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"';
  // 把 icon 画进容器：登记名 → 内置 SVG；<svg> → 去脚本后原样内嵌；其它 → 文本字形
  export function paintIcon(el: HTMLElement, icon?: string, fallbackChar?: string) {
    const raw = String(icon == null ? '' : icon).trim();
    if (/^<svg[\s>]/i.test(raw)) {
      el.innerHTML = raw.replace(/<script[\s\S]*?<\/script>/gi, '');
      return;
    }
    if (ICON_SVG[raw]) {
      el.innerHTML = '<svg ' + ICON_SVG_ATTR + '>' + ICON_SVG[raw] + '</svg>';
      return;
    }
    el.textContent = raw || fallbackChar || '';
  }
  export function paintPluginIcon(el: HTMLElement, p: PluginDescriptor) {
    const nm = (p && (p.name || p.id)) || '?';
    paintIcon(el, p && p.icon, (nm.charAt(0) || '?').toUpperCase());
  }

