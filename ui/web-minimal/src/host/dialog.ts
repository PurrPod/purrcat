// 本地 Electron 对话框与接口错误信息提取

  // ---- 本地 Electron 对话框 ----
  export function pickPath(r: unknown): string | null {
    if (!r) return null;
    if (Array.isArray(r)) return r[0] || null;
    // 原生对话框返回对象结构不固定（filePaths / paths / path），此处仅做局部结构收窄
    const o = r as { filePaths?: unknown; paths?: unknown; path?: unknown };
    if (Array.isArray(o.filePaths)) return o.filePaths[0] || null;
    if (Array.isArray(o.paths)) return o.paths[0] || null;
    if (typeof r === 'string') return r;
    if (typeof o.path === 'string') return o.path;
    return null;
  }

  // ---- 动作分发：宿主直接处理 ----
  // 后端错误统一是 {"detail": "..."}，取 detail 作为可读错误信息
  export async function apiErrorMessage(res: Response, fallback: string): Promise<string> {
    try {
      const text = await res.text();
      try {
        const data = JSON.parse(text);
        return (data && (data.detail || data.message)) || fallback;
      } catch (_) {
        return text || fallback;
      }
    } catch (_) {
      return fallback;
    }
  }

