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
    if (!activeId) { setEmpty(true); return; }
    const s = groupState.sessions.find((x) => x.id === activeId);
    const count = s ? Number(s.messages_count) || 0 : 0;
    // 只有「宿主仍处于草稿态」且「后端也仍是草稿」时才算空态欢迎页。
    // 首条消息发出后宿主草稿标记立即清除；后台注入（如随手记投递 main）产生的首条消息
    // 由列表刷新清除。否则处理中的会话会因 messages_count 暂为 0 而退回欢迎页。
    const draft = groupState.draft && (s ? !!s.draft : false);
    setEmpty(draft && count === 0);
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

