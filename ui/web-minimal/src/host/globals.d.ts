// 全局声明：宿主页面注入的 Electron / 插件接口
import type { ActionOrigin, PurrCatBridge } from './types.js';

declare global {
  interface Window {
    /** Electron preload 暴露的本地能力；普通浏览器中不存在 */
    purrcat?: PurrCatBridge;
    /** 宿主脚本接口：插件 iframe 通过 postMessage 间接调用，调试时可直接调用 */
    purrcatWebmin?: {
      callAction: (
        actionId: string,
        payload?: Record<string, unknown>,
        origin?: Partial<ActionOrigin>,
      ) => Promise<unknown>;
    };
  }
}

export {};
