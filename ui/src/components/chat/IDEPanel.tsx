import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { toast } from 'react-hot-toast';
import { TerminalSquare, X, FolderOpen, BookOpen, Save, Plus, PictureInPicture2, Eye, Code2, FileImage, FileVideo, AlertCircle, FileDiff, FolderTree, Check, Undo2 } from 'lucide-react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { sketchyShape1, sketchyShape2, sketchyShape3, MarkdownComponents, safeDecodeUri } from './ChatShared';

interface IDEPanelProps {
  workspacePath: string;
  onClose: () => void;
  // md 预览中链接点击的统一路由（ChatPage 注入：http→内置浏览器 / 本地文件→对应预览）
  onOpenLink?: (href: string) => void;
}

type FileNode = {
  name: string;
  isDir: boolean;
  path?: string;
  children?: FileNode[];
  expanded?: boolean;
};

// 文件类型判断
const IMAGE_EXTS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp', '.ico', '.avif']);
const VIDEO_EXTS = new Set(['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv']);
const BINARY_EXTS = new Set([
  '.exe', '.dll', '.so', '.dylib', '.bin', '.dat', '.db', '.sqlite', '.zip', '.tar',
  '.gz', '.rar', '.7z', '.woff', '.woff2', '.ttf', '.otf', '.eot', '.class', '.o',
  '.pyc', '.pyd', '.pdb', '.obj', '.wasm', '.pdf', '.doc', '.docx', '.xls', '.xlsx',
  '.ppt', '.pptx', '.ico',
]);
const TEXT_EXTS = new Set([
  '.txt', '.md', '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml',
  '.toml', '.ini', '.cfg', '.conf', '.sh', '.bash', '.zsh', '.fish', '.bat', '.ps1',
  '.css', '.scss', '.less', '.html', '.htm', '.xml', '.svg', '.rs', '.go', '.java',
  '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.pl', '.r', '.sql', '.graphql',
  '.vue', '.svelte', '.dockerfile', '.gitignore', '.env', '.log', '.csv',
]);

type FileType = 'text' | 'image' | 'video' | 'binary' | 'markdown';

function getFileType(filePath: string): FileType {
  const ext = '.' + (filePath.split('.').pop() || '').toLowerCase();
  if (IMAGE_EXTS.has(ext)) return 'image';
  if (VIDEO_EXTS.has(ext)) return 'video';
  if (ext === '.md' || ext === '.markdown') return 'markdown';
  if (BINARY_EXTS.has(ext)) return 'binary';
  if (TEXT_EXTS.has(ext)) return 'text';
  // 未知扩展名尝试当文本
  return 'text';
}

// 生成文件预览 URL（走后端 /api/filesystem/preview 代理）
function getPreviewUrl(filePath: string): string {
  return `/api/filesystem/preview?path=${encodeURIComponent(filePath)}`;
}

// 大文件拦截：文本文件超过此大小不打开（10万行 CSV 直接卡死的教训）
const MAX_TEXT_FILE_SIZE = 2 * 1024 * 1024; // 2MB

// 格式化文件大小
function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

// ===== File Changes（数据源同 ChatPage 的 FileChangesPanel：/api/filesystem/diffs）=====
type FileChangeItem = {
  id: string;
  path: string;
  rel?: string; // 相对 workspace 的展示路径
  change_type: 'created' | 'deleted' | 'modified';
  diff: string;
  oldest_backup_id: string;
  newest_backup_id: string;
};

// unified diff 行类型（oldNo/newNo：变更前/当前文件的行号，1-based；del 行无 newNo，add 行无 oldNo）
type FullDiffLine = { type: 'add' | 'del' | 'ctx'; text: string; oldNo?: number; newNo?: number };

// 整文件 diff 视图：以「当前文件内容」为骨架，把删除行插回原位（红）、新增行绿色、其余正常
// 结果是完整文件而非 diff 片段（Trae/Codex 风格，无 @@/+/- 符号），并携带连续的 old/new 侧行号
function buildFullDiffView(diffText: string, currentContent: string): FullDiffLine[] {
  const out: FullDiffLine[] = [];
  if (!diffText) return out;
  const newLines = currentContent.split('\n');
  // 文件以 \n 结尾时 split 会多出末尾空串，若 diff 没有对应的末尾标记则去掉
  if (newLines.length > 0 && newLines[newLines.length - 1] === '' && !diffText.includes('\\ No newline')) newLines.pop();
  const lines = diffText.split('\n');
  let pointer = 0; // 指向 newLines 中尚未消费的位置
  let oldNo = 1, newNo = 1; // old/new 侧行号计数器（整文件连续推进，行号即真实行号）
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (!m) continue; // 跳过 ---/+++ 头等
    const newStart = parseInt(m[1], 10);
    // 收集本 hunk 的行，并统计 new 侧行数（ctx+add）
    const hunk: FullDiffLine[] = [];
    let newCount = 0;
    let j = i + 1;
    while (j < lines.length && !lines[j].startsWith('@@')) {
      const l = lines[j];
      if (l.startsWith('+')) { hunk.push({ type: 'add', text: l.slice(1), newNo: newNo++ }); newCount++; }
      else if (l.startsWith('-')) hunk.push({ type: 'del', text: l.slice(1), oldNo: oldNo++ });
      else if (l.startsWith('\\')) { /* "\ No newline at end of file" 忽略 */ }
      else { hunk.push({ type: 'ctx', text: l.replace(/^ /, ''), oldNo: oldNo++, newNo: newNo++ }); newCount++; }
      j++;
    }
    // hunk 之前的未变更区域从当前文件内容补齐
    const s = Math.max(0, newStart - 1);
    while (pointer < s && pointer < newLines.length) {
      out.push({ type: 'ctx', text: newLines[pointer], oldNo: oldNo++, newNo: newNo++ });
      pointer++;
    }
    out.push(...hunk);
    pointer = s + newCount;
    i = j - 1;
  }
  // hunk 之后的剩余未变更区域
  while (pointer < newLines.length) {
    out.push({ type: 'ctx', text: newLines[pointer], oldNo: oldNo++, newNo: newNo++ });
    pointer++;
  }
  return out;
}

// 判断 diff 路径（可能是 /agent_vm 沙盒路径或绝对路径）与 IDE 中的真实路径是否同一文件
function isSameFilePath(a: string, b: string, workspace: string): boolean {
  const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+/g, '/').toLowerCase().replace(/\/$/, '');
  const na = norm(a), nb = norm(b), nw = norm(workspace);
  if (na === nb) return true;
  const rel = (p: string) => p.startsWith(nw) ? p.slice(nw.length).replace(/^\//, '') : p.replace(/^\/agent_vm\//, '');
  const ra = rel(na), rb = rel(nb);
  if (!ra || !rb) return false;
  return ra === rb || ra.endsWith('/' + rb) || rb.endsWith('/' + ra);
}

// 重建文件树时保留旧树的展开状态（按 path 匹配目录）
function mergeExpanded(oldNodes: FileNode[], newNodes: FileNode[]): FileNode[] {
  return newNodes.map(n => {
    if (!n.isDir) return n;
    const old = oldNodes.find(o => o.isDir && o.path === n.path);
    if (old && old.expanded) {
      return { ...n, expanded: true, children: mergeExpanded(old.children || [], n.children || []) };
    }
    return n;
  });
}

// ====== 多 Tab PTY 终端 ======
type TermTab = {
  id: string;
  label: string;
  terminalEl: HTMLDivElement;
  terminal: Terminal;
  fitAddon: FitAddon;
  ws: WebSocket;
  resizeObs: ResizeObserver;
};

