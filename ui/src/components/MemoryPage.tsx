import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, Brain, Database, List, Network, Clock, Quote, Search, Loader2, RefreshCw } from 'lucide-react';
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

export default function MemoryPage({ onBack }: { onBack: () => void }) {
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
  
  const [events, setEvents] = useState<any[]>([]);
  const [experiences, setExperiences] = useState<any[]>([]);
  const [graphData, setGraphData] = useState<{nodes: any[], edges: any[]}>({ nodes: [], edges: [] });
  
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [isGraphLoading, setIsGraphLoading] = useState(false);

  const graphRef = useRef<HTMLDivElement>(null);
  const networkInstance = useRef<VisNetwork | null>(null);

  useEffect(() => {
    fetch('http://localhost:8000/api/memory/events').then(res => res.json()).then(setEvents);
    fetch('http://localhost:8000/api/memory/experiences').then(res => res.json()).then(setExperiences);
    
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
    } catch (e) {
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
    } catch (e) {
      toast.error("检索失败");
    } finally {
      setIsSearching(false);
    }
  };

  useEffect(() => {
    if (viewMode === 'graph' && graphRef.current && graphData.nodes.length > 0) {
      if (networkInstance.current) {
        networkInstance.current.destroy();
      }

      const data = {
        nodes: new DataSet(graphData.nodes),
        edges: new DataSet(graphData.edges)
      };

      const options = {
        nodes: {
          shape: 'box',
          margin: 16,
          borderWidth: 4,
          color: {
            border: '#1A1A1A',
            background: '#FAF8F5',
            highlight: { border: '#D47A5A', background: '#FDF8F0' }
          },
          font: { face: '"Comic Sans MS", cursive', size: 18, bold: true, color: '#1A1A1A' },
          shadow: { enabled: true, color: '#1A1A1A', size: 0, x: 6, y: 6 }
        },
        edges: {
          width: 3,
          color: { color: '#1A1A1A', highlight: '#D47A5A' },
          font: { face: '"Comic Sans MS", cursive', size: 14, strokeWidth: 4, strokeColor: '#FAF8F5', color: '#1A1A1A' },
          smooth: { type: 'cubicBezier', roundness: 0.4 },
          arrows: { to: { enabled: true, scaleFactor: 1, type: 'arrow' } }
        },
        physics: {
          forceAtlas2Based: { gravitationalConstant: -140, centralGravity: 0.015, springLength: 160, springConstant: 0.08, damping: 0.4 },
          solver: 'forceAtlas2Based',
          stabilization: { enabled: true, iterations: 150 }
        }
      };

      networkInstance.current = new VisNetwork(graphRef.current, data, options);
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
          </div>
        </div>
      </div>

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
              title="拉取底层数据库全量图谱"
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
                <div key={exp.exp_id} style={i % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`bg-paper border-4 border-ink p-6 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 transition-all ${i % 3 === 0 ? 'rotate-1' : '-rotate-1'}`}>
                  <Quote size={20} className="text-[#3498DB] mb-2" strokeWidth={3} />
                  <p className="font-bold text-ink text-lg leading-relaxed">{exp.content}</p>
                  <div className="mt-4 pt-3 border-t-4 border-ink/10 border-dashed flex items-center gap-2 text-xs font-bold text-ink/50">
                    <Clock size={14} /> {exp.timestamp ? exp.timestamp.split('T')[0] : 'Unknown'}
                  </div>
                </div>
              ))}
            </div>
          )}

          {viewMode === 'events' && (
            <div className="p-10 flex flex-col gap-6 max-w-4xl mx-auto">
              {events.map((evt, i) => (
                <div key={evt.event_id || i} style={sketchyShape1} className={`flex items-start gap-6 bg-cream border-4 border-ink p-6 shadow-[6px_6px_0px_0px_rgba(212,122,90,0.4)] ${i % 2 === 0 ? '-rotate-1' : 'rotate-1'}`}>
                  <div className="shrink-0 bg-terracotta text-paper px-3 py-1 font-black text-sm border-2 border-ink -rotate-3" style={sketchyShape2}>
                    {evt.timestamp ? evt.timestamp.split('T')[0] : 'Fact'}
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