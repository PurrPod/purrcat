import { useState, useEffect, useMemo, useRef } from 'react';
import {
  ArrowLeft, Terminal, Trash2, X, Activity, Clock, Box, Send, MessageCircle
} from 'lucide-react';
import type { Node, Edge } from '@xyflow/react';
import { ReactFlow, Background, useNodesState, useEdgesState, Handle, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toast } from 'react-hot-toast';

// --- 风格常量 ---
const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 225px 15px/15px 255px 15px 225px' };

interface Task {
  id: string;
  name: string;
  graph_name?: string;
  expert_type?: string;
  state: 'running' | 'completed' | 'failed' | 'idle';
  step: number;
  create_time: string;
}

interface LogEntry {
  timestamp: number;
  type: string;
  content: string;
  node_id?: string;
  [key: string]: any;
}

// 🟢 1. 修复节点高亮：增加 selected 属性支持，对齐 Editor 样式
const TaskMonitorNode = ({ id, data, selected }: any) => {
  let statusColor = "bg-[#EBCB8B]";
  let isPulsing = false;

  if (data.nodeState === "running") {
    statusColor = "bg-[#3498DB]";
    isPulsing = true;
  } else if (data.nodeState === "completed") {
    statusColor = "bg-[#a3be8c]";
  } else if (data.nodeState === "error") {
    statusColor = "bg-[#bf616a]";
    isPulsing = true;
  } else if (data.nodeState === "waiting") {
    statusColor = "bg-[#d08770]";
    isPulsing = true;
  }

  const isTaskRunning = data.isTaskRunning;

  return (
    <div 
      style={data.shape} 
      className={`bg-paper p-4 min-w-[200px] transition-all duration-200 hover:-translate-y-1 border-4 border-ink
        ${selected ? 'shadow-[8px_8px_0px_0px_rgba(212,122,90,1)]' : 
          isTaskRunning ? 'shadow-[6px_6px_0px_0px_rgba(212,122,90,1)]' : 
          'shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}
    >
      <div className="flex items-center gap-3 mb-3 border-b-2 border-ink/10 pb-2">
        <div className={`w-4 h-4 border-2 border-ink -rotate-3 ${statusColor} ${isPulsing ? 'animate-pulse' : ''}`}></div>
        <div className="font-black text-lg truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          {data.label}
        </div>
      </div>
      
      <button
        onClick={(e) => { e.stopPropagation(); data.onShowLog(id); }}
        className="w-full flex items-center justify-center gap-2 bg-cream border-2 border-ink py-2 text-sm font-black hover:bg-terracotta hover:text-paper transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-0.5"
        style={sketchyShape3}
      >
        <Terminal size={16} strokeWidth={3} /> View Logs
      </button>

      <Handle type="target" position={Position.Left} className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-left-[28px] z-10 hover:!bg-terracotta hover:!scale-125 transition-transform" />
      <Handle type="source" position={Position.Right} className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-right-[28px] z-10 hover:!bg-[#a3be8c] hover:!scale-125 transition-transform" />
    </div>
  );
};

export default function TaskPage({ onBack, onSwitchToChat }: { onBack: () => void; onSwitchToChat?: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  
  const [currentNodeLogs, setCurrentNodeLogs] = useState<LogEntry[]>([]);
  
  // 🟢 2. 增加智能滚动 Refs
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const isAutoScroll = useRef(true);
  
  const [taskToDelete, setTaskToDelete] = useState<string | null>(null);
  const [logModalNodeId, setLogModalNodeId] = useState<string | null>(null);

  // 🟢 3. 增加精准制导输入框状态
  const [pushMessage, setPushMessage] = useState('');

  // 🟢 阻塞加载状态
  const [isCheckingOut, setIsCheckingOut] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[]);

  const nodeTypes = useMemo(() => ({ custom: TaskMonitorNode }), []);

  const loadTasks = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tasks');
      if (res.ok) setTasks(await res.json());
    } catch (e) { toast.error("获取任务列表失败"); }
  };

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectTask = async (task: Task) => {
    setIsCheckingOut(true);
    setSelectedTaskId(task.id);
    setNodes([]);
    setEdges([]);
    setCurrentNodeLogs([]);

    try {
      // 🌟 核心修改：不再去拉静态 /api/graphs，直接拉取该任务当前的完整运行时状态
      const stateRes = await fetch(`http://localhost:8000/api/tasks/${task.id}/state`);
      
      if (stateRes.ok) {
        const stateData = await stateRes.json();
        
        // 🌟 直接使用后端落盘的动态裂变后的 graph，保证 ID 100% 匹配
        const graph = stateData.graph || { nodes: [], edges: [] };
        
        // 兼容你的 FastAPI 包装：如果后端是 dag_state 就取 dag_state，否则 node_states
        const actualNodeStates = stateData.dag_state || stateData.node_states || {};
        const isCurrentlyRunning = stateData.state === 'running' || stateData.task_state === 'running';

        const flowNodes = graph.nodes.map((n: any, idx: number) => {
          const nodeInfo = actualNodeStates[n.id];
          const currentState = typeof nodeInfo === 'object' && nodeInfo !== null ? (nodeInfo.state || 'ready') : (nodeInfo || 'ready');
          
          let posX = 100 + (idx % 3) * 280, posY = 100 + Math.floor(idx / 3) * 180;
          if (Array.isArray(n.position)) {
              posX = n.position[0]; posY = n.position[1];
          } else if (n.position?.x !== undefined) {
              posX = n.position.x; posY = n.position.y;
          }

          return {
            id: n.id,
            type: 'custom',
            position: { x: posX, y: posY },
            data: {
              label: n.name && n.name.trim() ? n.name : n.id,
              shape: idx % 2 === 0 ? sketchyShape1 : sketchyShape2,
              isTaskRunning: isCurrentlyRunning,
              nodeState: currentState.toLowerCase(),
              onShowLog: (nodeId: string) => setLogModalNodeId(nodeId)
            }
          };
        });

        const flowEdges = graph.edges.map((e: any) => ({
          id: `e-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          animated: isCurrentlyRunning,
          style: { strokeWidth: 3, stroke: isCurrentlyRunning ? '#D47A5A' : '#1a1a1a' }
        }));

        setNodes(flowNodes);
        setEdges(flowEdges);
      } else {
        toast.error(`无法获取任务状态记录`);
      }
    } catch (e) {
      toast.error(`加载图谱失败`);
    } finally {
      setIsCheckingOut(false);
    }
  };

  useEffect(() => {
    if (!selectedTaskId || !logModalNodeId) return;

    const fetchNodeLogs = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/log`);
        if (res.ok) {
          const data = await res.json();
          const targetLogs = data.grouped_logs[logModalNodeId] || [];
          setCurrentNodeLogs(targetLogs);
        }
      } catch (e) { /* ignore */ }
    };

    fetchNodeLogs();
    const interval = setInterval(fetchNodeLogs, 1500);
    return () => clearInterval(interval);
  }, [selectedTaskId, logModalNodeId]);

  useEffect(() => {
    if (!selectedTaskId) return;

    const fetchTaskState = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/state`);
        if (res.ok) {
          const data = await res.json();
          // 🌟 兼容后端结构
          const nodeStates = data.dag_state || data.node_states || {};
          const isCurrentlyRunning = data.state === 'running' || data.task_state === 'running';

          setNodes((nds) =>
            nds.map((n) => {
              // 取出真实状态
              const nodeInfo = nodeStates[n.id];
              const currentState = (typeof nodeInfo === 'object' && nodeInfo !== null ? nodeInfo.state : nodeInfo) || 'ready';
              
              if (n.data.nodeState !== currentState.toLowerCase() || n.data.isTaskRunning !== isCurrentlyRunning) {
                return {
                  ...n,
                  data: {
                    ...n.data,
                    nodeState: currentState.toLowerCase(),
                    isTaskRunning: isCurrentlyRunning
                  }
                };
              }
              return n;
            })
          );

          setEdges((eds) =>
            eds.map((e) => {
              if (e.animated !== isCurrentlyRunning) {
                return {
                  ...e,
                  animated: isCurrentlyRunning,
                  style: { strokeWidth: 3, stroke: isCurrentlyRunning ? '#D47A5A' : '#1a1a1a' }
                };
              }
              return e;
            })
          );
        }
      } catch (e) { /* ignore */ }
    };

    fetchTaskState();
    const interval = setInterval(fetchTaskState, 1500);
    return () => clearInterval(interval);
  }, [selectedTaskId, setNodes]);

  // 🟢 4. 智能滚动处理逻辑
  const handleLogScroll = () => {
    if (!logsContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
    isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  useEffect(() => {
    if (isAutoScroll.current && logModalNodeId && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentNodeLogs, logModalNodeId]);

  // 🟢 5. 发送指令方法
  const handleForcePush = async () => {
    if (!pushMessage.trim() || !selectedTaskId) return;
    const msg = pushMessage.trim();
    setPushMessage('');
    isAutoScroll.current = true; // 发送指令后强制滚到底部以便查看结果

    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: msg, node_id: logModalNodeId })
      });
      if (res.ok) toast.success(`已向节点 [${logModalNodeId}] 发送指令`);
      else toast.error('任务可能已结束，注入失败');
    } catch (e) { toast.error('网络错误'); }
  };

  const confirmDeleteTask = async () => {
    if (!taskToDelete) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskToDelete}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success("任务已强制终止并彻底删除！");
        setTaskToDelete(null);
        if (selectedTaskId === taskToDelete) {
          setSelectedTaskId(null);
          setNodes([]);
          setEdges([]);
        }
        loadTasks();
      }
    } catch (e) { toast.error("操作失败，请检查网络"); }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">

      {isCheckingOut && (
        <div className="fixed inset-0 bg-cream/70 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-10 flex flex-col items-center justify-center gap-6 shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] -rotate-1 min-w-[320px]">
            <Activity size={64} className="animate-pulse text-terracotta" strokeWidth={2} />
            <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              LOADING TASK...
            </h3>
          </div>
        </div>
      )}

      {/* 悬浮日志弹窗 */}
      {logModalNodeId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/50 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-5xl h-[85vh] flex flex-col relative rotate-[0.5deg]">
            <button onClick={() => setLogModalNodeId(null)} className="absolute top-5 right-6 hover:rotate-90 hover:text-terracotta transition-all z-10">
              <X size={36} strokeWidth={3} />
            </button>
            
            <div className="p-6 border-b-4 border-ink bg-[#EBCB8B]/30 shrink-0 flex items-center gap-4">
               <div className="p-3 bg-paper border-4 border-ink -rotate-3" style={sketchyShape1}>
                 <Terminal size={28} className="text-ink" strokeWidth={2.5}/>
               </div>
               <div>
                 <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                   NODE LOGS
                 </h3>
                 <span className="font-bold text-ink/60">Target: {logModalNodeId}</span>
               </div>
            </div>
            
            {/* 🔴 日志列表容器增加 ref 和 onScroll 监听 */}
            <div 
              ref={logsContainerRef}
              onScroll={handleLogScroll}
              className="flex-1 overflow-y-auto p-8 bg-ink/5 font-mono text-[14px] leading-relaxed shadow-[inset_0px_4px_10px_rgba(0,0,0,0.05)]"
            >
               {currentNodeLogs.length === 0 ? (
                 <div className="flex flex-col items-center justify-center h-full opacity-40 gap-4 text-ink">
                   <Box size={64} strokeWidth={1.5} />
                   <p className="text-xl font-bold font-sans">No execution logs found for this node yet.</p>
                 </div>
               ) : (
                 <div className="flex flex-col gap-2">
                   {currentNodeLogs.map((log, idx) => {
                     const timeStr = new Date(log.timestamp * 1000).toLocaleTimeString('en-US', { hour12: false });
                     let colorClass = "text-ink/80"; 
                     if (log.type === "SYSTEM") colorClass = "text-ink/50";
                     if (log.type === "THOUGHT") colorClass = "text-[#3498DB] font-bold";
                     if (log.type === "TOOL_CALL") colorClass = "text-[#EBCB8B] font-bold";
                     if (log.type === "TOOL") colorClass = "text-[#a3be8c]";
                     if (log.type === "ERROR") colorClass = "text-[#bf616a] font-black";
                     if (log.type === "WARNING") colorClass = "text-[#d08770] font-bold";

                     return (
                       <div key={idx} className="flex gap-4 hover:bg-ink/5 p-1 rounded transition-colors break-all">
                         <span className="opacity-40 shrink-0 select-none">[{timeStr}]</span>
                         <span className={`shrink-0 w-24 select-none ${colorClass}`}>[{log.type}]</span>
                         <span className={`whitespace-pre-wrap ${colorClass}`}>
                           {log.content}
                         </span>
                       </div>
                     );
                   })}
                   {/* 自动滚动锚点 */}
                   <div ref={logEndRef} className="h-4" />
                 </div>
               )}
            </div>
            
            {/* 🔴 6. 新版日志弹窗底部：输入框替代了“滚动到底部”按钮 */}
            <div className="p-6 border-t-4 border-ink bg-paper shrink-0 flex gap-4">
              <input
                style={sketchyShape3} 
                value={pushMessage} 
                onChange={(e) => setPushMessage(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleForcePush(); }}
                placeholder={`向 ${logModalNodeId} 节点发送精确指令...`} 
                className="flex-1 bg-[#FDF8F0] border-4 border-ink px-6 py-4 font-bold focus:outline-none focus:bg-white transition-all shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] text-lg -rotate-[0.5deg] placeholder:text-ink/30"
              />
              <button
                style={sketchyShape1} 
                onClick={handleForcePush} 
                disabled={!pushMessage.trim()}
                className="bg-ink text-paper px-8 font-black flex items-center gap-3 border-4 border-ink hover:bg-terracotta hover:text-ink transition-all active:scale-95 disabled:opacity-50 shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] rotate-2"
              >
                <Send size={26} strokeWidth={2.5} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      {taskToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black text-[#bf616a] tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TERMINATE?</h3>
              <button onClick={() => setTaskToDelete(null)} className="hover:scale-110 hover:text-terracotta transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要终止该任务并删除所有执行记录吗？该节点对应的物理文件夹将被彻底抹除。</p>
            <div className="flex gap-4 mt-2 rotate-1">
              <button onClick={() => setTaskToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 hover:bg-sand transition-all">CANCEL</button>
              <button onClick={confirmDeleteTask} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 hover:bg-red-600 transition-all">TERMINATE</button>
            </div>
          </div>
        </div>
      )}

      {/* 左侧导航与任务列表 */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          {onSwitchToChat && (
            <button onClick={onSwitchToChat} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none rotate-3 hover:rotate-0 group" title="Go to Chat">
              <MessageCircle size={28} strokeWidth={3} className="text-ink group-hover:translate-x-1 transition-transform" />
            </button>
          )}
          <div style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#EBCB8B] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2">
            <Activity size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TASKS</span>
          </div>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-24 h-6 bg-[#EBCB8B]/40 border-2 border-ink rotate-2 z-10" style={sketchyShape1}></div>
          <div className="text-sm font-black text-ink uppercase tracking-widest mt-2 ml-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            <span className="bg-ink text-paper px-2 py-1 rotate-2 inline-block" style={sketchyShape2}>MONITOR</span>
          </div>
          
          <div className="flex-1 overflow-y-auto flex flex-col gap-4 pr-1 mt-2">
            {tasks.length === 0 ? (
               <div className="text-center font-bold text-ink/40 mt-10 italic">No tasks running or archived.</div>
            ) : (
              tasks.map((task, idx) => (
                <div 
                  key={task.id} 
                  onClick={() => handleSelectTask(task)}
                  className={`group cursor-pointer p-4 border-2 transition-all relative flex flex-col gap-2
                    ${idx % 3 === 0 ? 'rotate-1' : idx % 2 === 0 ? '-rotate-1' : 'rotate-2'}
                    ${selectedTaskId === task.id ? 'bg-terracotta border-ink text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream border-ink text-ink hover:bg-sand hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}
                  style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold truncate max-w-[180px] text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{task.name}</span>
                    {task.state === 'running' && <Activity size={18} strokeWidth={3} className="animate-pulse" />}
                  </div>
                  <div className="flex items-center gap-2 text-xs font-bold uppercase opacity-80">
                    <Clock size={14} strokeWidth={3} /> {task.create_time.split(' ')[1]} 
                    <span className="ml-auto bg-ink text-paper px-1.5 py-0.5 rounded-sm" style={sketchyShape1}>{task.state}</span>
                  </div>

                  <div 
                    onClick={(e) => { e.stopPropagation(); setTaskToDelete(task.id); }}
                    className="absolute -right-3 -top-3 bg-[#bf616a] text-paper border-2 border-ink p-1.5 opacity-0 group-hover:opacity-100 transition-all hover:scale-110 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] cursor-pointer"
                    style={{ borderRadius: '50% 10% 50% 10%' }}
                    title="Terminate Task"
                  >
                    <Trash2 size={16} strokeWidth={2.5}/>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 右侧全屏图谱视图 */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] overflow-hidden relative rotate-[0.5deg] z-10 flex flex-col">
        <div className="absolute -top-4 right-12 w-32 h-8 bg-terracotta/40 border-2 border-ink -rotate-3 z-50" style={sketchyShape2}></div>
        
        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0 absolute top-0 left-0 right-0 z-10 pointer-events-none">
          <div className="flex items-center gap-4 bg-paper/80 backdrop-blur-md p-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] pointer-events-auto -rotate-1" style={sketchyShape3}>
            <Terminal size={24} className="text-terracotta" strokeWidth={3} />
            <h2 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>GRAPH VISUALIZER</h2>
          </div>
        </div>
        
        <div className="flex-1 w-full h-full bg-cream/30">
          {selectedTaskId ? (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              nodesDraggable={true}
              elementsSelectable={true}
              zoomOnScroll={true}
              panOnDrag={true}
              fitView
              className="!h-full"
            >
              <Background gap={24} size={2} color="#1a1a1a" variant={'dots' as any} />
            </ReactFlow>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-ink gap-6">
               <div style={sketchyShape1} className="p-8 border-4 border-ink bg-cream shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] -rotate-3">
                 <Activity size={60} strokeWidth={2} className="text-[#EBCB8B]" />
               </div>
               <p className="text-2xl font-black rotate-2 text-ink/60" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Select a task to view its flow...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}