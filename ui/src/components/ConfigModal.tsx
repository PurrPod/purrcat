// src/components/ConfigModal.tsx
import { useState, useEffect } from 'react';
import {
  Settings, X, Save, FileJson, AlertCircle, Plus, Trash2, RefreshCw,
  ToggleLeft, ToggleRight, Folder, FolderRoot, Info
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './chat/ChatShared';

// 配置标签配置：key -> 中文名 + 说明
const CONFIG_TABS: Array<{ key: string; label: string; tip: string }> = [
  { key: 'settings', label: '全局设置', tip: 'settings.json · data_root 等全局开关（改完需重启）' },
  { key: 'model',    label: '模型配置', tip: 'model.json · LLM / Embedding 配置' },
  { key: 'sensor',   label: '传感器',   tip: 'activate_sensor.json · 钩子/定时任务' },
  { key: 'file',     label: '文件白名单', tip: 'file.json · 文件系统可见范围' },
  { key: 'mcp',      label: 'MCP 服务', tip: 'mcp_config.json · MCP 服务端注册' },
  { key: 'app',      label: '应用白名单', tip: 'app_config.json · 系统可见应用' },
  { key: 'cron',     label: '定时任务', tip: 'cron.json · Cron 表达式任务' },
  { key: 'loop',     label: '循环配置', tip: 'loop.json · Agent Loop 配置' },
];

export default function ConfigModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [activeTab, setActiveTab] = useState<string>('settings');
  const [configData, setConfigData] = useState<any>({});
  const [editMode, setEditMode] = useState<'visual' | 'raw'>('visual'); // 可视化 / 原始JSON
  const [rawJsonStr, setRawJsonStr] = useState<string>('');
  const [configMeta, setConfigMeta] = useState<Record<string, string> | null>(null);

  // ── 新增 key 表单状态 ──
  const [newKey, setNewKey] = useState('');
  const [newType, setNewType] = useState<'string' | 'number' | 'boolean' | 'object' | 'array'>('string');
  const [newValue, setNewValue] = useState('');

  // ── 展开的单个 key 编辑状态（可视化模式下修改 value） ──
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [keyEditStr, setKeyEditStr] = useState<string>('');

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

  // ── 可视化模式：展开某个 key ──
  const toggleKey = (key: string) => {
    if (expandedKey === key) {
      setExpandedKey(null);
      setKeyEditStr('');
      return;
    }
    setExpandedKey(key);
    setKeyEditStr(JSON.stringify(configData[key], null, 2));
  };

  // ── 可视化模式：保存单个 key 的编辑 ──
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

  // ── 可视化模式：删除 key ──
  const handleDeleteKey = (key: string) => {
    const newData = { ...configData };
    delete newData[key];
    setConfigData(newData);
    setRawJsonStr(JSON.stringify(getRawData(newData), null, 2));
    if (expandedKey === key) { setExpandedKey(null); setKeyEditStr(''); }
    toast.success(`[${key}] 已删除，记得点 SAVE ALL 落盘！`);
  };

  // ── 可视化模式：新增 key ──
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
        if (activeTab === 'settings') {
          toast("⚠️ data_root 修改需要重启程序才会生效", { icon: '🔔' });
        }
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
                <div className="break-all text-ink/80">{configMeta.DATA_ROOT}</div>
                {activeTab === 'settings' && (
                  <div className="mt-2 p-2 bg-paper border-2 border-ink rounded text-[11px] text-ink/60 flex items-start gap-1">
                    <Info size={14} className="shrink-0 mt-0.5" />
                    修改 data_root 后必须重启程序才生效
                  </div>
                )}
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
            {/* 顶部：标签说明 + 模式切换 + 保存按钮 */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-3xl font-black text-ink flex items-center gap-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  {currentTabMeta?.label ?? activeTab}
                  <button onClick={() => fetchConfig(activeTab)} title="重新从磁盘加载" className="p-2 border-2 border-ink bg-paper hover:bg-sand active:translate-y-1 transition-all" style={sketchyShape3}>
                    <RefreshCw size={18} strokeWidth={3} />
                  </button>
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

            {/* ── 编辑模式：可视化 ── */}
            {editMode === 'visual' && (
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
                      placeholder="Key 名称，例：data_root"
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
    </div>
  );
}
