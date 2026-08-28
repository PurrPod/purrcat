// src/components/ChatPage.tsx
import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, Cat, Clock, Activity, Server, Zap, Brain, GitMerge, Loader2, FolderOpen, Bell, Paperclip, X, Heart, List, ExternalLink, Plus, BookOpen, ClipboardCopy, TerminalSquare, AlertTriangle, Globe, Pause } from 'lucide-react';
import { toast } from 'react-hot-toast';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';

// 🌟 允许本地文件路径和 file:// 协议通过（用于预览），其余走默认安全过滤
// react-markdown v9 默认会把自定义协议（含 file:// 和 D:/ 盘符）过滤成空字符串
const allowFileUrlTransform = (url: string) => {
  // 1. file:// 协议
  if (url.startsWith('file://')) return url;
  // 1.5 term:// 协议 (Agent 建议执行的终端命令)
  if (url.startsWith('term://')) return url;
  // 2. Agent 沙盒路径
  if (url.startsWith('/agent_vm/') || url === '/agent_vm' ||
      url.startsWith('./agent_vm/') || url === './agent_vm') return url;
  // 3. Windows 绝对路径 (盘符+冒号+斜杠)
  if (/^[A-Za-z]:[/\\]/.test(url)) return url;
  // 4. 带文件扩展名的相对路径 (./xxx or ../xxx)
  if (url.startsWith('./') || url.startsWith('../')) {
    const ext = url.split('.').pop()?.toLowerCase() || '';
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'mp4', 'webm', 'mov', 'ogg',
         'pdf', 'txt', 'md', 'csv', 'json', 'log', 'html'].includes(ext)) return url;
  }
  return defaultUrlTransform(url);
};

import { Message, Session } from './chat/ChatTypes';
import { parseEventsContent, hasMessageInHistory, renderSketchyHeatmap, MarkdownComponents, safeDecodeUri, ToolCallBubble, ToolMessageBubble, sketchyShape1, sketchyShape2, sketchyShape3 } from './chat/ChatShared';
import ChatModals from './chat/ChatModals';
import ChatSidebar from './chat/ChatSidebar';
import { FileChangesPanel, RequestQueuePanel, TerminalPanel } from './chat/ChatPanels';
import AgentBrowserPanel from './chat/AgentBrowserPanel';
import IDEPanel from './chat/IDEPanel';
import ConfigModal from './ConfigModal';

// 🌟 多标签页类型定义
export type BrowserTab = { id: string; url: string; title: string };

