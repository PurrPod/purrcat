// src/components/MarketPage.tsx
import { useState, useEffect, useMemo, useRef } from 'react';
import { ArrowLeft, Store, RefreshCw, User, AlertCircle, Zap, Server, Activity, GitMerge, X, Copy, Search, LayoutGrid, FolderGit2, Download, Check, ChevronLeft, Loader2, Link2, Repeat, Languages } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useTranslation } from '../i18n';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

type MarketTab = 'skill' | 'mcp' | 'sensor' | 'graph' | 'loop';
type LayoutMode = 'repo' | 'skill';

// Registry v2.0 的 skill 条目结构
interface SkillEntry {
  name: string;
  desc: string;
  'desc-zh'?: string;
  author: string;
  'icon-link'?: string;
  'skill-single-link': string;
  repo: string;
}

// Registry v2.0 的 mcp 条目结构
interface McpEntry {
  name: string;
  desc: string;
  'desc-zh'?: string;
  'icon-link'?: string;
  repo: string;
  mcpServers: Record<string, any>;
}

// Sensor 注册表条目结构（PurrPod/sensors registry.json）
interface SensorEntry {
  name: string;
  description?: string;
  'description-zh'?: string;
  enabled?: boolean;
  env?: Record<string, string>;
  [k: string]: any;
}

interface InstalledSensor {
  name: string;
  enabled?: boolean;
  has_code?: boolean;
}

// Graph 注册表条目结构（PurrPod/graphs registry.json 中 graphs[]）
interface GraphEntry {
  name: string;
  description?: string;
  'description-zh'?: string;
  version?: string;
  global_schema?: any;
  [k: string]: any;
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

// 按当前语言偏好取描述：开启中文且存在中文描述时优先中文，否则回退英文
function pickDesc(en?: string, zh?: string, showZh = false): string {
  return (showZh ? (zh || en) : en) || '';
}

// 详情弹窗描述语言切换按钮：英文 desc ↔ 中文 desc-zh（无中文描述时不显示）
function DescLangButton({ hasZh, showZh, onToggle }: { hasZh: boolean; showZh: boolean; onToggle: () => void }) {
  const { t } = useTranslation();
  if (!hasZh) return null;
  return (
    <button
      onClick={onToggle}
      title={t('common.language')}
      aria-label={t('common.language')}
      style={sketchyShape2}
      className="flex items-center gap-1 text-xs font-black bg-cream border-2 border-ink px-2 py-1 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:translate-y-[1px] active:shadow-none shrink-0"
    >
      <Languages size={12} strokeWidth={3} />
      <span>{showZh ? 'EN' : '中'}</span>
    </button>
  );
}

export default function MarketPage({ onBack, initialTab }: { onBack: () => void; initialTab?: MarketTab }) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<MarketTab>(initialTab ?? 'skill');

  const [skillData, setSkillData] = useState<Record<string, SkillEntry>>({});
  const [isFetchingSkill, setIsFetchingSkill] = useState(false);

  const [mcpData, setMcpData] = useState<McpEntry[]>([]);
  const [isFetchingMcp, setIsFetchingMcp] = useState(false);

  // 选中的 MCP 详情信息弹窗 / 安装确认弹窗 / 已配置列表
  const [selectedMcpInfo, setSelectedMcpInfo] = useState<McpEntry | null>(null);
  const [mcpInstallConfirm, setMcpInstallConfirm] = useState<McpEntry | null>(null);
  const [installedMcpNames, setInstalledMcpNames] = useState<Set<string>>(new Set());
  const [installingMcpName, setInstallingMcpName] = useState<string | null>(null);

  // MCP 市场搜索 / build from scratch 弹窗
  const [mcpSearchQuery, setMcpSearchQuery] = useState('');
  const [showMcpFactoryModal, setShowMcpFactoryModal] = useState(false);
  const [factoryMcpName, setFactoryMcpName] = useState('');
  const [factoryGoal, setFactoryGoal] = useState('');
  const [isBuildingMcp, setIsBuildingMcp] = useState(false);

  // 🌟 Sensor 市场状态
  const [sensorData, setSensorData] = useState<SensorEntry[]>([]);
  const [isFetchingSensor, setIsFetchingSensor] = useState(false);
  const [sensorSearchQuery, setSensorSearchQuery] = useState('');
  const [selectedSensor, setSelectedSensor] = useState<SensorEntry | null>(null);
  const [installedSensorMap, setInstalledSensorMap] = useState<Map<string, InstalledSensor>>(new Map());
  const [installingSensorSet, setInstallingSensorSet] = useState<Set<string>>(new Set());

  // 🌟 Graph 市场状态
  const [graphData, setGraphData] = useState<GraphEntry[]>([]);
  const [isFetchingGraph, setIsFetchingGraph] = useState(false);
  const [graphSearchQuery, setGraphSearchQuery] = useState('');
  const [selectedGraph, setSelectedGraph] = useState<GraphEntry | null>(null);
  const [installedGraphNames, setInstalledGraphNames] = useState<Set<string>>(new Set());
  const [installingGraphSet, setInstallingGraphSet] = useState<Set<string>>(new Set());

