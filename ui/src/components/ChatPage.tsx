import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Cat, MessageSquarePlus, Clock, Wrench, Package, ChevronDown, ChevronUp, Loader2, X, Trash2, Terminal } from 'lucide-react';
import { toast } from 'react-hot-toast';

// 引入 Markdown 渲染库
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
    // 如果不是 JSON 格式，当作普通用户消息处理
    userMessages.push({ type: 'user', time: '', content });
  }
  
  return { userMessages, systemCount };
}

interface Session { id: string; alias: string; messages_count: number; updated_at: string; }

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

// 🟢 自定义 Markdown 渲染组件库 (保留手绘风格)
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
    // 判断是否为 pre 块包裹的代码
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


// 🟢 工具返回结果卡片
const ToolMessageBubble = ({ msg }: { msg: Message }) => {
  const [expanded, setExpanded] = useState(false);
  
  const contentStr = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);



  // 折叠状态：微型标签
  if (!expanded) {
    return (
      <div 
        onClick={() => setExpanded(true)} 
        style={sketchyShape3} 
        className="w-fit max-w-[250px] p-2 px-4 border-2 border-ink bg-[#a3be8c]/30 text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] mb-2 flex items-center justify-between gap-3 cursor-pointer hover:bg-[#a3be8c]/60 transition-all hover:-translate-y-0.5 self-start"
      >
        <div className="flex items-center gap-2 truncate">
          <Package size={14} strokeWidth={3} className="shrink-0 text-ink/70"/>
          <span className="font-black text-[11px] uppercase tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            RESULT: {msg.name || 'Output'}
          </span>
        </div>
        <ChevronDown size={14} strokeWidth={3} className="shrink-0 opacity-50"/>
      </div>
    );
  }

  // 展开状态：完整大框
  return (
    <div style={sketchyShape3} className="max-w-[85%] w-full p-4 border-4 border-ink bg-[#a3be8c]/30 text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] mb-4 transition-all self-start">
      <div>
        <div className="flex items-center gap-2 mb-2 border-b-2 border-ink/20 pb-1">
          <Package size={16} strokeWidth={3}/>
          <span className="font-black text-xs uppercase tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TOOL RESULT: {msg.name || 'Output'}</span>
        </div>
        <div className="font-mono text-[13px] opacity-90 whitespace-pre-wrap break-all">
          {contentStr}
        </div>
        <button 
          onClick={() => setExpanded(false)} 
          className="mt-3 text-xs font-black text-ink/70 hover:text-terracotta flex items-center gap-1 bg-white/50 px-2 py-1 border-2 border-transparent hover:border-ink transition-all"
          style={sketchyShape2}
        >
          <ChevronUp size={14} strokeWidth={3}/> COLLAPSE
        </button>
      </div>
    </div>
  );
};

// 🟢 工具调用发起卡片
const ToolCallBubble = ({ tc }: { tc: any }) => {
  const [expanded, setExpanded] = useState(false);
  const argsStr = tc.function?.arguments || '{}';

  // 折叠状态：微型标签
  if (!expanded) {
    return (
      <div 
        onClick={() => setExpanded(true)} 
        style={sketchyShape3} 
        className="w-fit max-w-[250px] p-2 px-4 border-2 border-ink bg-[#EBCB8B]/40 text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] mb-2 flex items-center justify-between gap-3 cursor-pointer hover:bg-[#EBCB8B]/70 transition-all hover:-translate-y-0.5 self-start"
      >
        <div className="flex items-center gap-2 truncate">
          <Wrench size={14} strokeWidth={3} className="shrink-0 text-ink/70"/>
          <span className="font-black text-[11px] uppercase tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            CALL: {tc.function?.name}
          </span>
        </div>
        <ChevronDown size={14} strokeWidth={3} className="shrink-0 opacity-50"/>
      </div>
    );
  }

  // 展开状态：完整大框
  return (
    <div style={sketchyShape3} className="w-full p-4 border-4 border-ink bg-[#EBCB8B]/40 text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] mb-2 transition-all">
      <div>
        <div className="flex items-center gap-2 mb-2 border-b-2 border-ink/20 pb-1">
          <Wrench size={16} strokeWidth={3}/>
          <span className="font-black text-xs uppercase tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CALLING TOOL: {tc.function?.name}</span>
        </div>
        <div className="font-mono text-[13px] opacity-80 break-all">
          {argsStr}
        </div>
        <button 
          onClick={() => setExpanded(false)} 
          className="mt-3 text-xs font-black text-ink/70 hover:text-terracotta flex items-center gap-1 bg-white/50 px-2 py-1 border-2 border-transparent hover:border-ink transition-all inline-flex"
          style={sketchyShape2}
        >
          <ChevronUp size={14} strokeWidth={3}/> COLLAPSE
        </button>
      </div>
    </div>
  );
};

