// src/App.tsx
import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import HomePage from './components/HomePage';
import ChatPage from './components/ChatPage';
import TaskPage from './components/TaskPage';
import MemoryPage from './components/MemoryPage';
import EditorPage from './components/EditorPage';
import SetupWizard from './components/SetupWizard';

interface EnvStatus {
  ready: boolean;
  engine: string | null;
  has_podman: boolean;
  has_docker: boolean;
}

export default function App() {
  const [envStatus, setEnvStatus] = useState<EnvStatus | null>(null);
  const [checkingEnv, setCheckingEnv] = useState(true);

  useEffect(() => {
    const checkEnv = async () => {
      try {
        const response = await fetch('/api/system/env/status');
        const data = await response.json();
        setEnvStatus({
          ready: data.ready,
          engine: data.engine || null,
          has_podman: data.has_podman || false,
          has_docker: data.has_docker || false
        });
      } catch (error) {
        console.error('环境检测失败:', error);
        setEnvStatus({
          ready: false,
          engine: null,
          has_podman: false,
          has_docker: false
        });
      } finally {
        setCheckingEnv(false);
      }
    };

    checkEnv();

    const interval = setInterval(checkEnv, 5000);
    return () => clearInterval(interval);
  }, []);

  if (checkingEnv) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-amber-50 to-orange-100 flex items-center justify-center">
        <div className="text-center">
          <div className="relative">
            <div className="w-20 h-20 border-4 border-amber-800 rounded-full animate-spin border-t-transparent"></div>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 bg-amber-500 rounded-full"></div>
            </div>
          </div>
          <p className="mt-6 text-amber-800 font-bold text-xl">检测运行环境中...</p>
        </div>
      </div>
    );
  }

  if (!envStatus?.ready) {
    return <SetupWizard onEnvReady={() => window.location.reload()} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeRouteWrapper />} />
        <Route path="/chat/:sessionId?" element={<ChatRouteWrapper />} />
        <Route path="/task" element={<TaskRouteWrapper />} />
        <Route path="/editor" element={<EditorPage />} />
        <Route path="/memory" element={<MemoryRouteWrapper />} />
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
  />;
}

function MemoryRouteWrapper() {
  const navigate = useNavigate();
  return <MemoryPage onBack={() => navigate('/')} />;
}

function ChatRouteWrapper() {
  const navigate = useNavigate();
  return <ChatPage onBack={() => navigate('/')} onSwitchToTask={() => navigate('/task')} />;
}

function TaskRouteWrapper() {
  const navigate = useNavigate();
  return <TaskPage onBack={() => navigate('/')} onSwitchToChat={() => navigate('/chat')} />;
}