function IDETerminal({ visible }: { visible: boolean }) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const tabCounterRef = useRef(1);
  const [tabs, setTabs] = useState<TermTab[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const fitById = useCallback((id: string) => {
    setTabs(prev => prev.map(t => {
      if (t.id !== id || !t.fitAddon) return t;
      try { t.fitAddon.fit(); } catch { /* noop */ }
      return t;
    }));
  }, []);

  const createTab = useCallback((cmd: string | null) => {
    const id = `ide-term-${tabCounterRef.current++}-${Date.now()}`;
    const label = cmd ? cmd.slice(0, 20) : `Shell ${tabCounterRef.current - 1}`;

    const container = document.createElement('div');
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.overflow = 'hidden';
    container.style.display = 'none';

    // 严谨严肃的终端配色 — Nord 风格深色
    const term = new Terminal({
      theme: {
        background: '#2e3440',
        foreground: '#d8dee9',
        cursor: '#88c0d0',
        selectionBackground: '#434c5e',
        black: '#3b4252', red: '#bf616a', green: '#a3be8c', yellow: '#ebcb8b',
        blue: '#81a1c1', magenta: '#b48ead', cyan: '#88c0d0', white: '#e5e9f0',
        brightBlack: '#4c566a', brightRed: '#d08770', brightGreen: '#a3be8c',
        brightYellow: '#ebcb8b', brightBlue: '#88c0d0', brightMagenta: '#b48ead',
        brightCyan: '#8fbcbb', brightWhite: '#eceff4',
      },
      cursorBlink: true,
      scrollback: 5000,
      fontSize: 15,
      fontFamily: '"Cascadia Code", "Fira Code", Consolas, monospace',
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(container);

    const cmdParam = cmd ? `?cmd=${encodeURIComponent(cmd)}` : '';
    const wsUrl = `ws://${window.location.host}/api/terminal/ws${cmdParam}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      try {
        const msg = '\x00' + JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows });
        if (ws.readyState === WebSocket.OPEN) ws.send(msg);
      } catch { /* noop */ }
      try { fitAddon.fit(); } catch { /* noop */ }
    };
    ws.onmessage = (event) => { term.write(event.data); };
    ws.onerror = () => { term.writeln(`\r\n\x1b[31m[WebSocket Error]\x1b[0m`); };
    ws.onclose = () => { term.writeln(`\r\n\x1b[33m[Disconnected]\x1b[0m`); };
    term.onData((data) => { if (ws.readyState === WebSocket.OPEN) ws.send(data); });
    term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) ws.send('\x00' + JSON.stringify({ type: 'resize', cols, rows }));
    });

    const resizeObs = new ResizeObserver(() => { try { fitAddon.fit(); } catch { /* noop */ } });
    resizeObs.observe(container);

    const newTab: TermTab = { id, label, terminalEl: container, terminal: term, fitAddon, ws, resizeObs };
    setTabs(prev => {
      const next = [...prev, newTab];
      requestAnimationFrame(() => { try { fitAddon.fit(); } catch { /* noop */ } });
      return next;
    });
    setActiveId(id);
    return id;
  }, []);

  const closeTab = useCallback((id: string) => {
    setTabs(prev => {
      const tab = prev.find(t => t.id === id);
      if (tab) { tab.resizeObs?.disconnect(); tab.ws?.close(); tab.terminal?.dispose(); tab.terminalEl?.remove(); }
      const next = prev.filter(t => t.id !== id);
      setActiveId(currId => (currId === id ? (next[next.length - 1]?.id ?? null) : currId));
      return next;
    });
  }, []);

  // 挂载/切换 tab
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    wrapper.innerHTML = '';
    const tab = tabs.find(t => t.id === activeId);
    if (tab && tab.terminalEl) {
      tab.terminalEl.style.display = 'block';
      wrapper.appendChild(tab.terminalEl);
      try { tab.fitAddon?.fit(); } catch { /* noop */ }
      try { tab.terminal?.refresh(0, (tab.terminal?.rows ?? 1) - 1); } catch { /* noop */ }
    }
    tabs.forEach(t => { if (t.id !== activeId && t.terminalEl) t.terminalEl.style.display = 'none'; });
  }, [activeId, tabs, visible]);

  // 卸载时清理
  useEffect(() => {
    return () => { tabs.forEach(t => { t.resizeObs?.disconnect(); t.ws?.close(); t.terminal?.dispose(); t.terminalEl?.remove(); }); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 首次自动建 tab
  useEffect(() => {
    if (visible && tabs.length === 0) createTab(null);
  }, [visible, tabs.length, createTab]);

  return (
    <div className="flex flex-col h-full">
      {/* Tab 栏 — 深色底上的手绘小卡 */}
      <div className="flex items-center gap-1.5 px-2 py-1 bg-[#2e3440] border-b-2 border-[#4c566a] shrink-0 overflow-x-auto">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => { setActiveId(tab.id); fitById(tab.id); }}
            style={activeId === tab.id ? sketchyShape1 : sketchyShape3}
            className={`flex items-center gap-1.5 px-3 py-1 text-[13px] font-bold transition-all whitespace-nowrap border-2 ${
              activeId === tab.id
                ? 'bg-[#434c5e] text-[#d8dee9] border-[#88c0d0] shadow-[2px_2px_0px_0px_rgba(0,0,0,0.4)] -rotate-[0.5deg]'
                : 'text-[#4c566a] border-transparent hover:text-[#d8dee9] hover:bg-[#3b4252] hover:border-[#4c566a]'
            }`}
          >
            <span className="max-w-[140px] truncate">{tab.label}</span>
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
              className="ml-1 opacity-50 hover:opacity-100 hover:text-[#bf616a] transition-colors"
            >
              <X size={10} strokeWidth={3} />
            </span>
          </button>
        ))}
        <button
          onClick={() => createTab(null)}
          style={sketchyShape2}
          className="p-1 text-[#4c566a] hover:text-[#88c0d0] border-2 border-[#4c566a] hover:border-[#88c0d0] transition-colors"
          title="新建终端"
        >
          <Plus size={12} strokeWidth={3} />
        </button>
      </div>
      {/* 终端内容 */}
      <div ref={wrapperRef} className="flex-1 min-h-0 bg-[#2e3440]" />
    </div>
  );
}

// ====== 主 IDE Panel ======
export default function IDEPanel({ workspacePath, onClose, onOpenLink }: IDEPanelProps) {
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [dirtyFiles, setDirtyFiles] = useState<Set<string>>(new Set());
  const [showTerminal, setShowTerminal] = useState(true);
  // Markdown 预览模式
  const [mdPreviewMode, setMdPreviewMode] = useState<Record<string, boolean>>({});
  // File Changes 视图：侧栏模式 + 变更列表 + 当前查看的变更
  const [sidebarMode, setSidebarMode] = useState<'explorer' | 'changes'>('explorer');
  const [fileChanges, setFileChanges] = useState<FileChangeItem[]>([]);
  const [activeChangePath, setActiveChangePath] = useState<string | null>(null);
  // 变更文件的当前磁盘内容（整文件 diff 视图的骨架），随轮询实时更新
  const [changeContents, setChangeContents] = useState<Record<string, string>>({});
  // 大文件防护：超大变更文件不装载全文，diff 视图退化为仅显示变更片段
  const [oversizedChanges, setOversizedChanges] = useState<Set<string>>(new Set());
  // 面板尺寸：侧栏宽度 + 终端高度（可拖拽调节）
  const [sidebarWidth, setSidebarWidth] = useState(220);
  const [terminalHeight, setTerminalHeight] = useState(280);
  // 大文件拦截提示（点开超大文本文件时显示）
  const [largeFileNotice, setLargeFileNotice] = useState<{ path: string; size: number } | null>(null);
  // 独立窗口（通过 /ide 路由识别自身处于独立窗口）
  const [detached] = useState(() => {
    return typeof window !== 'undefined' && window.location.pathname.startsWith('/ide');
  });

  // 🌟 行选择（1-based 区间）：编辑器为文件行号；变更视图为当前文件（new 侧）行号
  const [selectedLines, setSelectedLines] = useState<{ start: number; end: number } | null>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  // 切换文件/变更视图时清除行选择
  useEffect(() => { setSelectedLines(null); }, [activeFile, activeChangePath]);

  // 🌟 跨窗口广播通道：Ctrl+U 提取的「路径+行号」引用发给主窗口聊天输入框（独立窗口模式同样可达）
  const ideChannelRef = useRef<BroadcastChannel | null>(null);
  useEffect(() => {
    try { ideChannelRef.current = new BroadcastChannel('purrcat-ide'); } catch { ideChannelRef.current = null; }
    return () => { try { ideChannelRef.current?.close(); } catch { /* noop */ } ideChannelRef.current = null; };
  }, []);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const purrcat = (window as any).purrcat;
  const hasElectron = !!purrcat?.readDir;

  // ---- 文件操作 ----
  const readDirectory = async (dirPath: string): Promise<FileNode[]> => {
    if (purrcat?.readDir) {
      try {
        const entries = await purrcat.readDir(dirPath);
        return entries.map((e: any) => ({ name: e.name, isDir: e.isDir, path: e.path || `${dirPath}/${e.name}`, children: e.isDir ? [] : undefined, expanded: false }));
      } catch (e) { console.warn('purrcat.readDir failed, fallback to HTTP:', e); }
    }
    try {
      const res = await fetch(`/api/filesystem/list?path=${encodeURIComponent(dirPath)}`);
      if (res.ok) {
        const entries = await res.json();
        return entries.map((e: any) => ({ name: e.name, isDir: e.isDir, path: e.path || `${dirPath}/${e.name}`, children: e.isDir ? [] : undefined, expanded: false }));
      }
    } catch (e) { console.warn('HTTP readDir fallback failed:', e); }
    return [];
  };

  const readFileContent = async (filePath: string): Promise<string> => {
    if (purrcat?.readFile) {
      try { return await purrcat.readFile(filePath); } catch (e) { console.warn('purrcat.readFile failed, fallback to HTTP:', e); }
    }
    try {
      const res = await fetch(`/api/filesystem/read?path=${encodeURIComponent(filePath)}`);
      if (res.ok) { const data = await res.json(); return data.content || ''; }
    } catch (e) { console.warn('HTTP readFile fallback failed:', e); }
    return '';
  };

  const saveFileContent = async (filePath: string, content: string): Promise<boolean> => {
    if (purrcat?.writeFile) {
      try { await purrcat.writeFile(filePath, content); return true; } catch (e) { console.warn('purrcat.writeFile failed, fallback to HTTP:', e); }
    }
    try {
      const res = await fetch('/api/filesystem/write', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: filePath, content }) });
      return res.ok;
    } catch (e) { console.warn('HTTP writeFile fallback failed:', e); return false; }
  };

  // 获取文件大小（Electron fs:stat 优先，HTTP /stat 兜底），失败返回 0（不拦截）
  const getFileSize = async (filePath: string): Promise<number> => {
    if (purrcat?.statFile) {
      try { const st = await purrcat.statFile(filePath); if (st?.size != null) return st.size; } catch { /* fallthrough */ }
    }
    try {
      const res = await fetch(`/api/filesystem/stat?path=${encodeURIComponent(filePath)}`);
      if (res.ok) { const data = await res.json(); return data.size ?? 0; }
    } catch { /* noop */ }
    return 0;
  };

  // ---- 文件树 ----
  useEffect(() => {
    if (!workspacePath) return;
    setLoading(true);
    readDirectory(workspacePath).then((tree) => { setFileTree(tree); setLoading(false); });
  }, [workspacePath]);

  // ---- File Changes：轮询全局变更（同 ChatPage，3s）----
  const fetchDiffs = useCallback(async () => {
    try {
      const res = await fetch('/api/filesystem/diffs');
      if (res.ok) {
        const data = await res.json();
        if (data.diffs) setFileChanges(data.diffs);
      }
    } catch { /* noop */ }
  }, []);
  useEffect(() => {
    fetchDiffs();
    const t = setInterval(fetchDiffs, 3000);
    return () => clearInterval(t);
  }, [fetchDiffs]);

  // 变更列表按 workspace 过滤（绝对路径或 /agent_vm 沙盒路径两种体系；匹配不上时展示全部，避免空列表）
  const displayChanges = useMemo(() => {
    const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+/g, '/').toLowerCase().replace(/\/$/, '');
    const wp = norm(workspacePath);
    const mapped = fileChanges.map(c => {
      const dp = norm(c.path);
      if (wp && dp.startsWith(wp)) return { ...c, rel: c.path.slice(wp.length).replace(/^[/\\]/, '') };
      const stripped = dp.replace(/^\/agent_vm/, '');
      const first = stripped.split('/').filter(Boolean)[0] || '';
      if (first && wp.includes('/' + first)) return { ...c, rel: stripped.replace(/^\/+/, '') };
      return null;
    }).filter(Boolean) as FileChangeItem[];
    if (mapped.length > 0) return mapped;
    return fileChanges.map(c => ({ ...c, rel: c.path }));
  }, [fileChanges, workspacePath]);

  const activeChange = activeChangePath ? displayChanges.find(c => c.path === activeChangePath) || null : null;

  // 🌟 Ctrl+U：把选中文件路径 + 选中行区间提取为输入框元数据（如 /xxx/xxx.md L20-L21），广播给聊天输入框
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'u') return;
      if (!activeFile && !activeChange) return;
      e.preventDefault(); // 拦截浏览器「查看源代码」默认行为
      if (!selectedLines) { toast('先选中行：点击行号或拖选文本', { icon: '📌' }); return; }
      const target = activeChange
        ? (openTabs.find(t => isSameFilePath(t, activeChange.path, workspacePath)) || activeChange.path)
        : (activeFile as string);
      const rangeTxt = selectedLines.start === selectedLines.end
        ? `L${selectedLines.start}`
        : `L${selectedLines.start}-L${selectedLines.end}`;
      const text = `${target.replace(/\\/g, '/')} ${rangeTxt}`;
      ideChannelRef.current?.postMessage({ type: 'insert-input', text });
      toast.success(`已插入引用 ${rangeTxt} 到输入框`);
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [activeFile, activeChange, selectedLines, openTabs, workspacePath]);

  // 🌟 实时性：为 effects 提供最新值的 ref（避免闭包过期）
  const liveRef = useRef({ activeFile: null as string | null, dirty: new Set<string>(), changes: [] as FileChangeItem[], ws: '' });
  liveRef.current = { activeFile, dirty: dirtyFiles, changes: displayChanges, ws: workspacePath };

  // 实时刷新 1：变更列表每次更新后，若当前打开的文件在变更中且无未保存编辑，立即重读内容
  useEffect(() => {
    const { activeFile: af, dirty, changes, ws } = liveRef.current;
    if (!af || dirty.has(af)) return;
    if (!changes.some(c => isSameFilePath(c.path, af, ws))) return;
    readFileContent(af).then(content => {
      // fetch 期间用户可能已开始编辑或切走文件，避免覆盖输入
      if (liveRef.current.dirty.has(af) || liveRef.current.activeFile !== af) return;
      setFileContents(prev => ({ ...prev, [af]: content }));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileChanges]);

  // 实时刷新 2：变更文件集合变化（新建/删除文件）时重建文件树，保留展开状态
  const treeSigRef = useRef('');
  useEffect(() => {
    const sig = displayChanges.map(c => `${c.path}:${c.change_type}`).sort().join('|');
    if (sig === treeSigRef.current) return;
    treeSigRef.current = sig;
    if (!workspacePath) return;
    readDirectory(workspacePath).then(tree => setFileTree(prev => mergeExpanded(prev, tree)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayChanges, workspacePath]);

  // 实时刷新 3：当前查看的变更文件 → 拉取其磁盘内容作为整文件 diff 骨架（diff 更新时重取）
  useEffect(() => {
    if (!activeChange) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/filesystem/preview?path=${encodeURIComponent(activeChange.path)}`);
        if (res.ok && !cancelled) {
          const text = await res.text();
          // 🌟 大文件防护：超大文件不装载全文，骨架置空 → buildFullDiffView 自动退化为仅渲染变更片段
          if (text.length > MAX_TEXT_FILE_SIZE) {
            setOversizedChanges(prev => new Set(prev).add(activeChange.path));
            setChangeContents(prev => ({ ...prev, [activeChange.path]: '' }));
          } else {
            setOversizedChanges(prev => {
              if (!prev.has(activeChange.path)) return prev;
              const n = new Set(prev); n.delete(activeChange.path); return n;
            });
            setChangeContents(prev => ({ ...prev, [activeChange.path]: text }));
          }
        }
      } catch { /* noop */ }
    })();
    return () => { cancelled = true; };
  }, [activeChange?.path, fileChanges]);

  // 变更路径 → 匹配已打开 Tab 的真实路径（ack/rollback 后刷新其缓存）
  const findOpenTabForChange = (changePath: string): string | null => {
    return openTabs.find(t => isSameFilePath(t, changePath, workspacePath)) || null;
  };

  // 接收更改：删掉磁盘备份，该文件从变更列表移除（自动跳到下一个变更）
  const handleAckChange = async (change: FileChangeItem) => {
    try {
      const res = await fetch('/api/filesystem/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: change.path, backup_id: change.newest_backup_id }) });
      if (res.ok) {
        const next = displayChanges.find(c => c.path !== change.path);
        setActiveChangePath(next ? next.path : null);
        // 该文件若有已打开的 Tab（且未编辑），立即重读内容保证所见即所得
        const tabPath = findOpenTabForChange(change.path);
        if (tabPath && !dirtyFiles.has(tabPath)) {
          readFileContent(tabPath).then(content => setFileContents(prev => ({ ...prev, [tabPath]: content })));
        }
        fetchDiffs();
      }
    } catch { /* noop */ }
  };

  // 接收全部更改：一键清理所有未确认变更的备份
  const handleAckAllChanges = async () => {
    try {
      const res = await fetch('/api/filesystem/ack_all', { method: 'POST' });
      if (res.ok) {
        setActiveChangePath(null);
        setChangeContents({});
        fetchDiffs();
      }
    } catch { /* noop */ }
  };

  // 撤销更改：回滚到最旧备份，同时刷新文件树与内容缓存（自动跳到下一个变更）
  const handleRollbackChange = async (change: FileChangeItem) => {
    try {
      const res = await fetch('/api/filesystem/undo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: change.path, backup_id: change.oldest_backup_id }) });
      if (res.ok) {
        const next = displayChanges.find(c => c.path !== change.path);
        setActiveChangePath(next ? next.path : null);
        // 用真实 Tab 路径清缓存并重读（change.path 可能是沙盒路径，直接删 key 删不中）
        const tabPath = findOpenTabForChange(change.path);
        const realPath = tabPath || change.path;
        setFileContents(prev => { const n = { ...prev }; delete n[realPath]; return n; });
        if (tabPath && !dirtyFiles.has(tabPath)) {
          readFileContent(tabPath).then(content => setFileContents(prev => ({ ...prev, [tabPath]: content })));
        }
        readDirectory(workspacePath).then(tree => setFileTree(prev => mergeExpanded(prev, tree)));
        fetchDiffs();
      }
    } catch { /* noop */ }
  };

  const toggleDir = async (node: FileNode, parents: FileNode[] = []) => {
    if (!node.isDir) return;
    if (node.expanded === false && node.children && node.children.length === 0) {
      const children = await readDirectory(node.path || `${workspacePath}/${node.name}`);
      updateNodeInTree(node, parents, { children, expanded: true });
    } else {
      updateNodeInTree(node, parents, { expanded: !node.expanded });
    }
  };

  const updateNodeInTree = (target: FileNode, parents: FileNode[], patch: Partial<FileNode>) => {
    setFileTree((prev) => {
      const newTree = JSON.parse(JSON.stringify(prev));
      let list = newTree;
      for (const p of parents) { const found = list.find((n: FileNode) => n.path === p.path); if (found) list = found.children || []; }
      const found = list.find((n: FileNode) => n.path === target.path);
      if (found) Object.assign(found, patch);
      return newTree;
    });
  };

  const openFile = async (node: FileNode) => {
    if (node.isDir) return;
    const path = node.path || `${workspacePath}/${node.name}`;
    const fileType = getFileType(path);
    // 有未确认变更的文件（且本地无未保存编辑）→ 直接进入 filechange 视图
    const pendingChange = !dirtyFiles.has(path) && displayChanges.find(c => isSameFilePath(c.path, path, workspacePath));
    if (pendingChange) {
      setSidebarMode('changes');
      setActiveChangePath(pendingChange.path);
      return;
    }
    setActiveChangePath(null); // 打开普通文件时退出变更视图
    setLargeFileNotice(null); // 清除上一个拦截提示
    // 二进制文件不打开
    if (fileType === 'binary') return;
    // 🌟 大文件拦截：文本类文件先查大小，超限不加载（防止 10 万行 CSV 卡死）
    if (fileType === 'text' || fileType === 'markdown') {
      const size = await getFileSize(path);
      if (size > MAX_TEXT_FILE_SIZE) {
        setLargeFileNotice({ path, size });
        return;
      }
    }
    if (!openTabs.includes(path)) setOpenTabs((prev) => [...prev, path]);
    setActiveFile(path);
    if (fileType === 'text' || fileType === 'markdown') {
      // 🌟 每次打开都重新读磁盘内容，保证实时（不信任旧缓存）
      const content = await readFileContent(path);
      setFileContents((prev) => ({ ...prev, [path]: content }));
      setDirtyFiles((prev) => { if (prev.has(path)) { const n = new Set(prev); n.delete(path); return n; } return prev; });
    }
  };

  const closeTab = (path: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenTabs((prev) => {
      const idx = prev.indexOf(path);
      const next = prev.filter((p) => p !== path);
      if (activeFile === path) setActiveFile(next.length > 0 ? next[Math.max(0, idx - 1)] : null);
      return next;
    });
  };

  const handleSave = async () => {
    if (!activeFile) return;
    const content = fileContents[activeFile] || '';
    const ok = await saveFileContent(activeFile, content);
    if (ok) setDirtyFiles((prev) => { const n = new Set(prev); n.delete(activeFile); return n; });
  };

  const handleEditorChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (!activeFile) return;
    const value = e.target.value;
    setFileContents((prev) => ({ ...prev, [activeFile]: value }));
    setDirtyFiles((prev) => { const n = new Set(prev); n.add(activeFile); return n; });
  };

  // ---- 行号槽 + 行选择 ----
  // 当前编辑文件的行数组（行号槽渲染 + 点击行号计算偏移共用）
  const editorLines = useMemo(
    () => (activeFile ? (fileContents[activeFile] || '').split('\n') : []),
    [activeFile, fileContents]
  );

  // 行号槽与编辑区滚动同步
  const syncGutterScroll = () => {
    if (gutterRef.current && editorRef.current) gutterRef.current.scrollTop = editorRef.current.scrollTop;
  };

  // 点击行号：选中整行（Shift+点击扩展为区间）
  const handleGutterClick = (n: number, shift: boolean) => {
    if (!activeFile) return;
    const lines = (fileContents[activeFile] || '').split('\n');
    let s = n, e = n;
    if (shift && selectedLines) { s = Math.min(selectedLines.start, n); e = Math.max(selectedLines.end, n); }
    const off = (line: number) => lines.slice(0, line - 1).reduce((a, l) => a + l.length + 1, 0);
    const startOff = off(s);
    const endOff = off(e) + (lines[e - 1]?.length ?? 0);
    const ta = editorRef.current;
    if (ta) { ta.focus(); ta.setSelectionRange(startOff, endOff); }
    setSelectedLines({ start: s, end: e });
  };

  // 编辑区拖选/键盘选中文本 → 同步为选中行区间
  const syncSelectionFromTextarea = () => {
    const ta = editorRef.current;
    if (!ta || !activeFile) return;
    if (ta.selectionStart === ta.selectionEnd) return; // 无选区：保留行号点击的选择
    const v = ta.value;
    const s = v.slice(0, ta.selectionStart).split('\n').length;
    const e = v.slice(0, ta.selectionEnd).split('\n').length;
    setSelectedLines(prev => (prev && prev.start === Math.min(s, e) && prev.end === Math.max(s, e)) ? prev : { start: Math.min(s, e), end: Math.max(s, e) });
  };

  // 变更视图：点击行选中（Shift+点击扩展），行号取当前文件（new 侧）；纯删除行无当前行号
  const handleDiffRowClick = (ln: FullDiffLine, shift: boolean) => {
    if (ln.newNo == null) { toast('删除行在当前文件中不存在，无法引用', { icon: '⚠️' }); return; }
    const n = ln.newNo;
    setSelectedLines(shift && selectedLines
      ? { start: Math.min(selectedLines.start, n), end: Math.max(selectedLines.end, n) }
      : { start: n, end: n });
  };

  // ---- 独立窗口 ----
  const handleDetach = () => {
    if (!hasElectron || !purrcat?.ideDetach) return;
    purrcat.ideDetach(workspacePath);
    // 主窗口卸载 IDE 面板（与 AgentBrowser detach 行为一致），IDE 移入独立窗口
    onClose();
  };

  const handleReattach = () => {
    if (!hasElectron || !purrcat?.ideReattach) return;
    // 主进程销毁独立窗口并通知主窗口恢复 IDE 面板
    purrcat.ideReattach();
  };

  // 独立窗口中点关闭 = 回归主窗口（避免留下空窗口）
  const handleClose = () => {
    if (detached) { handleReattach(); return; }
    onClose();
  };

  // ---- 面板拖拽调尺寸 ----
  // 拖拽侧栏右缘：左右调节文件树/变更列表宽度
  const startSidebarResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = sidebarWidth;
    const onMove = (ev: MouseEvent) => {
      setSidebarWidth(Math.min(520, Math.max(150, startW + ev.clientX - startX)));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // 拖拽终端上缘：上下调节终端高度（上限为面板高度减去编辑器最小 180px）
  const startTerminalResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = terminalHeight;
    const maxH = Math.max(200, (wrapperRef.current?.clientHeight ?? 700) - 220);
    const onMove = (ev: MouseEvent) => {
      setTerminalHeight(Math.min(maxH, Math.max(110, startH - (ev.clientY - startY))));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // ---- 文件图标 ----
  const getFileIcon = (node: FileNode) => {
    if (node.isDir) return <FolderOpen size={16} className={`text-[#ebcb8b] transition-transform ${node.expanded ? '' : '-rotate-90'}`} strokeWidth={2} />;
    const ft = getFileType(node.path || node.name);
    if (ft === 'image') return <FileImage size={16} className="text-[#a3be8c]" strokeWidth={2} />;
    if (ft === 'video') return <FileVideo size={16} className="text-[#b48ead]" strokeWidth={2} />;
    if (ft === 'binary') return <AlertCircle size={16} className="text-[#4c566a]" strokeWidth={2} />;
    return <BookOpen size={16} className="text-[#88c0d0]" strokeWidth={2} />;
  };

  // ---- Markdown 渲染 ----
  // 🌟 弃用自研正则渲染（表格/代码块/任务列表等大量语法解析不出来），
  //    改用 ReactMarkdown + remark-gfm，与聊天气泡同一渲染引擎；表格/引用/图片样式见 ChatShared.MarkdownComponents
  // md 预览中本地图片改走后端 /preview 代理（相对路径基于 md 文件所在目录解析）
  const mdAssetProxy = (src: string) => {
    if (!src) return src;
    if (/^(https?:|data:|blob:)/i.test(src)) return src;
    const proxy = (p: string) => `/api/filesystem/preview?path=${encodeURIComponent(p)}`;
    if (src.startsWith('file://')) {
      let p = src.replace(/^file:\/\//, '');
      if (p.startsWith('/') && p.charAt(2) === ':') p = p.substring(1);
      return proxy(safeDecodeUri(p));
    }
    if (/^[A-Za-z]:[/\\]/.test(src) || src.startsWith('/agent_vm/') || src.startsWith('./agent_vm/')) return proxy(src);
    if (src.startsWith('/')) return proxy(src);
    const baseDir = (activeFile || '').replace(/\\/g, '/').split('/').slice(0, -1).join('/');
    const segs = (baseDir + '/' + src).split('/');
    const out: string[] = [];
    for (const s of segs) {
      if (s === '' || s === '.') continue;
      if (s === '..') out.pop();
      else out.push(s);
    }
    return proxy(out.join('/'));
  };

  const IDE_MARKDOWN_COMPONENTS: any = useMemo(() => ({
    ...MarkdownComponents,
    img: ({ src, ...props }: any) => <img src={mdAssetProxy(String(src || ''))} {...props} />,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [activeFile]);

  // ---- 渲染文件树节点 ----
  const renderFileNode = (node: FileNode, parents: FileNode[] = [], depth: number = 0) => {
    const isActive = activeFile === node.path;
    const ft = !node.isDir ? getFileType(node.path || node.name) : null;
    return (
      <div key={node.path || node.name}>
        <div
          onClick={() => {
            if (node.isDir) { toggleDir(node, parents); }
            else if (ft === 'binary') { /* 不打开 */ }
            else { openFile(node); }
          }}
          className={`flex items-center gap-2 text-sm p-1.5 cursor-pointer transition-colors select-none ${
            isActive
              ? 'bg-[#88c0d0]/15 text-[#2e3440] font-semibold'
              : ft === 'binary'
                ? 'text-[#4c566a] opacity-60 cursor-default'
                : 'text-[#4c566a] hover:bg-[#d8dee9]/30 hover:text-[#2e3440]'
          }`}
          style={{ paddingLeft: `${depth * 16 + 10}px` }}
        >
          {getFileIcon(node)}
          <span className="truncate flex-1">{node.name}</span>
          {!node.isDir && dirtyFiles.has(node.path || '') && (
            <span className="w-1.5 h-1.5 rounded-full bg-[#bf616a] shrink-0" />
          )}
        </div>
        {node.isDir && node.expanded && node.children && (
          <div>{node.children.map((child) => renderFileNode(child, [...parents, node], depth + 1))}</div>
        )}
      </div>
    );
  };

  // 当前活跃文件类型
  const activeFileType = activeFile ? getFileType(activeFile) : null;
  // 🌟 md 文件默认进入预览模式（用户手动切换过则记住其选择）
  const isMdPreview = activeFile && (mdPreviewMode[activeFile] ?? true);

  return (
    <div
      ref={wrapperRef}
      style={sketchyShape2}
      className="h-full bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] flex flex-col relative overflow-hidden"
    >
      {/* 顶部工具栏 — 手绘风框架：白色底 + 4px ink 描边 + 手绘按钮 */}
      <div className="px-4 py-2 flex items-center justify-between border-b-4 border-ink bg-paper shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 bg-[#88c0d0] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center -rotate-3 shrink-0" style={sketchyShape1}>
            <TerminalSquare size={16} className="text-ink" strokeWidth={3} />
          </div>
          <span className="text-xl font-black tracking-tight text-ink shrink-0" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Workspace</span>
          <span className="text-xs font-mono font-bold text-ink/40 truncate">{workspacePath}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Markdown 预览/编辑切换（变更视图时隐藏） */}
          {!activeChange && activeFileType === 'markdown' && (
            <button
              onClick={() => activeFile && setMdPreviewMode(prev => ({ ...prev, [activeFile]: !(prev[activeFile] ?? true) }))}
              style={sketchyShape3}
              className={`flex items-center gap-1 px-3 py-1 text-[13px] font-black border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-[1px] active:shadow-none ${
                isMdPreview
                  ? 'bg-[#88c0d0] text-paper hover:bg-[#5e81ac]'
                  : 'bg-paper text-ink hover:bg-[#88c0d0] hover:text-paper'
              }`}
              title={isMdPreview ? '切换到编辑' : '切换到预览'}
            >
              {isMdPreview ? <Code2 size={14} strokeWidth={3} /> : <Eye size={14} strokeWidth={3} />}
              {isMdPreview ? 'Edit' : 'Preview'}
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!!activeChange || !activeFile || !dirtyFiles.has(activeFile) || activeFileType === 'image' || activeFileType === 'video'}
            style={sketchyShape1}
            className={`flex items-center gap-1 px-3 py-1 text-[13px] font-black border-2 border-ink transition-all ${
              activeFile && dirtyFiles.has(activeFile) && activeFileType !== 'image' && activeFileType !== 'video'
                ? 'bg-[#a3be8c] text-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-[1px] active:shadow-none'
                : 'bg-paper/60 text-ink/30 cursor-not-allowed'
            }`}
            title="保存 (Ctrl+S)"
          >
            <Save size={14} strokeWidth={3} /> Save
          </button>
          {/* 独立窗口 */}
          {hasElectron && !detached && (
            <button onClick={handleDetach} style={sketchyShape2} className="p-1.5 text-ink bg-paper border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#88c0d0] hover:text-paper transition-all active:translate-y-[1px] active:shadow-none" title="独立窗口">
              <PictureInPicture2 size={13} strokeWidth={3} />
            </button>
          )}
          {detached && (
            <button onClick={handleReattach} style={sketchyShape2} className="p-1.5 text-paper bg-[#88c0d0] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#5e81ac] transition-all active:translate-y-[1px] active:shadow-none" title="回归主窗口">
              <PictureInPicture2 size={13} strokeWidth={3} />
            </button>
          )}
          <button onClick={handleClose} style={sketchyShape2} className="p-1.5 text-ink bg-paper border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-terracotta hover:text-paper transition-all active:translate-y-[1px] active:shadow-none" title={detached ? '回归主窗口' : '关闭'}>
            <X size={13} strokeWidth={3} />
          </button>
        </div>
      </div>

      {/* 主体工作区 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧 File Tree / File Changes — 头部手绘，列表内容保持板正；宽度可拖拽 */}
        <div style={{ width: sidebarWidth }} className="border-r-2 border-ink bg-white flex flex-col shrink-0">
          <div className="px-2 py-1.5 border-b-2 border-ink/15 bg-paper flex items-center justify-between shrink-0">
            <span className="text-[11px] font-black tracking-widest text-ink/60 uppercase pl-1 truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              {sidebarMode === 'explorer' ? 'Explorer' : `Changes (${displayChanges.length})`}
            </span>
            <div className="flex items-center gap-1">
              {sidebarMode === 'changes' && displayChanges.length > 0 && (
                <button
                  onClick={handleAckAllChanges}
                  style={sketchyShape2}
                  className="px-2 py-0.5 text-[10px] font-black border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] bg-[#a3be8c] text-ink hover:bg-[#8eb072] transition-all active:translate-y-[1px] active:shadow-none"
                  title="接收全部更改（清理所有备份）"
                >
                  接收全部
                </button>
              )}
              <button
                onClick={() => setSidebarMode('explorer')}
                style={sketchyShape1}
                className={`p-1 border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-[1px] active:shadow-none ${sidebarMode === 'explorer' ? 'bg-[#88c0d0] text-paper' : 'bg-white text-ink/60 hover:bg-[#e5e9f0]'}`}
                title="文件树"
              >
                <FolderTree size={12} strokeWidth={3} />
              </button>
              <button
                onClick={() => setSidebarMode('changes')}
                style={sketchyShape3}
                className={`relative p-1 border-2 border-ink shadow-[1px_1px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-[1px] active:shadow-none ${sidebarMode === 'changes' ? 'bg-[#88c0d0] text-paper' : 'bg-white text-ink/60 hover:bg-[#e5e9f0]'}`}
                title="文件变更"
              >
                <FileDiff size={12} strokeWidth={3} />
                {displayChanges.length > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[12px] h-[12px] px-[3px] rounded-full bg-[#bf616a] text-white text-[8px] font-bold flex items-center justify-center">{displayChanges.length}</span>
                )}
              </button>
            </div>
          </div>

          {sidebarMode === 'explorer' ? (
            <div className="flex-1 overflow-y-auto py-1">
              {loading ? (
                <div className="text-xs font-black text-ink/40 p-3 animate-pulse tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Loading...</div>
              ) : fileTree.length === 0 ? (
                <div className="flex flex-col items-center py-10 text-ink/30 select-none gap-2">
                  <div style={sketchyShape1} className="w-10 h-10 bg-paper border-2 border-ink/30 flex items-center justify-center -rotate-3">
                    <FolderOpen size={18} strokeWidth={2.5} />
                  </div>
                  <span className="text-[11px] font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Empty workspace</span>
                </div>
              ) : (
                fileTree.map((node) => renderFileNode(node))
              )}
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto py-1">
              {displayChanges.length === 0 ? (
                <div className="flex flex-col items-center py-10 text-ink/30 select-none gap-2">
                  <div style={sketchyShape3} className="w-10 h-10 bg-[#a3be8c]/20 border-2 border-ink/30 flex items-center justify-center rotate-3">
                    <Check size={18} strokeWidth={3} />
                  </div>
                  <span className="text-[11px] font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>All clean!</span>
                </div>
              ) : (
                displayChanges.map((c) => {
                  const isActive = activeChangePath === c.path;
                  const name = (c.rel || c.path).split('/').pop() || c.path;
                  const badgeCls = c.change_type === 'created'
                    ? 'bg-[#a3be8c] text-white'
                    : c.change_type === 'deleted'
                      ? 'bg-[#bf616a] text-white'
                      : 'bg-[#81a1c1] text-white';
                  const badgeTxt = c.change_type === 'created' ? 'N' : c.change_type === 'deleted' ? 'D' : 'M';
                  return (
                    <div
                      key={c.id || c.path}
                      onClick={() => setActiveChangePath(c.path)}
                      className={`flex items-center gap-2 text-sm px-2 py-1.5 cursor-pointer transition-colors select-none ${
                        isActive
                          ? 'bg-[#88c0d0]/15 text-[#2e3440] font-semibold'
                          : 'text-[#4c566a] hover:bg-[#d8dee9]/40 hover:text-[#2e3440]'
                      }`}
                      title={c.rel || c.path}
                    >
                      <span className={`w-4 h-4 shrink-0 rounded-[3px] text-[9px] font-bold flex items-center justify-center ${badgeCls}`}>{badgeTxt}</span>
                      <span className={`truncate flex-1 ${c.change_type === 'deleted' ? 'line-through opacity-60' : ''}`}>{name}</span>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* 垂直拖拽条：调节侧栏宽度 */}
        <div
          onMouseDown={startSidebarResize}
          className="w-1.5 shrink-0 cursor-col-resize bg-transparent hover:bg-[#88c0d0]/60 active:bg-[#88c0d0] transition-colors -ml-[2px] z-10"
          title="拖拽调节宽度"
        />

        {/* 右侧 Editor + Terminal */}
        <div className="flex-1 flex flex-col min-w-0 bg-white relative">
          {/* Editor Tabs — 白底手绘栏，Tab 为手绘小卡 */}
          <div className="flex items-end gap-1.5 px-2 pt-1.5 border-b-2 border-ink bg-paper shrink-0 overflow-x-auto">
            {openTabs.length === 0 && !activeChange && (
              <div className="px-3 pb-2 text-xs font-black text-ink/30 tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Select a file to open...</div>
            )}
            {activeChange && (() => {
              const name = (activeChange.rel || activeChange.path).split('/').pop() || activeChange.path;
              return (
                <div
                  style={sketchyShape3}
                  className="px-3 py-1 mb-1 text-[13px] flex items-center gap-1.5 cursor-pointer shrink-0 bg-white text-ink font-bold border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] -rotate-[0.5deg]"
                >
                  <FileDiff size={13} className="text-[#5e81ac]" strokeWidth={3} />
                  <span className="max-w-[200px] truncate">{name}</span>
                  <X size={11} className="opacity-40 hover:opacity-100 hover:text-[#bf616a] cursor-pointer" onClick={(e) => { e.stopPropagation(); setActiveChangePath(null); }} />
                </div>
              );
            })()}
            {openTabs.map((tabPath) => {
              const isActive = !activeChange && activeFile === tabPath;
              const fileName = tabPath.split(/[\\/]/).pop() || tabPath;
              const ft = getFileType(tabPath);
              return (
                <div
                  key={tabPath}
                  style={isActive ? sketchyShape1 : sketchyShape2}
                  onClick={() => {
                    setActiveFile(tabPath);
                    setActiveChangePath(null);
                    // 切 Tab 时若无未保存编辑则重新读盘，保证实时
                    if (!dirtyFiles.has(tabPath) && (ft === 'text' || ft === 'markdown')) {
                      readFileContent(tabPath).then(content => setFileContents(prev => ({ ...prev, [tabPath]: content })));
                    }
                  }}
                  className={`px-3 py-1 mb-1 text-[13px] flex items-center gap-1.5 cursor-pointer shrink-0 border-2 transition-all ${isActive
                    ? 'bg-white text-ink font-bold border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] rotate-[0.4deg] -translate-y-[1px]'
                    : 'border-transparent text-ink/50 hover:bg-white hover:text-ink hover:border-ink/30'}`}
                >
                  {ft === 'image' ? <FileImage size={13} className="text-[#a3be8c]" /> :
                   ft === 'video' ? <FileVideo size={13} className="text-[#b48ead]" /> :
                   <BookOpen size={13} className={isActive ? 'text-[#5e81ac]' : 'text-ink/40'} />}
                  <span className="max-w-[200px] truncate">{fileName}</span>
                  {dirtyFiles.has(tabPath) && <span className="w-1.5 h-1.5 rounded-full bg-[#bf616a] shrink-0" />}
                  <X size={11} className="opacity-40 hover:opacity-100 hover:text-[#bf616a] cursor-pointer" onClick={(e) => closeTab(tabPath, e)} />
                </div>
              );
            })}
          </div>

          {/* Editor Area */}
          <div className="flex-1 relative overflow-hidden">
            {largeFileNotice ? (
              // 大文件拦截视图
              <div className="absolute inset-0 flex flex-col items-center justify-center text-ink/40 select-none gap-3 px-8 text-center">
                <div style={sketchyShape2} className="w-16 h-16 bg-[#EBCB8B]/30 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center -rotate-2">
                  <AlertCircle size={28} strokeWidth={2.5} className="text-ink/60" />
                </div>
                <p className="font-black text-lg tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>File too large to open</p>
                <p className="text-sm font-mono font-bold truncate max-w-[80%]" title={largeFileNotice.path}>{largeFileNotice.path.split(/[\\/]/).pop()}</p>
                <p className="text-sm font-bold">{formatSize(largeFileNotice.size)} — exceeds the {formatSize(MAX_TEXT_FILE_SIZE)} text file limit.</p>
                <p className="text-xs font-bold opacity-60">Use the terminal to inspect this file (e.g. head / tail / less).</p>
                <button
                  onClick={() => setLargeFileNotice(null)}
                  style={sketchyShape3}
                  className="mt-1 px-4 py-1.5 text-[13px] font-black border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] bg-paper hover:bg-terracotta hover:text-paper transition-all active:translate-y-[1px] active:shadow-none"
                >
                  Dismiss
                </button>
              </div>
            ) : activeChange ? (
              // File Changes 详情视图：Trae/Codex 风格（无 @@/+/- 符号，删红增绿）+ 接收/撤销
              <div className="absolute inset-0 flex flex-col">
                <div className="px-3 py-1.5 flex items-center justify-between border-b-2 border-ink/15 bg-paper shrink-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileDiff size={14} className="text-[#5e81ac] shrink-0" strokeWidth={3} />
                    <span className="text-[13px] font-mono font-bold text-ink/60 truncate" title={activeChange.rel || activeChange.path}>{activeChange.rel || activeChange.path}</span>
                    <span
                      style={sketchyShape3}
                      className={`shrink-0 px-1.5 py-0.5 border-2 border-ink text-[10px] font-black uppercase ${
                        activeChange.change_type === 'created' ? 'bg-[#a3be8c] text-paper'
                        : activeChange.change_type === 'deleted' ? 'bg-[#bf616a] text-paper'
                        : 'bg-[#81a1c1] text-paper'
                      }`}
                    >{activeChange.change_type}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleAckChange(activeChange)}
                      style={sketchyShape2}
                      className="flex items-center gap-1 px-3 py-1 text-[13px] font-black border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] bg-[#a3be8c] text-ink hover:bg-[#8eb072] transition-all active:translate-y-[1px] active:shadow-none"
                      title="接收更改（保留当前内容并清理备份）"
                    >
                      <Check size={14} strokeWidth={3} /> 接收
                    </button>
                    <button
                      onClick={() => handleRollbackChange(activeChange)}
                      style={sketchyShape3}
                      className="flex items-center gap-1 px-3 py-1 text-[13px] font-black border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] bg-[#bf616a] text-paper hover:bg-[#a54e56] transition-all active:translate-y-[1px] active:shadow-none"
                      title="撤销更改（回滚到变更前）"
                    >
                      <Undo2 size={14} strokeWidth={3} /> 撤销
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-auto bg-white font-mono text-[15px] leading-[24px] py-1">
                  {(() => {
                    // 整文件视图：当前磁盘内容为骨架 + 删除行插回原位（红）/新增行（绿）
                    const lines = buildFullDiffView(activeChange.diff, changeContents[activeChange.path] ?? '');
                    if (lines.length === 0) return <div className="p-4 text-xs text-[#4c566a] italic">No visual difference detected.</div>;
                    // 🌟 渲染上限保险：超过 8000 行截断，防止海量 DOM 卡死界面
                    const MAX_RENDER_LINES = 8000;
                    const truncated = lines.length > MAX_RENDER_LINES;
                    const shown = truncated ? lines.slice(0, MAX_RENDER_LINES) : lines;
                    return (<>
                      {oversizedChanges.has(activeChange.path) && (
                        <div className="sticky top-0 z-10 px-3 py-1 bg-[#EBCB8B]/30 border-b-2 border-[#EBCB8B] text-xs font-bold text-ink/70">
                          文件过大（超过 {formatSize(MAX_TEXT_FILE_SIZE)}），仅显示变更片段，完整内容请用终端查看
                        </div>
                      )}
                      {shown.map((ln, i) => {
                      // 选中高亮：new 侧行号落在选中区间内（点击行/Shift+点击选中，Ctrl+U 提取引用）
                      const inSel = !!selectedLines && ln.newNo != null && ln.newNo >= selectedLines.start && ln.newNo <= selectedLines.end;
                      const rowBg = ln.type === 'add' ? 'bg-[#a3be8c]/15' : ln.type === 'del' ? 'bg-[#bf616a]/15' : (inSel ? 'bg-[#88c0d0]/20' : '');
                      return (
                        <div
                          key={i}
                          onClick={(e) => handleDiffRowClick(ln, e.shiftKey)}
                          title="点击选中行（Shift+点击扩展），Ctrl+U 提取为输入框引用"
                          className={`flex cursor-pointer transition-colors ${rowBg} ${inSel ? 'outline outline-1 -outline-offset-1 outline-[#5e81ac]' : ''}`}
                        >
                          <span className="w-9 shrink-0 text-right pr-1.5 select-none text-[12px] text-[#bf616a]/70">{ln.oldNo ?? ''}</span>
                          <span className="w-9 shrink-0 text-right pr-2 select-none text-[12px] text-[#4c566a]/70 border-r-2 border-ink/10 mr-2">{ln.newNo ?? ''}</span>
                          <span className={`w-[3px] shrink-0 ${ln.type === 'add' ? 'bg-[#a3be8c]' : ln.type === 'del' ? 'bg-[#bf616a]' : 'bg-transparent'}`} />
                          <span className={`flex-1 pr-3 whitespace-pre ${ln.type === 'ctx' ? 'text-[#4c566a]' : 'pl-2 text-[#2e3440]'}`}>{ln.text || '\u00A0'}</span>
                        </div>
                      );
                    })}
                      {truncated && (
                        <div className="sticky bottom-0 px-3 py-1 bg-[#EBCB8B]/30 border-t-2 border-[#EBCB8B] text-xs font-bold text-ink/70">
                          内容过长，已截断前 {MAX_RENDER_LINES} 行（共 {lines.length} 行）
                        </div>
                      )}
                    </>);
                  })()}
                </div>
              </div>
            ) : activeFile ? (
              activeFileType === 'image' ? (
                // 图片预览
                <div className="absolute inset-0 flex items-center justify-center bg-white p-4 overflow-auto">
                  <img src={getPreviewUrl(activeFile)} alt={activeFile.split(/[\\/]/).pop()} className="max-w-full max-h-full object-contain" />
                </div>
              ) : activeFileType === 'video' ? (
                // 视频预览
                <div className="absolute inset-0 flex items-center justify-center bg-white p-4">
                  <video src={getPreviewUrl(activeFile)} controls className="max-w-full max-h-full" />
                </div>
              ) : activeFileType === 'binary' ? (
                // 二进制文件 — 不会到这里，因为 openFile 拦截了
                <div className="absolute inset-0 flex flex-col items-center justify-center text-[#4c566a] select-none">
                  <AlertCircle size={48} strokeWidth={1.5} className="mb-3 opacity-40" />
                  <p className="font-semibold text-sm">Binary file — cannot display</p>
                </div>
              ) : activeFileType === 'markdown' && isMdPreview ? (
                // Markdown 预览模式（ReactMarkdown + GFM：支持表格/代码块/任务列表/删除线/嵌套列表等完整语法）
                <div
                  className="absolute inset-0 overflow-auto p-6 text-[#2e3440] text-sm leading-relaxed bg-white"
                  onClick={(e) => {
                    // 拦截链接点击：交给统一路由（http→内置浏览器 / 本地文件→对应预览），防止导航离开 IDE
                    const a = (e.target as HTMLElement).closest('a');
                    if (a) {
                      e.preventDefault();
                      const h = a.getAttribute('href') || '';
                      if (!h) return;
                      if (onOpenLink) onOpenLink(h);
                      else window.open(h, '_blank');
                    }
                  }}
                >
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={IDE_MARKDOWN_COMPONENTS}
                  >
                    {fileContents[activeFile] || ''}
                  </ReactMarkdown>
                </div>
              ) : (
                // 文本/Markdown 编辑模式：行号槽（点击选中整行，Shift+点击扩展）+ 编辑区
                <div className="absolute inset-0 flex bg-white">
                  {/* 行号槽：与编辑区同 line-height 对齐，滚动同步；超 5000 行不渲染（防 DOM 爆炸） */}
                  <div
                    ref={gutterRef}
                    className="w-14 shrink-0 overflow-hidden bg-[#eceff4] border-r-2 border-ink/10 py-4 select-none"
                    title="点击行号选中整行（Shift+点击扩展范围），Ctrl+U 提取为输入框引用"
                  >
                    {editorLines.length <= 5000 && editorLines.map((_, i) => {
                      const n = i + 1;
                      const inSel = !!selectedLines && n >= selectedLines.start && n <= selectedLines.end;
                      return (
                        <div
                          key={n}
                          onMouseDown={(e) => { e.preventDefault(); handleGutterClick(n, e.shiftKey); }}
                          className={`px-2 text-right font-mono text-[13px] leading-[24px] cursor-pointer transition-colors ${
                            inSel ? 'bg-[#88c0d0] text-ink font-bold' : 'text-[#4c566a]/60 hover:bg-[#d8dee9]'
                          }`}
                        >{n}</div>
                      );
                    })}
                  </div>
                  {/* 🌟 关闭软换行：行号槽按「每逻辑行一行」渲染（line-height 24px 逐行对齐），
                      若允许自动换行，长行会占多行导致后续行号与文本错位；关闭后长行横向滚动、行号永远与文件行一致 */}
                  <textarea
                    ref={editorRef}
                    wrap="off"
                    className="flex-1 min-w-0 p-4 font-mono text-[15px] bg-white outline-none resize-none text-[#2e3440] leading-[24px]"
                    style={{ whiteSpace: 'pre', overflowX: 'auto' }}
                    value={fileContents[activeFile] || ''}
                    onChange={handleEditorChange}
                    spellCheck={false}
                    onScroll={syncGutterScroll}
                    onMouseUp={syncSelectionFromTextarea}
                    onKeyUp={syncSelectionFromTextarea}
                    onKeyDown={(e) => {
                      if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSave(); }
                      // Tab 键插入空格
                      if (e.key === 'Tab') {
                        e.preventDefault();
                        const ta = e.target as HTMLTextAreaElement;
                        const start = ta.selectionStart, end = ta.selectionEnd;
                        const val = ta.value;
                        const newValue = val.substring(0, start) + '  ' + val.substring(end);
                        setFileContents(prev => ({ ...prev, [activeFile!]: newValue }));
                        requestAnimationFrame(() => { ta.selectionStart = ta.selectionEnd = start + 2; });
                      }
                    }}
                  />
                </div>
              )
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-ink/30 select-none gap-3">
                <div style={sketchyShape2} className="w-16 h-16 bg-paper border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center rotate-2">
                  <BookOpen size={28} strokeWidth={2.5} className="text-ink/40" />
                </div>
                <p className="font-black text-lg tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>No file open</p>
                <p className="text-sm font-bold opacity-60">Select a file from the explorer</p>
              </div>
            )}
          </div>

          {/* 水平拖拽条：调节终端高度 */}
          {showTerminal && (
            <div
              onMouseDown={startTerminalResize}
              className="h-1.5 shrink-0 cursor-row-resize bg-paper hover:bg-[#88c0d0]/60 active:bg-[#88c0d0] transition-colors"
              title="拖拽调节高度"
            />
          )}

          {/* Terminal Area — 外框手绘（border-t-4 ink），内容区保持 Nord 深色；高度可拖拽 */}
          {showTerminal && (
            <div style={{ height: terminalHeight }} className="border-t-4 border-ink flex flex-col bg-[#2e3440] shrink-0">
              <div className="px-3 py-1 bg-[#2e3440] border-b-2 border-ink/60 flex justify-between items-center shrink-0">
                <span className="text-[11px] font-black tracking-widest uppercase text-[#88c0d0]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Terminal</span>
                <button onClick={() => setShowTerminal(false)} style={sketchyShape2} className="text-[#d8dee9] hover:text-[#bf616a] border-2 border-[#4c566a] hover:border-ink px-1 transition-colors" title="隐藏终端">
                  <X size={10} strokeWidth={3} />
                </button>
              </div>
              <div className="flex-1 overflow-hidden">
                <IDETerminal visible={showTerminal} />
              </div>
            </div>
          )}

          {!showTerminal && (
            <button
              onClick={() => setShowTerminal(true)}
              className="h-7 border-t-4 border-ink bg-paper flex items-center justify-center text-[11px] font-black tracking-widest uppercase text-ink/50 hover:text-ink transition-colors shrink-0 gap-1.5"
              style={{ fontFamily: '"Comic Sans MS", cursive' }}
            >
              <TerminalSquare size={12} strokeWidth={3} /> Terminal
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
