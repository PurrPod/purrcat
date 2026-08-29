// src/components/ConfigModal.tsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Settings, X, Save, FileJson, AlertCircle, Plus, Trash2, RefreshCw,
  ToggleLeft, ToggleRight, Folder, FolderRoot, Info, HardDrive, Pencil,
  Loader2, Server, Cpu, Eye, Store
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './chat/ChatShared';

// 配置标签配置：key -> 中文名 + 说明（全局 settings 不再提供编辑页，数据根目录走侧栏迁移入口）
const CONFIG_TABS: Array<{ key: string; label: string; tip: string }> = [
  { key: 'model',    label: '模型配置', tip: 'model.json · 核心模型 / 后台模型 / 视觉顾问' },
  { key: 'sensor',   label: '传感器',   tip: 'activate_sensor.json · 钩子/定时任务' },
  { key: 'file',     label: '文件白名单', tip: 'file.json · 文件系统可见范围' },
  { key: 'mcp',      label: 'MCP 服务', tip: 'mcp_config.json · MCP 服务端注册' },
  { key: 'app',     label: '应用白名单', tip: 'app_config.json · 系统可见应用' },
];

// ── 模型配置页：三个模型角色 ──
const MODEL_CATEGORIES = [
  { key: 'main',   label: '核心模型', desc: 'Agent 对话主脑',          icon: Cpu },
  { key: 'task',   label: '后台模型', desc: '后台任务 / 工作流执行',   icon: Server },
  { key: 'vision', label: '视觉顾问', desc: '图片 / 视频多模态理解',   icon: Eye },
] as const;

// 目前支持的 SDK（key 前缀）
const MODEL_SDKS = ['openai'];

// 限流参数默认值（核心/后台模型）
const MODEL_LIMIT_DEFAULTS = {
  rpm: '60',
  tpm: '1000000',
  concurrency: '3',
  max_token: '500000',
};

type ModelForm = {
  sdk: string;
  modelName: string;
  apiKey: string;
  baseUrl: string;
  rpm: string;
  tpm: string;
  concurrency: string;
  maxToken: string;
};

const MCP_NEW_SERVER_TEMPLATE = '{\n  "command": "npx",\n  "args": [],\n  "env": {}\n}';

