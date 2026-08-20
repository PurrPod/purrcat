// src/components/DataSetupModal.tsx
// 首次启动数据盘引导：选一次数据盘（或使用默认位置）；日后可在配置中心随时更换
import { useEffect, useState } from 'react';
import { Folder, FolderRoot, HardDrive, Loader2 } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './chat/ChatShared';

export default function DataSetupModal({ onDone }: { onDone: () => void }) {
  const purrcat = (window as any).purrcat;
  const [defaultDir, setDefaultDir] = useState('~/.purrcat');
  const [selected, setSelected] = useState('');   // 用户选的数据盘；空 = 用默认位置
  const [submitting, setSubmitting] = useState(false);

  // 展示默认数据位置（~/.purrcat）
  useEffect(() => {
    fetch('/api/config/meta')
      .then((r) => r.json())
      .then((m) => { if (m?.PURRCAT_DIR) setDefaultDir(m.PURRCAT_DIR); })
      .catch(() => {});
  }, []);

  const pickDir = async () => {
    if (!purrcat?.openDialog) { toast('当前环境不支持选择文件夹', { icon: '🔔' }); return; }
    const dirs = await purrcat.openDialog({ directory: true });
    if (dirs && dirs.length > 0) setSelected(dirs[0]);
  };

  const submit = async (dataRoot: string) => {
    setSubmitting(true);
    try {
      const res = await fetch('/api/config/setup-data-root', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data_root: dataRoot }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success('数据盘设置成功，即将重启生效');
        onDone();
        // 让用户看到提示后自动重启，data_root 重启后才会真正生效
        setTimeout(() => {
          if (purrcat?.restartApp) purrcat.restartApp();
          else window.location.reload();
        }, 1500);
      } else {
        toast.error(typeof data?.detail === 'string' ? data.detail : '保存失败');
      }
    } catch {
      toast.error('网络错误，无法连接后端');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[2147483646] flex items-center justify-center bg-ink/80 backdrop-blur-sm p-4 md:p-8 pointer-events-auto">
      <div
        style={sketchyShape2}
        className="bg-cream border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-xl flex flex-col relative p-8 md:p-10"
      >
        <div
          className="absolute -top-5 right-10 w-28 h-12 bg-[#EBCB8B]/70 border-2 border-ink -rotate-3 z-50 pointer-events-none flex items-center justify-center font-black text-sm tracking-widest"
          style={sketchyShape1}
        >
          FIRST RUN
        </div>

        <div className="flex items-center gap-3 mb-4">
          <HardDrive size={40} strokeWidth={2.5} className="text-terracotta" />
          <h2 className="text-3xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>设置数据盘</h2>
        </div>

        <div className="text-[15px] font-bold text-ink/80 leading-relaxed mb-6">
          沙盒虚拟环境（agent_vm）、向量模型等<b className="text-ink">大文件</b>会存放在数据盘；
          对话记录、配置等<b className="text-ink">小数据固定在用户目录</b>。
          之后随时可以在配置中心更换数据盘（自动搬迁数据并重启）。
        </div>

        <div className="flex flex-col gap-4 mb-6">
          {/* 当前选择 */}
          <div style={sketchyShape1} className="bg-paper border-4 border-ink p-4 flex items-center gap-3">
            <FolderRoot size={24} strokeWidth={2.5} className={selected ? 'text-[#a3be8c]' : 'text-terracotta'} />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-black text-ink/50 tracking-widest mb-1">数据盘位置</div>
              <div className="font-mono text-[15px] font-bold text-ink break-all">
                {selected || defaultDir}
              </div>
            </div>
          </div>

          {/* 说明：可随时更换 */}
          <div className="flex items-start gap-2 text-xs font-bold text-ink/50">
            <span className="shrink-0">💡</span>
            设置完成后自动重启生效；日后如需更换，可在配置中心数据根目录旁点击铅笔图标。
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <button
            onClick={pickDir}
            disabled={submitting}
            style={sketchyShape1}
            className="flex items-center justify-center gap-2 px-6 py-3 bg-[#a3be8c] border-4 border-ink text-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] hover:-translate-y-0.5 active:translate-y-1 active:shadow-none transition-all"
          >
            <Folder size={20} strokeWidth={3} />
            选择数据盘…
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={() => submit(selected || defaultDir)}
              disabled={submitting}
              style={sketchyShape3}
              className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-paper border-4 border-ink text-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:-translate-y-0.5 active:translate-y-1 active:shadow-none transition-all"
            >
              {submitting ? <Loader2 size={20} strokeWidth={3} className="animate-spin" /> : null}
              {submitting ? '保存中…' : '使用该位置'}
            </button>
            <button
              onClick={() => submit(defaultDir)}
              disabled={submitting}
              style={sketchyShape2}
              className="flex-1 px-6 py-3 bg-paper border-4 border-ink text-ink/70 font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:text-ink hover:-translate-y-0.5 active:translate-y-1 active:shadow-none transition-all"
            >
              使用默认位置
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
