// 应用级提醒弹窗：插件通过 dialog.message 唤起，定时器用它提醒未绑定的事项
import { syncNativeCover } from './bus.js';
import { HOST } from './state.js';

  export interface NoticeOption {
    id: string;
    label: string;
    kind?: 'primary' | 'danger';
  }

  export interface NoticeSpec {
    title: string;
    description?: string;
    options?: NoticeOption[];
    dismissible?: boolean;
  }

  function fmtHHMM(minutes: number): string {
    const m = Math.max(0, Math.floor(minutes));
    return String(Math.floor(m / 60) % 24).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
  }

  // 展示宿主的模态提醒；resolve 为被选中的 option.id，取消/关闭为 null。
  export function showNotice(spec: NoticeSpec): Promise<string | null> {
    const doc = HOST.document;
    const options = (spec.options || []).filter((o) => o && o.id && o.label);
    if (!options.length) options.push({ id: 'ok', label: '知道了' });

    const wrap = doc.createElement('div');
    wrap.className = 'wm-modal-wrap wm-notice-wrap';
    wrap.style.display = 'flex';
    const box = doc.createElement('div');
    box.className = 'wm-notice';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    const title = doc.createElement('div');
    title.className = 'wm-notice-title';
    title.textContent = spec.title || '提醒';
    box.appendChild(title);
    if (spec.description) {
      const desc = doc.createElement('div');
      desc.className = 'wm-notice-desc';
      desc.textContent = spec.description;
      box.appendChild(desc);
    }
    const actions = doc.createElement('div');
    actions.className = 'wm-notice-actions';
    box.appendChild(actions);
    wrap.appendChild(box);

    return new Promise((resolve) => {
      let done = false;
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && spec.dismissible !== false) close(null);
      };
      const close = (value: string | null) => {
        if (done) return;
        done = true;
        doc.removeEventListener('keydown', onKey, true);
        wrap.remove();
        syncNativeCover();
        resolve(value);
      };
      options.forEach((opt) => {
        const btn = doc.createElement('button');
        btn.type = 'button';
        btn.className = 'wm-notice-btn' + (opt.kind ? ' is-' + opt.kind : '');
        btn.textContent = opt.label;
        btn.addEventListener('click', () => close(opt.id));
        actions.appendChild(btn);
      });
      if (spec.dismissible !== false) {
        wrap.addEventListener('click', (e) => { if (e.target === wrap) close(null); });
        doc.addEventListener('keydown', onKey, true);
      }
      doc.body.appendChild(wrap);
      syncNativeCover();
      const focusTarget = actions.lastElementChild as HTMLElement | null;
      if (focusTarget) focusTarget.focus();
    });
  }

  async function remindNote(data: Record<string, any>): Promise<string | null> {
    const start = Number(data.start);
    const time = Number.isFinite(start) ? fmtHHMM(start) : '';
    const desc = String(data.description || '').trim();
    return showNotice({
      title: '⏰ ' + (time ? time + ' · ' : '') + String(data.title || '随手记事项'),
      description: (desc || '时间到了，该做这件事了。') + (data.date ? '\n' + data.date : ''),
      options: [
        { id: 'open', label: '打开随手记' },
        { id: 'ok', label: '知道了', kind: 'primary' },
      ],
    });
  }

  // 未绑定 Worker 的随手记事项到点后，由宿主弹应用级提醒（不依赖随手记面板是否打开）。
  export function startTimerReminders(openPlugin?: (pluginId: string) => void) {
    if (typeof EventSource !== 'function') return;
    const seen = new Set<string>();
    let source: EventSource;
    try {
      source = new EventSource('/api/timer/stream');
    } catch (_) {
      return;
    }
    source.addEventListener('timer', (e: MessageEvent) => {
      let payload: any;
      try { payload = JSON.parse(e.data); } catch (_) { return; }
      if (!payload || payload.type !== 'fired') return;
      const evt = payload.event || {};
      if (String(evt.target || '') !== 'ui:note') return;
      const effect = evt.effect || {};
      if (effect.signal && effect.signal !== 'note_item') return;
      const key = String(evt.id || '') + '|' + String(evt.at || '');
      if (seen.has(key)) return;
      seen.add(key);
      if (seen.size > 200) {
        const oldest = seen.values().next().value;
        if (oldest) seen.delete(oldest);
      }
      remindNote(effect.payload || {}).then((choice) => {
        if (choice === 'open' && openPlugin) openPlugin('builtin-note');
      });
    });
  }