  // 🌟 Skill 市场新状态：搜索 / 排版切换 / repo 下钻 / 详情弹窗 / 安装状态
  const [searchQuery, setSearchQuery] = useState('');
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('repo');
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillEntry | null>(null);
  // 详情弹窗描述语言：默认英文 desc，开启后显示中文 desc-zh / description-zh
  const [showZhDesc, setShowZhDesc] = useState(false);
  const [installedNames, setInstalledNames] = useState<Set<string>>(new Set());
  const [installingSet, setInstallingSet] = useState<Set<string>>(new Set());
  const [isInstallingAll, setIsInstallingAll] = useState(false);

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
        if (isManual) toast.success(t('market.skillsRefreshed'));
      }
    } catch {
      toast.error(t('market.skillsFetchFailed'));
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
        if (isManual) toast.success(t('market.mcpRefreshed'));
      }
    } catch {
      toast.error(t('market.mcpFetchFailed'));
    } finally {
      setIsFetchingMcp(false);
    }
  };

  // 拉取 Sensor 注册表（通过后端 API，带超时 + 错误提示）
  const fetchSensorData = async (isManual = false) => {
    setIsFetchingSensor(true);
    try {
      const res = await fetch(`/api/tools/market/sensors?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setSensorData(Array.isArray(data?.sensors) ? data.sensors : []);
        if (isManual) toast.success(t('market.sensorsRefreshed'));
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || t('market.sensorsFetchFailed'));
      }
    } catch {
      toast.error(t('market.sensorsFetchFailed'));
    } finally {
      setIsFetchingSensor(false);
    }
  };

  // 拉取本地已安装 Sensor
  const fetchLocalSensors = async () => {
    try {
      const res = await fetch('/api/tools/market/sensors/installed');
      if (res.ok) {
        const list: InstalledSensor[] = await res.json();
        const map = new Map<string, InstalledSensor>();
        for (const s of list) if (s?.name) map.set(String(s.name).toLowerCase(), s);
        setInstalledSensorMap(map);
      }
    } catch { /* noop */ }
  };

  // 拉取 Graph 注册表（通过后端 API）
  const fetchGraphData = async (isManual = false) => {
    setIsFetchingGraph(true);
    try {
      const res = await fetch(`/api/tools/market/graphs?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setGraphData(Array.isArray(data?.graphs) ? data.graphs : []);
        if (isManual) toast.success(t('market.graphsRefreshed'));
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || t('market.graphsFetchFailed'));
      }
    } catch {
      toast.error(t('market.graphsFetchFailed'));
    } finally {
      setIsFetchingGraph(false);
    }
  };

  const fetchLocalGraphs = async () => {
    try {
      const res = await fetch('/api/tools/market/graphs/installed');
      if (res.ok) {
        const list: string[] = await res.json();
        setInstalledGraphNames(new Set(list.map(n => String(n).toLowerCase())));
      }
    } catch { /* noop */ }
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
        toast.success(data?.message || `${t('market.mcpInstalledPrefix')}${mcp.name}${t('market.mcpInstalledSuffix')}`);
        setMcpInstallConfirm(null);
        await fetchLocalMcps();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || t('market.mcpInstallFailed'));
      }
    } catch {
      toast.error(t('market.mcpInstallFailedNetwork'));
    } finally {
      setInstallingMcpName(null);
    }
  };

  // MCP 关键词过滤：匹配 name / desc / repo / server 名
  const filteredMcps = useMemo(() => {
    const q = mcpSearchQuery.trim().toLowerCase();
    if (!q) return mcpData;
    return mcpData.filter(m =>
      [m.name, m.desc, m.repo, ...Object.keys(m.mcpServers || {})].some(
        f => (f || '').toLowerCase().includes(q)
      )
    );
  }, [mcpData, mcpSearchQuery]);

  // 触发 MCP 工厂构建（类似 trace2skill：分配沙盒 + 告知 Agent）
  const handleBuildMcpFromScratch = async () => {
    const name = factoryMcpName.trim();
    const goal = factoryGoal.trim();
    if (!name) return toast.error(t('market.mcpNameRequired'));
    if (!goal) return toast.error(t('market.goalRequired'));

    setIsBuildingMcp(true);
    const tid = toast.loading(t('market.allocatingMcpFactory'));
    try {
      const res = await fetch('/api/evolve/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'mcp', name, is_upgrade: false, goal })
      });
      if (!res.ok) throw new Error(t('market.sandboxAllocFailed'));
      const data = await res.json();
      const factoryPath = `/agent_vm/mcp_workplace/${data.workplace_id}/${name}`;

      const content = `用户在MCP市场使用了build_mcp_from_scratch功能，已为你分配了MCP工厂${factoryPath}/，请从零构建一个全新的 MCP Server。以下是用户期望的目标功能：\n${goal}`;
      await fetch('/api/chat/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: '', events: [{ type: 'evolve_factory', content }] })
      });

      toast.success(t('market.mcpTaskDispatched'), { id: tid });
      setShowMcpFactoryModal(false);
      setFactoryMcpName('');
      setFactoryGoal('');
    } catch {
      toast.error(t('market.factoryAllocFailed'), { id: tid });
    } finally {
      setIsBuildingMcp(false);
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
    if (activeTab === 'sensor') {
      if (sensorData.length === 0) fetchSensorData();
      fetchLocalSensors();
    }
    if (activeTab === 'graph') {
      if (graphData.length === 0) fetchGraphData();
      fetchLocalGraphs();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleRefresh = () => {
    if (activeTab === 'skill') { fetchSkillData(true); fetchLocalSkills(); }
    if (activeTab === 'mcp') { fetchMcpData(true); fetchLocalMcps(); }
    if (activeTab === 'sensor') { fetchSensorData(true); fetchLocalSensors(); }
    if (activeTab === 'graph') { fetchGraphData(true); fetchLocalGraphs(); }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success(t('market.copied'));
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
        toast.success(`${t('market.skillInstalledPrefix')}${skill.name}${t('market.skillInstalledSuffix')}`);
        await fetchLocalSkills();
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || t('market.skillInstallFailed'));
      }
    } catch {
      toast.error(t('market.skillInstallFailedNetwork'));
    } finally {
      setInstallingSet(prev => { const n = new Set(prev); n.delete(key); return n; });
    }
  };

  // 一键安装仓库内全部 skill（后端按仓库分组下载，只装未安装的）
  const handleInstallAllInRepo = async (skills: SkillEntry[]) => {
    if (isInstallingAll) return;
    const pending = skills.filter(s => !isInstalled(s));
    if (pending.length === 0) return toast.success(t('market.repoAllInstalled'));
    setIsInstallingAll(true);
    const tid = toast.loading(`${t('market.batchInstallingPrefix')}${pending.length}${t('market.batchInstallingSuffix')}`);
    try {
      const res = await fetch('/api/tools/skills/install-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: pending.map(s => s['skill-single-link']) }),
      });
      const data = await res.json().catch(() => null);
      if (res.ok) {
        if (data?.failed?.length) {
          toast.error(`${data.message}：${data.failed.map((f: any) => f.path).join('、')}`, { id: tid });
        } else {
          toast.success(data?.message || t('market.batchInstallDone'), { id: tid });
        }
        await fetchLocalSkills();
      } else {
        toast.error(data?.detail || t('market.batchInstallFailed'), { id: tid });
      }
    } catch {
      toast.error(t('market.batchInstallFailedNetwork'), { id: tid });
    } finally {
      setIsInstallingAll(false);
    }
  };

  // ========= Sensor 工具方法 =========
  // 已安装核对：配置存在 + 传感器代码文件存在本地（has_code）才算已安装
  const isSensorInstalled = (s: SensorEntry) => {
    const info = installedSensorMap.get(String(s.name).toLowerCase());
    return !!info && !!info.has_code;
  };
  const isSensorInstalling = (s: SensorEntry) => installingSensorSet.has(String(s.name).toLowerCase());

  const handleInstallSensor = async (s: SensorEntry) => {
    const key = String(s.name);
    if (!key) return;
    if (installingSensorSet.has(key) || isSensorInstalled(s)) return;
    setInstallingSensorSet(prev => new Set(prev).add(key));
    try {
      const res = await fetch('/api/tools/market/sensors/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sensor: s }),
      });
      const data = await res.json().catch(() => null);
      if (res.ok) {
        if (data?.status === 'partial') {
          toast(data?.message || t('market.sensorPartialInstalled'), { icon: '⚠️' });
        } else {
          toast.success(data?.message || `${t('market.sensorInstalledPrefix')}${key}${t('market.sensorInstalledSuffix')}`);
        }
        await fetchLocalSensors();
      } else {
        toast.error(data?.detail || t('market.sensorInstallFailed'));
      }
    } catch {
      toast.error(t('market.sensorInstallFailedNetwork'));
    } finally {
      setInstallingSensorSet(prev => { const n = new Set(prev); n.delete(key); return n; });
    }
  };

  const filteredSensors = useMemo(() => {
    const q = sensorSearchQuery.trim().toLowerCase();
    if (!q) return sensorData;
    return sensorData.filter(s =>
      [s.name, s.description].some(f => (f || '').toLowerCase().includes(q))
    );
  }, [sensorData, sensorSearchQuery]);

  // ========= Graph 工具方法 =========
  const isGraphInstalled = (g: GraphEntry) => installedGraphNames.has(String(g.name).toLowerCase());
  const isGraphInstalling = (g: GraphEntry) => installingGraphSet.has(String(g.name).toLowerCase());

  const handleInstallGraph = async (g: GraphEntry) => {
    const key = String(g.name);
    if (!key) return;
    if (installingGraphSet.has(key) || isGraphInstalled(g)) return;
    setInstallingGraphSet(prev => new Set(prev).add(key));
    try {
      const res = await fetch('/api/tools/market/graphs/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: key }),
      });
      const data = await res.json().catch(() => null);
      if (res.ok) {
        toast.success(data?.message || `${t('market.graphInstalledPrefix')}${key}${t('market.graphInstalledSuffix')}`);
        await fetchLocalGraphs();
      } else {
        toast.error(data?.detail || t('market.graphInstallFailed'));
      }
    } catch {
      toast.error(t('market.graphInstallFailedNetwork'));
    } finally {
      setInstallingGraphSet(prev => { const n = new Set(prev); n.delete(key); return n; });
    }
  };

  const filteredGraphs = useMemo(() => {
    const q = graphSearchQuery.trim().toLowerCase();
    if (!q) return graphData;
    return graphData.filter(g =>
      [g.name, g.description].some(f => (f || '').toLowerCase().includes(q))
    );
  }, [graphData, graphSearchQuery]);

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

  const isFetching =
    activeTab === 'skill' ? isFetchingSkill :
    activeTab === 'mcp' ? isFetchingMcp :
    activeTab === 'sensor' ? isFetchingSensor :
    activeTab === 'graph' ? isFetchingGraph :
    false;

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
                <div className="flex justify-between items-end gap-3">
                  <span className="font-black text-ink tracking-widest text-sm">{t('market.description')}</span>
                  <DescLangButton hasZh={!!selectedSkill['desc-zh']} showZh={showZhDesc} onToggle={() => setShowZhDesc(v => !v)} />
                </div>
                <p className="text-[15px] font-bold leading-relaxed text-ink/80 mt-3 whitespace-pre-wrap break-words">{pickDesc(selectedSkill.desc, selectedSkill['desc-zh'], showZhDesc) || t('market.noDesc')}</p>
                <p className="text-xs font-bold text-ink/40 mt-4 break-all">{t('market.sourceRepoPrefix')}{selectedSkill.repo}</p>
              </div>

              {/* 弹窗 Footer：link 跳转 + 下载安装 */}
              <div className="p-6 pt-4 border-t-4 border-ink/10 flex items-center justify-end gap-4 shrink-0 flex-wrap">
                <a
                  href={selectedSkill['skill-single-link'] || selectedSkill.repo}
                  target="_blank"
                  rel="noreferrer"
                  title={t('market.gotoRepo')}
                  style={sketchyShape1}
                  className="w-14 h-14 flex items-center justify-center bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#88c0d0] hover:text-paper transition-all active:translate-y-1 active:shadow-none"
                >
                  <Link2 size={22} strokeWidth={3} />
                </a>
                <button
                  onClick={() => handleInstallSkill(selectedSkill)}
                  disabled={installed || installing}
                  title={installed ? t('market.installed') : t('market.downloadInstall')}
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
                  <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{installing ? t('market.installing') : installed ? t('market.installed') : t('market.download')}</span>
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
                  <div className="flex justify-between items-end gap-3">
                    <span className="font-black text-ink tracking-widest text-sm">DESCRIPTION:</span>
                    <DescLangButton hasZh={!!selectedMcpInfo['desc-zh']} showZh={showZhDesc} onToggle={() => setShowZhDesc(v => !v)} />
                  </div>
                  <p className="text-[15px] font-bold leading-relaxed text-ink/80 whitespace-pre-wrap break-words">{pickDesc(selectedMcpInfo.desc, selectedMcpInfo['desc-zh'], showZhDesc) || t('market.noDesc')}</p>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-end">
                    <span className="font-black text-ink tracking-widest text-sm">{t('market.mcpServers')}</span>
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
                  title={t('market.gotoRepo')}
                  style={sketchyShape1}
                  className="w-14 h-14 flex items-center justify-center bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#88c0d0] hover:text-paper transition-all active:translate-y-1 active:shadow-none"
                >
                  <Link2 size={22} strokeWidth={3} />
                </a>
                <button
                  onClick={() => setMcpInstallConfirm(selectedMcpInfo)}
                  disabled={installed || installing}
                  title={installed ? t('market.installed') : t('market.install')}
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
                  <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{installing ? t('market.installing') : installed ? t('market.installed') : t('market.install')}</span>
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
              <h3 className="text-xl font-black text-ink tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.installConfirmTitle')}</h3>
              <button onClick={() => setMcpInstallConfirm(null)} className="p-1.5 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all" style={sketchyShape3}>
                <X size={20} strokeWidth={3} />
              </button>
            </div>

            <div className="p-6 flex flex-col gap-4">
              <p className="font-bold text-ink">
                {t('market.installConfirmPrefix')}<span className="font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{mcpInstallConfirm.name}</span>{t('market.installConfirmSuffix')}
              </p>
              <div className="flex items-start gap-3 bg-[#FDF8F0] border-4 border-ink p-4 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3}>
                <AlertCircle size={22} strokeWidth={2.5} className="text-[#bf616a] shrink-0 mt-0.5" />
                <p className="text-sm font-bold text-ink/80 leading-relaxed">
                  {t('market.installConfirmNotePrefix')}
                  <span className="font-mono text-[#bf616a] px-1">{'<your-api-key>'}</span>
                  {t('market.installConfirmNoteSuffix')}
                </p>
              </div>
            </div>

            <div className="p-5 pt-2 border-t-4 border-ink/10 flex justify-end gap-4 shrink-0">
              <button
                onClick={() => setMcpInstallConfirm(null)}
                style={sketchyShape1}
                className="px-5 h-12 flex items-center bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:translate-y-1 active:shadow-none"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={() => confirmInstallMcp(mcpInstallConfirm)}
                disabled={installingMcpName === mcpInstallConfirm.name}
                style={sketchyShape2}
                className={`px-5 h-12 flex items-center gap-2 border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${installingMcpName === mcpInstallConfirm.name ? 'bg-[#EBCB8B] text-ink cursor-wait' : 'bg-terracotta text-paper hover:-translate-y-0.5'}`}
              >
                {installingMcpName === mcpInstallConfirm.name && <Loader2 size={18} strokeWidth={3} className="animate-spin" />}
                <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{installingMcpName === mcpInstallConfirm.name ? t('market.installing') : t('market.confirmInstall')}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🌟 Sensor 详情弹窗（无图标：用 Activity 色块占位） */}
      {selectedSensor && (() => {
        const installed = isSensorInstalled(selectedSensor);
        const installing = isSensorInstalling(selectedSensor);
        const installedInfo = installedSensorMap.get(String(selectedSensor.name).toLowerCase());
        const envKeys = Object.keys(selectedSensor.env || {});
        return (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto" onClick={() => setSelectedSensor(null)}>
            <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-2xl flex flex-col relative rotate-[0.5deg]" onClick={e => e.stopPropagation()}>
              <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#a3be8c]/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>

              <div className="flex justify-between items-start p-6 border-b-4 border-ink/20 shrink-0 gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="rounded-full border-2 border-ink bg-[#a3be8c] flex items-center justify-center shrink-0" style={{ width: 56, height: 56 }}>
                    <Activity size={30} strokeWidth={2.5} className="text-ink" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-2xl font-black tracking-wide text-ink break-all" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{selectedSensor.name}</h2>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {installed && (
                        <span className="text-[10px] font-black px-2 py-0.5 bg-[#a3be8c] border-2 border-ink text-ink flex items-center gap-1" style={sketchyShape3}>
                          <Check size={10} strokeWidth={4} />
                          {installedInfo?.enabled ? t('market.enabled') : t('market.installed')}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button onClick={() => setSelectedSensor(null)} className="p-2 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all shrink-0" style={sketchyShape3}>
                  <X size={24} strokeWidth={3} />
                </button>
              </div>

              <div className="p-6 flex-1 overflow-y-auto max-h-[45vh] flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-end gap-3">
                    <span className="font-black text-ink tracking-widest text-sm">{t('market.description')}</span>
                    <DescLangButton hasZh={!!selectedSensor['description-zh']} showZh={showZhDesc} onToggle={() => setShowZhDesc(v => !v)} />
                  </div>
                  <p className="text-[15px] font-bold leading-relaxed text-ink/80 whitespace-pre-wrap break-words">{pickDesc(selectedSensor.description, selectedSensor['description-zh'], showZhDesc) || t('market.noDesc')}</p>
                </div>

                {envKeys.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <div className="flex justify-between items-end">
                      <span className="font-black text-ink tracking-widest text-sm">{t('market.requiredEnv')}</span>
                      <span className="text-[11px] font-bold text-ink/40">{t('market.envFillHint')}</span>
                    </div>
                    <div style={sketchyShape1} className="bg-[#FDF8F0] border-4 border-ink p-4 overflow-x-auto shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]">
                      <div className="flex flex-col gap-2">
                        {envKeys.map(k => (
                          <div key={k} className="flex items-start gap-2 min-w-0">
                            <span className="font-mono font-black text-[13px] text-[#bf616a] shrink-0 w-56 truncate" title={k}>{k}</span>
                            <span className="font-mono text-[12px] text-ink/70 min-w-0 break-all">
                              {(selectedSensor.env?.[k] || '') === '' ? t('market.requiredField') : selectedSensor.env?.[k]}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="p-6 pt-4 border-t-4 border-ink/10 flex items-center justify-end gap-4 shrink-0 flex-wrap">
                <a
                  href="https://github.com/PurrPod/sensors"
                  target="_blank"
                  rel="noreferrer"
                  title={t('market.gotoOfficialRepo')}
                  style={sketchyShape1}
                  className="w-14 h-14 flex items-center justify-center bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#a3be8c] hover:text-paper transition-all active:translate-y-1 active:shadow-none"
                >
                  <Link2 size={22} strokeWidth={3} />
                </a>
                <button
                  onClick={() => handleInstallSensor(selectedSensor)}
                  disabled={installing || installed}
                  title={installed ? t('market.installedFull') : t('market.downloadInstall')}
                  style={sketchyShape2}
                  className={`h-14 px-6 flex items-center gap-2 border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${
                    installed
                      ? 'bg-[#d8d8d0] text-ink/40 cursor-not-allowed'
                      : installing
                        ? 'bg-[#EBCB8B] text-ink cursor-wait'
                        : 'bg-[#a3be8c] text-ink hover:-translate-y-0.5'
                  }`}
                >
                  {installing ? <Loader2 size={22} strokeWidth={3} className="animate-spin" /> : installed ? <Check size={22} strokeWidth={3} /> : <Download size={22} strokeWidth={3} />}
                  <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                    {installing ? t('market.installing') : installed ? t('market.installed') : t('market.download')}
                  </span>
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* 🌟 Graph 详情弹窗（无图标：用 GitMerge 色块占位） */}
      {selectedGraph && (() => {
        const installed = isGraphInstalled(selectedGraph);
        const installing = isGraphInstalling(selectedGraph);
        return (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto" onClick={() => setSelectedGraph(null)}>
            <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-2xl flex flex-col relative rotate-[0.5deg]" onClick={e => e.stopPropagation()}>
              <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#b48ead]/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>

              <div className="flex justify-between items-start p-6 border-b-4 border-ink/20 shrink-0 gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="rounded-full border-2 border-ink bg-[#b48ead] flex items-center justify-center shrink-0" style={{ width: 56, height: 56 }}>
                    <GitMerge size={30} strokeWidth={2.5} className="text-paper" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-2xl font-black tracking-wide text-ink break-all" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{selectedGraph.name}</h2>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {selectedGraph.version && (
                        <span className="text-[10px] font-black px-2 py-0.5 bg-cream border-2 border-ink text-ink" style={sketchyShape3}>v{selectedGraph.version}</span>
                      )}
                      <span className="text-[10px] font-black px-2 py-0.5 uppercase bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>Graph</span>
                      {installed && (
                        <span className="text-[10px] font-black px-2 py-0.5 bg-[#a3be8c] border-2 border-ink text-ink flex items-center gap-1" style={sketchyShape1}>
                          <Check size={10} strokeWidth={4} /> {t('market.installed')}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button onClick={() => setSelectedGraph(null)} className="p-2 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all shrink-0" style={sketchyShape3}>
                  <X size={24} strokeWidth={3} />
                </button>
              </div>

              <div className="p-6 flex-1 overflow-y-auto max-h-[45vh] flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-end gap-3">
                    <span className="font-black text-ink tracking-widest text-sm">{t('market.description')}</span>
                    <DescLangButton hasZh={!!selectedGraph['description-zh']} showZh={showZhDesc} onToggle={() => setShowZhDesc(v => !v)} />
                  </div>
                  <p className="text-[15px] font-bold leading-relaxed text-ink/80 whitespace-pre-wrap break-words">{pickDesc(selectedGraph.description, selectedGraph['description-zh'], showZhDesc) || t('market.noDesc')}</p>
                </div>

                {selectedGraph.global_schema && Object.keys(selectedGraph.global_schema).length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span className="font-black text-ink tracking-widest text-sm">{t('market.inputSchema')}</span>
                    <pre style={sketchyShape3} className="bg-[#FDF8F0] border-4 border-ink p-4 overflow-x-auto text-xs font-mono font-bold shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] text-ink">
                      {JSON.stringify(selectedGraph.global_schema, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              <div className="p-6 pt-4 border-t-4 border-ink/10 flex items-center justify-end gap-4 shrink-0 flex-wrap">
                <a
                  href="https://github.com/PurrPod/graphs"
                  target="_blank"
                  rel="noreferrer"
                  title={t('market.gotoOfficialRepo')}
                  style={sketchyShape1}
                  className="w-14 h-14 flex items-center justify-center bg-cream text-ink border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#b48ead] hover:text-paper transition-all active:translate-y-1 active:shadow-none"
                >
                  <Link2 size={22} strokeWidth={3} />
                </a>
                <button
                  onClick={() => handleInstallGraph(selectedGraph)}
                  disabled={installing || installed}
                  title={installed ? t('market.installed') : t('market.downloadInstall')}
                  style={sketchyShape2}
                  className={`h-14 px-6 flex items-center gap-2 border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${
                    installed
                      ? 'bg-[#d8d8d0] text-ink/40 cursor-not-allowed'
                      : installing
                        ? 'bg-[#EBCB8B] text-ink cursor-wait'
                        : 'bg-[#b48ead] text-paper hover:-translate-y-0.5'
                  }`}
                >
                  {installing ? <Loader2 size={22} strokeWidth={3} className="animate-spin" /> : installed ? <Check size={22} strokeWidth={3} /> : <Download size={22} strokeWidth={3} />}
                  <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                    {installing ? t('market.installing') : installed ? t('market.installed') : t('market.download')}
                  </span>
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* 🌟 MCP 工厂构建弹窗：build a mcp from scratch */}
      {showMcpFactoryModal && (
        <div className="fixed inset-0 z-[210] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-lg flex flex-col relative rotate-[0.5deg]">
            <div className="absolute -top-4 left-1/4 w-32 h-10 bg-[#88c0d0]/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>

            <div className="flex justify-between items-center p-5 border-b-4 border-ink/20 shrink-0">
              <h3 className="text-xl font-black text-ink tracking-wide" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.buildMcp')}</h3>
              <button onClick={() => setShowMcpFactoryModal(false)} className="p-1.5 border-2 border-ink bg-cream text-ink hover:bg-[#bf616a] hover:text-paper transition-all" style={sketchyShape3}>
                <X size={20} strokeWidth={3} />
              </button>
            </div>

            <div className="p-6 flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <span className="font-black text-ink text-sm tracking-widest">{t('market.mcpName')}</span>
                <input
                  value={factoryMcpName}
                  onChange={e => setFactoryMcpName(e.target.value)}
                  placeholder={t('market.mcpNamePh')}
                  className="bg-[#FDF8F0] border-4 border-ink px-4 py-2.5 font-bold text-ink placeholder:text-ink/40 outline-none focus:bg-paper transition-colors"
                  style={sketchyShape3}
                />
              </div>
              <div className="flex flex-col gap-2">
                <span className="font-black text-ink text-sm tracking-widest">{t('market.targetFunction')}</span>
                <textarea
                  value={factoryGoal}
                  onChange={e => setFactoryGoal(e.target.value)}
                  placeholder={t('market.mcpGoalPh')}
                  rows={5}
                  className="bg-[#FDF8F0] border-4 border-ink px-4 py-2.5 font-bold text-ink placeholder:text-ink/40 outline-none focus:bg-paper transition-colors resize-none"
                  style={sketchyShape3}
                />
              </div>
              <p className="text-xs font-bold text-ink/40">{t('market.factoryHint')}</p>
            </div>

            <div className="p-5 pt-2 border-t-4 border-ink/10 flex justify-end gap-4 shrink-0">
              <button
                onClick={() => setShowMcpFactoryModal(false)}
                style={sketchyShape1}
                className="px-5 h-12 flex items-center bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:translate-y-1 active:shadow-none"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleBuildMcpFromScratch}
                disabled={isBuildingMcp}
                style={sketchyShape2}
                className={`px-5 h-12 flex items-center gap-2 border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none ${isBuildingMcp ? 'bg-[#EBCB8B] text-ink cursor-wait' : 'bg-terracotta text-paper hover:-translate-y-0.5'}`}
              >
                {isBuildingMcp && <Loader2 size={18} strokeWidth={3} className="animate-spin" />}
                <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{isBuildingMcp ? t('market.allocating') : t('market.startBuild')}</span>
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
            <span className="tracking-widest text-lg font-black truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('home.market')}</span>
          </div>
        </div>

        <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
          <div className="flex-1 flex flex-col gap-4 mt-4">

            <button onClick={() => setActiveTab('skill')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'skill' ? 'bg-terracotta text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Zap size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.skills')}</div>
                <div className="text-xs font-bold opacity-70 truncate">{t('market.capabilities')}</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('mcp')} style={sketchyShape2} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'mcp' ? 'bg-[#EBCB8B] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Server size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.servers')}</div>
                <div className="text-xs font-bold opacity-70 truncate">{t('market.providers')}</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('sensor')} style={sketchyShape3} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'sensor' ? 'bg-[#a3be8c] text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Activity size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.sensors')}</div>
                <div className="text-xs font-bold opacity-70 truncate">{t('market.triggers')}</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('graph')} style={sketchyShape1} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'graph' ? 'bg-[#b48ead] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <GitMerge size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.graphs')}</div>
                <div className="text-xs font-bold opacity-70 truncate">{t('market.templates')}</div>
              </div>
            </button>

            <button onClick={() => setActiveTab('loop')} style={sketchyShape2} className={`p-4 border-4 border-ink text-left transition-all flex items-center gap-4 ${activeTab === 'loop' ? 'bg-[#5e81ac] text-paper shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] -translate-y-1' : 'bg-cream text-ink hover:bg-sand'}`}>
              <Repeat size={28} strokeWidth={2.5} className="shrink-0"/>
              <div className="min-w-0">
                <div className="font-black text-xl tracking-widest truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.loops')}</div>
                <div className="text-xs font-bold opacity-70 truncate">{t('market.paradigms')}</div>
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
              <button onClick={onBack} title={t('market.back')} style={sketchyShape2} className="p-2 bg-cream border-2 border-ink text-ink hover:bg-sand transition-all shrink-0">
                <ArrowLeft size={20} strokeWidth={3} />
              </button>
            )}
            <div style={sketchyShape2} className="w-12 h-12 bg-ink border-4 border-ink flex items-center justify-center rotate-6 shrink-0">
              {activeTab === 'skill' && <Zap className="text-terracotta" strokeWidth={2.5} />}
              {activeTab === 'mcp' && <Server className="text-[#EBCB8B]" strokeWidth={2.5} />}
              {activeTab === 'sensor' && <Activity className="text-[#a3be8c]" strokeWidth={2.5} />}
              {activeTab === 'graph' && <GitMerge className="text-[#b48ead]" strokeWidth={2.5} />}
              {activeTab === 'loop' && <Repeat className="text-[#5e81ac]" strokeWidth={2.5} />}
            </div>
            <h2 className={`${isNarrow ? 'text-lg' : 'text-3xl'} font-black tracking-widest text-ink uppercase truncate min-w-0`} style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              {activeTab === 'skill' ? t('market.skillTitle') : activeTab === 'mcp' ? t('market.mcpTitle') : activeTab === 'sensor' ? t('market.sensorTitle') : activeTab === 'graph' ? t('market.graphTitle') : t('market.loopTitle')}
            </h2>
          </div>

          <button
            onClick={handleRefresh}
            disabled={isFetching}
            style={sketchyShape2}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#EBCB8B] text-ink border-4 border-ink font-black text-lg shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-none transition-all rotate-2 disabled:opacity-50 shrink-0"
          >
            <RefreshCw size={20} strokeWidth={3} className={isFetching ? "animate-spin text-terracotta" : "text-ink"} />
            {!isNarrow && <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.refresh')}</span>}
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
                    placeholder={t('market.searchSkills')}
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
                    <FolderGit2 size={16} strokeWidth={3} className="shrink-0" /> {t('market.byRepo')}
                  </button>
                  <button
                    onClick={() => { setLayoutMode('skill'); setSelectedRepo(null); }}
                    className={`flex items-center gap-2 px-4 py-2.5 font-black text-sm border-l-4 border-ink transition-all ${layoutMode === 'skill' ? 'bg-terracotta text-paper' : 'text-ink hover:bg-sand'}`}
                  >
                    <LayoutGrid size={16} strokeWidth={3} className="shrink-0" /> {t('market.bySkill')}
                  </button>
                </div>
              </div>

              {isFetchingSkill && Object.keys(skillData).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-terracotta" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.fetching')}</p></div>
              ) : filteredSkills.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{searchQuery ? t('market.noMatch') : t('market.registryEmpty')}</p></div>
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
                            {skills.length}{t('market.skillCountSuffix')}
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
                    <ChevronLeft size={18} strokeWidth={3} /> {t('market.backToRepoList')}
                  </button>
                  {(() => {
                    const repoSkills = repoGroups.find(([r]) => r === selectedRepo)?.[1] ?? [];
                    const allInstalled = repoSkills.length > 0 && repoSkills.every(isInstalled);
                    return (
                      <div className="flex items-center gap-3 min-w-0">
                        <FolderGit2 size={22} strokeWidth={2.5} className="text-terracotta shrink-0" />
                        <span className="text-xl font-black text-ink truncate min-w-0" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{repoDisplayName(selectedRepo)}</span>
                        <span className="text-xs font-black px-2 py-1 bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>{repoSkills.length} skills</span>
                        <button
                          onClick={() => handleInstallAllInRepo(repoSkills)}
                          disabled={isInstallingAll || allInstalled}
                          title={allInstalled ? t('market.allInstalled') : t('market.installAllTitle')}
                          style={sketchyShape2}
                          className={`ml-auto h-11 px-5 flex items-center gap-2 border-4 border-ink font-black text-sm shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] transition-all active:translate-y-1 active:shadow-none shrink-0 ${
                            allInstalled
                              ? 'bg-[#d8d8d0] text-ink/40 cursor-not-allowed'
                              : isInstallingAll
                                ? 'bg-[#EBCB8B] text-ink cursor-wait'
                                : 'bg-terracotta text-paper hover:-translate-y-0.5'
                          }`}
                        >
                          {isInstallingAll ? <Loader2 size={18} strokeWidth={3} className="animate-spin" /> : allInstalled ? <Check size={18} strokeWidth={3} /> : <Download size={18} strokeWidth={3} />}
                          {!isNarrow && <span style={{ fontFamily: '"Comic Sans MS", cursive' }}>{isInstallingAll ? t('market.installing') : allInstalled ? t('market.allInstalled') : t('market.installAllBtn')}</span>}
                        </button>
                      </div>
                    );
                  })()}
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
                        <p className="text-sm font-bold text-ink/70 leading-relaxed line-clamp-2">{s.desc || t('market.noDesc')}</p>
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

          {/* MCP SERVERS 列表渲染（Registry v2.0：一个 mcp 一卡片 + 搜索 + 工厂入口） */}
          {activeTab === 'mcp' && (
            <div className={`${isNarrow ? 'p-4 gap-4' : 'p-10 gap-6'} flex flex-col`}>
              {/* 搜索框 */}
              <div className="flex items-center gap-3 bg-paper border-4 border-ink px-4 py-2.5 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape2}>
                <Search size={18} strokeWidth={3} className="text-ink/40 shrink-0" />
                <input
                  value={mcpSearchQuery}
                  onChange={e => setMcpSearchQuery(e.target.value)}
                  placeholder={t('market.searchMcp')}
                  className="flex-1 min-w-0 bg-transparent outline-none font-bold text-ink placeholder:text-ink/40 text-[15px]"
                />
                {mcpSearchQuery && (
                  <button onClick={() => setMcpSearchQuery('')} className="p-1 text-ink/40 hover:text-ink transition-colors shrink-0">
                    <X size={16} strokeWidth={3} />
                  </button>
                )}
              </div>

              {isFetchingMcp && mcpData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-[#EBCB8B]" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.fetching')}</p></div>
              ) : filteredMcps.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{mcpSearchQuery ? t('market.noMatch') : t('market.registryEmpty')}</p></div>
              ) : (
                <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-8'}`}>
                  {filteredMcps.map((mcp, idx) => {
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
                              <Check size={10} strokeWidth={4} /> {t('market.installed')}
                            </span>
                          )}
                        </div>

                        <p className="text-sm font-bold text-ink/70 leading-relaxed line-clamp-3 flex-1">{mcp.desc || t('market.noDesc')}</p>

                        <div className="flex items-center justify-between mt-1 pt-3 border-t-2 border-ink/10 border-dashed gap-2">
                          <p className="text-xs font-bold text-ink/40 truncate">{Object.keys(mcp.mcpServers || {}).join(', ')}</p>
                          <span className="text-[10px] font-black px-2 py-1 uppercase bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>MCP</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* 底部提示：没有想要的？从零构建一个！ */}
              <button
                onClick={() => setShowMcpFactoryModal(true)}
                className="w-full flex items-center justify-center gap-2 py-3 opacity-60 hover:opacity-100 transition-opacity"
              >
                <span className="text-sm font-bold text-ink/50">{t('market.noWant')}</span>
                <span className="text-sm font-black text-terracotta underline decoration-wavy decoration-2 underline-offset-4" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                  build a mcp from scratch!
                </span>
              </button>
            </div>
          )}

          {/* ================= SENSORS 列表渲染（搜索框 + 卡片平铺 + 无图标） ================= */}
          {activeTab === 'sensor' && (
            <div className={`${isNarrow ? 'p-4 gap-4' : 'p-10 gap-6'} flex flex-col`}>
              {/* 搜索框 */}
              <div className="flex items-center gap-3 bg-paper border-4 border-ink px-4 py-2.5 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape2}>
                <Search size={18} strokeWidth={3} className="text-ink/40 shrink-0" />
                <input
                  value={sensorSearchQuery}
                  onChange={e => setSensorSearchQuery(e.target.value)}
                  placeholder={t('market.searchSensors')}
                  className="flex-1 min-w-0 bg-transparent outline-none font-bold text-ink placeholder:text-ink/40 text-[15px]"
                />
                {sensorSearchQuery && (
                  <button onClick={() => setSensorSearchQuery('')} className="p-1 text-ink/40 hover:text-ink transition-colors shrink-0">
                    <X size={16} strokeWidth={3} />
                  </button>
                )}
              </div>

              {isFetchingSensor && sensorData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-[#a3be8c]" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.fetching')}</p></div>
              ) : filteredSensors.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{sensorSearchQuery ? t('market.noMatch') : t('market.registryEmpty')}</p></div>
              ) : (
                <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-8'} pb-8`}>
                  {filteredSensors.map((s, idx) => {
                    const installed = isSensorInstalled(s);
                    const installing = isSensorInstalling(s);
                    const installedInfo = installedSensorMap.get(String(s.name).toLowerCase());
                    return (
                      <button
                        key={s.name}
                        onClick={() => setSelectedSensor(s)}
                        style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2}
                        className={`bg-paper border-4 border-ink ${isNarrow ? 'p-4' : 'p-6'} flex flex-col gap-3 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all text-left ${idx % 3 === 0 ? 'rotate-1' : '-rotate-1'}`}
                      >
                        <div className="flex items-center gap-3 border-b-2 border-ink/10 pb-3 min-w-0">
                          {/* Sensor 无 icon：Activity 彩色圆标占位 */}
                          <div className="rounded-full border-2 border-ink bg-[#a3be8c] flex items-center justify-center shrink-0" style={{ width: 44, height: 44 }}>
                            <Activity size={22} strokeWidth={2.5} className="text-ink" />
                          </div>
                          <h3 className="text-xl font-black truncate text-ink flex-1 min-w-0" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={s.name}>{s.name}</h3>
                          {installed && (
                            <span className="flex items-center gap-1 text-[10px] font-black px-2 py-1 bg-[#a3be8c] text-ink border-2 border-ink shrink-0" style={sketchyShape3}>
                              <Check size={10} strokeWidth={4} />
                              {installedInfo?.enabled ? t('market.enabled') : t('market.installed')}
                            </span>
                          )}
                          {installing && (
                            <Loader2 size={16} strokeWidth={3} className="animate-spin shrink-0 text-[#EBCB8B]" />
                          )}
                        </div>

                        <p className="text-sm font-bold text-ink/70 leading-relaxed line-clamp-3 flex-1">{s.description || t('market.noDesc')}</p>

                        <div className="flex items-center justify-between mt-1 pt-3 border-t-2 border-ink/10 border-dashed gap-2">
                          <div className="flex items-center gap-1 flex-wrap min-w-0">
                            {s.env && Object.keys(s.env).length > 0 && (
                              <span className="text-[9px] font-black px-1.5 py-0.5 bg-[#FDF8F0] border-2 border-ink text-[#bf616a]" style={sketchyShape2}>ENV x{Object.keys(s.env).length}</span>
                            )}
                          </div>
                          <span className="text-[10px] font-black px-2 py-1 uppercase bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>SENSOR</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ================= GRAPHS 列表渲染（搜索框 + 卡片平铺 + 无图标） ================= */}
          {activeTab === 'graph' && (
            <div className={`${isNarrow ? 'p-4 gap-4' : 'p-10 gap-6'} flex flex-col`}>
              {/* 搜索框 */}
              <div className="flex items-center gap-3 bg-paper border-4 border-ink px-4 py-2.5 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape2}>
                <Search size={18} strokeWidth={3} className="text-ink/40 shrink-0" />
                <input
                  value={graphSearchQuery}
                  onChange={e => setGraphSearchQuery(e.target.value)}
                  placeholder={t('market.searchGraphs')}
                  className="flex-1 min-w-0 bg-transparent outline-none font-bold text-ink placeholder:text-ink/40 text-[15px]"
                />
                {graphSearchQuery && (
                  <button onClick={() => setGraphSearchQuery('')} className="p-1 text-ink/40 hover:text-ink transition-colors shrink-0">
                    <X size={16} strokeWidth={3} />
                  </button>
                )}
              </div>

              {isFetchingGraph && graphData.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50"><RefreshCw className="animate-spin text-[#b48ead]" size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.fetching')}</p></div>
              ) : filteredGraphs.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] gap-4 opacity-50 text-ink"><AlertCircle size={64} strokeWidth={2} /><p className="text-2xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{graphSearchQuery ? t('market.noMatch') : t('market.registryEmpty')}</p></div>
              ) : (
                <div className={`grid ${cardCols} ${isNarrow ? 'gap-4' : 'gap-8'} pb-8`}>
                  {filteredGraphs.map((g, idx) => {
                    const installed = isGraphInstalled(g);
                    const installing = isGraphInstalling(g);
                    return (
                      <button
                        key={g.name}
                        onClick={() => setSelectedGraph(g)}
                        style={idx % 2 === 0 ? sketchyShape3 : sketchyShape1}
                        className={`bg-paper border-4 border-ink ${isNarrow ? 'p-4' : 'p-6'} flex flex-col gap-3 shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-2 hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] transition-all text-left ${idx % 3 === 0 ? '-rotate-1' : 'rotate-1'}`}
                      >
                        <div className="flex items-center gap-3 border-b-2 border-ink/10 pb-3 min-w-0">
                          {/* Graph 无 icon：GitMerge 彩色圆标占位 */}
                          <div className="rounded-full border-2 border-ink bg-[#b48ead] flex items-center justify-center shrink-0" style={{ width: 44, height: 44 }}>
                            <GitMerge size={22} strokeWidth={2.5} className="text-paper" />
                          </div>
                          <h3 className="text-xl font-black truncate text-ink flex-1 min-w-0" style={{ fontFamily: '"Comic Sans MS", cursive' }} title={g.name}>{g.name}</h3>
                          {installed && (
                            <span className="flex items-center gap-1 text-[10px] font-black px-2 py-1 bg-[#a3be8c] text-ink border-2 border-ink shrink-0" style={sketchyShape3}>
                              <Check size={10} strokeWidth={4} /> {t('market.installed')}
                            </span>
                          )}
                          {installing && (
                            <Loader2 size={16} strokeWidth={3} className="animate-spin shrink-0 text-[#EBCB8B]" />
                          )}
                        </div>

                        <p className="text-sm font-bold text-ink/70 leading-relaxed line-clamp-3 flex-1">{g.description || t('market.noDesc')}</p>

                        <div className="flex items-center justify-between mt-1 pt-3 border-t-2 border-ink/10 border-dashed gap-2">
                          <p className="text-xs font-bold text-ink/40 truncate">
                            {g.version ? `v${g.version}` : g.global_schema && Object.keys(g.global_schema).length > 0 ? `${Object.keys(g.global_schema).length} input args` : 'No version info'}
                          </p>
                          <span className="text-[10px] font-black px-2 py-1 uppercase bg-ink text-paper border-2 border-ink shrink-0" style={sketchyShape3}>GRAPH</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ================= LOOPS 占位（coming soon） ================= */}
          {activeTab === 'loop' && (
            <div className="w-full h-full flex items-center justify-center">
              <div style={sketchyShape2} className="flex flex-col items-center gap-6 bg-paper border-4 border-ink px-10 py-12 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-2 max-w-lg text-center mx-6">
                <div style={sketchyShape1} className="w-24 h-24 bg-[#5e81ac] border-4 border-ink flex items-center justify-center rotate-6 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]">
                  <Repeat size={52} strokeWidth={2.5} className="text-paper" />
                </div>
                <h3 className="text-4xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{t('market.comingSoon')}</h3>
                <p className="text-sm font-bold text-ink/60 leading-relaxed">{t('market.loopSoon')}</p>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
