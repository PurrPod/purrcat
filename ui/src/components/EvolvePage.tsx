// src/components/EvolvePage.tsx
import { useState, useEffect } from 'react';
import { ArrowLeft, Plus, Dna, FileEdit, TestTube, GitMerge, FileText, Play, Check, X, Server, Zap, RefreshCw, Undo2, Save, MessageSquare } from 'lucide-react';
import { toast } from 'react-hot-toast';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

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
  blockquote: ({ ...props }: any) => <blockquote className="border-l-4 border-terracotta pl-4 py-1 italic text-ink/70 my-3 bg-terracotta/5 rounded-r-lg" {...props} />,
  pre: ({ ...props }: any) => <pre className="my-4 border-4 border-ink bg-ink/5 text-ink p-4 overflow-x-auto shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] font-mono text-sm leading-relaxed font-bold" style={sketchyShape2} {...props} />,
  code: ({ className, children, ...props }: any) => {
    const isInline = props.inline !== false && !className?.includes('language-') && !String(children).includes('\n');
    return isInline ? (
      <code className="bg-ink/10 text-terracotta px-1.5 py-0.5 border-2 border-ink mx-1 font-black text-[0.9em]" style={sketchyShape3} {...props}>{children}</code>
    ) : (<code className={className} {...props}>{children}</code>);
  }
};

type EvolveType = 'skill' | 'mcp';
type ProcessStep = 'edit' | 'test' | 'merge';
type WorkPlace = { workplace_id: string; name: string; status?: string };