export default function ChatPage({ onBack, onSwitchToTask }: { onBack: () => void; onSwitchToTask?: () => void }) {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();

  const [input, setInput] = useState('');
  // 🌟 IDE 引用插入：IDEPanel（含独立窗口）通过 BroadcastChannel 广播 Ctrl+U 提取的「路径+行号」引用
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    let bc: BroadcastChannel | null = null;
    try { bc = new BroadcastChannel('purrcat-ide'); } catch { return; }
    bc.onmessage = (e) => {
      const text = e.data?.type === 'insert-input' ? String(e.data.text || '') : '';
      if (!text) return;
      const ta = chatInputRef.current;
      if (ta) {
        const start = ta.selectionStart ?? ta.value.length;
        const end = ta.selectionEnd ?? ta.value.length;
        const before = ta.value.slice(0, start);
        const after = ta.value.slice(end);
        const pad = before && !/\s$/.test(before) ? ' ' : '';
        setInput(before + pad + text + after);
        requestAnimationFrame(() => {
          const pos = (before + pad + text).length;
          ta.focus();
          ta.selectionStart = ta.selectionEnd = pos;
        });
      } else {
        setInput(prev => (prev && !/\s$/.test(prev) ? prev + ' ' : prev) + text);
      }
    };
    return () => { try { bc?.close(); } catch { /* noop */ } };
  }, []);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId || null);
  
  const [currentBranchId, setCurrentBranchId] = useState<string>('main');
  const [branches, setBranches] = useState<Record<string, any>>({ main: {} });

  const [showSessionModal, setShowSessionModal] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [newAlias, setNewAlias] = useState('');
  const [selectedProject, setSelectedProject] = useState('');
  const [infoData, setInfoData] = useState<{skills: string[], workshops: string[]}>({skills: [], workshops: []});
  const [showBranchModal, setShowBranchModal] = useState(false);
  const [branchAlias, setBranchAlias] = useState('');
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const [branchToDelete, setBranchToDelete] = useState<string | null>(null);

  const [showBusyModal, setShowBusyModal] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingAlias, setEditingAlias] = useState('');
  // 🌟 切换会话拦截：存在未接受文件更改时暂存目标会话，弹确认框
  const [pendingSwitchId, setPendingSwitchId] = useState<string | null>(null);

  const [globalStats, setGlobalStats] = useState<any>(null);
  const [tokenData, setTokenData] = useState({ window: 0, max: 1000000, cached: 0 });
  const [useBrainstorm, setUseBrainstorm] = useState(false);

  const [showReqQueue, setShowReqQueue] = useState(false);
  const [pendingReqs, setPendingReqs] = useState<any[]>([]);
  const [feedbackInputs, setFeedbackInputs] = useState<Record<string, string>>({});
  const [authDurations, setAuthDurations] = useState<Record<string, number>>({}); 
  const prevPendingIds = useRef<string[]>([]);
  const [expandedReasons, setExpandedReasons] = useState<Record<string, boolean>>({});

  const [showFileView, setShowFileView] = useState(false);
  const [fileChanges, setFileChanges] = useState<any[]>([]);
  const [activeDiffPath, setActiveDiffPath] = useState<string | null>(null);

  // 终端面板状态
  const [showTerminal, setShowTerminal] = useState(false);
  const [terminalCmd, setTerminalCmd] = useState<string | null>(null); // null = 默认交互 shell
  const [pendingTermCmd, setPendingTermCmd] = useState<string | null>(null); // 确认弹窗中的待执行命令

  const [sidebarMode, setSidebarMode] = useState<'menu' | 'mcp' | 'skill' | 'cron' | 'sensor'>('menu');
  // 🌟 响应式：窗口宽度小于屏幕宽度一半时收起左侧菜单
  const [isCompact, setIsCompact] = useState(false);
  const [sensorData, setSensorData] = useState<any>({});
  const [mcpData, setMcpData] = useState<Record<string, any[]>>({});
  const [expandedMcp, setExpandedMcp] = useState<string | null>(null);
  const [isRefreshingMcp, setIsRefreshingMcp] = useState(false);

  const [skillData, setSkillData] = useState<any[]>([]);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [isRefreshingSkill, setIsRefreshingSkill] = useState(false);
  const [isReloadingSensors, setIsReloadingSensors] = useState(false);
  
  const [showInstallSkillModal, setShowInstallSkillModal] = useState(false);
  const [skillInstallUrl, setSkillInstallUrl] = useState('');
  const [isInstallingSkill, setIsInstallingSkill] = useState(false);
  
  const [cronData, setCronData] = useState<any[]>([]);
  const [showAddCronModal, setShowAddCronModal] = useState(false);
  const [newCron, setNewCron] = useState({ title: '', trigger_time: '', repeat_rule: 'none', task_hook: 'Agent', task_inputs_str: '{\n}' });

  const [showTraceModal, setShowTraceModal] = useState(false);
  const [traceType, setTraceType] = useState<'create' | 'upgrade'>('upgrade');
  const [traceSkillName, setTraceSkillName] = useState('');
  const [traceExpectation, setTraceExpectation] = useState('');
  const [isTracing, setIsTracing] = useState(false);

  // 🌟 心跳控制状态
  const [showHeartbeatModal, setShowHeartbeatModal] = useState(false);
  const [heartbeatConfig, setHeartbeatConfig] = useState({ interval: 1800, active: false, goal: '' });

  // --- 新增：内置浏览器状态（多标签页） ---
  const [showBrowser, setShowBrowser] = useState(false);
  const [browserDetached, setBrowserDetached] = useState(false);
  const [browserMode, setBrowserMode] = useState<'browse' | 'pick' | 'draw'>('browse');
  const [browserTabs, setBrowserTabs] = useState<BrowserTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  // 🌟 新增：IDE 状态
  const [showIDE, setShowIDE] = useState(false);
  const [ideWorkspace, setIdeWorkspace] = useState<string | null>(null);

  // 🌟 挂载时拉取现有的心跳配置
  const fetchAgentHeartbeat = async () => {
    try {
      const res = await fetch('/api/tools/heartbeat');
      if (res.ok) {
        const data = await res.json();
        setHeartbeatConfig({ interval: data.interval || 1800, active: !!data.active, goal: data.goal || '' });
      }
    } catch { /* noop */ }
  };
  useEffect(() => { fetchAgentHeartbeat(); }, []);

  // 🌟 响应式：监听窗口宽度，小于屏幕一半时收起左侧菜单
  useEffect(() => {
    const check = () => setIsCompact(window.innerWidth < window.screen.width / 2);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  // 🌟 挂载时拉取 info.json (skills & workshops)
  useEffect(() => {
    const fetchInfoData = async () => {
      try {
        const res = await fetch('/api/config/info');
        if (res.ok) setInfoData(await res.json());
      } catch { /* noop */ }
    };
    fetchInfoData();
  }, []);

  // 🌟 保存心跳配置（开启时必须提交非空 GOAL.md 内容）
  const saveHeartbeat = async () => {
    if (heartbeatConfig.active && !heartbeatConfig.goal.trim()) {
      toast.error("GOAL.md 内容为空，无法开启心跳！");
      return;
    }
    if (heartbeatConfig.interval < 60) {
      toast.error("心跳间隔最短为 60 秒！");
      return;
    }
    try {
      const res = await fetch('/api/tools/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interval: heartbeatConfig.interval,
          active: heartbeatConfig.active,
          goal: heartbeatConfig.goal
        })
      });
      if (res.ok) {
        toast.success("Agent 潜意识心跳已更新！");
        setShowHeartbeatModal(false);
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "心跳更新失败");
      }
    } catch { toast.error("心跳更新失败"); }
  };

  const [showMdModal, setShowMdModal] = useState(false);
  const [showToolMenu, setShowToolMenu] = useState(false);
  const [mdType, setMdType] = useState<'SOUL' | 'GOAL'>('SOUL');
  const [mdContent, setMdContent] = useState('');
  const [isSavingMd, setIsSavingMd] = useState(false);

  // 🌟 链接预览状态：type 决定弹窗用 img/video/iframe/markdown 渲染
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'video' | 'browser' | 'markdown'>('browser');
  const [previewRawUrl, setPreviewRawUrl] = useState<string>('');
  // Markdown 富文本预览：拉取原文后用 ReactMarkdown 渲染（null = 加载中）
  const [previewMdContent, setPreviewMdContent] = useState<string | null>(null);
  // md 文件所在目录（正斜杠形式），用于解析 md 内相对路径的图片/资源
  const [previewMdBaseDir, setPreviewMdBaseDir] = useState('');

  // 🌟 统一的链接路由核心：气泡内链接、md 预览弹窗内链接共用
  const handleRawLinkClick = (rawHref: string) => {
    // 🌟 term:// 协议：Agent 建议执行的终端命令，先弹确认框
    if (rawHref.startsWith('term://')) {
      // Markdown URL 不允许空格，Agent 会用 %20 编码；这里解码还原
      const cmd = decodeURIComponent(rawHref.replace(/^term:\/\//, ''));
      if (cmd) {
        setPendingTermCmd(cmd);
      }
      return; // 不走预览弹窗
    }

    let type: 'image' | 'video' | 'browser' = 'browser';

    // ——————————————————————————————————————————————————
    // 检测是否为「本地文件路径」，匹配后统一走 /preview 接口
    // ——————————————————————————————————————————————————
    let localPath: string | null = null;

    // 1. file:// 协议 (file:///D:/xxx or file:///Users/xxx)
    if (rawHref.startsWith('file://')) {
      let p = rawHref.replace(/^file:\/\//, '');
      // Windows 路径: /C:/xxx → C:/xxx
      if (p.startsWith('/') && p.charAt(2) === ':') {
        p = p.substring(1);
      }
      localPath = safeDecodeUri(p);
    }
    // 2. Agent 沙盒路径: /agent_vm/xxx or ./agent_vm/xxx
    else if (rawHref.startsWith('/agent_vm/') || rawHref === '/agent_vm' ||
             rawHref.startsWith('./agent_vm/') || rawHref === './agent_vm' ||
             rawHref.startsWith('../agent_vm/')) {
      localPath = rawHref; // 后端 convert_sandbox_path 会处理
    }
    // 3. Windows 绝对路径: C:/xxx 或 D:\xxx (盘符+冒号开头)
    else if (/^[A-Za-z]:[/\\]/.test(rawHref)) {
      localPath = rawHref;
    }
    // 4. 其他 ./ 或 ../ 开头的相对路径 + 已知扩展名
    else if ((rawHref.startsWith('./') || rawHref.startsWith('../'))) {
      const ext = rawHref.split('.').pop()?.toLowerCase() || '';
      if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'mp4', 'webm', 'mov', 'ogg',
           'pdf', 'txt', 'md', 'csv', 'json', 'log', 'html'].includes(ext)) {
        localPath = rawHref;
      }
    }

    if (localPath !== null) {
      const ext = localPath.split('.').pop()?.toLowerCase() || '';

      // 🌟 Markdown → 应用内富文本预览（ReactMarkdown + GFM，与聊天气泡同引擎）
      if (ext === 'md' || ext === 'markdown') {
        openMdPreview(localPath, rawHref);
        return;
      }

      // 🌟 HTML/SVG → Electron 下解析真实路径后以 file:// 启动内置浏览器，
      //    复用内置浏览器的元素 pick 模式 + 评论能力（SVG 由 Chromium 原生渲染，
      //    CDP 拾取完全兼容 SVG 文档）；Web 端回退到 /preview 代理预览
      if (['html', 'htm', 'svg'].includes(ext)) {
        if ((window as any).purrcat?.browserNewTab) {
          openLocalFileInBrowser(localPath, rawHref);
          return;
        }
        setPreviewType(ext === 'svg' ? 'image' : 'browser');
        setPreviewRawUrl(rawHref);
        setPreviewUrl(`/api/filesystem/preview?path=${encodeURIComponent(localPath)}`);
        return;
      }

      if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'].includes(ext)) {
        type = 'image';
      } else if (['mp4', 'webm', 'mov', 'ogg', 'avi', 'mkv'].includes(ext)) {
        type = 'video';
      } else {
        type = 'browser';
      }

      // 🌟 Electron 环境：在独立窗口中打开（加载后端 /preview URL，渲染效果与 iframe 一致）
      const finalUrl = `/api/filesystem/preview?path=${encodeURIComponent(localPath)}`;
      if ((window as any).purrcat?.openPreviewWindow) {
        const fullUrl = window.location.origin + finalUrl;
        const fileName = rawHref.replace(/\\/g, '/').split('/').pop() || 'Preview';
        (window as any).purrcat.openPreviewWindow(fullUrl, fileName, type);
        return;
      }

      // 非 Electron fallback：内嵌弹窗
      setPreviewType(type);
      setPreviewRawUrl(rawHref);
      setPreviewUrl(finalUrl);
      return;
    }

    // http/https 等非本地链接：在内置浏览器中打开
    openInBrowser(rawHref, rawHref.split('/').pop() || rawHref);
  };

  // 🌟 全局拦截气泡内的链接点击事件：本地路径走 FastAPI 代理，http/https 走内置浏览器
  const handleMessageClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    const anchor = target.closest('a');
    if (!anchor) return;

    // ⚠️ 必须用 getAttribute('href') 拿到 Agent 原始输出的字符串
    // anchor.href 是浏览器规范化后的 URL，会把 D:/xxx.png 变成 http://localhost:3000/chat/D:/xxx.png
    const rawHref = anchor.getAttribute('href') || '';
    if (!rawHref) return;

    e.preventDefault();
    handleRawLinkClick(rawHref);
  };

  // 🌟 主进程拦截的 window.open / target=_blank 链接统一走链接路由（http → 内置浏览器）
  // 用 ref 穿透闭包，保证监听器始终调用最新版 handleRawLinkClick（其内部依赖 browserTabs 等状态）
  const rawLinkClickRef = useRef(handleRawLinkClick);
  rawLinkClickRef.current = handleRawLinkClick;
  useEffect(() => {
    const off = (window as any).purrcat?.onOpenUrl?.((url: string) => rawLinkClickRef.current(url));
    return () => { if (off) off(); };
  }, []);

  const [showSkillSelectModal, setShowSkillSelectModal] = useState(false);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [tempSelectedSkills, setTempSelectedSkills] = useState<string[]>([]);

  const [showMcpSelectModal, setShowMcpSelectModal] = useState(false);
  const [selectedMcps, setSelectedMcps] = useState<string[]>([]);
  const [tempSelectedMcps, setTempSelectedMcps] = useState<string[]>([]);

  const [showGraphSelectModal, setShowGraphSelectModal] = useState(false);
  const [selectedGraphs, setSelectedGraphs] = useState<string[]>([]);
  const [tempSelectedGraphs, setTempSelectedGraphs] = useState<string[]>([]);
  const [graphData, setGraphData] = useState<any[]>([]);

  const [refPaths, setRefPaths] = useState<string[]>([]);
  const [showRefModal, setShowRefModal] = useState(false); 
  const [tempRefPath, setTempRefPath] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  const [showInstallMcpModal, setShowInstallMcpModal] = useState(false);
  const [mcpInstallJson, setMcpInstallJson] = useState('');
  const [isInstallingMcp, setIsInstallingMcp] = useState(false);

  const [showInstallSensorModal, setShowInstallSensorModal] = useState(false);
  const [sensorInstallJson, setSensorInstallJson] = useState('');
  const [isInstallingSensor, setIsInstallingSensor] = useState(false);

  const [isConfigOpen, setIsConfigOpen] = useState(false);

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingMsgsRef = useRef<string[]>([]);
  const isAutoScroll = useRef(true);

  // 🌟 气泡分组渲染（QQ 式）：一次只渲染一组 20 条，向上滚动/点击加载上一组
  const MSG_GROUP_SIZE = 20;
  const [msgGroupCount, setMsgGroupCount] = useState(1);
  const visibleMsgCount = msgGroupCount * MSG_GROUP_SIZE;
  const msgStartIdx = Math.max(0, messages.length - visibleMsgCount);
  const hasOlderMsgs = msgStartIdx > 0;

  // 加载上一组：高度补偿在 useLayoutEffect（DOM 提交后、绘制前）执行，
  // 旧方案用 rAF 在 React 未提交时补偿为 0，视口滞留顶部导致惯性滚动连锁触发多次加载
  const pendingCompensation = useRef<number | null>(null);
  const loadOlderMessages = () => {
    if (pendingCompensation.current !== null) return;
    const el = messagesContainerRef.current;
    if (!el) { setMsgGroupCount(g => g + 1); return; }
    pendingCompensation.current = el.scrollHeight;
    setMsgGroupCount(g => g + 1);
  };
  useLayoutEffect(() => {
    if (pendingCompensation.current === null || !messagesContainerRef.current) return;
    const el = messagesContainerRef.current;
    const prev = pendingCompensation.current;
    pendingCompensation.current = null;
    el.scrollTop += el.scrollHeight - prev; // 视口钉在原位，不跳动
  }, [msgGroupCount]);

  // 🌟 滚动监听 +「一次碰顶只加载一组」：碰顶触发后收起扳机，
  // 必须先离开顶部区域（scrollTop > 150）并度过 400ms 冷却期才能再次触发
  const nearTopArmed = useRef(true);
  const lastTopLoadAt = useRef(0);
  const handleScroll = () => {
    if (!messagesContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
    if (scrollTop > 150 && Date.now() - lastTopLoadAt.current > 400) {
      nearTopArmed.current = true;
    } else if (scrollTop < 60 && nearTopArmed.current && hasOlderMsgs) {
      nearTopArmed.current = false;
      lastTopLoadAt.current = Date.now();
      loadOlderMessages();
    }
  };

  // 🌟 会话/分支切换：下一次消息到达时直接瞬时贴底，不留在顶部
  const snapToBottomRef = useRef(true);
  useEffect(() => { snapToBottomRef.current = true; isAutoScroll.current = true; pendingCompensation.current = null; }, [currentSessionId, currentBranchId]);
  useEffect(() => {
    if (messages.length === 0) return;
    if (snapToBottomRef.current) {
      snapToBottomRef.current = false;
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
      return;
    }
    if (isAutoScroll.current) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  useEffect(() => { pendingMsgsRef.current = []; setMsgGroupCount(1); }, [currentBranchId]);
  useEffect(() => { setMsgGroupCount(1); }, [currentSessionId]);
  const fetchGlobalStats = async () => {
    try { const res = await fetch('/api/system/agent/stats'); if (res.ok) setGlobalStats(await res.json()); } catch { /* noop */ }
  };
  useEffect(() => { if (messages.length === 0) fetchGlobalStats(); }, [messages.length]);

  const loadBranches = async (sid: string) => {
    try { const res = await fetch(`/api/sessions/${sid}/branches`); if (res.ok) setBranches(await res.json()); } catch { setBranches({ main: {} }); }
  };

  const fetchGlobalDiffs = async () => {
    try { const res = await fetch('/api/filesystem/diffs'); if (res.ok) { const data = await res.json(); if (data.diffs) setFileChanges(data.diffs); } } catch { /* noop */ }
  };
  useEffect(() => { fetchGlobalDiffs(); const interval = setInterval(fetchGlobalDiffs, 3000); return () => clearInterval(interval); }, []);
  useEffect(() => { if (fileChanges.length > 0 && (!activeDiffPath || !fileChanges.some(c => c.path === activeDiffPath))) setActiveDiffPath(fileChanges[0].path); }, [fileChanges, activeDiffPath]);

  const handleAck = async (path: string, newestBackupId: string) => {
    try { const res = await fetch(`/api/filesystem/ack`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, backup_id: newestBackupId }) }); if (res.ok) { toast.success("已确认更改"); fetchGlobalDiffs(); } } catch { /* noop */ }
  };
  // 🌟 一键接受全部更改（FileChangesPanel / 切换会话拦截弹窗共用）
  const handleAckAll = async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/filesystem/ack_all', { method: 'POST' });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.success(`已接受全部更改（${data.total ?? 0} 个文件）`);
        fetchGlobalDiffs();
        return true;
      }
      toast.error('接受全部更改失败');
      return false;
    } catch { toast.error('接受全部更改失败'); return false; }
  };
  const handleRollback = async (path: string, oldestBackupId: string) => {
    try { const res = await fetch(`/api/filesystem/undo`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, backup_id: oldestBackupId }) }); if (res.ok) { toast.success("文件已恢复"); fetchGlobalDiffs(); } } catch { /* noop */ }
  };

  useEffect(() => {
    let tokenInterval: ReturnType<typeof setTimeout>;
    const fetchToken = async () => { try { const res = await fetch('/api/agent/token'); if (res.ok) { const data = await res.json(); setTokenData({ window: data.window_token, max: data.max_token, cached: data.cached_token || 0 }); } } catch { /* noop */ } };
    if (currentSessionId) { fetchToken(); tokenInterval = setInterval(fetchToken, 5000); }
    return () => { if (tokenInterval) clearInterval(tokenInterval); };
  }, [currentSessionId]);

  const fetchRequests = async () => {
    try { const resPending = await fetch('/api/requests').catch(() => null); if (resPending?.ok) { const dataPending = await resPending.json(); setPendingReqs(dataPending); const currentIds = dataPending.map((r: any) => r.id); if (currentIds.some((id: string) => !prevPendingIds.current.includes(id)) && dataPending.length > 0) setShowReqQueue(true); prevPendingIds.current = currentIds; } } catch { /* noop */ }
  };
  useEffect(() => { fetchRequests(); const interval = setInterval(fetchRequests, 3000); return () => clearInterval(interval); }, []);

  // 监听独立窗口回归事件（用户关闭独立窗口时主进程推送）
  useEffect(() => {
    const purrcat = (window as any).purrcat;
    if (!purrcat?.onBrowserReattached) return;
    return purrcat.onBrowserReattached(() => {
      // 👇 重点修复：在重新附着时，强制重置为正常浏览模式，防止带入旧状态
      setBrowserMode('browse');

      // 先更新可见性，让 React 开始渲染 AgentBrowserPanel 及其 DOM 树
      setBrowserDetached(false);
      setShowBrowser(true);
      // 🌟 延迟 100ms + requestAnimationFrame 双保险：
      // 等 React 挂载完成、Flex 布局稳定（侧边栏、Tab 栏尺寸完全落地），
      // 再触发 browser:set-bounds 同步，保证 getBoundingClientRect 测到准确值
      setTimeout(() => {
        window.requestAnimationFrame(() => {
          const ev = new CustomEvent('purrcat-browser-force-sync');
          window.dispatchEvent(ev);
        });
      }, 100);
    });
  }, []);

  // 监听 IDE 独立窗口回归事件
  useEffect(() => {
    const purrcat = (window as any).purrcat;
    if (!purrcat?.onIdeReattached) return;
    return purrcat.onIdeReattached(() => {
      setShowIDE(true);
    });
  }, []);

  // 监听独立窗口拾取的 comment（用户在独立浏览器窗口选取元素后转发到聊天）
  // 依赖 currentSessionId 以保证 comment 发到正确的会话
  useEffect(() => {
    const purrcat = (window as any).purrcat;
    if (!purrcat?.onBrowserComment) return;
    return purrcat.onBrowserComment((data: any) => {
      handleBrowserComment(data.pixelData, data.comment, data.url);
    });
  }, [currentSessionId]);

  const handleResolveReq = async (reqId: string, approved: boolean, ignore: boolean, duration: number = 5) => {
    const feedback = feedbackInputs[reqId] || '';
    try { const res = await fetch(`/api/requests/${reqId}/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved, feedback, ignore, duration }) }); if (res.ok) { toast.success("请求处理完成"); setFeedbackInputs(p => { const n = {...p}; delete n[reqId]; return n; }); fetchRequests(); } } catch { /* noop */ }
  };

  const handleRename = async (id: string) => {
    if (!editingAlias.trim()) { setEditingSessionId(null); return; }
    try { const res = await fetch(`/api/sessions/${id}/rename`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ alias: editingAlias.trim() }) }); if (res.ok) { toast.success("会话已重命名！"); loadSessions(); } } catch { /* noop */ }
    setEditingSessionId(null);
  };

  const handleFileUpload = async (files: FileList | File[]) => {
    // 桌面端通过 Electron webUtils.getPathForFile 拿拖拽/粘贴文件的真实绝对路径
    const purrcat = (window as any).purrcat;
    if (!purrcat?.getPathForFile) {
      toast.error('当前环境不支持拖拽上传（需在 PurrCat 桌面端运行）');
      return;
    }

    const MAX_SIZE = 50 * 1024 * 1024; // 50MB 大小限制
    const newPaths: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i] as any;

      // 1. 通过 Electron 拿真实绝对路径（替代 Tauri 的 file.path）
      let realPath: string | null = null;
      try { realPath = purrcat.getPathForFile(file); } catch { realPath = null; }
      if (!realPath) {
        console.warn('无法获取文件路径，跳过:', file.name);
        continue;
      }

      // 2. 文件夹拦截：Web 中 type 为空且 size 为 4096 整数倍通常是目录
      if (!file.type && file.size % 4096 === 0) {
        console.warn('文件夹暂不支持上传:', file.name);
        continue;
      }

      // 3. 大小拦截
      if (file.size > MAX_SIZE) {
        console.warn('文件过大，已拦截:', file.name);
        toast.error(`文件过大，已拦截: ${file.name} (最大 50MB)`);
        continue;
      }

      // 直接用真实绝对路径作为引用，后端 Agent 自行读取（无需复制到 buffer）
      newPaths.push(realPath);
    }

    // 更新标签
    if (newPaths.length > 0) {
      setRefPaths((prev: string[]) => [...new Set([...prev, ...newPaths])]);
      toast.success(`已添加 ${newPaths.length} 个文件`);
    }
  };
  const handlePaste = (e: React.ClipboardEvent) => { if (e.clipboardData.files && e.clipboardData.files.length > 0) { e.preventDefault(); handleFileUpload(e.clipboardData.files); } };
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); const items = e.dataTransfer.items; if (items && items.length > 0) { const validFiles: File[] = []; for (let i = 0; i < items.length; i++) { const item = items[i]; if (item.kind === 'file') { const file = item.getAsFile(); if (file) validFiles.push(file); } } if (validFiles.length > 0) handleFileUpload(validFiles); } };

  const openMdEditor = async (type: 'SOUL' | 'GOAL') => { setMdType(type); setMdContent('Loading...'); setShowMdModal(true); try { const res = await fetch(`/api/config/markdown/${type}`); if (res.ok) { const data = await res.json(); setMdContent(data.content); } } catch { /* noop */ } };
  const saveMdContent = async () => { setIsSavingMd(true); try { const res = await fetch(`/api/config/markdown/${mdType}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: mdContent }) }); if (res.ok) setShowMdModal(false); } catch { /* noop */ } finally { setIsSavingMd(false); } };

  const fetchSensorData = async () => { try { const res = await fetch('/api/config/sensor'); if (res.ok) setSensorData(await res.json()); } catch { /* noop */ } };
  const reloadSensors = async () => {
    if (isReloadingSensors) return;
    setIsReloadingSensors(true);
    try {
      const res = await fetch('/api/config/sensor/reload', { method: 'POST' });
      const data = await res.json().catch(() => null);
      if (res.ok) toast.success(data?.message || "Sensors 已热重启");
      else toast.error(data?.detail || 'Sensors 热重启失败');
    } catch { toast.error('Sensors 热重启失败'); } finally { setIsReloadingSensors(false); }
  };
  const toggleSensorStatus = async (sensorName: string) => { try { const newSensorData = JSON.parse(JSON.stringify(sensorData)); newSensorData[sensorName].enabled = !newSensorData[sensorName].enabled; setSensorData(newSensorData); const resSave = await fetch('/api/config/sensor', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(newSensorData) }); if (resSave.ok) await reloadSensors(); } catch { /* noop */ } };
  const handleInstallSensor = async () => { setIsInstallingSensor(true); try { const parsed = JSON.parse(sensorInstallJson); const newSensors = parsed.sensors ? parsed.sensors : parsed; const currentData = JSON.parse(JSON.stringify(sensorData)); Object.assign(currentData, newSensors); const resSave = await fetch('/api/config/sensor', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentData) }); if (resSave.ok) { await reloadSensors(); setShowInstallSensorModal(false); fetchSensorData(); } } catch { /* noop */ } finally { setIsInstallingSensor(false); } };

  const fetchMcp = async () => { try { const res = await fetch('/api/tools/mcp'); if (res.ok) setMcpData(await res.json()); } catch { /* noop */ } };
  const refreshMcp = async () => {
    if (isRefreshingMcp) return;
    setIsRefreshingMcp(true);
    try {
      const res = await fetch('/api/tools/mcp/refresh', { method: 'POST' });
      const data = await res.json().catch(() => null);
      if (res.ok) { toast.success(data?.message || 'MCP 已刷新'); fetchMcp(); }
      else toast.error(data?.detail || '刷新 MCP 失败');
    } catch { toast.error('刷新 MCP 失败'); } finally { setIsRefreshingMcp(false); }
  };
  const handleInstallMcp = async () => { setIsInstallingMcp(true); try { const res = await fetch('/api/tools/mcp/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config_json: mcpInstallJson.trim() }) }); if (res.ok) { setShowInstallMcpModal(false); fetchMcp(); } } catch { /* noop */ } finally { setIsInstallingMcp(false); } };

  const fetchSkill = async () => { try { const res = await fetch('/api/tools/skills'); if (res.ok) setSkillData(await res.json()); } catch { /* noop */ } };
  const refreshSkill = async () => {
    if (isRefreshingSkill) return;
    setIsRefreshingSkill(true);
    try {
      const res = await fetch('/api/tools/skills/refresh', { method: 'POST' });
      const data = await res.json().catch(() => null);
      if (res.ok) { toast.success(data?.message || 'Skill 已刷新'); fetchSkill(); }
      else toast.error(data?.detail || '刷新 Skill 失败');
    } catch { toast.error('刷新 Skill 失败'); } finally { setIsRefreshingSkill(false); }
  };
  const handleInstallSkill = async () => { setIsInstallingSkill(true); try { const res = await fetch('/api/tools/skills/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: skillInstallUrl.trim() }) }); if (res.ok) { setShowInstallSkillModal(false); fetchSkill(); } } catch { /* noop */ } finally { setIsInstallingSkill(false); } };

  const fetchGraphData = async () => { try { const res = await fetch('/api/graphs'); if (res.ok) setGraphData(await res.json()); } catch { /* noop */ } };

  useEffect(() => {
    if (showAddCronModal && newCron.task_hook && newCron.task_hook !== 'Agent') {
      fetch(`/api/graphs/${newCron.task_hook}/schema`)
        .then(res => res.json())
        .then(data => {
          const schema = data.global_schema || {};
          const template: Record<string, string> = {};
          Object.keys(schema).forEach(key => {
            template[key] = schema[key].description || `请输入值`;
          });
          setNewCron(prev => ({ ...prev, task_inputs_str: JSON.stringify(template, null, 2) }));
        })
        .catch(() => {});
    } else {
      setNewCron(prev => ({ ...prev, task_inputs_str: '{\n}' }));
    }
  }, [newCron.task_hook, showAddCronModal]);

  const fetchCron = async () => { try { const res = await fetch('/api/tools/cron'); if (res.ok) setCronData(await res.json()); } catch { /* noop */ } };
  const addCron = async () => { 
    let parsedInputs = {};
    if (newCron.task_hook !== 'Agent') {
      try {
        parsedInputs = JSON.parse(newCron.task_inputs_str);
      } catch {
        toast.error("工作流配置参数不符合合法标准的 JSON 格式！");
        return;
      }
    }
    try { 
      const res = await fetch('/api/tools/cron', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({
           title: newCron.title,
           trigger_time: newCron.trigger_time,
           repeat_rule: newCron.repeat_rule,
           task_hook: newCron.task_hook,
           task_inputs: parsedInputs
        }) 
      }); 
      if (res.ok) { 
        setShowAddCronModal(false); 
        setNewCron({ title: '', trigger_time: '', repeat_rule: 'none', task_hook: 'Agent', task_inputs_str: '{\n}' });
        fetchCron(); 
      } 
    } catch { /* noop */ } 
  };
  const deleteCron = async (id: string) => { try { await fetch(`/api/tools/cron/${id}`, { method: 'DELETE' }); fetchCron(); } catch { /* noop */ } };

  useEffect(() => { pendingMsgsRef.current = []; }, [currentBranchId]);

  const loadSessions = async () => { try { const res = await fetch('/api/sessions'); if (res.ok) { const data = await res.json(); setSessions(data); if (data.length > 0 && !currentSessionId) handleSelectSession(data[0].id); } } catch { /* noop */ } };
  const loadSessionHistory = async (id: string, bId: string = 'main') => { const res = await fetch(`/api/sessions/${id}?branch_id=${bId}`); if (res.ok) setMessages(await res.json()); };

  // 🌟 强制打断：物理掐断 Agent 正在执行的工具（长时网络请求/死循环命令）
  const handleForceInterrupt = async () => {
    try {
      const res = await fetch('/api/chat/interrupt', { method: 'POST' });
      if (res.ok) {
        toast.success('已强制打断 Agent');
        setIsAgentThinking(false);
      } else {
        toast.error('打断请求失败');
      }
    } catch { toast.error('打断请求失败'); }
  };

  // 🌟 记忆压缩：触发 Agent 的全局大总结并截断历史上下文（后台异步执行）
  const [isCompressingMemory, setIsCompressingMemory] = useState(false);
  const handleCompressMemory = async () => {
    if (isCompressingMemory) return;
    setIsCompressingMemory(true);
    toast('记忆压缩已开始，Agent 正在总结...', { icon: '🧠' });
    try {
      const res = await fetch('/api/chat/compress-memory', { method: 'POST' });
      if (res.ok) {
        // 后台执行中：轮询 compressing 标记（压缩不改 agent.state，不能靠 idle 判定）
        const checkDone = setInterval(async () => {
          try {
            const s = await fetch(`/api/sessions/${currentSessionId || ''}/status`);
            if (s.ok) {
              const sd = await s.json();
              if (sd.compressing === false) {
                clearInterval(checkDone);
                setIsCompressingMemory(false);
                toast.success('记忆压缩完成');
              }
            }
          } catch { /* noop */ }
        }, 2000);
        // 兜底：最长 10 分钟自动解除按钮锁定
        setTimeout(() => { clearInterval(checkDone); setIsCompressingMemory(false); }, 600000);
      } else {
        setIsCompressingMemory(false);
        toast.error('记忆压缩请求失败');
      }
    } catch {
      setIsCompressingMemory(false);
      toast.error('记忆压缩请求失败');
    }
  };
  
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { if (sessionId && sessionId !== currentSessionId) { pendingMsgsRef.current = []; setCurrentSessionId(sessionId); setCurrentBranchId('main'); loadSessionHistory(sessionId, 'main'); loadBranches(sessionId); } }, [sessionId, currentSessionId]);

  useEffect(() => {
    if (!currentSessionId) return;
    const interval = setInterval(async () => {
      if (isCheckingOut) return;
      try {
        const [msgRes, statusRes] = await Promise.all([ fetch(`/api/sessions/${currentSessionId}?branch_id=${currentBranchId}`), fetch(`/api/sessions/${currentSessionId}/status`) ]);
        if (msgRes.ok) {
          const history = await msgRes.json();
          pendingMsgsRef.current = pendingMsgsRef.current.filter(pendingText => !hasMessageInHistory(history, pendingText));
          const newMessages = [...history];
          pendingMsgsRef.current.forEach(text => newMessages.push({ role: 'user', content: text }));
          // 🌟 轮询去重：内容无变化时返回旧引用，跳过整个消息列表的重渲染（卡顿主因）
          setMessages(prev => {
            if (prev.length === newMessages.length
              && prev[prev.length - 1]?.content === newMessages[newMessages.length - 1]?.content
              && prev[0]?.content === newMessages[0]?.content) return prev;
            return newMessages;
          });
        }
        if (statusRes.ok) { const statusData = await statusRes.json(); setIsAgentThinking(statusData.is_thinking); loadBranches(currentSessionId); }
      } catch { /* noop */ }
    }, 1500);
    return () => clearInterval(interval);
  }, [currentSessionId, currentBranchId, isCheckingOut]);

  const handleSelectSession = async (id: string) => { setIsCheckingOut(true); setCurrentSessionId(id); setCurrentBranchId('main'); navigate(`/chat/${id}`, { replace: true }); try { await fetch(`/api/sessions/${id}/checkout`, { method: 'POST' }).catch(() => {}); await loadSessionHistory(id, 'main'); await loadBranches(id); } catch { /* noop */ } finally { setIsCheckingOut(false); } };

  // 🌟 切换会话拦截：存在未接受的文件更改时，先弹窗询问是否接受全部更改
  const requestSelectSession = (id: string) => {
    if (fileChanges.length > 0 && id !== currentSessionId) { setPendingSwitchId(id); return; }
    handleSelectSession(id);
  };
  // 确认接受全部更改并切换；取消则留在当前会话
  const confirmAckAllAndSwitch = async () => {
    if (!pendingSwitchId) return;
    const targetId = pendingSwitchId;
    setPendingSwitchId(null);
    const ok = await handleAckAll();
    if (ok) handleSelectSession(targetId);
  };
  const confirmNewSession = async () => {
    setShowModal(false);
    setIsCheckingOut(true);
    try {
      const res = await fetch('/api/sessions/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias: newAlias.trim() })
      });
      if (res.ok) {
        const data = await res.json();
        await loadSessions();
        await handleSelectSession(data.id);

        // 如果选择了作坊，则自动发送第一条消息注入上下文
        if (selectedProject) {
          await fetch('/api/chat/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: data.id,
              events: [{ type: 'user', content: `我们现在来处理作坊项目：${selectedProject}` }]
            })
          });
        }
      }
    } catch { /* noop */ } finally {
      setIsCheckingOut(false);
      setNewAlias('');
      setSelectedProject('');
    }
  };
  const confirmBranchSession = async () => { setShowBranchModal(false); setIsCheckingOut(true); try { const res = await fetch(`/api/sessions/${currentSessionId}/branch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ alias: branchAlias.trim() }) }); if (res.ok) { const data = await res.json(); await loadSessions(); await handleSelectSession(data.id); } } catch { /* noop */ } finally { setIsCheckingOut(false); } };
  // 🌟 一键分支：不弹窗，直接基于当前会话新建分支并切换过去（模仿 confirmBranchSession）
  const handleQuickBranch = async () => {
    if (!currentSessionId || isCheckingOut) return;
    setIsCheckingOut(true);
    try {
      const res = await fetch(`/api/sessions/${currentSessionId}/branch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ alias: '' }) });
      if (res.ok) {
        const data = await res.json();
        await loadSessions();
        await handleSelectSession(data.id);
      }
    } catch { /* noop */ } finally { setIsCheckingOut(false); }
  };
  const confirmDeleteSession = async () => { if (!sessionToDelete) return; try { const res = await fetch(`/api/sessions/${sessionToDelete}`, { method: 'DELETE' }); if (res.ok) { if (currentSessionId === sessionToDelete) { setCurrentSessionId(null); setMessages([]); } setSessionToDelete(null); loadSessions(); } } catch { /* noop */ } };

  const handleSend = async () => {
    if (!input.trim() || !currentSessionId) return;
    const eventsToPush: any[] = [];
    const userText = input.trim();
    refPaths.forEach(path => eventsToPush.push({ type: 'file-quote', content: `user quote the file：${path}` }));
    selectedSkills.forEach(skill => eventsToPush.push({ type: 'skill-quote', content: `user want you fetch skill：${skill}` }));
    selectedMcps.forEach(mcp => eventsToPush.push({ type: 'mcp-quote', content: `user want you fetch mcp：${mcp}` }));
    selectedGraphs.forEach(graph => eventsToPush.push({ type: 'graph-quote', content: `user quote the graph：${graph}` }));
    if (useBrainstorm) eventsToPush.push({ type: 'tool-quote', content: `user want you use BrainStorm` });
    eventsToPush.push({ type: 'user', content: userText });
    
    setInput(''); setSelectedSkills([]); setSelectedMcps([]); setSelectedGraphs([]); setRefPaths([]); setUseBrainstorm(false);
    
    // 立即进入思考状态，给用户视觉反馈
    setIsAgentThinking(true);
    
    // 🌟 治本修复：如果是正常长度，走乐观更新；如果是超长文本(>3000)，直接放弃乐观更新，静待后端轮询返回落盘提示
    if (userText.length < 3000) {
      pendingMsgsRef.current.push(userText);
      setMessages(prev => [...prev, { role: 'user', content: JSON.stringify({ events: eventsToPush }) }]);
    }

    try { await fetch('/api/chat/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: currentSessionId, events: eventsToPush }) }); } catch { /* noop */ }
  };

  // 🌟 在内置浏览器中打开链接（供 handleMessageClick 调用）
  const openInBrowser = async (url: string, title: string = 'Preview') => {
    const existingTab = browserTabs.find(t => t.url === url);
    if (existingTab) {
      setActiveTabId(existingTab.id);
      (window as any).purrcat?.browserSwitchTab?.(existingTab.id);
    } else {
      // 桌面端：先让主进程创建 WebContentsView，用返回的 tabId 作为前端 tab.id（两者对齐）
      let tabId = Date.now().toString();
      try {
        const pid = await (window as any).purrcat?.browserNewTab?.(url);
        if (pid) tabId = pid;
      } catch { /* 非 Electron 环境，用临时 id */ }
      const newTab: BrowserTab = { id: tabId, url, title };
      setBrowserTabs(prev => [...prev, newTab]);
      setActiveTabId(newTab.id);
    }
    setShowBrowser(true);
  };

  // 🌟 将宿主机真实路径转换为 file:// URL（盘符保留原样，其余段做百分号编码以支持空格/中文）
  const toFileUrl = (realPath: string) => {
    const norm = realPath.replace(/\\/g, '/');
    const m = norm.match(/^([A-Za-z]):\/(.*)$/);
    if (m) return `file:///${m[1]}:/${m[2].split('/').map(encodeURIComponent).join('/')}`;
    return 'file:///' + norm.replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/');
  };

  // 🌟 本地 HTML/SVG → 解析真实路径 → file:// 启动内置浏览器（可用元素 pick + 评论）
  const openLocalFileInBrowser = async (localPath: string, rawHref: string) => {
    const fileName = rawHref.replace(/\\/g, '/').split('/').pop() || 'Preview';
    // 解析失败回退：走 /preview 代理的普通预览（svg→img，html→iframe）
    const fallback = () => {
      const ext = localPath.split('.').pop()?.toLowerCase() || '';
      setPreviewType(ext === 'svg' ? 'image' : 'browser');
      setPreviewRawUrl(rawHref);
      setPreviewUrl(`/api/filesystem/preview?path=${encodeURIComponent(localPath)}`);
    };
    try {
      const res = await fetch(`/api/filesystem/resolve?path=${encodeURIComponent(localPath)}`);
      if (!res.ok) { fallback(); return; }
      const data = await res.json();
      if (!data.real_path) { fallback(); return; }
      openInBrowser(toFileUrl(data.real_path), fileName);
      toast.success('已在内置浏览器打开，可切换 pick 模式选取元素并评论', { icon: '🌐' });
    } catch {
      fallback();
    }
  };

  // 🌟 Markdown 链接 → 应用内富文本预览（拉取原文，ReactMarkdown + GFM 渲染）
  const openMdPreview = async (localPath: string, rawHref: string) => {
    setPreviewType('markdown');
    setPreviewRawUrl(rawHref);
    setPreviewUrl(`/api/filesystem/preview?path=${encodeURIComponent(localPath)}`); // 供"OPEN EXTERNALLY"兜底
    setPreviewMdBaseDir(localPath.replace(/\\/g, '/').split('/').slice(0, -1).join('/'));
    setPreviewMdContent(null);
    try {
      const res = await fetch(`/api/filesystem/read?path=${encodeURIComponent(localPath)}`);
      if (!res.ok) throw new Error('read failed');
      const data = await res.json();
      setPreviewMdContent(data.content ?? '');
    } catch {
      setPreviewMdContent(`# 读取失败\n\n无法加载文件内容：\n\n\`${localPath}\``);
    }
  };

  // 🌟 解析 md 预览中的图片/资源地址：本地与相对路径统一改走后端 /preview 代理
  const resolveMdAsset = (src: string) => {
    if (!src) return src;
    if (/^(https?:|data:|blob:)/i.test(src)) return src;
    const proxy = (p: string) => `/api/filesystem/preview?path=${encodeURIComponent(p)}`;
    if (src.startsWith('file://')) {
      let p = src.replace(/^file:\/\//, '');
      if (p.startsWith('/') && p.charAt(2) === ':') p = p.substring(1);
      return proxy(safeDecodeUri(p));
    }
    if (/^[A-Za-z]:[/\\]/.test(src) || src.startsWith('/agent_vm/') || src.startsWith('./agent_vm/')) return proxy(src);
    if (src.startsWith('/')) return proxy(src); // 绝对路径交给后端 convert_sandbox_path 解析
    // 相对路径：基于 md 文件所在目录拼接并归一化 ./ ..
    const segs = (previewMdBaseDir + '/' + src).split('/');
    const out: string[] = [];
    for (const s of segs) {
      if (s === '' || s === '.') continue;
      if (s === '..') out.pop();
      else out.push(s);
    }
    return proxy(out.join('/'));
  };

  // md 预览专用组件：在聊天样式基础上接管 <img>（本地资源代理）
  const MdPreviewComponents: any = {
    ...MarkdownComponents,
    img: ({ src, ...props }: any) => <img src={resolveMdAsset(String(src || ''))} {...props} />,
  };

  // 处理浏览器发来的评论，直接发送给 Agent（附带 currentUrl）
  const handleBrowserComment = async (pixelData: any, comment: string, currentUrl: string) => {
    if (!currentSessionId) return;
    
    const eventsToPush = [
      { 
        type: 'browser-comment', 
        content: `User marked an area in browser.\nURL: ${currentUrl}\nMode: ${pixelData.mode}\nElement/Pixels: ${JSON.stringify(pixelData.rect)}\nContext: ${pixelData.domContext}\nViewport: ${JSON.stringify(pixelData.viewport)}\nComment: ${comment}` 
      },
      { type: 'user', content: comment }
    ];

    setIsAgentThinking(true);
    setMessages(prev => [...prev, { role: 'user', content: JSON.stringify({ events: eventsToPush }) }]);

    try { 
      await fetch('/api/chat/batch', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify({ session_id: currentSessionId, events: eventsToPush }) 
      }); 
    } catch { toast.error("发送浏览器指令失败"); }
  };

  const confirmTraceToSkill = async () => {
    if (!currentSessionId) return;
    if (!traceSkillName.trim()) return toast.error("请指定技能名称！");
    if (!traceExpectation.trim()) return toast.error("请填写技能期望！");

    setIsTracing(true);
    const tid = toast.loading("正在为你分配技能进化工厂...");
    try {
      const res = await fetch('/api/evolve/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'skill',
          name: traceSkillName.trim(),
          is_upgrade: traceType === 'upgrade',
          goal: traceExpectation.trim()
        })
      });

      if (!res.ok) throw new Error("分配沙盒失败");
      const data = await res.json();
      const wp_id = data.workplace_id;
      const factoryPath = `/agent_vm/skill_workplace/${wp_id}/${traceSkillName.trim()}`;

      const content = `用户使用了trace_to_skill功能，已为你分配了技能工厂${factoryPath}/，请根据用户需要和本次会话的交互记录与历史经验升级或创建对应技能。以下是用户期望：\n${traceExpectation.trim()}`;

      const eventsToPush = [{ type: 'evolve_factory', content }];

      await fetch('/api/chat/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, events: eventsToPush })
      });

      toast.success("已将经验沉淀任务派发给 Agent！", { id: tid });
      setShowTraceModal(false);
      setTraceSkillName('');
      setTraceExpectation('');
    } catch (error) {
      console.error("工厂分配失败:", error);
      toast.error("工厂分配失败，请检查 Agent 状态", { id: tid });
    } finally {
      setIsTracing(false);
    }
  };

  // mode='file' 选文件(多选)；mode='directory' 选文件夹
  // 注：Windows/Linux 原生对话框不能同时选文件和文件夹，故按 mode 拆成两次单模式调用
  const handleAttachmentClick = async (mode: 'file' | 'directory' = 'file') => {
    setShowToolMenu(false);
    const purrcat = (window as any).purrcat;

    if (purrcat?.openDialog) {
      try {
        const paths = await purrcat.openDialog({ directory: mode === 'directory' });
        if (paths && Array.isArray(paths) && paths.length > 0) {

          if (mode === 'directory') {
            // 🌟 核心拦截逻辑：如果是选择文件夹，则弹出 IDE
            setIdeWorkspace(paths[0]);
            setShowBrowser(false); // 关闭浏览器，给 IDE 腾出空间
            setShowIDE(true);
            toast.success(`已在 IDE 中打开工作区: ${paths[0]}`);
          }

          setRefPaths((prev: string[]) => [...new Set([...prev, ...paths])]);
          if (mode === 'file') {
            toast.success(`已添加 ${paths.length} 个本地绝对路径`);
          }
        }
      } catch (e) {
        console.error('File selection canceled or failed', e);
      }
      return;
    }

    // 降级：HTML file input 仅支持文件多选，文件夹模式无降级
    if (mode === 'directory') {
      toast.error("提示：请在 preload.js/main.js 暴露 purrcat.openDialog() 以启用原生文件夹选择。");
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.onchange = (e: any) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files);
      }
    };
    input.click();
    toast.error("提示：请在 preload.js/main.js 暴露 purrcat.openDialog() 以启用原生文件选择。");
  };

  // --- Props 组织区 ---
  const modalProps = {
    isCheckingOut, showBusyModal, setShowBusyModal,
    showModal, setShowModal, newAlias, setNewAlias, selectedProject, setSelectedProject, workshops: infoData.workshops, confirmNewSession,
    showBranchModal, setShowBranchModal, branchAlias, setBranchAlias, confirmBranchSession,
    sessionToDelete, setSessionToDelete, confirmDeleteSession,
    branchToDelete, setBranchToDelete, currentSessionId, loadSessionHistory, loadBranches, setCurrentBranchId,
    showAddCronModal, setShowAddCronModal, newCron, setNewCron, addCron,
    showInstallSkillModal, setShowInstallSkillModal, skillInstallUrl, setSkillInstallUrl, handleInstallSkill, isInstallingSkill,
    showInstallMcpModal, setShowInstallMcpModal, mcpInstallJson, setMcpInstallJson, handleInstallMcp, isInstallingMcp,
    showInstallSensorModal, setShowInstallSensorModal, sensorInstallJson, setSensorInstallJson, handleInstallSensor, isInstallingSensor,
    showMdModal, setShowMdModal, mdType, mdContent, setMdContent, saveMdContent, isSavingMd,
    showSkillSelectModal, setShowSkillSelectModal, skillData, tempSelectedSkills, setTempSelectedSkills, expandedSkill, setExpandedSkill, setSelectedSkills,
    showMcpSelectModal, setShowMcpSelectModal, mcpData, tempSelectedMcps, setTempSelectedMcps, expandedMcp, setExpandedMcp, setSelectedMcps,
    showRefModal, setShowRefModal, tempRefPath, setTempRefPath, setRefPaths,
    showGraphSelectModal, setShowGraphSelectModal, graphData, tempSelectedGraphs, setTempSelectedGraphs, setSelectedGraphs,
    showSessionModal, setShowSessionModal, isAgentThinking, sessions, handleSelectSession: requestSelectSession, editingSessionId, editingAlias, setEditingAlias, setEditingSessionId, handleRename,
    pendingSwitchId, setPendingSwitchId, unacceptedChangeCount: fileChanges.length, confirmAckAllAndSwitch,
    showTraceModal, setShowTraceModal, traceType, setTraceType, traceSkillName, setTraceSkillName, traceExpectation, setTraceExpectation, confirmTraceToSkill, isTracing
  };

  const sidebarProps = {
    onBack, onSwitchToTask, setShowSessionModal, navigate,
    sidebarMode, setSidebarMode,
    sensorData, toggleSensorStatus, reloadSensors, isReloadingSensors, setShowInstallSensorModal, fetchSensorData,
    mcpData, expandedMcp, setExpandedMcp, refreshMcp, isRefreshingMcp, setShowInstallMcpModal, fetchMcp,
    skillData, expandedSkill, setExpandedSkill, refreshSkill, isRefreshingSkill, setShowInstallSkillModal, fetchSkill,
    cronData, deleteCron, setShowAddCronModal, fetchCron,
    openMdEditor, graphData, fetchGraphData  // 🌟 追加这两个！
  };

  const fileViewProps = { showFileView, setShowFileView, fileChanges, activeDiffPath, setActiveDiffPath, handleAck, handleRollback, handleAckAll };
  const queueProps = { showReqQueue, setShowReqQueue, pendingReqs, handleResolveReq, feedbackInputs, setFeedbackInputs, authDurations, setAuthDurations, expandedReasons, setExpandedReasons };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">

      <ChatModals {...modalProps} />
      <ConfigModal isOpen={isConfigOpen} onClose={() => setIsConfigOpen(false)} />
      
      {/* 🌟 如果浏览器和 IDE 都没有打开，才显示左侧边栏 */}
      {!showBrowser && !showIDE && !isCompact && <ChatSidebar {...sidebarProps} />}

      {/* 🌟 聊天框动态压缩：浏览器或 IDE 打开时都压缩至 420px */}
      <div style={sketchyShape1} className={`${(showBrowser || showIDE) ? 'w-[420px] shrink-0' : 'flex-1'} transition-all duration-300 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-10`}>
        
        {currentSessionId ? (
          <div className="absolute -top-2 right-12 px-6 py-1 bg-[#a3be8c] border-2 border-ink rotate-2 z-50 text-ink font-black text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center" style={sketchyShape2} title="Session ID">
            ID: {currentSessionId.split('_')[1] || currentSessionId.slice(-8)}
          </div>
        ) : <div className="absolute -top-4 right-12 w-32 h-8 bg-[#a3be8c]/80 border-2 border-ink -rotate-3 z-50" style={sketchyShape2}></div>}

        {!showBrowser && !showIDE ? (
          <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-4">
              <div style={sketchyShape1} className="w-12 h-12 bg-terracotta border-4 border-ink flex items-center justify-center -rotate-6 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]">
                <Cat size={28} className="text-paper" strokeWidth={2.5} />
              </div>
              <div className="flex items-center gap-3">
                <h2 className="text-4xl font-black tracking-tighter text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat.</h2>
                {/* 🌟 心跳控制按钮 */}
                <button 
                  onClick={() => setShowHeartbeatModal(true)} 
                  className={`p-2 border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all hover:scale-110 active:translate-y-1 active:shadow-none ${heartbeatConfig.active ? 'bg-[#bf616a] text-paper' : 'bg-cream text-ink/40'}`} 
                  style={sketchyShape3} 
                  title="Agent Subconscious Heartbeat"
                >
                  <Heart size={20} strokeWidth={3} className={heartbeatConfig.active ? "animate-pulse" : ""} />
                </button>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
               {currentSessionId && (
                 <div className="flex items-center gap-2" title={`Token: ${tokenData.window} / ${tokenData.max}`}>
                   <span className="text-[11px] font-black text-ink/50" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEM</span>
                   <div className="w-36 h-[14px] border-2 border-ink bg-cream p-[2px]" style={sketchyShape3}>
                     <div className="h-full transition-all duration-1000 ease-out border-r-2 border-ink" style={{ width: `${Math.min(100, (tokenData.window / tokenData.max) * 100)}%`, backgroundImage: (tokenData.window / tokenData.max) > 0.8 ? 'repeating-linear-gradient(45deg, #bf616a, #bf616a 2px, transparent 2px, transparent 6px)' : 'repeating-linear-gradient(-45deg, #d08770, #d08770 2px, transparent 2px, transparent 6px)', backgroundColor: (tokenData.window / tokenData.max) > 0.8 ? 'rgba(191,97,106,0.1)' : 'rgba(208,135,112,0.1)', ...sketchyShape1 }} />
                   </div>
                   <span className="text-[11px] font-black text-ink/70 w-8 text-right shrink-0">{Math.round((tokenData.window / tokenData.max) * 100)}%</span>
                 </div>
               )}

               <button onClick={() => { setTerminalCmd(null); setShowTerminal(!showTerminal); setShowFileView(false); }} className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center ${showTerminal ? 'bg-[#88c0d0] text-paper' : 'bg-cream text-ink'}`} style={sketchyShape2} title="打开终端">
                 <TerminalSquare size={20} strokeWidth={3} />
               </button>

               <button onClick={() => setShowFileView(!showFileView)} className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center ${showFileView ? 'bg-[#88c0d0] text-paper' : 'bg-cream text-ink'}`} style={sketchyShape3}>
                 <FolderOpen size={20} strokeWidth={3} />
                 {fileChanges.length > 0 && <span className="absolute -top-2 -right-2 bg-[#d08770] text-paper text-xs px-1.5 py-0.5 rounded-full border-2 border-ink">{fileChanges.length}</span>}
               </button>

               <button onClick={() => setShowReqQueue(!showReqQueue)} className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center ${pendingReqs.length > 0 ? 'bg-[#EBCB8B] text-ink animate-pulse' : 'bg-cream text-ink'}`} style={sketchyShape2}>
                 <Bell size={20} strokeWidth={3} />
                 {pendingReqs.length > 0 && <span className="absolute -top-2 -right-2 bg-[#bf616a] text-paper text-xs px-1.5 py-0.5 rounded-full border-2 border-ink">{pendingReqs.length}</span>}
               </button>

               <button onClick={() => {
                 if (browserDetached) {
                   (window as any).purrcat?.browserReattach();
                   setBrowserDetached(false);
                   setShowBrowser(true);
                 } else {
                   setShowBrowser(!showBrowser);
                 }
               }} className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center ${showBrowser || browserDetached ? 'bg-[#88c0d0] text-paper' : 'bg-cream text-ink'}`} style={sketchyShape3} title="内置浏览器">
                 <Globe size={20} strokeWidth={3} />
               </button>
            </div>
          </div>
        ) : (
          <div className="pt-6 px-6 pb-2 flex justify-between items-center shrink-0 border-b-4 border-ink/10">
            <h2 className="text-2xl font-black tracking-tighter text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat.</h2>
            <button onClick={() => { if (showIDE) setShowIDE(false); else setShowBrowser(false); }} className="p-1.5 border-2 border-ink hover:bg-[#bf616a] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all" style={sketchyShape2}>
              <X size={18} strokeWidth={3} />
            </button>
          </div>
        )}

        {currentSessionId && Object.keys(branches).length > 1 && (
          <div className="px-10 flex gap-3 overflow-x-auto shrink-0 pb-3 border-b-4 border-ink/10 pt-1 select-none">
            {Object.keys(branches).map((bId) => {
              const isActive = currentBranchId === bId;
              const label = bId === 'main' ? 'MAIN' : `${bId.split('_')[1] || bId}`;
              return (
                <div key={bId} className="relative group flex items-center">
                  <button onClick={() => { setCurrentBranchId(bId); loadSessionHistory(currentSessionId, bId); }} style={isActive ? sketchyShape1 : sketchyShape2} className={`px-4 py-1.5 font-black text-xs tracking-wider border-2 border-ink transition-all ${bId !== 'main' ? 'pr-8' : ''} ${isActive ? 'bg-[#EBCB8B] text-ink scale-105 z-10 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]' : 'bg-cream text-ink/80 hover:bg-sand hover:text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-[1px]'}`}>{label}</button>
                  {bId !== 'main' && <button onClick={(e) => { e.stopPropagation(); setBranchToDelete(bId); }} className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-0.5 bg-[#bf616a] text-paper border-2 border-ink rounded transition-all hover:scale-110 z-20"><X size={12} strokeWidth={3} /></button>}
                </div>
              );
            })}
          </div>
        )}

        {/* 🌟 消息渲染：分组加载（一次一组 20 条，向上滚动加载更早），加 onClick 拦截点击 */}
        <div ref={messagesContainerRef} onScroll={handleScroll} onClick={handleMessageClick} className={`flex-1 overflow-y-auto ${(showBrowser || showIDE) ? 'px-4' : 'px-10'} pb-6 flex flex-col gap-6 w-full z-10 pt-4`}>
          {messages.length === 0 && !showBrowser && !showIDE ? (
            <div className={`flex flex-col items-center justify-center h-full text-ink gap-5 p-2 w-full ${showBrowser ? 'max-w-none' : 'max-w-3xl'} mx-auto select-none`}>
              <div className="flex items-center mb-2"><p className="text-3xl font-black rotate-1 text-ink tracking-tight" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Hi, what are we building today?</p></div>
              <div className="grid grid-cols-3 gap-4 w-full">
                <div style={sketchyShape2} className="bg-paper border-4 border-ink p-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center gap-3 rotate-1"><div className="p-2 bg-[#EBCB8B]/30 border-2 border-ink" style={sketchyShape3}><Activity size={20} className="text-ink" strokeWidth={3} /></div><div className="flex-1 min-w-0"><div className="text-[10px] font-black text-ink/40">TODAY CALLS</div><div className="text-xl font-black font-mono text-ink truncate">{globalStats?.today?.calls ?? 0}</div></div></div>
                <div style={sketchyShape3} className="bg-paper border-4 border-ink p-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center gap-3 -rotate-1"><div className="p-2 bg-[#88c0d0]/30 border-2 border-ink" style={sketchyShape1}><Zap size={20} className="text-[#5e81ac]" strokeWidth={3} /></div><div className="flex-1 min-w-0"><div className="text-[10px] font-black text-ink/40">TOKENS BURNT</div><div className="text-xl font-black font-mono text-ink truncate">{globalStats?.today?.total_tokens ? globalStats.today.total_tokens.toLocaleString() : 0}</div></div></div>
                <div style={sketchyShape1} className="bg-paper border-4 border-ink p-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center gap-3 rotate-2"><div className="p-2 bg-[#a3be8c]/30 border-2 border-ink shrink-0" style={sketchyShape2}><Server size={20} className="text-[#729654]" strokeWidth={3} /></div><div className="flex-1 min-w-0 flex flex-col justify-center"><div className="text-[10px] font-black text-ink/40 leading-tight">CACHE HIT</div><div className="flex flex-col mt-0.5"><span className="text-lg font-black font-mono text-ink truncate leading-none">{globalStats?.today?.cached_tokens?.toLocaleString() || 0}</span></div></div></div>
              </div>
              <div style={sketchyShape1} className="w-full bg-paper border-4 border-ink p-5 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-3 relative mt-2">
                <div className="absolute -top-2 left-10 w-16 h-4 bg-[#d08770]/60 border-2 border-ink rotate-2" style={sketchyShape2}></div>
                <div className="flex justify-between items-end px-1"><span className="font-black text-sm tracking-wider" style={{ fontFamily: '"Comic Sans MS", cursive' }}>ANNUAL CONTRIBUTIONS</span></div>
                <div className="w-full">{renderSketchyHeatmap(globalStats?.heatmap)}</div>
              </div>
            </div>
          ) : (
            <>
          {hasOlderMsgs && (
            <div className="flex justify-center py-1">
              <button
                onClick={loadOlderMessages}
                style={sketchyShape3}
                className="px-4 py-1.5 text-xs font-black uppercase tracking-wider border-2 border-ink/40 text-ink/50 bg-paper hover:bg-[#88c0d0]/20 hover:border-ink hover:text-ink transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,0.15)]"
                title="加载更早的消息（也可直接滚动到顶部）"
              >
                ↑ 加载更早的消息（还有 {msgStartIdx} 条）
              </button>
            </div>
          )}
            {messages.slice(msgStartIdx).map((msg, idx) => {
              const gIdx = msgStartIdx + idx; // 全局索引（trace2skill 等按全局位置判断）
              if (msg.role === 'user') {
                const parsedData = parseEventsContent(msg.content);
                return (
                  <div key={gIdx} className="flex flex-col w-full items-end mb-4">
                    {parsedData.attachments.length > 0 && (
                      <div className="flex flex-col gap-2 w-full items-end mb-2">
                        {parsedData.attachments.map((att: any, aIdx: number) => (
                          <div key={`att-${aIdx}`} style={sketchyShape3} className="px-4 py-2 bg-ink/5 border-2 border-ink text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center gap-2 max-w-[70%]"><span className="font-bold text-xs opacity-80 font-mono truncate">{att.content}</span></div>
                        ))}
                      </div>
                    )}
                    {parsedData.userMessages.map((userMsg: any, uIdx: number) => (
                      <div key={`u-${uIdx}`} className="flex flex-col gap-3 w-full max-w-[85%] items-end">
                        {userMsg.content && (
                          <div style={sketchyShape2} className="group/bubble w-full p-6 border-4 border-ink relative bg-cream text-ink shadow-[6px 6px 0px 0px rgba(26,26,26,1)]">
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(userMsg.content).then(() => toast.success('Copied!'));
                              }}
                              className="absolute top-2 right-2 p-1.5 bg-paper border-2 border-ink text-ink/60 hover:text-ink hover:bg-[#F9E2AF] shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all opacity-0 group-hover/bubble:opacity-100 z-10"
                              style={sketchyShape3}
                              title="复制内容"
                            >
                              <ClipboardCopy size={14} strokeWidth={2.5} />
                            </button>
                            <div className="text-[17px] font-bold text-ink whitespace-pre-wrap break-words">{userMsg.content}</div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              } else if (msg.role === 'tool') {
                return <div key={gIdx} className="flex w-full justify-start"><ToolMessageBubble msg={msg} /></div>;
              } else {
                return (
                  <div key={gIdx} className="flex w-full justify-start">
                    <div className="flex flex-col gap-3 w-full max-w-[85%] items-start">
                      {msg.content && (
                        <div style={sketchyShape1} className="group/bubble w-full p-6 border-4 border-ink relative bg-cream text-ink shadow-[6px 6px 0px 0px rgba(26,26,26,1)]">
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(msg.content).then(() => toast.success('Copied!'));
                            }}
                            className="absolute top-2 right-2 p-1.5 bg-paper border-2 border-ink text-ink/60 hover:text-ink hover:bg-[#F9E2AF] shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all opacity-0 group-hover/bubble:opacity-100 z-10"
                            style={sketchyShape3}
                            title="复制内容"
                          >
                            <ClipboardCopy size={14} strokeWidth={2.5} />
                          </button>
                          <div>
                            <div className="flex items-center gap-2 mb-4">
                              <Cat size={20} strokeWidth={2.5}/>
                              <span className="font-black text-sm uppercase tracking-widest bg-ink text-paper px-2 py-0.5" style={{ ...sketchyShape3, fontFamily: '"Comic Sans MS", cursive' }}>ASSISTANT</span>
                            </div>
                            <div className="text-[17px] font-bold text-ink"><ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents} urlTransform={allowFileUrlTransform}>{msg.content}</ReactMarkdown></div>
                          </div>
                        </div>
                      )}
                      {msg.role === 'assistant' && gIdx === messages.length - 1 && !isAgentThinking && (
                        <div className="flex justify-end gap-2 mt-3 animate-in fade-in duration-300">
                          <button
                            onClick={() => {
                              if (skillData.length === 0) fetchSkill();
                              setShowTraceModal(true);
                            }}
                            className="p-2 bg-paper border-2 border-ink hover:bg-[#EBCB8B] hover:text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all hover:-translate-y-[1px] active:translate-y-0 active:shadow-none"
                            style={sketchyShape2}
                            title="Trace to Skill (经验沉淀为技能)"
                          >
                            <BookOpen size={18} strokeWidth={2.5} />
                          </button>
                          <button
                            onClick={handleCompressMemory}
                            disabled={isCompressingMemory}
                            className="p-2 bg-paper border-2 border-ink hover:bg-[#b48ead] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all hover:-translate-y-[1px] active:translate-y-0 active:shadow-none disabled:opacity-50 disabled:hover:bg-paper disabled:hover:text-ink disabled:hover:translate-y-0"
                            style={sketchyShape3}
                            title="Memory Compress (手动触发记忆压缩：全局大总结并截断历史上下文)"
                          >
                            {isCompressingMemory ? <Loader2 size={18} strokeWidth={2.5} className="animate-spin" /> : <Brain size={18} strokeWidth={2.5} />}
                          </button>
                          <button
                            onClick={handleQuickBranch}
                            disabled={isCheckingOut}
                            className="p-2 bg-paper border-2 border-ink hover:bg-[#a3be8c] hover:text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all hover:-translate-y-[1px] active:translate-y-0 active:shadow-none disabled:opacity-50 disabled:hover:bg-paper disabled:hover:text-ink disabled:hover:translate-y-0"
                            style={sketchyShape1}
                            title="Branch (基于当前会话新建分支并切换过去)"
                          >
                            {isCheckingOut ? <Loader2 size={18} strokeWidth={2.5} className="animate-spin" /> : <GitMerge size={18} strokeWidth={2.5} />}
                          </button>
                        </div>
                      )}
                      {msg.tool_calls && msg.tool_calls.map((tc: any, tIdx: number) => <ToolCallBubble key={`tc-${tIdx}`} tc={tc} />)}
                    </div>
                  </div>
                );
              }
            })}
            </>
          )}
          {currentBranchId === 'main' && messages.length > 0 && (
            <div className="flex justify-start mb-4 w-full">
              <div style={sketchyShape1} className={`p-4 w-fit transition-colors ${isAgentThinking ? 'bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-paper text-ink/40'}`}>
                <div className="flex items-center gap-3 px-2">
                  {isAgentThinking ? <Loader2 size={20} strokeWidth={3} className="animate-spin text-terracotta" /> : <Clock size={20} strokeWidth={3} className="text-ink/30" />}
                  <span className="font-black text-sm tracking-widest uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                    {isAgentThinking ? 'Processing...' : 'Dozing...'}
                  </span>
                  {isAgentThinking && (
                    <button
                      onClick={handleForceInterrupt}
                      className="ml-1 p-0.5 text-terracotta hover:text-ink transition-colors"
                      title="暂停：物理掐断正在执行的工具（长时请求/死循环命令）"
                    >
                      <Pause size={18} strokeWidth={3} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} className="h-2" />
        </div>

        <FileChangesPanel {...fileViewProps} />

        <TerminalPanel showTerminal={showTerminal} setShowTerminal={setShowTerminal} command={terminalCmd} />

        {currentBranchId === 'main' ? (
          <div className={`${(showBrowser || showIDE) ? 'px-4 pb-4' : 'px-10 pb-8'} pt-4 shrink-0 flex flex-col gap-3 w-full`}>
           {(selectedSkills.length > 0 || selectedMcps.length > 0 || selectedGraphs.length > 0 || refPaths.length > 0 || useBrainstorm) && (
             <div className="flex flex-wrap gap-2">
               {selectedSkills.map(skill => <div key={skill} style={sketchyShape3} className="flex items-center gap-1 bg-[#F9E2AF] border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"><span>⚡ {skill}</span><button onClick={() => setSelectedSkills(prev => prev.filter(s => s !== skill))} className="hover:text-terracotta ml-1"><X size={14} strokeWidth={3}/></button></div>)}
               {refPaths.map(path => <div key={path} style={sketchyShape1} className="flex items-center gap-1 bg-[#88c0d0] border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"><span className="truncate max-w-[200px]">📎 {path}</span><button onClick={() => setRefPaths(prev => prev.filter(p => p !== path))} className="hover:text-paper ml-1"><X size={14} strokeWidth={3}/></button></div>)}
               {useBrainstorm && <div style={sketchyShape2} className="flex items-center gap-1 bg-[#b48ead] border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"><span className="text-paper">🧠 BrainStorm</span><button onClick={() => setUseBrainstorm(false)} className="hover:text-ink text-paper ml-1"><X size={14} strokeWidth={3}/></button></div>}
               {selectedMcps.map(mcp => <div key={mcp} style={sketchyShape2} className="flex items-center gap-1 bg-[#88c0d0]/20 border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"><span className="text-ink">🔌 {mcp}</span><button onClick={() => setSelectedMcps(prev => prev.filter(s => s !== mcp))} className="hover:text-terracotta ml-1 text-ink/50 transition-colors"><X size={14} strokeWidth={3}/></button></div>)}
               {selectedGraphs.map(graph => <div key={graph} style={sketchyShape2} className="flex items-center gap-1 bg-ink text-paper border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"><span>🕸️ {graph}</span><button onClick={() => setSelectedGraphs(prev => prev.filter(s => s !== graph))} className="hover:text-terracotta ml-1 text-paper/50 transition-colors"><X size={14} strokeWidth={3}/></button></div>)}
             </div>
           )}

           {!showFileView && !showTerminal && (
           <div className={`flex gap-4 relative transition-all ${isDragging ? 'ring-4 ring-terracotta bg-terracotta/5' : ''}`} onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={handleDrop}>
             {isDragging && <div className="absolute inset-0 z-50 flex items-center justify-center bg-cream/90 border-4 border-dashed border-terracotta" style={sketchyShape2}><span className="text-2xl font-black text-terracotta">Drop files here to attach!</span></div>}
             <div className="flex-1 relative flex flex-col">
               <textarea ref={chatInputRef} style={sketchyShape3} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }} onPaste={handlePaste} placeholder={currentSessionId ? "Write your prompt here..." : "Select a chat first!"} disabled={!currentSessionId} rows={2} className="w-full bg-[#FDF8F0] border-4 border-ink p-5 pr-40 font-bold focus:outline-none resize-none text-lg -rotate-[0.5deg] placeholder:text-ink/30" />
               <div className="absolute right-3 bottom-3 flex items-center gap-2 z-10">
                 {/* 展开的工具菜单 */}
                 {showToolMenu && (
                   <div className="absolute bottom-full right-0 mb-3 w-56 bg-paper border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col p-1 z-20 animate-in slide-in-from-bottom-2 fade-in duration-200" style={sketchyShape3}>

                     <button onClick={() => { setShowToolMenu(false); if (Object.keys(mcpData).length === 0) fetchMcp(); setTempSelectedMcps([...selectedMcps]); setShowMcpSelectModal(true); }} className="flex items-center gap-3 p-3 hover:bg-[#F9E2AF] font-black text-sm text-left transition-all active:translate-y-1" style={sketchyShape1}>
                       <Server size={18} strokeWidth={3}/> MCP Tool
                     </button>

                     <button onClick={() => { setShowToolMenu(false); if (skillData.length === 0) fetchSkill(); setTempSelectedSkills([...selectedSkills]); setShowSkillSelectModal(true); }} className="flex items-center gap-3 p-3 hover:bg-[#F9E2AF] font-black text-sm text-left transition-all active:translate-y-1" style={sketchyShape2}>
                       <Zap size={18} strokeWidth={3}/> Skill
                     </button>

                     <button onClick={() => { setShowToolMenu(false); handleAttachmentClick('file'); }} className="flex items-center gap-3 p-3 hover:bg-[#88c0d0] hover:text-paper font-black text-sm text-left transition-all active:translate-y-1" style={sketchyShape1}>
                       <Paperclip size={18} strokeWidth={3}/> 选择文件
                     </button>

                     <button onClick={() => { setShowToolMenu(false); handleAttachmentClick('directory'); }} className="flex items-center gap-3 p-3 hover:bg-[#88c0d0] hover:text-paper font-black text-sm text-left transition-all active:translate-y-1" style={sketchyShape1}>
                       <FolderOpen size={18} strokeWidth={3}/> 选择文件夹
                     </button>

                     <button onClick={() => { setShowToolMenu(false); setUseBrainstorm(!useBrainstorm); }} className={`flex items-center gap-3 p-3 font-black text-sm text-left transition-all active:translate-y-1 ${useBrainstorm ? 'bg-[#b48ead] text-paper' : 'hover:bg-[#b48ead] hover:text-paper'}`} style={sketchyShape2}>
                       <Brain size={18} strokeWidth={3}/> BrainStorm Mode {useBrainstorm && ' (ON)'}
                     </button>

                     <button onClick={() => { setShowToolMenu(false); if (graphData.length === 0) fetchGraphData(); setTempSelectedGraphs([...selectedGraphs]); setShowGraphSelectModal(true); }} className="flex items-center gap-3 p-3 hover:bg-ink hover:text-paper font-black text-sm text-left transition-all active:translate-y-1" style={sketchyShape3}>
                       <GitMerge size={18} strokeWidth={3}/> Task Graph
                     </button>

                   </div>
                 )}

                 {/* 统一的展开/收纳按钮 */}
                 <button
                   onClick={() => setShowToolMenu(!showToolMenu)}
                   className={`p-2 border-2 border-ink transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] ${showToolMenu ? 'bg-terracotta text-paper' : 'bg-cream text-ink hover:bg-sand'}`}
                   style={sketchyShape1}
                   title="More Tools"
                 >
                   {/* 点击后十字架旋转45度变成一个 X 按钮，手感会更好 */}
                   <Plus size={24} strokeWidth={3} className={`transition-transform duration-300 ${showToolMenu ? 'rotate-45' : ''}`}/>
                 </button>
               </div>
             </div>
            {/* 🌟 只有在非浏览器/IDE模式下才渲染发送按钮 */}
            {!showBrowser && !showIDE && (
              <button style={sketchyShape1} onClick={handleSend} disabled={!currentSessionId || !input.trim()} className="bg-ink text-paper px-10 font-black flex items-center gap-3 border-4 border-ink hover:bg-terracotta hover:text-ink shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] rotate-2 min-h-[80px] self-end">
                <Send size={26} strokeWidth={2.5} />
              </button>
            )}
          </div>
           )}
        </div>
          ) : (
            <div className="px-10 pb-8 pt-4 shrink-0 flex justify-center w-full"><div style={sketchyShape3} className="bg-cream border-4 border-ink px-10 py-5 font-black text-ink/50 tracking-widest uppercase flex items-center gap-3">🔒 READ-ONLY SUB-BRANCH VIEW</div></div>
          )}
      </div>

      {showBrowser && !browserDetached && (
        <div className="flex-1 overflow-hidden animate-in slide-in-from-right-4 duration-300">
          <AgentBrowserPanel
            tabs={browserTabs}
            setTabs={setBrowserTabs}
            activeTabId={activeTabId}
            setActiveTabId={setActiveTabId}
            mode={browserMode}
            setMode={setBrowserMode}
            onComment={handleBrowserComment}
            onDetach={() => {
              // 👇 重点修复：在分离窗口前，先将主窗口状态重置为 browse，
              // 这会触发 AgentBrowserPanel 的 useEffect 清理工作
              setBrowserMode('browse');

              (window as any).purrcat?.browserDetach();
              setBrowserDetached(true);
              setShowBrowser(false);
            }}
          />
        </div>
      )}

      {/* 右侧渲染 IDE 面板 */}
      {showIDE && ideWorkspace && (
        <div className="flex-1 overflow-hidden animate-in slide-in-from-right-8 duration-300">
          <IDEPanel
            workspacePath={ideWorkspace}
            onClose={() => setShowIDE(false)}
            onOpenLink={handleRawLinkClick}
          />
        </div>
      )}

      <RequestQueuePanel {...queueProps} />

      {/* 🌟 专属心跳配置弹窗 */}
      {showHeartbeatModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a] flex items-center gap-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                <Heart size={24} className="animate-pulse"/> HEARTBEAT
              </h3>
              <button onClick={() => setShowHeartbeatModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            
            <div className="rotate-1 flex flex-col gap-4">
              <p className="text-sm font-bold opacity-70">Agent Subconscious Frequency（最短 60 秒）</p>

              {/* 秒数输入与拨键开关合并在一行 */}
              <div className="flex items-center justify-between gap-4 bg-cream border-4 border-ink p-3 shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3}>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={60}
                    value={heartbeatConfig.interval}
                    onChange={e => setHeartbeatConfig({...heartbeatConfig, interval: Math.max(60, parseInt(e.target.value) || 60)})}
                    className="w-20 bg-transparent font-black text-xl text-center focus:outline-none"
                  />
                  <span className="font-bold opacity-60">SECONDS</span>
                </div>

                {/* 纯净的粗线条 Sensor 风格拨键开关 */}
                <div
                  onClick={() => setHeartbeatConfig({...heartbeatConfig, active: !heartbeatConfig.active})}
                  className={`relative w-16 h-8 border-4 border-ink cursor-pointer transition-colors shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center shrink-0 active:translate-y-px active:shadow-none ${heartbeatConfig.active ? 'bg-[#a3be8c]' : 'bg-ink/20'}`}
                  style={sketchyShape2}
                >
                  <div className={`absolute w-5 h-5 bg-paper border-4 border-ink transition-transform duration-200 ${heartbeatConfig.active ? 'translate-x-8' : 'translate-x-1'}`} style={sketchyShape1} />
                </div>
              </div>

              {/* GOAL.md 内容编辑区：开启心跳时必填，随心跳一并提交 */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-black flex items-center gap-1"><List size={16} strokeWidth={3}/> GOAL.md（开启心跳必填）</p>
                  <button
                    onClick={() => { setShowHeartbeatModal(false); openMdEditor('GOAL'); }}
                    className="text-xs font-black underline underline-offset-4 hover:text-terracotta"
                  >
                    大窗口编辑
                  </button>
                </div>
                <textarea
                  value={heartbeatConfig.goal}
                  onChange={e => setHeartbeatConfig({...heartbeatConfig, goal: e.target.value})}
                  placeholder="写入当前目标，心跳将按间隔注入给 Agent..."
                  className="w-full h-28 bg-[#FDF8F0] border-4 border-ink p-2 text-sm font-bold resize-none focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]"
                  style={sketchyShape2}
                />
              </div>
            </div>

            <button onClick={saveHeartbeat} style={sketchyShape2} className="mt-2 w-full bg-[#bf616a] text-paper font-black py-4 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 rotate-1 text-xl tracking-widest">
              SAVE CONFIG
            </button>
          </div>
        </div>
      )}

      {/* 🌟 内嵌链接/文件预览弹窗（保留原手绘风格，按类型渲染 img/video/iframe） */}
      {previewUrl && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4" onClick={() => setPreviewUrl(null)}>
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-6xl h-[85vh]" onClick={e => e.stopPropagation()}>

            {/* 弹窗头部 */}
            <div className="flex justify-between items-center border-b-4 border-ink/20 pb-4 shrink-0">
              <div className="flex items-center gap-3 overflow-hidden flex-1">
                <ExternalLink size={28} className="text-[#3498DB] shrink-0" strokeWidth={2.5} />
                <h3 className="text-xl font-black tracking-widest text-ink truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  {previewRawUrl}
                </h3>
              </div>

              <div className="flex items-center gap-4 shrink-0 ml-4">
                {/* 外部浏览器打开兜底按钮：显式走 shell.openExternal 唤起系统浏览器 */}
                <button onClick={() => { const full = window.location.origin + previewUrl; if ((window as any).purrcat?.openExternal) (window as any).purrcat.openExternal(full); else window.open(full, '_blank'); }} className="flex items-center gap-2 p-2 px-4 bg-cream border-4 border-ink hover:bg-[#3498DB] hover:text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all font-black text-sm active:translate-y-1 active:shadow-none" title="Open in Browser" style={sketchyShape1}>
                  OPEN EXTERNALLY <ExternalLink size={16} strokeWidth={3} />
                </button>
                <button onClick={() => setPreviewUrl(null)} className="hover:text-terracotta hover:scale-110 transition-all">
                  <X size={32} strokeWidth={3} />
                </button>
              </div>
            </div>

            {/* 预览区：按类型渲染 */}
            <div className="flex-1 overflow-auto border-4 border-ink bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] relative flex items-center justify-center">
              {previewType === 'image' && (
                <img src={previewUrl} alt="Preview" className="max-w-full max-h-full object-contain" />
              )}
              {previewType === 'video' && (
                <video src={previewUrl} controls autoPlay className="max-w-full max-h-full" />
              )}
              {previewType === 'browser' && (
                <iframe
                  src={previewUrl}
                  className="w-full h-full border-none"
                  title="Link Preview"
                  sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                />
              )}
              {previewType === 'markdown' && (
                <div
                  className="w-full h-full overflow-auto p-6 text-left"
                  onClick={(e) => {
                    // 拦截 md 预览内的链接：复用统一链接路由（http→内置浏览器 / 本地→预览）
                    const a = (e.target as HTMLElement).closest('a');
                    if (a) {
                      e.preventDefault();
                      const h = a.getAttribute('href') || '';
                      if (h) handleRawLinkClick(h);
                    }
                  }}
                >
                  {previewMdContent === null ? (
                    <div className="font-black text-ink/40 animate-pulse tracking-widest">LOADING MARKDOWN...</div>
                  ) : (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={MdPreviewComponents}
                      urlTransform={allowFileUrlTransform}
                    >
                      {previewMdContent}
                    </ReactMarkdown>
                  )}
                </div>
              )}
            </div>

          </div>
        </div>
      )}

      {/* 🌟 term:// 命令确认弹窗 */}
      {pendingTermCmd && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4" onClick={() => setPendingTermCmd(null)}>
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 border-b-4 border-ink/20 pb-4">
              <AlertTriangle size={32} className="text-[#d08770] shrink-0" strokeWidth={2.5} />
              <h3 className="text-xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                CONFIRM EXECUTION
              </h3>
            </div>

            <div className="flex flex-col gap-3">
              <p className="text-ink font-bold text-sm">
                确认在主机运行以下命令吗？
              </p>
              <div className="flex items-start gap-2 p-4 bg-[#bf616a]/10 border-2 border-[#bf616a] text-ink text-xs font-bold" style={sketchyShape3}>
                <AlertTriangle size={16} className="text-[#bf616a] shrink-0 mt-0.5" strokeWidth={3} />
                <span>
                  <span className="text-[#bf616a] font-black">⚠ 风险提示：</span>
                  此命令将在你的主机上以子进程方式执行，拥有完整的系统访问权限。
                  请确认你信任 Agent 的输出，且理解该命令的作用。
                  执行后可在终端中继续交互输入。
                </span>
              </div>
              <div className="p-4 bg-[#1e1e2e] border-4 border-ink font-mono text-sm text-[#cdd6f4] break-all" style={sketchyShape1}>
                <span className="text-[#a3be8c]">$</span> {pendingTermCmd}
              </div>
            </div>

            <div className="flex gap-4 justify-end">
              <button
                onClick={() => setPendingTermCmd(null)}
                className="px-6 py-3 bg-cream text-ink font-black border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand active:translate-y-1 active:shadow-none transition-all"
                style={sketchyShape2}
              >
                CANCEL
              </button>
              <button
                onClick={() => {
                  setTerminalCmd(pendingTermCmd);
                  setShowFileView(false);
                  setShowTerminal(true);
                  setPendingTermCmd(null);
                }}
                className="px-6 py-3 bg-[#a3be8c] text-ink font-black border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all flex items-center gap-2"
                style={sketchyShape1}
              >
                <TerminalSquare size={18} strokeWidth={3} />
                RUN IN TERMINAL
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}