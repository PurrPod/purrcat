import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, Send, Cat, Clock, Wrench, Package, 
  ChevronDown, ChevronUp, Loader2, X, Trash2, 
  List, Brain, Server, Zap, AlarmClock, GitFork, Plus,
  RefreshCw, Terminal, User, FileText, Save,
  Settings, FileJson, AlertCircle, Download, Activity, Paperclip, Bell,
  FolderOpen, History, Undo2, CheckCircle
} from 'lucide-react';
import { toast } from 'react-hot-toast';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
  tool_calls?: any[];
}

interface EventItem {
  type: string;
  time: string;
  content: string;
}

function parseEventsContent(content: string): { userMessages: EventItem[], systemCount: number, attachments: EventItem[] } {
  const userMessages: EventItem[] = [];
  const attachments: EventItem[] = [];
  let systemCount = 0;
  
  try {
    const data = JSON.parse(content);
    if (data.events && Array.isArray(data.events)) {
      for (const event of data.events) {
        const eventType = event.type || '';
        const eventContent = event.content || '';
        const eventTime = event.time || '';
        
        if (eventType === 'user') {
          userMessages.push({ type: eventType, time: eventTime, content: eventContent });
        } else if (eventType === 'file-quote' || eventType === 'skill-quote') {
          attachments.push({ type: eventType, time: eventTime, content: eventContent });
        } else {
          systemCount++;
        }
      }
    }
  } catch {
    userMessages.push({ type: 'user', time: '', content });
  }
  
  return { userMessages, systemCount, attachments };
}

function hasMessageInHistory(history: any[], text: string) {
  for (let i = history.length - 1; i >= 0; i--) {
    const msg = history[i];
    if (msg.role === 'user') {
      if (msg.content === text) return true;
      const parsed = parseEventsContent(msg.content);
      if (parsed.userMessages.some((u: EventItem) => u.content === text)) {
        return true;
      }
    }
  }
  return false;
}

interface Session { id: string; alias: string; messages_count: number; updated_at: string; }

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

const MarkdownComponents: any = {
  p: ({ ...props }: any) => <p className="mb-3 last:mb-0 leading-relaxed" {...props} />,
  a: ({ ...props }: any) => <a className="text-[#3498DB] underline decoration-2 decoration-ink hover:text-terracotta transition-colors font-black" {...props} />,
  ul: ({ ...props }: any) => <ul className="list-disc pl-6 mb-3 space-y-2 font-bold marker:text-terracotta" {...props} />,
  ol: ({ ...props }: any) => <ol className="list-decimal pl-6 mb-3 space-y-2 font-bold marker:text-terracotta" {...props} />,
  li: ({ ...props }: any) => <li className="pl-1" {...props} />,
  h1: ({ ...props }: any) => <h1 className="text-2xl font-black mb-4 mt-2 border-b-4 border-ink inline-block pb-1" {...props} />,
  h2: ({ ...props }: any) => <h2 className="text-xl font-black mb-3 mt-2" {...props} />,
  h3: ({ ...props }: any) => <h3 className="text-lg font-black mb-2 mt-2" {...props} />,
  strong: ({ ...props }: any) => <strong className="font-black text-terracotta" {...props} />,
  blockquote: ({ ...props }: any) => (
    <blockquote className="border-l-4 border-terracotta pl-4 py-1 italic text-ink/70 my-3 bg-terracotta/5 rounded-r-lg" {...props} />
  ),
  pre: ({ ...props }: any) => (
    <pre className="my-4 border-4 border-ink bg-ink/5 text-ink p-4 overflow-x-auto shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] font-mono text-sm leading-relaxed font-bold" style={sketchyShape2} {...props} />
  ),
  code: ({ className, children, ...props }: any) => {
    const isInline = props.inline !== false && !className?.includes('language-') && !String(children).includes('\n');
    return isInline ? (
      <code className="bg-ink/10 text-terracotta px-1.5 py-0.5 border-2 border-ink mx-1 font-black text-[0.9em]" style={sketchyShape3} {...props}>
        {children}
      </code>
    ) : (
      <code className={className} {...props}>{children}</code>
    );
  }
};

const ToolMessageBubble = ({ msg }: { msg: Message }) => {
  const [expanded, setExpanded] = useState(false);
  const contentStr = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);

  if (!expanded) {
    return (
      <div onClick={() => setExpanded(true)} style={sketchyShape3} className="w-fit max-w-[250px] p-2 px-4 border-2 border-ink bg-[#a3be8c]/30 text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] mb-2 flex items-center justify-between gap-3 cursor-pointer hover:bg-[#a3be8c]/60 transition-all hover:-translate-y-0.5 self-start">
        <div className="flex items-center gap-2 truncate">
          <Package size={14} strokeWidth={3} className="shrink-0 text-ink/70"/>
          <span className="font-black text-[11px] uppercase tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>RESULT: {msg.name || 'Output'}</span>
        </div>
        <ChevronDown size={14} strokeWidth={3} className="shrink-0 opacity-50"/>
      </div>
    );
  }

  return (
    <div style={sketchyShape3} className="max-w-[85%] w-full p-4 border-4 border-ink bg-[#a3be8c]/30 text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] mb-4 transition-all self-start">
      <div>
        <div className="flex items-center gap-2 mb-2 border-b-2 border-ink/20 pb-1">
          <Package size={16} strokeWidth={3}/>
          <span className="font-black text-xs uppercase tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TOOL RESULT: {msg.name || 'Output'}</span>
        </div>
        <div className="font-mono text-[13px] opacity-90 whitespace-pre-wrap break-all">{contentStr}</div>
        <button onClick={() => setExpanded(false)} className="mt-3 text-xs font-black text-ink/70 hover:text-terracotta flex items-center gap-1 bg-white/50 px-2 py-1 border-2 border-transparent hover:border-ink transition-all" style={sketchyShape2}>
          <ChevronUp size={14} strokeWidth={3}/> COLLAPSE
        </button>
      </div>
    </div>
  );
};

const ToolCallBubble = ({ tc }: { tc: any }) => {
  const [expanded, setExpanded] = useState(false);
  const argsStr = tc.function?.arguments || '{}';

  if (!expanded) {
    return (
      <div onClick={() => setExpanded(true)} style={sketchyShape3} className="w-fit max-w-[250px] p-2 px-4 border-2 border-ink bg-[#EBCB8B]/40 text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] mb-2 flex items-center justify-between gap-3 cursor-pointer hover:bg-[#EBCB8B]/70 transition-all hover:-translate-y-0.5 self-start">
        <div className="flex items-center gap-2 truncate">
          <Wrench size={14} strokeWidth={3} className="shrink-0 text-ink/70"/>
          <span className="font-black text-[11px] uppercase tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CALL: {tc.function?.name}</span>
        </div>
        <ChevronDown size={14} strokeWidth={3} className="shrink-0 opacity-50"/>
      </div>
    );
  }

  return (
    <div style={sketchyShape3} className="w-full p-4 border-4 border-ink bg-[#EBCB8B]/40 text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] mb-2 transition-all">
      <div>
        <div className="flex items-center gap-2 mb-2 border-b-2 border-ink/20 pb-1">
          <Wrench size={16} strokeWidth={3}/>
          <span className="font-black text-xs uppercase tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CALLING TOOL: {tc.function?.name}</span>
        </div>
        <div className="font-mono text-[13px] opacity-80 break-all">{argsStr}</div>
        <button onClick={() => setExpanded(false)} className="mt-3 text-xs font-black text-ink/70 hover:text-terracotta flex items-center gap-1 bg-white/50 px-2 py-1 border-2 border-transparent hover:border-ink transition-all inline-flex" style={sketchyShape2}>
          <ChevronUp size={14} strokeWidth={3}/> COLLAPSE
        </button>
      </div>
    </div>
  );
};

