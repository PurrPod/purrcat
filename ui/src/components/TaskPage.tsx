import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, MessageSquare, Trash2, X, Terminal, Clock } from 'lucide-react';
import { toast } from 'react-hot-toast';

interface TaskInfo {
  id: string;
  name: string;
  state: string;
  step: number;
  expert_type: string;
  create_time: string;
}

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

// 简单的正则用于剥离后端返回的 Rich CLI 色彩标记，保持浏览器渲染干净
const cleanLogText = (text: string) => text.replace(/\[\/?([a-zA-Z0-9_#]+)\]/g, '');

export default function TaskPage({ onBack, onSwitchToChat }: { onBack: () => void, onSwitchToChat?: () => void }) {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [taskLog, setTaskLog] = useState<string>('');
  
  const [taskToDelete, setTaskToDelete] = useState<string | null>(null);

  const logEndRef = useRef<HTMLDivElement>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const isAutoScroll = useRef(true);

  const handleScroll = () => {
    if (!logContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
    isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  useEffect(() => {
    if (isAutoScroll.current) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [taskLog]);

  const loadTasks = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tasks');
      if (res.ok) {
        const data = await res.json();
        setTasks(data);
        if (data.length > 0 && !currentTaskId) setCurrentTaskId(data[0].id);
      }
    } catch (e) { toast.error("获取任务列表失败"); }
  };

  useEffect(() => { loadTasks(); }, []);

  useEffect(() => {
    if (!currentTaskId) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/tasks/${currentTaskId}/log`);
        if (res.ok) {
          const data = await res.json();
          setTaskLog(cleanLogText(data.log));
        }
      } catch (e) {}
    }, 1500);
    return () => clearInterval(interval);
  }, [currentTaskId]);

  const handleSelectTask = (taskId: string) => {
    setCurrentTaskId(taskId);
    isAutoScroll.current = true;
  };

  const confirmDeleteTask = async () => {
    if (!taskToDelete) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskToDelete}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success("任务已清理！");
        if (currentTaskId === taskToDelete) {
          setCurrentTaskId(null);
          setTaskLog('');
        }
        setTaskToDelete(null);
        loadTasks();
      }
    } catch (e) { toast.error("删除任务失败"); }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">
      
      {/* 🔴 任务删除确认弹窗 */}
      {taskToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DELETE TASK?</h3>
              <button onClick={() => setTaskToDelete(null)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要清理并终止这个任务记录吗？操作不可逆！</p>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setTaskToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                CANCEL
              </button>
              <button onClick={confirmDeleteTask} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                DESTROY
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --- 左侧侧边栏 --- */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          
          <div style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#81a1c1] text-paper border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-1">
             <span className="tracking-widest text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TASKS DB</span>
          </div>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="text-sm font-black text-ink uppercase tracking-widest mt-2 ml-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            <span className="bg-ink text-paper px-2 py-1 rotate-2 inline-block" style={sketchyShape2}>RUNNING & HISTORY</span>
          </div>
          
          <div className="flex-1 overflow-y-auto flex flex-col gap-4 pr-1 mt-2">
            {tasks.map((task, idx) => (
              <button
                key={task.id} onClick={() => handleSelectTask(task.id)} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                className={`text-left p-4 border-2 transition-all flex flex-col gap-2 relative group 
                  ${idx % 3 === 0 ? 'rotate-1' : idx % 2 === 0 ? '-rotate-1' : 'rotate-2'}
                  ${currentTaskId === task.id ? 'bg-[#81a1c1] border-ink text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream border-ink text-ink hover:bg-sand hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-bold truncate max-w-[150px] text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{task.name}</span>
                  
                  {/* 🔴 删除按钮 */}
                  <div onClick={(e) => { e.stopPropagation(); setTaskToDelete(task.id); }} className="p-1 hover:text-[#bf616a] hover:bg-white/50 rounded transition-colors" title="Delete Task">
                    <Trash2 size={16} strokeWidth={2.5} className={currentTaskId === task.id ? 'opacity-100' : 'opacity-40'} />
                  </div>
                </div>
                <div className={`flex items-center gap-3 text-xs font-bold ${currentTaskId === task.id ? 'text-paper/90' : 'text-ink/60'}`}>
                  <Terminal size={14} strokeWidth={3} /> {task.state} • Step: {task.step}
                </div>
              </button>
            ))}
            {tasks.length === 0 && <p className="text-center mt-10 font-bold text-ink/40">No tasks found</p>}
          </div>
        </div>
      </div>

      {/* --- 右侧大监视器 --- */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden rotate-[1deg] relative z-10">
        
        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4">
            <div style={sketchyShape2} className="w-12 h-12 bg-ink border-4 border-ink flex items-center justify-center rotate-3 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]">
              <Terminal size={24} className="text-[#a3be8c]" strokeWidth={3} />
            </div>
            <h2 className="text-4xl font-black tracking-tighter text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Task Monitor</h2>
            
            {/* 🔴 切换回 ChatPage 按钮 */}
            {onSwitchToChat && (
              <button onClick={onSwitchToChat} style={sketchyShape3} className="ml-2 w-10 h-10 bg-[#a3be8c] border-4 border-ink flex items-center justify-center hover:bg-[#8ca876] transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-2 hover:rotate-1" title="Back to Chat">
                <MessageSquare size={18} strokeWidth={3} className="text-ink" />
              </button>
            )}
          </div>
          {currentTaskId && (
            <div style={sketchyShape3} className="px-4 py-2 bg-ink/5 border-2 border-ink border-dashed text-sm font-bold text-ink/60 -rotate-1">
              ID: {currentTaskId.slice(0,8)}...
            </div>
          )}
        </div>

        <div className="px-10 pb-10 flex-1 overflow-hidden flex flex-col">
          <div ref={logContainerRef} onScroll={handleScroll} style={sketchyShape2} className="flex-1 bg-[#1a1c23] border-4 border-ink shadow-[inset_6px_6px_0px_0px_rgba(0,0,0,0.5)] p-6 overflow-y-auto font-mono text-[13px] text-[#e5e9f0] whitespace-pre-wrap -rotate-[0.5deg]">
             {taskLog ? taskLog : (
                 <div className="h-full flex flex-col items-center justify-center text-white/30 gap-4">
                     <Terminal size={48} strokeWidth={2}/>
                     <p>Select a task to view execution logs.</p>
                 </div>
             )}
             <div ref={logEndRef} className="h-4" />
          </div>
        </div>
      </div>
    </div>
  );
}