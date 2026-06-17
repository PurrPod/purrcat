// src/components/EvolvePage.tsx
import { useState, useEffect } from 'react';
import { ArrowLeft, Plus, Dna, FileEdit, TestTube, GitMerge, FileText, Play, Check, X, Server, Zap, ChevronRight, AlertCircle, Save, MessageSquare, RefreshCw, Undo2 } from 'lucide-react';
import { toast } from 'react-hot-toast';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

type EvolveType = 'skill' | 'mcp';
type ProcessStep = 'edit' | 'test' | 'merge';
type WorkPlace = { workplace_id: string; skill_name: string; status?: string };

export default function EvolvePage({ onBack }: { onBack: () => void }) {
  const [activeType, setActiveType] = useState<EvolveType>('skill');
  const [workplaces, setWorkplaces] = useState<WorkPlace[]>([]);
  const [activeWorkplace, setActiveWorkplace] = useState<WorkPlace | null>(null);
  const [currentStep, setCurrentStep] = useState<ProcessStep>('edit');

  // New Requirement Modal
  const [showNewModal, setShowNewModal] = useState(false);
  const [newReq, setNewReq] = useState({ type: 'create', name: '', description: '', scenario: '' });

  // Editor State
  const [skillMd, setSkillMd] = useState('');
  const [attachments, setAttachments] = useState<string[]>([]);
  
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

  // ==========================================
  // 🚀 真实的 API 调用逻辑
  // ==========================================
  
  // 1. 获取加工列表
  const fetchWorkplaces = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/evolve/list');
      if (res.ok) setWorkplaces(await res.json());
      else setWorkplaces([]);
    } catch {
      setWorkplaces([]);
    }
  };

  useEffect(() => { fetchWorkplaces(); }, []);

  // 当选择不同沙盒时，加载全部数据
  useEffect(() => {
    if (activeWorkplace) {
      loadFileData('SKILL.md', setSkillMd);
      loadAttachments();
      loadIterations();
    }
  }, [activeWorkplace]);

  // 2. 读取沙盒文件
  const loadFileData = async (filename: string, setter: (val: string) => void) => {
    if (!activeWorkplace) return;
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/file?workplace_id=${activeWorkplace.workplace_id}&skill_name=${activeWorkplace.skill_name}&filename=${filename}`);
      if (res.ok) {
        const data = await res.json();
        setter(data.content || "");
      } else {
        setter("");
      }
    } catch { setter("Network Error"); }
  };

  // 3. 读取沙盒附件列表
  const loadAttachments = async () => {
    if (!activeWorkplace) return;
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/file?workplace_id=${activeWorkplace.workplace_id}&skill_name=${activeWorkplace.skill_name}`);
      if (res.ok) {
        const data = await res.json();
        setAttachments(data.attachments || []);
      } else {
        setAttachments([]);
      }
    } catch { setAttachments([]); }
  };

  // 4. 读取迭代轮次
  const loadIterations = async () => {
    if (!activeWorkplace) return;
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/test/iterations?workplace_id=${activeWorkplace.workplace_id}`);
      if (res.ok) {
        const iters = await res.json();
        setIterations(iters);
        if (iters.length > 0) {
          handleSelectIteration(iters[iters.length - 1]); // 自动选择最新的一轮
        } else {
          setActiveIteration(null);
          setReportMd('');
        }
      }
    } catch {}
  };

  // 5. 拉取选定轮次的测试报告
  const handleSelectIteration = async (iter: number) => {
    if (!activeWorkplace) return;
    setActiveIteration(iter);
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/test/report?workplace_id=${activeWorkplace.workplace_id}&skill_name=${activeWorkplace.skill_name}&iteration=${iter}`);
      if (res.ok) {
        const data = await res.json();
        setReportMd(data.report_md || '*此轮次尚未生成评测报告。*');
      } else {
        setReportMd('*获取报告失败*');
      }
    } catch {
      setReportMd('*网络异常，无法获取报告*');
    }
  };

  // 6. 新建需求 -> 初始化工作区沙盒
  const handlePublishRequirement = async () => {
    if (!newReq.name.trim()) return toast.error("需要填写技能名称");
    const tid = toast.loading("正在分配并初始化物理沙盒...");
    try {
      const res = await fetch('http://localhost:8000/api/evolve/init', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_name: newReq.name.trim(),
          is_upgrade: newReq.type === 'upgrade'
        })
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message, { id: tid });
        setShowNewModal(false);
        setNewReq({ type: 'create', name: '', description: '', scenario: '' });
        fetchWorkplaces(); 
        
        // 自动激活刚刚创建的工作区
        setActiveWorkplace({ workplace_id: data.workplace_id, skill_name: newReq.name.trim() });
        setCurrentStep('edit');
      } else {
        const err = await res.json();
        toast.error(err.detail || "沙盒初始化失败", { id: tid });
      }
    } catch { toast.error("网络异常", { id: tid }); }
  };

  // 7. 物理落盘保存文件
  const handleSaveFile = async (filename: string, content: string) => {
    if (!activeWorkplace) return;
    const tid = toast.loading(`正在将修改落盘至沙盒的 ${filename}...`);
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/file?workplace_id=${activeWorkplace.workplace_id}&skill_name=${activeWorkplace.skill_name}&filename=${filename}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      if (res.ok) {
        toast.success(`[${filename}] 成功写入沙盒磁盘！`, { id: tid });
        if (filename === 'evals/evals.json') setShowEvalModal(false);
      } else {
        toast.error("写入失败，请检查沙盒状态", { id: tid });
      }
    } catch { toast.error("网络异常", { id: tid }); }
  };

  // 8. 触发并发盲测
  const handleRunTest = async () => {
    if (!activeWorkplace) return;
    const tid = toast.loading("正在唤醒 Agent 并发盲测流水线...");
    try {
      const res = await fetch('http://localhost:8000/api/evolve/test/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workplace_id: activeWorkplace.workplace_id, skill_name: activeWorkplace.skill_name })
      });
      if (res.ok) {
        toast.success("后台盲测流水线已成功启动！请随时点击刷新获取最新报告。", { id: tid });
      } else {
        toast.error("触发测试失败", { id: tid });
      }
    } catch { toast.error("网络异常", { id: tid }); }
  };

  // 9. 拉取代码比对 Diff
  const handleLoadDiff = async () => {
    if (!activeWorkplace) return;
    setCurrentStep('merge');
    setIsDiffLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/evolve/diff?workplace_id=${activeWorkplace.workplace_id}&skill_name=${activeWorkplace.skill_name}`);
      if (res.ok) {
        const data = await res.json();
        setDiffContent(data.diff_content || "文件内容与主库相比没有任何改变。");
      } else {
        setDiffContent("获取差异信息失败，请检查服务。");
      }
    } catch { setDiffContent("网络异常，无法获取差异。"); }
    finally { setIsDiffLoading(false); }
  };

  // 10. 处理最终合并与打回
  const handleMerge = async (approved: boolean) => {
    if (!activeWorkplace) return;
    if (!approved && !rejectReason.trim()) return toast.error("打回加工必须填写明确的指导建议与拒绝理由！");
    
    const tid = toast.loading(approved ? "执行强合并到主库..." : "将意见反馈至沙盒...");
    try {
      const res = await fetch('http://localhost:8000/api/evolve/handle', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workplace_id: activeWorkplace.workplace_id,
          skill_name: activeWorkplace.skill_name,
          is_approved: approved,
          reject_reason: rejectReason.trim()
        })
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || (approved ? "✅ 代码已并入主库！" : "❎ 意见已送达，已打回重做！"), { id: tid });
        if (approved) {
          // 合并成功，沙盒销毁，清空选中状态并重新拉列表
          setActiveWorkplace(null);
          fetchWorkplaces();
        } else {
          setRejectReason('');
        }
      } else { toast.error("操作失败", { id: tid }); }
    } catch { toast.error("网络异常", { id: tid }); }
  };

  // 11. 危险：主库回滚
  const handleRollback = async () => {
    if (!activeWorkplace) return;
    if (!confirm(`🚨 危险操作：确定要把主库的 ${activeWorkplace.skill_name} 强制回滚到上一次 Git 提交版本吗？这无法撤销！`)) return;
    try {
      const res = await fetch('http://localhost:8000/api/evolve/rollback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_name: activeWorkplace.skill_name })
      });
      if (res.ok) toast.success((await res.json()).message);
      else toast.error("回滚执行被拒");
    } catch { toast.error("网络异常"); }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 flex gap-6 overflow-hidden font-sans">
      
      {/* 👈 左侧导航与列表 */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink" />
          </button>
          <div style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#a3be8c] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-1">
            <Dna size={24} strokeWidth={2.5} />
            <span className="tracking-widest text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>FACTORY</span>
          </div>
        </div>

        {/* 类型切换栏 */}
        <div className="flex gap-2 shrink-0">
          <button onClick={() => setActiveType('skill')} style={sketchyShape3} className={`flex-1 py-3 border-4 border-ink font-black tracking-widest transition-all flex items-center justify-center gap-2 ${activeType === 'skill' ? 'bg-[#d08770] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
            <Zap size={18} strokeWidth={3}/> SKILL
          </button>
          <button onClick={() => setActiveType('mcp')} style={sketchyShape2} className={`flex-1 py-3 border-4 border-ink font-black tracking-widest transition-all flex items-center justify-center gap-2 ${activeType === 'mcp' ? 'bg-[#EBCB8B] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
            <Server size={18} strokeWidth={3}/> MCP
          </button>
        </div>

        <button onClick={() => setShowNewModal(true)} style={sketchyShape1} className="shrink-0 p-4 bg-ink text-paper border-4 border-ink font-black tracking-widest shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-2 hover:bg-terracotta hover:text-ink transition-all active:translate-y-1 active:shadow-none rotate-1">
          <Plus size={24} strokeWidth={3}/> NEW REQUIREMENT
        </button>

        {/* 正在加工的技能列表 */}
        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-4 flex flex-col gap-3 overflow-hidden -rotate-1 relative">
          
          <div className="flex justify-between items-center px-2 py-1 border-b-2 border-ink/20 pb-2">
            <span className="font-black text-ink/40 tracking-widest text-sm uppercase">Processing Lines</span>
            <button onClick={fetchWorkplaces} className="text-ink/40 hover:text-terracotta transition-colors"><RefreshCw size={16}/></button>
          </div>

          <div className="flex-1 overflow-y-auto flex flex-col gap-3 pr-1">
            {workplaces.map((wp, idx) => (
              <div key={wp.workplace_id} onClick={() => { setActiveWorkplace(wp); setCurrentStep('edit'); }} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`cursor-pointer p-4 border-4 border-ink transition-all flex flex-col gap-1 ${activeWorkplace?.workplace_id === wp.workplace_id ? 'bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream hover:bg-sand hover:-translate-y-1 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]'}`}>
                <span className="font-black text-lg truncate text-ink">{wp.skill_name}</span>
                <span className="text-[10px] font-bold opacity-60 text-ink">ID: {wp.workplace_id}</span>
              </div>
            ))}
            {workplaces.length === 0 && <div className="text-center opacity-40 font-bold mt-10">No items processing.</div>}
          </div>
        </div>
      </div>

      {/* 👉 右侧主工作区 */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] overflow-hidden relative rotate-[0.5deg] z-10 flex flex-col">
        {activeWorkplace ? (
          <>
            {/* 顶部分步引导 */}
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

            <div className="flex-1 overflow-hidden relative p-8 bg-cream/30">
              
              {/* === 步骤 1: FILES === */}
              {currentStep === 'edit' && (
                <div className="flex flex-col h-full gap-4 max-w-5xl mx-auto">
                  <div className="flex justify-between items-end">
                    <h2 className="text-3xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILL.md</h2>
                    <button onClick={() => handleSaveFile('SKILL.md', skillMd)} style={sketchyShape3} className="px-6 py-2 bg-[#a3be8c] border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none flex items-center gap-2">
                      <Save size={18} strokeWidth={3}/> SAVE
                    </button>
                  </div>
                  
                  <textarea 
                    value={skillMd} onChange={(e) => setSkillMd(e.target.value)} 
                    className="flex-1 w-full bg-[#FDF8F0] border-4 border-ink p-6 font-mono text-base font-bold focus:outline-none resize-none shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" 
                    style={sketchyShape2} spellCheck={false}
                  />

                  {attachments.length > 0 && (
                    <div className="shrink-0 p-4 bg-ink/5 border-4 border-ink border-dashed flex flex-wrap items-center gap-3" style={sketchyShape1}>
                      <span className="font-black text-sm uppercase opacity-60 mr-2">沙盒附件映射 ({attachments.length}):</span>
                      {attachments.map(att => (
                        <div key={att} className="px-3 py-1 bg-paper border-2 border-ink text-xs font-bold shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] text-ink" style={sketchyShape3}>{att}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* === 步骤 2: TEST === */}
              {currentStep === 'test' && (
                <div className="flex flex-col h-full gap-6 max-w-5xl mx-auto">
                  <div className="flex gap-6 shrink-0 h-32">
                    <div style={sketchyShape2} className="flex-1 bg-paper border-4 border-ink p-6 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] flex justify-between items-center rotate-1">
                      <div>
                        <h3 className="text-xl font-black text-[#d08770] tracking-widest mb-1">EVALS.JSON</h3>
                        <p className="text-sm font-bold opacity-60">配置测试用例与断言标准</p>
                      </div>
                      <button onClick={() => { loadFileData('evals/evals.json', setEvalJson); setShowEvalModal(true); }} className="p-3 bg-cream border-4 border-ink hover:bg-sand shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-1 active:shadow-none transition-all" style={sketchyShape1}>
                        <FileEdit size={24} strokeWidth={2.5}/>
                      </button>
                    </div>
                    <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink p-6 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] flex justify-between items-center -rotate-1">
                      <div>
                        <h3 className="text-xl font-black text-[#EBCB8B] tracking-widest mb-1">SPAWN EVALS</h3>
                        <p className="text-sm font-bold opacity-60">触发沙盒并发盲测流水线</p>
                      </div>
                      <button onClick={handleRunTest} className="px-6 py-3 bg-[#EBCB8B] text-ink font-black border-4 border-ink hover:bg-[#d8b877] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-1 active:shadow-none transition-all flex items-center gap-2" style={sketchyShape2}>
                        <Play size={20} strokeWidth={3} fill="currentColor"/> RUN
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 flex gap-6 min-h-0">
                    <div className="w-48 shrink-0 flex flex-col gap-3 overflow-y-auto">
                      <div className="flex justify-between items-center">
                        <span className="font-black text-ink/40 tracking-widest text-sm">ARCHIVES</span>
                        <button onClick={loadIterations} className="text-ink/40 hover:text-ink"><RefreshCw size={16}/></button>
                      </div>
                      {iterations.map(iter => (
                        <button key={iter} onClick={() => handleSelectIteration(iter)} style={sketchyShape1} className={`p-4 border-4 border-ink font-black text-left transition-all ${activeIteration === iter ? 'bg-ink text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]' : 'bg-cream hover:bg-sand shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]'}`}>
                          Iteration {iter}
                        </button>
                      ))}
                      {iterations.length === 0 && <div className="text-sm font-bold opacity-50 mt-4">No archives yet.</div>}
                    </div>
                    
                    <div style={sketchyShape1} className="flex-1 bg-[#FDF8F0] border-4 border-ink p-6 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] overflow-y-auto font-bold text-ink prose max-w-none">
                      {reportMd ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{reportMd}</ReactMarkdown> : <span className="opacity-40 italic">Select an iteration to view report...</span>}
                    </div>
                  </div>
                </div>
              )}

              {/* === 步骤 3: MERGE === */}
              {currentStep === 'merge' && (
                <div className="flex flex-col h-full gap-6 max-w-5xl mx-auto">
                  <div className="flex justify-between items-center shrink-0">
                    <h2 className="text-3xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DIFF REVIEW</h2>
                    <button onClick={handleLoadDiff} className="flex items-center gap-2 px-4 py-2 border-4 border-ink font-black bg-cream shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand active:translate-y-1 active:shadow-none" style={sketchyShape3}>
                      <RefreshCw size={16} className={isDiffLoading ? "animate-spin" : ""}/> RELOAD DIFF
                    </button>
                  </div>

                  <div className="flex-1 bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-sm font-bold overflow-y-auto shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape1}>
                    {diffContent ? diffContent.split('\n').map((line, i) => {
                      let bg = '';
                      if (line.startsWith('+')) bg = 'bg-[#a3be8c]/20 text-[#a3be8c]';
                      if (line.startsWith('-')) bg = 'bg-[#bf616a]/20 text-[#bf616a]';
                      return <div key={i} className={`px-2 py-0.5 rounded ${bg}`}>{line || '\u00A0'}</div>;
                    }) : <span className="opacity-40">Click Reload Diff to fetch...</span>}
                  </div>

                  <div className="shrink-0 flex flex-col gap-4 bg-terracotta/10 p-6 border-4 border-ink border-dashed" style={sketchyShape2}>
                    <p className="font-black text-terracotta flex items-center gap-2"><MessageSquare size={20}/> FINAL DECISION</p>
                    <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder="如果不满意，请在这里写下你的修复指导意见，发回给 Agent 重做..." className="w-full bg-cream border-4 border-ink p-3 font-bold focus:outline-none resize-none h-24 shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3} />
                    <div className="flex gap-4">
                      <button onClick={() => handleMerge(false)} className="flex-1 py-4 bg-[#bf616a] text-paper border-4 border-ink font-black text-xl shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a54e56] active:translate-y-1 active:shadow-none flex justify-center items-center gap-2" style={sketchyShape1}>
                        <X strokeWidth={4}/> REJECT & REWORK
                      </button>
                      <button onClick={() => handleMerge(true)} className="flex-1 py-4 bg-[#a3be8c] text-ink border-4 border-ink font-black text-xl shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none flex justify-center items-center gap-2" style={sketchyShape2}>
                        <Check strokeWidth={4}/> APPROVE & MERGE
                      </button>
                    </div>
                  </div>
                  
                  <div className="pt-2 border-t-2 border-ink/20 border-dashed flex justify-between items-center">
                     <span className="text-sm font-bold text-[#bf616a] flex items-center gap-1"><AlertCircle size={16}/> 主库紧急救援：</span>
                     <button onClick={handleRollback} style={sketchyShape2} className="px-6 py-2 bg-paper text-[#bf616a] border-4 border-[#bf616a] font-black text-sm shadow-[2px_2px_0px_0px_#bf616a] hover:-translate-y-[1px] hover:bg-[#bf616a]/10 active:shadow-none active:translate-y-[1px] transition-all flex items-center gap-2">
                       <Undo2 size={16} strokeWidth={3}/> GIT REVERT TO PREVIOUS
                     </button>
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

      {/* === MODALS === */}
      
      {/* 1. 发布新需求弹窗 */}
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
                <label className="font-bold opacity-70 text-sm">Skill Name (Directory Level):</label>
                <input value={newReq.name} onChange={e=>setNewReq({...newReq, name: e.target.value})} placeholder="e.g. excel_parser" className="w-full bg-[#FDF8F0] border-4 border-ink p-3 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape2}/>
              </div>

              {/* 需求与场景：前端留好结构，待接入Agent Prompt */}
              <div className="flex flex-col gap-2">
                 <label className="font-bold opacity-70 text-sm">Description (What does it do?):</label>
                 <textarea value={newReq.description} onChange={e=>setNewReq({...newReq, description: e.target.value})} placeholder="I want a skill that can..." className="w-full h-20 resize-none bg-[#FDF8F0] border-4 border-ink p-3 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape1}/>
              </div>
              <div className="flex flex-col gap-2">
                 <label className="font-bold opacity-70 text-sm">Scenarios (When to trigger?):</label>
                 <textarea value={newReq.scenario} onChange={e=>setNewReq({...newReq, scenario: e.target.value})} placeholder="Trigger this skill whenever the user says..." className="w-full h-20 resize-none bg-[#FDF8F0] border-4 border-ink p-3 font-bold focus:outline-none shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3}/>
              </div>
            </div>

            <button onClick={handlePublishRequirement} style={sketchyShape1} className="w-full py-4 bg-terracotta text-paper border-4 border-ink font-black text-xl tracking-widest shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:bg-[#c4684b] active:translate-y-1 active:shadow-none rotate-1 mt-2">
              BUILD SANDBOX
            </button>
          </div>
        </div>
      )}

      {/* 3. 修改 evals.json 弹窗 */}
      {showEvalModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape1} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 w-full max-w-4xl h-[85vh]">
            <div className="flex justify-between items-center rotate-1 border-b-4 border-ink/20 pb-4 shrink-0">
              <h3 className="text-3xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>evals.json</h3>
              <button onClick={() => setShowEvalModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={32} strokeWidth={3}/></button>
            </div>
            
            <textarea 
              value={evalJson} onChange={e => setEvalJson(e.target.value)} 
              className="flex-1 w-full border-4 border-ink bg-[#FDF8F0] p-6 font-mono text-sm font-bold focus:outline-none resize-none rotate-1 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" 
              style={sketchyShape2} spellCheck={false} 
            />
            
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