import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, Brain, Database, List, Network, Clock, Quote, Search, Loader2, RefreshCw, Trash2, X, FileText, Save } from 'lucide-react';
import { Network as VisNetwork } from 'vis-network';
import { DataSet } from 'vis-data';
import { toast } from 'react-hot-toast';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

const MarkdownComponents: any = {
  h2: ({ ...props }: any) => <h2 className="text-2xl font-black mb-4 mt-6 border-b-4 border-ink inline-block pb-1 text-terracotta" {...props} />,
  ul: ({ ...props }: any) => <ul className="list-disc pl-6 mb-4 space-y-3 font-bold marker:text-ink text-lg" {...props} />,
  li: ({ ...props }: any) => <li className="pl-1 leading-relaxed" {...props} />,
  p: ({ ...props }: any) => <p className="mb-4 text-lg font-bold" {...props} />,
};

type ViewMode = 'events' | 'experiences' | 'graph' | 'search';
type DeleteTarget = { type: 'event' | 'experience' | 'relation'; id?: string; source?: string; target?: string; text?: string } | null;

export default function MemoryPage({ onBack }: { onBack: () => void }) {
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
  
  const [events, setEvents] = useState<any[]>([]);
  const [experiences, setExperiences] = useState<any[]>([]);
  const [graphData, setGraphData] = useState<{nodes: any[], edges: any[]}>({ nodes: [], edges: [] });
  
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isGraphLoading, setIsGraphLoading] = useState(false);

  // 🌟 删除状态
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);

  // 🌟 MEMORY.md 相关的编辑器状态
  const [showMdModal, setShowMdModal] = useState(false);
  const [mdContent, setMdContent] = useState('');
  const [isSavingMd, setIsSavingMd] = useState(false);

  // 打开并异步读取 Markdown 文件
  const openMdEditor = async () => {
    setMdContent('Loading...');
    setShowMdModal(true);
    try {
      const res = await fetch('http://localhost:8000/api/memory/markdown');
      if (res.ok) {
        const data = await res.json();
        setMdContent(data.content);
      } else {
        toast.error('读取 MEMORY.md 失败');
        setMdContent('');
      }
    } catch {
      toast.error('网络错误，无法读取记忆文件');
      setMdContent('');
    }
  };

  // 保存修改并落盘
  const saveMdContent = async () => {
    setIsSavingMd(true);
    try {
      const res = await fetch('http://localhost:8000/api/memory/markdown', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: mdContent })
      });
      if (res.ok) {
        toast.success('[MEMORY.md] 笔记已成功落盘保存！');
        setShowMdModal(false);
      } else {
        toast.error('保存文件失败');
      }
    } catch {
      toast.error('网络异常，保存失败');
    } finally {
      setIsSavingMd(false);
    }
  };

  const graphRef = useRef<HTMLDivElement>(null);
  const networkInstance = useRef<VisNetwork | null>(null);

  const fetchEvents = () => fetch('http://localhost:8000/api/memory/events').then(res => res.json()).then(setEvents);
  const fetchExperiences = () => fetch('http://localhost:8000/api/memory/experiences').then(res => res.json()).then(setExperiences);

  useEffect(() => {
    fetchEvents();
    fetchExperiences();
    fetchGraphData(true);
  }, []);

  const fetchGraphData = async (isQuiet = false) => {
    setIsGraphLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/memory/graph');
      if (res.ok) {
        const data = await res.json();
        setGraphData(data);
        if (!isQuiet) toast.success(`全量刷新成功！共加载 ${data.nodes.length} 个节点`);
      }
    } catch {
      toast.error("全量加载图谱失败");
    } finally {
      setIsGraphLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    try {
      const res = await fetch(`http://localhost:8000/api/memory/search?q=${encodeURIComponent(searchQuery)}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResult(data.result);
      }
    } catch {
      toast.error("检索失败");
    } finally {
      setIsSearching(false);
    }
  };

  // 🌟 处理实际的删除请求
  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      let res;
      if (deleteTarget.type === 'event') {
        res = await fetch(`http://localhost:8000/api/memory/events/${deleteTarget.id}`, { method: 'DELETE' });
      } else if (deleteTarget.type === 'experience') {
        res = await fetch(`http://localhost:8000/api/memory/experiences/${deleteTarget.id}`, { method: 'DELETE' });
      } else if (deleteTarget.type === 'relation') {
        res = await fetch(`http://localhost:8000/api/memory/graph/relation?source_node_id=${deleteTarget.source}&target_node_id=${deleteTarget.target}`, { method: 'DELETE' });
      }

      if (res?.ok) {
        toast.success("记忆已被永久擦除！");
        if (deleteTarget.type === 'event') fetchEvents();
        if (deleteTarget.type === 'experience') fetchExperiences();
        if (deleteTarget.type === 'relation') fetchGraphData(true);
      } else {
        toast.error("删除失败");
      }
    } catch {
      toast.error("网络异常，删除失败");
    } finally {
      setDeleteTarget(null);
    }
  };

  useEffect(() => {
    if (viewMode === 'graph' && graphRef.current && graphData.nodes.length > 0) {
      if (networkInstance.current) {
        networkInstance.current.destroy();
      }

      // 为了能在点击事件中识别 source 和 target，将 edge 的 id 强制设为 "source___target"
      const mappedEdges = graphData.edges.map(e => ({
        ...e,
        id: `${e.from}___${e.to}`
      }));

      const data = {
        nodes: new DataSet(graphData.nodes),
        edges: new DataSet(mappedEdges)
      };

      const options = {
        nodes: {
          shape: 'box',
          margin: { top: 16, right: 16, bottom: 16, left: 16 },
          borderWidth: 4,
          color: { border: '#1A1A1A', background: '#FAF8F5', highlight: { border: '#D47A5A', background: '#FDF8F0' } },
          font: { face: '"Comic Sans MS", cursive', size: 18, bold: 'bold', color: '#1A1A1A' },
          shadow: { enabled: true, color: '#1A1A1A', size: 0, x: 6, y: 6 }
        },
        edges: {
          width: 3,
          color: { color: '#1A1A1A', highlight: '#D47A5A' },
          font: { face: '"Comic Sans MS", cursive', size: 14, strokeWidth: 4, strokeColor: '#FAF8F5', color: '#1A1A1A', background: 'none' },
          smooth: { enabled: true, type: 'cubicBezier', roundness: 0.4 },
          arrows: { to: { enabled: true, scaleFactor: 1, type: 'arrow' } },
          interaction: { hover: true }
        },
        physics: {
          forceAtlas2Based: { gravitationalConstant: -140, centralGravity: 0.015, springLength: 160, springConstant: 0.08, damping: 0.4 },
          solver: 'forceAtlas2Based',
          stabilization: { enabled: true, iterations: 150 }
        },
        interaction: { hover: true, selectConnectedEdges: false }
      };

      networkInstance.current = new VisNetwork(graphRef.current, data, options);

      // 🌟 监听连线点击事件，触发删除确认
      networkInstance.current.on("selectEdge", function (params) {
        if (params.nodes.length === 0 && params.edges.length === 1) {
          const edgeId = params.edges[0] as string;
          const [source, target] = edgeId.split('___');
          const edgeInfo = graphData.edges.find(e => e.from === source && e.to === target);
          
          setDeleteTarget({
            type: 'relation',
            source,
            target,
            text: `[${graphData.nodes.find(n => n.id === source)?.label}] —(${edgeInfo?.label})—> [${graphData.nodes.find(n => n.id === target)?.label}]`
          });
        }
      });
    }

    return () => {
      if (networkInstance.current) {
        networkInstance.current.destroy();
        networkInstance.current = null;
      }
    };
  }, [viewMode, graphData]);

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">
      
      {/* 🌟 统一记忆删除确认弹窗 */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>FORGET THIS?</h3>
              <button onClick={() => setDeleteTarget(null)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <div className="rotate-1">
              <p className="font-bold text-ink/70 mb-3 text-sm">此段记忆将被永久抹除，确定继续吗？</p>
              <div className="bg-cream border-2 border-ink border-dashed p-4 font-bold text-ink shadow-[inset_2px_2px_0px_rgba(0,0,0,0.05)] break-words max-h-40 overflow-y-auto" style={sketchyShape1}>
                {deleteTarget.text}
              </div>
            </div>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setDeleteTarget(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">KEEP</button>
              <button onClick={confirmDelete} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">FORGET</button>
            </div>
          </div>
        </div>
      )}

      {/* MEMORY.md 手绘风大型水平编辑弹窗 */}
      {showMdModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-5xl h-[85vh]">
            
            {/* 弹窗头部 */}
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/20 pb-4 shrink-0">
              <div className="flex items-center gap-3">
                <FileText size={32} className="text-terracotta" strokeWidth={2.5} />
                <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  MEMORY.md
                </h3>
              </div>
              <button onClick={() => setShowMdModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={32} strokeWidth={3}/>
              </button>
            </div>
            
            {/* 水平宽敞的高级文本输入区 */}
            <div className="flex-1 -rotate-1 overflow-hidden flex flex-col w-full">
              <textarea 
                value={mdContent} 
                onChange={e => setMdContent(e.target.value)} 
                className="w-full h-full border-4 border-ink bg-[#FDF8F0] p-6 font-mono text-base leading-relaxed font-bold focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] resize-none" 
                style={sketchyShape3} 
                spellCheck={false}
                placeholder="在此处以 Markdown 格式沉淀或修改你的原始记忆笔记..."
              />
            </div>
            
            {/* 底部功能组合键 */}
            <div className="shrink-0 flex justify-end gap-4 -rotate-1 pt-2">
              <button onClick={() => setShowMdModal(false)} style={sketchyShape3} className="px-8 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">
                CANCEL
              </button>
              <button onClick={saveMdContent} disabled={isSavingMd} style={sketchyShape1} className="px-10 bg-[#a3be8c] text-ink font-black py-3 border-4 border-ink hover:bg-[#8eb072] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 flex items-center gap-2">
                {isSavingMd ? <Loader2 className="animate-spin" size={24} strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>} 
                SAVE TO DISK
              </button>
            </div>

          </div>
        </div>
      )}

      {/* 左侧导航 */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:shadow-none -rotate-3 hover:rotate-0">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink" />
          </button>
          <div style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#a3be8c] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2">
            <Brain size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEMORY DB</span>
          </div>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="flex-1 flex flex-col gap-4 mt-4">
            <button onClick={() => setViewMode('search')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${viewMode === 'search' ? 'bg-[#bf616a] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Search size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SEARCH</div>
                <div className="text-xs font-bold opacity-70">Hybrid Retrieval</div>
              </div>
            </button>

            <button onClick={() => setViewMode('graph')} style={sketchyShape2} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${viewMode === 'graph' ? 'bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream hover:bg-sand'}`}>
              <Network size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>COGNITION</div>
                <div className="text-xs font-bold opacity-70">Knowledge Graph</div>
              </div>
            </button>

            <button onClick={() => setViewMode('experiences')} style={sketchyShape3} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${viewMode === 'experiences' ? 'bg-[#3498DB]/80 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream hover:bg-sand'}`}>
              <Database size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EXPERIENCES</div>
                <div className="text-xs font-bold opacity-70">Vector Memory (Top 30)</div>
              </div>
            </button>

            <button onClick={() => setViewMode('events')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${viewMode === 'events' ? 'bg-terracotta text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream hover:bg-sand'}`}>
              <List size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EVENTS</div>
                <div className="text-xs font-bold opacity-70">Objective Facts (Top 30)</div>
              </div>
            </button>

            {/* MEMORY.MD 纯文本修改入口 */}
            <button onClick={openMdEditor} style={sketchyShape2} className="p-4 border-4 border-ink text-left transition-all flex items-center gap-4 bg-[#b48ead]/30 text-ink hover:bg-[#b48ead]/60 hover:-translate-y-1 hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]">
              <FileText size={28} strokeWidth={2.5} className="text-[#8f6a88]"/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEMORY.MD</div>
                <div className="text-xs font-bold opacity-70">Raw Memory Notes</div>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* 右侧面板主体 */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] overflow-hidden relative rotate-[0.5deg] z-10 flex flex-col">
        
        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0 border-b-4 border-ink/10 relative z-20 bg-paper">
          <div className="flex items-center gap-4">
            <div style={sketchyShape2} className="w-12 h-12 bg-ink border-4 border-ink flex items-center justify-center rotate-6">
              {viewMode === 'search' ? <Search className="text-[#bf616a]" strokeWidth={2.5} /> : 
               viewMode === 'graph' ? <Network className="text-[#EBCB8B]" strokeWidth={2.5} /> : 
               viewMode === 'experiences' ? <Database className="text-[#3498DB]" strokeWidth={2.5}/> : <List className="text-terracotta" strokeWidth={2.5}/>}
            </div>
            <h2 className="text-3xl font-black tracking-widest text-ink uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              {viewMode === 'search' ? 'HYBRID SEARCH' : 
               viewMode === 'graph' ? 'KNOWLEDGE GRAPH' : 
               viewMode === 'experiences' ? 'VECTOR EXPERIENCES' : 'OBJECTIVE EVENTS'}
            </h2>
          </div>

          {viewMode === 'graph' && (
            <button
              onClick={() => fetchGraphData(false)}
              disabled={isGraphLoading}
              style={sketchyShape2}
              className="flex items-center gap-2 px-5 py-2.5 bg-[#EBCB8B] text-ink border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all rotate-2 disabled:opacity-50"
            >
              <RefreshCw size={20} strokeWidth={3} className={isGraphLoading ? "animate-spin text-terracotta" : "text-ink"} />
              <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>REFRESH</span>
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto w-full h-full relative bg-cream/30">
          
          {viewMode === 'search' && (
            <div className="p-10 flex flex-col h-full max-w-4xl mx-auto">
              <div className="flex gap-4 shrink-0 mb-8">
                <input
                  style={sketchyShape2} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()} placeholder="Ask your memory anything..."
                  className="flex-1 bg-paper border-4 border-ink p-4 text-xl font-bold focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]"
                />
                <button onClick={handleSearch} disabled={isSearching || !searchQuery.trim()} style={sketchyShape1} className="bg-ink text-paper px-8 font-black flex items-center gap-3 border-4 border-ink hover:bg-terracotta hover:text-ink shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] rotate-2">
                  {isSearching ? <Loader2 size={28} className="animate-spin" /> : <Search size={28} strokeWidth={3} />}
                </button>
              </div>
              <div className="flex-1 overflow-y-auto pr-4">
                {searchResult ? (
                  <div style={sketchyShape3} className="bg-paper border-4 border-ink p-8 shadow-[8px_8px_0px_0px_rgba(26,26,26,1)]">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{searchResult}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-48 opacity-40 gap-4 rotate-2">
                    <Search size={64} strokeWidth={1.5} />
                    <p className="text-2xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Hit Enter to search the void...</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {viewMode === 'graph' && (
            <>
              <div className="absolute top-4 left-6 z-20 pointer-events-none bg-paper border-2 border-ink/30 px-3 py-1 font-bold text-ink/50 text-sm" style={sketchyShape2}>
                Tip: Click any edge (line) to forget a relationship.
              </div>
              {isGraphLoading && (
                <div className="absolute inset-0 bg-paper/60 backdrop-blur-sm z-50 flex items-center justify-center gap-3">
                  <Loader2 size={32} className="animate-spin text-terracotta" strokeWidth={3} />
                  <span className="font-black text-xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Syncing All Triples...</span>
                </div>
              )}
              {graphData.nodes.length === 0 && !isGraphLoading ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center opacity-40 gap-4">
                  <Network size={64} />
                  <p className="text-xl font-bold">Graph is empty. Try clicking REFRESH.</p>
                </div>
              ) : (
                <div ref={graphRef} className="absolute inset-0 outline-none"></div>
              )}
            </>
          )}

          {viewMode === 'experiences' && (
            <div className="p-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {experiences.map((exp, i) => (
                <div key={exp.exp_id} style={i % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`group relative bg-paper border-4 border-ink p-6 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 transition-all ${i % 3 === 0 ? 'rotate-1' : '-rotate-1'}`}>
                  
                  {/* 🌟 悬浮显示删除按钮 */}
                  <button 
                    onClick={() => setDeleteTarget({ type: 'experience', id: exp.exp_id, text: exp.content })}
                    className="absolute -top-3 -right-3 bg-[#bf616a] text-paper border-2 border-ink p-2 opacity-0 group-hover:opacity-100 transition-all hover:scale-110 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] z-20 cursor-pointer" 
                    style={{ borderRadius: '50% 10% 50% 10%' }}
                    title="Forget Experience"
                  >
                    <Trash2 size={16} strokeWidth={2.5}/>
                  </button>

                  <Quote size={20} className="text-[#3498DB] mb-2" strokeWidth={3} />
                  <p className="font-bold text-ink text-lg leading-relaxed">{exp.content}</p>
                  <div className="mt-4 pt-3 border-t-4 border-ink/10 border-dashed flex items-center gap-2 text-xs font-bold text-ink/50">
                    <Clock size={14} /> {exp.timestamp ? exp.timestamp.replace('T', ' ').substring(0, 16) : 'Unknown'}
                  </div>
                </div>
              ))}
            </div>
          )}

          {viewMode === 'events' && (
            <div className="p-10 flex flex-col gap-6 max-w-4xl mx-auto">
              {events.map((evt, i) => (
                <div key={evt.event_id || i} style={sketchyShape1} className={`group relative flex items-start gap-6 bg-cream border-4 border-ink p-6 shadow-[6px_6px_0px_0px_rgba(212,122,90,0.4)] ${i % 2 === 0 ? '-rotate-1' : 'rotate-1'}`}>
                  
                  {/* 🌟 悬浮显示删除按钮 */}
                  <button 
                    onClick={() => setDeleteTarget({ type: 'event', id: evt.event_id, text: evt.content })}
                    className="absolute -top-3 -right-3 bg-[#bf616a] text-paper border-2 border-ink p-2 opacity-0 group-hover:opacity-100 transition-all hover:scale-110 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] z-20 cursor-pointer" 
                    style={{ borderRadius: '50% 10% 50% 10%' }}
                    title="Forget Event"
                  >
                    <Trash2 size={16} strokeWidth={2.5}/>
                  </button>

                  <div className="shrink-0 bg-terracotta text-paper px-3 py-1 font-black text-sm border-2 border-ink -rotate-3" style={sketchyShape2}>
                    {evt.timestamp ? evt.timestamp.replace('T', ' ').substring(0, 16) : 'Fact'}
                  </div>
                  <div className="font-bold text-ink text-lg pt-1">{evt.content}</div>
                </div>
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}