export default function ConfigModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const purrcat = (window as any).purrcat;
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>('model');
  const [configData, setConfigData] = useState<any>({});
  const [editMode, setEditMode] = useState<'visual' | 'raw'>('visual'); // 可视化 / 原始JSON
  const [rawJsonStr, setRawJsonStr] = useState<string>('');
  const [configMeta, setConfigMeta] = useState<Record<string, string> | null>(null);

  // ── 通用 key-value 编辑状态 ──
  const [newKey, setNewKey] = useState('');
  const [newType, setNewType] = useState<'string' | 'number' | 'boolean' | 'object' | 'array'>('string');
  const [newValue, setNewValue] = useState('');
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [keyEditStr, setKeyEditStr] = useState('');

  // ── 模型配置页状态 ──
  const [modelFormCat, setModelFormCat] = useState<string | null>(null);
  const [modelForm, setModelForm] = useState<ModelForm | null>(null);

  // ── MCP 配置页状态 ──
  const [mcpExpanded, setMcpExpanded] = useState<string | null>(null);
  const [mcpEditStr, setMcpEditStr] = useState('');
  const [newServerName, setNewServerName] = useState('');
  const [newServerJson, setNewServerJson] = useState(MCP_NEW_SERVER_TEMPLATE);

  // ── 数据根目录迁移状态 ──
  const [pendingRoot, setPendingRoot] = useState<string | null>(null); // 待确认的新目录
  const [migrating, setMigrating] = useState(false);

  // 如果数据被包过 __ARRAY_WRAPPER__，保存和 raw 显示时要解包
  const getRawData = (d: any) => {
    if (d && typeof d === 'object' && !Array.isArray(d) && Object.keys(d).length === 1 && '__ARRAY_WRAPPER__' in d) {
      return d.__ARRAY_WRAPPER__;
    }
    return d;
  };

  const resetNewKeyForm = () => {
    setNewKey('');
    setNewType('string');
    setNewValue('');
  };

  // ── 加载 meta（路径信息） ──
  const fetchMeta = async () => {
    try {
      const res = await fetch('/api/config/meta');
      if (res.ok) setConfigMeta(await res.json());
    } catch { /* noop */ }
  };

  // ── 加载配置 ──
  const fetchConfig = async (tab: string) => {
    try {
      const res = await fetch(`/api/config/${tab}`);
      if (res.ok) {
        let data = await res.json();
        if (data === null || typeof data !== 'object') data = {};
        if (Array.isArray(data)) data = { __ARRAY_WRAPPER__: data };
        setConfigData(data);
        setRawJsonStr(JSON.stringify(getRawData(data), null, 2));
        setExpandedKey(null);
        setKeyEditStr('');
        setModelFormCat(null);
        setModelForm(null);
        setMcpExpanded(null);
        setMcpEditStr('');
        resetNewKeyForm();
      } else {
        toast.error(`无法加载 ${tab} 配置`);
      }
    } catch {
      toast.error("网络错误，无法连接后端");
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchMeta();
      fetchConfig(activeTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, activeTab]);

  // ── 数据根目录迁移：选目录 → 确认 → 搬迁+重启 ──
  const pickDataRoot = async () => {
    if (!purrcat?.openDialog) { toast('当前环境不支持选择文件夹', { icon: '🔔' }); return; }
    const dirs = await purrcat.openDialog({ directory: true });
    if (dirs && dirs.length > 0) setPendingRoot(dirs[0]);
  };

  const confirmDataRootChange = async () => {
    if (!pendingRoot) return;
    setMigrating(true);
    try {
      const res = await fetch('/api/config/change-data-root', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data_root: pendingRoot }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setPendingRoot(null);
        toast.success(data?.message || '数据已搬迁，即将重启生效');
        // 搬迁落盘完成后重启，data_root 重启后才会真正生效
        setTimeout(() => {
          if (purrcat?.restartApp) purrcat.restartApp();
          else window.location.reload();
        }, 1500);
      } else {
        toast.error(typeof data?.detail === 'string' ? data.detail : '数据目录迁移失败');
      }
    } catch {
      toast.error('网络错误，无法连接后端');
    } finally {
      setMigrating(false);
    }
  };

  // ══════════════ 模型配置页逻辑 ══════════════

  const buildModelForm = (cat: string): ModelForm => {
    const catCfg = configData?.[cat];
    const form: ModelForm = {
      sdk: 'openai',
      modelName: '',
      apiKey: '',
      baseUrl: '',
      rpm: MODEL_LIMIT_DEFAULTS.rpm,
      tpm: MODEL_LIMIT_DEFAULTS.tpm,
      concurrency: MODEL_LIMIT_DEFAULTS.concurrency,
      maxToken: MODEL_LIMIT_DEFAULTS.max_token,
    };
    if (catCfg && typeof catCfg === 'object' && !Array.isArray(catCfg)) {
      const entryKey = Object.keys(catCfg)[0];
      if (entryKey) {
        form.modelName = entryKey.includes(':') ? entryKey.split(':').slice(1).join(':') : entryKey;
        const entry = catCfg[entryKey] || {};
        form.apiKey = Array.isArray(entry.api_keys) && entry.api_keys.length ? String(entry.api_keys[0]) : '';
        form.baseUrl = entry.base_url || '';
        form.rpm = entry.rpm != null ? String(entry.rpm) : MODEL_LIMIT_DEFAULTS.rpm;
        form.tpm = entry.tpm != null ? String(entry.tpm) : MODEL_LIMIT_DEFAULTS.tpm;
        form.concurrency = entry.concurrency != null ? String(entry.concurrency) : MODEL_LIMIT_DEFAULTS.concurrency;
        form.maxToken = entry.max_token != null ? String(entry.max_token) : MODEL_LIMIT_DEFAULTS.max_token;
      }
    }
    return form;
  };

  const openModelForm = (cat: string) => {
    if (modelFormCat === cat) { setModelFormCat(null); setModelForm(null); return; }
    setModelFormCat(cat);
    setModelForm(buildModelForm(cat));
  };

  const applyModelForm = () => {
    if (!modelFormCat || !modelForm) return;
    const f = modelForm;
    if (!f.modelName.trim()) { toast.error('请填写模型名'); return; }
    if (!f.apiKey.trim()) { toast.error('请填写 API Key'); return; }
    if (!f.baseUrl.trim()) { toast.error('请填写 Base URL'); return; }

    const entryKey = `${f.sdk}:${f.modelName.trim()}`;
    const entry: any = {
      api_keys: [f.apiKey.trim()],
      base_url: f.baseUrl.trim(),
    };
    // 视觉顾问只需要 sdk / 模型名 / baseurl / apikey
    if (modelFormCat !== 'vision') {
      entry.rpm = Number(f.rpm) || Number(MODEL_LIMIT_DEFAULTS.rpm);
      entry.tpm = Number(f.tpm) || Number(MODEL_LIMIT_DEFAULTS.tpm);
      entry.concurrency = Number(f.concurrency) || Number(MODEL_LIMIT_DEFAULTS.concurrency);
      entry.max_token = Number(f.maxToken) || Number(MODEL_LIMIT_DEFAULTS.max_token);
    }

    const newData = { ...configData, [modelFormCat]: { [entryKey]: entry } };
    setConfigData(newData);
    setRawJsonStr(JSON.stringify(getRawData(newData), null, 2));
    setModelFormCat(null);
    setModelForm(null);
    toast.success('已暂存到内存，记得点 SAVE ALL 落盘！');
  };

  const modelEntrySummary = (cat: string): string => {
    const catCfg = configData?.[cat];
    if (!catCfg || typeof catCfg !== 'object' || Array.isArray(catCfg)) return '未配置';
    const entryKey = Object.keys(catCfg)[0];
    if (!entryKey) return '未配置';
    return entryKey;
  };

  // ══════════════ MCP 配置页逻辑 ══════════════

  const getMcpServers = (): Record<string, any> => {
    const s = configData?.mcpServers;
    return s && typeof s === 'object' && !Array.isArray(s) ? s : {};
  };

  const setMcpServers = (servers: Record<string, any>) => {
    const newData = { ...configData, mcpServers: servers };
    setConfigData(newData);
    setRawJsonStr(JSON.stringify(getRawData(newData), null, 2));
  };

  const toggleMcpServer = (name: string) => {
    if (mcpExpanded === name) { setMcpExpanded(null); setMcpEditStr(''); return; }
    setMcpExpanded(name);
    setMcpEditStr(JSON.stringify(getMcpServers()[name], null, 2));
  };

  const saveMcpServer = (name: string) => {
    try {
      const parsed = JSON.parse(mcpEditStr);
      const servers = { ...getMcpServers(), [name]: parsed };
      setMcpServers(servers);
      setMcpExpanded(null);
      setMcpEditStr('');
      toast.success(`[${name}] 已修改，记得点 SAVE ALL 落盘！`);
    } catch {
      toast.error('JSON 格式不合法，无法保存此服务器');
    }
  };

  const deleteMcpServer = (name: string) => {
    const servers = { ...getMcpServers() };
    delete servers[name];
    setMcpServers(servers);
    if (mcpExpanded === name) { setMcpExpanded(null); setMcpEditStr(''); }
    toast.success(`[${name}] 已删除，记得点 SAVE ALL 落盘！`);
  };

  const addMcpServer = () => {
    const name = newServerName.trim();
    if (!name) { toast.error('请输入服务器名称'); return; }
    const servers = getMcpServers();
    if (name in servers) { toast.error('该服务器已存在，想修改请展开它'); return; }
    let parsed: any;
    try {
      parsed = JSON.parse(newServerJson || '{}');
    } catch {
      toast.error('服务器配置不是合法 JSON');
      return;
    }
    setMcpServers({ ...servers, [name]: parsed });
    setNewServerName('');
    setNewServerJson(MCP_NEW_SERVER_TEMPLATE);
    toast.success(`已添加 [${name}]，记得点 SAVE ALL 落盘！`);
  };

  // ══════════════ 通用 key-value 逻辑 ══════════════

  const toggleKey = (key: string) => {
    if (expandedKey === key) {
      setExpandedKey(null);
      setKeyEditStr('');
      return;
    }
    setExpandedKey(key);
    setKeyEditStr(JSON.stringify(configData[key], null, 2));
  };

  const handleSaveKey = async (key: string) => {
    try {
      const parsed = JSON.parse(keyEditStr);
      const newData = { ...configData, [key]: parsed };
      setConfigData(newData);
      setRawJsonStr(JSON.stringify(getRawData(newData), null, 2));
      setExpandedKey(null);
      toast.success(`[${key}] 已修改，记得点 SAVE ALL 落盘！`);
    } catch {
      toast.error("JSON 格式不合法，无法保存此项");
    }
  };

  const handleDeleteKey = (key: string) => {
    const newData = { ...configData };
    delete newData[key];
    setConfigData(newData);
    setRawJsonStr(JSON.stringify(getRawData(newData), null, 2));
    if (expandedKey === key) { setExpandedKey(null); setKeyEditStr(''); }
    toast.success(`[${key}] 已删除，记得点 SAVE ALL 落盘！`);
  };

  const handleAddKey = () => {
    if (!newKey.trim()) { toast.error("请输入 key 名称"); return; }
    if (newKey in configData) { toast.error("该 key 已存在，想修改请展开它"); return; }

    let parsed: any;
    try {
      switch (newType) {
        case 'string':  parsed = newValue; break;
        case 'number':  parsed = Number(newValue); if (isNaN(parsed)) throw new Error(); break;
        case 'boolean': parsed = newValue.toLowerCase() === 'true' ? true : false; break;
        case 'object':
        case 'array':   parsed = JSON.parse(newValue || (newType === 'object' ? '{}' : '[]')); break;
      }
    } catch {
      toast.error(`值格式不合法（${newType}）`);
      return;
    }

    const newData = { ...configData, [newKey.trim()]: parsed };
    setConfigData(newData);
    setRawJsonStr(JSON.stringify(getRawData(newData), null, 2));
    resetNewKeyForm();
    toast.success(`已添加 [${newKey}]，记得点 SAVE ALL 落盘！`);
  };

  // ── 整体保存（可视化模式和 raw 模式统一走这里） ──
  const handleSaveAll = async () => {
    try {
      let payload: any;
      if (editMode === 'visual') {
        payload = getRawData(configData);
      } else {
        payload = JSON.parse(rawJsonStr);
      }
      const res = await fetch(`/api/config/${activeTab}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success("🎉 配置已成功保存到磁盘！");
        fetchConfig(activeTab);
      } else {
        toast.error("保存失败：后端拒绝请求");
      }
    } catch {
      toast.error("保存失败：JSON 格式不合法或网络错误");
    }
  };

  // ── 模式切换 ──
  const switchToRaw = () => {
    setRawJsonStr(JSON.stringify(getRawData(configData), null, 2));
    setEditMode('raw');
  };
  const switchToVisual = () => {
    try {
      let parsed = JSON.parse(rawJsonStr);
      if (Array.isArray(parsed)) parsed = { __ARRAY_WRAPPER__: parsed };
      if (parsed === null || typeof parsed !== 'object') throw new Error();
      setConfigData(parsed);
      setEditMode('visual');
    } catch {
      toast.error("原始 JSON 不是对象/数组，无法切回可视化模式");
    }
  };

  const currentTabMeta = CONFIG_TABS.find(t => t.key === activeTab);

  if (!isOpen) return null;

  const inputCls = "w-full bg-[#FDF8F0] border-4 border-ink px-4 py-2.5 font-mono font-bold text-[14px] focus:outline-none focus:bg-white";
  const labelCls = "text-xs font-black text-ink/50 tracking-widest mb-1";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 md:p-8 pointer-events-auto">
      <div style={sketchyShape2} className="bg-cream border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-7xl h-[90vh] flex flex-col relative">
        <div className="absolute -top-4 left-1/4 w-32 h-10 bg-terracotta/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>
        <button onClick={onClose} className="absolute top-4 right-6 hover:rotate-90 hover:text-terracotta transition-all z-10 p-2 bg-paper border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape3}><X size={28} strokeWidth={4} /></button>

        <div className="flex flex-row h-full overflow-hidden">
          {/* 左侧：标签栏 */}
          <div className="w-64 shrink-0 border-r-4 border-ink/20 flex flex-col p-6 gap-6 overflow-y-auto">
            <div className="flex items-center gap-3">
              <Settings size={36} strokeWidth={2.5} className="text-terracotta" />
              <h2 className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CONFIG</h2>
            </div>

            {/* 路径信息条 */}
            {configMeta && (
              <div style={sketchyShape1} className="bg-[#EBCB8B]/30 border-2 border-ink border-dashed p-3 flex flex-col gap-2 text-xs font-bold">
                <div className="flex items-center gap-2 text-terracotta"><FolderRoot size={16} /> 配置目录</div>
                <div className="break-all text-ink/80">{configMeta.PURRCAT_DIR}</div>
                <div className="flex items-center gap-2 text-[#a3be8c] mt-1"><Folder size={16} /> 数据根目录</div>
                <div className="flex items-start gap-1">
                  <div className="break-all text-ink/80 flex-1">{configMeta.DATA_ROOT}</div>
                  <button
                    onClick={pickDataRoot}
                    title="更改数据根目录（自动搬迁数据并重启）"
                    className="shrink-0 p-1 border-2 border-ink bg-paper hover:bg-[#a3be8c] transition-all active:translate-y-0.5"
                    style={sketchyShape3}
                  >
                    <Pencil size={13} strokeWidth={3} />
                  </button>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-3">
              {CONFIG_TABS.map((tab, idx) => {
                const isActive = activeTab === tab.key;
                const rotation = idx % 2 === 0 ? 'rotate-1' : '-rotate-1';
                const shape = idx % 3 === 0 ? sketchyShape1 : idx % 2 === 0 ? sketchyShape2 : sketchyShape3;
                return (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    style={shape}
                    className={`px-4 py-2 font-black border-4 border-ink uppercase tracking-wider transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] text-left ${isActive ? 'bg-[#EBCB8B] text-ink -translate-x-1' : 'bg-paper text-ink/70 hover:bg-sand'} ${rotation}`}
                  >
                    <div className="text-base" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{tab.label}</div>
                    <div className="text-[10px] font-bold opacity-60 normal-case tracking-normal mt-0.5">{tab.key}.json</div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 右侧：编辑区 */}
          <div className="flex-1 overflow-y-auto p-6 md:p-8 flex flex-col gap-4">
            {/* 顶部：标签说明 + 模式切换 + 保存按钮（右侧留白避开右上角关闭按钮） */}
            <div className="flex flex-wrap items-center justify-between gap-3 pr-16">
              <div>
                <div className="text-3xl font-black text-ink flex items-center gap-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  {currentTabMeta?.label ?? activeTab}
                  <button onClick={() => fetchConfig(activeTab)} title="重新从磁盘加载" className="p-2 border-2 border-ink bg-paper hover:bg-sand active:translate-y-1 transition-all" style={sketchyShape3}>
                    <RefreshCw size={18} strokeWidth={3} />
                  </button>
                  {(activeTab === 'mcp' || activeTab === 'sensor') && (
                    <button
                      onClick={() => { onClose(); navigate(`/market?tab=${activeTab}`); }}
                      title={activeTab === 'mcp' ? '前往市场浏览 / 安装 MCP 服务' : '前往市场浏览 / 安装传感器'}
                      className="p-2 border-2 border-ink bg-paper hover:bg-[#EBCB8B] active:translate-y-1 transition-all flex items-center gap-1"
                      style={sketchyShape3}
                    >
                      <Store size={18} strokeWidth={3} />
                    </button>
                  )}
                </div>
                <div className="text-sm font-bold text-ink/50 mt-1">{currentTabMeta?.tip}</div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={editMode === 'visual' ? switchToRaw : switchToVisual}
                  style={sketchyShape2}
                  className="flex items-center gap-2 px-4 py-2 bg-paper border-4 border-ink font-black shadow-[3px_3px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 transition-all"
                >
                  {editMode === 'visual' ? <ToggleLeft size={20} strokeWidth={3} /> : <ToggleRight size={20} strokeWidth={3} className="text-[#a3be8c]" />}
                  <span>{editMode === 'visual' ? '可视化编辑' : '原始 JSON 编辑'}</span>
                </button>

                <button
                  onClick={handleSaveAll}
                  style={sketchyShape1}
                  className="px-6 py-2 bg-[#a3be8c] border-4 border-ink text-ink font-black flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all rotate-1"
                >
                  <Save size={20} strokeWidth={3} /> SAVE ALL
                </button>
              </div>
            </div>

            {/* ── 编辑模式：原始 JSON ── */}
            {editMode === 'raw' && (
              <div style={sketchyShape3} className="bg-paper border-4 border-ink p-4 flex flex-col gap-3 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)] flex-1">
                <div className="flex items-center gap-2 text-ink/60 font-bold text-sm bg-terracotta/10 p-2 border-2 border-ink border-dashed" style={sketchyShape1}>
                  <AlertCircle size={16} strokeWidth={3} /> 直接编辑完整 JSON。保存时整体覆盖写盘。
                </div>
                <textarea
                  value={rawJsonStr}
                  onChange={(e) => setRawJsonStr(e.target.value)}
                  className="flex-1 min-h-[50vh] bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-[14px] leading-relaxed font-bold focus:outline-none focus:bg-white resize-y"
                  spellCheck={false}
                />
              </div>
            )}

            {/* ── 编辑模式：可视化 · 模型配置 ── */}
            {editMode === 'visual' && activeTab === 'model' && (
              <div className="flex flex-col gap-5 flex-1">
                {MODEL_CATEGORIES.map((cat, idx) => {
                  const CatIcon = cat.icon;
                  const isEditing = modelFormCat === cat.key;
                  const itemShape = idx % 2 === 0 ? sketchyShape2 : sketchyShape1;
                  return (
                    <div key={cat.key} className="flex flex-col gap-2">
                      <div style={itemShape} className={`w-full border-4 border-ink transition-all ${isEditing ? 'bg-ink text-paper shadow-none' : 'bg-paper text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}>
                        <button onClick={() => openModelForm(cat.key)} className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-black/5 transition-colors">
                          <div className="flex items-center gap-3 min-w-0">
                            <CatIcon size={26} strokeWidth={2.5} className={isEditing ? 'text-terracotta' : 'text-[#EBCB8B]'} />
                            <div className="min-w-0">
                              <div className="text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{cat.label}</div>
                              <div className={`text-xs font-bold opacity-60 mt-1 truncate ${isEditing ? 'text-paper/60' : 'text-ink/60'}`}>
                                {cat.desc} · <span className="font-mono">{modelEntrySummary(cat.key)}</span>
                              </div>
                            </div>
                          </div>
                          <span className="font-bold opacity-50 shrink-0">{isEditing ? 'CLOSE' : 'EDIT'}</span>
                        </button>
                      </div>

                      {isEditing && modelForm && (
                        <div style={sketchyShape3} className="bg-paper border-4 border-ink p-5 flex flex-col gap-4 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)]">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <div className={labelCls}>SDK</div>
                              <select
                                value={modelForm.sdk}
                                onChange={(e) => setModelForm({ ...modelForm, sdk: e.target.value })}
                                className="w-full bg-[#FDF8F0] border-4 border-ink px-4 py-2.5 font-black focus:outline-none focus:bg-white"
                              >
                                {MODEL_SDKS.map(s => <option key={s} value={s}>{s}</option>)}
                              </select>
                            </div>
                            <div>
                              <div className={labelCls}>模型名（MODEL NAME）</div>
                              <input
                                value={modelForm.modelName}
                                onChange={(e) => setModelForm({ ...modelForm, modelName: e.target.value })}
                                placeholder="例：deepseek-v4-flash"
                                className={inputCls}
                                spellCheck={false}
                              />
                            </div>
                            <div>
                              <div className={labelCls}>API KEY</div>
                              <input
                                value={modelForm.apiKey}
                                onChange={(e) => setModelForm({ ...modelForm, apiKey: e.target.value })}
                                placeholder="sk-..."
                                type="password"
                                className={inputCls}
                                spellCheck={false}
                              />
                            </div>
                            <div>
                              <div className={labelCls}>BASE URL</div>
                              <input
                                value={modelForm.baseUrl}
                                onChange={(e) => setModelForm({ ...modelForm, baseUrl: e.target.value })}
                                placeholder="https://api.deepseek.com"
                                className={inputCls}
                                spellCheck={false}
                              />
                            </div>
                          </div>

                          {/* 限流参数（视觉顾问不需要） */}
                          {modelFormCat !== 'vision' && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2 border-t-2 border-ink/10 border-dashed">
                              <div>
                                <div className={labelCls}>RPM</div>
                                <input value={modelForm.rpm} onChange={(e) => setModelForm({ ...modelForm, rpm: e.target.value })} className={inputCls} type="number" spellCheck={false} />
                              </div>
                              <div>
                                <div className={labelCls}>TPM</div>
                                <input value={modelForm.tpm} onChange={(e) => setModelForm({ ...modelForm, tpm: e.target.value })} className={inputCls} type="number" spellCheck={false} />
                              </div>
                              <div>
                                <div className={labelCls}>CONCURRENCY</div>
                                <input value={modelForm.concurrency} onChange={(e) => setModelForm({ ...modelForm, concurrency: e.target.value })} className={inputCls} type="number" spellCheck={false} />
                              </div>
                              <div>
                                <div className={labelCls}>MAX TOKEN</div>
                                <input value={modelForm.maxToken} onChange={(e) => setModelForm({ ...modelForm, maxToken: e.target.value })} className={inputCls} type="number" spellCheck={false} />
                              </div>
                            </div>
                          )}

                          <div className="flex justify-end">
                            <button
                              onClick={applyModelForm}
                              style={sketchyShape1}
                              className="px-6 py-2 bg-[#a3be8c] border-4 border-ink text-ink font-black flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all rotate-1"
                            >
                              <Save size={18} strokeWidth={3} /> 应用修改（暂存内存）
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                <div className="text-xs font-bold text-ink/40 flex items-start gap-1">
                  <Info size={14} className="shrink-0 mt-0.5" />
                  修改后暂存内存，点右上角 SAVE ALL 落盘并热重载模型；视觉顾问仅需 SDK / 模型名 / Base URL / API Key。
                </div>
              </div>
            )}

            {/* ── 编辑模式：可视化 · MCP 服务（按单服务器拆分） ── */}
            {editMode === 'visual' && activeTab === 'mcp' && (
              <div className="flex flex-col gap-5 flex-1">
                {(() => {
                  const servers = getMcpServers();
                  const names = Object.keys(servers);
                  if (names.length === 0) {
                    return (
                      <div className="text-center font-bold text-ink/40 mt-10 text-2xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                        空配置 — 可以在下方添加
                      </div>
                    );
                  }
                  return names.map((name, idx) => {
                    const isExpanded = mcpExpanded === name;
                    const cfg = servers[name] || {};
                    const valType = Array.isArray(cfg) ? 'array' : typeof cfg;
                    const valPreview = JSON.stringify(cfg).slice(0, 80) + (JSON.stringify(cfg).length > 80 ? '...' : '');
                    const itemShape = idx % 2 === 0 ? sketchyShape2 : sketchyShape1;
                    return (
                      <div key={name} className="flex flex-col gap-2">
                        <div style={itemShape} className={`w-full border-4 border-ink transition-all ${isExpanded ? 'bg-ink text-paper shadow-none' : 'bg-paper text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}>
                          <div className="flex items-stretch">
                            <button onClick={() => toggleMcpServer(name)} className="flex-1 flex items-center justify-between gap-3 p-4 text-left hover:bg-black/5 transition-colors">
                              <div className="flex items-center gap-3">
                                <Server size={22} strokeWidth={2.5} className={isExpanded ? 'text-terracotta' : 'text-[#88c0d0]'} />
                                <div>
                                  <div className="text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{name}</div>
                                  <div className={`text-xs font-bold opacity-60 mt-1 ${isExpanded ? 'text-paper/60' : 'text-ink/60'}`}>
                                    type: <span className="px-2 py-0.5 border-2 border-current rounded mr-2">{valType}</span>
                                    <span className="break-all">{valPreview}</span>
                                  </div>
                                </div>
                              </div>
                              <span className="font-bold opacity-50 shrink-0">{isExpanded ? 'CLOSE' : 'EDIT'}</span>
                            </button>
                            <button
                              onClick={() => deleteMcpServer(name)}
                              title="删除此服务器"
                              className={`shrink-0 px-4 border-l-4 border-ink flex items-center gap-2 font-black transition-colors ${isExpanded ? 'hover:bg-terracotta' : 'hover:bg-terracotta hover:text-paper'}`}
                            >
                              <Trash2 size={18} strokeWidth={3} />
                            </button>
                          </div>
                        </div>
                        {isExpanded && (
                          <div style={sketchyShape3} className="bg-paper border-4 border-ink p-4 flex flex-col gap-3 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)]">
                            <div className="flex items-center gap-2 text-ink/60 font-bold text-sm bg-terracotta/10 p-2 border-2 border-ink border-dashed" style={sketchyShape1}>
                              <AlertCircle size={16} strokeWidth={3} /> 修改 value（保持合法 JSON，字符串要加引号）
                            </div>
                            <textarea
                              value={mcpEditStr}
                              onChange={(e) => setMcpEditStr(e.target.value)}
                              className="w-full h-56 bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-[14px] leading-relaxed font-bold focus:outline-none focus:bg-white resize-y"
                              spellCheck={false}
                            />
                            <div className="flex justify-end">
                              <button
                                onClick={() => saveMcpServer(name)}
                                style={sketchyShape1}
                                className="px-6 py-2 bg-[#a3be8c] border-4 border-ink text-ink font-black flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all rotate-1"
                              >
                                <Save size={18} strokeWidth={3} /> 应用修改（暂存内存）
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  });
                })()}

                {/* 新增 MCP 服务器区域 */}
                <div style={sketchyShape2} className="bg-[#EBCB8B]/20 border-4 border-ink border-dashed p-5 flex flex-col gap-4 shadow-[6px_6px_0px_0px_rgba(26,26,26,0.8)]">
                  <div className="flex items-center gap-3">
                    <div style={sketchyShape3} className="w-10 h-10 bg-[#88c0d0] border-4 border-ink flex items-center justify-center text-paper rotate-3">
                      <Plus size={22} strokeWidth={3} />
                    </div>
                    <div>
                      <div className="text-xl font-black text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>新增 MCP 服务器</div>
                      <div className="text-sm font-bold text-ink/50">填完点击右侧 ADD 按钮，然后记得 SAVE ALL 落盘</div>
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row gap-3">
                    <input
                      value={newServerName}
                      onChange={(e) => setNewServerName(e.target.value)}
                      placeholder="服务器名称，例：github"
                      className="flex-1 md:flex-[2] bg-paper border-4 border-ink px-4 py-3 font-mono font-bold text-base focus:outline-none focus:bg-white"
                      spellCheck={false}
                    />
                    <button
                      onClick={addMcpServer}
                      style={sketchyShape1}
                      className="px-6 py-3 bg-[#88c0d0] border-4 border-ink text-ink font-black flex items-center justify-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#6aa9bb] active:translate-y-1 active:shadow-none transition-all"
                    >
                      <Plus size={20} strokeWidth={3} /> ADD
                    </button>
                  </div>
                  <textarea
                    value={newServerJson}
                    onChange={(e) => setNewServerJson(e.target.value)}
                    className="w-full h-32 bg-paper border-4 border-ink p-3 font-mono text-[13px] leading-relaxed font-bold focus:outline-none focus:bg-white resize-y"
                    spellCheck={false}
                  />
                </div>
              </div>
            )}

            {/* ── 编辑模式：可视化 · 通用 key-value（传感器/文件白名单/应用白名单/定时任务） ── */}
            {editMode === 'visual' && activeTab !== 'model' && activeTab !== 'mcp' && (
              <div className="flex flex-col gap-5 flex-1">
                {Object.keys(configData).length === 0 ? (
                  <div className="text-center font-bold text-ink/40 mt-10 text-2xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                    空配置 — 可以在下方添加
                  </div>
                ) : (
                  Object.keys(configData).map((key, idx) => {
                    if (key === '__ARRAY_WRAPPER__') return null;
                    const isExpanded = expandedKey === key;
                    const val = configData[key];
                    const valType = Array.isArray(val) ? 'array' : typeof val;
                    const valPreview = typeof val === 'object'
                      ? JSON.stringify(val).slice(0, 80) + (JSON.stringify(val).length > 80 ? '...' : '')
                      : String(val).slice(0, 80) + (String(val).length > 80 ? '...' : '');
                    const itemShape = idx % 2 === 0 ? sketchyShape2 : sketchyShape1;

                    return (
                      <div key={key} className="flex flex-col gap-2">
                        <div style={itemShape} className={`w-full border-4 border-ink transition-all ${isExpanded ? 'bg-ink text-paper shadow-none' : 'bg-paper text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}>
                          <div className="flex items-stretch">
                            <button onClick={() => toggleKey(key)} className="flex-1 flex items-center justify-between gap-3 p-4 text-left hover:bg-black/5 transition-colors">
                              <div className="flex items-center gap-3">
                                <FileJson size={22} strokeWidth={2.5} className={isExpanded ? 'text-terracotta' : 'text-[#EBCB8B]'} />
                                <div>
                                  <div className="text-xl font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{key}</div>
                                  <div className={`text-xs font-bold opacity-60 mt-1 ${isExpanded ? 'text-paper/60' : 'text-ink/60'}`}>
                                    type: <span className="px-2 py-0.5 border-2 border-current rounded mr-2">{valType}</span>
                                    <span className="break-all">{valPreview}</span>
                                  </div>
                                </div>
                              </div>
                              <span className="font-bold opacity-50 shrink-0">{isExpanded ? 'CLOSE' : 'EDIT'}</span>
                            </button>
                            <button
                              onClick={() => handleDeleteKey(key)}
                              title="删除此项"
                              className={`shrink-0 px-4 border-l-4 border-ink flex items-center gap-2 font-black transition-colors ${isExpanded ? 'hover:bg-terracotta' : 'hover:bg-terracotta hover:text-paper'}`}
                            >
                              <Trash2 size={18} strokeWidth={3} />
                            </button>
                          </div>
                        </div>
                        {isExpanded && (
                          <div style={sketchyShape3} className="bg-paper border-4 border-ink p-4 flex flex-col gap-3 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)]">
                            <div className="flex items-center gap-2 text-ink/60 font-bold text-sm bg-terracotta/10 p-2 border-2 border-ink border-dashed" style={sketchyShape1}>
                              <AlertCircle size={16} strokeWidth={3} /> 修改 value（保持合法 JSON，字符串要加引号）
                            </div>
                            <textarea
                              value={keyEditStr}
                              onChange={(e) => setKeyEditStr(e.target.value)}
                              className="w-full h-56 bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-[14px] leading-relaxed font-bold focus:outline-none focus:bg-white resize-y"
                              spellCheck={false}
                            />
                            <div className="flex justify-end">
                              <button
                                onClick={() => handleSaveKey(key)}
                                style={sketchyShape1}
                                className="px-6 py-2 bg-[#a3be8c] border-4 border-ink text-ink font-black flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] active:translate-y-1 active:shadow-none transition-all rotate-1"
                              >
                                <Save size={18} strokeWidth={3} /> 应用修改（暂存内存）
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}

                {/* 新增 key 区域 */}
                <div style={sketchyShape2} className="bg-[#EBCB8B]/20 border-4 border-ink border-dashed p-5 flex flex-col gap-4 shadow-[6px_6px_0px_0px_rgba(26,26,26,0.8)]">
                  <div className="flex items-center gap-3">
                    <div style={sketchyShape3} className="w-10 h-10 bg-terracotta border-4 border-ink flex items-center justify-center text-paper rotate-3">
                      <Plus size={22} strokeWidth={3} />
                    </div>
                    <div>
                      <div className="text-xl font-black text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>新增配置项</div>
                      <div className="text-sm font-bold text-ink/50">填完后点击右侧 ADD 按钮，然后记得 SAVE ALL 落盘</div>
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row gap-3">
                    <input
                      value={newKey}
                      onChange={(e) => setNewKey(e.target.value)}
                      placeholder="Key 名称"
                      className="flex-1 md:flex-[2] bg-paper border-4 border-ink px-4 py-3 font-mono font-bold text-base focus:outline-none focus:bg-white"
                    />
                    <select
                      value={newType}
                      onChange={(e) => setNewType(e.target.value as any)}
                      className="md:w-36 bg-paper border-4 border-ink px-3 py-3 font-black focus:outline-none focus:bg-white"
                    >
                      <option value="string">string</option>
                      <option value="number">number</option>
                      <option value="boolean">boolean</option>
                      <option value="object">object (JSON)</option>
                      <option value="array">array (JSON)</option>
                    </select>
                    <input
                      value={newValue}
                      onChange={(e) => setNewValue(e.target.value)}
                      placeholder={newType === 'object' ? '{"a":1}' : newType === 'array' ? '[1,2,3]' : newType === 'boolean' ? 'true/false' : newType === 'number' ? '123' : '字符串值'}
                      className="flex-1 md:flex-[3] bg-paper border-4 border-ink px-4 py-3 font-mono font-bold text-base focus:outline-none focus:bg-white"
                    />
                    <button
                      onClick={handleAddKey}
                      style={sketchyShape1}
                      className="px-6 py-3 bg-[#88c0d0] border-4 border-ink text-ink font-black flex items-center justify-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#6aa9bb] active:translate-y-1 active:shadow-none transition-all"
                    >
                      <Plus size={20} strokeWidth={3} /> ADD
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 数据根目录迁移确认弹窗 ── */}
      {pendingRoot && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-ink/80 backdrop-blur-sm p-4 pointer-events-auto" onClick={() => !migrating && setPendingRoot(null)}>
          <div style={sketchyShape2} className="bg-cream border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-lg flex flex-col relative p-8" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <HardDrive size={36} strokeWidth={2.5} className="text-terracotta" />
              <h3 className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>更换数据根目录</h3>
            </div>

            <div className="flex flex-col gap-3 mb-6 text-[15px] font-bold text-ink/80 leading-relaxed">
              <div style={sketchyShape1} className="bg-paper border-4 border-ink p-4 flex flex-col gap-2">
                <div className="text-xs font-black text-ink/50 tracking-widest">当前数据根目录</div>
                <div className="font-mono text-[14px] font-bold text-ink break-all">{configMeta?.DATA_ROOT}</div>
                <div className="text-xs font-black text-ink/50 tracking-widest mt-2">新数据根目录</div>
                <div className="font-mono text-[14px] font-bold text-[#a3be8c] break-all">{pendingRoot}</div>
              </div>
              <div className="flex items-start gap-2 text-xs font-bold text-ink/50">
                <Info size={14} className="shrink-0 mt-0.5" />
                确认后将把 agent_vm / embedding 等大型数据搬迁到新位置，随后自动重启程序生效。搬迁期间请勿操作。
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={confirmDataRootChange}
                disabled={migrating}
                style={sketchyShape1}
                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-[#a3be8c] border-4 border-ink text-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] hover:-translate-y-0.5 active:translate-y-1 active:shadow-none transition-all disabled:opacity-60 disabled:cursor-wait"
              >
                {migrating ? <Loader2 size={20} strokeWidth={3} className="animate-spin" /> : null}
                {migrating ? '搬迁中…' : '确认搬迁并重启'}
              </button>
              <button
                onClick={() => setPendingRoot(null)}
                disabled={migrating}
                style={sketchyShape3}
                className="px-6 py-3 bg-paper border-4 border-ink text-ink/70 font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:text-ink active:translate-y-1 active:shadow-none transition-all disabled:opacity-60"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
