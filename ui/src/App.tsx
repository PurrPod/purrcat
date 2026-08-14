// src/App.tsx
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { Minus, Square, X } from 'lucide-react';

import HomePage from './components/HomePage';
import ChatPage from './components/ChatPage';
import TaskPage from './components/TaskPage';
import MemoryPage from './components/MemoryPage';
import EditorPage from './components/EditorPage';
import MarketPage from './components/MarketPage'; // 🌟 导入新页面
import EvolvePage from './components/EvolvePage'; // 🌟 导入新页面

const sketchyBtn = { borderRadius: '6px 10px 5px 8px/8px 5px 10px 6px' };

function WindowControls() {
  const purrcat = (window as any).purrcat;
  if (!purrcat?.winMinimize) return null;
  return (
    <div className="no-drag fixed top-2.5 right-2 z-[2147483647] flex gap-2 items-center">
      <button onClick={() => purrcat.winMinimize()} title="最小化"
        className="win-ctrl w-7 h-7 border-2 border-ink bg-transparent flex items-center justify-center text-ink hover:bg-ink/10 hover:-translate-y-0.5 transition-all"
        style={sketchyBtn}>
        <Minus size={14} strokeWidth={3.5} />
      </button>
      <button onClick={() => purrcat.winToggleMaximize()} title="最大化"
        className="win-ctrl w-7 h-7 border-2 border-ink bg-transparent flex items-center justify-center text-ink hover:bg-ink/10 hover:-translate-y-0.5 transition-all"
        style={sketchyBtn}>
        <Square size={11} strokeWidth={3.5} />
      </button>
      <button onClick={() => purrcat.winClose()} title="关闭"
        className="win-ctrl w-7 h-7 border-2 border-ink bg-transparent flex items-center justify-center text-ink hover:bg-terracotta hover:text-white hover:border-terracotta hover:-translate-y-0.5 transition-all"
        style={sketchyBtn}>
        <X size={14} strokeWidth={3.5} />
      </button>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <WindowControls />
      <Routes>
        <Route path="/" element={<HomeRouteWrapper />} />
        <Route path="/chat/:sessionId?" element={<ChatRouteWrapper />} />
        <Route path="/task" element={<TaskRouteWrapper />} />
        <Route path="/editor" element={<EditorPage />} />
        <Route path="/memory" element={<MemoryRouteWrapper />} />
        <Route path="/market" element={<MarketRouteWrapper />} /> {/* 🌟 新增路由 */}
        <Route path="/evolve" element={<EvolveRouteWrapper />} /> {/* 🌟 新增路由 */}
      </Routes>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#FAF8F5',
            color: '#1A1A1A',
            fontFamily: '"Comic Sans MS", cursive',
            border: '4px solid #1a1a1a',
            boxShadow: '6px 6px 0px 0px #1a1a1a',
            borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px',
            fontWeight: '900',
            fontSize: '1.1rem',
            padding: '16px 24px'
          },
        }}
      />
    </BrowserRouter>
  );
}

function HomeRouteWrapper() {
  const navigate = useNavigate();
  return <HomePage 
    onEnterChat={() => navigate('/chat')} 
    onEnterEditor={() => navigate('/editor')} 
    onEnterMarket={() => navigate('/market')}
    onEnterEvolve={() => navigate('/evolve')}
    onEnterTask={() => navigate('/task')}     // 🌟 传入新增的 Task 路由
    onEnterMemory={() => navigate('/memory')} // 🌟 传入新增的 Memory 路由
  />;
}

function MemoryRouteWrapper() {
  const navigate = useNavigate();
  return <MemoryPage onBack={() => navigate(-1)} />;
}

function ChatRouteWrapper() {
  const navigate = useNavigate();
  return <ChatPage onBack={() => navigate(-1)} onSwitchToTask={() => navigate('/task')} />;
}

function TaskRouteWrapper() {
  const navigate = useNavigate();
  return <TaskPage onBack={() => navigate(-1)} />;
}

// 🌟 Market 的 Wrapper
function MarketRouteWrapper() {
  const navigate = useNavigate();
  return <MarketPage onBack={() => navigate(-1)} />;
}

// 🌟 Evolve 的 Wrapper
function EvolveRouteWrapper() {
  const navigate = useNavigate();
  return <EvolvePage onBack={() => navigate(-1)} />;
}