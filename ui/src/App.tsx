import { useState, useEffect } from 'react';
import { Toaster } from 'react-hot-toast';
import { ReactFlowProvider } from '@xyflow/react';
import HomePage from './components/HomePage';
import Toolbar from './components/Toolbar';
import NodePanel from './components/NodePanel';
import FlowCanvas from './components/FlowCanvas';
import ChatPage from './components/ChatPage';
import TaskPage from './components/TaskPage';
import { useFlowStore } from './store/flowStore';

const nodeModules = import.meta.glob('../node_json/*.json', { eager: true });

function initializeCatalog() {
  const store = useFlowStore.getState();
  Object.values(nodeModules).forEach((mod: any) => {
    const nodeDef = mod.default || mod;
    if (nodeDef && nodeDef.type && nodeDef.name) {
      store.addCatalogItem({
        type: nodeDef.type,
        name: nodeDef.name,
        description: nodeDef.description || '',
        color: nodeDef.color || '#D47A5A',
        inputs: nodeDef.inputs || [],
        outputs: nodeDef.outputs || [],
        config: nodeDef.config || [],
        isCustom: true,
      });
    }
  });
}

type ViewState = 'home' | 'chat' | 'editor' | 'task';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };

const GlobalSketchyOverrides = () => (
  <style dangerouslySetInnerHTML={{__html: `
    * { font-family: "Comic Sans MS", "Chalkboard SE", "Comic Neue", cursive !important; }
    input, textarea, select, button { border-radius: 15px 225px 15px 255px/255px 15px 225px 15px !important; }

    .react-flow__node {
      border: 4px solid #1A1A1A !important;
      border-radius: 255px 15px 225px 15px/15px 225px 15px 255px !important;
      box-shadow: 8px 8px 0px 0px #1A1A1A !important;
    }
    .react-flow__node:nth-child(even) {
      border-radius: 15px 225px 15px 255px/255px 15px 225px 15px !important;
    }

    .react-flow__controls {
      border: 4px solid #1A1A1A !important;
      box-shadow: 6px 6px 0px 0px #1A1A1A !important;
      border-radius: 15px 225px 15px 255px/255px 15px 225px 15px !important;
      background: #FAF8F5 !important;
    }
    .react-flow__controls-button {
      border-bottom: 3px solid #1A1A1A !important;
      background: transparent !important;
      fill: #1A1A1A !important;
    }
    .react-flow__controls-button:hover { background: #EBCB8B !important; }

    .react-flow__handle {
      border: 3px solid #1A1A1A !important;
      width: 16px !important;
      height: 16px !important;
      background: #FAF8F5 !important;
    }

    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #1A1A1A; border-radius: 15px 225px 15px 255px/255px 15px 225px 15px; border: 2px solid #FAF8F5; }
  `}} />
);

function App() {
  const [currentView, setCurrentView] = useState<ViewState>('home');

  useEffect(() => {
    if (currentView === 'editor') {
      initializeCatalog();
    }
  }, [currentView]);

  return (
    <>
      {currentView === 'home' && <HomePage onEnterChat={() => setCurrentView('chat')} onEnterEditor={() => setCurrentView('editor')} />}
      {currentView === 'chat' && <ChatPage onBack={() => setCurrentView('home')} onSwitchToTask={() => setCurrentView('task')} />}

      {currentView === 'editor' && (
        // 桌布：加大 padding，扩大元素呼吸感
        <div className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-8 flex flex-col gap-8 overflow-hidden">
          <GlobalSketchyOverrides />

          {/* 顶栏彻底变成悬浮的两片纸 */}
          <Toolbar onBack={() => setCurrentView('home')} />
          
          {/* 画布和左侧栏容器，同样拉大间距 */}
          <div className="flex-1 flex gap-10 min-h-0 relative z-10 w-full max-w-[1920px] mx-auto">
            <ReactFlowProvider>
              
              {/* 左侧节点列表（去掉了它本身的背景边框，变成纯粹装贴纸的容器） */}
              <div className="w-[340px] flex flex-col relative z-20 h-full overflow-y-auto pr-4">
                 <NodePanel />
              </div>

              {/* 右侧大画板 */}
              <div 
                style={sketchyShape1}
                className="flex-1 bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] relative overflow-hidden z-10 flex flex-col rotate-[0.5deg]"
              >
                <div className="absolute -top-6 left-20 w-40 h-10 bg-[#EBCB8B]/80 border-4 border-ink -rotate-2 z-50 pointer-events-none" style={sketchyShape2}></div>
                
                <div className="flex-1 w-full h-full">
                  <FlowCanvas />
                </div>
              </div>

            </ReactFlowProvider>
          </div>
        </div>
      )}

      {currentView === 'task' && (
        <TaskPage onBack={() => setCurrentView('home')} onSwitchToChat={() => setCurrentView('chat')} />
      )}

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
    </>
  );
}

export default App;