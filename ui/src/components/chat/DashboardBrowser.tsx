// components/chat/DashboardBrowser.tsx
// 🌟 Dashboard 专用"内部浏览器预览"：顶部折叠导航条 + 铺满容器用 Electron WebContentsView 渲染真实页面。
// 复用聊天页内部浏览器的 view 能力（bounds 同步 / 导航 / 遮挡安全），保留简洁的前进后退/刷新/地址栏/外部打开。
import { useEffect, useRef, useState } from 'react';
import { Globe, ArrowLeft, ArrowRight, RotateCw, ExternalLink } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useTranslation } from '../../i18n';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

interface DashboardBrowserProps {
  url: string | null;        // 当前要展示的看板地址；变化时在同一 view 内导航
}

export default function DashboardBrowser({ url }: DashboardBrowserProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const tabIdRef = useRef<string | null>(null);
  const urlRef = useRef(url);
  urlRef.current = url;

  // 当前真实加载地址（由主进程 navigate 事件驱动），地址栏据此回显
  const [currentUrl, setCurrentUrl] = useState('');
  const [addressDraft, setAddressDraft] = useState('');

  const purrcat = (window as any).purrcat;
  const hasElectron = !!purrcat?.browserNewTab;

  // navigate 事件把当前地址回填到地址栏
  useEffect(() => { setAddressDraft(currentUrl); }, [currentUrl]);

  const normalize = (u: string) => (/^\w+:\/\//.test(u) ? u : 'http://' + u);

  // 建 Tab 并铺满容器（Letterbox 等比，固定 1280×800 逻辑视口）
  useEffect(() => {
    if (!hasElectron) return;
    let cancelled = false;

    (async () => {
      const initialUrl = urlRef.current;
      let id: string | null = null;
      try {
        id = (await purrcat.browserNewTab(initialUrl || '')) || null;
      } catch { /* 主进程异常 */ }
      if (cancelled) return;
      tabIdRef.current = id;
      // 🌟 建 tab 完成后立刻触发一遍 bounds 同步：否则新 view 仍是 OFFSCREEN，出现摆放错乱/溢出
      if (id) window.dispatchEvent(new Event('purrcat-browser-force-sync'));
    })();

    return () => {
      cancelled = true;
      const id = tabIdRef.current;
      try { purrcat.browserHide(); } catch { /* ignore */ }
      if (id) { try { purrcat.browserCloseTab(id, null); } catch { /* ignore */ } }
      tabIdRef.current = null;
    };
  }, [hasElectron, purrcat]);

  // 地址变化：在同一 view 内导航，不发新的 Tab
  useEffect(() => {
    if (!hasElectron || !url) return;
    if (tabIdRef.current) {
      purrcat.browserNavigate(tabIdRef.current, url).catch(() => {});
    }
  }, [url, hasElectron, purrcat]);

  // bounds 同步：把原生 view 精确铺满 view 区域（scale=1，CSS 视口=区域尺寸，页随区域重排，无留白/溢出）
  useEffect(() => {
    if (!hasElectron) return;
    let disposed = false;
    let debounceTimer: number | null = null;

    const sync = () => {
      if (disposed) return;
      const el = containerRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (r.width <= 50 || r.height <= 50 || r.width > 4000 || r.height > 4000) return;

      // 🌟 内缩 INSET：原生 view 角必须退到圆角切割线以内才不会"尖角探出圆角框"。
      //    Electron 31 的 WebContentsView 无法 setBorderRadius，只能用内缩让直角藏进圆角纸边
      const INSET = 16;
      if (debounceTimer) window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        if (disposed) return;
        purrcat.browserSetBounds(
          Math.round(r.left + INSET),
          Math.round(r.top + INSET),
          Math.round(r.width - INSET * 2),
          Math.round(r.height - INSET * 2),
          1
        ).catch(() => {});
      }, 10);
    };

    const firstTimer = window.setTimeout(sync, 60);
    const ro = new ResizeObserver(sync);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener('resize', sync);
    window.addEventListener('purrcat-browser-force-sync', sync);

    return () => {
      disposed = true;
      window.clearTimeout(firstTimer);
      if (debounceTimer) window.clearTimeout(debounceTimer);
      ro.disconnect();
      window.removeEventListener('resize', sync);
      window.removeEventListener('purrcat-browser-force-sync', sync);
    };
  }, [hasElectron, purrcat]);

  // 主进程导航事件：拦截解码 + 当前地址回显
  useEffect(() => {
    if (!hasElectron) return;
    const off = purrcat.onTabEvent((evt: any) => {
      if (evt.type === 'blocked') {
        toast.error(evt.reason || t('chat.selfUrlBlocked'));
      } else if (evt.type === 'navigate' && tabIdRef.current && evt.tabId === tabIdRef.current) {
        setCurrentUrl(evt.url || '');
      }
    });
    return () => { if (off) off(); };
  }, [hasElectron, purrcat, t]);

  // ---- 导航条动作 ----
  const goBack = () => {
    const id = tabIdRef.current;
    if (id && purrcat?.browserGoBack) purrcat.browserGoBack(id).catch(() => {});
  };
  const goForward = () => {
    const id = tabIdRef.current;
    if (id && purrcat?.browserGoForward) purrcat.browserGoForward(id).catch(() => {});
  };
  const reload = () => {
    const id = tabIdRef.current;
    if (id && purrcat?.browserReload) purrcat.browserReload(id).catch(() => {});
  };
  const goAddress = () => {
    const u = addressDraft.trim();
    if (!u) return;
    const id = tabIdRef.current;
    if (id && purrcat?.browserNavigate) purrcat.browserNavigate(id, normalize(u)).catch(() => {});
  };
  const openExternal = () => {
    const u = currentUrl || addressDraft.trim();
    if (!u) return;
    const finalUrl = normalize(u);
    if (purrcat?.openExternal) purrcat.openExternal(finalUrl);
    else window.open(finalUrl, '_blank');
  };

  // 非 Electron（纯 Web）环境：无法用原生 WebContentsView
  if (!hasElectron) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center bg-[#e5e9f0] text-ink/40">
        <Globe size={48} strokeWidth={2} className="mb-4" />
        <p className="text-sm font-bold">{t('chat.desktopOnly')}</p>
      </div>
    );
  }

  return (
    // 🌟 bg 用纸面底 + 歪切圆角：原生 view 内缩后，边缘是一圈同色纸面圆角框，
    //    既能藏住 view 的矩角、又能让边界融入容器（"嵌入 + 虚化"感）
    <div
      className="h-full w-full flex flex-col overflow-hidden bg-[#FDF8F0]"
      style={{ borderRadius: '22px 12px 20px 14px/14px 20px 12px 22px', boxShadow: 'inset 0 0 2px 0 rgba(26,26,26,0.15)' }}
    >
      {/* 🌟 顶部折叠导航条：后退/前进/刷新 + 地址栏 + 外部打开 */}
      <div className="flex items-center gap-2 p-2 bg-paper border-b-4 border-ink shrink-0 relative z-10">
        <button onClick={goBack} disabled={!tabIdRef.current} className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-white hover:bg-sand disabled:opacity-40 disabled:cursor-not-allowed" style={sketchyShape1} title="后退">
          <ArrowLeft size={16} strokeWidth={3} />
        </button>
        <button onClick={goForward} disabled={!tabIdRef.current} className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-white hover:bg-sand disabled:opacity-40 disabled:cursor-not-allowed" style={sketchyShape2} title="前进">
          <ArrowRight size={16} strokeWidth={3} />
        </button>
        <button onClick={reload} disabled={!tabIdRef.current} className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-white hover:bg-sand disabled:opacity-40 disabled:cursor-not-allowed" style={sketchyShape3} title="刷新">
          <RotateCw size={16} strokeWidth={3} />
        </button>
        <input
          value={addressDraft}
          onChange={(e) => setAddressDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') goAddress(); }}
          className="flex-1 border-4 border-ink bg-white px-3 py-1.5 font-bold focus:outline-none text-sm min-w-0"
          style={sketchyShape3}
          placeholder="输入网址，回车打开"
        />
        <button onClick={openExternal} disabled={!currentUrl} className="p-2 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors bg-white hover:bg-sand disabled:opacity-40 disabled:cursor-not-allowed" style={sketchyShape1} title="在外部浏览器打开">
          <ExternalLink size={16} strokeWidth={3} />
        </button>
      </div>

      {/* 下部 view 区域：原生 view 只铺这里，导航条保持 HTML 不被盖住 */}
      <div ref={containerRef} className="flex-1 relative overflow-hidden bg-[#FDF8F0]" />
    </div>
  );
}