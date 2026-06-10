import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  ArrowLeft, Terminal, Trash2, X, Activity, Clock, Box, Send, MessageCircle, RefreshCw,
  Square, Play, AlertTriangle, Plus, ChevronDown, ChevronUp
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
  state: 'running' | 'completed' | 'failed' | 'idle' | 'interrupted' | 'killed';
  step: number;
  create_time: string;
}

interface LogEntry {
  timestamp: number;
  type: string;
  content: string;
  node_id?: string;
  [key: string]: string | number | undefined;
}

interface TaskMonitorNodeData {
  nodeState: 'running' | 'completed' | 'error' | 'waiting' | 'skipped' | 'ready';
  isTaskRunning: boolean;
  label: string;
  shape: Record<string, string>;
  inHandles?: string[];
  outHandles?: string[];
  onShowLog: (id: string) => void;
  onReset: (id: string) => void;
}

interface TaskMonitorNodeProps {
  id: string;
  data: TaskMonitorNodeData;
  selected?: boolean;
}

interface GraphNode {
  id: string;
  name?: string;
  position?: [number, number] | { x: number; y: number };
}

interface GraphEdge {
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}

// ==========================================
// 🌟 1. 监控节点组件 (移除冗余色块，保留右上角标签)
// ==========================================
const TaskMonitorNode = ({ id, data, selected }: TaskMonitorNodeProps) => {
  let statusColor = "bg-[#EBCB8B]";
  let statusText = "READY";
  let isPulsing = false;

  if (data.nodeState === "running") {
    statusColor = "bg-[#3498DB]"; statusText = "RUNNING"; isPulsing = true;
  } else if (data.nodeState === "completed") {
    statusColor = "bg-[#a3be8c]"; statusText = "COMPLETED";
  } else if (data.nodeState === "error") {
    statusColor = "bg-[#bf616a]"; statusText = "ERROR"; isPulsing = true;
  } else if (data.nodeState === "waiting") {
    statusColor = "bg-[#d08770]"; statusText = "WAITING"; isPulsing = true;
  } else if (data.nodeState === "skipped") {
    statusColor = "bg-ink/20"; statusText = "SKIPPED";
  }

  const isTaskRunning = data.isTaskRunning;

  // 动态引脚均分计算
  const getHandleTop = (idx: number, total: number) => {
    return `${(100 / (total + 1)) * (idx + 1)}%`;
  };

  return (
    <div 
      style={data.shape} 
      className={`bg-paper p-4 min-w-[200px] transition-all duration-200 hover:-translate-y-1 border-4 border-ink relative
        ${selected ? 'shadow-[8px_8px_0px_0px_rgba(212,122,90,1)]' : 
          isTaskRunning ? 'shadow-[6px_6px_0px_0px_rgba(212,122,90,1)]' : 
          'shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}
        ${isPulsing && isTaskRunning ? 'ring-4 ring-offset-2 ring-[#3498DB]/30' : ''}`}
    >
      {/* 右上角醒目的状态贴纸 */}
      <div className={`absolute -top-3 -right-2 px-2 py-0.5 text-[11px] font-black tracking-widest border-2 border-ink text-paper rotate-3 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] ${statusColor}`} style={{ fontFamily: '"Comic Sans MS", cursive' }}>
        {statusText}
      </div>

      <div className="flex items-center mb-3 border-b-2 border-ink/10 pb-2 pt-1">
        <div className="font-black text-lg truncate pr-2 text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          {data.label}
        </div>
      </div>
      
      <div className="flex gap-2 w-full">
        <button
          onClick={(e) => { e.stopPropagation(); data.onShowLog(id); }}
          className="flex-1 flex items-center justify-center gap-1 bg-cream border-2 border-ink py-2 text-sm font-black hover:bg-terracotta hover:text-paper transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-0.5"
          style={sketchyShape3}
          title="查看日志"
        >
          <Terminal size={14} strokeWidth={3} /> Logs
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); data.onReset(id); }}
          className="px-3 flex items-center justify-center bg-[#EBCB8B] border-2 border-ink py-2 text-ink hover:bg-[#d8b877] transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-0.5"
          style={sketchyShape1}
          title="重置节点并执行下游"
        >
          <RefreshCw size={14} strokeWidth={3} />
        </button>
      </div>

      {data.inHandles?.map((handleId: string, idx: number) => (
        <Handle key={`in-${handleId}`} id={handleId} type="target" position={Position.Left} className="!bg-ink !w-3 !h-3 !border-2 !border-paper !-left-[22px] z-10" style={{ top: getHandleTop(idx, data.inHandles!.length) }} />
      ))}
      {data.outHandles?.map((handleId: string, idx: number) => (
        <Handle key={`out-${handleId}`} id={handleId} type="source" position={Position.Right} className="!bg-ink !w-3 !h-3 !border-2 !border-paper !-right-[22px] z-10" style={{ top: getHandleTop(idx, data.outHandles!.length) }} />
      ))}
    </div>
  );
};

