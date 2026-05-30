// src/App.tsx
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import HomePage from './components/HomePage';
import ChatPage from './components/ChatPage';
import TaskPage from './components/TaskPage';
import MemoryPage from './components/MemoryPage';
import EditorPage from './components/EditorPage';

export default function App() {
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