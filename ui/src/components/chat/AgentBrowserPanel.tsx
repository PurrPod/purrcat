import React, { useState, useRef, useEffect } from 'react';
import { MousePointer2, Frame, Globe, Send, X, Code2, ExternalLink } from 'lucide-react';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './ChatShared';
import type { BrowserTab } from '../ChatPage';

interface AgentBrowserPanelProps {
  tabs: BrowserTab[];
  setTabs: React.Dispatch<React.SetStateAction<BrowserTab[]>>;
  activeTabId: string | null;
  setActiveTabId: (id: string | null) => void;
  mode: 'browse' | 'pick' | 'draw';
  setMode: (mode: 'browse' | 'pick' | 'draw') => void;
  onComment: (pixelData: any, comment: string, currentUrl: string) => void;
}

const VIRTUAL_WIDTH = 1280;

const INJECT_SCRIPT = `
  (function() {
    if (window._purrcatInjected) return;
    window._purrcatInjected = true;

    let overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.pointerEvents = 'none';
    overlay.style.backgroundColor = 'rgba(235, 203, 139, 0.4)';
    overlay.style.border = '2px dashed #d08770';
    overlay.style.zIndex = '2147483647';
    overlay.style.display = 'none';
    document.body.appendChild(overlay);

    let isPicking = false;

    window.addEventListener('message', (e) => {
      if (e.data === 'PURRCAT_START_PICK') isPicking = true;
      if (e.data === 'PURRCAT_STOP_PICK') {
        isPicking = false;
        overlay.style.display = 'none';
      }
    });

    document.addEventListener('mouseover', (e) => {
      if (!isPicking) return;
      e.stopPropagation();
      const rect = e.target.getBoundingClientRect();
      overlay.style.width = rect.width + 'px';
      overlay.style.height = rect.height + 'px';
      overlay.style.left = rect.left + 'px';
      overlay.style.top = rect.top + 'px';
      overlay.style.display = 'block';
    }, true);

    document.addEventListener('click', (e) => {
      if (!isPicking) return;
      e.preventDefault();
      e.stopPropagation();
      
      const target = e.target;
      const rect = target.getBoundingClientRect();
      
      window.parent.postMessage({
        type: 'PURRCAT_ELEMENT_PICKED',
        data: {
          tag: target.tagName.toLowerCase(),
          id: target.id,
          className: typeof target.className === 'string' ? target.className : '',
          rect: { x: rect.left, y: rect.top, w: rect.width, h: rect.height }
        }
      }, '*');
      
      isPicking = false;
      overlay.style.display = 'none';
    }, true);
  })();
`;

