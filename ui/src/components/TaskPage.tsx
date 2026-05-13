import React, { useState, useEffect, useMemo } from 'react';
import { 
  ArrowLeft, Terminal, Trash2, X, Activity, Clock, Box
} from 'lucide-react';
import { ReactFlow, Background, useNodesState, useEdgesState, Handle, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css'; // 🔴 修复1：必须引入 React Flow 的核心样式
import { toast } from 'react-hot-toast';

// --- 风格常量 (完全同步 ChatPage) ---
const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

interface Task {
  id: string;
  name: string;
  graph_name?: string; // 🔴 接收真实的图谱文件名
  expert_type?: string;
  state: 'running' | 'completed' | 'failed' | 'idle';
  step: number;
  create_time: string;
}

// 🟢 自定义任务节点 (带查看日志按钮)
const TaskMonitorNode = ({ id, data }: any) => {
  return (
    <div 
      style={data.shape} 
      className={`bg-paper border-4 border-ink p-4 min-w-[200px] transition-transform duration-200 hover:-translate-y-1 
        ${data.isRunning ? 'shadow-[8px_8px_0px_0px_rgba(212,122,90,1)] border-terracotta' : 'shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}
    >
      <div className="flex items-center gap-3 mb-3 border-b-2 border-ink/10 pb-2">
        <div className={`w-4 h-4 border-2 border-ink -rotate-3 ${data.isRunning ? 'bg-terracotta animate-pulse' : 'bg-[#EBCB8B]'}`}></div>
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

      {/* 隐形 Handle 用于连线 */}
      <Handle type="target" position={Position.Left} className="!bg-ink !w-3 !h-3 !-left-[18px] !border-2 !border-paper" />
      <Handle type="source" position={Position.Right} className="!bg-ink !w-3 !h-3 !-right-[18px] !border-2 !border-paper" />
    </div>
  );
};

export default function TaskPage({ onBack }: { onBack: () => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string>('');
  
  // 弹窗状态
  const [taskToDelete, setTaskToDelete] = useState<string | null>(null);
  const [logModalNodeId, setLogModalNodeId] = useState<string | null>(null);

  // React Flow 状态
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // 注册自定义节点
  const nodeTypes = useMemo(() => ({ custom: TaskMonitorNode }), []);

  // 1. 获取任务列表
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

  // 2. 选择任务：加载图谱定义和日志
  const handleSelectTask = async (task: Task) => {
    setSelectedTaskId(task.id);
    setNodes([]); // 切换任务时先清空画板
    setEdges([]);
    
    try {
      // 🔴 修复：使用后端传来的真实图谱文件名去请求 (兜底使用 default)
      const targetGraph = task.graph_name || 'default';
      const gRes = await fetch(`http://localhost:8000/api/graphs/${targetGraph}`);

      if (gRes.ok) {
        const graph = await gRes.json();
        
        // 解析节点并绑定 onShowLog 回调
        const flowNodes = graph.nodes.map((n: any, idx: number) => ({
          id: n.id,
          type: 'custom',
          position: { x: 100 + (idx % 3) * 280, y: 100 + Math.floor(idx / 3) * 180 },
          data: { 
            label: n.data?.name || n.id,
            shape: idx % 2 === 0 ? sketchyShape1 : sketchyShape2,
            isRunning: task.state === 'running',
            onShowLog: (nodeId: string) => setLogModalNodeId(nodeId) // 点击触发弹窗
          }
        }));
        
        const flowEdges = graph.edges.map((e: any) => ({
          id: `e-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          animated: task.state === 'running',
          style: { strokeWidth: 3, stroke: task.state === 'running' ? '#D47A5A' : '#1a1a1a' }
        }));
        
        setNodes(flowNodes);
        setEdges(flowEdges);
      } else {
        toast.error(`无法找到架构文件: ${targetGraph}`);
      }
    } catch (e) {
      toast.error(`加载图谱失败`);
    }

    // 获取完整日志缓存到内存
    loadLogs(task.id);
  };

  const loadLogs = async (tid: string) => {
    const lRes = await fetch(`http://localhost:8000/api/tasks/${tid}/log`);
    if (lRes.ok) {
      const data = await lRes.json();
      setLogs(data.log);
    }
  };

  // 3. 删除任务逻辑 (物理删除后端)
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

  // 提取选中节点的专属日志
  const filteredLogs = logModalNodeId 
    ? logs.split('\n').filter(line => line.includes(logModalNodeId)).join('\n')
    : '';

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">
      
      {/* 🔴 悬浮日志弹窗 (手绘风格) */}
      {logModalNodeId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/50 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-5xl h-[80vh] flex flex-col relative rotate-[0.5deg]">
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
            
            <div className="flex-1 overflow-y-auto p-8 bg-ink/5 font-mono text-[14px] text-ink whitespace-pre-wrap leading-relaxed shadow-[inset_0px_4px_10px_rgba(0,0,0,0.05)]">
               {filteredLogs || (
                 <div className="flex flex-col items-center justify-center h-full opacity-40 gap-4">
                   <Box size={64} strokeWidth={1.5} />
                   <p className="text-xl font-bold font-sans">No execution logs found for this node yet.</p>
                 </div>
               )}
            </div>
          </div>
        </div>
      )}

      {/* 🔴 删除确认弹窗 */}
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

      {/* --- 左侧导航与任务列表 (与 ChatPage 对齐) --- */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
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

                  {/* 删除按钮 */}
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

      {/* --- 右侧全屏图谱视图 --- */}
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
              onNodesChange={onNodesChange} // 🔴 修复1：强绑定 Change 方法
              onEdgesChange={onEdgesChange} // 🔴 修复1：强绑定 Change 方法
              nodeTypes={nodeTypes}
              nodesDraggable={true}
              zoomOnScroll={true}
              panOnDrag={true}
              fitView
              className="!h-full"
            >
              <Background gap={24} size={2} color="#1a1a1a" opacity={0.1} variant="dots" />
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