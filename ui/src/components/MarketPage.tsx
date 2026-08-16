// src/components/MarketPage.tsx
import { useState, useEffect, useMemo, useRef } from 'react';
import { ArrowLeft, Store, RefreshCw, User, AlertCircle, Zap, Server, Activity, GitMerge, X, Copy, Search, LayoutGrid, FolderGit2, Download, Check, ChevronLeft, Loader2, Link2 } from 'lucide-react';
import { toast } from 'react-hot-toast';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

type MarketTab = 'skill' | 'mcp' | 'sensor' | 'graph';
type LayoutMode = 'repo' | 'skill';

// Registry v2.0 的 skill 条目结构
interface SkillEntry {
  name: string;
  desc: string;
  author: string;
  'icon-link'?: string;
  'skill-single-link': string;
  repo: string;
}

// Registry v2.0 的 mcp 条目结构
interface McpEntry {
  name: string;
  desc: string;
  'icon-link'?: string;
  repo: string;
  mcpServers: Record<string, any>;
}

// skill 图标（无 icon-link 时回退为 Zap 圆标）
function SkillIcon({ skill, size = 40 }: { skill: SkillEntry; size?: number }) {
  const [errored, setErrored] = useState(false);
  const icon = skill['icon-link'];
  if (icon && !errored) {
    return (
      <img
        src={icon}
        alt={skill.name}
        width={size}
        height={size}
        onError={() => setErrored(true)}
        className="rounded-full border-2 border-ink object-cover bg-paper shrink-0"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div className="rounded-full border-2 border-ink bg-[#EBCB8B] flex items-center justify-center shrink-0" style={{ width: size, height: size }}>
      <Zap size={Math.round(size * 0.55)} strokeWidth={2.5} className="text-ink" />
    </div>
  );
}

// mcp 图标（无 icon-link 时回退为 Server 圆标）
function McpIcon({ mcp, size = 40 }: { mcp: McpEntry; size?: number }) {
  const [errored, setErrored] = useState(false);
  const icon = mcp['icon-link'];
  if (icon && !errored) {
    return (
      <img
        src={icon}
        alt={mcp.name}
        width={size}
        height={size}
        onError={() => setErrored(true)}
        className="rounded-full border-2 border-ink object-cover bg-paper shrink-0"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div className="rounded-full border-2 border-ink bg-[#88c0d0] flex items-center justify-center shrink-0" style={{ width: size, height: size }}>
      <Server size={Math.round(size * 0.55)} strokeWidth={2.5} className="text-ink" />
    </div>
  );
}

// 从 skill-single-link 推断安装后的本地目录名（与后端逻辑一致）
function expectedDirName(skill: SkillEntry): string {
  const link = skill['skill-single-link'] || '';
  const m = link.match(/github\.com\/[^/]+\/([^/]+)\/tree\/[^/]+(?:\/(.*))?/);
  if (m) {
    const path = (m[2] || '').replace(/\/+$/, '');
    return path ? path.split('/').pop()! : m[1];
  }
  return skill.name;
}

function repoDisplayName(repoUrl: string): string {
  const tail = repoUrl.replace(/\/+$/, '').split('/').pop();
  return tail || repoUrl;
}

function shortDesc(desc: string, n = 30): string {
  if (!desc) return '';
  return desc.length > n ? desc.slice(0, n) + '…' : desc;
}

export default function MarketPage({ onBack }: { onBack: () => void }) {
  const [activeTab, setActiveTab] = useState<MarketTab>('skill');

  const [skillData, setSkillData] = useState<Record<string, SkillEntry>>({});
  const [isFetchingSkill, setIsFetchingSkill] = useState(false);

  const [mcpData, setMcpData] = useState<McpEntry[]>([]);
  const [isFetchingMcp, setIsFetchingMcp] = useState(false);

  // 选中的 MCP 详情信息弹窗 / 安装确认弹窗 / 已配置列表
  const [selectedMcpInfo, setSelectedMcpInfo] = useState<McpEntry | null>(null);
  const [mcpInstallConfirm, setMcpInstallConfirm] = useState<McpEntry | null>(null);
  const [installedMcpNames, setInstalledMcpNames] = useState<Set<string>>(new Set());
  const [installingMcpName, setInstallingMcpName] = useState<string | null>(null);

  // 🌟 Skill 市场新状态：搜索 / 排版切换 / repo 下钻 / 详情弹窗 / 安装状态
  const [searchQuery, setSearchQuery] = useState('');
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('repo');
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillEntry | null>(null);
  const [installedNames, setInstalledNames] = useState<Set<string>>(new Set());
  const [installingSet, setInstallingSet] = useState<Set<string>>(new Set());

  // 🌟 容器宽度监听（ResizeObserver）：字号 / 网格列数 / 侧栏显隐全部按容器实际宽度自适应
  const rootRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1280);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) setContainerWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 侧栏 320px + 间距 24px；容器不足 900px 时隐藏左侧菜单，主内容区至少保留 ~560px
  const showSidebar = containerWidth >= 900;
  const mainWidth = showSidebar ? containerWidth - 344 : containerWidth;
  const cardCols = mainWidth >= 810 ? 'grid-cols-3' : mainWidth >= 540 ? 'grid-cols-2' : 'grid-cols-1';
  const isNarrow = containerWidth < 640;

  const fetchSkillData = async (isManual = false) => {
    setIsFetchingSkill(true);
    try {
      const res = await fetch(`https://raw.githubusercontent.com/PurrPod/skills/main/registry.json?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setSkillData(data.skills || {});
        if (isManual) toast.success("Skills 列表已刷新！");
      }
    } catch {
      toast.error("Skills 仓库请求失败");
    } finally {
      setIsFetchingSkill(false);
    }
  };

  // 拉取本地已安装 skill 列表，建立小写名称集合（含 SKILL.md 的 name 和目录名）
  const fetchLocalSkills = async () => {
    try {
      const res = await fetch('/api/tools/skills');
      if (res.ok) {
        const list: any[] = await res.json();
        const names = new Set<string>();
        for (const s of list) {
          if (s?.name) names.add(String(s.name).toLowerCase());
          if (s?.dir_name) names.add(String(s.dir_name).toLowerCase());
        }
        setInstalledNames(names);
      }
    } catch { /* noop */ }
  };

  const fetchMcpData = async (isManual = false) => {
    setIsFetchingMcp(true);
    try {
      const res = await fetch(`https://raw.githubusercontent.com/PurrPod/mcps/main/registry.json?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setMcpData(Array.isArray(data.mcps) ? data.mcps : Object.values(data.mcps || {}));
        if (isManual) toast.success("MCP Servers 列表已刷新！");
      }
    } catch {
      toast.error("MCP 仓库请求失败");
    } finally {
      setIsFetchingMcp(false);
    }
  };

  // 拉取本地 mcp_config.json 中已配置的 server 名列表（"已安装"检测）
  const fetchLocalMcps = async () => {
    try {
      const res = await fetch('/api/tools/mcp/list');
      if (res.ok) {
        const list: string[] = await res.json();
        setInstalledMcpNames(new Set(list.map(n => n.toLowerCase())));
      }
    } catch { /* noop */ }
  };

  const isMcpInstalled = (mcp: McpEntry) =>
    Object.keys(mcp.mcpServers || {}).some(k => installedMcpNames.has(k.toLowerCase()));

  const confirmInstallMcp = async (mcp: McpEntry) => {
    setInstallingMcpName(mcp.name);
    try {
      const res = await fetch('/api/tools/mcp/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_json: JSON.stringify({ mcpServers: mcp.mcpServers }),
          repo: mcp.repo || '',
        }),
      });
      if (res.ok) {
        const data = await res.json().catch(() => null);
        toast.success(data?.message || `MCP '${mcp.name}' 安装成功！`);
        setMcpInstallConfirm(null);
        await fetchLocalMcps();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'MCP 安装失败');
      }
    } catch {
      toast.error('MCP 安装失败，请检查网络');
    } finally {
      setInstallingMcpName(null);
    }
  };

  useEffect(() => {
    if (activeTab === 'skill') {
      if (Object.keys(skillData).length === 0) fetchSkillData();
      fetchLocalSkills();
    }
    if (activeTab === 'mcp') {
      if (mcpData.length === 0) fetchMcpData();
      fetchLocalMcps();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleRefresh = () => {
    if (activeTab === 'skill') { fetchSkillData(true); fetchLocalSkills(); }
    if (activeTab === 'mcp') { fetchMcpData(true); fetchLocalMcps(); }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('已复制到剪贴板！');
  };

  const isInstalled = (skill: SkillEntry) =>
    installedNames.has(skill.name.toLowerCase()) ||
    installedNames.has(expectedDirName(skill).toLowerCase());

  const handleInstallSkill = async (skill: SkillEntry) => {
    const key = skill.name;
    if (installingSet.has(key) || isInstalled(skill)) return;
    setInstallingSet(prev => new Set(prev).add(key));
    try {
      const res = await fetch('/api/tools/skills/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: skill['skill-single-link'] }),
      });
      if (res.ok) {
        toast.success(`Skill '${skill.name}' 安装成功！`);
        await fetchLocalSkills();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Skill 安装失败');
      }
    } catch {
      toast.error('Skill 安装失败，请检查网络');
    } finally {
      setInstallingSet(prev => { const n = new Set(prev); n.delete(key); return n; });
    }
  };

  // 关键词过滤：匹配 name / desc / repo / author
  const filteredSkills = useMemo(() => {
    const all = Object.values(skillData);
    const q = searchQuery.trim().toLowerCase();
    if (!q) return all;
    return all.filter(s =>
      [s.name, s.desc, s.repo, s.author].some(f => (f || '').toLowerCase().includes(q))
    );
  }, [skillData, searchQuery]);

  // 按 repo 分组
  const repoGroups = useMemo(() => {
    const groups = new Map<string, SkillEntry[]>();
    for (const s of filteredSkills) {
      if (!groups.has(s.repo)) groups.set(s.repo, []);
      groups.get(s.repo)!.push(s);
    }
    return Array.from(groups.entries());
  }, [filteredSkills]);

  const isFetching = activeTab === 'skill' ? isFetchingSkill : isFetchingMcp;

  return (
    <div ref={rootRef} className="absolute inset-0 bg-[#fdfaf5] bg-[radial-gradient(#1a1a1a_1px,transparent_1px)] [background-size:24px_24px] p-6 md:p-8 flex gap-6 overflow-hidden font-sans">

      {/* 🌟 Skill 详情弹窗 */}
      {selectedSkill && (() => {
        const installed = isInstalled(selectedSkill);
        const installing = installingSet.has(selectedSkill.name);
        return (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto" onClick={() => setSelectedSkill(null)}>
            <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-2xl flex flex-col relative rotate-[0.5deg]" onClick={e => e.stopPropagation()}>
              <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#EBCB8B]/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>

              {/* 弹窗 Header */}
              <div className="flex justify-between items-start p-6 border-b-4 border-ink/20 shrink-0 gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  <SkillIcon skill={selectedSkill} size={56} />
                  <div className="min-w-0">
                    <h2 className="text-2xl font-black tracking-wide text-ink break-all" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{selectedSkill.name}</h2>
                    <p className="text-sm font-bold text-ink/60 flex items-center gap-1.5 mt-1"><User size={14} strokeWidth={3} /> {selectedSkill.author || 'Unknown'}</p>
                  </div>
                </div>
                <button onClick={() => setSelectedSkill(null)} className="p-2 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all shrink-0" style={sketchyShape3}>
                  <X size={24} strokeWidth={3} />
                </button>
              </div>

              {/* 弹窗 Body：完整描述 */}
              <div className="p-6 flex-1 overflow-y-auto max-h-[45vh]">
                <span className="font-black text-ink tracking-widest text-sm">DESCRIPTION:</span>
                <p className="text-[15px] font-bold leading-relaxed text-ink/80 mt-3 whitespace-pre-wrap break-words">{selectedSkill.desc || '（暂无描述）'}</p>
                <p className="text-xs font-bold text-ink/40 mt-4 break-all">来源仓库: {selectedSkill.repo}</p>
              </div>

              {/* 弹窗 Footer：link 跳转 + 下载安装 */}
              <div className="p-6 pt-4 border-t-4 border-ink/10 flex items-center justify-end gap-4 shrink-0 flex-wrap">
                <a
                  href={selectedSkill['skill-single-link'] || selectedSkill.repo}
                  target="_blank"
                  rel="noreferrer"
                  title="跳转仓库"
                  style={sketchyShape1}
                  className="w-14 h-14 flex items-center justify-center bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#88c0d0] hover:text-paper transition-all active:translate-y-1 active:shadow-none"
                >
                  <Link2 size={22} strokeWidth={3} />
                </a>
                <button
                  onClick={() => handleInstallSkill(selectedSkill)}
                  disabled={installed || installing}
                  title={installed ? '已安装' : '下载安装'}
                  style={sketchyShape2}
                  className={`h-14 px-6 flex items-center gap-2 border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${
                    installed
                      ? 'bg-[#d8d8d0] text-ink/40 cursor-not-allowed'
                      : installing
                        ? 'bg-[#EBCB8B] text-ink cursor-wait'
                        : 'bg-terracotta text-paper hover:-translate-y-0.5'
                  }`}
                >
                  {installing ? <Loader2 size={22} strokeWidth={3} className="animate-spin" /> : installed ? <Check size={22} strokeWidth={3} /> : <Download size={22} strokeWidth={3} />}
                  <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{installing ? '安装中...' : installed ? '已安装' : '下载'}</span>
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* 🌟 MCP 详情弹窗（Registry v2.0） */}
      {selectedMcpInfo && (() => {
        const installed = isMcpInstalled(selectedMcpInfo);
        const installing = installingMcpName === selectedMcpInfo.name;
        return (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto" onClick={() => setSelectedMcpInfo(null)}>
            <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-3xl flex flex-col relative rotate-[0.5deg]" onClick={e => e.stopPropagation()}>
              <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#EBCB8B]/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>

              {/* 弹窗 Header */}
              <div className="flex justify-between items-start p-6 border-b-4 border-ink/20 shrink-0 gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  <McpIcon mcp={selectedMcpInfo} size={56} />
                  <div className="min-w-0">
                    <h2 className="text-2xl font-black tracking-wide text-ink break-all" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{selectedMcpInfo.name}</h2>
                    <p className="text-xs font-bold text-ink/40 mt-1 break-all">{selectedMcpInfo.repo}</p>
                  </div>
                </div>
                <button onClick={() => setSelectedMcpInfo(null)} className="p-2 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all shrink-0" style={sketchyShape3}>
                  <X size={24} strokeWidth={3} />
                </button>
              </div>

              {/* 弹窗 Body：描述 + mcpServers schema */}
              <div className="p-6 flex-1 overflow-y-auto max-h-[45vh] flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <span className="font-black text-ink tracking-widest text-sm">DESCRIPTION:</span>
                  <p className="text-[15px] font-bold leading-relaxed text-ink/80 whitespace-pre-wrap break-words">{selectedMcpInfo.desc || '（暂无描述）'}</p>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-end">
                    <span className="font-black text-ink tracking-widest text-sm">MCP SERVERS (SCHEMA):</span>
                    <button onClick={() => copyToClipboard(JSON.stringify({ mcpServers: selectedMcpInfo.mcpServers }, null, 2))} className="flex items-center gap-1 text-xs font-black bg-cream border-2 border-ink px-2 py-1 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a3be8c] transition-all active:translate-y-[1px] active:shadow-none" style={sketchyShape2}>
                      <Copy size={12} strokeWidth={3}/> COPY
                    </button>
                  </div>
                  {/* 格式化并渲染 JSON */}
                  <pre style={sketchyShape3} className="bg-[#FDF8F0] border-4 border-ink p-4 overflow-x-auto text-sm font-mono font-bold shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] text-ink">
                    {JSON.stringify({ mcpServers: selectedMcpInfo.mcpServers }, null, 2)}
                  </pre>
                </div>
              </div>

              {/* 弹窗 Footer：link 跳转 + 安装 */}
              <div className="p-6 pt-4 border-t-4 border-ink/10 flex items-center justify-end gap-4 shrink-0 flex-wrap">
                <a
                  href={selectedMcpInfo.repo}
                  target="_blank"
                  rel="noreferrer"
                  title="跳转仓库"
                  style={sketchyShape1}
                  className="w-14 h-14 flex items-center justify-center bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#88c0d0] hover:text-paper transition-all active:translate-y-1 active:shadow-none"
                >
                  <Link2 size={22} strokeWidth={3} />
                </a>
                <button
                  onClick={() => setMcpInstallConfirm(selectedMcpInfo)}
                  disabled={installed || installing}
                  title={installed ? '已安装' : '安装'}
                  style={sketchyShape2}
                  className={`h-14 px-6 flex items-center gap-2 border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${
                    installed
                      ? 'bg-[#d8d8d0] text-ink/40 cursor-not-allowed'
                      : installing
                        ? 'bg-[#EBCB8B] text-ink cursor-wait'
                        : 'bg-[#EBCB8B] text-ink hover:-translate-y-0.5'
                  }`}
                >
                  {installing ? <Loader2 size={22} strokeWidth={3} className="animate-spin" /> : installed ? <Check size={22} strokeWidth={3} /> : <Download size={22} strokeWidth={3} />}
                  <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{installing ? '安装中...' : installed ? '已安装' : '安装'}</span>
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* 🌟 MCP 安装确认弹窗：提示可能需要手动填写 API Key 等字段 */}
      {mcpInstallConfirm && (
        <div className="fixed inset-0 z-[210] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-lg flex flex-col relative rotate-[0.5deg]">
            <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#bf616a]/50 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>

            <div className="flex justify-between items-center p-5 border-b-4 border-ink/20 shrink-0">
              <h3 className="text-xl font-black text-ink tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>安装确认</h3>
              <button onClick={() => setMcpInstallConfirm(null)} className="p-1.5 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all" style={sketchyShape3}>
                <X size={20} strokeWidth={3} />
              </button>
            </div>

            <div className="p-6 flex flex-col gap-4">
              <p className="font-bold text-ink">
                即将安装 <span className="font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{mcpInstallConfirm.name}</span>，其配置将合并到 MCP 配置文件中。
              </p>
              <div className="flex items-start gap-3 bg-[#FDF8F0] border-4 border-ink p-4 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3}>
                <AlertCircle size={22} strokeWidth={2.5} className="text-[#bf616a] shrink-0 mt-0.5" />
                <p className="text-sm font-bold text-ink/80 leading-relaxed">
                  注意：部分 MCP Server 需要手动填写认证字段（如将配置中的
                  <span className="font-mono text-[#bf616a] px-1">{'<your-api-key>'}</span>
                  替换为你的真实 API Key），否则该 MCP 将无法生效。安装完成后，可在设置中编辑 MCP 配置进行填写。
                </p>
              </div>
            </div>

            <div className="p-5 pt-2 border-t-4 border-ink/10 flex justify-end gap-4 shrink-0">
              <button
                onClick={() => setMcpInstallConfirm(null)}
                style={sketchyShape1}
                className="px-5 h-12 flex items-center bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:translate-y-1 active:shadow-none"
              >
                取消
              </button>
              <button
                onClick={() => confirmInstallMcp(mcpInstallConfirm)}
                disabled={installingMcpName === mcpInstallConfirm.name}
                style={sketchyShape2}
                className={`px-5 h-12 flex items-center gap-2 border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${installingMcpName === mcpInstallConfirm.name ? 'bg-[#EBCB8B] text-ink cursor-wait' : 'bg-terracotta text-paper hover:-translate-y-0.5'}`}
              >
                {installingMcpName === mcpInstallConfirm.name && <Loader2 size={18} strokeWidth={3} className="animate-spin" />}
                <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{installingMcpName === mcpInstallConfirm.name ? '安装中...' : '确认安装'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ================= 👈 左侧导航菜单（容器过窄时自动隐藏） ================= */}
      {showSidebar && (
      <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
        <div className="flex gap-4 items-center">
          <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group shrink-0">
            <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
          </button>
          <div style={sketchyShape1} className="flex-1 min-w-0 h-16 flex items-center justify-center gap-2 bg-[#88c0d0] text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2">
            <Store size={22} strokeWidth={2.5} className="shrink-0" />
            <span className="tracking-widest text-lg font-black truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MARKET</span>
          </div>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="flex-1 flex flex-col gap-4 mt-4">

            <button onClick={() => setActiveTab('skill')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'skill' ? 'bg-terracotta text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Zap size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILLS</div>
                <div className="text-xs font-bold opacity-70 truncate">Agent Capabilities</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('mcp')} style={sketchyShape2} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'mcp' ? 'bg-[#EBCB8B] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Server size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP SERVERS</div>
                <div className="text-xs font-bold opacity-70 truncate">Context Providers</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('sensor')} style={sketchyShape3} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'sensor' ? 'bg-[#a3be8c] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Activity size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSORS</div>
                <div className="text-xs font-bold opacity-70 truncate">Autonomous Triggers</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('graph')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'graph' ? 'bg-[#b48ead] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <GitMerge size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>GRAPHS</div>
                <div className="text-xs font-bold opacity-70 truncate">Workflow Templates</div>
              </div>
            </button>

          </div>
        </div>
      </div>
      )}

      {/* ================= 👉 右侧主内容区 ================= */}
      <div style={sketchyShape1} className="flex-1 min-w-0 bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] overflow-hidden relative rotate-[0.5deg] z-10 flex flex-col">

        <div className={`${isNarrow ? 'px-4 pt-4 pb-3' : 'px-10 pt-8 pb-4'} flex items-center justify-between gap-3 shrink-0 border-b-4 border-ink/10 relative z-20 bg-paper`}>
          <div className="flex items-center gap-3 min-w-0">
            {/* 侧栏隐藏后，在标题栏提供返回按钮 */}
            {!showSidebar && (
              <button onClick={onBack} title="返回" style={sketchyShape2} className="p-2 bg-cream border-2 border-ink text-ink hover:bg-sand transition-all shrink-0">
                <ArrowLeft size={20} strokeWidth={3} />
              </button>
            )}
            <div style={sketchyShape2} className="w-12 h-12 bg-ink border-4 border-ink flex items-center justify-center rotate-6 shrink-0">
              {activeTab === 'skill' && <Zap className="text-terracotta" strokeWidth={2.5} />}
              {activeTab === 'mcp' && <Server className="text-[#EBCB8B]" strokeWidth={2.5} />}
              {activeTab === 'sensor' && <Activity className="text-[#a3be8c]" strokeWidth={2.5} />}
              {activeTab === 'graph' && <GitMerge className="text-[#b48ead]" strokeWidth={2.5} />}
            </div>
            <h2 className={`${isNarrow ? 'text-lg' : 'text-3xl'} font-black tracking-widest text-ink uppercase truncate min-w-0`} style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              {activeTab} EXPLORER
            </h2>
          </div>

          <button
            onClick={handleRefresh}
            disabled={isFetching || (activeTab !== 'skill' && activeTab !== 'mcp')}
            style={sketchyShape2}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#EBCB8B] text-ink border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all rotate-2 disabled:opacity-50 shrink-0"
          >
            <RefreshCw size={20} strokeWidth={3} className={isFetching ? "animate-spin text-terracotta" : "text-ink"} />
            {!isNarrow && <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>REFRESH</span>}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto w-full h-full relative bg-cream/30">

          {/* ================= SKILLS 列表渲染（Registry v2.0） ================= */}
          {activeTab === 'skill' && (
            <div className={`${isNarrow ? 'p-4 gap-4' : 'p-8 gap-6'} flex flex-col`}>
              {/* 工具栏：搜索框 + 排版切换 */}
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex-1 min-w-[180px] flex items-center gap-3 bg-paper border-4 border-ink px-4 py-2.5 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape2}>
                  <Search size={18} strokeWidth={3} className="text-ink/40 shrink-0" />
                  <input
                    value={searchQuery}
                    onChange={e => { setSearchQuery(e.target.value); setSelectedRepo(null); }}
                    placeholder="搜索技能名 / 描述 / 仓库 / 作者..."
                    className="flex-1 min-w-0 bg-transparent outline-none font-bold text-ink placeholder:text-ink/40 text-[15px]"
                  />
                  {searchQuery && (
                    <button onClick={() => setSearchQuery('')} className="p-1 text-ink/40 hover:text-ink transition-colors shrink-0">
                      <X size={16} strokeWidth={3} />
                    </button>
                  )}
                </div>

                <div className="flex border-4 border-ink bg-cream shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] overflow-hidden shrink-0" style={sketchyShape1}>
                  <button
                    onClick={() => { setLayoutMode('repo'); setSelectedRepo(null); }}
                    className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm transition-all ${layoutMode === 'repo' ? 'bg-terracotta text-paper' : 'text-ink hover:bg-sand'}`}
                  >
                    <FolderGit2 size={16} strokeWidth={3} className="shrink-0" /> 按仓库
                  </button>
                  <button
                    onClick={() => { setLayoutMode('skill'); setSelectedRepo(null); }}
                    className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm border-l-4 border-ink transition-all ${layoutMode === 'skill' ? 'bg-terracotta text-paper' : 'text-ink hover:bg-sand'}`}
                  >
                    <LayoutGrid size={16} strokeWidth={3} className="shrink-0" /> 按技能
                  </button>
                </div>
              </div>

              {isFetchingSkill && Object.keys(skillData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-terracotta" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Fetching Repositories...</p></div>
              ) : filteredSkills.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{searchQuery ? 'No Match.' : 'Registry is empty.'}</p></div>
              ) : layoutMode === 'repo' && !selectedRepo ? (
                /* ---------- 排版一：按仓库展示 ---------- */
                <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-6'} pb-8`}>
                  {repoGroups.map(([repo, skills], idx) => {
                    const iconSkill = skills.find(s => s['icon-link']) || skills[0];
                    return (
                      <button
                        key={repo}
                        onClick={() => setSelectedRepo(repo)}
                        style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                        className={`bg-paper border-4 border-ink ${isNarrow ? 'p-4' : 'p-6'} flex items-center gap-5 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all text-left ${idx % 3 === 0 ? '-rotate-1' : 'rotate-1'}`}
                      >
                        <SkillIcon skill={iconSkill} size={64} />
                        <div className="flex-1 min-w-0">
                          <h3 className="text-xl font-black truncate text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={repoDisplayName(repo)}>{repoDisplayName(repo)}</h3>
                          <p className="text-sm font-bold text-ink/60 mt-2 flex items-center gap-1.5">
                            <Zap size={14} strokeWidth={3} className="text-terracotta shrink-0" />
                            {skills.length} 个技能
                          </p>
                          <p className="text-xs font-bold text-ink/40 truncate mt-1">by {skills[0].author || 'Unknown'}</p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : layoutMode === 'repo' && selectedRepo ? (
                /* ---------- 排版一（下钻）：某仓库内的技能列表 ---------- */
                <div className="flex flex-col gap-6 pb-8">
                  <button
                    onClick={() => setSelectedRepo(null)}
                    style={sketchyShape1}
                    className="w-fit flex items-center gap-2 px-4 py-2 bg-cream border-4 border-ink text-ink font-black text-sm shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:translate-y-1 active:shadow-none -rotate-1"
                  >
                    <ChevronLeft size={18} strokeWidth={3} /> 返回仓库列表
                  </button>
                  <div className="flex items-center gap-3 min-w-0">
                    <FolderGit2 size={22} strokeWidth={2.5} className="text-terracotta shrink-0" />
                    <span className="text-xl font-black text-ink truncate min-w-0" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{repoDisplayName(selectedRepo)}</span>
                    <span className="text-xs font-black px-2 py-1 bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>{(repoGroups.find(([r]) => r === selectedRepo)?.[1] ?? []).length} skills</span>
                  </div>
                  <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-6'}`}>
                    {(repoGroups.find(([r]) => r === selectedRepo)?.[1] ?? []).map((s, idx) => (
                      <button
                        key={s.name}
                        onClick={() => setSelectedSkill(s)}
                        style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                        className={`bg-paper border-4 border-ink ${isNarrow ? 'p-4' : 'p-5'} flex flex-col gap-2 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 hover:shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] transition-all text-left ${idx % 3 === 0 ? '-rotate-1' : 'rotate-1'}`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <SkillIcon skill={s} size={36} />
                          <h3 className="text-lg font-black truncate text-ink flex-1 min-w-0 text-left" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={s.name}>{s.name}</h3>
                        </div>
                        <p className="text-sm font-bold text-ink/70 leading-relaxed line-clamp-2">{s.desc || '（暂无描述）'}</p>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                /* ---------- 排版二：按技能平铺展示 ---------- */
                <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-6'} pb-8`}>
                  {filteredSkills.map((s, idx) => (
                    <button
                      key={s.name}
                      onClick={() => setSelectedSkill(s)}
                      style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
                      className={`bg-paper border-4 border-ink ${isNarrow ? 'p-4' : 'p-5'} flex flex-col gap-2 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 hover:shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] transition-all text-left ${idx % 3 === 0 ? '-rotate-1' : 'rotate-1'}`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <SkillIcon skill={s} size={36} />
                        <h3 className="text-lg font-black truncate text-ink flex-1 min-w-0 text-left" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={s.name}>{s.name}</h3>
                      </div>
                      <p className="text-sm font-bold text-ink/70 leading-relaxed">{shortDesc(s.desc)}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* MCP SERVERS 列表渲染（Registry v2.0：一个 mcp 一卡片） */}
          {activeTab === 'mcp' && (
            <div className={isNarrow ? 'p-4' : 'p-10'}>
              {isFetchingMcp && mcpData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-[#EBCB8B]" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Fetching Repositories...</p></div>
              ) : mcpData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[50vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Registry is empty.</p></div>
              ) : (
                <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-8'}`}>
                  {mcpData.map((mcp, idx) => {
                    const installed = isMcpInstalled(mcp);
                    return (
                      <button
                        key={mcp.name}
                        onClick={() => setSelectedMcpInfo(mcp)}
                        style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2}
                        className={`bg-paper border-4 border-ink ${isNarrow ? 'p-4' : 'p-6'} flex flex-col gap-3 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all text-left ${idx % 3 === 0 ? 'rotate-1' : '-rotate-1'}`}
                      >
                        <div className="flex items-center gap-3 border-b-2 border-ink/10 pb-3 min-w-0">
                          <McpIcon mcp={mcp} size={44} />
                          <h3 className="text-xl font-black truncate text-ink flex-1 min-w-0" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={mcp.name}>{mcp.name}</h3>
                          {installed && (
                            <span className="flex items-center gap-1 text-[10px] font-black px-2 py-1 bg-[#a3be8c] text-ink border-2 border-ink shrink-0" style={sketchyShape3}>
                              <Check size={10} strokeWidth={4} /> 已安装
                            </span>
                          )}
                        </div>

                        <p className="text-sm font-bold text-ink/70 leading-relaxed line-clamp-3 flex-1">{mcp.desc || '（暂无描述）'}</p>

                        <div className="flex items-center justify-between mt-1 pt-3 border-t-2 border-ink/10 border-dashed gap-2">
                          <p className="text-xs font-bold text-ink/40 truncate">{Object.keys(mcp.mcpServers || {}).join(', ')}</p>
                          <span className="text-[10px] font-black px-2 py-1 uppercase bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>MCP</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {activeTab !== 'skill' && activeTab !== 'mcp' && (
            <div className="flex flex-col items-center justify-center h-[60vh] gap-6 opacity-40 text-ink">
              {activeTab === 'sensor' && <Activity size={80} strokeWidth={1.5} />}
              {activeTab === 'graph' && <GitMerge size={80} strokeWidth={1.5} />}
              <p className="text-3xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>COMING SOON</p>
              <p className="font-bold text-lg">此模块的在线集市正在施工中...</p>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