export default function AgentBrowserPanel({
  tabs, setTabs, activeTabId, setActiveTabId,
  mode, setMode, onComment
}: AgentBrowserPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const iframeRefs = useRef<Record<string, HTMLIFrameElement | null>>({});

  const [addressInput, setAddressInput] = useState('');
  const [scaleProps, setScaleProps] = useState({ scale: 1, virtualHeight: 800 });
  const [injectionFailed, setInjectionFailed] = useState(false);

  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [currentRect, setCurrentRect] = useState<{ x: number, y: number, w: number, h: number } | null>(null);
  const [showCommentBox, setShowCommentBox] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [pickedElement, setPickedElement] = useState<any>(null);

  const activeTab = tabs.find(t => t.id === activeTabId);

  // 🌟 监听活跃 Tab 变化，同步地址栏
  useEffect(() => {
    if (activeTab) setAddressInput(activeTab.url);
  }, [activeTabId, activeTab]);

  // 缩放计算
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const newScale = width / VIRTUAL_WIDTH;
        const newVHeight = height / newScale;
        setScaleProps({ scale: newScale, virtualHeight: newVHeight });
      }
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // 多 Tab 下的通讯控制：只给当前激活的 iframe 发消息
  useEffect(() => {
    if (!activeTabId) return;
    const activeIframe = iframeRefs.current[activeTabId];
    if (!activeIframe) return;

    if (mode === 'pick' && !injectionFailed) {
      activeIframe.contentWindow?.postMessage('PURRCAT_START_PICK', '*');
    } else {
      activeIframe.contentWindow?.postMessage('PURRCAT_STOP_PICK', '*');
      setPickedElement(null);
    }
  }, [mode, injectionFailed, activeTabId]);

  // 监听选取返回
  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type === 'PURRCAT_ELEMENT_PICKED') {
        setCurrentRect(e.data.data.rect);
        setPickedElement(e.data.data);
        setShowCommentBox(true);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const handleIframeLoad = (tabId: string) => {
    try {
      const doc = iframeRefs.current[tabId]?.contentDocument;
      if (doc) {
        const script = doc.createElement('script');
        script.innerHTML = INJECT_SCRIPT;
        doc.body.appendChild(script);
        setInjectionFailed(false);
      }
    } catch {
      setInjectionFailed(true);
    }
  };

  const handleAddressSubmit = () => {
    if (!activeTabId || !addressInput.trim()) return;
    let finalUrl = addressInput;
    if (!finalUrl.startsWith('http') && !finalUrl.startsWith('blob') && !finalUrl.startsWith('data')) {
      finalUrl = 'http://' + finalUrl;
    }
    setTabs(tabs.map(t => t.id === activeTabId ? { ...t, url: finalUrl } : t));
  };

  const closeTab = (id: string) => {
    const newTabs = tabs.filter(t => t.id !== id);
    setTabs(newTabs);
    if (activeTabId === id) {
      setActiveTabId(newTabs.length > 0 ? newTabs[newTabs.length - 1].id : null);
    }
    setMode('browse');
    setShowCommentBox(false);
    setCurrentRect(null);
  };

  // 🌟 核心数学公式：将鼠标物理坐标转换为无损的虚拟像素坐标
  const getScaledCoords = (e: React.MouseEvent) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) / scaleProps.scale,
      y: (e.clientY - rect.top) / scaleProps.scale
    };
  };

  const handleDrawStart = (e: React.MouseEvent) => {
    if (showCommentBox) {
      setShowCommentBox(false);
      setCurrentRect(null);
      return;
    }
    const { x, y } = getScaledCoords(e);

    if (mode === 'pick' && injectionFailed) {
      setCurrentRect({ x: x - 5, y: y - 5, w: 10, h: 10 });
      setShowCommentBox(true);
      return;
    }

    if (mode === 'draw') {
      setIsDrawing(true);
      setStartPos({ x, y });
      setCurrentRect({ x, y, w: 0, h: 0 });
    }
  };

  const handleDrawMove = (e: React.MouseEvent) => {
    if (!isDrawing || mode !== 'draw') return;
    const { x, y } = getScaledCoords(e);
    setCurrentRect({
      x: Math.min(startPos.x, x),
      y: Math.min(startPos.y, y),
      w: Math.abs(x - startPos.x),
      h: Math.abs(y - startPos.y)
    });
  };

  const handleDrawEnd = () => {
    if (isDrawing && mode === 'draw') {
      setIsDrawing(false);
      if (currentRect && currentRect.w > 10 && currentRect.h > 10) {
        setShowCommentBox(true);
      } else {
        setCurrentRect(null);
      }
    }
  };

  const submitComment = () => {
    if (!commentText.trim() || !currentRect || !activeTab) return;

    const elementContext = pickedElement
      ? `DOM Tag: <${pickedElement.tag}${pickedElement.id ? ` id="${pickedElement.id}"` : ''}${pickedElement.className ? ` class="${pickedElement.className}"` : ''}>`
      : (injectionFailed && mode === 'pick' ? 'User clicked specific coordinate' : 'User drawn area');

    onComment(
      { mode, rect: currentRect, domContext: elementContext, viewport: { width: VIRTUAL_WIDTH, height: scaleProps.virtualHeight } },
      commentText,
      activeTab.url
    );

    setCommentText('');
    setShowCommentBox(false);
    setCurrentRect(null);
    setPickedElement(null);
    setMode('browse');
  };

  const needsOverlay = mode === 'draw' || (mode === 'pick' && injectionFailed);

  return (
    <div style={sketchyShape2} className="h-full bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col relative overflow-hidden">

      {/* 🌟 多标签栏 (Tab Bar) */}
      <div className="flex bg-[#bf616a] p-2 gap-2 overflow-x-auto shrink-0">
        {tabs.map(tab => (
          <div
            key={tab.id}
            onClick={() => setActiveTabId(tab.id)}
            className={`flex items-center gap-2 px-3 py-1.5 border-2 border-ink cursor-pointer min-w-[120px] max-w-[200px] transition-colors ${activeTabId === tab.id ? 'bg-cream text-ink font-bold shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]' : 'bg-sand text-ink/70 hover:bg-paper'}`}
            style={sketchyShape1}
          >
            <span className="truncate flex-1 text-xs">{tab.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
              className={`p-0.5 rounded hover:bg-terracotta hover:text-paper ${activeTabId === tab.id ? 'text-ink' : 'text-ink/50'}`}
            >
              <X size={12} strokeWidth={3} />
            </button>
          </div>
        ))}
      </div>

      {/* 地址栏 & 工具栏 */}
      <div className="flex items-center gap-3 p-3 border-b-4 border-ink bg-cream shrink-0 relative z-10">
        <div className="flex gap-2">
          <button onClick={() => setMode('browse')} className={`p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors ${mode === 'browse' ? 'bg-[#88c0d0] text-paper' : 'bg-white hover:bg-sand'}`} style={sketchyShape1} title="正常浏览">
            <Globe size={18} strokeWidth={3} />
          </button>

          <button onClick={() => { setMode('pick'); setShowCommentBox(false); setCurrentRect(null); }} className={`p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors ${mode === 'pick' ? 'bg-[#EBCB8B] text-ink' : 'bg-white hover:bg-sand'}`} style={sketchyShape3} title="元素选取">
            <MousePointer2 size={18} strokeWidth={3} />
          </button>

          <button onClick={() => { setMode('draw'); setShowCommentBox(false); setCurrentRect(null); }} className={`p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors ${mode === 'draw' ? 'bg-[#bf616a] text-paper' : 'bg-white hover:bg-sand'}`} style={sketchyShape2} title="自由画框">
            <Frame size={18} strokeWidth={3} />
          </button>
        </div>

        <input
          disabled={!activeTabId}
          value={addressInput}
          onChange={e => setAddressInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAddressSubmit()}
          className="flex-1 border-4 border-ink bg-white px-3 py-1.5 font-bold focus:outline-none text-sm disabled:bg-sand disabled:text-ink/50"
          style={sketchyShape3}
          placeholder={activeTabId ? "输入网址，回车访问..." : ""}
        />
        <button
          onClick={() => {
            const url = activeTab?.url || addressInput;
            if (url) {
              const finalUrl = url.startsWith('http') || url.startsWith('blob') || url.startsWith('data') ? url : 'http://' + url;
              window.open(finalUrl, '_blank');
            }
          }}
          disabled={!activeTabId}
          className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-white hover:bg-sand disabled:opacity-40 disabled:cursor-not-allowed"
          style={sketchyShape3}
          title="在外部浏览器中打开"
        >
          <ExternalLink size={16} strokeWidth={3} />
        </button>
      </div>

      {/* 🌟 视图区：处理空白主页和多 Iframe 渲染 */}
      <div ref={containerRef} className="flex-1 relative overflow-hidden bg-[#e5e9f0]">

        {tabs.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#e5e9f0] z-50 text-ink/40">
            <Globe size={48} strokeWidth={2} className="mb-4" />
            <h2 className="text-xl font-black tracking-wider" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat Browser</h2>
            <p className="text-xs font-bold mt-1">Waiting for connection...</p>
          </div>
        ) : (
          <div
            className="absolute top-0 left-0 origin-top-left bg-white"
            style={{
              width: VIRTUAL_WIDTH,
              height: scaleProps.virtualHeight,
              transform: `scale(${scaleProps.scale})`
            }}
          >
            {/* 🌟 核心：遍历渲染所有的 Tab，隐藏非活跃的 Tab，这样切换就不会刷新网页 */}
            {tabs.map(tab => (
              <iframe
                key={tab.id}
                ref={el => { iframeRefs.current[tab.id] = el; }}
                src={tab.url}
                onLoad={() => handleIframeLoad(tab.id)}
                className="w-full h-full border-none absolute inset-0"
                style={{
                  display: activeTabId === tab.id ? 'block' : 'none',
                  pointerEvents: needsOverlay ? 'none' : 'auto'
                }}
              />
            ))}

            {/* 交互拦截层：只在 Draw 模式或跨域降级 Pick 模式下启用 */}
            {needsOverlay && (
              <div
                className="absolute inset-0 z-10 cursor-crosshair"
                onMouseDown={handleDrawStart}
                onMouseMove={handleDrawMove}
                onMouseUp={handleDrawEnd}
              />
            )}

            {/* 渲染当前选区 (基于 1280px 标准坐标系) */}
            {currentRect && (
              <div
                className={`absolute border-4 pointer-events-none z-20 ${mode === 'pick' ? 'border-[#EBCB8B] bg-[#EBCB8B]/20' : 'border-[#bf616a] bg-[#bf616a]/20'}`}
                style={{
                  left: currentRect.x,
                  top: currentRect.y,
                  width: Math.max(currentRect.w, 8),
                  height: Math.max(currentRect.h, 8),
                  ...sketchyShape1
                }}
              >
                {pickedElement && (
                  <div className="absolute -top-7 left-[-4px] bg-ink text-paper text-[10px] font-bold px-2 py-1 rounded-t flex items-center gap-1 whitespace-nowrap">
                    <Code2 size={10} />
                    {pickedElement.tag}
                    {pickedElement.className && <span className="opacity-70">.{pickedElement.className.split(' ')[0]}</span>}
                  </div>
                )}
              </div>
            )}

            {/* 评论悬浮窗 */}
            {showCommentBox && currentRect && (
              <div
                className="absolute z-30 bg-paper border-4 border-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] p-3 pointer-events-auto"
                style={{
                  width: 280,
                  left: Math.min(currentRect.x + currentRect.w + 10, VIRTUAL_WIDTH - 300),
                  top: Math.max(10, currentRect.y - 20),
                  ...sketchyShape2
                }}
              >
                <div className="flex justify-between items-center mb-2">
                  <span className="font-black text-sm text-terracotta tracking-wider">COMMAND</span>
                  <button onClick={() => { setShowCommentBox(false); setCurrentRect(null); setPickedElement(null); setMode('browse'); }} className="hover:text-terracotta"><X size={16} strokeWidth={3} /></button>
                </div>
                <textarea
                  autoFocus
                  value={commentText}
                  onChange={e => setCommentText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitComment(); }
                  }}
                  placeholder={pickedElement ? `修改 <${pickedElement.tag}> 元素...` : "要求 Agent 修改此处的..."}
                  className="w-full bg-[#FDF8F0] border-2 border-ink p-2 text-sm font-bold resize-none h-20 focus:outline-none mb-2"
                  style={sketchyShape3}
                />
                <button onClick={submitComment} className="w-full bg-ink text-paper font-black py-2 flex justify-center items-center gap-2 hover:bg-terracotta hover:text-ink transition-colors border-2 border-ink" style={sketchyShape1}>
                  <Send size={14} strokeWidth={3} /> EXECUTE
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}