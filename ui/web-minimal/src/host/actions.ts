// 动作分发：插件 action → 后端 API / 宿主行为
import { broadcast, broadcastAll } from './bus.js';
import { activeSessionBusy, applyConfigTo, ensureSessionId, saveConfig } from './config-apply.js';
import { apiErrorMessage, pickPath } from './dialog.js';
import { openUrlInBrowserPanel } from './links.js';
import { reloadManifest } from './manifest.js';
import { buildRail, setPluginHidden } from './rail.js';
import { broadcastSessions, refreshSessions, setEmpty, updateEmpty } from './sessions.js';
import { setSettingsOpen } from './settings-appearance.js';
import { CONFIG_NAV, activateSlotPlugin, settingsTab, setSettingsTab } from './settings-tabs.js';
import { HOST, activeBySlot, configByPlugin, groupState } from './state.js';

  export async function dispatch(
    actionId: string,
    payload: Record<string, any> = {},
    origin?: import('./types.js').ActionOrigin,
  ): Promise<unknown> {
    payload = payload || {};
    switch (actionId) {
      case 'chat.send': {
        let sessionId = await ensureSessionId(payload.session_id || groupState.activeSessionId, payload.message);
        if (!sessionId) throw new Error('无法创建会话');
        groupState.activeSessionId = sessionId;
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: payload.message || '' }),
        });
        if (!res.ok) throw new Error(await res.text());
        setEmpty(false);
        const body = await res.json();
        // 乐观本地即时显示用户消息，随后 fetch 同步（后端异步写入，fetch 慢时也不丢"你好"）
        // 用后端回传的 processed_message：超长输入会被后端替换为「已落盘」占位符，
        // 若这里仍广播原文，占位符永远确认不掉原文，乐观消息会一直卡在列表最下方
        const shown = body && typeof body.processed_message === 'string' ? body.processed_message : (payload.message || '');
        if (shown) broadcast('session', 'conversation.local', { session_id: sessionId, events: [{ role: 'user', content: String(shown) }] });
        refreshSessions().then(updateEmpty);   // 更新 messages_count，维持 empty 状态准确
        broadcastSessions('conversation.updated', { session_id: sessionId });
        return body;
      }
      case 'chat.sendBatch': {
        // 草稿态建会话时用批次里的首条用户文本命名（输入框消息就是这个事件）
        const batch = Array.isArray(payload.events) ? payload.events : [];
        const firstUser = batch.find((ev) => ev && ev.type === 'user' && typeof ev.content === 'string');
        let sessionId = await ensureSessionId(payload.session_id || groupState.activeSessionId, firstUser ? firstUser.content : '');
        if (!sessionId) throw new Error('无法创建会话');
        groupState.activeSessionId = sessionId;
        const res = await fetch('/api/chat/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, events: payload.events || [] }),
        });
        if (!res.ok) throw new Error(await res.text());
        setEmpty(false);
        const body = await res.json();
        // 乐观本地即时显示 type=user 的事件，随后 fetch 同步去重。
        // 用后端回传的 processed_events：超长输入已替换为「已落盘」占位符，广播原文会卡在列表最下方
        const evs = (body && Array.isArray(body.processed_events)) ? body.processed_events : (Array.isArray(payload.events) ? payload.events : []);
        const uv = evs.filter((e: { type?: string }) => e && e.type === 'user').map((e: { content?: unknown }) => ({ role: 'user', content: String(e.content || '') }));
        if (uv.length) broadcast('session', 'conversation.local', { session_id: sessionId, events: uv });
        refreshSessions().then(updateEmpty);
        broadcastSessions('conversation.updated', { session_id: sessionId });
        return body;
      }
      case 'sessions.list': {
        const list = await (await fetch('/api/sessions')).json();
        groupState.sessions = list || [];
        updateEmpty();
        return groupState.sessions;
      }
      case 'sessions.new': {
        // Agent 忙碌时禁止新建并切走，避免打断正在进行的任务
        if (await activeSessionBusy()) return { status: 'busy' };
        // 纯前端草稿态：不落盘、不进列表。会话延迟到首条消息时由 ensureSessionId 创建，
        // 届时按 draftParadigm 生成系统提示词；从项目内新建时携带 draftProjectId。
        groupState.draft = true;
        groupState.draftParadigm = '';
        groupState.draftProjectId = String(payload.project_id || '');
        groupState.activeSessionId = '';
        await refreshSessions();
        updateEmpty();
        broadcastSessions('session.switched', { session_id: '' });
        return { status: 'ok', draft: true };
      }
      case 'session.switch': {
        const target = String(payload.session_id || '');
        // 切到「同一个」会话无需拦截；切到不同会话时若 Agent 忙碌则拒绝（对齐原 UI：等待任务完成再切换）
        if (target && target !== groupState.activeSessionId && (await activeSessionBusy())) return { status: 'busy' };
        // 切到已有会话即退出草稿态（放弃未发送的新会话占位与项目草稿归属）
        if (target) {
          groupState.draft = false;
          groupState.draftProjectId = '';
        }
        if (target) {
          // 关键：把后端「当前活跃会话」一并检出。后端 Agent 只挂载一个活跃会话，
          // 未指定 session_id 的外部事件会路由到它；只改前端状态不 checkout，
          // 新事件仍会落进上一个会话。
          const res = await fetch('/api/sessions/' + encodeURIComponent(target) + '/checkout', { method: 'POST' });
          if (!res.ok) throw new Error((await res.text()) || '切换会话失败');
          groupState.activeSessionId = target;
          await refreshSessions();
          updateEmpty();
          broadcastSessions('session.switched', { session_id: target });
        }
        return { status: 'ok' };
      }
      // 重命名会话：对齐后端 PUT /api/sessions/{id}/rename
      case 'session.rename': {
        const sid = String(payload.session_id || '');
        const alias = String(payload.alias || '').trim();
        if (!sid) throw new Error('缺少 session_id');
        if (!alias) throw new Error('会话名称不能为空');
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid) + '/rename', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ alias }),
        });
        if (!res.ok) throw new Error((await res.text()) || '重命名失败');
        await refreshSessions();
        broadcastSessions('conversation.updated', { session_id: sid });
        broadcast('session', 'session.renamed', { session_id: sid, alias });
        return { status: 'ok', alias };
      }
      // 删除会话：对齐后端 DELETE /api/sessions/{id}
      case 'session.delete': {
        const sid = String(payload.session_id || '');
        if (!sid) throw new Error('缺少 session_id');
        const wasActive = groupState.activeSessionId === sid;
        // 后端禁止删除正在活跃的会话：删当前会话前先把它检出到另一个会话，
        // 否则前端与后端活跃会话同步后这条请求必被拒绝
        if (wasActive) {
          const other = groupState.sessions.find((s) => s.id !== sid);
          if (other) {
            const co = await fetch('/api/sessions/' + encodeURIComponent(other.id) + '/checkout', { method: 'POST' });
            if (!co.ok) throw new Error((await co.text()) || '切换会话失败');
          }
        }
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid), { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.text()) || '删除失败');
        // 删掉的正是当前会话：清空活动会话（回到欢迎态），并让各 slot 重新对账
        if (wasActive) groupState.activeSessionId = '';
        await refreshSessions();
        updateEmpty();
        // 只有当前会话被删才需要切换事件；删其它会话不打断正在进行的会话（避免清空乐观消息缓冲）
        broadcastSessions(wasActive ? 'session.switched' : 'conversation.updated', { session_id: groupState.activeSessionId });
        return { status: 'ok' };
      }
      // ---- 项目（会话分类器）：对齐后端 /api/projects* ----
      case 'projects.list': {
        const list = await (await fetch('/api/projects')).json();
        return Array.isArray(list) ? list : [];
      }
      case 'projects.create': {
        const name = String(payload.name || '').trim();
        if (!name) throw new Error('项目名称不能为空');
        const res = await fetch('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, '创建项目失败'));
        const data = await res.json();
        broadcast('sidebar', 'projects.updated', { project_id: data.id });
        return data;
      }
      case 'projects.update': {
        const pid = String(payload.project_id || '');
        if (!pid) throw new Error('缺少 project_id');
        const body: Record<string, any> = {};
        if (payload.name !== undefined) body.name = String(payload.name).trim();
        const res = await fetch('/api/projects/' + encodeURIComponent(pid), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, '保存项目失败'));
        const data = await res.json();
        broadcast('sidebar', 'projects.updated', { project_id: pid });
        return data;
      }
      case 'projects.delete': {
        const pid = String(payload.project_id || '');
        if (!pid) throw new Error('缺少 project_id');
        const deleteSessions = !!payload.delete_sessions;
        // 连会话一起删时，先把当前活跃会话挪出该项目（后端拒删活跃会话）
        if (deleteSessions) {
          const inProject = groupState.sessions.filter((s) => String(s.project_id || '') === pid);
          if (inProject.some((s) => s.id === groupState.activeSessionId)) {
            const other = groupState.sessions.find((s) => String(s.project_id || '') !== pid);
            if (!other) throw new Error('项目内只剩当前活跃会话，请先新建或切换到其它会话再删除');
            const co = await fetch('/api/sessions/' + encodeURIComponent(other.id) + '/checkout', { method: 'POST' });
            if (!co.ok) throw new Error(await apiErrorMessage(co, '切换会话失败'));
            groupState.activeSessionId = other.id;
            groupState.draft = false;
            groupState.draftProjectId = '';
            broadcastSessions('session.switched', { session_id: other.id });
          }
        }
        const res = await fetch('/api/projects/' + encodeURIComponent(pid) + '?delete_sessions=' + (deleteSessions ? 'true' : 'false'), { method: 'DELETE' });
        if (!res.ok) throw new Error(await apiErrorMessage(res, '删除项目失败'));
        const data = await res.json();
        await refreshSessions();
        updateEmpty();
        broadcast('sidebar', 'projects.updated', { project_id: pid });
        broadcastSessions('conversation.updated', { session_id: groupState.activeSessionId });
        return data;
      }
      // 会话归入/移出项目（空 project_id = 移回未分类）；不改写会话系统提示
      case 'session.moveToProject': {
        const sid = String(payload.session_id || '');
        const pid = String(payload.project_id || '');
        if (!sid) throw new Error('缺少 session_id');
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid) + '/project', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: pid }),
        });
        if (!res.ok) throw new Error(await apiErrorMessage(res, '移动会话失败'));
        const data = await res.json();
        await refreshSessions();
        broadcast('sidebar', 'projects.updated', { project_id: pid });
        broadcastSessions('conversation.updated', { session_id: groupState.activeSessionId });
        return data;
      }
      // 待审批队列：对齐后端 GET /api/requests（主进程会在轮询时顺带 kick skill/sensor 免审测试）
      case 'requests.list': {
        const list = await (await fetch('/api/requests')).json();
        return Array.isArray(list) ? list : [];
      }
      // 审批裁决：对齐后端 POST /api/requests/{id}/resolve
      case 'requests.resolve': {
        const rid = String(payload.request_id || '');
        if (!rid) throw new Error('缺少 request_id');
        const res = await fetch('/api/requests/' + encodeURIComponent(rid) + '/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            approved: !!payload.approved,
            feedback: String(payload.feedback || ''),
            ignore: !!payload.ignore,
            duration: Number(payload.duration || 5),
          }),
        });
        if (!res.ok) throw new Error((await res.text()) || '裁决失败');
        const data = await res.json();
        broadcastAll('requests.updated', { request_id: rid });
        return data;
      }
      case 'chat.interrupt':
        return (await fetch('/api/chat/interrupt', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })).json();
      // 会话分支：基于当前会话新建分支并切换过去（对齐后端 POST /api/sessions/{id}/branch）
      case 'session.branch': {
        // Agent 忙碌时禁止拉取分支（原 UI 同样拦截），避免新分支会话与进行中任务相互干扰
        if (await activeSessionBusy()) return { status: 'busy' };
        const sid = String(payload.session_id || groupState.activeSessionId || '');
        if (!sid) throw new Error('缺少 session_id');
        const res = await fetch('/api/sessions/' + encodeURIComponent(sid) + '/branch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ alias: String(payload.alias || '') }),
        });
        if (!res.ok) throw new Error((await res.text()) || '分支失败');
        const data = await res.json();
        if (data && data.id) {
          groupState.activeSessionId = data.id;
          await refreshSessions();
          updateEmpty();
          broadcastSessions('session.switched', { session_id: data.id });
        }
        return data;
      }
      // trace2skill：分配技能工厂并向当前会话注入 evolve_factory 事件（对齐原 UI confirmTraceToSkill）
      case 'chat.traceToSkill': {
        const sid = String(payload.session_id || groupState.activeSessionId || '');
        if (!sid) throw new Error('缺少 session_id');
        const name = String(payload.name || '').trim();
        const goal = String(payload.goal || '').trim();
        if (!name) throw new Error('技能名称不能为空');
        if (!goal) throw new Error('期望描述不能为空');
        const initRes = await fetch('/api/evolve/init', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'skill', name, is_upgrade: !!payload.is_upgrade, goal, trace: true, session_id: sid }),
        });
        if (!initRes.ok) throw new Error((await initRes.text()) || '工厂分配失败');
        const initData = await initRes.json();
        const factoryPath = '/agent_vm/skill_workplace/' + initData.workplace_id + '/' + name;
        const content = '用户触发了技能工厂，已为你分配了技能工厂' + factoryPath + '/，请根据用户需要和本次会话的交互记录与历史经验升级或创建对应技能。以下是用户期望：\n' + goal;
        const batchRes = await fetch('/api/chat/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid, events: [{ type: 'evolve_factory', content }] }),
        });
        if (!batchRes.ok) throw new Error((await batchRes.text()) || '任务下发失败');
        setEmpty(false);
        broadcastSessions('conversation.updated', { session_id: sid });
        return { status: 'ok' };
      }
      // ---- 浮层原语：宿主只认"调用方所属实例"，做通用移动/关闭（不感知具体插件；many 槽各实例独立） ----
      case 'slot.move': {
        const el = origin && origin.inst;
        if (!el) throw new Error('缺少调用方实例');
        if (payload.dx || payload.dy) {
          const r = el.getBoundingClientRect();
          const w = el.offsetWidth, h = el.offsetHeight;
          el.style.right = 'auto';
          el.style.left = Math.max(0, Math.min(HOST.innerWidth - w, r.left + (Number(payload.dx) || 0))) + 'px';
          el.style.top = Math.max(0, Math.min(HOST.innerHeight - h, r.top + (Number(payload.dy) || 0))) + 'px';
        }
        return { status: 'ok' };
      }
      case 'slot.close': {
        const el = origin && origin.inst;
        if (el) el.style.display = 'none';   // 只隐藏调用方实例
        return { status: 'ok' };
      }
      // 插件请求「关闭并记住」：与白条开关共用同一状态源（webminConfig.rail.hidden），
      // 重启后保持关闭；白条图标同步置灰，点白条图标即可重新启用
      case 'slot.hide': {
        const pid = origin && origin.pluginId;
        if (!pid) throw new Error('缺少调用方插件');
        setPluginHidden(pid, true);
        buildRail();   // 固定区域已按区域合并图标，重建即可反映显隐
        return { status: 'ok' };
      }
      // ---- 配置 ----
      case 'config.get':
        return configByPlugin[payload.plugin_id] || {};
      case 'config.set': {
        const pid = payload.plugin_id;
        if (!pid) throw new Error('缺少 plugin_id');
        configByPlugin[pid] = Object.assign({}, configByPlugin[pid], payload.config || {});
        // 先实时下发到目标插件（透明度热加载），再持久化；写盘失败不阻断视觉更新
        applyConfigTo(pid);
        broadcast('settings', 'config.updated', { plugin_id: pid, config: configByPlugin[pid] });
        await saveConfig();
        return configByPlugin[pid];
      }
      case 'settings.meta':
        return { plugins: groupState.plugins, config: configByPlugin };
      case 'settings.open': {
        // 可直接指定标签页（如部署页），未指定则沿用上次打开的标签页
        const tab = String((payload && payload.tab) || '');
        if (tab && CONFIG_NAV.indexOf(tab) >= 0) setSettingsTab(tab);
        setSettingsOpen(true); return { status: 'ok' };
      }
      case 'settings.close':
        setSettingsOpen(false); return { status: 'ok' };
      // ---- 引用 ----
      case 'dialog.files': {
        const pc = HOST.purrcat;
        if (!pc || !pc.openDialog) throw new Error('本地文件选择仅在 Electron 内可用');
        return pc.openDialog({ directory: false, properties: ['openFile', 'multiSelections'] });
      }
      case 'dialog.folder': {
        const pc = HOST.purrcat;
        if (!pc || !pc.openDialog) throw new Error('本地文件夹选择仅在 Electron 内可用');
        return pc.openDialog({ directory: true, properties: ['openDirectory', 'multiSelections'] });
      }
      // 由插件用 <input type="file"> 选好 File 后，交给宿主解析真实绝对路径
      case 'dialog.resolveFiles': {
        if (!HOST.purrcat || !HOST.purrcat.getPathForFile) throw new Error('本地路径解析仅在 Electron 内可用');
        const files = Array.isArray(payload.files) ? payload.files : [];
        const paths = [];
        for (const f of files) {
          try { const p = HOST.purrcat.getPathForFile(f); if (p) paths.push(p); } catch (_) { /* 单个失败跳过 */ }
        }
        return { paths: paths };
      }
      case 'dialog.pickWallpaper': {
        const pc = HOST.purrcat;
        if (!pc || !pc.openDialog) throw new Error('本地壁纸选择仅在 Electron 内可用');
        const r = await pc.openDialog({ properties: ['openFile'], filters: [{ name: 'Walls', extensions: ['png','jpg','jpeg','gif','webp','bmp','mp4','webm','mov'] }] });
        const p = pickPath(r);
        if (!p) return null;
        const up = await (await fetch('/api/webmin/wallpaper', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: p }) })).json();
        return up;
      }
      case 'plugin.delete': {
        if (!payload.plugin_id) throw new Error('缺少 plugin_id');
        const res = await fetch(`/api/webmin/plugin/${encodeURIComponent(payload.plugin_id)}/delete`, { method: 'POST' });
        if (!res.ok) throw new Error((await res.text()) || '删除失败');
        await reloadManifest();
        return { status: 'ok' };
      }
      case 'plugin.activate': {
        const p = (groupState.plugins || []).find((x) => x.id === payload.plugin_id);
        if (!p) throw new Error('插件不存在');
        activateSlotPlugin(p);
        return { status: 'ok' };
      }
      case 'ref.graphs': {
        const graphs = await (await fetch('/api/graphs')).json();
        return (graphs || []).map((g: string | { name?: string }) => (typeof g === 'string' ? g : g.name));
      }
      // ---- 插件自带后端 RPC ----
      case 'plugin.rpc': {
        const pid = payload.plugin_id;
        if (!pid) throw new Error('缺少 plugin_id');
        const res = await fetch(`/api/webmin/plugin-rpc/${encodeURIComponent(pid)}/${encodeURIComponent(payload.handler || '')}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ payload: payload.payload || {}, timeout: payload.timeout }),
        });
        if (!res.ok) throw new Error((await res.text()) || '插件后端调用失败');
        return (await res.json()).result;
      }
      // ---- 内置浏览器（原生 WebContentsView，非 iframe）----
      // 插件 iframe 拿不到 window.purrcat（preload 只在主 frame 生效，未开
      // nodeIntegrationInSubFrames），因此由宿主把原生浏览器原语转发给 purrcat，
      // 并负责「插件 iframe 局部坐标 → 主窗口内容区坐标」的换算。
      case 'browser.available':
        return { available: !!(HOST.purrcat && HOST.purrcat.browserNewTab) };
      case 'browser.bounds': {
        const pc = HOST.purrcat;
        if (!pc || !pc.browserSetBounds) throw new Error('内置浏览器仅在 Electron 内可用');
        let ox = 0, oy = 0;
        const fr = origin && origin.iframe;
        if (fr && fr.getBoundingClientRect) { const r = fr.getBoundingClientRect(); ox = r.left; oy = r.top; }
        await pc.browserSetBounds(
          Math.round(ox + (Number(payload.x) || 0)),
          Math.round(oy + (Number(payload.y) || 0)),
          Math.round(Number(payload.w) || 1),
          Math.round(Number(payload.h) || 1),
          1,
        );
        return { status: 'ok' };
      }
      case 'browser.hide': {
        if (HOST.purrcat && HOST.purrcat.browserHide) await HOST.purrcat.browserHide();
        return { status: 'ok' };
      }
      case 'browser.newTab': {
        if (!HOST.purrcat || !HOST.purrcat.browserNewTab) throw new Error('内置浏览器仅在 Electron 内可用');
        return { tabId: await HOST.purrcat.browserNewTab(payload.url || '') };
      }
      case 'browser.closeTab': {
        if (HOST.purrcat && HOST.purrcat.browserCloseTab) await HOST.purrcat.browserCloseTab(payload.tabId, payload.nextTabId || undefined);
        return { status: 'ok' };
      }
      case 'browser.switchTab': {
        if (HOST.purrcat && HOST.purrcat.browserSwitchTab) await HOST.purrcat.browserSwitchTab(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.navigate': {
        if (HOST.purrcat && HOST.purrcat.browserNavigate) await HOST.purrcat.browserNavigate(payload.tabId, payload.url);
        return { status: 'ok' };
      }
      case 'browser.reload': {
        if (HOST.purrcat && HOST.purrcat.browserReload) await HOST.purrcat.browserReload(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.goBack': {
        if (HOST.purrcat && HOST.purrcat.browserGoBack) await HOST.purrcat.browserGoBack(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.goForward': {
        if (HOST.purrcat && HOST.purrcat.browserGoForward) await HOST.purrcat.browserGoForward(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.pickStart': {
        if (!HOST.purrcat || !HOST.purrcat.browserPickStart) throw new Error('内置浏览器仅在 Electron 内可用');
        return await HOST.purrcat.browserPickStart(payload.tabId);
      }
      case 'browser.pickEnd': {
        if (HOST.purrcat && HOST.purrcat.browserPickEnd) await HOST.purrcat.browserPickEnd(payload.tabId);
        return { status: 'ok' };
      }
      case 'browser.locate': {
        if (!HOST.purrcat || !HOST.purrcat.browserLocate) return null;
        return await HOST.purrcat.browserLocate(payload.tabId, payload.x, payload.y);
      }
      case 'browser.pickElement': {
        if (!HOST.purrcat || !HOST.purrcat.browserCdpPickElement) return null;
        return await HOST.purrcat.browserCdpPickElement(payload.tabId, payload.x, payload.y);
      }
      case 'browser.openExternal': {
        if (HOST.purrcat && HOST.purrcat.openExternal) await HOST.purrcat.openExternal(payload.url);
        return { status: 'ok' };
      }
      // 网页链接统一路由：主进程拦下的 target=_blank/window.open 与插件显式调用都走这里
      case 'browser.openUrl':
        return openUrlInBrowserPanel(payload.url);
      // 草稿态下选择 Agent Loop（范式）：仅记录在宿主，待首条消息建会话时生效。
      // 与 session.* 系列同属宿主对外契约，插件无需感知彼此即可热插拔。
      case 'session.setDraftParadigm': {
        if (!groupState.draft) return { status: 'noop' };
        groupState.draftParadigm = String(payload.paradigm || '');
        return { status: 'ok', paradigm: groupState.draftParadigm };
      }
      case 'state.get':
        return { ...groupState, plugins: undefined, activeBySlot: { ...activeBySlot } };
      // 子代理分支视图切换：会话插件据此切换查看分支（同时由分支状态进入/退出输入只读）
      case 'branch.select': {
        const bid = String(payload.branch_id || 'main');
        groupState.activeBranchId = bid;
        broadcastAll('branch.switched', { branch_id: bid });
        return { status: 'ok' };
      }
      default:
        return null;
    }
  }

