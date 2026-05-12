import { MessageSquare, GitMerge } from 'lucide-react'
import { useFlowStore } from '../store/flowStore'

// 手绘魔法
const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

export default function HomePage({ 
  onEnterChat, 
  onEnterEditor 
}: { 
  onEnterChat: () => void, 
  onEnterEditor: () => void 
}) {
  
  const handleNewWorkflow = () => {
    useFlowStore.getState().clearGraph()
    onEnterEditor()
  }

  return (
    <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] flex flex-col items-center justify-center overflow-hidden font-sans">
      
      {/* 散落在桌上的装饰性小纸条 */}
      <div 
        style={sketchyShape3}
        className="absolute top-20 left-32 bg-[#EBCB8B] border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] px-6 py-4 -rotate-6 font-black text-ink text-xl z-0"
      >
        <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>Top Secret! 🐾</span>
      </div>
      
      <div 
        style={sketchyShape2}
        className="absolute bottom-32 right-40 bg-ink text-paper border-4 border-ink shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] px-8 py-6 rotate-12 font-black text-2xl z-0"
      >
        <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>Agent System V1.0</span>
      </div>

      <div className="max-w-4xl w-full px-6 z-10">
        <div className="text-center mb-16 relative">
          {/* 标题背景的高亮记号笔效果 */}
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

        <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-3xl mx-auto relative mt-12">
          {/* 开始对话卡片 */}
          <div className="relative group">
            {/* 纸胶带 */}
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 w-24 h-8 bg-terracotta/40 border-2 border-ink rotate-3 z-20 transition-transform group-hover:rotate-6" style={sketchyShape1}></div>
            
            <button
              onClick={onEnterChat}
              style={sketchyShape2}
              className="w-full bg-paper border-4 border-ink p-10 flex flex-col items-center justify-center gap-6 hover:-translate-y-2 hover:-rotate-2 shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] hover:shadow-[14px_14px_0px_0px_rgba(26,26,26,1)] transition-all -rotate-1 relative z-10"
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
            {/* 纸胶带 */}
            <div className="absolute -top-3 right-10 w-20 h-8 bg-[#EBCB8B]/80 border-2 border-ink -rotate-6 z-20 transition-transform group-hover:-rotate-12" style={sketchyShape2}></div>

            <button
              onClick={handleNewWorkflow}
              style={sketchyShape1}
              className="w-full bg-paper border-4 border-ink p-10 flex flex-col items-center justify-center gap-6 hover:-translate-y-2 hover:rotate-2 shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] hover:shadow-[14px_14px_0px_0px_rgba(212,122,90,1)] transition-all rotate-1 relative z-10"
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
    </div>
  )
}