export default function EvolvePage({ onBack }: { onBack: () => void }) {
  const [activeType, setActiveType] = useState<EvolveType>('skill');
  const [workplaces, setWorkplaces] = useState<WorkPlace[]>([]);
  const [activeWorkplace, setActiveWorkplace] = useState<WorkPlace | null>(null);
  const [currentStep, setCurrentStep] = useState<ProcessStep>('edit');

  const [showNewModal, setShowNewModal] = useState(false);
  const [newReq, setNewReq] = useState({ type: 'create', name: '', description: '', scenario: '' });

  // Editor State
  const [files, setFiles] = useState<string[]>([]);
  const [activeFile, setActiveFile] = useState<string>('');
  const [fileContent, setFileContent] = useState('');
  
  // Test State
  const [showEvalModal, setShowEvalModal] = useState(false);
  const [evalJson, setEvalJson] = useState('');
  const [iterations, setIterations] = useState<number[]>([]);
  const [activeIteration, setActiveIteration] = useState<number | null>(null);
  const [reportMd, setReportMd] = useState('');

  // Merge State
  const [diffContent, setDiffContent] = useState('');
  const [isDiffLoading, setIsDiffLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);

  const fetchWorkplaces = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/list?type=${activeType}`);
      if (res.ok) setWorkplaces(await res.json());
      else setWorkplaces([]);
    } catch { setWorkplaces([]); }
  };

  useEffect(() => {
    setActiveWorkplace(null);
    setFiles([]); setActiveFile(''); setFileContent('');
    setIterations([]); setActiveIteration(null); setReportMd(''); setDiffContent('');
    fetchWorkplaces();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeType]);

  useEffect(() => {
    if (activeWorkplace) {
      loadFiles();
      loadIterations();
      setCurrentStep('edit');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkplace]);

  const loadFiles = async () => {
    if (!activeWorkplace) return;
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/file?workplace_id=${activeWorkplace.workplace_id}&name=${activeWorkplace.name}&type=${activeType}`);
      if (res.ok) {
        const data = await res.json();
        setFiles(data.attachments || []);
        const defaultFile = activeType === 'skill' ? 'SKILL.md' : 'server.py';
        if (data.attachments.includes(defaultFile)) setActiveFile(defaultFile);
        else if (data.attachments.length > 0) setActiveFile(data.attachments[0]);
      }
    } catch { /* noop */ }
  };

  useEffect(() => {
    if (activeFile) loadFileData(activeFile, setFileContent);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFile]);

  const loadFileData = async (filename: string, setter: (val: string) => void) => {
    if (!activeWorkplace) return;
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/file?workplace_id=${activeWorkplace.workplace_id}&name=${activeWorkplace.name}&filename=${filename}&type=${activeType}`);
      if (res.ok) setter((await res.json()).content || "");
      else setter("");
    } catch { setter("Network Error"); }
  };

  const loadIterations = async () => {
    if (!activeWorkplace) return;
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/test/iterations?workplace_id=${activeWorkplace.workplace_id}&type=${activeType}`);
      if (res.ok) {
        const iters = await res.json();
        setIterations(iters);
        if (iters.length > 0) handleSelectIteration(iters[iters.length - 1]);
        else { setActiveIteration(null); setReportMd(''); }
      }
    } catch { /* noop */ }
  };

  const handleSelectIteration = async (iter: number) => {
    if (!activeWorkplace) return;
    setActiveIteration(iter);
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/test/report?workplace_id=${activeWorkplace.workplace_id}&name=${activeWorkplace.name}&iteration=${iter}&type=${activeType}`);
      if (res.ok) setReportMd((await res.json()).report_md || '*此轮次尚未生成评测报告。*');
      else setReportMd('*获取报告失败*');
    } catch { setReportMd('*网络异常，无法获取报告*'); }
  };

  const handlePublishRequirement = async () => {
    if (!newReq.name.trim()) return toast.error("需要填写名称");
    const tid = toast.loading("正在分配并初始化物理沙盒...");
    try {
      const res = await fetch('http://localhost:8000/api/evolve/init', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: activeType, name: newReq.name.trim(), is_upgrade: newReq.type === 'upgrade' })
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message, { id: tid });
        setShowNewModal(false);
        setNewReq({ type: 'create', name: '', description: '', scenario: '' });
        fetchWorkplaces(); 
        setActiveWorkplace({ workplace_id: data.workplace_id, name: newReq.name.trim() });
      } else {
        toast.error((await res.json()).detail || "沙盒初始化失败", { id: tid });
      }
    } catch { toast.error("网络异常", { id: tid }); }
  };

  const handleSaveFile = async (filename: string, content: string) => {
    if (!activeWorkplace) return;
    const tid = toast.loading(`正在将修改落盘至沙盒的 ${filename}...`);
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/file?workplace_id=${activeWorkplace.workplace_id}&name=${activeWorkplace.name}&filename=${filename}&type=${activeType}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      if (res.ok) {
        toast.success(`[${filename}] 成功写入沙盒磁盘！`, { id: tid });
        if (filename === 'evals/evals.json') setShowEvalModal(false);
      } else toast.error("写入失败，请检查沙盒状态", { id: tid });
    } catch { toast.error("网络异常", { id: tid }); }
  };

  const handleRunTest = async () => {
    if (!activeWorkplace) return;
    const tid = toast.loading("正在唤醒 Agent 并发盲测流水线...");
    try {
      const res = await fetch('http://localhost:8000/api/evolve/test/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: activeType, workplace_id: activeWorkplace.workplace_id, name: activeWorkplace.name })
      });
      if (res.ok) toast.success("后台盲测流水线已成功启动！请随时点击刷新获取最新报告。", { id: tid });
      else toast.error("触发测试失败", { id: tid });
    } catch { toast.error("网络异常", { id: tid }); }
  };

  const handleLoadDiff = async () => {
    if (!activeWorkplace) return;
    setCurrentStep('merge');
    setIsDiffLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/diff?workplace_id=${activeWorkplace.workplace_id}&name=${activeWorkplace.name}&type=${activeType}`);
      if (res.ok) setDiffContent((await res.json()).diff_content || "文件内容没有任何改变。");
      else setDiffContent("获取差异信息失败。");
    } catch { setDiffContent("网络异常，无法获取差异。"); }
    finally { setIsDiffLoading(false); }
  };

  const handleMerge = async (approved: boolean) => {
    if (!activeWorkplace) return;
    if (!approved && !rejectReason.trim()) return toast.error("打回加工必须填写拒绝理由！");
    const tid = toast.loading(approved ? "执行强合并到主库..." : "将意见反馈至沙盒...");
    try {
      const res = await fetch('http://localhost:8000/api/evolve/handle', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: activeType, workplace_id: activeWorkplace.workplace_id, name: activeWorkplace.name, is_approved: approved, reject_reason: rejectReason.trim() })
      });
      if (res.ok) {
        toast.success((await res.json()).message || (approved ? "✅ 并入主库！" : "❎ 意见已送达"), { id: tid });
        if (approved) { setActiveWorkplace(null); fetchWorkplaces(); }
        else setRejectReason('');
      } else toast.error("操作失败", { id: tid });
    } catch { toast.error("网络异常", { id: tid }); }
  };

  const handleSendReject = () => {
    if (!rejectReason.trim()) {
      toast.error("必须填写指导意见！");
      return;
    }
    handleMerge(false);
    setShowRejectModal(false);
  };

  const handleRollback = async () => {
    if (!activeWorkplace) return;
    if (!confirm(`🚨 危险操作：确定要把主库的 ${activeWorkplace.name} 强制回滚到上一次 Git 提交版本吗？这无法撤销！`)) return;
    try {
      const res = await fetch('http://localhost:8000/api/evolve/rollback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: activeType, name: activeWorkplace.name })
      });
      if (res.ok) toast.success((await res.json()).message);
      else toast.error("回滚执行被拒");
    } catch { toast.error("网络异常"); }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 flex gap-6 overflow-hidden font-sans">
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} title="BACK" className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink" />
          </button>
          
          {/* 修改1: 将 NEW REQUIREMENT 移动到这里，变为正方形 */}
          <button onClick={() => setShowNewModal(true)} style={sketchyShape3} title="NEW REQUIREMENT" className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none rotate-3 hover:-rotate-3">
            <Plus size={28} strokeWidth={3} className="text-ink" />
          </button>

          <div style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#a3be8c] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-1">
            <Dna size={24} strokeWidth={2.5} />
            <span className="tracking-widest text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>FACTORY</span>
          </div>
        </div>

        <div className="flex gap-2 shrink-0">
          <button onClick={() => setActiveType('skill')} style={sketchyShape3} className={`flex-1 py-3 border-4 border-ink font-black tracking-widest transition-all flex items-center justify-center gap-2 ${activeType === 'skill' ? 'bg-[#d08770] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
            <Zap size={18} strokeWidth={3}/> SKILL
          </button>
          <button onClick={() => setActiveType('mcp')} style={sketchyShape2} className={`flex-1 py-3 border-4 border-ink font-black tracking-widest transition-all flex items-center justify-center gap-2 ${activeType === 'mcp' ? 'bg-[#EBCB8B] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
            <Server size={18} strokeWidth={3}/> MCP
          </button>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-4 flex flex-col gap-3 overflow-hidden -rotate-1 relative">
          <div className="flex justify-between items-center px-2 py-1 border-b-2 border-ink/20 pb-2">
            <span className="font-black text-ink/40 tracking-widest text-sm uppercase">Processing Lines</span>
            <button onClick={fetchWorkplaces} className="text-ink/40 hover:text-terracotta transition-colors"><RefreshCw size={16}/></button>
          </div>
          <div className="flex-1 overflow-y-auto flex flex-col gap-3 pr-1">
            {workplaces.map((wp, idx) => (
              <div key={wp.workplace_id} onClick={() => setActiveWorkplace(wp)} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`cursor-pointer p-4 border-4 border-ink transition-all flex flex-col gap-1 ${activeWorkplace?.workplace_id === wp.workplace_id ? 'bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream hover:bg-sand hover:-translate-y-1 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]'}`}>
                <span className="font-black text-lg truncate text-ink">{wp.name}</span>
                <span className="text-[10px] font-bold opacity-60 text-ink">ID: {wp.workplace_id}</span>
              </div>
            ))}
            {workplaces.length === 0 && <div className="text-center opacity-40 font-bold mt-10">No items processing.</div>}
          </div>
        </div>
      </div>

      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] overflow-hidden relative rotate-[0.5deg] z-10 flex flex-col">
        {activeWorkplace ? (
          <>
            {/* 修改2: 移除了测试、合并页面的多余分界线 */}
            <div className="flex bg-cream border-b-4 border-ink shrink-0 h-20">
              <button onClick={() => setCurrentStep('edit')} className={`flex-1 flex items-center justify-center gap-3 font-black tracking-widest transition-all ${currentStep === 'edit' ? 'bg-[#88c0d0] text-paper text-xl border-b-4 border-ink' : 'text-ink/40 hover:bg-sand hover:text-ink'}`}>
                <FileEdit size={24} strokeWidth={3} /> 1. FILES
              </button>
              <div className="w-1 bg-ink/20 shrink-0"></div>
              <button onClick={() => setCurrentStep('test')} className={`flex-1 flex items-center justify-center gap-3 font-black tracking-widest transition-all ${currentStep === 'test' ? 'bg-[#EBCB8B] text-ink text-xl border-b-4 border-ink' : 'text-ink/40 hover:bg-sand hover:text-ink'}`}>
                <TestTube size={24} strokeWidth={3} /> 2. EVALS
              </button>
              <div className="w-1 bg-ink/20 shrink-0"></div>
              <button onClick={() => { setCurrentStep('merge'); handleLoadDiff(); }} className={`flex-1 flex items-center justify-center gap-3 font-black tracking-widest transition-all ${currentStep === 'merge' ? 'bg-[#a3be8c] text-ink text-xl border-b-4 border-ink' : 'text-ink/40 hover:bg-sand hover:text-ink'}`}>
                <GitMerge size={24} strokeWidth={3} /> 3. MERGE
              </button>
            </div>

            <div className="flex-1 overflow-hidden relative p-6 bg-cream/30">
              {currentStep === 'edit' && (
                <div className="flex h-full gap-6 w-full max-w-7xl mx-auto">
                  <div className="w-64 shrink-0 flex flex-col gap-3 border-r-4 border-ink/20 pr-4 overflow-y-auto">
                     <span className="font-black text-ink/40 tracking-widest text-sm mb-1">SANDBOX FILES</span>
                     {files.filter(f => !f.startsWith('evals')).map((f, idx) => (
                        <button key={f} onClick={() => setActiveFile(f)} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`p-3 border-2 border-ink text-left font-bold text-sm break-all ${activeFile === f ? 'bg-[#88c0d0] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-cream text-ink hover:bg-sand'}`}>
                           <FileText size={16} className="inline mb-0.5 mr-1 opacity-70"/>{f}
                        </button>
                     ))}
                  </div>
                  <div className="flex-1 flex flex-col min-w-0 gap-4">
                    <div className="flex justify-between items-end">
                      <h2 className="text-2xl font-black text-ink tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{activeFile || 'No file selected'}</h2>
                      <button onClick={() => handleSaveFile(activeFile, fileContent)} disabled={!activeFile} style={sketchyShape3} className="px-6 py-2 bg-[#a3be8c] border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none flex items-center gap-2 disabled:opacity-50">
                        <Save size={18} strokeWidth={3}/> SAVE
                      </button>
                    </div>
                    <textarea value={fileContent} onChange={(e) => setFileContent(e.target.value)} disabled={!activeFile} className="flex-1 w-full bg-[#FDF8F0] border-4 border-ink p-6 font-mono text-sm font-bold focus:outline-none resize-none shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] disabled:opacity-50" style={sketchyShape2} spellCheck={false} />
                  </div>
                </div>
              )}

              {currentStep === 'test' && (
                <div className="flex h-full gap-6 w-full max-w-7xl mx-auto">
                  <div className="w-72 shrink-0 flex flex-col gap-3 overflow-y-auto pr-2">
                    {/* 修改3: 把配置、运行移到迭代列表右上角化身正方形图标 */}
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-black text-ink/40 tracking-widest text-sm">ARCHIVES</span>
                      <div className="flex gap-2">
                        <button onClick={() => { loadFileData('evals/evals.json', setEvalJson); setShowEvalModal(true); }} className="w-9 h-9 bg-cream border-2 border-ink flex items-center justify-center hover:bg-[#d08770] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:translate-y-[1px] active:translate-x-[1px] active:shadow-none transition-all" style={sketchyShape2} title="Edit Evals.json">
                          <FileEdit size={16} strokeWidth={2.5}/>
                        </button>
                        <button onClick={handleRunTest} className="w-9 h-9 bg-[#EBCB8B] text-ink border-2 border-ink flex items-center justify-center hover:bg-[#d8b877] shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:translate-y-[1px] active:translate-x-[1px] active:shadow-none transition-all" style={sketchyShape1} title="Run Evaluator">
                          <Play size={16} strokeWidth={3} fill="currentColor"/>
                        </button>
                        <button onClick={loadIterations} className="w-9 h-9 bg-cream border-2 border-ink flex items-center justify-center hover:bg-sand text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:translate-y-[1px] active:translate-x-[1px] active:shadow-none transition-all" style={sketchyShape3} title="Refresh Archives">
                          <RefreshCw size={16}/>
                        </button>
                      </div>
                    </div>
                    {iterations.map(iter => (
                      <button key={iter} onClick={() => handleSelectIteration(iter)} style={sketchyShape1} className={`p-4 border-4 border-ink font-black text-left transition-all ${activeIteration === iter ? 'bg-ink text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-cream hover:bg-sand shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]'}`}>
                        Iteration {iter}
                      </button>
                    ))}
                    {iterations.length === 0 && <div className="text-sm font-bold opacity-50 mt-4">No archives yet.</div>}
                  </div>
                  
                  <div style={sketchyShape1} className="flex-1 bg-[#FDF8F0] border-4 border-ink p-8 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] overflow-y-auto font-bold text-ink">
                    {reportMd ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>{reportMd}</ReactMarkdown> : <span className="opacity-40 italic">Select an iteration to view report...</span>}
                  </div>
                </div>
              )}

              {currentStep === 'merge' && (
                <div className="flex flex-col h-full gap-6 w-full max-w-6xl mx-auto">
                  {/* 修改4 & 5: 全部合并到右上角的正方形图标组 */}
                  <div className="flex justify-between items-center shrink-0">
                    <h2 className="text-3xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DIFF REVIEW</h2>
                    
                    <div className="flex gap-4">
                      <button onClick={handleLoadDiff} title="Reload Diff" className="w-12 h-12 bg-cream border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand flex items-center justify-center active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all" style={sketchyShape3}>
                        <RefreshCw size={22} strokeWidth={3} className={isDiffLoading ? "animate-spin" : ""}/>
                      </button>
                      <button onClick={handleRollback} title="Revert Main to Previous" className="w-12 h-12 bg-cream text-[#bf616a] border-4 border-[#bf616a] shadow-[4px_4px_0px_0px_#bf616a] hover:bg-[#bf616a]/10 flex items-center justify-center active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all" style={sketchyShape2}>
                        <Undo2 size={22} strokeWidth={3}/>
                      </button>
                      
                      <div className="w-1 bg-ink/20 mx-1 shrink-0 rounded-full"></div>

                      <button onClick={() => setShowRejectModal(true)} title="Reject & Request Rework" className="w-12 h-12 bg-[#bf616a] text-paper border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] flex items-center justify-center active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all" style={sketchyShape1}>
                        <X size={26} strokeWidth={4}/>
                      </button>
                      <button onClick={() => handleMerge(true)} title="Approve & Merge" className="w-12 h-12 bg-[#a3be8c] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] flex items-center justify-center active:translate-y-[2px] active:translate-x-[2px] active:shadow-none transition-all" style={sketchyShape3}>
                        <Check size={26} strokeWidth={4}/>
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 bg-[#FDF8F0] border-4 border-ink p-6 font-mono text-sm font-bold overflow-y-auto shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape1}>
                    {diffContent ? diffContent.split('\n').map((line, i) => {
                      let bg = '';
                      if (line.startsWith('+')) bg = 'bg-[#a3be8c]/20 text-[#a3be8c]';
                      if (line.startsWith('-')) bg = 'bg-[#bf616a]/20 text-[#bf616a]';
                      return <div key={i} className={`px-2 py-0.5 rounded ${bg}`}>{line || '\u00A0'}</div>;
                    }) : <span className="opacity-40">Click Reload Diff to fetch...</span>}
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-6 opacity-40">
            <Dna size={80} strokeWidth={1.5} className="text-ink" />
            <p className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Select a process to start.</p>
          </div>
        )}
      </div>

      {showNewModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-lg">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-terracotta" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW REQUIREMENT</h3>
              <button onClick={() => setShowNewModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="flex flex-col gap-4 -rotate-1">
              <div className="flex gap-4">
                <button onClick={() => setNewReq({...newReq, type: 'create'})} style={sketchyShape1} className={`flex-1 py-3 border-4 border-ink font-black ${newReq.type === 'create' ? 'bg-[#EBCB8B] shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]' : 'bg-cream text-ink/50'}`}>CREATE NEW</button>
                <button onClick={() => setNewReq({...newReq, type: 'upgrade'})} style={sketchyShape3} className={`flex-1 py-3 border-4 border-ink font-black ${newReq.type === 'upgrade' ? 'bg-[#88c0d0] text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]' : 'bg-cream text-ink/50'}`}>UPGRADE EXIST</button>
              </div>
              <div className="flex flex-col gap-2">
                <label className="font-bold opacity-70 text-sm">{activeType === 'skill' ? 'Skill Name' : 'MCP Name'} (Directory Level):</label>
                <input value={newReq.name} onChange={e=>setNewReq({...newReq, name: e.target.value})} placeholder={`e.g. ${activeType === 'skill' ? 'excel_parser' : 'my_mcp_server'}`} className="w-full bg-[#FDF8F0] border-4 border-ink p-3 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape2}/>
              </div>
              <div className="flex flex-col gap-2">
                 <label className="font-bold opacity-70 text-sm">Description (What does it do?):</label>
                 <textarea value={newReq.description} onChange={e=>setNewReq({...newReq, description: e.target.value})} placeholder="I want a module that can..." className="w-full h-20 resize-none bg-[#FDF8F0] border-4 border-ink p-3 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape1}/>
              </div>
              <div className="flex flex-col gap-2">
                 <label className="font-bold opacity-70 text-sm">Scenarios (When to trigger?):</label>
                 <textarea value={newReq.scenario} onChange={e=>setNewReq({...newReq, scenario: e.target.value})} placeholder="Trigger this whenever the user says..." className="w-full h-20 resize-none bg-[#FDF8F0] border-4 border-ink p-3 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3}/>
              </div>
            </div>
            <button onClick={handlePublishRequirement} style={sketchyShape1} className="w-full py-4 bg-terracotta text-paper border-4 border-ink font-black text-xl tracking-widest shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:bg-[#c4684b] active:translate-y-1 active:shadow-none rotate-1 mt-2">
              BUILD SANDBOX
            </button>
          </div>
        </div>
      )}

      {/* 修改6: 打回重做专属涂鸦弹窗 */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-lg">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>FEEDBACK & REWORK</h3>
              <button onClick={() => setShowRejectModal(false)} className="hover:text-[#bf616a] hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="flex flex-col gap-2 -rotate-1">
              <label className="font-bold opacity-70 text-sm">指导意见：</label>
              <textarea 
                value={rejectReason} 
                onChange={e => setRejectReason(e.target.value)} 
                placeholder="如果不满意，请在这里写下指导意见，发回给 Agent 重做..." 
                className="w-full h-32 resize-none bg-[#FDF8F0] border-4 border-ink p-4 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" 
                style={sketchyShape3} 
              />
            </div>
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowRejectModal(false)} style={sketchyShape1} className="flex-1 py-3 bg-cream text-ink border-4 border-ink font-black text-lg tracking-widest shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand active:translate-y-1 active:shadow-none">
                CANCEL
              </button>
              <button onClick={handleSendReject} style={sketchyShape3} className="flex-[1.5] py-3 bg-[#bf616a] text-paper border-4 border-ink font-black text-lg tracking-widest shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-1 active:shadow-none flex items-center justify-center gap-2">
                <MessageSquare size={20}/> SEND FEEDBACK
              </button>
            </div>
          </div>
        </div>
      )}

      {showEvalModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape1} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 w-full max-w-4xl h-[85vh]">
            <div className="flex justify-between items-center rotate-1 border-b-4 border-ink/20 pb-4 shrink-0">
              <h3 className="text-3xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>evals.json</h3>
              <button onClick={() => setShowEvalModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={32} strokeWidth={3}/></button>
            </div>
            <textarea value={evalJson} onChange={e => setEvalJson(e.target.value)} className="flex-1 w-full border-4 border-ink bg-[#FDF8F0] p-6 font-mono text-sm font-bold focus:outline-none resize-none rotate-1 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape2} spellCheck={false} />
            <div className="shrink-0 flex justify-end gap-4 pt-2 rotate-1">
              <button onClick={() => setShowEvalModal(false)} style={sketchyShape3} className="px-8 bg-cream text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all">CANCEL</button>
              <button onClick={() => handleSaveFile('evals/evals.json', evalJson)} style={sketchyShape1} className="px-10 bg-[#EBCB8B] text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center gap-2 hover:bg-[#d8b877] transition-all">
                <Save size={24} strokeWidth={3}/> SAVE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}