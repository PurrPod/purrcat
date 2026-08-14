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

export default function AgentBrowserPanel({
  tabs, setTabs, activeTabId, setActiveTabId,
  mode, setMode, onComment
}: AgentBrowserPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const logicalOverlayRef = useRef<HTMLDivElement>(null); // 新增：逻辑坐标系容器
  const lastHoverRef = useRef(0);

  // 新增：固定逻辑分辨率（保持桌面端浏览体验）
  const VIEWPORT_W = 1280;
  const VIEWPORT_H = 800;

  const [addressInput, setAddressInput] = useState('');
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [hoverRect, setHoverRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });
  const [currentRect, setCurrentRect] = useState<{ x: number, y: number, w: number, h: number } | null>(null);
  const [showCommentBox, setShowCommentBox] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [pickedElement, setPickedElement] = useState<any>(null);

  // 缩放和留白位置
  const [viewScale, setViewScale] = useState(1);
  const [viewOffset, setViewOffset] = useState({ x: 0, y: 0 });

  const purrcat = (window as any).purrcat;
  const hasElectron = !!purrcat?.browserNewTab;

  const activeTab = tabs.find(t => t.id === activeTabId);

  useEffect(() => {
    if (activeTab) setAddressInput(activeTab.url);
  }, [activeTabId, activeTab]);

  // bounds 同步：保证前端等比例缩放 (Letterbox)，并带缩放比例给主进程
  useEffect(() => {
    if (!hasElectron) return;
    const sync = () => {
      const el = containerRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        const targetRatio = VIEWPORT_W / VIEWPORT_H;
        const currentRatio = r.width / r.height;
        let s = 1;
        let scaledW = r.width;
        let scaledH = r.height;
        let offsetX = 0;
        let offsetY = 0;

        // 计算居中留白 (Letterbox 策略)
        if (currentRatio > targetRatio) {
          s = r.height / VIEWPORT_H;
          scaledW = VIEWPORT_W * s;
          offsetX = (r.width - scaledW) / 2;
        } else {
          s = r.width / VIEWPORT_W;
          scaledH = VIEWPORT_H * s;
          offsetY = (r.height - scaledH) / 2;
        }

        setViewScale(s);
        setViewOffset({ x: offsetX, y: offsetY });

        // 将 letterboxed 的确切物理坐标 + scale参数 发给原生
        // (主进程用 enableDeviceEmulation 锁定 1280x800 桌面视口并按 s 硬缩放，避免响应式变形)
        // Math.round 防护：Electron setBounds 严格要求整数，传小数会导致定位错位或白边
        purrcat.browserSetBounds(
          Math.round(r.left + offsetX),
          Math.round(r.top + offsetY),
          Math.round(scaledW),
          Math.round(scaledH),
          s
        );
      }
    };
    sync();
    const ro = new ResizeObserver(sync);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener('resize', sync);
    return () => { ro.disconnect(); window.removeEventListener('resize', sync); };
  }, [hasElectron]);

  // 卸载时通知主进程把原生 view 移到屏外，避免它继续盖住 React 工作区
  useEffect(() => {
    return () => {
      if (hasElectron) {
        try { purrcat.browserHide(); } catch (_) {}
      }
    };
  }, [hasElectron]);

  useEffect(() => {
    if (!hasElectron || !activeTabId) return;
    let cancelled = false;
    if (mode === 'browse') {
      purrcat.browserPickEnd(activeTabId).catch(() => {});
      setSnapshot(null);
      setHoverRect(null);
    } else {
      purrcat.browserPickStart(activeTabId).then((res: any) => {
        if (!cancelled) setSnapshot(res?.imageDataUrl || null);
      }).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [mode, activeTabId, hasElectron]);

  useEffect(() => {
    if (!hasElectron) return;
    const off = purrcat.onTabEvent((evt: any) => {
      if (evt.type === 'title') {
        setTabs(prev => prev.map(t => t.id === evt.tabId ? { ...t, title: evt.title } : t));
      } else if (evt.type === 'navigate') {
        setTabs(prev => prev.map(t => t.id === evt.tabId ? { ...t, url: evt.url } : t));
        if (evt.tabId === activeTabId) setAddressInput(evt.url);
      }
    });
    return () => { if (off) off(); };
  }, [hasElectron, activeTabId, setTabs]);

  const switchTab = (id: string) => {
    setActiveTabId(id);
    if (hasElectron) purrcat.browserSwitchTab(id).catch(() => {});
  };

  const handleAddressSubmit = async () => {
    const url = addressInput.trim();
    if (!url) return;
    let finalUrl = url;
    if (!finalUrl.startsWith('http') && !finalUrl.startsWith('blob') && !finalUrl.startsWith('data')) {
      finalUrl = 'http://' + finalUrl;
    }
    if (activeTabId) {
      setTabs(tabs.map(t => t.id === activeTabId ? { ...t, url: finalUrl } : t));
      if (hasElectron) purrcat.browserNavigate(activeTabId, finalUrl).catch(() => {});
    } else if (hasElectron) {
      // 无标签页：新建一个并加载该网址
      let tabId = Date.now().toString();
      try {
        const pid = await purrcat.browserNewTab(finalUrl);
        if (pid) tabId = pid;
      } catch (_) {}
      setTabs(prev => [...prev, { id: tabId, url: finalUrl, title: '' }]);
      setActiveTabId(tabId);
    }
  };

  const closeTab = (id: string) => {
    if (hasElectron) purrcat.browserCloseTab(id).catch(() => {});
    const newTabs = tabs.filter(t => t.id !== id);
    setTabs(newTabs);
    if (activeTabId === id) {
      const next = newTabs.length > 0 ? newTabs[newTabs.length - 1].id : null;
      setActiveTabId(next);
      if (next && hasElectron) purrcat.browserSwitchTab(next).catch(() => {});
    }
    setMode('browse');
    setShowCommentBox(false);
    setCurrentRect(null);
    setHoverRect(null);
  };

  // 核心：无论外层怎么变，换算回1280x800的绝对逻辑坐标
  const getCoords = (e: React.MouseEvent) => {
    const el = logicalOverlayRef.current;
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect(); // 获取的是被 scale 缩放后的 DOM Rect
    return { 
      x: (e.clientX - rect.left) / viewScale, 
      y: (e.clientY - rect.top) / viewScale 
    };
  };

  const handleHover = (e: React.MouseEvent) => {
    if (mode !== 'pick' || showCommentBox) return;
    const now = Date.now();
    if (now - lastHoverRef.current < 120) return;
    lastHoverRef.current = now;
    const { x, y } = getCoords(e);
    if (!hasElectron || !activeTabId) return;
    purrcat.browserLocate(activeTabId, x, y).then((el: any) => {
      if (el && el.rect) setHoverRect({ x: el.rect.x, y: el.rect.y, w: el.rect.w, h: el.rect.h });
      else setHoverRect(null);
    }).catch(() => {});
  };

  const handleDown = (e: React.MouseEvent) => {
    if (showCommentBox) { setShowCommentBox(false); setCurrentRect(null); setPickedElement(null); return; }
    const { x, y } = getCoords(e);

    if (mode === 'pick') {
      if (!hasElectron || !activeTabId) return;
      purrcat.browserLocate(activeTabId, x, y).then((el: any) => {
        setPickedElement(el);
        setCurrentRect(el && el.rect ? { x: el.rect.x, y: el.rect.y, w: el.rect.w, h: el.rect.h } : { x: x - 5, y: y - 5, w: 10, h: 10 });
        setShowCommentBox(true);
        setHoverRect(null);
      }).catch(() => {});
      return;
    }

    if (mode === 'draw') {
      setIsDrawing(true);
      setStartPos({ x, y });
      setCurrentRect({ x, y, w: 0, h: 0 });
    }
  };

  const handleMove = (e: React.MouseEvent) => {
    if (mode === 'pick') { handleHover(e); return; }
    if (!isDrawing || mode !== 'draw') return;
    const { x, y } = getCoords(e);
    setCurrentRect({
      x: Math.min(startPos.x, x),
      y: Math.min(startPos.y, y),
      w: Math.abs(x - startPos.x),
      h: Math.abs(y - startPos.y)
    });
  };

  const handleUp = () => {
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
    const vw = VIEWPORT_W;
    const vh = VIEWPORT_H;
    const elementContext = pickedElement
      ? `DOM Tag: <${pickedElement.tag}${pickedElement.id ? ` id="${pickedElement.id}"` : ''}${pickedElement.cls ? ` class="${pickedElement.cls}"` : ''}>`
      : (mode === 'pick' ? 'User clicked specific coordinate' : 'User drawn area');
    onComment(
      { mode, rect: currentRect, domContext: elementContext, viewport: { width: vw, height: vh } },
      commentText,
      activeTab.url
    );
    setCommentText('');
    setShowCommentBox(false);
    setCurrentRect(null);
    setPickedElement(null);
    setHoverRect(null);
    setMode('browse');
  };

  const needsOverlay = mode === 'draw' || mode === 'pick';

  return (
    <div style={sketchyShape2} className="h-full bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col relative overflow-hidden">
      {/* 顶部标签栏、地址栏维持不变 ... */}
      <div className="flex bg-white p-2 gap-2 overflow-x-auto shrink-0">
        {tabs.map(tab => (
          <div key={tab.id} onClick={() => switchTab(tab.id)} className={`flex items-center gap-2 px-3 py-1.5 border-2 border-ink cursor-pointer min-w-[120px] max-w-[200px] transition-colors ${activeTabId === tab.id ? 'bg-cream text-ink font-bold shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]' : 'bg-sand text-ink/70 hover:bg-paper'}`} style={sketchyShape1}>
            <span className="truncate flex-1 text-xs">{tab.title || tab.url}</span>
            <button onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }} className={`p-0.5 rounded hover:bg-terracotta hover:text-paper ${activeTabId === tab.id ? 'text-ink' : 'text-ink/50'}`}><X size={12} strokeWidth={3} /></button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 p-3 border-b-4 border-ink bg-cream shrink-0 relative z-10">
        <div className="flex gap-2">
          <button onClick={() => setMode('browse')} className={`p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors ${mode === 'browse' ? 'bg-[#88c0d0] text-paper' : 'bg-white hover:bg-sand'}`} style={sketchyShape1} title="正常浏览"><Globe size={18} strokeWidth={3} /></button>
          <button onClick={() => { setMode('pick'); setShowCommentBox(false); setCurrentRect(null); setPickedElement(null); setHoverRect(null); }} className={`p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors ${mode === 'pick' ? 'bg-[#EBCB8B] text-ink' : 'bg-white hover:bg-sand'}`} style={sketchyShape3} title="元素选取"><MousePointer2 size={18} strokeWidth={3} /></button>
          <button onClick={() => { setMode('draw'); setShowCommentBox(false); setCurrentRect(null); setPickedElement(null); setHoverRect(null); }} className={`p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors ${mode === 'draw' ? 'bg-[#bf616a] text-paper' : 'bg-white hover:bg-sand'}`} style={sketchyShape2} title="自由画框"><Frame size={18} strokeWidth={3} /></button>
        </div>
        <input value={addressInput} onChange={e => setAddressInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAddressSubmit()} className="flex-1 border-4 border-ink bg-white px-3 py-1.5 font-bold focus:outline-none text-sm" style={sketchyShape3} placeholder="输入网址，回车访问..." />
        <button onClick={() => { const url = activeTab?.url || addressInput; if (url) window.open(url.startsWith('http') || url.startsWith('blob') || url.startsWith('data') ? url : 'http://' + url, '_blank'); }} disabled={!activeTabId} className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-white hover:bg-sand disabled:opacity-40 disabled:cursor-not-allowed" style={sketchyShape3} title="在外部浏览器中打开"><ExternalLink size={16} strokeWidth={3} /></button>
      </div>

      <div ref={containerRef} className="flex-1 relative overflow-hidden bg-[#e5e9f0]">
        {tabs.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#e5e9f0] z-50 text-ink/40">
            <Globe size={48} strokeWidth={2} className="mb-4" />
            <h2 className="text-xl font-black tracking-wider" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PurrCat Browser</h2>
            <p className="text-xs font-bold mt-1">Waiting for connection...</p>
          </div>
        ) : !hasElectron ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#e5e9f0] z-50 text-ink/40 p-8 text-center">
            <Globe size={48} strokeWidth={2} className="mb-4" />
            <p className="text-sm font-bold">内置浏览器仅在 PurrCat 桌面端可用</p>
          </div>
        ) : (
          <>
            {/* 绝对居中的 Letterbox 等比例包裹层 */}
            <div 
              className="absolute pointer-events-none"
              style={{
                left: viewOffset.x,
                top: viewOffset.y,
                width: VIEWPORT_W * viewScale,
                height: VIEWPORT_H * viewScale,
                overflow: 'hidden'
              }}
            >
              {/* 真正的 1280x800 逻辑映射区域，利用 CSS transform 同步原生缩放 */}
              <div
                ref={logicalOverlayRef}
                className="absolute origin-top-left pointer-events-auto"
                style={{
                  width: VIEWPORT_W,
                  height: VIEWPORT_H,
                  transform: `scale(${viewScale})`
                }}
              >
                {/* 必须使用 object-fill 因为我们已经确切规划好了比例 */}
                {needsOverlay && snapshot && (
                  <img src={snapshot} alt="" className="absolute inset-0 w-full h-full object-fill pointer-events-none" />
                )}

                {needsOverlay && (
                  <div
                    className="absolute inset-0 z-10 cursor-crosshair"
                    onMouseDown={handleDown}
                    onMouseMove={handleMove}
                    onMouseUp={handleUp}
                  />
                )}

                {mode === 'pick' && hoverRect && !showCommentBox && (
                  <div className="absolute border-2 border-[#EBCB8B] bg-[#EBCB8B]/15 pointer-events-none z-20" style={{ left: hoverRect.x, top: hoverRect.y, width: Math.max(hoverRect.w, 4), height: Math.max(hoverRect.h, 4) }} />
                )}

                {currentRect && (
                  <div
                    className={`absolute border-4 pointer-events-none z-20 ${mode === 'pick' ? 'border-[#EBCB8B] bg-[#EBCB8B]/20' : 'border-[#bf616a] bg-[#bf616a]/20'}`}
                    style={{ left: currentRect.x, top: currentRect.y, width: Math.max(currentRect.w, 8), height: Math.max(currentRect.h, 8), ...sketchyShape1 }}
                  >
                    {pickedElement && (
                      <div className="absolute -top-7 left-[-4px] bg-ink text-paper text-[10px] font-bold px-2 py-1 rounded-t flex items-center gap-1 whitespace-nowrap">
                        <Code2 size={10} />{pickedElement.tag}{pickedElement.cls && <span className="opacity-70">.{pickedElement.cls.split(' ')[0]}</span>}
                      </div>
                    )}
                  </div>
                )}

                {showCommentBox && currentRect && (
                  <div
                    className="absolute z-30 bg-paper border-4 border-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] p-3 pointer-events-auto"
                    style={{
                      width: 280,
                      left: Math.min(currentRect.x + currentRect.w + 10, VIEWPORT_W - 300),
                      top: Math.max(10, currentRect.y - 20),
                      ...sketchyShape2
                    }}
                  >
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-black text-sm text-terracotta tracking-wider">COMMAND</span>
                      <button onClick={() => { setShowCommentBox(false); setCurrentRect(null); setPickedElement(null); setHoverRect(null); setMode('browse'); }} className="hover:text-terracotta"><X size={16} strokeWidth={3} /></button>
                    </div>
                    <textarea autoFocus value={commentText} onChange={e => setCommentText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitComment(); } }} placeholder={pickedElement ? `修改 <${pickedElement.tag}> 元素...` : "要求 Agent 修改此处的..."} className="w-full bg-[#FDF8F0] border-2 border-ink p-2 text-sm font-bold resize-none h-20 focus:outline-none mb-2" style={sketchyShape3} />
                    <button onClick={submitComment} className="w-full bg-ink text-paper font-black py-2 flex justify-center items-center gap-2 hover:bg-terracotta hover:text-ink transition-colors border-2 border-ink" style={sketchyShape1}>
                      <Send size={14} strokeWidth={3} /> EXECUTE
                    </button>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}