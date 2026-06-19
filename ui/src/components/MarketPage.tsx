// src/components/MarketPage.tsx
import { useState, useEffect } from 'react';
import { ArrowLeft, Store, RefreshCw, User, ExternalLink, AlertCircle, Zap, Server, Activity, GitMerge, Info, X, Copy } from 'lucide-react';
import { toast } from 'react-hot-toast';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

type MarketTab = 'skill' | 'mcp' | 'sensor' | 'graph';

export default function MarketPage({ onBack }: { onBack: () => void }) {
  const [activeTab, setActiveTab] = useState<MarketTab>('skill');
  
  const [skillData, setSkillData] = useState<Record<string, any>>({});
  const [isFetchingSkill, setIsFetchingSkill] = useState(false);

  const [mcpData, setMcpData] = useState<Record<string, any>>({});
  const [isFetchingMcp, setIsFetchingMcp] = useState(false);

  // 选中的 MCP 详情信息弹窗
  const [selectedMcpInfo, setSelectedMcpInfo] = useState<any>(null);

  const fetchSkillData = async (isManual = false) => {
    setIsFetchingSkill(true);
    try {
      const res = await fetch(`https://raw.githubusercontent.com/PurrPod/skills/main/registry.json?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setSkillData(data.skills || {});
        if (isManual) toast.success("Skills 列表已刷新！");
      }
    } catch {
      toast.error("Skills 仓库请求失败");
    } finally {
      setIsFetchingSkill(false);
    }
  };

  const fetchMcpData = async (isManual = false) => {
    setIsFetchingMcp(true);
    try {
      const res = await fetch(`https://raw.githubusercontent.com/PurrPod/mcps/main/registry.json?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setMcpData(data.mcps || {});
        if (isManual) toast.success("MCP Servers 列表已刷新！");
      }
    } catch {
      toast.error("MCP 仓库请求失败");
    } finally {
      setIsFetchingMcp(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'skill' && Object.keys(skillData).length === 0) fetchSkillData();
    if (activeTab === 'mcp' && Object.keys(mcpData).length === 0) fetchMcpData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleRefresh = () => {
    if (activeTab === 'skill') fetchSkillData(true);
    if (activeTab === 'mcp') fetchMcpData(true);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('已复制到剪贴板！');
  };

  const isFetching = activeTab === 'skill' ? isFetchingSkill : isFetchingMcp;

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">
      
      {/* 🌟 MCP 详情弹窗 */}
      {selectedMcpInfo && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-3xl flex flex-col relative rotate-[0.5deg]">
            <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#EBCB8B]/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>
            
            {/* 弹窗 Header */}
            <div className="flex justify-between items-center p-6 border-b-4 border-ink/20 shrink-0">
              <div className="flex items-center gap-3">
                <Server size={32} strokeWidth={2.5} className="text-[#EBCB8B]" />
                <div>
                  <h2 className="text-2xl font-black tracking-widest text-ink mt-1 uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{selectedMcpInfo.name}</h2>
                  <p className="text-sm font-bold text-ink/60">by {selectedMcpInfo.author}</p>
                </div>
              </div>
              <button onClick={() => setSelectedMcpInfo(null)} className="p-2 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all" style={sketchyShape3}>
                <X size={24} strokeWidth={3} />
              </button>
            </div>

            {/* 弹窗 Body */}
            <div className="p-6 flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <span className="font-black text-ink tracking-widest">SOURCE URL:</span>
                <a href={selectedMcpInfo.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 px-4 py-2 border-2 border-ink bg-[#FDF8F0] text-[#3498DB] font-bold text-sm w-fit shadow-[2px_2px_0px_0px_rgba(26,26,26,0.1)] hover:underline" style={sketchyShape1}>
                  {selectedMcpInfo.source_url} <ExternalLink size={14} />
                </a>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-end">
                  <span className="font-black text-ink tracking-widest">CONFIGURATION (JSON):</span>
                  <button onClick={() => copyToClipboard(JSON.stringify({ mcpServers: selectedMcpInfo.mcpServers }, null, 2))} className="flex items-center gap-1 text-xs font-black bg-cream border-2 border-ink px-2 py-1 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a3be8c] transition-all active:translate-y-[1px] active:shadow-none" style={sketchyShape2}>
                    <Copy size={12} strokeWidth={3}/> COPY
                  </button>
                </div>
                {/* 格式化并渲染 JSON */}
                <pre style={sketchyShape3} className="bg-[#FDF8F0] border-4 border-ink p-4 overflow-x-auto text-sm font-mono font-bold shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] text-ink">
                  {JSON.stringify({ mcpServers: selectedMcpInfo.mcpServers }, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ================= 👈 左侧导航菜单 ================= */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          <div style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#88c0d0] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2">
            <Store size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MARKET</span>
          </div>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="flex-1 flex flex-col gap-4 mt-4">
            
            <button onClick={() => setActiveTab('skill')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'skill' ? 'bg-terracotta text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Zap size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILLS</div>
                <div className="text-xs font-bold opacity-70">Agent Capabilities</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('mcp')} style={sketchyShape2} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'mcp' ? 'bg-[#EBCB8B] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Server size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP SERVERS</div>
                <div className="text-xs font-bold opacity-70">Context Providers</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('sensor')} style={sketchyShape3} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'sensor' ? 'bg-[#a3be8c] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Activity size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSORS</div>
                <div className="text-xs font-bold opacity-70">Autonomous Triggers</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('graph')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'graph' ? 'bg-[#b48ead] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <GitMerge size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>GRAPHS</div>
                <div className="text-xs font-bold opacity-70">Workflow Templates</div>
              </div>
            </button>

          </div>
        </div>
      </div>

      {/* ================= 👉 右侧主内容区 ================= */}
      <div style={sketchyShape1} className="flex-1 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] overflow-hidden relative rotate-[0.5deg] z-10 flex flex-col">
        
        <div className="pt-8 px-10 pb-4 flex items-center justify-between shrink-0 border-b-4 border-ink/10 relative z-20 bg-paper">
          <div className="flex items-center gap-4">
            <div style={sketchyShape2} className="w-12 h-12 bg-ink border-4 border-ink flex items-center justify-center rotate-6">
              {activeTab === 'skill' && <Zap className="text-terracotta" strokeWidth={2.5} />}
              {activeTab === 'mcp' && <Server className="text-[#EBCB8B]" strokeWidth={2.5} />}
              {activeTab === 'sensor' && <Activity className="text-[#a3be8c]" strokeWidth={2.5} />}
              {activeTab === 'graph' && <GitMerge className="text-[#b48ead]" strokeWidth={2.5} />}
            </div>
            <h2 className="text-3xl font-black tracking-widest text-ink uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              {activeTab} EXPLORER
            </h2>
          </div>

          <button
            onClick={handleRefresh}
            disabled={isFetching || (activeTab !== 'skill' && activeTab !== 'mcp')}
            style={sketchyShape2}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#EBCB8B] text-ink border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all rotate-2 disabled:opacity-50"
          >
            <RefreshCw size={20} strokeWidth={3} className={isFetching ? "animate-spin text-terracotta" : "text-ink"} />
            <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>REFRESH</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto w-full h-full relative bg-cream/30">
          
          {/* SKILLS 列表渲染 */}
          {activeTab === 'skill' && (
            <div className="p-10">
              {isFetchingSkill && Object.keys(skillData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-terracotta" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Fetching Repositories...</p></div>
              ) : Object.keys(skillData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Registry is empty.</p></div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8 pb-8">
                  {Object.values(skillData).map((skill: any, idx) => (
                    <div key={skill.name} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`bg-paper border-4 border-ink p-6 flex flex-col gap-3 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all ${idx % 3 === 0 ? '-rotate-1' : 'rotate-1'}`}>
                      <div className="flex justify-between items-start border-b-2 border-ink/10 pb-3 mb-1">
                        <h3 className="text-xl font-black truncate text-ink pr-2" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={skill.name}>{skill.name}</h3>
                        <span className={`text-[10px] font-black px-2 py-1 uppercase border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] ${skill.type === 'official' ? 'bg-[#a3be8c] text-ink' : 'bg-ink text-paper'}`} style={sketchyShape1}>{skill.type || 'community'}</span>
                      </div>
                      <p className="text-sm font-bold opacity-60 flex items-center gap-1.5"><User size={14} strokeWidth={3} /> {skill.author || 'Unknown'}</p>
                      <p className="text-[15px] font-bold mt-2 flex-1 leading-relaxed text-ink/80">{skill.description}</p>
                      {skill.tags && skill.tags.length > 0 && <div className="flex flex-wrap gap-2 mt-2">{skill.tags.map((tag: string) => <span key={tag} className="text-[10px] font-black px-2 py-0.5 bg-[#FDF8F0] border-2 border-ink/40 text-ink/60" style={sketchyShape3}>#{tag}</span>)}</div>}
                      <div className="flex justify-end mt-4 pt-4 border-t-2 border-ink/10 border-dashed">
                        <a href={skill.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 px-5 py-2 bg-cream hover:bg-[#88c0d0] hover:text-paper border-4 border-ink text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] font-black text-sm transition-all active:translate-y-1 active:shadow-none" style={sketchyShape1}>GITHUB <ExternalLink size={16} strokeWidth={3} /></a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* MCP SERVERS 列表渲染 */}
          {activeTab === 'mcp' && (
            <div className="p-10">
              {isFetchingMcp && Object.keys(mcpData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-[#EBCB8B]" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Fetching Repositories...</p></div>
              ) : Object.keys(mcpData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Registry is empty.</p></div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8 pb-8">
                  {Object.values(mcpData).map((mcp: any, idx) => (
                    <div key={mcp.name} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`bg-paper border-4 border-ink p-6 flex flex-col gap-3 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all ${idx % 3 === 0 ? 'rotate-1' : '-rotate-1'}`}>
                      <div className="flex justify-between items-start border-b-2 border-ink/10 pb-3 mb-1">
                        <h3 className="text-xl font-black truncate text-ink pr-2" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={mcp.name}>{mcp.name}</h3>
                        <span className={`text-[10px] font-black px-2 py-1 uppercase border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] ${mcp.type === 'official' ? 'bg-terracotta text-paper' : 'bg-ink text-paper'}`} style={sketchyShape3}>{mcp.type || 'community'}</span>
                      </div>
                      
                      <p className="text-sm font-bold opacity-60 flex items-center gap-1.5"><User size={14} strokeWidth={3} /> {mcp.author || 'Unknown'}</p>
                      
                      <p className="text-[15px] font-bold mt-2 flex-1 leading-relaxed text-ink/80">{mcp.description}</p>
                      
                      <div className="flex justify-between items-center mt-4 pt-4 border-t-2 border-ink/10 border-dashed">
                        {/* INFO 配置详情查看按钮 */}
                        <button onClick={() => setSelectedMcpInfo(mcp)} className="flex items-center gap-1 px-4 py-2 bg-[#EBCB8B] hover:bg-[#d8b877] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] font-black text-sm transition-all active:translate-y-1 active:shadow-none" style={sketchyShape2}>
                          <Info size={16} strokeWidth={3} /> CONFIG
                        </button>

                        <a href={mcp.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 px-4 py-2 bg-cream hover:bg-sand text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] font-black text-sm transition-all active:translate-y-1 active:shadow-none" style={sketchyShape1}>
                          <ExternalLink size={16} strokeWidth={3} /> REPO
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab !== 'skill' && activeTab !== 'mcp' && (
            <div className="flex flex-col items-center justify-center h-[60vh] gap-6 opacity-40 text-ink">
              {activeTab === 'sensor' && <Activity size={80} strokeWidth={1.5} />}
              {activeTab === 'graph' && <GitMerge size={80} strokeWidth={1.5} />}
              <p className="text-3xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>COMING SOON</p>
              <p className="font-bold text-lg">此模块的在线集市正在施工中...</p>
            </div>
          )}
          
        </div>
      </div>
    </div>
  );
}