export default function ChatPage({ onBack, onSwitchToTask }: { onBack: () => void; onSwitchToTask?: () => void }) {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();

  // --- 基础状态 ---
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId || null);
  
  // --- 🌟 新增：隔离分支状态控制 ---
  const [currentBranchId, setCurrentBranchId] = useState<string>('main');
  const [branches, setBranches] = useState<Record<string, any>>({ main: {} });

  // --- 弹窗与控制状态 ---
  const [showSessionModal, setShowSessionModal] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [newAlias, setNewAlias] = useState('');
  const [showBranchModal, setShowBranchModal] = useState(false);
  const [branchAlias, setBranchAlias] = useState('');
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [isAgentThinking, setIsAgentThinking] = useState(false);

  // --- 🌟 修复：新增支线删除确认弹窗状态 ---
  const [branchToDelete, setBranchToDelete] = useState<string | null>(null);

  // --- 🌟 修复：切分支时，强制清空假消息队列，防止 main 的消息在 sub 乱窜 ---
  useEffect(() => {
    pendingMsgsRef.current = [];
  }, [currentBranchId]);

  // --- Token 状态 ---
  const [tokenData, setTokenData] = useState({ window: 0, max: 1000000 });

  // --- 🌟 新增：请求审批队列状态 ---
  const [showReqQueue, setShowReqQueue] = useState(false);
  const [pendingReqs, setPendingReqs] = useState<any[]>([]);
  const [feedbackInputs, setFeedbackInputs] = useState<Record<string, string>>({});
  const prevPendingIds = useRef<string[]>([]);
  const [expandedReasons, setExpandedReasons] = useState<Record<string, boolean>>({});

  // --- 🌟 真实的文件变更视图状态 ---
  const [showFileView, setShowFileView] = useState(false);
  const [fileChanges, setFileChanges] = useState<any[]>([]);

  // --- 🌟 新增：拉取当前会话子宇宙分支列表 ---
  const loadBranches = async (sid: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/sessions/${sid}/branches`);
      if (res.ok) {
        const data = await res.json();
        setBranches(data);
      }
    } catch {
      setBranches({ main: {} });
    }
  };

  // 🌟 全局拉取接口
  const fetchGlobalDiffs = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/filesystem/diffs');
      if (res.ok) {
        const data = await res.json();
        if (data.diffs) {
          setFileChanges(data.diffs);
        }
      }
    } catch (e) {
      console.error("Fetch diffs error", e);
    }
  };

  // 每 3 秒同步一次底层全局 Diff 状态
  useEffect(() => {
    fetchGlobalDiffs();
    const interval = setInterval(fetchGlobalDiffs, 3000);
    return () => clearInterval(interval);
  }, []);

  // --- 🌟 确认变更函数（向前截断） ---
  const handleAck = async (changeId: string, path: string, backupId: string) => {
    try {
      if (!backupId) { toast.error("缺乏快照标识，无法确认"); return; }
      const res = await fetch(`http://localhost:8000/api/filesystem/ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, backup_id: backupId })
      });
      
      if (res.ok) {
        toast.success("已确认更改并清理旧备份！");
        fetchGlobalDiffs(); // 立刻刷新视图，后端已物理抹除，数据会自动消失！
      } else {
        const err = await res.json();
        toast.error(err.detail || "确认失败");
      }
    } catch {
      toast.error("网络异常");
    }
  };

  // --- 🌟 一键回滚函数（向后截断） ---
  const handleRollback = async (changeId: string, path: string, backupId: string) => {
    try {
      if (!backupId) { toast.error("缺乏快照标识，无法精准回滚"); return; }
      const res = await fetch(`http://localhost:8000/api/filesystem/undo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, backup_id: backupId })
      });
      
      if (res.ok) {
        toast.success("时光倒流：文件已恢复，后续修改已废弃！");
        fetchGlobalDiffs(); // 立刻刷新视图
      } else {
        const err = await res.json();
        toast.error(err.detail || "回滚失败");
      }
    } catch {
      toast.error("网络异常，回滚失败");
    }
  };

  // 轮询 Token 进度
  useEffect(() => {
    let tokenInterval: ReturnType<typeof setTimeout>;
    const fetchToken = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/agent/token');
        if (res.ok) {
          const data = await res.json();
          setTokenData({ window: data.window_token, max: data.max_token });
        }
      } catch (e) {
        console.error("Fetch token error", e);
      }
    };

    if (currentSessionId) {
      fetchToken();
      tokenInterval = setInterval(fetchToken, 5000);
    }
    return () => { if (tokenInterval) clearInterval(tokenInterval); };
  }, [currentSessionId]);

  // --- 🌟 新增：请求队列拉取与操作逻辑 ---
  const fetchRequests = async () => {
    try {
      const resPending = await fetch('http://localhost:8000/api/requests').catch(() => null);

      if (resPending?.ok) {
        const dataPending = await resPending.json();
        setPendingReqs(dataPending);
        
        // 自动弹出逻辑：如果有新的 pending 请求，就自动打开右侧抽屉
        const currentIds = dataPending.map((r: any) => r.id);
        const hasNew = currentIds.some((id: string) => !prevPendingIds.current.includes(id));
        if (hasNew && dataPending.length > 0) {
          setShowReqQueue(true);
        }
        prevPendingIds.current = currentIds;
      }
    } catch (e) {
      console.error("Fetch requests error", e);
    }
  };

  useEffect(() => {
    fetchRequests();
    const interval = setInterval(fetchRequests, 3000); // 每3秒拉取一次
    return () => clearInterval(interval);
  }, []);

  const handleResolveReq = async (reqId: string, approved: boolean, ignore: boolean) => {
    const feedback = feedbackInputs[reqId] || '';
    try {
      const res = await fetch(`http://localhost:8000/api/requests/${reqId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, feedback, ignore })
      });
      if (res.ok) {
        toast.success(ignore ? "请求已静默忽略" : "请求处理完成");
        setFeedbackInputs(prev => { const n = {...prev}; delete n[reqId]; return n; });
        fetchRequests(); // 刷新
      } else {
        toast.error("请求处理失败");
      }
    } catch { toast.error("网络异常"); }
  };

  // --- 侧边栏面板状态 ---
  const [sidebarMode, setSidebarMode] = useState<'menu' | 'mcp' | 'skill' | 'cron' | 'sensor'>('menu');
  const [sensorData, setSensorData] = useState<any>({});
  const [mcpData, setMcpData] = useState<Record<string, any[]>>({});
  const [expandedMcp, setExpandedMcp] = useState<string | null>(null);
  
  const [skillData, setSkillData] = useState<any[]>([]);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  
  // --- 🌟 新增：Skill 下载弹窗与状态 ---
  const [showInstallSkillModal, setShowInstallSkillModal] = useState(false);
  const [skillInstallUrl, setSkillInstallUrl] = useState('');
  const [isInstallingSkill, setIsInstallingSkill] = useState(false);
  
  const [cronData, setCronData] = useState<any[]>([]);
  const [showAddCronModal, setShowAddCronModal] = useState(false);
  const [newCron, setNewCron] = useState({ title: '', trigger_time: '', repeat_rule: 'none' });

  // --- MD编辑状态 (SOUL / SOLO / TODO) ---
  const [showMdModal, setShowMdModal] = useState(false);
  const [mdType, setMdType] = useState<'SOUL' | 'SOLO' | 'TODO'>('SOUL');
  const [mdContent, setMdContent] = useState('');
  const [isSavingMd, setIsSavingMd] = useState(false);

  // --- Skill 选择器相关状态 ---
  const [showSkillSelectModal, setShowSkillSelectModal] = useState(false);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [tempSelectedSkills, setTempSelectedSkills] = useState<string[]>([]);

  // --- 🌟 引用文件/目录状态 ---
  const [refPaths, setRefPaths] = useState<string[]>([]);
  const [showRefModal, setShowRefModal] = useState(false); // 改为 Modal
  const [tempRefPath, setTempRefPath] = useState('');

  // --- 🌟 拖拽/上传相关状态 ---
  const [isDragging, setIsDragging] = useState(false);

  // --- 常量定义 ---
  const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB 限制

  // --- 🌟 处理文件上传并转为本地路径（带安全拦截） ---
  const handleFileUpload = async (files: FileList | File[]) => {
    try {
      const newPaths: string[] = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];

        // 🛑 安全拦截：文件大小限制
        if (file.size > MAX_FILE_SIZE) {
          toast.error(`文件 [${file.name}] 太大啦！请不要超过 20MB。`);
          continue;
        }

        console.log(`准备上传: ${file.name}, 类型: ${file.type}, 大小: ${(file.size / 1024 / 1024).toFixed(2)}MB`);

        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('http://localhost:8000/api/system/upload-buffer', { 
          method: 'POST', 
          body: formData, 
        });

        if (res.ok) {
          const data = await res.json();
          newPaths.push(data.absolute_path);
        } else {
          toast.error(`上传 ${file.name} 失败`);
        }
      }
      
      if (newPaths.length > 0) {
        setRefPaths(prev => [...new Set([...prev, ...newPaths])]);
        toast.success(`成功载入 ${newPaths.length} 个文件`);
      }
    } catch {
      toast.error("网络错误，文件上传失败");
    }
  };

  // --- 🌟 处理粘贴事件 ---
  const handlePaste = (e: React.ClipboardEvent) => {
    // 如果剪贴板里有文件（截图、复制的图片等）
    if (e.clipboardData.files && e.clipboardData.files.length > 0) {
      e.preventDefault(); // 阻止默认的粘贴文本行为
      handleFileUpload(e.clipboardData.files);
    }
  };

  // --- 🌟 处理拖拽事件 (🌟 增强版：拦截文件夹)
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    // 使用 dataTransfer.items 来进行更深度的探测
    const items = e.dataTransfer.items;
    if (items && items.length > 0) {
      const validFiles: File[] = [];
      let hasFolder = false;

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          // 核心魔法：获取文件系统条目，判断是不是文件夹
          const entry = item.webkitGetAsEntry();
          if (entry && entry.isDirectory) {
            hasFolder = true;
          } else {
            // 是正常文件，提取出来
            const file = item.getAsFile();
            if (file) validFiles.push(file);
          }
        }
      }

      // 如果探测到了文件夹，给出友好的专属提示
      if (hasFolder) {
        toast.error("暂不支持直接上传文件夹哦！请选择具体的文件。");
      }

      // 如果拖拽的内容里有合法的文件（比如混着拖的），继续上传合法文件
      if (validFiles.length > 0) {
        handleFileUpload(validFiles);
      }
    }
  };

  // --- 配置中心选项卡常量 ---
  const CONFIG_TABS = ['model', 'sensor', 'file', 'memory', 'mcp'];

  // --- 配置中心核心状态 ---
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('model');
  const [configData, setConfigData] = useState<Record<string, any>>({});
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [editJsonStr, setEditJsonStr] = useState('');

  // --- 配置读取函数 ---
  const fetchConfig = async (tab: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/config/${tab}`);
      if (res.ok) {
        const data = await res.json();
        setConfigData(data);
        setExpandedKey(null);
        setEditJsonStr('');
      } else {
        toast.error(`无法加载 ${tab} 配置`);
      }
    } catch {
      toast.error("网络错误，无法连接后端");
    }
  };

  // 监听弹窗开启及 Tab 切换
  useEffect(() => {
    if (isConfigOpen) {
      fetchConfig(activeTab);
    }
  }, [isConfigOpen, activeTab]);

  const toggleKey = (key: string) => {
    if (expandedKey === key) {
      setExpandedKey(null);
    } else {
      setExpandedKey(key);
      setEditJsonStr(JSON.stringify(configData[key], null, 2));
    }
  };

  // --- 配置保存落盘函数 ---
  const handleSaveConfig = async (key: string) => {
    try {
      const parsedValue = JSON.parse(editJsonStr);
      const newConfig = { ...configData, [key]: parsedValue };

      const res = await fetch(`http://localhost:8000/api/config/${activeTab}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig)
      });

      if (res.ok) {
        toast.success(`[${key}] 配置已落盘！`);
        setConfigData(newConfig);
        setExpandedKey(null);
      } else {
        toast.error("保存失败，后端拒绝了请求");
      }
    } catch {
      toast.error("保存失败：JSON 格式不合法！请检查引号和括号。");
    }
  };

  const openMdEditor = async (type: 'SOUL' | 'SOLO' | 'TODO') => {
    setMdType(type);
    setMdContent('Loading...');
    setShowMdModal(true);
    try {
      const res = await fetch(`http://localhost:8000/api/config/markdown/${type}`);
      if (res.ok) {
        const data = await res.json();
        setMdContent(data.content);
      } else {
        toast.error(`读取 ${type}.md 失败`);
        setMdContent('');
      }
    } catch {
      toast.error(`网络错误，无法读取 ${type}.md`);
      setMdContent('');
    }
  };

  const saveMdContent = async () => {
    setIsSavingMd(true);
    try {
      const res = await fetch(`http://localhost:8000/api/config/markdown/${mdType}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: mdContent })
      });
      if (res.ok) {
        toast.success(`[${mdType}.md] 已成功落盘保存！`);
        setShowMdModal(false);
      } else {
        toast.error("保存失败");
      }
    } catch {
      toast.error("网络异常，保存失败");
    } finally {
      setIsSavingMd(false);
    }
  };

  // --- API 交互 (Sensor, MCP, Skill, Cron) ---
  const fetchSensorData = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/config/sensor');
      if (res.ok) setSensorData(await res.json());
    } catch { toast.error("获取 Sensor 列表失败"); }
  };

  const reloadSensors = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/config/sensor/reload', { method: 'POST' });
      if (res.ok) toast.success("所有启用的 Sensors 已完成热重启！");
      else toast.error("热重启发生异常");
    } catch { toast.error("重启指令发送失败"); }
  };

  const toggleSensorStatus = async (sensorName: string) => {
    try {
       const newSensorData = JSON.parse(JSON.stringify(sensorData));
       if (!newSensorData[sensorName]) return;
       
       const currentStatus = newSensorData[sensorName].enabled || false;
       newSensorData[sensorName].enabled = !currentStatus;
       
       setSensorData(newSensorData);

       const resSave = await fetch('http://localhost:8000/api/config/sensor', {
         method: 'PUT', headers: {'Content-Type': 'application/json'},
         body: JSON.stringify(newSensorData)
       });
       
       if (resSave.ok) {
          toast.success(`[${sensorName}] 已置为 ${!currentStatus ? '启动' : '关闭'}状态，正在应用到内存...`);
          await reloadSensors();
       } else {
          toast.error("配置文件落盘失败");
       }
    } catch {
       toast.error("操作异常");
    }
  };

  const fetchMcp = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/mcp');
      if (res.ok) setMcpData(await res.json());
    } catch { toast.error("获取 MCP 列表失败"); }
  };

  const refreshMcp = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/mcp/refresh', { method: 'POST' });
      if (res.ok) { toast.success("MCP 工具已刷新"); fetchMcp(); }
    } catch { toast.error("刷新 MCP 失败"); }
  };

  const fetchSkill = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/skills');
      if (res.ok) setSkillData(await res.json());
    } catch { toast.error("获取 Skill 列表失败"); }
  };

  const refreshSkill = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/skills/refresh', { method: 'POST' });
      if (res.ok) { toast.success("Skills 已刷新"); fetchSkill(); }
    } catch { toast.error("刷新 Skill 失败"); }
  };

  // 🌟 新增：调用后端下载并热更新 Skill
  const handleInstallSkill = async () => {
    if (!skillInstallUrl.trim()) {
      toast.error("Github URL 不能为空！");
      return;
    }
    setIsInstallingSkill(true);
    try {
      const res = await fetch('http://localhost:8000/api/tools/skills/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: skillInstallUrl.trim() })
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || "Skill 下载并加载成功！");
        setShowInstallSkillModal(false);
        setSkillInstallUrl('');
        fetchSkill(); // 重新拉取以更新前端列表
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "安装失败，请检查 URL 格式");
      }
    } catch {
      toast.error("网络异常，无法下载 Skill");
    } finally {
      setIsInstallingSkill(false);
    }
  };

  // --- 🌟 新增：MCP 安装弹窗与状态 ---
  const [showInstallMcpModal, setShowInstallMcpModal] = useState(false);
  const [mcpInstallJson, setMcpInstallJson] = useState('');
  const [isInstallingMcp, setIsInstallingMcp] = useState(false);

  // --- 🌟 新增：Sensor 安装弹窗与状态 ---
  const [showInstallSensorModal, setShowInstallSensorModal] = useState(false);
  const [sensorInstallJson, setSensorInstallJson] = useState('');
  const [isInstallingSensor, setIsInstallingSensor] = useState(false);

  // 🌟 新增：处理 Sensor JSON 注入并热重启
  const handleInstallSensor = async () => {
    if (!sensorInstallJson.trim()) {
      toast.error("JSON 配置不能为空！");
      return;
    }
    setIsInstallingSensor(true);
    try {
      const parsed = JSON.parse(sensorInstallJson);
      const newSensors = parsed.sensors ? parsed.sensors : parsed;

      const currentData = JSON.parse(JSON.stringify(sensorData));

      Object.assign(currentData, newSensors);

      const resSave = await fetch('http://localhost:8000/api/config/sensor', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentData)
      });

      if (resSave.ok) {
        toast.success("Sensor 配置合并成功，正在触发热加载...");
        
        await reloadSensors(); 
        
        setShowInstallSensorModal(false);
        setSensorInstallJson('');
        fetchSensorData();
      } else {
        toast.error("配置文件落盘失败");
      }
    } catch {
      toast.error("JSON 解析失败，请检查格式！");
    } finally {
      setIsInstallingSensor(false);
    }
  };

  // 🌟 新增：调用后端接口安装并刷新 MCP
  const handleInstallMcp = async () => {
    if (!mcpInstallJson.trim()) {
      toast.error("JSON 配置不能为空！");
      return;
    }
    setIsInstallingMcp(true);
    try {
      const res = await fetch('http://localhost:8000/api/tools/mcp/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_json: mcpInstallJson.trim() })
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || "MCP 安装成功！");
        setShowInstallMcpModal(false);
        setMcpInstallJson('');
        fetchMcp(); // 重新拉取最新的 MCP 列表渲染
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "安装失败，请检查 JSON 格式或网络");
      }
    } catch {
      toast.error("网络异常，无法安装 MCP");
    } finally {
      setIsInstallingMcp(false);
    }
  };

  const fetchCron = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/cron');
      if (res.ok) setCronData(await res.json());
    } catch { toast.error("获取闹钟列表失败"); }
  };

  const addCron = async () => {
    if(!newCron.title.trim() || !newCron.trigger_time.trim()) {
      toast.error("闹钟标题和时间不能为空"); return;
    }
    try {
      const res = await fetch('http://localhost:8000/api/tools/cron', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newCron)
      });
      if (res.ok) { 
        toast.success("闹钟添加成功"); 
        setShowAddCronModal(false); 
        setNewCron({ title: '', trigger_time: '', repeat_rule: 'none' });
        fetchCron(); 
      }
    } catch { toast.error("添加闹钟失败"); }
  };

  const deleteCron = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/tools/cron/${id}`, { method: 'DELETE' });
      if (res.ok) { toast.success("闹钟已删除"); fetchCron(); }
    } catch { toast.error("删除闹钟失败"); }
  };

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return;
    try {
      const res = await fetch(`http://localhost:8000/api/sessions/${sessionToDelete}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success("会话已彻底删除！");
        if (currentSessionId === sessionToDelete) {
          setCurrentSessionId(null);
          setMessages([]);
        }
        setSessionToDelete(null);
        loadSessions();
      }
    } catch { toast.error("删除失败，请检查网络"); }
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const isAutoScroll = useRef(true);
  const pendingMsgsRef = useRef<string[]>([]);

  const handleScroll = () => {
    if (!messagesContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  useEffect(() => {
    if (isAutoScroll.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  useEffect(() => { loadSessions(); }, []);

  // --- 🌟 改造：会话初始检出重置 ---
  useEffect(() => {
    if (sessionId && sessionId !== currentSessionId) {
      pendingMsgsRef.current = [];
      setCurrentSessionId(sessionId);
      setCurrentBranchId('main'); // 切新会话时重置回主干
      loadSessionHistory(sessionId, 'main');
      loadBranches(sessionId);
    }
  }, [sessionId]);

  // --- 🌟 改造：轮询拦截器，使其能自动定位至当前聚焦的书签分支 ---
  useEffect(() => {
    if (!currentSessionId) return;
    const interval = setInterval(async () => {
      if (isCheckingOut) return;
      try {
        const [msgRes, statusRes] = await Promise.all([
          // 加上 branch_id 约束查询
          fetch(`http://localhost:8000/api/sessions/${currentSessionId}?branch_id=${currentBranchId}`),
          fetch(`http://localhost:8000/api/sessions/${currentSessionId}/status`)
        ]);

        if (msgRes.ok) {
          const history = await msgRes.json();
          pendingMsgsRef.current = pendingMsgsRef.current.filter(pendingText => {
            return !hasMessageInHistory(history, pendingText);
          });
          
          const newMessages = [...history];
          pendingMsgsRef.current.forEach(text => {
            newMessages.push({ role: 'user', content: text });
          });
          
          setMessages(newMessages);
        }
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setIsAgentThinking(statusData.is_thinking);
          
          // 当后台打工仔分支正在并发开辟时，定时顺手刷新分支列表，让新诞生支线书签"啪"地弹出来
          loadBranches(currentSessionId);
        }
      } catch (e) {
        console.error('Error checking agent status:', e);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [currentSessionId, currentBranchId, isCheckingOut]); // 🌟 挂载关联依赖

  const loadSessions = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/sessions');
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
        if (data.length > 0 && !currentSessionId) {
          const firstSessionId = data[0].id;
          // ✅ 核心修复：必须通过 handleSelectSession 去触发后端的 checkout
          await handleSelectSession(firstSessionId);
        }
      }
    } catch { toast.error("获取会话失败"); }
  };

  // --- 🌟 改造：支持传入分支标识的历史读取 ---
  const loadSessionHistory = async (id: string, bId: string = 'main') => {
    const res = await fetch(`http://localhost:8000/api/sessions/${id}?branch_id=${bId}`);
    if (res.ok) {
      const history = await res.json();
      setMessages(history);
    }
  };

  const handleSelectSession = async (id: string) => {
    setIsCheckingOut(true);
    setCurrentSessionId(id);
    setCurrentBranchId('main'); // 重置
    navigate(`/chat/${id}`, { replace: true });
    isAutoScroll.current = true;
    try {
      await fetch(`http://localhost:8000/api/sessions/${id}/checkout`, { method: 'POST' }).catch(() => {});
      await loadSessionHistory(id, 'main');
      await loadBranches(id); // 加载全量分支书签
    } catch { 
      toast.error('加载记录失败'); 
    } finally {
      setIsCheckingOut(false);
    }
  };

  const confirmNewSession = async () => {
    if (!newAlias.trim()) {
      toast.error('请输入对话名称！');
      return;
    }
    setShowModal(false);
    setIsCheckingOut(true); 
    try {
      const res = await fetch('http://localhost:8000/api/sessions/new', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ alias: newAlias.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`开启全新对话: ${newAlias}`);
        setNewAlias('');
        await loadSessions();
        await handleSelectSession(data.id); 
      } else {
        setIsCheckingOut(false);
      }
    } catch { 
      toast.error('创建失败'); 
      setIsCheckingOut(false); 
    }
  };

  const confirmBranchSession = async () => {
    if (!branchAlias.trim()) {
      toast.error('请输入分支名称！');
      return;
    }
    if (!currentSessionId) {
      toast.error('当前没有可用的会话来拉取分支！');
      return;
    }
    
    setShowBranchModal(false);
    setIsCheckingOut(true);
    
    try {
      const res = await fetch(`http://localhost:8000/api/sessions/${currentSessionId}/branch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias: branchAlias.trim() }),
      });
      
      if (res.ok) {
        const data = await res.json();
        toast.success(`成功从当前进度拉取分支: ${branchAlias}`);
        setBranchAlias('');
        await loadSessions();
        await handleSelectSession(data.id);
      } else {
        setIsCheckingOut(false);
        toast.error('衍生分支失败');
      }
    } catch {
      toast.error('网络错误，无法拉取分支');
      setIsCheckingOut(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || !currentSessionId) return;
    
    const eventsToPush: any[] = [];
    const userText = input.trim();
    
    // 1. 遍历并注入文件引用 (覆盖了拖拽、粘贴、点击弹窗等所有方式)
    if (refPaths.length > 0) {
      refPaths.forEach(path => {
        eventsToPush.push({
          type: 'file-quote',
          content: `user quote the file：${path}`
        });
      });
    }

    // 2. 遍历并注入 Skill 引用
    if (selectedSkills.length > 0) {
      selectedSkills.forEach(skill => {
        eventsToPush.push({
          type: 'skill-quote',
          content: `user want you fetch skill：${skill}`
        });
      });
    }

    // 3. 注入用户的真实文本
    eventsToPush.push({
      type: 'user',
      content: userText
    });
    
    // 清理状态
    setInput('');
    setSelectedSkills([]); 
    setRefPaths([]); 
    isAutoScroll.current = true;
    
    // 把纯文本放入 pending 列阵，用于防重检测
    pendingMsgsRef.current.push(userText);
    
    // 构造本地的假消息格式用于立即渲染（包装成后端格式）
    const fakeMsgContent = JSON.stringify({ events: eventsToPush });
    setMessages(prev => [...prev, { role: 'user', content: fakeMsgContent }]);

    try {
      await fetch('http://localhost:8000/api/chat/batch', {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          session_id: currentSessionId, 
          events: eventsToPush
        }),
      });
    } catch { 
      toast.error('网络错误'); 
    }
  };

  // 🌟 智能判定环境的附件点击事件
  const handleAttachmentClick = async () => {
    // 探测当前是否在 Tauri 桌面客户端环境中 (忽略 TypeScript 报错)
    // @ts-expect-error window.__TAURI__ may not exist in all environments
    const tauri = typeof window !== 'undefined' ? window.__TAURI__ : null;

    if (tauri && tauri.dialog) {
      // 🚀 桌面端环境：直接调用系统原生的文件选择器
      try {
        const selected = await tauri.dialog.open({ 
          multiple: true, // 允许多选
        });
        
        if (selected) {
           const paths = Array.isArray(selected) ? selected : [selected];
           // 去重并添加到标签列表中
           setRefPaths(prev => [...new Set([...prev, ...paths])]);
           setShowRefModal(false); // 确保手绘弹窗是关闭的
        }
      } catch (err) {
        console.error("原生弹窗调用失败，降级为 Web 模式", err);
        setShowRefModal(true); // 降级弹窗
      }
    } else {
      // 🌐 纯 Web 环境：降级弹出我们的手绘风弹窗
      setShowRefModal(true);
    }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">
      
      {/* 检出状态遮罩 */}
      {isCheckingOut && (
        <div className="fixed inset-0 bg-cream/70 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-10 flex flex-col items-center justify-center gap-6 shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] -rotate-1 min-w-[320px]">
            <div className="relative flex items-center justify-center">
              <div className="absolute inset-0 bg-[#EBCB8B] rounded-full blur-xl opacity-60 animate-pulse"></div>
              <div className="bg-ink p-4 border-4 border-paper shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] z-10" style={sketchyShape3}>
                <Loader2 size={64} strokeWidth={2.5} className="animate-spin text-paper" />
              </div>
            </div>
            <div className="text-center mt-2">
              <h3 className="text-3xl font-black tracking-widest text-ink mb-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CHECKING OUT...</h3>
              <p className="font-bold opacity-70 text-base text-ink/80 bg-terracotta/10 px-3 py-1 border-2 border-dashed border-ink/20 inline-block" style={sketchyShape1}>
                Waiting for the agent to complete tasks...
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 新建会话弹窗 */}
      {showModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-md w-full">
            <div className="flex justify-between items-center -rotate-1">
              <h3 className="text-3xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW CHAT</h3>
              <button onClick={() => setShowModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <div className="-rotate-1">
              <input autoFocus value={newAlias} onChange={e => setNewAlias(e.target.value)} onKeyDown={e => e.key === 'Enter' && confirmNewSession()} placeholder="Give it a cool name..." className="w-full border-4 border-ink bg-cream p-4 font-bold text-lg focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" style={sketchyShape3} />
            </div>
            <button onClick={confirmNewSession} style={{ ...sketchyShape1, fontFamily: '"Comic Sans MS", cursive' }} className="bg-terracotta text-paper font-black tracking-widest text-xl py-4 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-none transition-all rotate-1">
              CREATE NOW
            </button>
          </div>
        </div>
      )}

      {/* 衍生分支 (Branch) 弹窗 */}
      {showBranchModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-md w-full">
            <div className="flex justify-between items-center -rotate-1">
              <h3 className="text-3xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>BRANCH CHAT</h3>
              <button onClick={() => setShowBranchModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <div className="-rotate-1">
              <p className="font-bold opacity-70 mb-2 text-ink">基于当前时间线创造一个平行宇宙：</p>
              <input autoFocus value={branchAlias} onChange={e => setBranchAlias(e.target.value)} onKeyDown={e => e.key === 'Enter' && confirmBranchSession()} placeholder="Give the new branch a name..." className="w-full border-4 border-ink bg-cream p-4 font-bold text-lg focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" style={sketchyShape3} />
            </div>
            <button onClick={confirmBranchSession} style={{ ...sketchyShape1, fontFamily: '"Comic Sans MS", cursive' }} className="bg-[#d08770] text-paper font-black tracking-widest text-xl py-4 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-none transition-all rotate-1">
              FORK TIMELINE
            </button>
          </div>
        </div>
      )}

      {/* 彻底删除会话分支确认弹窗 */}
      {sessionToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DELETE CHAT?</h3>
              <button onClick={() => setSessionToDelete(null)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要删除这个分支会话吗？该分支上的历史记忆将永久丢失！</p>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setSessionToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">CANCEL</button>
              <button onClick={confirmDeleteSession} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">DELETE</button>
            </div>
          </div>
        </div>
      )}

      {/* 彻底删除支线分支确认弹窗 */}
      {branchToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DESTROY BRANCH?</h3>
              <button onClick={() => setBranchToDelete(null)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要彻底销毁支线 [{branchToDelete}] 的全部历史记忆吗？</p>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setBranchToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">CANCEL</button>
              <button onClick={async () => {
                 if (!currentSessionId) return;
                 try {
                     const res = await fetch(`http://localhost:8000/api/sessions/${currentSessionId}/branches/${branchToDelete}`, { method: 'DELETE' });
                     if (res.ok) {
                       toast.success('支线已永久销毁');
                       // 如果删的是当前正在看的支线，立刻退回主干
                       if (currentBranchId === branchToDelete) {
                         setCurrentBranchId('main');
                         loadSessionHistory(currentSessionId, 'main');
                       }
                       loadBranches(currentSessionId);
                       setBranchToDelete(null);
                     }
                   } catch {
                     toast.error('销毁失败');
                   }
              }} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">DESTROY</button>
            </div>
          </div>
        </div>
      )}

      {/* 新增 Cron 弹窗 */}
      {showAddCronModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-sm w-full">
            <h3 className="text-2xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW ALARM</h3>
            <input placeholder="Alarm Title..." value={newCron.title} onChange={e=>setNewCron({...newCron, title:e.target.value})} className="border-4 border-ink p-3 font-bold bg-cream focus:outline-none" style={sketchyShape3} />
            <input placeholder="Trigger Time (cron expr or HH:MM)" value={newCron.trigger_time} onChange={e=>setNewCron({...newCron, trigger_time:e.target.value})} className="border-4 border-ink p-3 font-bold bg-cream focus:outline-none" style={sketchyShape1} />
            <div className="flex gap-4 mt-2">
              <button onClick={() => setShowAddCronModal(false)} className="flex-1 bg-cream border-4 border-ink font-black py-3 active:translate-y-1 transition-transform shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none" style={sketchyShape2}>CANCEL</button>
              <button onClick={addCron} className="flex-1 bg-[#d08770] text-paper border-4 border-ink font-black py-3 active:translate-y-1 transition-transform shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none" style={sketchyShape1}>SAVE</button>
            </div>
          </div>
        </div>
      )}

      {/* 🌟 新增：第三方 Skill 安装弹窗 */}
      {showInstallSkillModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-terracotta" style={{ fontFamily: '"Comic Sans MS", cursive' }}>INSTALL SKILL</h3>
              <button onClick={() => setShowInstallSkillModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            
            <div className="-rotate-1">
              <p className="font-bold opacity-70 mb-3 text-ink text-sm">
                输入第三方 Skill 的 Github Tree 链接以自动安装：<br/>
                <span className="text-xs opacity-80">(e.g. https://github.com/owner/repo/tree/main/path/to/skill)</span>
              </p>
              <input 
                autoFocus 
                value={skillInstallUrl} 
                onChange={e => setSkillInstallUrl(e.target.value)} 
                onKeyDown={e => e.key === 'Enter' && handleInstallSkill()} 
                placeholder="https://github.com/..." 
                className="w-full border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-base focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" 
                style={sketchyShape3} 
              />
            </div>
            
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowInstallSkillModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] hover:shadow-none transition-all">
                CANCEL
              </button>
              <button onClick={handleInstallSkill} disabled={isInstallingSkill} style={sketchyShape1} className="flex-1 bg-[#a3be8c] text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] hover:translate-y-[1px] hover:shadow-none transition-all flex items-center justify-center gap-2">
                {isInstallingSkill ? <Loader2 size={24} className="animate-spin" strokeWidth={3}/> : <Download size={24} strokeWidth={3}/>}
                DOWNLOAD
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🌟 新增：MCP 配置解析与安装弹窗 */}
      {showInstallMcpModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-[#88c0d0]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>INSTALL MCP</h3>
              <button onClick={() => setShowInstallMcpModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            
            <div className="-rotate-1 flex flex-col h-full">
              <p className="font-bold opacity-70 mb-3 text-ink text-sm">
                在此粘贴标准格式的 MCP 配置文件内容：<br/>
                <span className="text-xs opacity-80">(必须是以 `mcpServers` 为根节点的完整 JSON 对象)</span>
              </p>
              <textarea 
                autoFocus 
                value={mcpInstallJson} 
                onChange={e => setMcpInstallJson(e.target.value)} 
                placeholder={'{\n  "mcpServers": {\n    "awslabs-core-mcp-server": {\n      "command": "uvx",\n      "args": ["awslabs.core-mcp-server@latest"]\n    }\n  }\n}'}
                className="w-full h-64 border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-sm font-mono focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30 resize-none" 
                style={sketchyShape3} 
                spellCheck={false}
              />
            </div>
            
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowInstallMcpModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] hover:shadow-none transition-all">
                CANCEL
              </button>
              <button onClick={handleInstallMcp} disabled={isInstallingMcp} style={sketchyShape1} className="flex-1 bg-[#88c0d0] text-paper font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#72a6b5] hover:translate-y-[1px] hover:shadow-none transition-all flex items-center justify-center gap-2">
                {isInstallingMcp ? <Loader2 size={24} className="animate-spin" strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>}
                SAVE & LOAD
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🌟 新增：Sensor JSON 解析与安装弹窗 */}
      {showInstallSensorModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-[#a3be8c]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>ADD SENSOR</h3>
              <button onClick={() => setShowInstallSensorModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            
            <div className="-rotate-1 flex flex-col h-full">
              <p className="font-bold opacity-70 mb-3 text-ink text-sm">
                在此粘贴 Sensor 的 JSON 配置：<br/>
                <span className="text-xs opacity-80">(可以直接粘贴某个 sensor 对象，我们会自动将其合并并热重载进程)</span>
              </p>
              <textarea 
                autoFocus 
                value={sensorInstallJson} 
                onChange={e => setSensorInstallJson(e.target.value)} 
                placeholder={'{\n  "my_custom_sensor": {\n    "enabled": true,\n    "env": {\n      "API_KEY": "xxx"\n    },\n    "capabilities": {\n      "observe": true,\n      "express": false\n    }\n  }\n}'}
                className="w-full h-64 border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-sm font-mono focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30 resize-none" 
                style={sketchyShape3} 
                spellCheck={false}
              />
            </div>
            
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowInstallSensorModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] hover:shadow-none transition-all">
                CANCEL
              </button>
              <button onClick={handleInstallSensor} disabled={isInstallingSensor} style={sketchyShape1} className="flex-1 bg-[#a3be8c] text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] hover:translate-y-[1px] hover:shadow-none transition-all flex items-center justify-center gap-2">
                {isInstallingSensor ? <Loader2 size={24} className="animate-spin" strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>}
                SAVE & LOAD
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Markdown 编辑弹窗 (SOUL / SOLO) */}
      {showMdModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-4xl h-[85vh]">
            
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/20 pb-4 shrink-0">
              <div className="flex items-center gap-3">
                <FileText size={32} className="text-terracotta" strokeWidth={2.5} />
                <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  {mdType}.md
                </h3>
              </div>
              <button onClick={() => setShowMdModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={32} strokeWidth={3}/>
              </button>
            </div>
            
            <div className="flex-1 -rotate-1 overflow-hidden flex flex-col w-full">
              <textarea 
                value={mdContent} 
                onChange={e => setMdContent(e.target.value)} 
                className="w-full h-full border-4 border-ink bg-[#FDF8F0] p-6 font-mono text-base leading-relaxed font-bold focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] resize-none" 
                style={sketchyShape3} 
                spellCheck={false}
                placeholder={`开始编辑你的 ${mdType}...`}
              />
            </div>
            
            <div className="shrink-0 flex justify-end gap-4 -rotate-1 pt-2">
              <button onClick={() => setShowMdModal(false)} style={sketchyShape3} className="px-8 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                CANCEL
              </button>
              <button onClick={saveMdContent} disabled={isSavingMd} style={sketchyShape1} className="px-10 bg-[#a3be8c] text-ink font-black py-3 border-4 border-ink hover:bg-[#8eb072] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 flex items-center gap-2">
                {isSavingMd ? <Loader2 className="animate-spin" size={24} strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>} 
                SAVE FILE
              </button>
            </div>

          </div>
        </div>
      )}

      {/* Skill 选择弹窗 */}
      {showSkillSelectModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-md h-[70vh]">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-3 shrink-0">
              <h3 className="text-2xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SELECT SKILLS</h3>
              <button onClick={() => setShowSkillSelectModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto flex flex-col gap-3 -rotate-1 p-1">
              {skillData.length === 0 ? (
                 <p className="font-bold text-center mt-6 opacity-50 text-sm">No Skills loaded</p>
              ) : (
                 skillData.map((skill: any, idx) => {
                   const isSelected = tempSelectedSkills.includes(skill.name);
                   return (
                     <div key={skill.name} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${isSelected ? 'shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] border-terracotta bg-terracotta/10' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]'} flex flex-col gap-2 cursor-pointer`} onClick={() => {
                       if (isSelected) setTempSelectedSkills(prev => prev.filter(s => s !== skill.name));
                       else setTempSelectedSkills(prev => [...prev, skill.name]);
                     }}>
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 border-2 border-ink flex items-center justify-center ${isSelected ? 'bg-terracotta' : 'bg-paper'}`} style={sketchyShape2}>
                            {isSelected && <div className="w-2.5 h-2.5 bg-paper rounded-full" />}
                          </div>
                          <span className="font-black text-lg flex-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{skill.name}</span>
                          <button onClick={(e) => { e.stopPropagation(); setExpandedSkill(expandedSkill === skill.name ? null : skill.name); }}>
                             {expandedSkill === skill.name ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
                          </button>
                        </div>
                        {expandedSkill === skill.name && (
                          <div className="text-xs font-bold opacity-80 pl-8 pt-1 border-t-2 border-ink/10 border-dashed mt-1">{skill.description}</div>
                        )}
                     </div>
                   );
                 })
              )}
            </div>
            <div className="shrink-0 flex justify-end gap-3 -rotate-1 pt-2 border-t-4 border-ink/10">
              <button onClick={() => {
                  setSelectedSkills(tempSelectedSkills);
                  setShowSkillSelectModal(false);
                }}
                style={sketchyShape1} className="px-8 bg-[#EBCB8B] text-ink font-black py-3 border-4 border-ink hover:bg-[#d8b877] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                COMPLETE
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🌟 引用本地路径弹窗 (Web 降级模式) */}
      {showRefModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-[#88c0d0]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>REFERENCE FILE</h3>
              <button onClick={() => setShowRefModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            
            <div className="-rotate-1">
              <p className="font-bold opacity-70 mb-3 text-ink text-sm">
                请输入或粘贴本地文件/文件夹的绝对路径：<br/>
                <span className="text-xs opacity-80">(在 Tauri 桌面模式下，此弹窗将被系统原生选择器取代)</span>
              </p>
              <input 
                autoFocus 
                value={tempRefPath} 
                onChange={e => setTempRefPath(e.target.value)} 
                onKeyDown={e => { 
                  if (e.key === 'Enter' && tempRefPath.trim()) { 
                    setRefPaths(prev => [...new Set([...prev, tempRefPath.trim()])]); 
                    setTempRefPath(''); 
                    setShowRefModal(false); 
                  } 
                }} 
                placeholder="/Users/dev/my_project/file.py" 
                className="w-full border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-base focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" 
                style={sketchyShape3} 
              />
            </div>
            
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowRefModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] hover:shadow-none transition-all">
                CANCEL
              </button>
              <button 
                onClick={() => { 
                  if (tempRefPath.trim()) { 
                    setRefPaths(prev => [...new Set([...prev, tempRefPath.trim()])]); 
                    setTempRefPath(''); 
                    setShowRefModal(false); 
                  } 
                }} 
                style={sketchyShape1} 
                className="flex-1 bg-[#88c0d0] text-paper font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#72a6b5] hover:translate-y-[1px] hover:shadow-none transition-all flex items-center justify-center gap-2"
              >
                <Plus size={24} strokeWidth={3}/> ADD PATH
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 配置面板弹窗部分 */}
      {isConfigOpen && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 md:p-8 pointer-events-auto">
          <div 
            style={sketchyShape2} 
            className="bg-cream border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-5xl h-[80vh] flex flex-row relative"
          >
            <div className="absolute -top-4 left-1/4 w-32 h-10 bg-terracotta/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>
            <button onClick={() => setIsConfigOpen(false)} className="absolute top-4 right-6 hover:rotate-90 hover:text-terracotta transition-all z-10 p-2 bg-paper border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape3}>
              <X size={28} strokeWidth={4} />
            </button>

            {/* 左侧卡片式 Tab 导航 */}
            <div className="w-56 shrink-0 border-r-4 border-ink/20 flex flex-col p-6">
              <div className="pb-6 flex items-center gap-4">
                <Settings size={36} strokeWidth={2.5} className="text-terracotta" />
                <h2 className="text-xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CONFIG</h2>
              </div>
              <div className="flex flex-col gap-4">
                {CONFIG_TABS.map((tab, idx) => {
                  const isActive = activeTab === tab;
                  const rotation = idx % 2 === 0 ? 'rotate-1' : '-rotate-1';
                  const shape = idx % 3 === 0 ? sketchyShape1 : idx % 2 === 0 ? sketchyShape2 : sketchyShape3;
                  return (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      style={shape}
                      className={`px-4 py-2.5 font-black text-base border-4 border-ink uppercase tracking-wider transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]
                        ${isActive ? 'bg-[#EBCB8B] text-ink -translate-x-1' : 'bg-paper text-ink/70 hover:bg-sand'} ${rotation}`}
                    >
                      {tab}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 右侧主配置编辑区 */}
            <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-6">
              {Object.keys(configData).length === 0 ? (
                <div className="text-center font-bold text-ink/40 mt-10 text-xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>No data found or Loading...</div>
              ) : (
                Object.keys(configData).map((key, idx) => {
                  const isExpanded = expandedKey === key;
                  const itemShape = idx % 2 === 0 ? sketchyShape2 : sketchyShape1;

                  return (
                    <div key={key} className="flex flex-col gap-2">
                      <button
                        onClick={() => toggleKey(key)}
                        style={itemShape}
                        className={`w-full text-left p-4 border-4 border-ink flex justify-between items-center transition-all 
                          ${isExpanded ? 'bg-ink text-paper shadow-none' : 'bg-paper text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 hover:shadow-[8px_8px_0px_0px_rgba(26,26,26,1)]'}`}
                      >
                        <div className="flex items-center gap-3">
                          <FileJson size={20} strokeWidth={2.5} className={isExpanded ? 'text-terracotta' : 'text-[#EBCB8B]'} />
                          <span className="text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{key}</span>
                        </div>
                        <span className="font-bold opacity-50 text-sm">{isExpanded ? 'CLOSE' : 'EDIT'}</span>
                      </button>

                      {isExpanded && (
                        <div style={sketchyShape3} className="bg-paper border-4 border-ink p-4 flex flex-col gap-4 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)]">
                          <div className="flex items-center gap-2 text-ink/60 font-bold text-xs bg-terracotta/10 p-2 border-2 border-ink border-dashed" style={sketchyShape1}>
                            <AlertCircle size={14} strokeWidth={3} />
                            注意：请严格遵守 JSON 格式（必须带双引号），否则会保存失败！
                          </div>
                          <textarea
                            value={editJsonStr}
                            onChange={(e) => setEditJsonStr(e.target.value)}
                            className="w-full h-48 bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-sm leading-relaxed font-bold focus:outline-none focus:bg-white resize-y"
                            spellCheck={false}
                          />
                          <div className="flex justify-end">
                            <button
                              onClick={() => handleSaveConfig(key)}
                              style={sketchyShape1}
                              className="px-6 py-2 bg-[#a3be8c] border-4 border-ink text-ink font-black text-lg flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all rotate-1"
                            >
                              <Save size={20} strokeWidth={3} /> SAVE TO DISK
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* 会话切换侧滑列表模态框 */}
      {showSessionModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-2xl w-full h-[80vh]">
            <div className="flex justify-between items-center border-b-4 border-ink/20 pb-4 shrink-0">
              <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SWITCH CHAT</h3>
              <div className="flex items-center gap-4">
                 <button onClick={() => {
                   if (!currentSessionId) {
                     toast.error('请先进入一个对话再拉取分支！');
                     return;
                   }
                   const currentName = sessions.find(s => s.id === currentSessionId)?.alias || 'Current Chat';
                   setBranchAlias(`${currentName} (Branch)`);
                   setShowSessionModal(false);
                   setShowBranchModal(true);
                 }} className="p-2 bg-cream border-4 border-ink hover:bg-sand transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape1} title="Branch (Fork) Current Chat">
                    <GitFork size={24} strokeWidth={3}/>
                 </button>
                 <button onClick={() => { setShowSessionModal(false); setNewAlias('New Chat'); setShowModal(true); }} className="p-2 bg-terracotta text-paper border-4 border-ink hover:bg-[#C46A4A] transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape3} title="New Chat">
                    <Plus size={24} strokeWidth={3}/>
                 </button>
                 <div className="w-1 h-8 bg-ink/20 mx-1 rounded-full"></div>
                 <button onClick={() => setShowSessionModal(false)} className="p-2 hover:text-terracotta hover:scale-110 transition-all">
                    <X size={32} strokeWidth={3}/>
                 </button>
              </div>
            </div>
            
            {/* 🔴 修复穿模：增加了 p-3 和 gap-5 留足旋转空间 */}
            <div className="flex-1 overflow-y-auto flex flex-col gap-5 p-3">
                {sessions.map((session, idx) => (
                  <button
                    key={session.id} 
                    onClick={() => { handleSelectSession(session.id); setShowSessionModal(false); }} 
                    style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                    className={`text-left p-4 border-4 transition-all flex flex-col gap-2 relative group 
                      ${idx % 3 === 0 ? 'rotate-1' : idx % 2 === 0 ? '-rotate-1' : 'rotate-2'}
                      ${currentSessionId === session.id ? 'bg-[#EBCB8B] border-ink text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream border-ink text-ink hover:bg-sand hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-black truncate max-w-[400px] text-xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{session.alias}</span>
                      <div onClick={(e) => { e.stopPropagation(); setSessionToDelete(session.id); setShowSessionModal(false); }} className="p-1.5 hover:text-paper hover:bg-[#bf616a] rounded transition-colors border-2 border-transparent hover:border-ink" title="Delete Chat">
                        <Trash2 size={20} strokeWidth={2.5} className={currentSessionId === session.id ? 'opacity-100' : 'opacity-40'} />
                      </div>
                    </div>
                    <div className={`flex items-center gap-3 text-sm font-bold opacity-70`}>
                      <Clock size={16} strokeWidth={3} /> {session.updated_at}
                    </div>
                  </button>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* --- 左侧多功能聚合面板 --- */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          {/* 返回按钮 */}
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group" title="Back">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          
          {/* 🌟 新增：移动到这里的 TASK 纯图标按钮 */}
          <button onClick={onSwitchToTask || (() => navigate('/task'))} style={sketchyShape3} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-[#D8E2DC] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none rotate-3 hover:rotate-0 group" title="Go to Task">
            <Terminal size={28} strokeWidth={3} className="text-ink group-hover:translate-x-1 transition-transform" />
          </button>

          {/* SWITCH 按钮 */}
          <button onClick={() => setShowSessionModal(true)} style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#EBCB8B] text-ink border-4 border-ink hover:bg-[#d8b877] transition-all active:scale-95 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2 hover:-rotate-1">
            <List size={22} strokeWidth={3} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SWITCH</span>
          </button>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          
          {/* 主菜单模式 */}
          {sidebarMode === 'menu' && (
             <div className="flex-1 flex flex-col gap-5 p-2 mt-2 overflow-y-auto">
                 <button onClick={() => navigate('/memory')} style={sketchyShape1} className="flex-1 border-4 border-ink bg-[#FFB5A7]/40 hover:bg-[#FFB5A7] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-1 active:shadow-none active:translate-y-1">
                     <Brain size={28} strokeWidth={2.5} className="text-[#c76c6c]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEMORY</span>
                 </button>
                 <button onClick={() => {setSidebarMode('mcp'); fetchMcp();}} style={sketchyShape2} className="flex-1 border-4 border-ink bg-[#F9E2AF]/50 hover:bg-[#F9E2AF] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-1 active:shadow-none active:translate-y-1">
                     <Server size={28} strokeWidth={2.5} className="text-[#b8956e]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP</span>
                 </button>
                 <button onClick={() => {setSidebarMode('skill'); fetchSkill();}} style={sketchyShape3} className="flex-1 border-4 border-ink bg-[#FCD5CE]/50 hover:bg-[#FCD5CE] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-2 active:shadow-none active:translate-y-1">
                     <Zap size={28} strokeWidth={2.5} className="text-[#d08770]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILL</span>
                 </button>
                 <button onClick={() => {setSidebarMode('cron'); fetchCron();}} style={sketchyShape1} className="flex-1 border-4 border-ink bg-[#E8D1C5]/50 hover:bg-[#E8D1C5] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1">
                     <AlarmClock size={28} strokeWidth={2.5} className="text-[#a07b8a]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CRON</span>
                 </button>
                 {/* 新增的 SOUL 按钮 */}
                 <button onClick={() => openMdEditor('SOUL')} style={sketchyShape2} className="flex-1 border-4 border-ink bg-[#b48ead]/50 hover:bg-[#b48ead] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                     <FileText size={28} strokeWidth={2.5} className="text-[#8f6a88]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SOUL</span>
                 </button>
                 {/* 新增的 SOLO 按钮 */}
                 <button onClick={() => openMdEditor('SOLO')} style={sketchyShape3} className="flex-1 border-4 border-ink bg-[#88c0d0]/50 hover:bg-[#88c0d0] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                     <User size={28} strokeWidth={2.5} className="text-[#5e81ac]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SOLO</span>
                 </button>

                 {/* 新增的 TODO 按钮 */}
                 <button onClick={() => openMdEditor('TODO')} style={sketchyShape1} className="flex-1 border-4 border-ink bg-[#EBCB8B]/50 hover:bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1 min-h-[60px]">
                     <List size={28} strokeWidth={2.5} className="text-[#b8956e]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TODO</span>
                 </button>

                 {/* 新增：手绘风 CONFIG 功能按钮 */}
                 <button onClick={() => {setSidebarMode('sensor'); fetchSensorData();}} style={sketchyShape3} className="flex-1 border-4 border-ink bg-[#EBCB8B]/40 hover:bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1 min-h-[60px]">
                     <Activity size={28} strokeWidth={2.5} className="text-[#b8956e]"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSOR</span>
                 </button>
             </div>
          )}

          {/* MCP 子面板 */}
          {sidebarMode === 'mcp' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
                 <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                     <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                     <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP SERVERS</span>
                     
                     {/* 🌟 修改：右侧增加配置/下载按钮和刷新按钮 */}
                     <div className="flex items-center gap-2">
                        <button onClick={() => setShowInstallMcpModal(true)} className="p-1 bg-[#88c0d0] text-paper border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-all" title="Install new MCP">
                           <Plus size={18} strokeWidth={3}/>
                        </button>
                        <button onClick={refreshMcp} className="p-1 bg-[#F9E2AF] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all">
                           <RefreshCw size={18} strokeWidth={3}/>
                        </button>
                     </div>
                 </div>
                 {/* 🔴 修复穿模：增加 p-2 和 gap-4 */}
                 <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                    {Object.keys(mcpData).length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No MCP loaded</p> :
                      Object.entries(mcpData).map(([server, tools], idx) => (
                        <div key={server} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${expandedMcp === server ? 'shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-1' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 cursor-pointer'}`}>
                            <div className="flex justify-between items-center" onClick={() => setExpandedMcp(expandedMcp === server ? null : server)}>
                               <span className="font-black text-lg truncate flex-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{server}</span>
                               <span className="shrink-0">{expandedMcp === server ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}</span>
                            </div>
                            {expandedMcp === server && (
                                <div className="mt-3 flex flex-col gap-3 border-t-2 border-ink/20 pt-3 border-dashed">
                                   {tools.map((t: any) => (
                                      <div key={t.name} className="text-sm">
                                         <div className="font-bold text-terracotta break-all">{t.name}</div>
                                         <div className="opacity-70 text-xs mt-1 leading-relaxed">{t.description}</div>
                                      </div>
                                   ))}
                                </div>
                            )}
                        </div>
                    ))}
                 </div>
             </div>
          )}

          {/* Skill 子面板 */}
          {sidebarMode === 'skill' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
                 <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                     <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                     <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILLS</span>
                     
                     {/* 🌟 修改：右侧增加下载按钮和刷新按钮 */}
                     <div className="flex items-center gap-2">
                        <button onClick={() => setShowInstallSkillModal(true)} className="p-1 bg-terracotta text-paper border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-all" title="Install new Skill">
                           <Plus size={18} strokeWidth={3}/>
                        </button>
                        <button onClick={refreshSkill} className="p-1 bg-[#FCD5CE] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all">
                           <RefreshCw size={18} strokeWidth={3}/>
                        </button>
                     </div>
                 </div>
                 {/* 🔴 修复穿模：增加 p-2 和 gap-4 */}
                 <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                    {skillData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Skills loaded</p> :
                      skillData.map((skill: any, idx) => (
                        <div key={skill.name} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`border-4 border-ink bg-cream p-3 transition-all ${expandedSkill === skill.name ? 'shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-1' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 cursor-pointer'}`}>
                            <div className="flex justify-between items-center" onClick={() => setExpandedSkill(expandedSkill === skill.name ? null : skill.name)}>
                               <span className="font-black text-lg truncate flex-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{skill.name}</span>
                               <span className="shrink-0">{expandedSkill === skill.name ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}</span>
                            </div>
                            {expandedSkill === skill.name && (
                                <div className="mt-3 flex flex-col gap-2 border-t-2 border-ink/20 pt-2 border-dashed">
                                   <div className="opacity-80 text-xs font-bold leading-relaxed">{skill.description}</div>
                                </div>
                            )}
                        </div>
                    ))}
                 </div>
             </div>
          )}

          {/* Cron 子面板 */}
          {sidebarMode === 'cron' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
                 <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                     <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                     <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>ALARMS</span>
                     <button onClick={fetchCron} className="p-1 bg-[#E8D1C5] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all"><RefreshCw size={18} strokeWidth={3}/></button>
                 </div>
                 {/* 🔴 修复穿模：增加 p-2 和 gap-4 */}
                 <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                    {cronData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Alarms configured</p> :
                      cronData.map((cron: any, idx) => (
                        <div key={cron.id || cron.title} style={idx % 2 === 0 ? sketchyShape3 : sketchyShape1} className={`border-4 border-ink bg-cream p-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-1 relative group ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'}`}>
                           <div className="flex justify-between items-center">
                              <span className="font-black text-lg truncate pr-6">{cron.title}</span>
                              <button onClick={()=>deleteCron(cron.id || cron.title)} className="absolute top-2 right-2 p-1 bg-[#bf616a] text-paper border-2 border-ink rounded hover:scale-110 transition-transform opacity-0 group-hover:opacity-100"><Trash2 size={14} strokeWidth={3}/></button>
                           </div>
                           <div className="text-xs font-bold text-ink/70 flex items-center gap-1 mt-1"><Clock size={12}/> Time: {cron.trigger_time}</div>
                           <div className="text-xs font-bold text-ink/70 flex items-center gap-1"><AlarmClock size={12}/> Status: {cron.status || 'Active'}</div>
                        </div>
                    ))}
                 </div>
                 <button onClick={()=>setShowAddCronModal(true)} style={sketchyShape2} className="shrink-0 p-3 bg-[#E8D1C5] text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-1 hover:shadow-none transition-all flex items-center justify-center gap-2 mt-2">
                    <Plus size={20} strokeWidth={3}/> ADD ALARM
                 </button>
             </div>
          )}

          {/* Sensor 子面板 */}
          {sidebarMode === 'sensor' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
                 <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                     <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                     <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSORS</span>
                     
                     <div className="flex items-center gap-2">
                        <button onClick={() => setShowInstallSensorModal(true)} title="Add Sensor via JSON" className="p-1 bg-[#a3be8c] text-ink border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-all">
                           <Plus size={18} strokeWidth={3}/>
                        </button>
                        <button onClick={reloadSensors} title="强制热重启" className="p-1 bg-[#EBCB8B] text-ink border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all">
                           <RefreshCw size={18} strokeWidth={3}/>
                        </button>
                     </div>
                 </div>
                 
                 <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                    {!sensorData || Object.keys(sensorData).length === 0 ? (
                        <p className="font-bold text-center mt-6 opacity-50 text-sm">No Sensors found</p>
                    ) : (
                      Object.entries(sensorData).map(([name, cfg]: [string, any], idx) => (
                        <div key={name} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className="border-4 border-ink bg-cream p-3 transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-2 relative">
                            
                            <div className="flex justify-between items-center pr-2">
                               <span className="font-black text-[17px] truncate max-w-[150px]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{name}</span>
                               
                               <button 
                                 onClick={() => toggleSensorStatus(name)} 
                                 className={`relative w-12 h-6 border-2 border-ink flex items-center px-1 transition-colors shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] cursor-pointer active:translate-y-[1px] active:shadow-none 
                                   ${cfg.enabled ? 'bg-[#a3be8c] justify-end' : 'bg-ink/10 justify-start'}`} 
                                 style={sketchyShape1} 
                                 title={cfg.enabled ? "Click to Disable" : "Click to Enable"} 
                               > 
                                 <div className="w-3.5 h-3.5 bg-ink" style={sketchyShape3}></div> 
                               </button>
                            </div>

                            {cfg.description && (
                                <div className="text-xs font-bold opacity-70 leading-relaxed mt-1">
                                    {cfg.description}
                                </div>
                            )}

                            <div className="flex gap-2 mt-2 border-t-2 border-ink/10 pt-2 border-dashed">
                               {cfg.capabilities?.observe && (
                                   <div 
                                      title="Observe (接收输入)" 
                                      className="w-4 h-4 bg-[#88c0d0] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-transform rotate-3" 
                                      style={sketchyShape2} 
                                   ></div> 
                               )}
                               {cfg.capabilities?.express && (
                                   <div 
                                      title="Express (主动输出)" 
                                      className="w-4 h-4 bg-[#EBCB8B] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-transform -rotate-3" 
                                      style={sketchyShape1} 
                                   ></div> 
                               )}
                            </div>
                        </div>
                    )))}
                 </div>
             </div>
          )}

        </div>
      </div>

      {/* --- 右侧大聊天纸板 --- */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-10">
        
        {/* 🌟 改造原本的黄色小胶带：有会话时显示 ID，无会话时作为纯装饰 */}
        {currentSessionId ? (
          <div className="absolute -top-2 right-12 px-6 py-1 bg-[#a3be8c] border-2 border-ink rotate-2 z-50 text-ink font-black text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center" style={sketchyShape2} title="Session ID">
            ID: {currentSessionId.split('_')[1] || currentSessionId.slice(-8)}
          </div>
        ) : (
          <div className="absolute -top-4 right-12 w-32 h-8 bg-[#a3be8c]/80 border-2 border-ink -rotate-3 z-50" style={sketchyShape2}></div>
        )}

        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            <div style={sketchyShape1} className="w-12 h-12 bg-terracotta border-4 border-ink flex items-center justify-center -rotate-6 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]">
              <Cat size={28} className="text-paper" strokeWidth={2.5} />
            </div>
            <h2 className="text-4xl font-black tracking-tighter text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat.</h2>
          </div>
          
          <div className="flex items-center gap-3">
             {/* 原本涂鸦风 Token 进度条 */}
             {currentSessionId && (
               <div className="flex items-center gap-2" title={`Token: ${tokenData.window} / ${tokenData.max}`}>
                 <span className="text-[11px] font-black text-ink/50" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEM</span>
                 <div className="w-36 h-[14px] border-2 border-ink bg-cream p-[2px]" style={sketchyShape3}>
                   <div 
                     className="h-full transition-all duration-1000 ease-out border-r-2 border-ink" 
                     style={{ 
                       width: `${Math.min(100, (tokenData.window / tokenData.max) * 100)}%`, 
                       // 核心魔法：CSS 实现马克笔斜线排线（Hatched）效果 
                       backgroundImage: (tokenData.window / tokenData.max) > 0.8 
                          ? 'repeating-linear-gradient(45deg, #bf616a, #bf616a 2px, transparent 2px, transparent 6px)' 
                          : 'repeating-linear-gradient(-45deg, #d08770, #d08770 2px, transparent 2px, transparent 6px)', 
                       backgroundColor: (tokenData.window / tokenData.max) > 0.8 ? 'rgba(191,97,106,0.1)' : 'rgba(208,135,112,0.1)', 
                       ...sketchyShape1 
                     }} 
                   />
                 </div>
                 <span className="text-[11px] font-black text-ink/70 w-8 text-right">
                   {Math.round((tokenData.window / tokenData.max) * 100)}%
                 </span>
               </div>
             )}

             {/* 🌟 新增：文件变更视图按钮 */}
             <button
                onClick={() => setShowFileView(!showFileView)}
                className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none ${showFileView ? 'bg-[#88c0d0] text-paper' : 'bg-cream text-ink'}`}
                style={sketchyShape3}
                title="File Changes"
             >
               <FolderOpen size={20} strokeWidth={3} />
               {fileChanges.length > 0 && (
                 <span className="absolute -top-2 -right-2 bg-[#d08770] text-paper text-xs px-1.5 py-0.5 rounded-full border-2 border-ink">
                   {fileChanges.length}
                 </span>
               )}
             </button>

             {/* 🌟 新增：审批队列触发按钮 - 只显示图标 */}
             <button
                onClick={() => setShowReqQueue(!showReqQueue)}
                className={`relative w-10 h-10 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all flex items-center justify-center hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none ${pendingReqs.length > 0 ? 'bg-[#EBCB8B] text-ink animate-pulse' : 'bg-cream text-ink'}`}
                style={sketchyShape2}
                title="Requests Queue"
             >
               <Bell size={20} strokeWidth={3} />
               {pendingReqs.length > 0 && (
                 <span className="absolute -top-2 -right-2 bg-[#bf616a] text-paper text-xs px-1.5 py-0.5 rounded-full border-2 border-ink">
                   {pendingReqs.length}
                 </span>
               )}
             </button>
          </div>
        </div>

        {/* ==================== 🌟 核心新增：书签/抽屉式多分支切换导航栏 ==================== */}
        {currentSessionId && Object.keys(branches).length > 1 && (
          <div className="px-10 flex gap-3 overflow-x-auto shrink-0 pb-3 border-b-4 border-ink/10 pt-1 select-none">
            {Object.keys(branches).map((bId) => {
              const isActive = currentBranchId === bId;
              const label = bId === 'main' ? 'MAIN' : `${bId.split('_')[1] || bId}`;
              
              return (
                <div key={bId} className="relative group flex items-center">
                  <button
                    onClick={() => {
                      setCurrentBranchId(bId);
                      loadSessionHistory(currentSessionId, bId);
                    }}
                    style={isActive ? sketchyShape1 : sketchyShape2}
                    className={`px-4 py-1.5 font-black text-xs tracking-wider border-2 border-ink transition-all active:translate-y-0.5 active:shadow-none 
                      ${bId !== 'main' ? 'pr-8' : ''} 
                      ${isActive 
                        ? 'bg-[#EBCB8B] text-ink border-solid scale-105 z-10 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]' 
                        : 'bg-cream text-ink/80 border-solid hover:bg-sand hover:text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-[1px]'}`}
                  >
                    {label}
                  </button>
                  
                  {/* 🌟 修复：点击 X 时，触发手绘风弹窗而不是系统默认 confirm */}
                  {bId !== 'main' && (
                    <button
                       onClick={(e) => {
                         e.stopPropagation();
                         setBranchToDelete(bId); // 👈 在这里触发状态
                       }}
                       className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-0.5 bg-[#bf616a] text-paper border-2 border-ink rounded transition-all hover:scale-110 z-20 cursor-pointer"
                       title="彻底删除此支线"
                    >
                       <X size={12} strokeWidth={3} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {/* ================================================================================== */}

        <div ref={messagesContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-10 pb-6 flex flex-col gap-6 w-full z-10 pt-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-ink gap-6">
              <div style={sketchyShape1} className="p-8 border-4 border-ink bg-cream shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] -rotate-3">
                <Cat size={80} strokeWidth={1.5} className="text-terracotta" />
              </div>
              <p className="text-2xl font-black rotate-2 text-ink/60" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Waiting for your command...</p>
            </div>
          ) : (
            messages.map((msg, idx) => {
              if (msg.role === 'user') {
                const parsedData = parseEventsContent(msg.content);
                return (
                  <div key={idx} className="flex flex-col w-full items-end mb-4">
                    
                    {/* 渲染被批注入的 附件 和 Skill 小气泡 */}
                    {parsedData.attachments.length > 0 && (
                      <div className="flex flex-col gap-2 w-full items-end mb-2">
                        {parsedData.attachments.map((att, aIdx) => (
                          <div key={`att-${aIdx}`} style={sketchyShape3} className="px-4 py-2 bg-ink/5 border-2 border-ink text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center gap-2 max-w-[70%]">
                            {att.type === 'file-quote' ? <Paperclip size={14} className="shrink-0"/> : <Zap size={14} className="text-terracotta shrink-0"/>}
                            <span className="font-bold text-xs opacity-80 font-mono truncate">{att.content}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 渲染用户的真实发言内容 */}
                    {parsedData.userMessages.map((userMsg, uIdx) => (
                      <div key={`u-${uIdx}`} className={`flex flex-col gap-3 w-full max-w-[85%] items-end`}>
                        {userMsg.content && (
                          <div style={sketchyShape2} className="w-full p-6 border-4 border-ink relative bg-cream text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]">
                            <div className="text-[17px] font-bold text-ink">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{userMsg.content}</ReactMarkdown>
                            </div>
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
                    <div className={`flex flex-col gap-3 w-full max-w-[85%] items-start`}>
                      {msg.content && (
                        <div style={sketchyShape1} className="w-full p-6 border-4 border-ink relative bg-cream text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]">
                          <div>
                            <div className="flex items-center gap-2 mb-4">
                              <Cat size={20} strokeWidth={2.5}/>
                              <span className="font-black text-sm uppercase tracking-widest bg-ink text-paper px-2 py-0.5" style={{ ...sketchyShape3, fontFamily: '"Comic Sans MS", cursive' }}>ASSISTANT</span>
                            </div>
                            <div className="text-[17px] font-bold text-ink">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{msg.content}</ReactMarkdown>
                            </div>
                          </div>
                        </div>
                      )}
                      {msg.tool_calls && msg.tool_calls.map((tc, t_idx) => (
                        <ToolCallBubble key={`tc-${t_idx}`} tc={tc} />
                      ))}
                    </div>
                  </div>
                );
              }
            })
          )}

          {/* 🌟 修复：只在主干分支显示大模型的思考/休眠状态 */}
          {currentBranchId === 'main' && (
            <div className="flex justify-start mb-4 w-full">
              <div style={sketchyShape1} className={`p-4 w-fit transition-colors ${isAgentThinking ? 'bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-paper text-ink/40'}`}>
                <div className="flex items-center gap-3 px-2">
                  {isAgentThinking ? <Loader2 size={20} strokeWidth={3} className="animate-spin text-terracotta" /> : <Clock size={20} strokeWidth={3} className="text-ink/30" />}
                  <span className="font-black text-sm tracking-widest uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{isAgentThinking ? 'Processing...' : 'Dozing...'}</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} className="h-2" />
        </div>

        {/* 🌟 新增：文件变更视图 */}
        {showFileView && (
          <div className="px-10 pb-6 pt-2">
            <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-6">
              <div className="flex items-center gap-3 mb-4">
                <History size={28} strokeWidth={2.5} className="text-[#d08770]" />
                <h2 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  FILE CHANGES
                  <span className="ml-2 text-sm opacity-60">({fileChanges.length})</span>
                </h2>
              </div>

              {fileChanges.length === 0 ? (
                <div className="flex flex-col items-center py-10 opacity-50">
                  <CheckCircle size={48} strokeWidth={1.5} />
                  <p className="font-bold text-sm mt-2">No file changes yet!</p>
                </div>
              ) : (
                <div className="flex flex-col gap-4 max-h-[400px] overflow-y-auto">
                  {fileChanges.map((change, idx) => (
                    <div 
                      key={change.id} 
                      className={`bg-cream border-4 border-ink p-4 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all hover:-translate-y-0.5 ${idx % 2 === 0 ? 'rotate-0.5' : '-rotate-0.5'}`}
                      style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div className="flex items-center gap-2">
                          <FileText size={16} strokeWidth={3} className="text-[#88c0d0]" />
                          <span className="font-black text-sm text-ink truncate max-w-[300px]">{change.path}</span>
                        </div>
                        <span className="text-[10px] font-bold opacity-60 bg-paper px-2 py-0.5 border-2 border-ink">{change.time}</span>
                      </div>

                      {/* Diff 渲染 */}
                      <div className="bg-[#FDF8F0] p-3 border-2 border-ink/20 font-mono text-sm overflow-x-auto">
                        {change.diff.split('\n').map((line: string, i: number) => {
                          let colorClass = 'text-ink/70';
                          if (line.startsWith('+')) colorClass = 'text-[#a3be8c]';
                          if (line.startsWith('-')) colorClass = 'text-[#bf616a]';
                          if (line.startsWith('@')) colorClass = 'text-[#88c0d0]';
                          return (
                            <div key={i} className={`${colorClass} leading-relaxed ${line.startsWith('+') || line.startsWith('-') ? 'pl-2' : ''}`}>
                              {line || '\u00A0'}
                            </div>
                          );
                        })}
                      </div>

                      {/* 确认 / 回滚操作栏 */}
                      <div className="flex gap-4 mt-3">
                        <button
                          onClick={() => handleAck(change.id, change.path, change.backup_id)}
                          className="flex-1 bg-cream text-ink font-black py-2.5 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a3be8c] active:translate-y-1 active:shadow-none transition-all flex justify-center items-center gap-2"
                          style={sketchyShape2}
                        >
                          <CheckCircle size={18} strokeWidth={3}/> ACKNOWLEDGE
                        </button>
                        
                        <button
                          onClick={() => handleRollback(change.id, change.path, change.backup_id)}
                          className="flex-1 bg-[#bf616a] text-paper font-black py-2.5 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-1 active:shadow-none transition-all flex justify-center items-center gap-2"
                          style={sketchyShape3}
                        >
                          <Undo2 size={18} strokeWidth={3}/> ROLLBACK
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 🌟 修复：完全隔离的底部操作栏 - 子分支下变成全局 Read-Only 提示 */}
        {currentBranchId === 'main' ? (
          <div className="px-10 pb-8 pt-4 shrink-0 flex flex-col gap-3 w-full">

           {/* 渲染已选的 Skill 和 引入的文件路径 */}
           {(selectedSkills.length > 0 || refPaths.length > 0) && (
             <div className="flex flex-wrap gap-2">
               {selectedSkills.map(skill => (
                 <div key={skill} style={sketchyShape3} className="flex items-center gap-1 bg-[#F9E2AF] border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]">
                   <span>⚡ {skill}</span>
                   <button onClick={() => setSelectedSkills(prev => prev.filter(s => s !== skill))} className="hover:text-terracotta ml-1"><X size={14} strokeWidth={3}/></button>
                 </div>
               ))}
               {/* 🌟 渲染已引入的路径标签 */}
               {refPaths.map(path => (
                 <div key={path} style={sketchyShape1} className="flex items-center gap-1 bg-[#88c0d0] border-2 border-ink px-3 py-1 font-bold text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]">
                   <span className="truncate max-w-[200px]">📎 {path}</span>
                   <button onClick={() => setRefPaths(prev => prev.filter(p => p !== path))} className="hover:text-paper ml-1"><X size={14} strokeWidth={3}/></button>
                 </div>
               ))}
             </div>
           )}

           {/* 在输入框外层套一个 Drag 区域 */}
           <div 
             className={`flex gap-4 relative transition-all ${isDragging ? 'ring-4 ring-terracotta bg-terracotta/5' : ''}`}
             onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }} 
             onDragLeave={() => setIsDragging(false)} 
             onDrop={handleDrop}
           >
             
             {/* 拖拽时的手绘风遮罩 */}
             {isDragging && (
               <div className="absolute inset-0 z-50 flex items-center justify-center bg-cream/90 border-4 border-dashed border-terracotta" style={sketchyShape2}>
                 <span className="text-2xl font-black text-terracotta">Drop files here to attach!</span>
               </div>
             )}

             <div className="flex-1 relative flex flex-col">
               <textarea
                 style={sketchyShape3} value={input} onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                 onPaste={handlePaste}
                 placeholder={currentSessionId ? "Write your prompt here..." : "Select a chat first!"} disabled={!currentSessionId} rows={2}
                 className="w-full bg-[#FDF8F0] border-4 border-ink p-5 pr-28 font-bold focus:outline-none focus:bg-white transition-all shadow-[inset_4px 4px 0px 0px_rgba(26,26,26,0.05)] resize-none text-lg -rotate-[0.5deg] placeholder:text-ink/30"
               />
               
               {/* 按钮组 */}
               <div className="absolute right-3 bottom-3 flex items-center gap-2 z-10">
                 {/* 🌟 修改：引用文件按钮 */}
                <button
                  onClick={handleAttachmentClick}
                  className="p-2 bg-cream border-2 border-ink hover:bg-[#88c0d0] transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"
                  style={sketchyShape1}
                  title="引用本地文件或文件夹"
                >
                   <Paperclip className="text-ink" size={20} strokeWidth={3}/>
                 </button>

                 {/* 原有的 Skill 按钮 */}
                 <button
                   onClick={() => { 
                     if (skillData.length === 0) fetchSkill(); 
                     setTempSelectedSkills([...selectedSkills]); 
                     setShowSkillSelectModal(true); 
                   }}
                   className="p-2 bg-cream border-2 border-ink hover:bg-[#F9E2AF] transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]"
                   style={sketchyShape2}
                   title="Select Skills"
                 >
                   <Zap className="text-ink" size={20} strokeWidth={3}/>
                 </button>
               </div>
             </div>
             <button
               style={sketchyShape1} onClick={handleSend} disabled={!currentSessionId || !input.trim()}
               className="bg-ink text-paper px-10 font-black flex items-center gap-3 border-4 border-ink hover:bg-terracotta hover:text-ink transition-all active:scale-95 disabled:opacity-50 shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] rotate-2 min-h-[80px] self-end"
             >
               <Send size={26} strokeWidth={2.5} />
             </button>
           </div>
        </div>
          ) : (
            <div className="px-10 pb-8 pt-4 shrink-0 flex justify-center w-full">
               <div style={sketchyShape3} className="bg-cream border-4 border-ink px-10 py-5 font-black text-ink/50 tracking-widest uppercase shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] flex items-center gap-3">
                  🔒 READ-ONLY SUB-BRANCH VIEW
               </div>
            </div>
          )}
      </div>

      {/* --- 🌟 新增：右侧 Request 请求处理队列纸板 --- */}
      {showReqQueue && (
        <div style={sketchyShape3} className="w-[340px] shrink-0 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-20">
          {/* Header */}
          <div className="flex flex-col shrink-0 p-4 bg-paper">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <Bell size={24} strokeWidth={2.5} className="text-[#EBCB8B]" />
                <h3 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  PENDING
                  {pendingReqs.length > 0 && ` (${pendingReqs.length})`}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setShowReqQueue(false)} className="hover:text-terracotta hover:rotate-90 transition-all p-1 bg-paper border-2 border-ink" style={sketchyShape1}>
                  <X size={20} strokeWidth={3} />
                </button>
              </div>
            </div>
          </div>

          {/* 列表渲染区 */}
          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4 bg-paper">
            {pendingReqs.length === 0 ? (
              <div className="flex flex-col items-center opacity-50 mt-10">
                <Activity size={48} strokeWidth={1.5} />
                <p className="font-bold text-sm mt-2">All caught up! No requests.</p>
              </div>
            ) : (
              pendingReqs.map((req, idx) => (
                <div key={req.id} className={`bg-paper border-4 border-ink p-4 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-3 relative transition-all hover:-translate-y-1 group ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'}`} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}>
                  {/* 悬浮时右上角显示IGNORE按钮 */}
                  <button 
                    onClick={() => handleResolveReq(req.id, false, true)} 
                    className="opacity-0 group-hover:opacity-100 p-1.5 bg-ink text-paper border-2 border-ink hover:scale-110 transition-all absolute -top-2 -right-2 z-10" 
                    style={sketchyShape2} 
                    title="Ignore (Silent)"
                  >
                    <X size={12} strokeWidth={3} />
                  </button>

                  <div className="flex justify-between items-start">
                    <span className="font-black text-xs uppercase px-2 py-0.5 bg-[#EBCB8B] border-2 border-ink" style={sketchyShape1}>{req.type}</span>
                    <span className="text-[10px] font-bold opacity-60 bg-cream px-1">{req.created_at?.split(' ')[1]}</span>
                  </div>
                  
                  <div>
                    <div className="text-[15px] font-black text-ink break-all leading-tight">{req.target}</div>
                    
                    {/* Reason 折叠显示 */}
                    <button 
                      onClick={() => setExpandedReasons({...expandedReasons, [req.id]: !expandedReasons[req.id]})}
                      className="text-xs font-bold text-ink/50 mt-2 flex items-center gap-1 hover:text-ink transition-colors"
                    >
                      {expandedReasons[req.id] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      Reason
                    </button>
                    {expandedReasons[req.id] && (
                      <div className="text-xs font-bold text-ink/70 bg-ink/5 p-2 mt-1 leading-relaxed">{req.reason}</div>
                    )}
                  </div>

                  <input
                    value={feedbackInputs[req.id] || ''}
                    onChange={e => setFeedbackInputs({...feedbackInputs, [req.id]: e.target.value})}
                    placeholder="Feedback (Optional)..."
                    className="w-full text-xs font-bold p-2 border-2 border-ink focus:outline-none bg-[#FDF8F0] shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30"
                    style={sketchyShape2}
                  />

                  <div className="flex gap-2 mt-1">
                    <button onClick={() => handleResolveReq(req.id, true, false)} className="flex-1 bg-[#a3be8c] text-ink font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all flex justify-center items-center" style={sketchyShape1}>
                      APPROVE
                    </button>
                    <button onClick={() => handleResolveReq(req.id, false, false)} className="flex-1 bg-[#bf616a] text-paper font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-1 active:shadow-none transition-all" style={sketchyShape2}>
                      REJECT
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

    </div>
  );
}