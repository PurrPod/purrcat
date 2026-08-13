// src/components/HomePage.tsx
import { useState } from 'react'
import {
  MessageSquare, GitMerge, Settings, Terminal, Brain, Store
} from 'lucide-react'
import { useFlowStore } from '../store/flowStore'
import ConfigModal from './ConfigModal'

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

export default function HomePage({
  onEnterChat,
  onEnterEditor,
  onEnterMarket,
  onEnterEvolve,
  onEnterTask,
  onEnterMemory
}: {
  onEnterChat: () => void,
  onEnterEditor: () => void,
  onEnterMarket: () => void,
  onEnterEvolve: () => void,
  onEnterTask: () => void,
  onEnterMemory: () => void
}) {
  const [isConfigOpen, setIsConfigOpen] = useState(false);

  const handleNewWorkflow = () => {
    useFlowStore.getState().clearGraph()
    onEnterEditor()
  }

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] flex flex-col items-center justify-center overflow-hidden font-sans select-none">

      <button
        onClick={() => setIsConfigOpen(true)}
        style={sketchyShape3}
        className="absolute top-8 right-8 z-50 w-16 h-16 bg-[#EBCB8B] border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center transition-all hover:bg-terracotta hover:text-paper group rotate-6 hover:-rotate-3"
      >
        <Settings size={32} strokeWidth={2.5} className="group-hover:animate-[spin_3s_linear_infinite]" />
      </button>

      <div className="absolute top-16 md:top-20 left-1/2 -translate-x-1/2 z-30 pointer-events-none px-6 py-6">
        <h1 className="text-7xl md:text-[5.5rem] font-black text-ink tracking-tight leading-none relative whitespace-nowrap" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          PurrCat v1.0.0
          <svg className="absolute left-[-18%] top-1/2 -translate-y-1/2 w-[136%] h-24 -z-10 rotate-[-2deg]" viewBox="0 0 400 80" preserveAspectRatio="none" style={{ mixBlendMode: 'multiply' }}>
            <defs>
              <linearGradient id="brushGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#EBCB8B" stopOpacity="0.5"/>
                <stop offset="15%" stopColor="#EBCB8B" stopOpacity="0.8"/>
                <stop offset="50%" stopColor="#EBCB8B" stopOpacity="1.0"/>
                <stop offset="85%" stopColor="#EBCB8B" stopOpacity="0.8"/>
                <stop offset="100%" stopColor="#EBCB8B" stopOpacity="0.5"/>
              </linearGradient>
            </defs>
            <path d="M 0 30 C 40 10, 90 20, 140 15 C 190 10, 240 25, 290 20 C 340 15, 380 30, 390 50 C 390 70, 350 85, 300 80 C 250 75, 200 90, 150 85 C 100 80, 50 90, 0 70 C 0 50, 0 50, 0 30 Z" fill="url(#brushGrad)" opacity="0.9" />
          </svg>
        </h1>
      </div>

      {/* 🌟 三栏布局，左右各3个，形成弧形 */}
      <div className="relative w-full max-w-[1400px] min-h-[650px] flex flex-col md:flex-row items-center justify-center z-10 px-4 md:px-8 mt-40 md:mt-16 gap-6 md:gap-4 lg:gap-8">

        {/* 👈 左侧按钮组 (CHAT, TASK, EDITOR) */}
        <div className="flex-1 flex flex-col items-center md:items-end justify-center gap-6 z-20 w-full mt-8 md:mt-0 order-2 md:order-1">

          {/* 1. CHAT Button */}
          <button onClick={onEnterChat} className="w-[290px] h-[160px] relative flex flex-col items-center justify-center gap-2 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group md:mr-4 lg:mr-8">
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(212,122,90,1)] transition-all duration-200" fill="#fdfaf5">
              <path d="M 50,60 C 20,40 15,10 60,15 C 85,-5 135,-2 150,25 C 185,-10 240,0 255,35 C 295,25 315,70 285,100 C 315,135 295,175 250,170 C 230,200 170,205 135,180 C 100,205 50,190 55,155 C 15,145 20,95 50,60 Z" stroke="rgba(26,26,26,1)" strokeWidth="4.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="group-hover:fill-white transition-colors" />
            </svg>
            <div style={sketchyShape3} className="w-14 h-14 bg-terracotta border-4 border-ink flex items-center justify-center rotate-6 group-hover:bg-ink group-hover:-rotate-6 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <MessageSquare size={28} className="text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CHAT</h2>
              <p className="text-ink/50 text-[10px] font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Talk to Agent</p>
            </div>
          </button>

          {/* 2. TASK Button */}
          <button onClick={onEnterTask} className="w-[290px] h-[160px] relative flex flex-col items-center justify-center gap-2 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group md:-mr-6 lg:-mr-12">
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(235,203,139,1)] transition-all duration-200" fill="#fdfaf5">
              <path d="M 40,70 C 10,60 10,20 50,20 C 70,0 120,0 140,20 C 170,-5 230,-5 250,25 C 290,10 310,50 290,80 C 320,110 310,160 270,160 C 260,195 200,205 160,185 C 130,210 70,200 60,170 C 20,170 10,120 40,70 Z" stroke="rgba(26,26,26,1)" strokeWidth="4.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="group-hover:fill-white transition-colors" />
            </svg>
            <div style={sketchyShape1} className="w-14 h-14 bg-[#EBCB8B] border-4 border-ink flex items-center justify-center -rotate-3 group-hover:bg-ink group-hover:rotate-3 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <Terminal size={28} className="text-ink group-hover:text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TASK</h2>
              <p className="text-ink/50 text-[10px] font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Agent Workflows</p>
            </div>
          </button>

          {/* 3. EDITOR Button */}
          <button onClick={handleNewWorkflow} className="w-[290px] h-[160px] relative flex flex-col items-center justify-center gap-2 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group md:mr-4 lg:mr-8">
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(26,26,26,1)] transition-all duration-200" fill="#fdfaf5">
              <path d="M 50,60 C 20,40 15,10 60,15 C 85,-5 135,-2 150,25 C 185,-10 240,0 255,35 C 295,25 315,70 285,100 C 315,135 295,175 250,170 C 230,200 170,205 135,180 C 100,205 50,190 55,155 C 15,145 20,95 50,60 Z" stroke="rgba(26,26,26,1)" strokeWidth="4.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="group-hover:fill-white transition-colors" />
            </svg>
            <div style={sketchyShape2} className="w-14 h-14 bg-ink border-4 border-ink flex items-center justify-center -rotate-6 group-hover:bg-terracotta group-hover:rotate-6 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <GitMerge size={28} className="text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EDITOR</h2>
              <p className="text-ink/50 text-[10px] font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DAG Editor</p>
            </div>
          </button>

        </div>

        {/* 🐱 中间小猫 Logo */}
        <div className="shrink-0 w-[260px] md:w-[350px] lg:w-[450px] h-[340px] md:h-[585px] flex items-end justify-center z-10 hover:scale-[1.03] transition-transform duration-500 relative order-1 md:order-2">
          <img src="/src/purrcat-logo.png" alt="PurrCat Logo" className="w-full h-full object-contain filter drop-shadow-[4px_4px_0px_rgba(26,26,26,0.15)]" draggable={false} />
        </div>

        {/* 👉 右侧按钮组 (MARKET, MEMORY, EVOLVE) */}
        <div className="flex-1 flex flex-col items-center md:items-start justify-center gap-6 z-20 w-full mt-8 md:mt-0 order-3">

          {/* 1. MARKET Button */}
          <button onClick={onEnterMarket} className="w-[290px] h-[160px] relative flex flex-col items-center justify-center gap-2 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group md:ml-4 lg:ml-8">
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(136,192,208,1)] transition-all duration-200" fill="#fdfaf5">
              <path d="M 50,60 C 20,40 15,10 60,15 C 85,-5 135,-2 150,25 C 185,-10 240,0 255,35 C 295,25 315,70 285,100 C 315,135 295,175 250,170 C 230,200 170,205 135,180 C 100,205 50,190 55,155 C 15,145 20,95 50,60 Z" stroke="rgba(26,26,26,1)" strokeWidth="4.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="group-hover:fill-white transition-colors" />
            </svg>
            <div style={sketchyShape1} className="w-14 h-14 bg-[#88c0d0] border-4 border-ink flex items-center justify-center rotate-3 group-hover:bg-ink group-hover:-rotate-3 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <Store size={28} className="text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MARKET</h2>
              <p className="text-ink/50 text-[10px] font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Skills Explorer</p>
            </div>
          </button>

          {/* 2. MEMORY Button */}
          <button onClick={onEnterMemory} className="w-[290px] h-[160px] relative flex flex-col items-center justify-center gap-2 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group md:-ml-6 lg:-ml-12">
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(180,142,173,1)] transition-all duration-200" fill="#fdfaf5">
              <path d="M 40,70 C 10,60 10,20 50,20 C 70,0 120,0 140,20 C 170,-5 230,-5 250,25 C 290,10 310,50 290,80 C 320,110 310,160 270,160 C 260,195 200,205 160,185 C 130,210 70,200 60,170 C 20,170 10,120 40,70 Z" stroke="rgba(26,26,26,1)" strokeWidth="4.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="group-hover:fill-white transition-colors" />
            </svg>
            <div style={sketchyShape2} className="w-14 h-14 bg-[#b48ead] border-4 border-ink flex items-center justify-center rotate-6 group-hover:bg-ink group-hover:-rotate-6 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <Brain size={28} className="text-paper" strokeWidth={2.5} />
            </div>
            <div className="text-center z-10">
              <h2 className="text-xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEMORY</h2>
              <p className="text-ink/50 text-[10px] font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Knowledge Graph</p>
            </div>
          </button>

          {/* 3. EVOLVE Button */}
          <button onClick={onEnterEvolve} className="w-[290px] h-[160px] relative flex flex-col items-center justify-center gap-2 transition-all duration-200 active:translate-y-2 hover:-translate-y-1 group md:ml-4 lg:ml-8">
            <svg viewBox="0 0 310 210" className="absolute inset-0 w-full h-full filter drop-shadow-[8px_8px_0px_rgba(26,26,26,1)] group-hover:drop-shadow-[10px_10px_0px_rgba(163,190,140,1)] transition-all duration-200" fill="#fdfaf5">
              <path d="M 40,70 C 10,60 10,20 50,20 C 70,0 120,0 140,20 C 170,-5 230,-5 250,25 C 290,10 310,50 290,80 C 320,110 310,160 270,160 C 260,195 200,205 160,185 C 130,210 70,200 60,170 C 20,170 10,120 40,70 Z" stroke="rgba(26,26,26,1)" strokeWidth="4.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="group-hover:fill-white transition-colors" />
            </svg>
            <div style={sketchyShape3} className="w-14 h-14 bg-[#a3be8c] border-4 border-ink flex items-center justify-center -rotate-6 group-hover:bg-ink group-hover:rotate-6 transition-all duration-300 shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] z-10">
              <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-paper"><path d="m2 15 5.29-5.29a2 2 0 0 1 2.83 0L14 13.5a2 2 0 0 0 2.83 0L22 8"/><path d="m2 9 5.29 5.29a2 2 0 0 0 2.83 0L14 10.5a2 2 0 0 1 2.83 0L22 16"/></svg>
            </div>
            <div className="text-center z-10">
              <h2 className="text-xl font-black text-ink tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EVOLVE</h2>
              <p className="text-ink/50 text-[10px] font-bold mt-0.5 tracking-wider uppercase" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Skill Factory</p>
            </div>
          </button>

        </div>
      </div>

      {/* ============ 配置中心 Modal ============ */}
      <ConfigModal isOpen={isConfigOpen} onClose={() => setIsConfigOpen(false)} />
    </div>
  )
}
