import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, Send, Cat, Clock, Wrench, Package, 
  ChevronDown, ChevronUp, Loader2, X, Trash2, 
  List, Brain, Server, Zap, AlarmClock, GitFork, Plus,
  RefreshCw, Terminal
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

function parseEventsContent(content: string): { userMessages: EventItem[], systemCount: number } {
  const userMessages: EventItem[] = [];
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
        } else {
          systemCount++;
        }
      }
    }
  } catch (e) {
    userMessages.push({ type: 'user', time: '', content });
  }
  
  return { userMessages, systemCount };
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
    const isInline = !className?.includes('language-');
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

  // --- 弹窗与控制状态 ---
  const [showSessionModal, setShowSessionModal] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [newAlias, setNewAlias] = useState('');
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [isAgentThinking, setIsAgentThinking] = useState(false);

  // --- 侧边栏面板状态 ---
  const [sidebarMode, setSidebarMode] = useState<'menu' | 'mcp' | 'skill' | 'cron'>('menu');
  const [mcpData, setMcpData] = useState<Record<string, any[]>>({});
  const [expandedMcp, setExpandedMcp] = useState<string | null>(null);
  
  const [skillData, setSkillData] = useState<any[]>([]);
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  
  const [cronData, setCronData] = useState<any[]>([]);
  const [showAddCronModal, setShowAddCronModal] = useState(false);
  const [newCron, setNewCron] = useState({ title: '', trigger_time: '', repeat_rule: 'none' });

  // --- API 交互 (MCP, Skill, Cron) ---
  const fetchMcp = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/mcp');
      if (res.ok) setMcpData(await res.json());
    } catch (e) { toast.error("获取 MCP 列表失败"); }
  };

  const refreshMcp = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/mcp/refresh', { method: 'POST' });
      if (res.ok) { toast.success("MCP 工具已刷新"); fetchMcp(); }
    } catch (e) { toast.error("刷新 MCP 失败"); }
  };

  const fetchSkill = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/skills');
      if (res.ok) setSkillData(await res.json());
    } catch (e) { toast.error("获取 Skill 列表失败"); }
  };

  const refreshSkill = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/skills/refresh', { method: 'POST' });
      if (res.ok) { toast.success("Skills 已刷新"); fetchSkill(); }
    } catch (e) { toast.error("刷新 Skill 失败"); }
  };

  const fetchCron = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tools/cron');
      if (res.ok) setCronData(await res.json());
    } catch (e) { toast.error("获取闹钟列表失败"); }
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
    } catch (e) { toast.error("添加闹钟失败"); }
  };

  const deleteCron = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/tools/cron/${id}`, { method: 'DELETE' });
      if (res.ok) { toast.success("闹钟已删除"); fetchCron(); }
    } catch (e) { toast.error("删除闹钟失败"); }
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
    } catch (e) { toast.error("删除失败，请检查网络"); }
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const isAutoScroll = useRef(true);

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

  useEffect(() => {
    if (sessionId && sessionId !== currentSessionId) {
      setCurrentSessionId(sessionId);
      loadSessionHistory(sessionId);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!currentSessionId) return;
    const interval = setInterval(async () => {
      if (isCheckingOut) return;
      try {
        const [msgRes, statusRes] = await Promise.all([
          fetch(`http://localhost:8000/api/sessions/${currentSessionId}`),
          fetch(`http://localhost:8000/api/sessions/${currentSessionId}/status`)
        ]);

        if (msgRes.ok) {
          const history = await msgRes.json();
          setMessages(history);
        }
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          setIsAgentThinking(statusData.is_thinking);
        }
      } catch (e) {
        console.error('Error checking agent status:', e);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [currentSessionId, isCheckingOut]);

  const loadSessions = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/sessions');
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
        if (data.length > 0 && !currentSessionId) {
          const firstSessionId = data[0].id;
          setCurrentSessionId(firstSessionId);
          await loadSessionHistory(firstSessionId);
        }
      }
    } catch (e) { toast.error("获取会话失败"); }
  };

  const loadSessionHistory = async (id: string) => {
    const res = await fetch(`http://localhost:8000/api/sessions/${id}`);
    if (res.ok) {
      const history = await res.json();
      setMessages(history);
    }
  };

  const handleSelectSession = async (id: string) => {
    setIsCheckingOut(true);
    setCurrentSessionId(id);
    navigate(`/chat/${id}`, { replace: true });
    isAutoScroll.current = true;
    try {
      await fetch(`http://localhost:8000/api/sessions/${id}/checkout`, { method: 'POST' }).catch(() => {});
      await loadSessionHistory(id);
    } catch (e) { 
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
    } catch (e) { 
      toast.error('创建失败'); 
      setIsCheckingOut(false); 
    }
  };

  const handleSend = async () => {
    if (!input.trim() || !currentSessionId) return;
    const userText = input.trim();
    setInput('');
    isAutoScroll.current = true;
    setMessages(prev => [...prev, { role: 'user', content: userText }]);

    try {
      await fetch('http://localhost:8000/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, message: userText }),
      });
    } catch (e) { toast.error('网络错误'); }
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

      {/* 会话切换侧滑列表模态框 */}
      {showSessionModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-2xl w-full h-[80vh]">
            <div className="flex justify-between items-center border-b-4 border-ink/20 pb-4 shrink-0">
              <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SWITCH CHAT</h3>
              <div className="flex items-center gap-4">
                 <button className="p-2 bg-cream border-4 border-ink hover:bg-sand transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape1} title="Branch (Fork) - Coming Soon">
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
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          <button onClick={() => setShowSessionModal(true)} style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#EBCB8B] text-ink border-4 border-ink hover:bg-[#d8b877] transition-all active:scale-95 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2 hover:-rotate-1">
            <List size={22} strokeWidth={3} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SWITCH</span>
          </button>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          
          {/* 主菜单模式 🔴 更新了马卡龙暖色系 */}
          {sidebarMode === 'menu' && (
             <div className="flex-1 flex flex-col gap-5 p-2 mt-2">
                 <button onClick={() => navigate('/memory')} style={sketchyShape1} className="flex-1 border-4 border-ink bg-[#FFB5A7] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-1 active:shadow-none active:translate-y-1">
                     <Brain size={28} strokeWidth={2.5} className="text-ink"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEMORY</span>
                 </button>
                 <button onClick={() => {setSidebarMode('mcp'); fetchMcp();}} style={sketchyShape2} className="flex-1 border-4 border-ink bg-[#F9E2AF] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-1 active:shadow-none active:translate-y-1">
                     <Server size={28} strokeWidth={2.5} className="text-ink"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP</span>
                 </button>
                 <button onClick={() => {setSidebarMode('skill'); fetchSkill();}} style={sketchyShape3} className="flex-1 border-4 border-ink bg-[#FCD5CE] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-2 active:shadow-none active:translate-y-1">
                     <Zap size={28} strokeWidth={2.5} className="text-ink"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILL</span>
                 </button>
                 <button onClick={() => {setSidebarMode('cron'); fetchCron();}} style={sketchyShape1} className="flex-1 border-4 border-ink bg-[#E8D1C5] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1">
                     <AlarmClock size={28} strokeWidth={2.5} className="text-ink"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CRON</span>
                 </button>
                 <button onClick={onSwitchToTask || (() => navigate('/task'))} style={sketchyShape2} className="flex-1 border-4 border-ink bg-[#D8E2DC] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-1 active:shadow-none active:translate-y-1">
                     <Terminal size={28} strokeWidth={2.5} className="text-ink"/>
                     <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TASK</span>
                 </button>
             </div>
          )}

          {/* MCP 子面板 */}
          {sidebarMode === 'mcp' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
                 <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                     <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                     <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP SERVERS</span>
                     <button onClick={refreshMcp} className="p-1 bg-[#F9E2AF] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all"><RefreshCw size={18} strokeWidth={3}/></button>
                 </div>
                 {/* 🔴 修复穿模：增加 p-2 和 gap-4 */}
                 <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                    {Object.keys(mcpData).length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No MCP loaded</p> :
                      Object.entries(mcpData).map(([server, tools], idx) => (
                        <div key={server} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${expandedMcp === server ? 'shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-1 rotate-0' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 cursor-pointer'} ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'}`}>
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
                     <button onClick={refreshSkill} className="p-1 bg-[#FCD5CE] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all"><RefreshCw size={18} strokeWidth={3}/></button>
                 </div>
                 {/* 🔴 修复穿模：增加 p-2 和 gap-4 */}
                 <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                    {skillData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Skills loaded</p> :
                      skillData.map((skill: any, idx) => (
                        <div key={skill.name} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`border-4 border-ink bg-cream p-3 transition-all ${expandedSkill === skill.name ? 'shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-1 rotate-0' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 cursor-pointer'} ${idx % 2 === 0 ? '-rotate-1' : 'rotate-1'}`}>
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

        </div>
      </div>

      {/* --- 右侧大聊天纸板 --- */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-10">
        <div className="absolute -top-4 right-12 w-32 h-8 bg-[#EBCB8B]/80 border-2 border-ink -rotate-3 z-50" style={sketchyShape2}></div>

        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            <div style={sketchyShape1} className="w-12 h-12 bg-terracotta border-4 border-ink flex items-center justify-center -rotate-6 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]">
              <Cat size={28} className="text-paper" strokeWidth={2.5} />
            </div>
            <h2 className="text-4xl font-black tracking-tighter text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat.</h2>
          </div>
          {currentSessionId && (
            <div style={sketchyShape3} className="px-4 py-2 bg-ink/5 border-2 border-ink border-dashed text-sm font-bold text-ink/60 rotate-2">
              # {currentSessionId.slice(-8)}
            </div>
          )}
        </div>

        <div ref={messagesContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-10 pb-6 flex flex-col gap-6 w-full z-10">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-ink gap-6">
              <div style={sketchyShape1} className="p-8 border-4 border-ink bg-cream shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] -rotate-3">
                <Cat size={80} strokeWidth={1.5} className="text-terracotta" />
              </div>
              <p className="text-2xl font-black rotate-2 text-ink/60" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Waiting for your command...</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx}>
                {msg.role === 'user' ? (
                  parseEventsContent(msg.content).userMessages.map((userMsg, uIdx) => (
                    <div key={`${idx}-${uIdx}`} className="flex w-full justify-end">
                      <div className={`flex flex-col gap-3 w-full max-w-[85%] items-end`}>
                        {userMsg.content && (
                          <div style={sketchyShape2} className="w-full p-6 border-4 border-ink relative bg-terracotta text-paper shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]">
                            <div className="absolute w-3 h-3 bg-ink rounded-full -top-2 -right-2"></div>
                            <div className="text-[17px] font-bold text-paper">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{userMsg.content}</ReactMarkdown>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                ) : msg.role === 'tool' ? (
                  <div className="flex w-full justify-start"><ToolMessageBubble msg={msg} /></div>
                ) : (
                  <div className="flex w-full justify-start">
                    <div className={`flex flex-col gap-3 w-full max-w-[85%] items-start`}>
                      {msg.content && (
                        <div style={sketchyShape1} className="w-full p-6 border-4 border-ink relative bg-cream text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]">
                          <div className="absolute w-3 h-3 bg-ink rounded-full -top-2 -left-2"></div>
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
                )}
              </div>
            ))
          )}

          <div className="flex justify-start mb-4 w-full">
            <div style={sketchyShape1} className={`p-4 w-fit transition-colors ${isAgentThinking ? 'bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-paper text-ink/40'}`}>
              <div className="flex items-center gap-3 px-2">
                {isAgentThinking ? <Loader2 size={20} strokeWidth={3} className="animate-spin text-terracotta" /> : <Clock size={20} strokeWidth={3} className="text-ink/30" />}
                <span className="font-black text-sm tracking-widest uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{isAgentThinking ? 'Processing...' : 'Dozing...'}</span>
              </div>
            </div>
          </div>
          <div ref={messagesEndRef} className="h-2" />
        </div>

        <div className="px-10 pb-8 pt-4 shrink-0">
          <div className="flex gap-4">
            <textarea
              style={sketchyShape3} value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder={currentSessionId ? "Write your prompt here..." : "Select a chat first!"} disabled={!currentSessionId} rows={2}
              className="flex-1 bg-[#FDF8F0] border-4 border-ink p-5 font-bold focus:outline-none focus:bg-white transition-all shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] resize-none text-lg -rotate-[0.5deg] placeholder:text-ink/30"
            />
            <button
              style={sketchyShape1} onClick={handleSend} disabled={!currentSessionId || !input.trim()}
              className="bg-ink text-paper px-10 font-black flex items-center gap-3 border-4 border-ink hover:bg-terracotta hover:text-ink transition-all active:scale-95 disabled:opacity-50 shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] rotate-2 min-h-[80px] self-end"
            >
              <Send size={26} strokeWidth={2.5} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}