export default function ChatPage({ onBack, onSwitchToTask }: { onBack: () => void, onSwitchToTask?: () => void }) {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId || null);

  const [showModal, setShowModal] = useState(false);
  const [newAlias, setNewAlias] = useState('');

  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  
  // 🟢 核心：检出状态锁定器
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  
  // 🟢 Agent 真实状态（由后端 API 驱动）
  const [isAgentThinking, setIsAgentThinking] = useState(false);

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
        // 🟢 并发请求：同时拉取「历史记录」和「Agent 真实状态」
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
      } catch (e) { /* ignore polling errors */ }
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
    setIsCheckingOut(true); // 开启等待动画
    try {
      const res = await fetch('http://localhost:8000/api/sessions/new', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ alias: newAlias.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`开启全新对话: ${newAlias}`);
        setNewAlias('');
        await loadSessions();
        await handleSelectSession(data.id); // 会继续维持 isCheckingOut 直到加载完毕
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
      
      {/* 🟢 修复：将 bg-ink/50 替换为 bg-cream/70 (护眼浅色) */}
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
              <h3 className="text-3xl font-black tracking-widest text-ink mb-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                CHECKING OUT...
              </h3>
              <p className="font-bold opacity-70 text-base text-ink/80 bg-terracotta/10 px-3 py-1 border-2 border-dashed border-ink/20 inline-block" style={sketchyShape1}>
                Waiting for the agent to complete tasks...
              </p>
            </div>
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-md w-full">
            <div className="flex justify-between items-center -rotate-1">
              <h3 className="text-3xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW CHAT</h3>
              <button onClick={() => setShowModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <div className="-rotate-1">
              <input
                autoFocus
                value={newAlias}
                onChange={e => setNewAlias(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && confirmNewSession()}
                placeholder="Give it a cool name..."
                className="w-full border-4 border-ink bg-cream p-4 font-bold text-lg focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30"
                style={sketchyShape3}
              />
            </div>
            <button onClick={confirmNewSession} style={{ ...sketchyShape1, fontFamily: '"Comic Sans MS", cursive' }} className="bg-terracotta text-paper font-black tracking-widest text-xl py-4 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-none transition-all rotate-1">
              CREATE NOW
            </button>
          </div>
        </div>
      )}

      {sessionToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DELETE CHAT?</h3>
              <button onClick={() => setSessionToDelete(null)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要删除这个分支会话吗？该分支上的历史记忆将永久丢失！</p>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setSessionToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                CANCEL
              </button>
              <button onClick={confirmDeleteSession} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                DELETE
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --- 左侧会话卡片 --- */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          <button onClick={() => { setNewAlias('New Task'); setShowModal(true); }} style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-terracotta text-paper border-4 border-ink hover:bg-[#C46A4A] transition-all active:scale-95 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2 hover:-rotate-1">
            <MessageSquarePlus size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW CHAT</span>
          </button>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-24 h-6 bg-terracotta/20 border-2 border-ink rotate-2 z-10" style={sketchyShape1}></div>
          <div className="text-sm font-black text-ink uppercase tracking-widest mt-2 ml-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            <span className="bg-ink text-paper px-2 py-1 rotate-2 inline-block" style={sketchyShape2}>HISTORY</span>
          </div>
          
          <div className="flex-1 overflow-y-auto flex flex-col gap-4 pr-1 mt-2">
            {sessions.map((session, idx) => (
              <button
                key={session.id} onClick={() => handleSelectSession(session.id)} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                className={`text-left p-4 border-2 transition-all flex flex-col gap-2 relative group 
                  ${idx % 3 === 0 ? 'rotate-1' : idx % 2 === 0 ? '-rotate-1' : 'rotate-2'}
                  ${currentSessionId === session.id ? 'bg-terracotta border-ink text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream border-ink text-ink hover:bg-sand hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-bold truncate max-w-[180px] text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{session.alias}</span>

                  <div onClick={(e) => { e.stopPropagation(); setSessionToDelete(session.id); }} className="p-1 hover:text-[#bf616a] hover:bg-white/50 rounded transition-colors" title="Delete Chat">
                    <Trash2 size={16} strokeWidth={2.5} className={currentSessionId === session.id ? 'opacity-100' : 'opacity-40'} />
                  </div>
                </div>
                <div className={`flex items-center gap-3 text-xs font-bold ${currentSessionId === session.id ? 'text-paper/90' : 'text-ink/60'}`}>
                  <Clock size={14} strokeWidth={3} /> {session.updated_at.split(' ')[0]}
                </div>
              </button>
            ))}
          </div>
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

            {onSwitchToTask && (
              <button onClick={onSwitchToTask} style={sketchyShape3} className="ml-2 w-10 h-10 bg-[#EBCB8B] border-4 border-ink flex items-center justify-center hover:bg-[#d8b877] transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none rotate-2 hover:-rotate-1" title="Switch to Task Monitor">
                <Terminal size={20} strokeWidth={3} className="text-ink" />
              </button>
            )}
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
                  // 用户消息：解析 events JSON
                  parseEventsContent(msg.content).userMessages.map((userMsg, uIdx) => (
                    <div key={`${idx}-${uIdx}`} className="flex w-full justify-end">
                      <div className={`flex flex-col gap-3 w-full max-w-[85%] items-end`}>
                        {userMsg.content && (
                          <div style={sketchyShape2} className="w-full p-6 border-4 border-ink relative bg-terracotta text-paper shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]">
                            <div className="absolute w-3 h-3 bg-ink rounded-full -top-2 -right-2"></div>
                            <div className="text-[17px] font-bold text-paper">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                                {userMsg.content}
                              </ReactMarkdown>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                ) : msg.role === 'tool' ? (
                  <div className="flex w-full justify-start">
                    <ToolMessageBubble msg={msg} />
                  </div>
                ) : (
                  // assistant 消息
                  <div className="flex w-full justify-start">
                    <div className={`flex flex-col gap-3 w-full max-w-[85%] items-start`}>
                      {msg.content && (
                        <div style={sketchyShape1} className="w-full p-6 border-4 border-ink relative bg-cream text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]">
                          <div className="absolute w-3 h-3 bg-ink rounded-full -top-2 -left-2"></div>
                          <div>
                            <div className="flex items-center gap-2 mb-4">
                              <Cat size={20} strokeWidth={2.5}/>
                              <span className="font-black text-sm uppercase tracking-widest bg-ink text-paper px-2 py-0.5" style={{ ...sketchyShape3, fontFamily: '"Comic Sans MS", cursive' }}>
                                ASSISTANT
                              </span>
                            </div>
                            <div className="text-[17px] font-bold text-ink">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                                {msg.content}
                              </ReactMarkdown>
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
            <div
              style={sketchyShape1}
              className={`p-4 w-fit transition-colors
                ${isAgentThinking ? 'bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-paper text-ink/40'}`}
            >
              <div className="flex items-center gap-3 px-2">
                {isAgentThinking ? (
                  <Loader2 size={20} strokeWidth={3} className="animate-spin text-terracotta" />
                ) : (
                  <Clock size={20} strokeWidth={3} className="text-ink/30" />
                )}
                <span className="font-black text-sm tracking-widest uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  {isAgentThinking ? 'Processing...' : 'Dozing...'}
                </span>
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