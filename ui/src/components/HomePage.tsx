// src/components/HomePage.tsx
import { useState, useEffect } from 'react'
import { MessageSquare, GitMerge, Settings, X, Save, FileJson, AlertCircle } from 'lucide-react'
import { useFlowStore } from '../store/flowStore'
import { toast } from 'react-hot-toast'

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

const CONFIG_TABS = ['model', 'sensor', 'file', 'memory', 'mcp'];

export default function HomePage({ 
  onEnterChat, 
  onEnterEditor
}: { 
  onEnterChat: () => void, 
  onEnterEditor: () => void
}) {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('model');
  const [configData, setConfigData] = useState<Record<string, any>>({});
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [editJsonStr, setEditJsonStr] = useState('');

  const handleNewWorkflow = () => {
    useFlowStore.getState().clearGraph()
    onEnterEditor()
  }

  const fetchConfig = async (tab: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/config/${tab}`);
      if (res.ok) {
        const data = await res.json();
        setConfigData(data);
        setExpandedKey(null);
        setEditJsonStr('');
      } else {
        toast.error(`无法加载 ${tab} 配置`);
      }
    } catch {
      toast.error("网络错误，无法连接后端");
    }
  };

  useEffect(() => {
    if (isConfigOpen) {
      fetchConfig(activeTab);
    }
  }, [isConfigOpen, activeTab]);

  const toggleKey = (key: string) => {
    if (expandedKey === key) {
      setExpandedKey(null);
    } else {
      setExpandedKey(key);
      setEditJsonStr(JSON.stringify(configData[key], null, 2));
    }
  };

  const handleSave = async (key: string) => {
    try {
      const parsedValue = JSON.parse(editJsonStr);
      const newConfig = { ...configData, [key]: parsedValue };

      const res = await fetch(`http://localhost:8000/api/config/${activeTab}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig)
      });

      if (res.ok) {
        toast.success(`[${key}] 配置已落盘！`);
        setConfigData(newConfig);
        setExpandedKey(null);
      } else {
        toast.error("保存失败，后端拒绝了请求");
      }
    } catch {
      toast.error("保存失败：JSON 格式不合法！请检查引号和括号。");
    }
  };

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] flex flex-col items-center justify-center overflow-hidden font-sans">
      
      <button 
        onClick={() => setIsConfigOpen(true)}
        style={sketchyShape3}
        className="absolute top-8 right-8 z-20 w-16 h-16 bg-[#EBCB8B] border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center transition-all hover:bg-terracotta hover:text-paper group rotate-6 hover:-rotate-3"
      >
        <Settings size={32} strokeWidth={2.5} className="group-hover:animate-[spin_3s_linear_infinite]" />
      </button>

      <div 
        style={sketchyShape3}
        className="absolute top-20 left-32 bg-[#EBCB8B] border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] px-6 py-4 -rotate-6 font-black text-ink text-xl z-0 pointer-events-none"
      >
        <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>Top Secret! 🐾</span>
      </div>
      
      <div 
        style={sketchyShape2}
        className="absolute bottom-32 right-40 bg-ink text-paper border-4 border-ink shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] px-8 py-6 rotate-12 font-black text-2xl z-0 pointer-events-none"
      >
        <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>Agent System V1.0</span>
      </div>

      <div className="max-w-4xl w-full px-6 z-10">
        <div className="text-center mb-16 relative">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-12 bg-terracotta/20 -rotate-2 mix-blend-multiply pointer-events-none"></div>
          
          <h1 
            className="text-6xl md:text-8xl font-black text-ink tracking-tighter mb-4 relative z-10 drop-shadow-[4px_4px_0px_rgba(212,122,90,0.3)]"
            style={{ fontFamily: '"Comic Sans MS", cursive' }}
          >
            Hello, PurrCat.
          </h1>
          <p className="text-ink/80 text-2xl font-bold mt-6 rotate-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            What are we building today?
          </p>
        </div>

        {/* 🌟 修改点：只保留两列入口 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-3xl mx-auto relative mt-12">
          {/* 开始对话卡片 */}
          <div className="relative group">
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 w-24 h-8 bg-terracotta/40 border-2 border-ink rotate-3 z-20 transition-transform group-hover:rotate-6" style={sketchyShape1}></div>
            
            <button
              onClick={onEnterChat}
              style={sketchyShape2}
              className="w-full bg-paper border-4 border-ink p-12 flex flex-col items-center justify-center gap-6 hover:-translate-y-2 hover:-rotate-2 shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] hover:shadow-[14px_14px_0px_0px_rgba(26,26,26,1)] transition-all -rotate-1 relative z-10"
            >
              <div 
                style={sketchyShape3}
                className="w-24 h-24 bg-ink border-4 border-ink flex items-center justify-center rotate-3 group-hover:bg-terracotta transition-colors duration-300"
              >
                <MessageSquare size={48} className="text-paper" strokeWidth={2.5} />
              </div>
              <div className="text-center">
                <h2 className="text-3xl font-black text-ink mb-2 tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CHAT</h2>
                <p className="text-ink/60 font-bold" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Talk to Agent</p>
              </div>
            </button>
          </div>

          {/* 编辑工作流卡片 */}
          <div className="relative group">
            <div className="absolute -top-3 right-10 w-20 h-8 bg-[#EBCB8B]/80 border-2 border-ink -rotate-6 z-20 transition-transform group-hover:-rotate-12" style={sketchyShape2}></div>

            <button
              onClick={handleNewWorkflow}
              style={sketchyShape1}
              className="w-full bg-paper border-4 border-ink p-12 flex flex-col items-center justify-center gap-6 hover:-translate-y-2 hover:rotate-2 shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] hover:shadow-[14px_14px_0px_0px_rgba(212,122,90,1)] transition-all rotate-1 relative z-10"
            >
              <div 
                style={sketchyShape2}
                className="w-24 h-24 bg-terracotta border-4 border-ink flex items-center justify-center -rotate-3 group-hover:bg-ink transition-colors duration-300"
              >
                <GitMerge size={48} className="text-paper" strokeWidth={2.5} />
              </div>
              <div className="text-center">
                <h2 className="text-3xl font-black text-ink mb-2 tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EDITOR</h2>
                <p className="text-ink/60 font-bold" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DAG Workflow</p>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* 🔴 配置面板弹窗部分保持不变... */}
      {isConfigOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 md:p-8 pointer-events-auto">
          <div 
            style={sketchyShape2} 
            className="bg-cream border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-6xl h-[85vh] flex flex-row relative"
          >
            <div className="absolute -top-4 left-1/4 w-32 h-10 bg-terracotta/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>
            <button onClick={() => setIsConfigOpen(false)} className="absolute top-4 right-6 hover:rotate-90 hover:text-terracotta transition-all z-10 p-2 bg-paper border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape3}>
              <X size={28} strokeWidth={4} />
            </button>

            <div className="w-64 shrink-0 border-r-4 border-ink/20 flex flex-col p-6">
              <div className="pb-6 flex items-center gap-4">
                <Settings size={40} strokeWidth={2.5} className="text-terracotta" />
                <h2 className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CONFIG</h2>
              </div>
              <div className="flex flex-col gap-4">
                {CONFIG_TABS.map((tab, idx) => {
                  const isActive = activeTab === tab;
                  const rotation = idx % 2 === 0 ? 'rotate-1' : '-rotate-1';
                  const shape = idx % 3 === 0 ? sketchyShape1 : idx % 2 === 0 ? sketchyShape2 : sketchyShape3;
                  return (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      style={shape}
                      className={`px-4 py-3 font-black text-lg border-4 border-ink uppercase tracking-wider transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]
                        ${isActive ? 'bg-[#EBCB8B] text-ink -translate-x-1' : 'bg-paper text-ink/70 hover:bg-sand'} ${rotation}`}
                    >
                      {tab}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-6">
              {Object.keys(configData).length === 0 ? (
                <div className="text-center font-bold text-ink/40 mt-10 text-2xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>No data found or Loading...</div>
              ) : (
                Object.keys(configData).map((key, idx) => {
                  const isExpanded = expandedKey === key;
                  const itemShape = idx % 2 === 0 ? sketchyShape2 : sketchyShape1;

                  return (
                    <div key={key} className="flex flex-col gap-2">
                      <button
                        onClick={() => toggleKey(key)}
                        style={itemShape}
                        className={`w-full text-left p-4 border-4 border-ink flex justify-between items-center transition-all 
                          ${isExpanded ? 'bg-ink text-paper shadow-none' : 'bg-paper text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 hover:shadow-[8px_8px_0px_0px_rgba(26,26,26,1)]'}`}
                      >
                        <div className="flex items-center gap-3">
                          <FileJson size={24} strokeWidth={2.5} className={isExpanded ? 'text-terracotta' : 'text-[#EBCB8B]'} />
                          <span className="text-2xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{key}</span>
                        </div>
                        <span className="font-bold opacity-50">{isExpanded ? 'CLOSE' : 'EDIT'}</span>
                      </button>

                      {isExpanded && (
                        <div style={sketchyShape3} className="bg-paper border-4 border-ink p-4 flex flex-col gap-4 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)]">
                          <div className="flex items-center gap-2 text-ink/60 font-bold text-sm bg-terracotta/10 p-2 border-2 border-ink border-dashed" style={sketchyShape1}>
                            <AlertCircle size={16} strokeWidth={3} />
                            注意：请严格遵守 JSON 格式（必须带双引号），否则会保存失败！
                          </div>
                          <textarea
                            value={editJsonStr}
                            onChange={(e) => setEditJsonStr(e.target.value)}
                            className="w-full h-64 bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-[15px] leading-relaxed font-bold focus:outline-none focus:bg-white resize-y"
                            spellCheck={false}
                          />
                          <div className="flex justify-end">
                            <button
                              onClick={() => handleSave(key)}
                              style={sketchyShape1}
                              className="px-8 py-3 bg-[#a3be8c] border-4 border-ink text-ink font-black text-xl flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all rotate-1"
                            >
                              <Save size={24} strokeWidth={3} /> SAVE TO DISK
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}