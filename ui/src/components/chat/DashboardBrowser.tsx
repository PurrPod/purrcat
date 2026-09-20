// components/chat/DashboardBrowser.tsx
// 🌟 Dashboard 专用"内部浏览器预览"：零工具栏，铺满容器用 Electron WebContentsView 渲染真实页面。
// 复用聊天页内部浏览器的修 view 能力（bounds 同步 / 导航 / 遮挡安全），去掉全部按钮与模式。
import { useEffect, useRef } from 'react';
import { Globe } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useTranslation } from '../../i18n';

interface DashboardBrowserProps {
  url: string | null;        // 当前要展示的看板地址；变化时在同一 view 内导航
}

export default function DashboardBrowser({ url }: DashboardBrowserProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const tabIdRef = useRef<string | null>(null);
  const urlRef = useRef(url);
  urlRef.current = url;

  const purrcat = (window as any).purrcat;
  const hasElectron = !!purrcat?.browserNewTab;

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

  // bounds 同步：把原生 view 精确铺满容器（scale=1，CSS 视口=容器尺寸，页随容器重排，无留白/溢出）
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

  // 主进程导航被拦截（如打开应用自身地址）时提示
  useEffect(() => {
    if (!hasElectron) return;
    const off = purrcat.onTabEvent((evt: any) => {
      if (evt.type === 'blocked') {
        toast.error(evt.reason || t('chat.selfUrlBlocked'));
      }
    });
    return () => { if (off) off(); };
  }, [hasElectron, purrcat, t]);

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
      ref={containerRef}
      className="h-full w-full relative overflow-hidden bg-[#FDF8F0]"
      style={{ borderRadius: '22px 12px 20px 14px/14px 20px 12px 22px', boxShadow: 'inset 0 0 2px 0 rgba(26,26,26,0.15)' }}
    />
  );
}