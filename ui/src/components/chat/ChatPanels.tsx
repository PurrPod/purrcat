// src/components/chat/ChatPanels.tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { History, Minus, CheckCircle, FileText, Undo2, Bell, X, Activity, ChevronDown, ChevronUp, TerminalSquare, Plus, ChevronRight, AlertTriangle, Rocket } from 'lucide-react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './ChatShared';
import { useTranslation } from '../../i18n';

export function FileChangesPanel(props: any) {
  const { t } = useTranslation();
  const { showFileView, setShowFileView, fileChanges, activeDiffPath, setActiveDiffPath, handleAck, handleRollback, handleAckAll } = props;
  if (!showFileView) return null;

  return (
    <div className="px-10 pb-6 pt-2 flex flex-col w-full shrink-0">
      <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-6 flex flex-col h-[55vh] min-h-[35vh] max-h-[85vh] resize-y overflow-hidden">
        <div className="flex items-center gap-3 mb-5 border-b-4 border-ink/20 pb-3 shrink-0">
          <History size={26} strokeWidth={2.5} className="text-[#d08770]" />
          <h2 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            {t('chat.fileChanges')} <span className="ml-2 text-sm opacity-60">({fileChanges.length} {t('chat.filesModified')})</span>
          </h2>
          {fileChanges.length > 0 && (
            <button onClick={handleAckAll} title={t('chat.ackAllCleanHint')} style={sketchyShape3} className="ml-auto px-3 py-1 bg-[#a3be8c] text-ink text-xs font-black border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-[1px] active:shadow-none transition-all flex items-center gap-1.5 -rotate-1">
              <CheckCircle size={14} strokeWidth={3} /> {t('chat.acknowledgeAll')}
            </button>
          )}
          <button onClick={() => setShowFileView(false)} className={`${fileChanges.length > 0 ? '' : 'ml-auto '}p-1.5 border-2 border-ink bg-cream hover:bg-[#d08770] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-[1px]`} style={sketchyShape2}><Minus size={20} strokeWidth={3} /></button>
        </div>

        {fileChanges.length === 0 ? (
          <div className="flex flex-col items-center py-10 opacity-50"><CheckCircle size={48} strokeWidth={1.5} /><p className="font-bold text-sm mt-2">{t('chat.allFilesClean')}</p></div>
        ) : (
          <div className="flex flex-col md:flex-row gap-6 flex-1 min-h-0 items-stretch">
            <div className="w-full md:w-72 shrink-0 overflow-y-auto flex flex-col gap-3 pr-2">
              {fileChanges.map((change: any, idx: number) => {
                const isSelected = activeDiffPath === change.path;
                const changeType = change.change_type || 'modified';
                let badge = null;
                let titleStyle = "font-black text-xs truncate flex-1 transition-all";
                if (changeType === 'deleted') { badge = <span className="absolute -top-2 -left-2 bg-[#bf616a] text-paper px-1.5 py-0.5 text-[9px] font-black border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] z-10" style={sketchyShape1}>{t('chat.deletedLabel')}</span>; titleStyle += " line-through opacity-60 decoration-2"; }
                else if (changeType === 'created') { badge = <span className="absolute -top-2 -left-2 bg-[#a3be8c] text-ink px-1.5 py-0.5 text-[9px] font-black border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] z-10" style={sketchyShape1}>{t('chat.newLabel')}</span>; }

                return (
                  <div key={change.id} onClick={() => setActiveDiffPath(change.path)} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`p-3 border-2 border-ink transition-all cursor-pointer flex flex-col gap-1 relative select-none ${idx % 2 === 0 ? 'rotate-0.5' : '-rotate-0.5'} ${isSelected ? 'bg-[#88c0d0] text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-0.5' : 'bg-cream text-ink hover:bg-sand shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-[1px]'}`}>
                    {badge}
                    <div className="flex items-center gap-2 w-full"><FileText size={14} className={isSelected ? 'text-paper' : 'text-[#88c0d0]'} strokeWidth={3} /><span className={titleStyle}>{change.path.split('/').pop()}</span></div>
                    <span className={`text-[9px] font-bold ${isSelected ? 'text-paper/70' : 'text-ink/40'} truncate`} title={change.path}>{change.path}</span>
                  </div>
                );
              })}
            </div>
            <div className="flex-1 flex flex-col min-w-0">
              {(() => {
                const currentChange = fileChanges.find((c:any) => c.path === activeDiffPath);
                if (!currentChange) return <div className="flex-1 flex items-center justify-center italic opacity-40 text-sm">{t('chat.selectFile')}</div>;
                return (
                  <div className="flex-1 flex flex-col min-h-0">
                    <div className="flex-1 bg-[#FDF8F0] p-4 border-4 border-ink font-mono text-xs overflow-auto shadow-[inset_3px_3px_6px_rgba(0,0,0,0.05)]" style={sketchyShape2}>
                      {currentChange.diff ? currentChange.diff.split('\n').map((line: string, i: number) => {
                        let colorClass = 'text-ink/70';
                        if (line.startsWith('+')) colorClass = 'text-[#a3be8c] font-bold bg-[#a3be8c]/10';
                        if (line.startsWith('-')) colorClass = 'text-[#bf616a] font-bold bg-[#bf616a]/10';
                        if (line.startsWith('@')) colorClass = 'text-[#88c0d0]';
                        return <div key={i} className={`${colorClass} leading-relaxed whitespace-pre rounded px-1`}>{line || '\u00A0'}</div>;
                      }) : <span className="opacity-50 italic p-2 block">{t('chat.noVisualDiff')}</span>}
                    </div>
                    <div className="flex gap-4 mt-3 shrink-0">
                      <button onClick={() => handleAck(currentChange.path, currentChange.newest_backup_id)} className="flex-1 bg-[#a3be8c] text-ink font-black py-2.5 border-2 border-ink shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-0.5 active:shadow-none transition-all flex justify-center items-center gap-2" style={sketchyShape2}><CheckCircle size={16} strokeWidth={3}/> {t('chat.acknowledge')}</button>
                      <button onClick={() => handleRollback(currentChange.path, currentChange.oldest_backup_id)} className="flex-1 bg-[#bf616a] text-paper font-black py-2.5 border-2 border-ink shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-0.5 active:shadow-none transition-all flex justify-center items-center gap-2" style={sketchyShape3}><Undo2 size={16} strokeWidth={3}/> {t('chat.revert')}</button>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function RequestQueuePanel(props: any) {
  const { t } = useTranslation();
  const { showReqQueue, setShowReqQueue, pendingReqs, handleResolveReq, feedbackInputs, setFeedbackInputs, authDurations, setAuthDurations, expandedReasons, setExpandedReasons, onGoDeploy } = props;
  if (!showReqQueue) return null;

  return (
    <div style={sketchyShape3} className="w-[340px] shrink-0 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-20">
      <div className="flex flex-col shrink-0 p-4 bg-paper">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2"><Bell size={24} strokeWidth={2.5} className="text-[#EBCB8B]" /><h3 className="text-2xl font-black tracking-widest text-ink">{t('chat.pending')}</h3></div>
          <button onClick={() => setShowReqQueue(false)} className="hover:text-terracotta hover:rotate-90 transition-all p-1 bg-paper border-2 border-ink" style={sketchyShape1}><X size={20} strokeWidth={3} /></button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4 bg-paper">
        {pendingReqs.length === 0 ? (
          <div className="flex flex-col items-center opacity-50 mt-10"><Activity size={48} strokeWidth={1.5} /><p className="font-bold text-sm mt-2">{t('chat.noRequests')}</p></div>
        ) : (
          pendingReqs.map((req: any, idx: number) => {
            const isDepCheck = req.type === 'dependency_check';
            return (
              <div key={req.id} className={`bg-paper border-4 border-ink p-4 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-3 relative transition-all group ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'} ${isDepCheck ? 'border-[#d08770]' : ''}`} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}>
                <button onClick={() => handleResolveReq(req.id, false, true)} className="opacity-0 group-hover:opacity-100 p-1.5 bg-ink text-paper border-2 border-ink hover:scale-110 transition-all absolute -top-2 -right-2 z-10" style={sketchyShape2} title={t('chat.ignoreSilent')}><X size={12} strokeWidth={3} /></button>
                <div className="flex justify-between items-start">
                  {isDepCheck ? (
                    <span className="font-black text-xs uppercase px-2 py-0.5 bg-[#d08770] text-paper border-2 border-ink flex items-center gap-1" style={sketchyShape1}><AlertTriangle size={11} strokeWidth={3} />{t('chat.dependency')}</span>
                  ) : (
                    <span className="font-black text-xs uppercase px-2 py-0.5 bg-[#EBCB8B] border-2 border-ink" style={sketchyShape1}>{req.type}</span>
                  )}
                </div>
                <div>
                  <div className="text-[15px] font-black text-ink break-all leading-tight">{req.target}</div>
                  <button onClick={() => setExpandedReasons({...expandedReasons, [req.id]: !expandedReasons[req.id]})} className="text-xs font-bold text-ink/50 mt-2 flex items-center gap-1 hover:text-ink transition-colors">{expandedReasons[req.id] ? <ChevronUp size={12} /> : <ChevronDown size={12} />} {t('chat.reason')}</button>
                  {expandedReasons[req.id] && <div className="text-xs font-bold text-ink/70 bg-ink/5 p-2 mt-1 leading-relaxed whitespace-pre-wrap">{req.reason}</div>}
                </div>
                {req.type === 'computer_use' && (
                  <div className="flex items-center justify-between mt-1 mb-1 p-2 border-2 border-ink bg-[#88c0d0]/20" style={sketchyShape3}><span className="text-xs font-black text-ink uppercase">⏳ {t('chat.timeLimit')}</span><select value={authDurations[req.id] || 10} onChange={e => setAuthDurations({...authDurations, [req.id]: parseInt(e.target.value)})} className="bg-cream border-2 border-ink text-xs p-1 font-bold" style={sketchyShape2}><option value={10}>10 {t('chat.mins')}</option><option value={30}>30 {t('chat.mins')}</option><option value={-1}>{t('chat.todayUnlimited')}</option></select></div>
                )}
                {/* dependency_check 不需要 feedback 输入 */}
                {!isDepCheck && (
                  <input value={feedbackInputs[req.id] || ''} onChange={e => setFeedbackInputs({...feedbackInputs, [req.id]: e.target.value})} placeholder={t('chat.feedbackOptional')} className="w-full text-xs font-bold p-2 border-2 border-ink focus:outline-none bg-[#FDF8F0] shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" style={sketchyShape2} />
                )}
                {isDepCheck ? (
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => { if (onGoDeploy) onGoDeploy(); handleResolveReq(req.id, true, false); }} className="flex-1 bg-[#EBCB8B] text-ink font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#d8b877] active:translate-y-1 active:shadow-none transition-all flex justify-center items-center gap-1.5" style={sketchyShape1}><Rocket size={12} strokeWidth={3} />{t('chat.goToDeploy')}</button>
                    <button onClick={() => handleResolveReq(req.id, false, false)} className="flex-1 bg-cream text-ink font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-sand active:translate-y-1 active:shadow-none transition-all" style={sketchyShape2}>{t('chat.gotIt')}</button>
                  </div>
                ) : (
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => handleResolveReq(req.id, true, false, authDurations[req.id] || 10)} className="flex-1 bg-[#a3be8c] text-ink font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all flex justify-center items-center" style={sketchyShape1}>{t('chat.approve')}</button>
                    <button onClick={() => handleResolveReq(req.id, false, false, authDurations[req.id] || 10)} className="flex-1 bg-[#bf616a] text-paper font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-1 active:shadow-none transition-all" style={sketchyShape2}>{t('chat.reject')}</button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// =============================================
// 终端面板 (xterm.js + WebSocket)
// — 支持：多 Tab / 折叠不杀进程 / 自动 CRLF 归一化
// =============================================

type TabState = {
  id: string;
  label: string;
  command: string | null; // null = 交互 shell
  isCollapsed: boolean;   // 折叠时保持 DOM + 连接
  terminalEl: HTMLDivElement | null;
  terminal: Terminal | null;
  fitAddon: FitAddon | null;
  ws: WebSocket | null;
  resizeObs: ResizeObserver | null;
};

export function TerminalPanel(props: any) {
  const { showTerminal, setShowTerminal, command: commandProp } = props;
  const { t } = useTranslation();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const tabCounterRef = useRef(1);

  // Tab 列表 + 当前激活 tab
  const [tabs, setTabs] = useState<TabState[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // 每次折叠/展开都要重 fit 一下
  const fitById = useCallback((id: string) => {
    setTabs(prev => prev.map(tb => {
      if (tb.id !== id || !tb.fitAddon) return tb;
      try { tb.fitAddon.fit(); } catch { /* noop */ }
      return tb;
    }));
  }, []);

  // 新建一个 tab
  const createTab = useCallback((cmd: string | null) => {
    const id = `tab-${tabCounterRef.current++}-${Date.now()}`;
    // 标签名统一用普通 Shell 命名（不拿命令本身当标签，与正常打开的终端一致）
    const label = `· Shell ${tabCounterRef.current - 1}`;

    // 先创建容器 DOM
    const container = document.createElement('div');
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.overflow = 'hidden';
    container.style.background = '#1e1e2e';
    container.style.display = 'none'; // 非激活默认隐藏（保持 DOM 不销毁）

    // 初始化 xterm — PTY 模式下不需要 convertEol，PTY 会输出正确的 CRLF
    const term = new Terminal({
      theme: { background: '#1e1e2e', foreground: '#cdd6f4', cursor: '#f5e0dc', selectionBackground: '#585b70' },
      cursorBlink: true,
      scrollback: 5000,
      fontSize: 14,
      fontFamily: '"Cascadia Code", "Fira Code", "JetBrains Mono", Consolas, monospace',
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(container);

    // WebSocket — 始终开交互 shell。命令不走 ?cmd=（后端 -Command 静默执行，
    // 命令本身和运行位置都不回显），改为 shell 就绪后以键盘输入注入：
    // 提示符（含运行位置）+ 命令回显都像手动敲入一样自然，还避开 -Command 的引号转义问题
    const wsUrl = `ws://${window.location.host}/api/terminal/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      // 连接建立后立即发送一次当前尺寸
      try {
        const sendResize = (t: Terminal, w: WebSocket) => {
          const resizeMsg = '\x00' + JSON.stringify({ type: 'resize', cols: t.cols, rows: t.rows });
          if (w.readyState === WebSocket.OPEN) w.send(resizeMsg);
        };
        sendResize(term, ws);
      } catch { /* noop */ }
      try { fitAddon.fit(); } catch { /* noop */ }
    };

    let cmdInjected = cmd == null; // 无命令的 tab 天然视为已注入
    ws.onmessage = (event) => {
      // PTY 已经输出正确的 CRLF，前端直接 write 即可
      term.write(event.data);
      if (!cmdInjected) {
        cmdInjected = true;
        // 收到第一段输出 = shell 已就绪（提示符已出），此时把命令当键盘输入注入才会被回显；
        // 更早发会在 shell 完成初始化前丢失。'\r' 即 xterm 里按下 Enter 的原始字节
        if (cmd && ws.readyState === WebSocket.OPEN) ws.send(cmd + '\r');
      }
    };

    ws.onerror = () => {
      term.writeln(`\r\n\x1b[31m[WebSocket Error] Failed to connect to terminal.\x1b[0m`);
    };

    ws.onclose = () => {
      term.writeln(`\r\n\x1b[33m[Disconnected]\x1b[0m`);
    };

    // 用户输入 → 发给后端 PTY 的 stdin
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data);
    });

    // 终端尺寸变化 → 发 resize 控制消息给后端 (\x00 前缀标识控制消息)
    term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('\x00' + JSON.stringify({ type: 'resize', cols, rows }));
      }
    });

    const resizeObs = new ResizeObserver(() => {
      try { fitAddon.fit(); } catch { /* noop */ }
    });
    resizeObs.observe(container);

    const newTab: TabState = {
      id,
      label,
      command: cmd,
      isCollapsed: false,
      terminalEl: container,
      terminal: term,
      fitAddon,
      ws,
      resizeObs,
    };

    setTabs(prev => {
      const next = [...prev, newTab];
      // 首次创建时下一帧 fit
      requestAnimationFrame(() => {
        try { fitAddon.fit(); } catch { /* noop */ }
      });
      return next;
    });
    setActiveId(id);
    return id;
  }, []);

  // 关闭 tab（真正销毁进程 + DOM）
  const closeTab = useCallback((id: string) => {
    setTabs(prev => {
      const tab = prev.find(t => t.id === id);
      if (tab) {
        tab.resizeObs?.disconnect();
        tab.ws?.close();
        tab.terminal?.dispose();
        tab.terminalEl?.remove();
      }
      const next = prev.filter(t => t.id !== id);
      setActiveId(currId => {
        if (currId !== id) return currId;
        return next[next.length - 1]?.id ?? null;
      });
      return next;
    });
  }, []);

  // 激活 tab（把它的 terminalEl 挂载到 wrapper 里）
  // 依赖 showTerminal：最小化→展开时 wrapperRef 是新 DOM，必须重新挂载 + refresh
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    // 清空旧内容
    wrapper.innerHTML = '';
    const tab = tabs.find(t => t.id === activeId);
    if (tab && tab.terminalEl) {
      tab.terminalEl.style.display = 'block';
      wrapper.appendChild(tab.terminalEl);
      try { tab.fitAddon?.fit(); } catch { /* noop */ }
      // 强制重绘所有可见行 — 解决 display:none → block 后 canvas 空白
      try { tab.terminal?.refresh(0, (tab.terminal?.rows ?? 1) - 1); } catch { /* noop */ }
    }
    // 其他 tab 隐藏但保留 DOM
    tabs.forEach(t => {
      if (t.id !== activeId && t.terminalEl) {
        t.terminalEl.style.display = 'none';
      }
    });
  }, [activeId, tabs, showTerminal]);

  // tabs 的 ref 镜像：卸载清理 effect 的闭包捕获的是初始空 tabs（stale closure），走 ref 才能真正关掉连接
  const tabsRef = useRef<TabState[]>([]);
  useEffect(() => { tabsRef.current = tabs; }, [tabs]);

  // 组件卸载时清理所有 tabs
  useEffect(() => {
    return () => {
      tabsRef.current.forEach(t => {
        t.resizeObs?.disconnect();
        t.ws?.close();
        t.terminal?.dispose();
        t.terminalEl?.remove();
      });
    };
  }, []);

  // 🌟 面板打开 / 新命令（term:// 点击 RUN）统一在这里建 tab。
  // 原来拆成两个 effect：RUN 点击时 showTerminal 与 commandProp 在同一次渲染里变化，
  // 两个 effect 都触发（后者读到的 tabs 还是未提交的旧值 []），导致一次开两个终端；合并后天然只开一个。
  // commandProp 是 { seq, cmd } 事件对象：seq 变化才算新的一次 RUN（同一条命令重复点也算新）——
  // 只比字符串的话，重复 RUN 同一条命令会被判重跳过 → 卡住没反应
  const lastSeqRef = useRef<number>(-1);
  useEffect(() => {
    const evt: { seq: number; cmd: string } | null = commandProp ?? null;
    const isNewCmd = !!evt && evt.seq !== lastSeqRef.current;
    if (evt) lastSeqRef.current = evt.seq;
    if (!showTerminal) return;
    if (tabs.length === 0) {
      // 面板打开但还没有任何 tab：建一个；恰好有新命令就直接在这个 tab 里执行
      createTab(isNewCmd && evt ? evt.cmd : null);
      return;
    }
    // 已有 tab 时来了新命令（term:// RUN）：新开一个 tab 执行
    if (isNewCmd && evt) createTab(evt.cmd);
  }, [showTerminal, tabs.length, commandProp, createTab]);

  // 外层未挂载时不渲染
  if (!showTerminal) return null;

  const activeTab = tabs.find(t => t.id === activeId);

  return (
    <div className="px-10 pb-6 pt-2 flex flex-col w-full shrink-0">
      <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-4 flex flex-col h-[55vh] min-h-[35vh] max-h-[85vh] resize-y overflow-hidden">
        {/* 头部 */}
        <div className="flex items-center gap-3 mb-3 border-b-4 border-ink/20 pb-3 shrink-0">
          <TerminalSquare size={26} strokeWidth={2.5} className="text-[#88c0d0]" />
          <h2 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            TERMINAL
          </h2>

          {/* —— Tab 栏 —— */}
          <div className="flex items-center gap-1 ml-4 flex-1 overflow-x-auto">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => {
                  if (tab.isCollapsed) {
                    // 重新展开：切换激活后，display=block 会在下一个 effect 里处理
                    setTabs(prev => prev.map(tb => tb.id === tab.id ? { ...tb, isCollapsed: false } : tb));
                  }
                  setActiveId(tab.id);
                  fitById(tab.id);
                }}
                className={`group flex items-center gap-2 px-3 py-1.5 border-2 border-ink text-sm font-bold whitespace-nowrap select-none transition-all ${activeId === tab.id
                  ? 'bg-[#88c0d0] text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] -translate-y-[1px]'
                  : 'bg-cream text-ink hover:bg-sand shadow-[2px_2px_0px_0px_rgba(26,26,26,0.4)]'
                }`}
                style={activeId === tab.id ? sketchyShape1 : sketchyShape3}
              >
                {tab.isCollapsed && <ChevronRight size={12} strokeWidth={3} className="opacity-70" />}
                <span className="max-w-[120px] truncate">{tab.label}</span>
                {/* Tab 上的关闭 X：关掉就真杀进程 */}
                <span
                  role="button"
                  onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
                  className="ml-1 opacity-50 hover:opacity-100 hover:bg-[#bf616a] hover:text-paper rounded transition-colors p-0.5"
                >
                  <X size={12} strokeWidth={3} />
                </span>
              </button>
            ))}
            {/* 新增 Tab 按钮 */}
            <button
              onClick={() => createTab(null)}
              className="ml-1 p-1.5 border-2 border-ink bg-cream hover:bg-[#a3be8c] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all"
              style={sketchyShape2}
              title={t('chat.newTerminal')}
            >
              <Plus size={14} strokeWidth={3} />
            </button>
          </div>

          {/* 折叠按钮：只改 isCollapsed，不销毁 tab */}
          <button
            onClick={() => {
              setShowTerminal(false);
              if (activeTab) {
                setTabs(prev => prev.map(tb => tb.id === activeTab.id ? { ...tb, isCollapsed: true } : tb));
              }
            }}
            className="ml-auto p-1.5 border-2 border-ink bg-cream hover:bg-[#d08770] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-[1px]"
            style={sketchyShape2}
            title={t('chat.minimizeKeepRunning')}
          >
            <Minus size={20} strokeWidth={3} />
          </button>
        </div>

        {/* 终端主体 */}
        <div
          ref={wrapperRef}
          className="flex-1 min-h-0 border-4 border-ink bg-[#1e1e2e] p-2 overflow-hidden"
          style={sketchyShape2}
        />
      </div>
    </div>
  );
}
