// src/components/ChatPage.tsx
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, Cat, Clock, Activity, Server, Zap, Brain, GitMerge, Loader2, FolderOpen, Bell, Paperclip, X, Heart, User, List, ExternalLink, Plus, BookOpen, ClipboardCopy, TerminalSquare, AlertTriangle, Globe } from 'lucide-react';
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
import { parseEventsContent, hasMessageInHistory, renderSketchyHeatmap, MarkdownComponents, ToolCallBubble, ToolMessageBubble, sketchyShape1, sketchyShape2, sketchyShape3 } from './chat/ChatShared';
import ChatModals from './chat/ChatModals';
import ChatSidebar from './chat/ChatSidebar';
import { FileChangesPanel, RequestQueuePanel, TerminalPanel } from './chat/ChatPanels';
import AgentBrowserPanel from './chat/AgentBrowserPanel';
import ConfigModal from './ConfigModal';

// 🌟 多标签页类型定义
export type BrowserTab = { id: string; url: string; title: string };

export default function ChatPage({ onBack, onSwitchToTask }: { onBack: () => void; onSwitchToTask?: () => void }) {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();

  const [input, setInput] = useState('');
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
  
  const [skillData, setSkillData] = useState<any[]>([]);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  
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
  const [heartbeatConfig, setHeartbeatConfig] = useState({ interval: 1800, active: true });

  // --- 新增：内置浏览器状态（多标签页） ---
  const [showBrowser, setShowBrowser] = useState(false);
  const [browserMode, setBrowserMode] = useState<'browse' | 'pick' | 'draw'>('browse');
  const [browserTabs, setBrowserTabs] = useState<BrowserTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  // 🌟 挂载时拉取现有的心跳配置
  const fetchAgentHeartbeat = async () => {
    try {
      const res = await fetch('/api/tools/loop');
      if (res.ok) {
        const loops = await res.json();
        const agentLoop = loops.find((l: any) => l.task_hook === 'Agent');
        if (agentLoop) {
          setHeartbeatConfig({ interval: agentLoop.interval, active: agentLoop.active });
        }
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

  // 🌟 保存心跳配置
  const saveHeartbeat = async () => {
    try {
      const res = await fetch('/api/tools/loop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: '系统心跳',
          interval: heartbeatConfig.interval,
          task_hook: 'Agent',
          task_inputs: {},
          active: heartbeatConfig.active
        })
      });
      if (res.ok) {
        toast.success("Agent 潜意识心跳已更新！");
        setShowHeartbeatModal(false);
      }
    } catch { toast.error("心跳更新失败"); }
  };

  const [showMdModal, setShowMdModal] = useState(false);
  const [showToolMenu, setShowToolMenu] = useState(false);
  const [mdType, setMdType] = useState<'SOUL' | 'SOLO' | 'TODO'>('SOUL');
  const [mdContent, setMdContent] = useState('');
  const [isSavingMd, setIsSavingMd] = useState(false);

  // 🌟 链接预览状态：type 决定弹窗用 img/video/iframe 渲染
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'video' | 'browser'>('browser');
  const [previewRawUrl, setPreviewRawUrl] = useState<string>('');

  // 🌟 全局拦截气泡内的链接点击事件：本地路径走 FastAPI 代理，http/https 走 iframe
  const handleMessageClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    const anchor = target.closest('a');
    if (!anchor) return;

    // ⚠️ 必须用 getAttribute('href') 拿到 Agent 原始输出的字符串
    // anchor.href 是浏览器规范化后的 URL，会把 D:/xxx.png 变成 http://localhost:3000/chat/D:/xxx.png
    const rawHref = anchor.getAttribute('href') || '';
    if (!rawHref) return;

    e.preventDefault();

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
    let finalUrl = rawHref;

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
      localPath = p;
    }
    // 2. Agent 沙盒路径: /agent_vm/xxx or ./agent_vm/xxx
    else if (rawHref.startsWith('/agent_vm/') || rawHref === '/agent_vm' ||
             rawHref.startsWith('./agent_vm/') || rawHref === './agent_vm' ||
             rawHref.startsWith('../agent_vm/')) {
      localPath = rawHref; // 后端 resolve_absolute_path 会处理
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
      if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
        type = 'image';
      } else if (['mp4', 'webm', 'mov', 'ogg'].includes(ext)) {
        type = 'video';
      } else {
        // 其他本地文件：兜底用 browser 渲染（/preview 返回 FileResponse，iframe 会显示或触发下载）
        type = 'browser';
      }
      finalUrl = `/api/filesystem/preview?path=${encodeURIComponent(localPath)}`;
    }

    // 🌟 browser 类型直接在内置浏览器中打开（图片/视频仍走弹窗）
    if (type === 'browser') {
      openInBrowser(finalUrl, rawHref.split('/').pop() || rawHref);
      return;
    }

    setPreviewType(type);
    setPreviewRawUrl(rawHref);
    setPreviewUrl(finalUrl);
  };

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
  
  // 🌟 恢复原版滚动监听逻辑
  const handleScroll = () => { if (!messagesContainerRef.current) return; const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current; isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 50; };
  useEffect(() => { if (isAutoScroll.current) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => { pendingMsgsRef.current = []; }, [currentBranchId]);
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
      try { realPath = purrcat.getPathForFile(file); } catch (_) { realPath = null; }
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

  const openMdEditor = async (type: 'SOUL' | 'SOLO' | 'TODO') => { setMdType(type); setMdContent('Loading...'); setShowMdModal(true); try { const res = await fetch(`/api/config/markdown/${type}`); if (res.ok) { const data = await res.json(); setMdContent(data.content); } } catch { /* noop */ } };
  const saveMdContent = async () => { setIsSavingMd(true); try { const res = await fetch(`/api/config/markdown/${mdType}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: mdContent }) }); if (res.ok) setShowMdModal(false); } catch { /* noop */ } finally { setIsSavingMd(false); } };

  const fetchSensorData = async () => { try { const res = await fetch('/api/config/sensor'); if (res.ok) setSensorData(await res.json()); } catch { /* noop */ } };
  const reloadSensors = async () => { try { await fetch('/api/config/sensor/reload', { method: 'POST' }); toast.success("Sensors 已热重启"); } catch { /* noop */ } };
  const toggleSensorStatus = async (sensorName: string) => { try { const newSensorData = JSON.parse(JSON.stringify(sensorData)); newSensorData[sensorName].enabled = !newSensorData[sensorName].enabled; setSensorData(newSensorData); const resSave = await fetch('/api/config/sensor', { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(newSensorData) }); if (resSave.ok) await reloadSensors(); } catch { /* noop */ } };
  const handleInstallSensor = async () => { setIsInstallingSensor(true); try { const parsed = JSON.parse(sensorInstallJson); const newSensors = parsed.sensors ? parsed.sensors : parsed; const currentData = JSON.parse(JSON.stringify(sensorData)); Object.assign(currentData, newSensors); const resSave = await fetch('/api/config/sensor', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentData) }); if (resSave.ok) { await reloadSensors(); setShowInstallSensorModal(false); fetchSensorData(); } } catch { /* noop */ } finally { setIsInstallingSensor(false); } };

  const fetchMcp = async () => { try { const res = await fetch('/api/tools/mcp'); if (res.ok) setMcpData(await res.json()); } catch { /* noop */ } };
  const refreshMcp = async () => { try { await fetch('/api/tools/mcp/refresh', { method: 'POST' }); fetchMcp(); } catch { /* noop */ } };
  const handleInstallMcp = async () => { setIsInstallingMcp(true); try { const res = await fetch('/api/tools/mcp/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ config_json: mcpInstallJson.trim() }) }); if (res.ok) { setShowInstallMcpModal(false); fetchMcp(); } } catch { /* noop */ } finally { setIsInstallingMcp(false); } };

  const fetchSkill = async () => { try { const res = await fetch('/api/tools/skills'); if (res.ok) setSkillData(await res.json()); } catch { /* noop */ } };
  const refreshSkill = async () => { try { await fetch('/api/tools/skills/refresh', { method: 'POST' }); fetchSkill(); } catch { /* noop */ } };
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
          setMessages(newMessages);
        }
        if (statusRes.ok) { const statusData = await statusRes.json(); setIsAgentThinking(statusData.is_thinking); loadBranches(currentSessionId); }
      } catch { /* noop */ }
    }, 1500);
    return () => clearInterval(interval);
  }, [currentSessionId, currentBranchId, isCheckingOut]);

  const handleSelectSession = async (id: string) => { setIsCheckingOut(true); setCurrentSessionId(id); setCurrentBranchId('main'); navigate(`/chat/${id}`, { replace: true }); try { await fetch(`/api/sessions/${id}/checkout`, { method: 'POST' }).catch(() => {}); await loadSessionHistory(id, 'main'); await loadBranches(id); } catch { /* noop */ } finally { setIsCheckingOut(false); } };
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
      } catch (_) { /* 非 Electron 环境，用临时 id */ }
      const newTab: BrowserTab = { id: tabId, url, title };
      setBrowserTabs(prev => [...prev, newTab]);
      setActiveTabId(newTab.id);
    }
    setShowBrowser(true);
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
          is_upgrade: traceType === 'upgrade'
        })
      });

      if (!res.ok) throw new Error("分配沙盒失败");
      const data = await res.json();
      const wp_id = data.workplace_id;
      const factoryPath = `./agent_vm/skill_workplace/${wp_id}/${traceSkillName.trim()}`;

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
          setRefPaths((prev: string[]) => [...new Set([...prev, ...paths])]);
          toast.success(`已添加 ${paths.length} 个本地绝对路径`);
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
    showSessionModal, setShowSessionModal, isAgentThinking, sessions, handleSelectSession, editingSessionId, editingAlias, setEditingAlias, setEditingSessionId, handleRename,
    showTraceModal, setShowTraceModal, traceType, setTraceType, traceSkillName, setTraceSkillName, traceExpectation, setTraceExpectation, confirmTraceToSkill, isTracing
  };

  const sidebarProps = {
    onBack, onSwitchToTask, setShowSessionModal, navigate,
    sidebarMode, setSidebarMode,
    sensorData, toggleSensorStatus, reloadSensors, setShowInstallSensorModal, fetchSensorData,
    mcpData, expandedMcp, setExpandedMcp, refreshMcp, setShowInstallMcpModal, fetchMcp,
    skillData, expandedSkill, setExpandedSkill, refreshSkill, setShowInstallSkillModal, fetchSkill,
    cronData, deleteCron, setShowAddCronModal, fetchCron,
    openMdEditor, graphData, fetchGraphData  // 🌟 追加这两个！
  };

  const fileViewProps = { showFileView, setShowFileView, fileChanges, activeDiffPath, setActiveDiffPath, handleAck, handleRollback };
  const queueProps = { showReqQueue, setShowReqQueue, pendingReqs, handleResolveReq, feedbackInputs, setFeedbackInputs, authDurations, setAuthDurations, expandedReasons, setExpandedReasons };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">

      {/* 无标题栏窗口的顶部拖拽区：拖动此处移动窗口。右上角的最小/最大/关闭按钮由 titleBarOverlay 提供 */}
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 28, WebkitAppRegion: 'drag', zIndex: 40 } as React.CSSProperties} />

      <ChatModals {...modalProps} />
      <ConfigModal isOpen={isConfigOpen} onClose={() => setIsConfigOpen(false)} />
      
      {!showBrowser && !isCompact && <ChatSidebar {...sidebarProps} />}

      {/* 🌟 聊天框动态压缩：改为 w-[420px] 增加宽度 */}
      <div style={sketchyShape1} className={`${showBrowser ? 'w-[420px] shrink-0' : 'flex-1'} transition-all duration-300 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-10`}>
        
        {currentSessionId ? (
          <div className="absolute -top-2 right-12 px-6 py-1 bg-[#a3be8c] border-2 border-ink rotate-2 z-50 text-ink font-black text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center" style={sketchyShape2} title="Session ID">
            ID: {currentSessionId.split('_')[1] || currentSessionId.slice(-8)}
          </div>
        ) : <div className="absolute -top-4 right-12 w-32 h-8 bg-[#a3be8c]/80 border-2 border-ink -rotate-3 z-50" style={sketchyShape2}></div>}

        {!showBrowser ? (
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

               <button onClick={() => setShowBrowser(!showBrowser)} className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center ${showBrowser ? 'bg-[#88c0d0] text-paper' : 'bg-cream text-ink'}`} style={sketchyShape3} title="内置浏览器">
                 <Globe size={20} strokeWidth={3} />
               </button>
            </div>
          </div>
        ) : (
          <div className="pt-6 px-6 pb-2 flex justify-between items-center shrink-0 border-b-4 border-ink/10">
            <h2 className="text-2xl font-black tracking-tighter text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat.</h2>
            <button onClick={() => setShowBrowser(false)} className="p-1.5 border-2 border-ink hover:bg-[#bf616a] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all" style={sketchyShape2}>
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

        {/* 🌟 恢复原版消息渲染映射 (.map)，加上 onClick 拦截点击 */}
        <div ref={messagesContainerRef} onScroll={handleScroll} onClick={handleMessageClick} className={`flex-1 overflow-y-auto ${showBrowser ? 'px-4' : 'px-10'} pb-6 flex flex-col gap-6 w-full z-10 pt-4`}>
          {messages.length === 0 && !showBrowser ? (
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
            messages.map((msg, idx) => {
              if (msg.role === 'user') {
                const parsedData = parseEventsContent(msg.content);
                return (
                  <div key={idx} className="flex flex-col w-full items-end mb-4">
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
                return <div key={idx} className="flex w-full justify-start"><ToolMessageBubble msg={msg} /></div>;
              } else {
                return (
                  <div key={idx} className="flex w-full justify-start">
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
                      {msg.role === 'assistant' && idx === messages.length - 1 && !isAgentThinking && (
                        <div className="flex justify-end mt-3 animate-in fade-in duration-300">
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
                        </div>
                      )}
                      {msg.tool_calls && msg.tool_calls.map((tc: any, tIdx: number) => <ToolCallBubble key={`tc-${tIdx}`} tc={tc} />)}
                    </div>
                  </div>
                );
              }
            })
          )}
          {currentBranchId === 'main' && messages.length > 0 && (
            <div className="flex justify-start mb-4 w-full">
              <div style={sketchyShape1} className={`p-4 w-fit transition-colors ${isAgentThinking ? 'bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-paper text-ink/40'}`}>
                <div className="flex items-center gap-3 px-2">
                  {isAgentThinking ? <Loader2 size={20} strokeWidth={3} className="animate-spin text-terracotta" /> : <Clock size={20} strokeWidth={3} className="text-ink/30" />}
                  <span className="font-black text-sm tracking-widest uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                    {isAgentThinking ? 'Processing...' : 'Dozing...'}
                  </span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} className="h-2" />
        </div>

        <FileChangesPanel {...fileViewProps} />

        <TerminalPanel showTerminal={showTerminal} setShowTerminal={setShowTerminal} command={terminalCmd} />

        {currentBranchId === 'main' ? (
          <div className={`${showBrowser ? 'px-4 pb-4' : 'px-10 pb-8'} pt-4 shrink-0 flex flex-col gap-3 w-full`}>
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
               <textarea style={sketchyShape3} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }} onPaste={handlePaste} placeholder={currentSessionId ? "Write your prompt here..." : "Select a chat first!"} disabled={!currentSessionId} rows={2} className="w-full bg-[#FDF8F0] border-4 border-ink p-5 pr-40 font-bold focus:outline-none resize-none text-lg -rotate-[0.5deg] placeholder:text-ink/30" />
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
            {/* 🌟 只有在非浏览器模式下才渲染发送按钮（浏览器模式用回车发送） */}
            {!showBrowser && (
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

      {showBrowser && (
        <div className="flex-1 overflow-hidden animate-in slide-in-from-right-4 duration-300">
          <AgentBrowserPanel 
            tabs={browserTabs}
            setTabs={setBrowserTabs}
            activeTabId={activeTabId}
            setActiveTabId={setActiveTabId}
            mode={browserMode}
            setMode={setBrowserMode}
            onComment={handleBrowserComment}
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
              <p className="text-sm font-bold opacity-70">Agent Subconscious Frequency</p>

              {/* 秒数输入与拨键开关合并在一行 */}
              <div className="flex items-center justify-between gap-4 bg-cream border-4 border-ink p-3 shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3}>
                <div className="flex items-center gap-2">
                  <input 
                    type="number" 
                    value={heartbeatConfig.interval} 
                    onChange={e => setHeartbeatConfig({...heartbeatConfig, interval: parseInt(e.target.value) || 60})} 
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

              {/* 底部收编的 SOLO.md 与 TODO.md 按钮 */}
              <div className="flex gap-4 mt-2">
                <button 
                  onClick={() => { setShowHeartbeatModal(false); openMdEditor('SOLO'); }} 
                  style={sketchyShape3} 
                  className="flex-1 border-4 border-ink bg-[#88c0d0] text-paper font-black py-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#72a6b5] active:translate-y-1 active:shadow-none transition-all flex items-center justify-center gap-2" 
                >
                  <User size={20} strokeWidth={3}/> SOLO.md
                </button>
                <button 
                  onClick={() => { setShowHeartbeatModal(false); openMdEditor('TODO'); }} 
                  style={sketchyShape1} 
                  className="flex-1 border-4 border-ink bg-[#EBCB8B] text-ink font-black py-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#d8b877] active:translate-y-1 active:shadow-none transition-all flex items-center justify-center gap-2" 
                >
                  <List size={20} strokeWidth={3}/> TODO.md
                </button>
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
                {/* 外部浏览器打开兜底按钮 */}
                <a href={previewUrl} target="_blank" rel="noreferrer" className="flex items-center gap-2 p-2 px-4 bg-cream border-4 border-ink hover:bg-[#3498DB] hover:text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all font-black text-sm active:translate-y-1 active:shadow-none" title="Open in Browser" style={sketchyShape1}>
                  OPEN EXTERNALLY <ExternalLink size={16} strokeWidth={3} />
                </a>
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