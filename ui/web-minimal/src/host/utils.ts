// 通用工具（有效配置合并、插件槽反查）
import { slotByPluginId } from './state.js';
import type { PluginDescriptor } from './types.js';

  // ---- 工具 ----
  export function effectiveConfig(desc: PluginDescriptor): Record<string, unknown> {
    const sch = desc.configSchema || [];
    const stored = desc.config || {};
    const out: Record<string, unknown> = {};
    sch.forEach((f) => {
      if (f.default !== undefined) out[f.key] = f.default;
      else if (f.type === 'switch') out[f.key] = false;
      else if (f.type === 'number') out[f.key] = 0;
      else if (f.type === 'select') out[f.key] = (f.options && f.options[0]) || '';
      else out[f.key] = '';
    });
    Object.assign(out, stored);
    return out;
  }
  export function slotOfPlugin(pid: string): string | null {
    return slotByPluginId[pid] || null;
  }

