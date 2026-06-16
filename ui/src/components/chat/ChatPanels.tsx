// src/components/chat/ChatPanels.tsx
import React from 'react';
import { History, Minus, CheckCircle, FileText, Undo2, Bell, X, Activity, ChevronDown, ChevronUp } from 'lucide-react';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './ChatShared';

export function FileChangesPanel(props: any) {
  const { showFileView, setShowFileView, fileChanges, activeDiffPath, setActiveDiffPath, handleAck, handleRollback } = props;
  if (!showFileView) return null;

  return (
    <div className="px-10 pb-6 pt-2 flex flex-col w-full shrink-0">
      <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-6 flex flex-col h-[55vh] min-h-[35vh] max-h-[85vh] resize-y overflow-hidden">
        <div className="flex items-center gap-3 mb-5 border-b-4 border-ink/20 pb-3 shrink-0">
          <History size={26} strokeWidth={2.5} className="text-[#d08770]" />
          <h2 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            FILE CHANGES <span className="ml-2 text-sm opacity-60">({fileChanges.length} files modified)</span>
          </h2>
          <button onClick={() => setShowFileView(false)} className="ml-auto p-1.5 border-2 border-ink bg-cream hover:bg-[#d08770] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-[1px]" style={sketchyShape2}><Minus size={20} strokeWidth={3} /></button>
        </div>

        {fileChanges.length === 0 ? (
          <div className="flex flex-col items-center py-10 opacity-50"><CheckCircle size={48} strokeWidth={1.5} /><p className="font-bold text-sm mt-2">All files clean!</p></div>
        ) : (
          <div className="flex flex-col md:flex-row gap-6 flex-1 min-h-0 items-stretch">
            <div className="w-full md:w-72 shrink-0 overflow-y-auto flex flex-col gap-3 pr-2">
              {fileChanges.map((change: any, idx: number) => {
                const isSelected = activeDiffPath === change.path;
                const changeType = change.change_type || 'modified';
                let badge = null;
                let titleStyle = "font-black text-xs truncate flex-1 transition-all";
                if (changeType === 'deleted') { badge = <span className="absolute -top-2 -left-2 bg-[#bf616a] text-paper px-1.5 py-0.5 text-[9px] font-black border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] z-10" style={sketchyShape1}>DELETED</span>; titleStyle += " line-through opacity-60 decoration-2"; }
                else if (changeType === 'created') { badge = <span className="absolute -top-2 -left-2 bg-[#a3be8c] text-ink px-1.5 py-0.5 text-[9px] font-black border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] z-10" style={sketchyShape1}>NEW</span>; }

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
                if (!currentChange) return <div className="flex-1 flex items-center justify-center italic opacity-40 text-sm">Select a file...</div>;
                return (
                  <div className="flex-1 flex flex-col min-h-0">
                    <div className="flex-1 bg-[#FDF8F0] p-4 border-4 border-ink font-mono text-xs overflow-auto shadow-[inset_3px_3px_6px_rgba(0,0,0,0.05)]" style={sketchyShape2}>
                      {currentChange.diff ? currentChange.diff.split('\n').map((line: string, i: number) => {
                        let colorClass = 'text-ink/70';
                        if (line.startsWith('+')) colorClass = 'text-[#a3be8c] font-bold bg-[#a3be8c]/10';
                        if (line.startsWith('-')) colorClass = 'text-[#bf616a] font-bold bg-[#bf616a]/10';
                        if (line.startsWith('@')) colorClass = 'text-[#88c0d0]';
                        return <div key={i} className={`${colorClass} leading-relaxed whitespace-pre rounded px-1`}>{line || '\u00A0'}</div>;
                      }) : <span className="opacity-50 italic p-2 block">No visual difference detected.</span>}
                    </div>
                    <div className="flex gap-4 mt-3 shrink-0">
                      <button onClick={() => handleAck(currentChange.path, currentChange.newest_backup_id)} className="flex-1 bg-[#a3be8c] text-ink font-black py-2.5 border-2 border-ink shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-0.5 active:shadow-none transition-all flex justify-center items-center gap-2" style={sketchyShape2}><CheckCircle size={16} strokeWidth={3}/> ACKNOWLEDGE</button>
                      <button onClick={() => handleRollback(currentChange.path, currentChange.oldest_backup_id)} className="flex-1 bg-[#bf616a] text-paper font-black py-2.5 border-2 border-ink shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-0.5 active:shadow-none transition-all flex justify-center items-center gap-2" style={sketchyShape3}><Undo2 size={16} strokeWidth={3}/> REVERT</button>
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
  const { showReqQueue, setShowReqQueue, pendingReqs, handleResolveReq, feedbackInputs, setFeedbackInputs, authDurations, setAuthDurations, expandedReasons, setExpandedReasons } = props;
  if (!showReqQueue) return null;

  return (
    <div style={sketchyShape3} className="w-[340px] shrink-0 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-20">
      <div className="flex flex-col shrink-0 p-4 bg-paper">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2"><Bell size={24} strokeWidth={2.5} className="text-[#EBCB8B]" /><h3 className="text-2xl font-black tracking-widest text-ink">PENDING</h3></div>
          <button onClick={() => setShowReqQueue(false)} className="hover:text-terracotta hover:rotate-90 transition-all p-1 bg-paper border-2 border-ink" style={sketchyShape1}><X size={20} strokeWidth={3} /></button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4 bg-paper">
        {pendingReqs.length === 0 ? (
          <div className="flex flex-col items-center opacity-50 mt-10"><Activity size={48} strokeWidth={1.5} /><p className="font-bold text-sm mt-2">No requests.</p></div>
        ) : (
          pendingReqs.map((req: any, idx: number) => (
            <div key={req.id} className={`bg-paper border-4 border-ink p-4 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-3 relative transition-all group ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'}`} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}>
              <button onClick={() => handleResolveReq(req.id, false, true)} className="opacity-0 group-hover:opacity-100 p-1.5 bg-ink text-paper border-2 border-ink hover:scale-110 transition-all absolute -top-2 -right-2 z-10" style={sketchyShape2} title="Ignore (Silent)"><X size={12} strokeWidth={3} /></button>
              <div className="flex justify-between items-start"><span className="font-black text-xs uppercase px-2 py-0.5 bg-[#EBCB8B] border-2 border-ink" style={sketchyShape1}>{req.type}</span></div>
              <div>
                <div className="text-[15px] font-black text-ink break-all leading-tight">{req.target}</div>
                <button onClick={() => setExpandedReasons({...expandedReasons, [req.id]: !expandedReasons[req.id]})} className="text-xs font-bold text-ink/50 mt-2 flex items-center gap-1 hover:text-ink transition-colors">{expandedReasons[req.id] ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Reason</button>
                {expandedReasons[req.id] && <div className="text-xs font-bold text-ink/70 bg-ink/5 p-2 mt-1 leading-relaxed">{req.reason}</div>}
              </div>
              {req.type === 'computer_use' && (
                <div className="flex items-center justify-between mt-1 mb-1 p-2 border-2 border-ink bg-[#88c0d0]/20" style={sketchyShape3}><span className="text-xs font-black text-ink uppercase">⏳ TIME LIMIT:</span><select value={authDurations[req.id] || 5} onChange={e => setAuthDurations({...authDurations, [req.id]: parseInt(e.target.value)})} className="bg-cream border-2 border-ink text-xs p-1 font-bold" style={sketchyShape2}><option value={5}>5 MINS</option><option value={10}>10 MINS</option></select></div>
              )}
              <input value={feedbackInputs[req.id] || ''} onChange={e => setFeedbackInputs({...feedbackInputs, [req.id]: e.target.value})} placeholder="Feedback (Optional)..." className="w-full text-xs font-bold p-2 border-2 border-ink focus:outline-none bg-[#FDF8F0] shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" style={sketchyShape2} />
              <div className="flex gap-2 mt-1">
                <button onClick={() => handleResolveReq(req.id, true, false, authDurations[req.id] || 5)} className="flex-1 bg-[#a3be8c] text-ink font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all flex justify-center items-center" style={sketchyShape1}>APPROVE</button>
                <button onClick={() => handleResolveReq(req.id, false, false, authDurations[req.id] || 5)} className="flex-1 bg-[#bf616a] text-paper font-black text-xs py-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-1 active:shadow-none transition-all" style={sketchyShape2}>REJECT</button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}