// 配置保存、下发与会话草稿（ensureSessionId）
import { broadcastSessions, refreshSessions, updateEmpty } from './sessions.js';
import { configByPlugin, frameByPluginId, frames, groupState } from './state.js';

  // ---- 配置持久化与下发 ----
  export async function saveConfig() {
    const res = await fetch('/api/webmin/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plugins: configByPlugin }),
    });
    if (!res.ok) throw new Error(await res.text());
  }
  export function applyConfigTo(pid: string) {
    const iframe = frameByPluginId[pid];
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage({ type: 'configApply', config: configByPlugin[pid] || {} }, '*');
    }
  }
  // 兼容：frames 用对象，保留原访问方式（值为该 slot 的实例数组）
  export function slots(s: string) { return frames[s]; }

  // 草稿首条消息 → 会话名：剔除控制字符/零宽与双向控制符，折叠空白，最多保留 10 个字。
  // 侧栏卡片用 textContent 渲染并带省略号截断，无需额外转义。
  export function draftSessionAlias(message: string) {
    let text = String(message == null ? '' : message)
      .replace(/[\u0000-\u001f\u007f-\u009f\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (!text) return '';
    const chars = Array.from(text);
    let alias = chars.length > 10 ? chars.slice(0, 10).join('') : text;
    return alias.replace(/[\u200c\u200d]+$/, '').trim();   // 截断后可能留下尾部的零宽连接符
  }

  export async function ensureSessionId(sessionId: string, firstMessage: string): Promise<string> {
    if (sessionId) return sessionId;
    // 草稿态下首个消息到此：此刻才真正建会话，并把用户选的范式一并带入，
    // 保证系统提示词用「所选范式」生成（而非默认范式）。
    // draftProjectId 非空 = 在某个项目里点「新建会话」：后端会把该项目 MEMORY.md 的路径与维护约定注入系统提示
    // 首条消息同时作为会话名（最多 10 个字），之后仍可手动重命名
    const body: Record<string, any> = { paradigm: groupState.draftParadigm || '', project_id: groupState.draftProjectId || '' };
    const alias = draftSessionAlias(firstMessage);
    if (alias) body.alias = alias;
    const created = await (await fetch('/api/sessions/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json();
    if (created && created.id) {
      groupState.activeSessionId = created.id;
      groupState.draft = false;
      groupState.draftParadigm = '';
      groupState.draftProjectId = '';
      await refreshSessions();
      updateEmpty();
      broadcastSessions('session.switched', { session_id: created.id });
      return created.id;
    }
    return '';
  }

  // 当前活动会话的后台 Agent 是否仍在工作（/status 的 is_thinking，与历史面板同源）。
  // 用于「Agent 忙碌时禁止切换会话/新建/拉分支」，保护正在进行的任务数据。
  // 探测失败一律视为空闲（不阻断），避免会话暂不可用时完全无法操作。
  export async function activeSessionBusy() {
    const sid = groupState.activeSessionId;
    if (!sid) return false;
    try {
      const st = await (await fetch('/api/sessions/' + encodeURIComponent(sid) + '/status')).json();
      return !!(st && st.is_thinking);
    } catch (_) { return false; }
  }

