// src/components/chat/ChatShared.tsx
/* eslint-disable react-refresh/only-export-components */
import { useState } from 'react';
import { Package, ChevronDown, ChevronUp, Wrench } from 'lucide-react';
import { EventItem, Message } from './ChatTypes';

export const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
export const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
export const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

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
    <div className="flex justify-center w-full">
      <div className="grid grid-rows-7 grid-flow-col gap-[3px] p-3 bg-cream/30 w-fit">
        {cells}
      </div>
    </div>
  );
}

export const ToolMessageBubble = ({ msg }: { msg: Message }) => {
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