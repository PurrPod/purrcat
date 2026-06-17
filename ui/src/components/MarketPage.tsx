// src/components/MarketPage.tsx
import { useState, useEffect } from 'react';
import { ArrowLeft, Store, RefreshCw, User, ExternalLink, AlertCircle, Zap, Server, Activity, GitMerge } from 'lucide-react';
import { toast } from 'react-hot-toast';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

type MarketTab = 'skill' | 'mcp' | 'sensor' | 'graph';

export default function MarketPage({ onBack }: { onBack: () => void }) {
  const [activeTab, setActiveTab] = useState<MarketTab>('skill');
  const [marketData, setMarketData] = useState<Record<string, any>>({});
  const [isFetching, setIsFetching] = useState(true);

  const fetchMarketData = async (isManual = false) => {
    setIsFetching(true);
    try {
      // 拉取 Github Raw 数据 (自带跨域允许)
      const res = await fetch(`https://raw.githubusercontent.com/PurrPod/skills/main/registry.json?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setMarketData(data.skills || {});
        if (isManual) toast.success("集市数据已更新！");
      } else {
        toast.error("无法拉取注册表，请检查网络。");
      }
    } catch (e) {
      toast.error("集市请求失败，可能受限于 Github 访问限制。");
    } finally {
      setIsFetching(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'skill') {
      fetchMarketData();
    }
  }, [activeTab]);

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">
      
      {/* ================= 👈 左侧导航菜单 ================= */}
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        
        {/* 顶部标题区 */}
        <div className="flex gap-4 items-center">
          <button 
            onClick={onBack} 
            style={sketchyShape2} 
            className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group"
          >
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          
          <div 
            style={sketchyShape1} 
            className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#88c0d0] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2"
          >
            <Store size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MARKET</span>
          </div>
        </div>

        {/* 菜单列表区 */}
        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="flex-1 flex flex-col gap-4 mt-4">
            
            <button 
              onClick={() => setActiveTab('skill')} 
              style={sketchyShape1} 
              className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'skill' ? 'bg-terracotta text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}
            >
              <Zap size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILLS</div>
                <div className="text-xs font-bold opacity-70">Agent Capabilities</div>
              </div>
            </button>

            <button 
              onClick={() => setActiveTab('mcp')} 
              style={sketchyShape2} 
              className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'mcp' ? 'bg-[#EBCB8B] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}
            >
              <Server size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP SERVERS</div>
                <div className="text-xs font-bold opacity-70">Context Providers</div>
              </div>
            </button>

            <button 
              onClick={() => setActiveTab('sensor')} 
              style={sketchyShape3} 
              className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'sensor' ? 'bg-[#a3be8c] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}
            >
              <Activity size={28} strokeWidth={2.5}/>
              <div>
                <div className="font-black text-xl tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSORS</div>
                <div className="text-xs font-bold opacity-70">Autonomous Triggers</div>
              </div>
            </button>

            <button 
              onClick={() => setActiveTab('graph')} 
              style={sketchyShape1} 
              className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'graph' ? 'bg-[#b48ead] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}
            >
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
        
        {/* 内容区 Header */}
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
            onClick={() => fetchMarketData(true)}
            disabled={isFetching || activeTab !== 'skill'}
            style={sketchyShape2}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#EBCB8B] text-ink border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all rotate-2 disabled:opacity-50"
          >
            <RefreshCw size={20} strokeWidth={3} className={isFetching ? "animate-spin text-terracotta" : "text-ink"} />
            <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>REFRESH</span>
          </button>
        </div>

        {/* 内容区 Body */}
        <div className="flex-1 overflow-y-auto w-full h-full relative bg-cream/30">
          
          {/* SKILLS 面板 */}
          {activeTab === 'skill' && (
            <div className="p-10">
              {isFetching && Object.keys(marketData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50">
                  <RefreshCw className="animate-spin text-terracotta" size={64} strokeWidth={2} />
                  <p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Fetching Repositories...</p>
                </div>
              ) : Object.keys(marketData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50 text-ink">
                  <AlertCircle size={64} strokeWidth={2} />
                  <p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Registry is empty.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8 pb-8">
                  {Object.values(marketData).map((skill: any, idx) => (
                    <div 
                      key={skill.name} 
                      style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} 
                      className={`bg-paper border-4 border-ink p-6 flex flex-col gap-3 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all ${idx % 3 === 0 ? '-rotate-1' : 'rotate-1'}`}
                    >
                      <div className="flex justify-between items-start border-b-2 border-ink/10 pb-3 mb-1">
                        <h3 className="text-xl font-black truncate text-ink pr-2" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={skill.name}>
                          {skill.name}
                        </h3>
                        <span className={`text-[10px] font-black px-2 py-1 uppercase border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] ${skill.type === 'official' ? 'bg-[#a3be8c] text-ink' : 'bg-ink text-paper'}`} style={sketchyShape1}>
                          {skill.type || 'community'}
                        </span>
                      </div>
                      
                      <p className="text-sm font-bold opacity-60 flex items-center gap-1.5">
                        <User size={14} strokeWidth={3} /> {skill.author || 'Unknown'}
                      </p>
                      
                      <p className="text-[15px] font-bold mt-2 flex-1 leading-relaxed text-ink/80">
                        {skill.description}
                      </p>

                      {skill.tags && skill.tags.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-2">
                          {skill.tags.map((tag: string) => (
                            <span key={tag} className="text-[10px] font-black px-2 py-0.5 bg-[#FDF8F0] border-2 border-ink/40 text-ink/60" style={sketchyShape3}>#{tag}</span>
                          ))}
                        </div>
                      )}
                      
                      <div className="flex justify-end mt-4 pt-4 border-t-2 border-ink/10 border-dashed">
                        <a 
                          href={skill.source_url || `https://github.com/PurrPod/skillpod/tree/main/community/${skill.name}`} 
                          target="_blank" 
                          rel="noreferrer" 
                          className="flex items-center gap-2 px-5 py-2 bg-cream hover:bg-[#88c0d0] hover:text-paper border-4 border-ink text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] font-black text-sm transition-all active:translate-y-1 active:shadow-none" 
                          style={sketchyShape1}
                        >
                          GITHUB <ExternalLink size={16} strokeWidth={3} />
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 预留的面版 - 其它选项卡 */}
          {activeTab !== 'skill' && (
            <div className="flex flex-col items-center justify-center h-[60vh] gap-6 opacity-40 text-ink">
              {activeTab === 'mcp' && <Server size={80} strokeWidth={1.5} />}
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