export default function TaskPage({ onBack, onSwitchToChat }: { onBack: () => void; onSwitchToChat?: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [currentNodeLogs, setCurrentNodeLogs] = useState<LogEntry[]>([]);
  
  // 🌟 新增：Dashboard 展开/折叠状态
  const [isDashboardOpen, setIsDashboardOpen] = useState(true);
  
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const isAutoScroll = useRef(true);
  
  const [taskToDelete, setTaskToDelete] = useState<string | null>(null);
  const [logModalNode, setLogModalNode] = useState<{ id: string; name: string; state: string } | null>(null);

  const [pushMessage, setPushMessage] = useState('');
  const [isCheckingOut, setIsCheckingOut] = useState(false);

  // --- 🌟 启动新任务 (JSON 模板模式) ---
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [availableGraphs, setAvailableGraphs] = useState<Array<{ name: string }>>([]);
  const [launchTaskName, setLaunchTaskName] = useState('my_awesome_task');
  const [launchGraphName, setLaunchGraphName] = useState('');
  const [launchInputs, setLaunchInputs] = useState('');
  // 👇 新增这个状态，用于控制自定义下拉菜单的展开/收起
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[]);

  const nodeTypes = useMemo(() => ({ custom: TaskMonitorNode }), []);

  const currentSelectedTask = useMemo(() => {
    return tasks.find(t => t.id === selectedTaskId) || null;
  }, [tasks, selectedTaskId]);

  const loadTasks = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/tasks');
      if (res.ok) setTasks(await res.json());
    } catch { /* silent */ }
  };

  const loadAvailableGraphs = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/graphs');
      if (res.ok) {
        const data = await res.json();
        setAvailableGraphs(data);
        if (data.length > 0 && !launchGraphName) {
          setLaunchGraphName(data[0].name.replace(/\.json$/, ''));
        }
      }
    } catch { toast.error("获取工作流模板失败"); }
  };

  // 🌟 核心改进：当切换工作流时，自动拉取 Schema 并生成带提示的 JSON 模板
  useEffect(() => {
    if (!launchGraphName) return;
    fetch(`http://localhost:8000/api/graphs/${launchGraphName}/schema`)
      .then(res => res.json())
      .then(data => {
        const schema = data.global_schema || {};
        const template: Record<string, string> = {};
        Object.keys(schema).forEach(key => {
          template[key] = schema[key].description || `填写 ${key} 的值`;
        });
        setLaunchInputs(JSON.stringify(template, null, 2));
      })
      .catch(() => toast.error("无法加载该工作流的入参配置"));
  }, [launchGraphName]);

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 3000);
    return () => clearInterval(interval);
  }, []);

  // 🌟 强壮的极限容错状态解析器 (修复 READY 问题)
  const extractState = (rawState: string | { state?: string; value?: string } | undefined) => {
    if (!rawState) return 'ready';
    // 兼容字符串、对象或包含 value 的枚举属性
    let s = typeof rawState === 'string' ? rawState : (rawState.state || rawState.value || String(rawState));
    s = s.toLowerCase();
    if (s.includes('completed')) return 'completed';
    if (s.includes('running')) return 'running';
    if (s.includes('error')) return 'error';
    if (s.includes('waiting')) return 'waiting';
    if (s.includes('skipped')) return 'skipped';
    return 'ready';
  };

  const fetchTaskState = useCallback(async () => {
    if (!selectedTaskId) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/state`);
      if (res.ok) {
        const data = await res.json();
        // 增加对多级后端的容错判断
        const nodeStates = data.node_state || data.dag_state || data.node_states || data.nodes || {};
        const isCurrentlyRunning = ['running', 'starting'].includes((data.state || '').toLowerCase());

        setNodes((nds) =>
          nds.map((n) => {
            const currentState = extractState(nodeStates[n.id]);
            if (n.data.nodeState !== currentState || n.data.isTaskRunning !== isCurrentlyRunning) {
              return { ...n, data: { ...n.data, nodeState: currentState, isTaskRunning: isCurrentlyRunning } };
            }
            return n;
          })
        );

        setEdges((eds) =>
          eds.map((e) => {
            if (e.animated !== isCurrentlyRunning) {
              return { ...e, animated: isCurrentlyRunning, style: { strokeWidth: 3, stroke: isCurrentlyRunning ? '#D47A5A' : '#1a1a1a' } };
            }
            return e;
          })
        );
      }
    } catch { /* ignore */ }
  }, [selectedTaskId, setNodes, setEdges]);

  // 重置节点 (触发后立即刷新界面，告别等待感！)
  const handleResetNode = async (nodeId: string) => {
    if (!selectedTaskId) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/nodes/${nodeId}/reset`, { method: 'POST' });
      if (res.ok) {
        toast.success(`已重置节点 [${nodeId}] 并执行下游`);
        fetchTaskState(); // 🚀 立马强制刷新状态
        loadTasks();
      } else {
        const errData = await res.json().catch(() => ({}));
        toast.error(errData.detail || '重置失败');
      }
    } catch {
      toast.error('网络错误');
    }
  };

  const handleKillTask = async () => {
    if (!selectedTaskId) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/stop`, { method: 'POST' });
      if (res.ok) {
        toast.success("进程已优雅中止，Checkpoint 存档已留存。");
        fetchTaskState();
        loadTasks();
      } else {
        toast.error('中止任务失败');
      }
    } catch { toast.error('网络错误'); }
  };

  // 提交创建任务
  const handleLaunchTaskSubmit = async () => {
    if (!launchTaskName.trim() || !launchGraphName) {
      toast.error("任务名和工作流模板不能为空！");
      return;
    }
    
    let parsedInputs = {};
    try {
      parsedInputs = JSON.parse(launchInputs);
    } catch {
      toast.error("JSON 格式错误！请确保属性名和字符串值都使用了规范的双引号。");
      return;
    }

    try {
      const res = await fetch('http://localhost:8000/api/tasks/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_name: launchTaskName.trim(),
          graph_name: launchGraphName,
          inputs: parsedInputs
        })
      });

      if (res.ok) {
        const data = await res.json();
        toast.success("🚀 工作流任务已成功抛入后台运行！");
        setIsCreateModalOpen(false);
        loadTasks();
        if (data.task_id) setSelectedTaskId(data.task_id);
      } else {
        const errData = await res.json().catch(() => ({}));
        toast.error(errData.detail || "创建失败，请检查输入参数是否合法。");
      }
    } catch { toast.error("网络错误，启动任务失败"); }
  };

  const handleSelectTask = async (task: Task) => {
    setIsCheckingOut(true);
    setSelectedTaskId(task.id);
    setNodes([]); setEdges([]); setCurrentNodeLogs([]);

    try {
      const stateRes = await fetch(`http://localhost:8000/api/tasks/${task.id}/state`);
      if (stateRes.ok) {
        const stateData = await stateRes.json();
        const graph = stateData.graph || { nodes: [], edges: [] };
        // 兼容多级状态结构
        const nodeStates = stateData.node_state || stateData.dag_state || stateData.node_states || stateData.nodes || {};
        const isCurrentlyRunning = ['running', 'starting'].includes((stateData.state || '').toLowerCase());

        const flowNodes = (graph.nodes || []).map((n: GraphNode, idx: number) => {
          if (!n) return null;
          const currentState = extractState(nodeStates[n.id]);
          
          let posX = 100 + (idx % 3) * 280, posY = 100 + Math.floor(idx / 3) * 180;
          if (Array.isArray(n.position)) { posX = n.position[0]; posY = n.position[1]; } 
          else if (n.position?.x !== undefined) { posX = n.position.x; posY = n.position.y; }

          const inHandles = [...new Set((graph.edges || []).filter((e: GraphEdge) => e.target === n.id).map((e: GraphEdge) => e.targetHandle || 'default'))];
          const outHandles = [...new Set((graph.edges || []).filter((e: GraphEdge) => e.source === n.id).map((e: GraphEdge) => e.sourceHandle || 'default'))];

          return {
            id: n.id, type: 'custom', position: { x: posX, y: posY },
            data: {
              label: n.name && n.name.trim() ? n.name : n.id,
              shape: idx % 2 === 0 ? sketchyShape1 : sketchyShape2,
              isTaskRunning: isCurrentlyRunning,
              nodeState: currentState,
              inHandles, outHandles,
              onShowLog: (nodeId: string) => setLogModalNode({ id: nodeId, name: n.name || nodeId, state: currentState }),
              onReset: (nodeId: string) => handleResetNode(nodeId)
            }
          };
        }).filter(Boolean) as Node[];

        const flowEdges = (graph.edges || []).map((e: GraphEdge) => {
          if (!e || !e.source || !e.target) return null;
          return {
            id: `e-${e.source}-${e.target}`, source: e.source, target: e.target,
            animated: isCurrentlyRunning,
            style: { strokeWidth: 3, stroke: isCurrentlyRunning ? '#D47A5A' : '#1a1a1a' }
          };
        }).filter(Boolean) as Edge[];

        setNodes(flowNodes); setEdges(flowEdges);
      }
    } catch { toast.error(`加载图谱失败`); } finally { setIsCheckingOut(false); }
  };

  useEffect(() => {
    if (!selectedTaskId || !logModalNode?.id) return;
    const fetchNodeLogs = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/log`);
        if (res.ok) {
          const data = await res.json();
          setCurrentNodeLogs(data.grouped_logs[logModalNode.id] || []);
        }
      } catch { /* ignore */ }
    };
    fetchNodeLogs();
    const interval = setInterval(fetchNodeLogs, 1500);
    return () => clearInterval(interval);
  }, [selectedTaskId, logModalNode?.id]);

  useEffect(() => {
    if (!selectedTaskId) return;
    fetchTaskState();
    const interval = setInterval(fetchTaskState, 1500);
    return () => clearInterval(interval);
  }, [selectedTaskId, fetchTaskState]);

  const handleLogScroll = () => {
    if (!logsContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
    isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  useEffect(() => {
    if (isAutoScroll.current && logModalNode?.id && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentNodeLogs, logModalNode?.id]);

  const handleForcePush = async () => {
    if (!pushMessage.trim() || !selectedTaskId || !logModalNode?.id) return;
    const msg = pushMessage.trim(); setPushMessage(''); isAutoScroll.current = true;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${selectedTaskId}/submit`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: msg, node_id: logModalNode.id })
      });
      if (res.ok) toast.success(`指令已发送给 [${logModalNode.name}]`);
      else toast.error('指令注入被拒');
    } catch { toast.error('网络错误'); }
  };

  const confirmDeleteTask = async () => {
    if (!taskToDelete) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskToDelete}`, { method: 'DELETE' });
      if (res.ok) {
        toast.success("任务及存档已彻底抹除"); setTaskToDelete(null);
        if (selectedTaskId === taskToDelete) { setSelectedTaskId(null); setNodes([]); setEdges([]); }
        loadTasks();
      }
    } catch { toast.error("删除失败"); }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">

      {isCheckingOut && (
        <div className="fixed inset-0 bg-cream/70 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-10 flex flex-col items-center justify-center gap-6 shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] -rotate-1 min-w-[320px]">
            <Activity size={64} className="animate-pulse text-terracotta" strokeWidth={2} />
            <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>LOADING TASK...</h3>
          </div>
        </div>
      )}

      {/* 日志弹窗 */}
      {logModalNode && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/50 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-5xl h-[85vh] flex flex-col relative overflow-hidden">
            <button onClick={() => setLogModalNode(null)} className="absolute top-5 right-6 hover:rotate-90 hover:text-terracotta transition-all z-20"><X size={36} strokeWidth={3} /></button>

            {/* 人工干预强黄色横幅 */}
            {logModalNode.state === 'waiting' && (
              <div className="bg-[#d08770] text-paper py-2.5 flex items-center justify-center gap-2 font-black tracking-widest border-b-4 border-ink text-sm shrink-0" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                <AlertTriangle size={18} className="animate-bounce text-paper" />
                HUMAN INTERVENTION REQUIRED: AWAITING YOUR COMMAND
              </div>
            )}
            
            <div className="p-6 border-b-4 border-ink bg-[#EBCB8B]/30 shrink-0 flex items-center gap-4">
               <div className="p-3 bg-paper border-4 border-ink -rotate-3" style={sketchyShape1}><Terminal size={28} className="text-ink" strokeWidth={2.5}/></div>
               <div>
                 <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{logModalNode.name}</h3>
                 <span className="font-bold text-ink/60 text-sm">Target ID: {logModalNode.id}</span>
               </div>
            </div>
            
            <div ref={logsContainerRef} onScroll={handleLogScroll} className="flex-1 overflow-y-auto p-8 bg-ink/5 font-mono text-[14px] leading-relaxed shadow-[inset_0px_4px_10px_rgba(0,0,0,0.05)]">
               {currentNodeLogs.length === 0 ? (
                 <div className="flex flex-col items-center justify-center h-full opacity-40 gap-4 text-ink">
                   <Box size={64} strokeWidth={1.5} />
                   <p className="text-xl font-bold font-sans">No execution logs found.</p>
                 </div>
               ) : (
                 <div className="flex flex-col gap-2">
                   {currentNodeLogs.map((log, idx) => {
                     const timeStr = new Date(log.timestamp).toLocaleTimeString('en-US', { hour12: false });
                     let colorClass = "text-ink/80";
                     if (log.type === "SYSTEM") colorClass = "text-ink/50";
                     if (log.type === "THOUGHT") colorClass = "text-[#3498DB] font-bold";
                     if (log.type === "TOOL_CALL") colorClass = "text-[#EBCB8B] font-bold";
                     if (log.type === "TOOL") colorClass = "text-[#a3be8c]";
                     if (log.type === "ERROR") colorClass = "text-[#bf616a] font-black";
                     if (log.type === "WARNING") colorClass = "text-[#d08770] font-bold";
                     const isArtifact = log.type.toUpperCase() === "ARTIFACT";
                     if (isArtifact) colorClass = "text-[#88c0d0] font-black";
                     return (
                       <div key={idx} className={`flex ${isArtifact ? 'flex-col gap-2' : 'gap-4'} hover:bg-ink/5 p-1 rounded transition-colors break-all`}>
                         <div className="flex gap-4 items-start">
                           <span className="opacity-40 shrink-0 select-none">[{timeStr}]</span>
                           <span className={`shrink-0 w-24 select-none ${colorClass}`}>[{log.type}]</span>
                           {!isArtifact && <span className={`whitespace-pre-wrap ${colorClass}`}>{log.content}</span>}
                         </div>
                         {isArtifact && (
                           <div className="mt-2 w-full h-[600px] border-4 border-ink bg-white shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] relative overflow-hidden" style={sketchyShape3}>
                             <div className="absolute top-0 left-0 right-0 h-8 bg-ink/5 border-b-2 border-ink flex items-center px-4 gap-2">
                               <div className="w-3 h-3 rounded-full bg-[#bf616a] border-2 border-ink"></div>
                               <div className="w-3 h-3 rounded-full bg-[#EBCB8B] border-2 border-ink"></div>
                               <div className="w-3 h-3 rounded-full bg-[#a3be8c] border-2 border-ink"></div>
                               <span className="text-xs font-bold text-ink/40 ml-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Data Dashboard View</span>
                             </div>
                             <iframe
                               srcDoc={log.content}
                               className="w-full h-[calc(100%-2rem)] mt-8 border-none"
                               sandbox="allow-scripts allow-popups"
                             />
                           </div>
                         )}
                       </div>
                     );
                   })}
                   <div ref={logEndRef} className="h-4" />
                 </div>
               )}
            </div>
            
            <div className="p-6 border-t-4 border-ink bg-paper shrink-0 flex gap-4">
              <input
                style={sketchyShape3} value={pushMessage} onChange={(e) => setPushMessage(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleForcePush(); }}
                placeholder={`Tell [${logModalNode.name}] what to do next...`} 
                className={`flex-1 bg-[#FDF8F0] border-4 border-ink px-6 py-4 font-bold focus:outline-none focus:bg-white transition-all shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] text-lg
                  ${logModalNode.state === 'waiting' ? 'border-[#d08770] placeholder:text-[#d08770]/60' : 'placeholder:text-ink/30'}`}
              />
              <button
                style={sketchyShape1} onClick={handleForcePush} disabled={!pushMessage.trim()}
                className="bg-ink text-paper px-8 font-black flex items-center gap-3 border-4 border-ink hover:bg-terracotta hover:text-ink transition-all active:scale-95 disabled:opacity-50 shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] rotate-2"
              >
                <Send size={26} strokeWidth={2.5} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🌟 重新设计的创建任务弹窗 (JSON 模板预填充) */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-lg p-8 relative rotate-1">
            <button onClick={() => { setIsCreateModalOpen(false); setIsDropdownOpen(false); }} className="absolute top-4 right-4 hover:rotate-90 transition-transform"><X size={32} strokeWidth={3} /></button>
            <h3 className="text-3xl font-black mb-6 tracking-widest text-terracotta" style={{ fontFamily: '"Comic Sans MS", cursive' }}>LAUNCH MISSION</h3>
            
            <p className="font-bold mb-2 opacity-70 text-sm">1. Select Deployed Graph:</p>
            <div className="relative mb-4">
              {/* 🌟 自定义下拉框触发按钮 */}
              <div
                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                style={sketchyShape3}
                className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold cursor-pointer shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-between hover:-translate-y-[1px] transition-transform select-none"
              >
                <span className="truncate">
                  {availableGraphs.length === 0 ? "No deployed graphs" : (launchGraphName || "Select a graph...")}
                </span>
                <ChevronDown
                  size={20}
                  strokeWidth={3}
                  className={`text-ink transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`}
                />
              </div>

              {/* 🌟 完全可控的手绘风下拉菜单列表 */}
              {isDropdownOpen && availableGraphs.length > 0 && (
                <div
                  className="absolute left-0 right-0 top-[110%] bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] z-[200] max-h-56 overflow-y-auto p-2 flex flex-col gap-1"
                  style={sketchyShape2}
                >
                  {availableGraphs.map((g, idx) => {
                    const nameClean = g.name.replace(/\.json$/, '');
                    const isSelected = launchGraphName === nameClean;
                    return (
                      <div
                        key={nameClean}
                        onClick={() => {
                          setLaunchGraphName(nameClean);
                          setIsDropdownOpen(false);
                        }}
                        style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3}
                        className={`p-3 font-bold text-lg cursor-pointer transition-all border-4
                          ${isSelected
                            ? 'bg-[#EBCB8B] border-ink text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]'
                            : 'border-transparent text-ink/80 hover:bg-cream hover:border-ink hover:text-ink hover:shadow-[2px_2px_0px_0px_rgba(26,26,26,0.5)] hover:-translate-y-[1px]'
                          }`}
                      >
                        {nameClean}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            <p className="font-bold mb-2 opacity-70 text-sm">2. Task Alias:</p>
            <input 
              value={launchTaskName} onChange={e => setLaunchTaskName(e.target.value)}
              style={sketchyShape3} className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold mb-4 focus:outline-none placeholder:text-ink/30"
              placeholder="e.g. data_pipeline_run_01"
            />

            <p className="font-bold mb-2 opacity-70 text-sm flex justify-between">
              <span>3. Configuration inputs (JSON):</span>
              <span className="text-[11px] text-[#bf616a] opacity-80 font-normal">须双引号严格键值对</span>
            </p>
            {/* 自动填充的键值描述模板文本框 */}
            <textarea 
              value={launchInputs} onChange={e => setLaunchInputs(e.target.value)}
              style={sketchyShape1} className="w-full bg-cream border-4 border-ink p-3 font-mono text-sm font-bold mb-6 focus:outline-none h-36 resize-none"
              spellCheck={false}
            />

            <div className="flex gap-4 mt-2">
              <button onClick={() => { setIsCreateModalOpen(false); setIsDropdownOpen(false); }} style={sketchyShape2} className="flex-1 py-3 bg-cream border-4 border-ink text-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all">
                CANCEL
              </button>
              <button onClick={handleLaunchTaskSubmit} style={sketchyShape1} className="flex-1 py-3 bg-terracotta border-4 border-ink text-paper font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-0.5 hover:shadow-none transition-all">
                LAUNCH <Play size={16} className="inline ml-1" strokeWidth={3} fill="currentColor"/>
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
              <h3 className="text-2xl font-black text-[#bf616a] tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DESTROY RECORD?</h3>
              <button onClick={() => setTaskToDelete(null)} className="hover:scale-110 hover:text-terracotta transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要抹除该记录吗？此操作属于物理删除！</p>
            <div className="flex gap-4 mt-2 rotate-1">
              <button onClick={() => setTaskToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 hover:bg-sand transition-all">CANCEL</button>
              <button onClick={confirmDeleteTask} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 hover:bg-red-600 transition-all">DELETE</button>
            </div>
          </div>
        </div>
      )}

      {/* 左侧导航与任务列表 */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group"><ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" /></button>
          {onSwitchToChat && <button onClick={onSwitchToChat} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none rotate-3 hover:rotate-0 group" title="Go to Chat"><MessageCircle size={28} strokeWidth={3} className="text-ink group-hover:translate-x-1 transition-transform" /></button>}
          <button 
            onClick={() => { loadAvailableGraphs(); setIsCreateModalOpen(true); setIsDropdownOpen(false); }}
            style={sketchyShape1} 
            className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#EBCB8B] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2 hover:bg-[#d8b877] transition-all active:translate-y-0.5 active:shadow-none"
          >
            <Plus size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>New</span>
          </button>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-24 h-6 bg-[#EBCB8B]/40 border-2 border-ink rotate-2 z-10" style={sketchyShape1}></div>
          <div className="text-sm font-black text-ink uppercase tracking-widest mt-2 ml-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            <span className="bg-ink text-paper px-2 py-1 rotate-2 inline-block" style={sketchyShape2}>MONITOR</span>
          </div>
          
          <div className="flex-1 overflow-y-auto flex flex-col gap-4 pr-1 mt-1">
            {tasks.length === 0 ? (
               <div className="text-center font-bold text-ink/40 mt-10 italic">No tasks running.</div>
            ) : (
              tasks.map((task, idx) => (
                <div 
                  key={task.id} onClick={() => handleSelectTask(task)}
                  className={`group cursor-pointer p-4 border-2 transition-all relative flex flex-col gap-2
                    ${idx % 3 === 0 ? 'rotate-1' : idx % 2 === 0 ? '-rotate-1' : 'rotate-2'}
                    ${selectedTaskId === task.id ? 'bg-[#EBCB8B] border-ink text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream border-ink text-ink hover:bg-sand hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}
                  style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold truncate max-w-[180px] text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{task.name}</span>
                    {task.state === 'running' && <Activity size={18} strokeWidth={3} className="animate-pulse" />}
                  </div>
                  <div className="flex items-center gap-2 text-xs font-bold uppercase opacity-80">
                    <Clock size={14} strokeWidth={3} /> {task.create_time ? task.create_time.split(' ')[1] : '--:--'} 
                    <span className="ml-auto bg-ink text-paper px-1.5 py-0.5 rounded-sm" style={sketchyShape1}>{task.state}</span>
                  </div>

                  <div onClick={(e) => { e.stopPropagation(); setTaskToDelete(task.id); }} className="absolute -right-3 -top-3 bg-[#bf616a] text-paper border-2 border-ink p-1.5 opacity-0 group-hover:opacity-100 transition-all hover:scale-110 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] cursor-pointer z-20" style={{ borderRadius: '50% 10% 50% 10%' }}>
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
        
        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0 absolute top-0 left-0 right-0 z-50 pointer-events-none">
          <div className="flex items-center gap-4 bg-paper/80 backdrop-blur-md p-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] pointer-events-auto -rotate-1" style={sketchyShape3}>
            <Terminal size={24} className="text-terracotta" strokeWidth={3} />
            <h2 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>GRAPH VISUALIZER</h2>
          </div>

          {selectedTaskId && currentSelectedTask?.state === 'running' && (
            <button
              onClick={handleKillTask} style={sketchyShape2}
              className="pointer-events-auto flex items-center gap-2 bg-[#bf616a] text-paper border-4 border-ink px-5 py-2.5 font-black text-base shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-red-500 hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all rotate-1"
            >
              <Square size={16} strokeWidth={3} fill="currentColor" /><span style={{ fontFamily: '"Comic Sans MS", cursive' }}>STOP PROCESS</span>
            </button>
          )}
        </div>
        
        <div className="flex-1 w-full h-full bg-cream/30 relative">
          
          {/* 🌟 新增：全局节点状态看板 Dashboard */}
          {selectedTaskId && (
            <div className="absolute top-6 right-6 z-50 flex flex-col w-80 items-end pointer-events-none">
              {/* 触发按钮 */}
              <button
                onClick={() => setIsDashboardOpen(!isDashboardOpen)}
                style={sketchyShape2}
                className="pointer-events-auto flex items-center gap-2 bg-[#EBCB8B] text-ink border-4 border-ink px-4 py-2 font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all"
              >
                <Activity size={18} strokeWidth={3} />
                <span className="tracking-widest text-sm" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DASHBOARD</span>
                {isDashboardOpen ? <ChevronUp size={18} strokeWidth={3} /> : <ChevronDown size={18} strokeWidth={3} />}
              </button>

              {/* 折叠面板内容 */}
              {isDashboardOpen && (
                <div
                  style={sketchyShape3}
                  className="pointer-events-auto mt-4 w-full bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] flex flex-col max-h-[60vh] overflow-hidden"
                >
                  <div className="p-3 border-b-4 border-ink bg-cream/80">
                    <span className="font-black text-sm tracking-widest text-ink/80">NODE STATUS</span>
                  </div>
                  
                  <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
                    {nodes.length === 0 ? (
                      <div className="text-center font-bold text-ink/40 py-4 text-sm">No nodes found</div>
                    ) : (
                      nodes.map((n, idx) => {
                        // 根据状态映射风格颜色
                        const sColor = n.data.nodeState === 'running' ? 'bg-[#3498DB] text-paper' :
                                       n.data.nodeState === 'completed' ? 'bg-[#a3be8c] text-ink' :
                                       n.data.nodeState === 'error' ? 'bg-[#bf616a] text-paper' :
                                       n.data.nodeState === 'waiting' ? 'bg-[#d08770] text-paper animate-pulse' :
                                       n.data.nodeState === 'skipped' ? 'bg-ink/20 text-ink' : 'bg-[#EBCB8B] text-ink';

                        return (
                          <div
                            key={n.id}
                            onClick={() => setLogModalNode({ id: n.id, name: String(n.data.label), state: String(n.data.nodeState) })}
                            style={idx % 2 === 0 ? sketchyShape2 : sketchyShape1}
                            className="flex items-center justify-between p-3 border-2 border-ink bg-cream hover:bg-sand cursor-pointer transition-all hover:-translate-y-[2px] shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-0 active:shadow-none"
                            title="Click to view logs"
                          >
                            <div className="flex items-center gap-2 overflow-hidden pr-2">
                              <Terminal size={14} className="shrink-0 text-ink/50" />
                              <span className="font-bold text-sm truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                                {String(n.data.label)}
                              </span>
                            </div>
                            <span className={`shrink-0 text-[10px] font-black tracking-wider border-2 border-ink px-1.5 py-0.5 ${sColor}`}>
                              {(String(n.data.nodeState) || 'READY').toUpperCase()}
                            </span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 原有 ReactFlow 画布 */}
          {selectedTaskId ? (
            <ReactFlow
              nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} nodeTypes={nodeTypes}
              nodesDraggable={true} elementsSelectable={true} zoomOnScroll={true} panOnDrag={true} fitView className="!h-full"
            >
              <Background gap={24} size={2} color="#1a1a1a" variant={'dots' as any} />
            </ReactFlow>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-ink gap-6">
               <div style={sketchyShape1} className="p-8 border-4 border-ink bg-cream shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] -rotate-3"><Activity size={60} strokeWidth={2} className="text-[#EBCB8B]" /></div>
               <p className="text-2xl font-black rotate-2 text-ink/60" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Select a task to view its flow...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}