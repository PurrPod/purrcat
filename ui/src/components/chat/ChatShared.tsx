// src/components/chat/ChatShared.tsx
/* eslint-disable react-refresh/only-export-components */
import { useEffect, useRef, useState } from 'react';
import { Package, ChevronDown, ChevronUp, Wrench, Brain, Pause, Loader2 } from 'lucide-react';
import { EventItem, Message } from './ChatTypes';
import { useTranslation } from '../../i18n';

export const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
export const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
export const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

// 安全的 URI 解码：文件名含裸 % 等非法编码序列时原样返回，避免 decodeURIComponent 抛错打断点击处理
export function safeDecodeUri(s: string): string {
  try { return decodeURIComponent(s); } catch { return s; }
}

export function parseEventsContent(content: string): { userMessages: EventItem[], systemCount: number, attachments: EventItem[] } {
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
        } else if (eventType === 'file-quote' || eventType === 'skill-quote' || eventType === 'tool-quote' || eventType === 'mcp-quote' || eventType === 'graph-quote') {
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

export function hasMessageInHistory(history: any[], text: string) {
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

export const MarkdownComponents: any = {
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
  // 🌟 GFM 表格/图片/分隔线（IDE md 预览与聊天气泡共用）
  table: ({ ...props }: any) => (
    <div className="my-4 overflow-x-auto">
      <table className="border-collapse border-2 border-ink text-sm font-bold w-full" {...props} />
    </div>
  ),
  thead: ({ ...props }: any) => <thead className="bg-ink/10" {...props} />,
  th: ({ ...props }: any) => <th className="border-2 border-ink px-3 py-1.5 text-left" {...props} />,
  td: ({ ...props }: any) => <td className="border-2 border-ink/60 px-3 py-1.5 align-top" {...props} />,
  img: ({ ...props }: any) => <img className="max-w-full my-2 border-2 border-ink/20" {...props} />,
  hr: ({ ...props }: any) => <hr className="my-4 border-t-4 border-ink/20" {...props} />,
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

export function renderSketchyHeatmap(heatmapData: Record<string, number> = {}) {
  const cells = [];
  const today = new Date();
  const totalDays = 364; 
  const startDay = new Date(today);
  startDay.setDate(today.getDate() - totalDays);
  const startDayOfWeek = startDay.getDay(); 
  startDay.setDate(startDay.getDate() - startDayOfWeek); 

  for (let i = 0; i < 371; i++) {
    const current = new Date(startDay);
    current.setDate(startDay.getDate() + i);
    const dateStr = current.toISOString().split('T')[0];
    const count = heatmapData[dateStr] || 0;

    let colorClass = 'bg-white border-ink/20';
    if (count > 0 && count <= 10) colorClass = 'bg-[#a3be8c]/40 border-ink/40';
    if (count > 10 && count <= 50) colorClass = 'bg-[#a3be8c]/70 border-ink/70';
    if (count > 50) colorClass = 'bg-[#a3be8c] border-ink';

    cells.push(
      <div 
        key={dateStr}
        title={`${dateStr} : ${count} CALLS`}
        className={`w-2.5 h-2.5 border transition-all hover:scale-150 hover:border-terracotta hover:z-10 relative cursor-crosshair ${colorClass}`}
        style={{ borderRadius: i % 3 === 0 ? '1px 3px 1px 2px' : '2px 1px 3px 1px' }} 
      />
    );
  }

  return (
    <div className="w-full overflow-x-auto">
      <div className="grid grid-rows-7 grid-flow-col gap-[3px] p-3 bg-cream/30 w-fit mx-auto">
        {cells}
      </div>
    </div>
  );
}

// 🌟 提取工具结果的纯净 content：后端把 {"content": ..., "metadata": {...}} 整体 JSON 序列化后
// 作为 tool 消息的 content 下发，直接展示会带出 metadata 且换行变成字面 \n。
// 这里解析后只取 content 字段（真实换行交给 whitespace-pre-wrap 渲染）；
// 兼容异常路径的 {"error": ...} 格式；非该格式则原样展示。
// vision 直注时 content 是 OpenAI 多模态 parts 数组：只展示文本占位（图片路径），
// 不渲染图片本体。
export function extractToolContent(content: unknown): string {
  if (Array.isArray(content)) {
    const textParts = content
      .filter((p: any) => p && p.type === 'text' && typeof p.text === 'string')
      .map((p: any) => p.text);
    return textParts.join('\n') || '[图片已注入对话]';
  }
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content);
      if (parsed && typeof parsed === 'object') {
        if (typeof parsed.content === 'string') return parsed.content;
        if (Array.isArray(parsed.content)) {
          const textParts = parsed.content
            .filter((p: any) => p && p.type === 'text' && typeof p.text === 'string')
            .map((p: any) => p.text);
          return textParts.join('\n') || '[图片已注入对话]';
        }
        if (typeof parsed.error === 'string') return parsed.error;
      }
    } catch { /* 非 JSON 格式，原样展示 */ }
    return content;
  }
  return JSON.stringify(content, null, 2);
}

