// 会话列表与空态（刷新 / 广播）
import { broadcast, broadcastAll } from './bus.js';
import { groupState } from './state.js';

  // ---- 空态 ----（沿用现有机制）
  export function setEmpty(v: unknown) {
    groupState.empty = !!v;
    broadcast('session', 'layout.empty', { empty: !!v });
  }
  export function updateEmpty() {
    const activeId = groupState.activeSessionId;
    let empty = !activeId;
    if (activeId) {
      const s = groupState.sessions.find((x) => x.id === activeId);
      const count = s ? Number(s.messages_count) || 0 : 0;
      empty = count === 0;
    }
    setEmpty(empty);
  }
  // 重新拉取会话列表，保证 empty 判定与侧栏高亮基于最新数据
  export async function refreshSessions() {
    try {
      const list = await (await fetch('/api/sessions')).json();
      groupState.sessions = Array.isArray(list) ? list : groupState.sessions;
    } catch (_) { /* 保持原样 */ }
  }
  // 会话状态变更事件需同时通知会话卡片(history)与侧栏(列表)，侧栏据此刷新选中高亮
  export function broadcastSessions(event: string, data?: unknown) {
    // 切换会话：分支视图一律回到主干，并广播给输入框等插件（子代理视图只读）
    if (event === 'session.switched') {
      groupState.activeBranchId = 'main';
      broadcastAll('branch.switched', { branch_id: 'main' });
    }
    broadcast('session', event, data);
    broadcast('sidebar', event, data);
  }

