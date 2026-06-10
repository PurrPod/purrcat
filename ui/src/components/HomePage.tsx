// src/components/HomePage.tsx
import { useState, useEffect } from 'react'
import { MessageSquare, GitMerge, Settings, X, Save, FileJson, AlertCircle } from 'lucide-react'
import { useFlowStore } from '../store/flowStore'
import { toast } from 'react-hot-toast'

// 原有配置面板手绘形变
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
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] flex flex-col items-center justify-center overflow-hidden font-sans select-none">
      
      {/* ⚙️ 右上角系统配置齿轮 */}
      <button 
        onClick={() => setIsConfigOpen(true)}
        style={sketchyShape3}
        className="absolute top-8 right-8 z-50 w-16 h-16 bg-[#EBCB8B] border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center transition-all hover:bg-terracotta hover:text-paper group rotate-6 hover:-rotate-3"
      >
        <Settings size={32} strokeWidth={2.5} className="group-hover:animate-[spin_3s_linear_infinite]" />
      </button>

      {/* 👑 全局大艺术字标题：独立嵌在整个页面偏左上角 */}
      <div className="absolute top-12 left-12 md:top-16 md:left-24 z-30 pointer-events-none">
        <h1 className="text-5xl md:text-7xl font-black text-[#EBCB8B] tracking-tight leading-none" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          Hello, PurrCat.
        </h1>
      </div>

      {/* 🌟 核心漫画分镜主容器 */}
      <div className="relative w-full max-w-6xl h-[650px] flex flex-col md:flex-row items-center justify-center z-10 px-6 mt-16 md:mt-12">
        
        {/* ================= 👈 左侧分镜：小猫全身照 + 专属发言气泡 ================= */}
        <div className="flex-1 w-full flex flex-col items-center md:items-end justify-center relative h-full">
          
          {/* 💬 小猫口中吐出的单独对话气泡：尖角精准指向下方的小猫头部 */}
          <div 
            className="absolute top-0 md:top-8 md:left-12 bg-paper border-4 border-ink p-5 shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] z-30 rotate-2 max-w-xs"
            style={sketchyShape1}
          >
            <p className="text-ink text-xl font-black tracking-wide leading-tight" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              What are we building today?
            </p>
            {/* 漫画对话框专属小尖角尾巴 - 指向大猫咪 */}
            <div className="absolute -bottom-[12px] left-1/3 w-5 h-5 bg-paper border-b-4 border-r-4 border-ink rotate-45 z-10"></div>
          </div>

          {/* 🐾 小猫全身照安全容器 - 显著变大且更靠右以接近云朵想法区 */}
          <div className="absolute bottom-2 md:bottom-6 md:right-4 w-[400px] h-[520px] flex items-end justify-center z-10 hover:scale-[1.03] transition-transform duration-500">
            <img 
              src="/src/purrcat-logo.png" 
              alt="PurrCat Logo" 
              className="w-full h-full object-contain filter drop-shadow-[4px_4px_0px_rgba(26,26,26,0.15)]"
              draggable={false}
            />
          </div>

        </div>

        {/* ================= 👉 右侧分镜：小猫头顶冒出的精美云朵选项 ================= */}
        <div className="flex-1 w-full flex flex-col items-center md:items-start justify-center gap-10 relative z-20 md:pl-24 h-full mt-28 md:mt-0">
          
          {/* ☁️ 选项一：直接对话 (CHAT) - 调换后移至上方 */}
          <button
            onClick={onEnterChat}
            className="w-[310px] h-[210px] relative flex flex-col items-center justify-center gap-3 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group"
          >
            {/* 云朵背景 */}
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(212,122,90,1)] transition-all duration-200" fill="#fdfaf5">
              <path 
                d="M 50,60 
                   C 20,40 15,10 60,15 
                   C 85,-5 135,-2 150,25 
                   C 185,-10 240,0 255,35 
                   C 295,25 315,70 285,100 
                   C 315,135 295,175 250,170 
                   C 230,200 170,205 135,180 
                   C 100,205 50,190 55,155 
                   C 15,145 20,95 50,60 Z" 
                stroke="rgba(26,26,26,1)" 
                strokeWidth="4.5" 
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
                className="group-hover:fill-white transition-colors"
              />
            </svg>

            {/* 核心内容 - 改为原 Editor 经典的暖红配色 (bg-terracotta) */}
            <div style={sketchyShape3} className="w-16 h-16 bg-terracotta border-4 border-ink flex items-center justify-center rotate-6 group-hover:bg-ink group-hover:-rotate-6 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <MessageSquare size={32} className="text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-2xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CHAT</h2>
              <p className="text-ink/50 text-xs font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Talk to Agent</p>
            </div>
          </button>

          {/* ☁️ 选项二：工作流编辑器 (EDITOR) - 调换后移至下方且右偏错落 */}
          <button
            onClick={handleNewWorkflow}
            className="w-[310px] h-[210px] relative flex flex-col items-center justify-center gap-3 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 md:ml-16 group"
          >
            {/* 云朵背景 */}
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(26,26,26,1)] transition-all duration-200" fill="#fdfaf5">
              <path 
                d="M 40,70 
                   C 10,60 10,20 50,20 
                   C 70,0 120,0 140,20 
                   C 170,-5 230,-5 250,25 
                   C 290,10 310,50 290,80 
                   C 320,110 310,160 270,160 
                   C 260,195 200,205 160,185 
                   C 130,210 70,200 60,170 
                   C 20,170 10,120 40,70 Z" 
                stroke="rgba(26,26,26,1)" 
                strokeWidth="4.5" 
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
                className="group-hover:fill-white transition-colors"
              />
            </svg>

            {/* 核心内容 - 改为稳重帅气的极客纯黑色 (bg-ink) */}
            <div style={sketchyShape2} className="w-16 h-16 bg-ink border-4 border-ink flex items-center justify-center -rotate-6 group-hover:bg-terracotta group-hover:rotate-6 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <GitMerge size={32} className="text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-2xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EDITOR</h2>
              <p className="text-ink/50 text-xs font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DAG Workflow</p>
            </div>
          </button>

        </div>
      </div>

      {/* ========================================================== */}
      {/* 🔴 后续配置面板弹窗中心（原有逻辑落盘安全承接） */}
      {/* ========================================================== */}
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