export const ToolMessageBubble = ({ msg }: { msg: Message }) => {
  const [expanded, setExpanded] = useState(false);
  const contentStr = extractToolContent(msg.content);

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

export const ToolCallBubble = ({ tc }: { tc: any }) => {
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

// 🌟 Thinking/Reasoning 气泡：live 态（模型思考中/工具执行中）用原 Processing 的 cream 色，
// phase=thinking 显示 THINKING...（Brain 图标），phase=processing 显示 PROCESSING...（转圈）；
// 暂停按钮在块内文字后面（复刻原 Processing 布局）；思考结束后落为淡蓝色静态 REASONING 气泡
// （与 TOOL 消息同级，收起按钮同 ToolMessageBubble 放正文下方左侧）。
// 宽度统一 w-full 由外层容器控制（避免嵌套 max-w-[85%] 叠乘导致静态气泡比 live 的窄）；
// 折叠偏好持久化：用户折叠过 Thinking 后，下次思考不再自动展开
const THINKING_EXPANDED_KEY = 'purrcat-thinking-expanded';
const readThinkingExpandedPref = (): boolean => {
  try { return localStorage.getItem(THINKING_EXPANDED_KEY) !== 'collapsed'; } catch { return true; }
};
const writeThinkingExpandedPref = (v: boolean) => {
  try { localStorage.setItem(THINKING_EXPANDED_KEY, v ? 'expanded' : 'collapsed'); } catch { /* noop */ }
};

export const ReasoningBubble = ({ text, live = false, phase = 'thinking', onPause }: { text: string; live?: boolean; phase?: 'thinking' | 'processing' | 'aborting'; onPause?: () => void }) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(live ? readThinkingExpandedPref() : false);
  const bodyRef = useRef<HTMLDivElement>(null);

  // live 态的展开/折叠要记住用户偏好（下次 thinking 沿用）；静态气泡不写偏好
  const setLiveExpanded = (v: boolean) => {
    setExpanded(v);
    writeThinkingExpandedPref(v);
  };

  // 流式阶段：新文本到达时滚动到底部跟随
  useEffect(() => {
    if (live && expanded && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [text, live, expanded]);

  const title = live ? (phase === 'thinking' ? 'THINKING...' : phase === 'processing' ? 'PROCESSING...' : 'ABORTING...') : 'REASONING';
  // PROCESSING/ABORTING 用转圈（工具执行中/打断等待收尾），THINKING/REASONING 用 Brain
  const isSpinning = live && (phase === 'processing' || phase === 'aborting');
  const TitleIcon = isSpinning ? Loader2 : Brain;
  const titleIconSpin = isSpinning ? 'animate-spin' : '';

  // 🌟 live 折叠态（用户折叠过 或 尚无思考内容/工具执行中）：等价原 Processing 块（cream 色），
  // 暂停按钮在块内文字后面（复刻原 Processing 布局）
  if (live && (!expanded || !text)) {
    return (
      <div style={sketchyShape1} className="p-4 w-fit bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] mb-3 flex items-center gap-3 self-start">
        <TitleIcon size={20} strokeWidth={3} className={`text-ink shrink-0 ${titleIconSpin}`} />
        <span className="font-black text-sm tracking-widest uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{title}</span>
        {onPause && phase !== 'aborting' && (
          <button onClick={onPause} className="p-0.5 text-terracotta hover:text-ink transition-colors shrink-0" title={t('chat.pauseHint')}>
            <Pause size={18} strokeWidth={3} />
          </button>
        )}
        {text && (
          <button onClick={() => setLiveExpanded(true)} className="p-0.5 text-ink/60 hover:text-ink transition-colors shrink-0" title={t('chat.expandThinking')}>
            <ChevronDown size={18} strokeWidth={3} />
          </button>
        )}
      </div>
    );
  }

  // 静态折叠态：小 chip（淡蓝）
  if (!expanded) {
    return (
      <div onClick={() => setExpanded(true)} style={sketchyShape2} className="w-fit max-w-[250px] p-2 px-4 border-2 border-ink bg-[#D8E2DC]/60 text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] mb-2 flex items-center justify-between gap-3 cursor-pointer hover:bg-[#D8E2DC] transition-all hover:-translate-y-0.5 self-start">
        <div className="flex items-center gap-2 truncate">
          <Brain size={14} strokeWidth={3} className="shrink-0 text-[#5e81ac]"/>
          <span className="font-black text-[11px] uppercase tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>REASONING</span>
        </div>
        <ChevronDown size={14} strokeWidth={3} className="shrink-0 opacity-50"/>
      </div>
    );
  }

  // live 展开态（cream）/ 静态展开态（淡蓝）：收起按钮与 ToolMessageBubble 同位（正文下方左侧 mt-3）
  return (
    <div style={sketchyShape2} className={`w-full p-6 border-4 border-ink text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] mb-3 transition-all self-start ${live ? 'bg-cream' : 'bg-[#D8E2DC]/40'}`}>
      <div className="flex items-center gap-2 mb-3 border-b-2 border-ink/20 pb-2">
        <TitleIcon size={16} strokeWidth={3} className={`shrink-0 ${live ? 'text-ink' : 'text-[#5e81ac]'} ${titleIconSpin}`}/>
        <span className="font-black text-xs uppercase tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          {title}
        </span>
        {live && onPause && phase !== 'aborting' && (
          <button onClick={onPause} className="p-0.5 text-terracotta hover:text-ink transition-colors shrink-0" title={t('chat.pauseHint')}>
            <Pause size={16} strokeWidth={3} />
          </button>
        )}
        {live && (
          <button onClick={() => setLiveExpanded(false)} className="ml-auto p-0.5 text-ink/60 hover:text-ink transition-colors" title={t('chat.collapseThinking')}>
            <ChevronUp size={16} strokeWidth={3} />
          </button>
        )}
      </div>
      <div ref={bodyRef} className="font-mono text-[13px] opacity-90 whitespace-pre-wrap break-all max-h-72 overflow-y-auto">{text}</div>
      {!live && (
        <button onClick={() => setExpanded(false)} className="mt-3 text-xs font-black text-ink/70 hover:text-terracotta flex items-center gap-1 bg-white/50 px-2 py-1 border-2 border-transparent hover:border-ink transition-all" style={sketchyShape2}>
          <ChevronUp size={14} strokeWidth={3}/> COLLAPSE
        </button>
      )}
    </div>
  );
};