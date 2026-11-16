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
  // ---- 宿主配置保存统一出口 ----
  // 所有 /api/webmin/config 的 PUT 走同一串行队列：每次保存都是整分节快照，并发乱序
  // 到达时旧快照会覆盖新快照（Ctrl+R 后状态回退）；keepalive 让「保存后立刻刷新」时
  // 在途请求不被页面卸载掐死。失败静默（不打断队列），调用方各自决定是否等待。
  let cfgWrite: Promise<unknown> = Promise.resolve();
  export function saveWebminConfig(payload: Record<string, unknown>): Promise<void> {
    const run = cfgWrite.then(() =>
      fetch('/api/webmin/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      }).then((res) => { if (!res.ok) throw new Error(String(res.status)); })
    );
    cfgWrite = run.catch(() => {});
    return run;
  }

