import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MousePointer2, Frame, Globe, Send, X, Code2, ExternalLink, PictureInPicture2 } from 'lucide-react';
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
  onDetach: () => void;
}

export default function AgentBrowserPanel({
  tabs, setTabs, activeTabId, setActiveTabId,
  mode, setMode, onComment, onDetach
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
  // pick 模式下后端返回的 CSS viewport 尺寸（和当前浏览器浏览时的实际视口一致，不再固定 1280×800）
  // browse 模式时忽略，使用 VIEWPORT_W/H（browse 模式用 CDP Overlay 原生高亮不需要截图坐标系）
  const [pickViewport, setPickViewport] = useState<{ w: number; h: number } | null>(null);

  const purrcat = (window as any).purrcat;
  const hasElectron = !!purrcat?.browserNewTab;

  // 🌟 动态逻辑视口：browse 模式固定基准 1280×800（CDP Overlay 原生高亮不依赖坐标系）
  // pick/draw 模式使用后端返回的 viewportCss(W,H)，和浏览时 live viewport 1:1 对齐
  const VP_W = mode === 'browse' ? VIEWPORT_W : (pickViewport?.w || VIEWPORT_W);
  const VP_H = mode === 'browse' ? VIEWPORT_H : (pickViewport?.h || VIEWPORT_H);
  // sync() 注册在初始化时，需要随时取最新 VP_W/VP_H，用 ref 穿透闭包
  const viewportRef = useRef({ w: VP_W, h: VP_H });
  viewportRef.current = { w: VP_W, h: VP_H };

  const activeTab = tabs.find(t => t.id === activeTabId);

  useEffect(() => {
    if (activeTab) setAddressInput(activeTab.url);
  }, [activeTabId, activeTab]);

  // bounds 同步：保证前端等比例缩放 (Letterbox)，并带缩放比例给主进程
  useEffect(() => {
    if (!hasElectron) return;
    let disposed = false;
    let debounceTimer: number | null = null;

    const sync = () => {
      if (disposed) return;
      const el = containerRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();

      // 过滤无效或异常的极端尺寸（如窗口最小化/恢复瞬间测出的 0 或超大值）
      if (r.width <= 50 || r.height <= 50 || r.width > 4000 || r.height > 4000) return;

      // 附加合理性检查：容器必须占主窗口可视区域的合理比例
      const vw = typeof window !== 'undefined' ? window.innerWidth : 1280;
      const vh = typeof window !== 'undefined' ? window.innerHeight : 800;
      if (r.width < vw * 0.15 || r.height < vh * 0.15) return;

      const { w: VP_W, h: VP_H } = viewportRef.current;
      const targetRatio = VP_W / VP_H;
      const currentRatio = r.width / r.height;
      let s = 1;
      let scaledW = r.width;
      let scaledH = r.height;
      let offsetX = 0;
      let offsetY = 0;

      if (currentRatio > targetRatio) {
        s = r.height / VP_H;
        scaledW = VP_W * s;
        offsetX = (r.width - scaledW) / 2;
      } else {
        s = r.width / VP_W;
        scaledH = VP_H * s;
        offsetY = (r.height - scaledH) / 2;
      }

      // 安全 Clamp：限制缩放倍数在 0.2 ~ 2.0 之间，防止 GPU 崩溃 + 内容缩到看不清
      s = Math.min(Math.max(s, 0.2), 2.0);

      setViewScale(s);
      setViewOffset({ x: offsetX, y: offsetY });

      const screenW = typeof window !== 'undefined' && window.screen ? window.screen.width : 2560;
      const screenH = typeof window !== 'undefined' && window.screen ? window.screen.height : 1440;
      const safeW = Math.min(Math.round(scaledW), screenW);
      const safeH = Math.min(Math.round(scaledH), screenH);

      // 前端 debounce：合并 ResizeObserver + window.resize 的抖动
      if (debounceTimer) window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        if (disposed) return;
        purrcat.browserSetBounds(
          Math.round(r.left + offsetX),
          Math.round(r.top + offsetY),
          safeW,
          safeH,
          s
        );
      }, 10);
    };

    // 首次挂载延迟 50ms 执行，保证 React DOM 布局已稳定，
    // 避免首次测量值极小 → scale clamp 到 0.1 导致内容暴缩
    const firstTimer = window.setTimeout(sync, 50);

    const ro = new ResizeObserver(sync);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener('resize', sync);
    // 独立窗口合并回主窗口时，ChatPage 会派发 force-sync 事件要求立刻同步 bounds
    window.addEventListener('purrcat-browser-force-sync', sync);
    return () => {
      disposed = true;
      window.clearTimeout(firstTimer);
      if (debounceTimer) window.clearTimeout(debounceTimer);
      ro.disconnect();
      window.removeEventListener('resize', sync);
      window.removeEventListener('purrcat-browser-force-sync', sync);
    };
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
      setPickViewport(null);
      // 回到 browse 模式时确保 CDP Overlay 已开启（后续 hover 会 highlight）
    } else {
      // 进入 pick/draw 模式，清除 CDP Overlay（view 已被 hide，overlay 无意义）
      if (purrcat?.browserCdpUnhighlight) purrcat.browserCdpUnhighlight(activeTabId).catch(() => {});
      purrcat.browserPickStart(activeTabId).then((res: any) => {
        if (cancelled) return;
        setSnapshot(res?.imageDataUrl || null);
        // 🌟 读取后端返回的 viewportCss(W,H) 作为当前 pick 模式的逻辑坐标系
        // 这和 browse 时 Chromium 的 CSS viewport 1:1 对齐，所以画面和 locate/rect 完全匹配
        if (res && res.viewportCssWidth && res.viewportCssHeight) {
          setPickViewport({ w: res.viewportCssWidth, h: res.viewportCssHeight });
        } else if (res && res.width && res.height) {
          // 老版本回退
          setPickViewport({ w: res.width, h: res.height });
        }
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

  // 🌟 核心换算：统一"屏幕物理像素 → 1280x800 逻辑坐标（CSS 视口坐标）"
  // 坐标系真相（任何缩放都不会变）：
  //   - WebContentsView 内部 CSS 视口恒 = 1280x800
  //       · browse 模式：bounds=1280s×800s, zoomFactor=s → CSS 视口=(1280s)/s=1280
  //       · pick   模式：bounds=1280×800,   zoomFactor=1 → CSS 视口=1280
  //   - 前端 logicalOverlayRef 内部坐标：1280x800（再经 transform:scale(s) 渲染到屏幕）
  //   - CDP DOM.getNodeForLocation / elementFromPoint / getBoundingClientRect
  //     全部使用"CSS 视口坐标"，也就是我们的 1280x800 逻辑坐标
  // 所以：所有进出 IPC 的 x/y 必须统一换算到 1280x800 空间，绝对不能再乘/除一次 scale！
  const toLogicalCoords = useCallback((clientX: number, clientY: number) => {
    const el = logicalOverlayRef.current;
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect(); // 已被 scale 后的屏幕像素矩形
    return {
      x: (clientX - rect.left) / viewScale,
      y: (clientY - rect.top) / viewScale,
    };
  }, [viewScale]);

  // React 事件版：pick/draw 模式下 pointer-events=auto 时调用
  const getCoords = (e: React.MouseEvent) => toLogicalCoords(e.clientX, e.clientY);

  const handleHover = (e: React.MouseEvent) => {
    if (showCommentBox) return;
    const now = Date.now();
    if (now - lastHoverRef.current < 120) return;
    lastHoverRef.current = now;
    const { x, y } = getCoords(e);
    if (!hasElectron || !activeTabId) return;

    // pick 模式：view 被隐藏 + 使用截图背景，用 React 自己画 hover 框
    if (mode === 'pick') {
      purrcat.browserLocate(activeTabId, x, y).then((el: any) => {
        if (el && el.rect) setHoverRect({ x: el.rect.x, y: el.rect.y, w: el.rect.w, h: el.rect.h });
        else setHoverRect(null);
      }).catch(() => {});
      return;
    }

    // browse 模式：view 可见，使用 CDP Overlay 原生高亮（零偏差）
    if (mode === 'browse' && purrcat?.browserCdpHighlight) {
      purrcat.browserCdpHighlight(activeTabId, x, y).catch(() => {});
    }
  };

  // browse 模式鼠标离开 overlay 时清除 CDP Overlay
  const handleHoverLeave = () => {
    if (mode !== 'browse') return;
    if (!hasElectron || !activeTabId) return;
    if (purrcat?.browserCdpUnhighlight) {
      purrcat.browserCdpUnhighlight(activeTabId).catch(() => {});
    }
  };

  const handleDown = (e: React.MouseEvent) => {
    if (showCommentBox) { setShowCommentBox(false); setCurrentRect(null); setPickedElement(null); return; }
    const { x, y } = getCoords(e);

    if (mode === 'pick') {
      if (!hasElectron || !activeTabId) return;
      // 点击拾取：优先用 CDP 方案提取完整语义信息，fallback 到 browserLocate
      const cdpFn = purrcat?.browserCdpPickElement;
      if (cdpFn) {
        cdpFn(activeTabId, x, y).then((el: any) => {
          if (el) {
            setPickedElement(el);
            setCurrentRect(el.rect ? { x: el.rect.x, y: el.rect.y, w: el.rect.w, h: el.rect.h } : { x: x - 5, y: y - 5, w: 10, h: 10 });
            setShowCommentBox(true);
            setHoverRect(null);
          }
        }).catch(() => {});
      } else {
        purrcat.browserLocate(activeTabId, x, y).then((el: any) => {
          setPickedElement(el);
          setCurrentRect(el && el.rect ? { x: el.rect.x, y: el.rect.y, w: el.rect.w, h: el.rect.h } : { x: x - 5, y: y - 5, w: 10, h: 10 });
          setShowCommentBox(true);
          setHoverRect(null);
        }).catch(() => {});
      }
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

  // browse 模式 hover：用 window 级 mousemove 监听（capture 阶段），不拦截网页交互
  // 因为 browse 模式下 overlay 的 pointer-events=none，React onMouseMove 永远不会触发
  useEffect(() => {
    if (!hasElectron || !purrcat?.browserCdpHighlight || mode !== 'browse' || !activeTabId) return;
    const onMove = (e: MouseEvent) => {
      const el = logicalOverlayRef.current;
      if (!el) return;
      const now = Date.now();
      if (now - lastHoverRef.current < 120) return;
      // 只在鼠标位于容器范围内时才 highlight
      const r = el.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) {
        lastHoverRef.current = now;
        purrcat.browserCdpUnhighlight!(activeTabId).catch(() => {});
        return;
      }
      lastHoverRef.current = now;
      // 🌟 复用统一换算函数：屏幕像素 → 1280x800 CSS 视口坐标
      // CDP Overlay.highlightNode 需要的正是 CSS 视口坐标，因此直接传
      const { x, y } = toLogicalCoords(e.clientX, e.clientY);
      purrcat.browserCdpHighlight!(activeTabId, x, y).catch(() => {});
    };
    window.addEventListener('mousemove', onMove, true);
    return () => {
      window.removeEventListener('mousemove', onMove, true);
      if (purrcat?.browserCdpUnhighlight) purrcat.browserCdpUnhighlight(activeTabId).catch(() => {});
    };
  }, [mode, activeTabId, hasElectron, viewScale, toLogicalCoords]);

  const submitComment = () => {
    if (!commentText.trim() || !currentRect || !activeTab) return;
    const vw = VP_W;
    const vh = VP_H;
    // 组装 Agent 可读的元素语义上下文
    // CDP 方案返回 tagName/attributes/outerHTML/innerText/cssSelector
    // 旧方案返回 tag/id/cls
    let elementContext: string;
    if (pickedElement) {
      if (pickedElement.outerHTML) {
        // CDP 方案：完整语义
        const parts: string[] = [];
        parts.push(`Element: <${pickedElement.tagName}>`);
        if (pickedElement.innerText) parts.push(`Text: "${pickedElement.innerText.trim().substring(0, 200)}"`);
        if (pickedElement.cssSelector) parts.push(`CSS Selector: ${pickedElement.cssSelector}`);
        parts.push(`HTML: ${pickedElement.outerHTML.substring(0, 500)}`);
        elementContext = parts.join('\n');
      } else {
        // 旧方案 fallback
        elementContext = `DOM Tag: <${pickedElement.tag || pickedElement.tagName}${pickedElement.id ? ` id="${pickedElement.id}"` : ''}${pickedElement.cls ? ` class="${pickedElement.cls}"` : ''}>`;
      }
    } else {
      elementContext = mode === 'pick' ? 'User clicked specific coordinate' : 'User drawn area';
    }
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
        {hasElectron && <button onClick={onDetach} disabled={!activeTabId} className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-[#88c0d0] text-paper hover:bg-[#5e81ac] disabled:opacity-40 disabled:cursor-not-allowed" style={sketchyShape3} title="独立窗口"><PictureInPicture2 size={16} strokeWidth={3} /></button>}
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
                width: VP_W * viewScale,
                height: VP_H * viewScale,
                overflow: 'hidden'
              }}
            >
              {/* 动态逻辑尺寸映射区域：browse=1280×800 / pick=live viewportCss(W,H) */}
              <div
                ref={logicalOverlayRef}
                className={`absolute origin-top-left ${needsOverlay ? 'pointer-events-auto' : ''}`}
                style={{
                  width: VP_W,
                  height: VP_H,
                  transform: `scale(${viewScale})`,
                  pointerEvents: needsOverlay ? 'auto' : 'none',
                }}
                onMouseMove={needsOverlay ? undefined : handleHover}
                onMouseLeave={needsOverlay ? undefined : handleHoverLeave}
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
                        <Code2 size={10} />{pickedElement.tagName || pickedElement.tag}{pickedElement.innerText ? <span className="opacity-70 max-w-[120px] truncate">"{pickedElement.innerText.substring(0, 30)}"</span> : <span className="opacity-70">{pickedElement.cls ? `.${pickedElement.cls.split(' ')[0]}` : ''}</span>}
                      </div>
                    )}
                  </div>
                )}

                {showCommentBox && currentRect && (
                  <div
                    className="absolute z-30 bg-paper border-4 border-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] p-3 pointer-events-auto"
                    style={{
                      width: 280,
                      left: Math.min(currentRect.x + currentRect.w + 10, VP_W - 300),
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