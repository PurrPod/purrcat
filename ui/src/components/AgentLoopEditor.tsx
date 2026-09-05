// src/components/AgentLoopEditor.tsx
// PARADIGM（Agent Loop）机制编辑器：
//  - 文件打开/保存/新建/删除统一放到顶部 Toolbar（与 Workflow 的 OPEN/DEPLOY 一致），通过 ref 暴露
//  - 左侧只放 Hook 组件视图（按生命周期组织，action 可展开编辑 config）
//  - 右侧：带环循环骨架图（风格与 Workflow 一致：白底卡片 + 小色块标记 + 横平竖直连线）
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { ReactFlow, Background, Controls, MarkerType, Handle, Position } from '@xyflow/react';
import type { Node as FlowNode, Edge as FlowEdge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toast } from 'react-hot-toast';
import { ChevronDown, Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';

// ============ 领域模型 ============

// 真实 PARADIGM 中支持的 Hook（顺序即流程图展示顺序）
const HOOK_META = [
  { key: 'on_build_system_prompt', label: '构建系统提示词时', color: '#FFD27D' },
  { key: 'on_loop_start', label: '循环开始时', color: '#7FB8E6' },
  { key: 'on_loop_epoch', label: '每轮循环迭代时', color: '#8CC98F' },
  { key: 'on_loop_end', label: '循环结束时', color: '#E8909A' },
  { key: 'on_tool_calling', label: '工具调用时', color: '#B597E0' },
] as const;

type HookKey = (typeof HOOK_META)[number]['key'];
const HOOK_KEYS: HookKey[] = HOOK_META.map((h) => h.key);
const HOOK_KEY_SET = new Set<string>(HOOK_KEYS);

// 可选动作类型（与 hook_handler.py 分发一致；command_on 为旧版别名）
const ACTION_TYPES = [
  { key: 'injection', label: '提示注入', desc: '注入一段提示文本' },
  { key: 'file_operation', label: '文件操作', desc: '读写 / 检查工作区文件' },
  { key: 'memo_injection', label: '记忆注入', desc: '装载系统共享记忆缓存' },
  { key: 'tool_use_check', label: '工具使用检查', desc: '校验本轮工具调用记录' },
  { key: 'command_run', label: '命令执行', desc: '在终端执行一条命令' },
] as const;

type ActionTypeKey = (typeof ACTION_TYPES)[number]['key'];

interface AgentAction {
  id: string;
  type: string;
  label: string; // 中文名（已知类型展开 / 未知类型显示原名）
  config: Record<string, unknown>; // YAML action 的参数（可被前端直接编辑）
}

interface FieldDef {
  key: string;
  label: string;
  kind: 'text' | 'number' | 'textarea' | 'bool' | 'select';
  options?: string[];
  placeholder?: string;
  // 仅在满足条件时展示（例如 file_operation.content 只在 write_in/add_in 时出现）
  when?: { key: string; in?: unknown[]; value?: unknown };
}

// 各动作类型的“常用字段”定义（用于结构化编辑）；未覆盖的字段走通用 JSON 编辑器兜底
const FIELD_SCHEMA: Record<string, FieldDef[]> = {
  injection: [
    { key: 'content', label: '注入内容', kind: 'textarea', placeholder: '注入给 Agent 的提示文本' },
    // 注意：delay / interval 不放在这里——它们仅在 on_loop_epoch（每轮循环运行时）以“二选一开关”出现
  ],
  file_operation: [
    { key: 'action', label: '操作', kind: 'select', options: ['read', 'exist_check', 'write_in', 'add_in', 'delete'] },
    { key: 'path', label: '路径', kind: 'text', placeholder: '例如 @RULES / agent_vm/xxx.txt' },
    {
      key: 'content',
      label: '写入内容',
      kind: 'textarea',
      placeholder: 'write_in / add_in 时写入的内容',
      when: { key: 'action', in: ['write_in', 'add_in'] },
    },
    { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' },
  ],
  memo_injection: [
    { key: 'type', label: '记忆类型', kind: 'text', placeholder: 'full / light / 其它键名' },
    { key: 'count', label: '条数 count', kind: 'number' },
  ],
  tool_use_check: [
    { key: 'name', label: '工具名 name', kind: 'text', placeholder: '例如 Memo / ComputerUse' },
    { key: 'successed_prompt', label: '成功提示 successed_prompt', kind: 'text' },
    { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' },
  ],
  command_run: [
    { key: 'command', label: '命令', kind: 'text', placeholder: '要执行的 shell 命令' },
    { key: 'return_log', label: '回传输出 return_log', kind: 'bool' },
    { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' },
  ],
  command_on: [
    { key: 'command', label: '命令', kind: 'text', placeholder: '要执行的 shell 命令' },
    { key: 'return_log', label: '回传输出 return_log', kind: 'bool' },
    { key: 'failed_prompt', label: '失败提示 failed_prompt', kind: 'text' },
  ],
};

const labelOfType = (type: string) => ACTION_TYPES.find((a) => a.key === type)?.label ?? type;

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v);

const makeActionId = (hookKey: HookKey) => `${hookKey}-${Math.random().toString(36).slice(2, 9)}`;

const makeEmptyHooks = (): Record<HookKey, AgentAction[]> => {
  const st = {} as Record<HookKey, AgentAction[]>;
  HOOK_KEYS.forEach((k) => (st[k] = []));
  return st;
};

// 从 YAML 的 hook 动作数组转换到编辑器内部结构
const toActions = (hookKey: HookKey, arr: unknown): AgentAction[] => {
  if (!Array.isArray(arr)) return [];
  return arr
    .map((item, i) => {
      if (!isPlainObject(item)) return null;
      const keys = Object.keys(item);
      if (keys.length === 0) return null;
      const type = keys[0];
      const cfg = item[type];
      return {
        id: `${hookKey}-${i}-${type}`,
        type,
        label: labelOfType(type),
        config: isPlainObject(cfg) ? cfg : {},
      };
    })
    .filter((x): x is AgentAction => x !== null);
};

const cloneJson = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };

// 隐藏连线用锚点（保留 handle 用于精确连边，但视觉上不显示小圆点）；
// ag-dummy 为纯路由用的隐形节点（外绕回线轨道）
const HIDE_HANDLE_CSS = `
  .react-flow__handle.ag-node-hidden-handle {
    width: 0 !important;
    height: 0 !important;
    min-width: 0 !important;
    min-height: 0 !important;
    border: 0 !important;
    background: transparent !important;
    opacity: 0;
  }
  .react-flow__node.ag-dummy {
    border: 0 !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    opacity: 0 !important;
    pointer-events: none !important;
  }
`;

// 每个可编辑节点（Hook/决策站）四个方向都提供收发锚点，供不同走向的边使用
const STATION_HANDLES = (
  <>
    <Handle type="target" position={Position.Top} id="t_top" className="ag-node-hidden-handle" />
    <Handle type="source" position={Position.Top} id="s_top" className="ag-node-hidden-handle" />
    <Handle type="target" position={Position.Bottom} id="t_bot" className="ag-node-hidden-handle" />
    <Handle type="source" position={Position.Bottom} id="s_bot" className="ag-node-hidden-handle" />
    <Handle type="target" position={Position.Left} id="t_left" className="ag-node-hidden-handle" />
    <Handle type="source" position={Position.Left} id="s_left" className="ag-node-hidden-handle" />
    <Handle type="target" position={Position.Right} id="t_right" className="ag-node-hidden-handle" />
    <Handle type="source" position={Position.Right} id="s_right" className="ag-node-hidden-handle" />
  </>
);

interface StationData {
  label: string;
  code: string;
  color: string;
  items: AgentAction[];
}

// Hook 决策站：白底卡片，头部用“小色块”表示 Hook 颜色（与 Workflow 节点风格一致）
function StationNode({ data }: { data: StationData }) {
  const { label, code, color, items } = data;
  return (
    <div className="flex flex-col w-full h-full bg-paper">
      {STATION_HANDLES}
      <div className="flex items-center gap-2 px-3 py-2 border-b-2 border-ink/15">
        <span className="w-3 h-3 shrink-0 border-2 border-ink inline-block" style={{ background: color }} />
        <span
          className="font-black text-ink text-[15px] leading-none truncate"
          style={{ fontFamily: '"Comic Sans MS", cursive' }}
        >
          {label}
        </span>
        <span className="ml-auto shrink-0 bg-cream border-2 border-ink px-2 py-0.5 text-[11px] font-black text-ink leading-none" style={sketchyShape2}>
          {items.length}
        </span>
      </div>
      <div className="flex flex-col gap-1 px-2 py-1.5">
        {items.length === 0 ? (
          <div
            className="text-center text-[11px] font-bold text-ink/35 border-2 border-dashed border-ink/25 py-2"
            style={{ fontFamily: '"Comic Sans MS", cursive' }}
          >
            未配置动作（点击左侧 + 添加）
          </div>
        ) : (
          items.map((it, idx) => (
            <div key={it.id} className="flex items-center gap-2 border-2 border-ink/80 px-2 py-1 bg-cream" style={sketchyShape2}>
              <span className="w-4 shrink-0 text-center text-[11px] font-black text-ink/40 leading-none">{idx + 1}</span>
              <span className="font-black text-ink text-[13px] leading-none truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                {it.label}
              </span>
              <span className="ml-auto shrink-0 text-[10px] font-bold text-ink/40 leading-none">{it.type}</span>
            </div>
          ))
        )}
      </div>
      <div className="px-3 pb-1.5 text-[10px] font-bold text-ink/30 leading-none">{code}</div>
    </div>
  );
}

// 骨架上的普通节点（用户输入 / 结束）——白底，与 Workflow 的普通节点一致
function PlainNode({ data }: { data: { label: string } }) {
  return (
    <div className="w-full h-full flex items-center justify-center px-3">
      <Handle type="target" position={Position.Top} id="t_top" className="ag-node-hidden-handle" />
      <Handle type="target" position={Position.Left} id="t_left" className="ag-node-hidden-handle" />
      <Handle type="source" position={Position.Bottom} id="s_bot" className="ag-node-hidden-handle" />
      <Handle type="source" position={Position.Left} id="s_left" className="ag-node-hidden-handle" />
      <span
        className="font-black text-ink text-[15px] text-center leading-snug"
        style={{ fontFamily: '"Comic Sans MS", cursive' }}
      >
        {data.label}
      </span>
    </div>
  );
}

// 纯路由用的隐形节点：把外绕回线绕到主体外侧走线，避免与主干连线重叠
function DummyNode() {
  return (
    <div className="w-0 h-0">
      <Handle type="target" position={Position.Top} id="t_top" className="ag-node-hidden-handle" />
      <Handle type="source" position={Position.Top} id="s_top" className="ag-node-hidden-handle" />
      <Handle type="target" position={Position.Bottom} id="t_bot" className="ag-node-hidden-handle" />
      <Handle type="source" position={Position.Bottom} id="s_bot" className="ag-node-hidden-handle" />
      <Handle type="target" position={Position.Left} id="t_left" className="ag-node-hidden-handle" />
      <Handle type="source" position={Position.Left} id="s_left" className="ag-node-hidden-handle" />
      <Handle type="target" position={Position.Right} id="t_right" className="ag-node-hidden-handle" />
      <Handle type="source" position={Position.Right} id="s_right" className="ag-node-hidden-handle" />
    </div>
  );
}

// 注册给 ReactFlow 使用的节点渲染器
const nodeTypes = { station: StationNode, plain: PlainNode, dummy: DummyNode };

// 骨架图布局常量
const STATION_WIDTH = 300;
const STATION_H = (count: number) => 48 + (count > 0 ? count * 34 : 34); // 头部 + 每行动作
const PLAIN_H = 60;
const GAP_V = 90;

// ============ 配置字段控件 ============

type FieldKind = 'text' | 'number' | 'textarea' | 'bool' | 'select' | 'json';

interface FieldControlProps {
  kind: FieldKind;
  value: unknown;
  options?: string[];
  placeholder?: string;
  onCommit: (v: unknown) => void; // '' / undefined 表示删除该字段
}

const prettyJson = (value: unknown): string => {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const inputCls =
  'w-full bg-cream border-2 border-ink px-2 py-1 text-[13px] font-bold text-ink outline-none focus:bg-paper';

function FieldControl({ kind, value, options = [], placeholder, onCommit }: FieldControlProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState(false);

  if (kind === 'select' || kind === 'bool') {
    const current = value === undefined || value === null ? '' : String(value);
    return (
      <select className={inputCls} value={current} onChange={(e) => onCommit(e.target.value)}>
        <option value="">（未设置）</option>
        {kind === 'bool' ? (
          <>
            <option value="true">是</option>
            <option value="false">否</option>
          </>
        ) : (
          options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))
        )}
      </select>
    );
  }

  if (kind === 'number') {
    const current = value === undefined || value === null ? '' : String(value);
    return (
      <input
        type="number"
        className={inputCls}
        value={current}
        placeholder={placeholder}
        onChange={(e) => {
          const t = e.target.value;
          if (t === '') return onCommit('');
          const n = Number(t);
          if (!Number.isNaN(n)) onCommit(n);
        }}
      />
    );
  }

  if (kind === 'json') {
    const shown = draft ?? prettyJson(value);
    return (
      <div className="w-full">
        <textarea
          rows={3}
          className={`${inputCls} resize-y font-mono ${error ? '!border-[#bf616a] !bg-[#fdeceb]' : ''}`}
          value={shown}
          placeholder={placeholder ?? 'JSON 文本（留空则删除该配置）'}
          onChange={(e) => {
            setDraft(e.target.value);
            setError(false);
          }}
          onBlur={() => {
            const raw = (draft ?? prettyJson(value)).trim();
            if (!raw) {
              setDraft(null);
              setError(false);
              onCommit(undefined);
              return;
            }
            try {
              onCommit(JSON.parse(raw));
              setDraft(null);
              setError(false);
            } catch {
              setError(true);
            }
          }}
        />
        {error && (
          <div className="text-[10px] font-bold text-[#bf616a] leading-tight mt-0.5">JSON 格式有误，未保存</div>
        )}
      </div>
    );
  }

  if (kind === 'textarea') {
    return (
      <textarea
        rows={2}
        className={`${inputCls} resize-y`}
        value={value === undefined || value === null ? '' : String(value)}
        placeholder={placeholder}
        onChange={(e) => onCommit(e.target.value)}
      />
    );
  }

  return (
    <input
      type="text"
      className={inputCls}
      value={value === undefined || value === null ? '' : String(value)}
      placeholder={placeholder}
      onChange={(e) => onCommit(e.target.value)}
    />
  );
}

// 触发时机开关：未点亮 = 延迟；点亮 = 间隔
function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className="flex items-center gap-1.5 group"
      title={checked ? '当前：间隔触发，点击切换为延迟' : '当前：延迟触发，点击切换为间隔'}
    >
      {checked ? (
        <ToggleRight size={20} strokeWidth={2.5} className="text-terracotta" />
      ) : (
        <ToggleLeft size={20} strokeWidth={2.5} className="text-ink/60 group-hover:text-ink" />
      )}
      <span className="text-[11px] font-black text-ink/70 leading-none" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
        {checked ? '间隔' : '延迟'}
      </span>
    </button>
  );
}

// 字段可见性：when.in / when.value 命中才展示
const isFieldVisible = (field: FieldDef, cfg: Record<string, unknown>): boolean => {
  if (!field.when) return true;
  const actual = cfg[field.when.key];
  if (field.when.value !== undefined) return actual === field.when.value;
  if (field.when.in) return field.when.in.some((v) => v === actual);
  return true;
};

// 把字符串解析成 YAML 里更像的标量（纯数字/布尔 → 原类型，其它保留字符串）
const parseScalar = (text: string): unknown => {
  const t = text.trim();
  if (t === 'true') return true;
  if (t === 'false') return false;
  if (t !== '' && !Number.isNaN(Number(t))) return Number(t);
  return t;
};

// parameter_check 的结构化编辑器：
// 外层 = 检查项列表（命中任一检查项即算用对该工具），一项内多个参数条件需同时满足。
// 新增的检查项先进入“待填草稿”，填完参数名与期望值后才真正写入配置。
function ParameterCheckEditor({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (v: unknown[]) => void;
}) {
  const [pending, setPending] = useState<{ key: string; value: string }[]>([]);

  const items: { key: string; value: unknown }[][] = Array.isArray(value)
    ? value.map((it) =>
        isPlainObject(it) ? Object.entries(it).map(([k, v]) => ({ key: k, value: v })) : []
      )
    : [];

  const build = (pairItems: { key: string; value: unknown }[][]) => {
    const out = pairItems
      .map((pairs) => {
        const obj: Record<string, unknown> = {};
        pairs.forEach((p) => {
          const key = (p.key ?? '').trim();
          if (!key) return;
          obj[key] = parseScalar(
            p.value === undefined || p.value === null
              ? ''
              : typeof p.value === 'string'
                ? p.value.trim()
                : String(p.value)
          );
        });
        return obj;
      })
      .filter((obj) => Object.keys(obj).length > 0);
    onChange(out);
  };

  const editPending = (idx: number, field: 'key' | 'value', text: string) => {
    const rows = pending.map((r, j) => (j === idx ? { ...r, [field]: text } : r));
    const row = rows[idx];
    if (row.key.trim() && row.value.trim() !== '') {
      setPending(rows.filter((_, j) => j !== idx));
      build([...items, [{ key: row.key, value: row.value }]]);
    } else {
      setPending(rows);
    }
  };

  const totalVisible = items.length + pending.length;

  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] font-bold text-ink/45 leading-tight" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
        任一项匹配即算使用该工具；一项内多个条件需同时满足
      </div>
      {totalVisible === 0 && (
        <div className="text-center text-[11px] font-bold text-ink/35 border-2 border-dashed border-ink/25 py-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          无参数约束（点击下方添加）
        </div>
      )}

      {items.map((pairs, idx) => (
        <div key={idx} className="flex flex-col gap-1.5 border-2 border-ink/70 p-2 bg-cream/60" style={sketchyShape2}>
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-black text-ink/70 leading-none">检查项 {idx + 1}</span>
            <div className="flex items-center gap-1">
              <button
                title="在该检查项内新增参数条件"
                onClick={() => setPending([...pending, { key: '', value: '' }])}
                className="w-6 h-6 flex items-center justify-center bg-cream border-2 border-ink text-ink hover:bg-sand"
                style={sketchyShape1}
              >
                <Plus size={12} strokeWidth={3} />
              </button>
              <button
                title="删除该检查项"
                onClick={() => build(items.filter((_, i) => i !== idx))}
                className="w-6 h-6 flex items-center justify-center text-ink/50 hover:text-paper hover:bg-[#bf616a] border-2 border-ink/40 hover:border-ink"
                style={sketchyShape2}
              >
                <Trash2 size={12} strokeWidth={2.5} />
              </button>
            </div>
          </div>
          {pairs.map((pair, pidx) => (
            <div key={pidx} className="flex items-center gap-1.5">
              <input
                className="flex-1 min-w-0 bg-paper border-2 border-ink px-2 py-1 text-[12px] font-bold text-ink outline-none"
                value={pair.key}
                placeholder="参数名"
                onChange={(e) => {
                  const next = items.map((p, i) =>
                    i === idx ? p.map((q, j) => (j === pidx ? { ...q, key: e.target.value } : q)) : p
                  );
                  build(next);
                }}
              />
              <span className="text-ink/50 font-black text-xs">=</span>
              <input
                className="flex-1 min-w-0 bg-paper border-2 border-ink px-2 py-1 text-[12px] font-bold text-ink outline-none"
                value={pair.value === undefined || pair.value === null ? '' : String(pair.value)}
                placeholder="期望值"
                onChange={(e) => {
                  const next = items.map((p, i) =>
                    i === idx ? p.map((q, j) => (j === pidx ? { ...q, value: e.target.value } : q)) : p
                  );
                  build(next);
                }}
              />
              <button
                title="移除该条件"
                onClick={() => {
                  const next = items.map((p, i) =>
                    i === idx ? p.filter((_, j) => j !== pidx) : p
                  );
                  build(next);
                }}
                className="w-6 h-6 shrink-0 flex items-center justify-center text-ink/40 hover:text-paper hover:bg-[#bf616a]"
              >
                <Trash2 size={12} strokeWidth={2.5} />
              </button>
            </div>
          ))}
        </div>
      ))}

      {/* 待填草稿（新增后尚未填完整的检查项） */}
      {pending.map((row, idx) => (
        <div
          key={`pending-${idx}`}
          className="flex flex-col gap-1.5 border-2 border-dashed border-terracotta/70 p-2 bg-cream/30"
          style={sketchyShape2}
        >
          <span className="text-[11px] font-black text-terracotta leading-none">新检查项（待填写）</span>
          <div className="flex items-center gap-1.5">
            <input
              className="flex-1 min-w-0 bg-paper border-2 border-ink px-2 py-1 text-[12px] font-bold text-ink outline-none"
              value={row.key}
              placeholder="参数名（例如 action）"
              onChange={(e) => editPending(idx, 'key', e.target.value)}
            />
            <span className="text-ink/50 font-black text-xs">=</span>
            <input
              className="flex-1 min-w-0 bg-paper border-2 border-ink px-2 py-1 text-[12px] font-bold text-ink outline-none"
              value={row.value}
              placeholder="期望值（例如 add）"
              onChange={(e) => editPending(idx, 'value', e.target.value)}
            />
            <button
              title="放弃该检查项"
              onClick={() => setPending(pending.filter((_, j) => j !== idx))}
              className="w-6 h-6 shrink-0 flex items-center justify-center text-ink/40 hover:text-paper hover:bg-[#bf616a]"
            >
              <Trash2 size={12} strokeWidth={2.5} />
            </button>
          </div>
        </div>
      ))}

      <button
        title="新增检查项"
        onClick={() => setPending([...pending, { key: '', value: '' }])}
        className="self-start flex items-center gap-1 px-3 py-1.5 bg-cream border-2 border-ink text-ink font-black hover:bg-sand text-[12px]"
        style={sketchyShape1}
      >
        <Plus size={13} strokeWidth={3} />
        添加检查项
      </button>
    </div>
  );
}

// action 的配置编辑器：已知字段按类型渲染；未知字段用 JSON 兜底（不丢数据）
function ConfigEditor({
  action,
  schema,
  allowTiming,
  allowExpect,
  onField,
  onReplace,
}: {
  action: AgentAction;
  schema: FieldDef[];
  allowTiming: boolean; // 仅 on_loop_epoch（每轮循环运行时）允许配置 delay/interval
  allowExpect: boolean; // 仅 on_loop_end（循环结束时）允许配置退出期望（成功/失败）
  onField: (key: string, val: unknown) => void;
  onReplace: (cfg: Record<string, unknown>) => void;
}) {
  const cfg = action.config;
  const schemaKeys = new Set(schema.map((f) => f.key));
  // allowTiming 时 delay/interval 由“触发时机”开关管理；tool_use_check 的 parameter_check 走结构化编辑器
  const isTimingKey = (k: string) => allowTiming && (k === 'delay' || k === 'interval');
  const isParamCheckKey = (k: string) => action.type === 'tool_use_check' && k === 'parameter_check';
  const isExpectKey = (k: string) => allowExpect && k === 'expect';
  const extraKeys = Object.keys(cfg).filter(
    (k) => !schemaKeys.has(k) && !isTimingKey(k) && !isParamCheckKey(k) && !isExpectKey(k)
  );

  const mergeExtra = (parsed: unknown) => {
    const next: Record<string, unknown> = { ...cfg };
    extraKeys.forEach((k) => delete next[k]);
    if (isPlainObject(parsed)) {
      Object.entries(parsed).forEach(([k, v]) => {
        if (v !== undefined && v !== '') next[k] = v;
      });
    }
    onReplace(next);
  };

  // ---- delay / interval：二选一（默认不点 = 延迟；点开 = 间隔），仅 epoch 可见 ----
  const timingOn = Object.prototype.hasOwnProperty.call(cfg, 'interval');
  const timingKey: 'delay' | 'interval' = timingOn ? 'interval' : 'delay';
  const commitTiming = (isInterval: boolean, val: unknown) => {
    const next: Record<string, unknown> = {};
    Object.keys(cfg).forEach((k) => {
      if (k === 'delay' || k === 'interval') return;
      next[k] = cfg[k];
    });
    if (val !== '' && val !== undefined && val !== null) next[isInterval ? 'interval' : 'delay'] = val;
    onReplace(next);
  };

  // ---- 循环结束时的“退出期望”：该条件符合期望才算通过、才能跳出循环 ----
  const expectFail = cfg.expect === 'fail' || cfg.expect === false;
  const commitExpect = (fail: boolean) => {
    const next: Record<string, unknown> = { ...cfg };
    delete next.expect;
    if (fail) next.expect = 'fail';
    onReplace(next);
  };

  const expectBtn = (fail: boolean) => (
    <button
      onClick={() => commitExpect(fail)}
      className={`flex-1 py-1.5 px-2 border-2 border-ink text-[12px] font-black transition-colors ${
        expectFail === fail ? 'bg-ink text-paper' : 'bg-cream text-ink hover:bg-sand'
      }`}
      style={sketchyShape2}
    >
      {fail ? '期望失败' : '期望成功'}
    </button>
  );

  return (
    <div className="flex flex-col gap-2 px-3 py-2 bg-paper border-t-2 border-ink/10">
      {allowTiming && (
        <div className="flex flex-col gap-1.5 border-2 border-dashed border-ink/30 p-2 bg-cream/50">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-black text-ink/60 leading-none">触发时机</span>
            <ToggleSwitch
              checked={timingOn}
              onChange={(on) => commitTiming(on, cfg.interval ?? cfg.delay)}
            />
          </div>
          <span className="text-[11px] font-black text-ink/60 leading-none">
            {timingOn ? '间隔轮次 interval' : '延迟轮次 delay'}
          </span>
          <FieldControl
            kind="number"
            value={cfg[timingKey]}
            placeholder={timingOn ? '每隔 N 轮触发一次' : '仅在第 N 轮触发一次'}
            onCommit={(v) => commitTiming(timingOn, v)}
          />
        </div>
      )}
      {allowExpect && (
        <div className="flex flex-col gap-1.5 border-2 border-dashed border-ink/30 p-2 bg-cream/50">
          <span className="text-[11px] font-black text-ink/60 leading-none">退出期望（决定能否跳出循环）</span>
          <div className="flex gap-2">{expectBtn(false)}{expectBtn(true)}</div>
          <p className="m-0 text-[10px] font-bold text-ink/40 leading-tight" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
            期望“失败”= 该条件未满足才算通过，允许结束本轮
          </p>
        </div>
      )}
      {schema.length === 0 && (
        <div className="text-[11px] font-bold text-ink/45" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          该动作类型暂无结构化解（{action.type}），直接编辑完整配置：
        </div>
      )}
      {schema.filter((f) => isFieldVisible(f, cfg)).map((f) => (
        <div key={f.key} className="flex flex-col gap-1">
          <span className="text-[11px] font-black text-ink/60 leading-none">{f.label}</span>
          <FieldControl
            kind={f.kind}
            value={cfg[f.key]}
            options={f.options}
            placeholder={f.placeholder}
            onCommit={(v) => onField(f.key, v)}
          />
        </div>
      ))}
      {action.type === 'tool_use_check' && (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-black text-ink/60 leading-none">参数约束 parameter_check</span>
          <ParameterCheckEditor
            value={cfg.parameter_check}
            onChange={(v) => {
              const next = { ...cfg };
              if (v.length > 0) next.parameter_check = v;
              else delete next.parameter_check;
              onReplace(next);
            }}
          />
        </div>
      )}
      {schema.length > 0 && extraKeys.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-black text-ink/60 leading-none">
            其他字段（{extraKeys.join('、')}）
          </span>
          <FieldControl
            kind="json"
            value={Object.fromEntries(extraKeys.map((k) => [k, cfg[k]]))}
            onCommit={(v) => mergeExtra(v)}
          />
        </div>
      )}
      {schema.length === 0 && (
        <FieldControl kind="json" value={cfg} onCommit={(v) => onReplace(isPlainObject(v) ? v : {})} />
      )}
    </div>
  );
}

// ============ 对外暴露的句柄（供顶部 Toolbar 调用） ============

export interface AgentLoopEditorHandle {
  openFile: (name: string) => Promise<void>;
  save: () => Promise<void>;
  create: () => void;
  deleteFile: (name: string) => Promise<void>;
}

export interface AgentLoopEditorProps {
  onActiveChange?: (name: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
}

// ============ 主组件 ============

const AgentLoopEditor = forwardRef<AgentLoopEditorHandle, AgentLoopEditorProps>(function AgentLoopEditor(
  { onActiveChange, onDirtyChange },
  ref
) {
  const [paradigmState, setParadigmState] = useState<Record<HookKey, AgentAction[]>>(makeEmptyHooks);
  const [openHooks, setOpenHooks] = useState<HookKey[]>(HOOK_KEYS);
  const [openActions, setOpenActions] = useState<Set<string>>(new Set());
  const [menuFor, setMenuFor] = useState<HookKey | null>(null);
  const sectionRef = useRef<HTMLDivElement | null>(null);

  const [activeFile, setActiveFile] = useState('');
  const [rootMeta, setRootMeta] = useState<Record<string, unknown>>({});
  const [extraHooks, setExtraHooks] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  // 最近一次加载/保存的完整 YAML 快照（JSON），用于精确计算是否有未保存改动
  const [baselineKey, setBaselineKey] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');

  // 把内部状态汇报给 EditorPage（用于顶部 Toolbar 展示当前文件）
  useEffect(() => {
    onActiveChange?.(activeFile);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFile]);

  // 点击下拉菜单以外区域时收起
  useEffect(() => {
    if (!menuFor) return;
    const onDocDown = (e: MouseEvent) => {
      if (sectionRef.current && !sectionRef.current.contains(e.target as Node)) {
        setMenuFor(null);
      }
    };
    document.addEventListener('mousedown', onDocDown);
    return () => document.removeEventListener('mousedown', onDocDown);
  }, [menuFor]);

  const applyDoc = (name: string, root: Record<string, unknown>) => {
    const hooks = isPlainObject(root.hooks) ? root.hooks : {};
    const meta: Record<string, unknown> = {};
    const extra: Record<string, unknown> = {};
    Object.entries(root).forEach(([k, v]) => {
      if (k === 'hooks') return;
      meta[k] = v;
    });
    Object.entries(hooks).forEach(([k, v]) => {
      if (!HOOK_KEY_SET.has(k)) extra[k] = v;
    });

    const st = {} as Record<HookKey, AgentAction[]>;
    HOOK_KEYS.forEach((hk) => {
      st[hk] = toActions(hk, hooks[hk]);
    });
    setParadigmState(st);
    setRootMeta(meta);
    setExtraHooks(extra);
    setActiveFile(name);
    setBaselineKey(JSON.stringify(cloneJson(root)));
    setOpenActions(new Set());
    setMenuFor(null);
  };

  const refreshFiles = async (): Promise<string> => {
    const res = await fetch('/api/paradigms');
    if (!res.ok) throw new Error('获取 paradigm 列表失败');
    const data = await res.json();
    return data.default as string;
  };

  const loadFile = async (name: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/paradigms/${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error(`paradigm 不存在: ${name}`);
      const body = await res.json();
      applyDoc(name, body.data ?? {});
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  // 启动时默认加载 PARADIGM.yaml（默认 Agent Loop）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const defaultName = await refreshFiles();
        if (!cancelled && defaultName) await loadFile(defaultName);
      } catch (e) {
        if (!cancelled) toast.error(e instanceof Error ? e.message : '无法连接后端');
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleHook = (hookKey: HookKey) => {
    setOpenHooks((prev) => (prev.includes(hookKey) ? prev.filter((k) => k !== hookKey) : [...prev, hookKey]));
  };

  const toggleAction = (actionId: string) => {
    setOpenActions((prev) => {
      const next = new Set(prev);
      if (next.has(actionId)) next.delete(actionId);
      else next.add(actionId);
      return next;
    });
  };

  const handleAddAction = (hookKey: HookKey, type: ActionTypeKey) => {
    setParadigmState((prev) => ({
      ...prev,
      [hookKey]: [
        ...prev[hookKey],
        { id: makeActionId(hookKey), type, label: labelOfType(type), config: {} },
      ],
    }));
    setMenuFor(null);
  };

  const handleRemoveAction = (hookKey: HookKey, actionId: string) => {
    setParadigmState((prev) => ({
      ...prev,
      [hookKey]: prev[hookKey].filter((a) => a.id !== actionId),
    }));
  };

  // 更新单个字段：''/undefined 表示删除该字段
  const commitField = (hookKey: HookKey, actionId: string, key: string, val: unknown) => {
    setParadigmState((prev) => ({
      ...prev,
      [hookKey]: prev[hookKey].map((a) => {
        if (a.id !== actionId) return a;
        const next = { ...a.config };
        if (val === '' || val === undefined || val === null) delete next[key];
        else next[key] = val;
        return { ...a, config: next };
      }),
    }));
  };

  // 整体替换 config（含 JSON 兜底编辑器）
  const replaceConfig = (hookKey: HookKey, actionId: string, cfg: Record<string, unknown>) => {
    setParadigmState((prev) => ({
      ...prev,
      [hookKey]: prev[hookKey].map((a) => (a.id === actionId ? { ...a, config: cfg } : a)),
    }));
  };

  const buildYamlDoc = (): Record<string, unknown> => {
    const hooks: Record<string, unknown> = { ...cloneJson(extraHooks) };
    HOOK_KEYS.forEach((hk) => {
      hooks[hk] = paradigmState[hk].map((a) => {
        const cfg = isPlainObject(a.config) ? cloneJson(a.config) : {};
        return { [a.type]: cfg };
      });
    });
    return { ...cloneJson(rootMeta), hooks };
  };

  // 与“加载/保存的基线”精确对比：改回原样即不再标脏
  const dirty = baselineKey !== null && JSON.stringify(buildYamlDoc()) !== baselineKey;
  useEffect(() => {
    onDirtyChange?.(dirty);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty]);

  // Toolbar 通过 ref 打开文件（带未保存确认）
  const openFile = async (name: string) => {
    if (!name || name === activeFile) return;
    if (dirty && !window.confirm('当前文件有未保存的修改，切换将丢弃这些修改，确定继续？')) return;
    await loadFile(name);
  };

  const handleSave = async () => {
    if (!activeFile) return;
    setSaving(true);
    try {
      const doc = buildYamlDoc();
      const res = await fetch(`/api/paradigms/${encodeURIComponent(activeFile)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: doc }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error((errBody && errBody.detail) || '保存失败');
      }
      setBaselineKey(JSON.stringify(doc));
      toast.success(`已保存 ${activeFile}.yaml`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const deleteFile = async (name: string) => {
    if (!name) return;
    if (!window.confirm(`确定删除 paradigm「${name}」？该操作不可恢复。`)) return;
    try {
      const res = await fetch(`/api/paradigms/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error((errBody && errBody.detail) || '删除失败');
      }
      toast.success(`已删除 ${name}.yaml`);
      const defaultName = await refreshFiles();
      if (name === activeFile) await loadFile(defaultName);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '删除失败');
    }
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) {
      toast.error('请输入文件名');
      return;
    }
    setSaving(true);
    try {
      const skeleton: Record<string, unknown> = {
        name,
        description: '新的 Agent Loop',
        path: 'agent_vm',
        hooks: HOOK_KEYS.reduce<Record<string, unknown[]>>((acc, k) => {
          acc[k] = [];
          return acc;
        }, {}),
      };
      const res = await fetch(`/api/paradigms/${encodeURIComponent(name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: skeleton }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error((errBody && errBody.detail) || '新建失败');
      }
      setCreating(false);
      setNewName('');
      await loadFile(name);
      toast.success(`已新建 ${name}.yaml`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '新建失败');
    } finally {
      setSaving(false);
    }
  };

  useImperativeHandle(ref, () => ({
    openFile,
    save: handleSave,
    create: () => setCreating(true),
    deleteFile,
  }));

  // ===== 依据左侧状态，在「带环骨架」上推导流程图 =====
  // 骨架语义（对应 Mermaid 示例）：
  //   构建系统提示词 → 用户输入 → 循环开始 → 每轮循环迭代 →
  //     ├─ 有工具调用 → 工具调用检查 ─┐
  //     └─ 无工具调用 ────────────┼→ 循环结束检查 →(成功)→ 结束
  //                                   └─(失败)→ 回到「每轮循环迭代」（形成环）
  //   结束后 → 回到「用户输入」（下一轮任务循环，走左外绕线）
  const { nodes, edges } = useMemo(() => {
    const generatedNodes: FlowNode[] = [];
    const generatedEdges: FlowEdge[] = [];

    const addNode = (node: FlowNode) => {
      generatedNodes.push(node);
    };

    const addEdge = (
      source: string,
      sourceHandle: string,
      target: string,
      targetHandle: string,
      label?: string,
      arrow: boolean = true
    ) => {
      const edge: FlowEdge = {
        id: `e-${source}->${target}@${sourceHandle}-${targetHandle}`,
        source,
        sourceHandle,
        target,
        targetHandle,
        type: 'step',
        animated: true,
        style: { stroke: '#1A1A1A', strokeWidth: 2 },
        markerEnd: arrow
          ? { type: MarkerType.ArrowClosed, color: '#1A1A1A', width: 16, height: 16 }
          : undefined,
      };
      if (label) {
        edge.label = label;
        edge.labelStyle = { fill: '#1A1A1A', fontSize: 13, fontWeight: 700, fontFamily: '"Comic Sans MS", cursive' };
        edge.labelBgStyle = { fill: '#FAF8F5', stroke: '#1A1A1A', strokeWidth: 1 };
        edge.labelBgPadding = [8, 5] as never;
      }
      generatedEdges.push(edge);
    };

    const metaOf = (key: HookKey) => HOOK_META.find((h) => h.key === key)!;
    const station = (key: HookKey, items: AgentAction[]): FlowNode => {
      const meta = metaOf(key);
      return {
        id: key,
        type: 'station',
        position: { x: 0, y: 0 },
        data: { label: meta.label, code: key, color: meta.color, items },
        style: { width: STATION_WIDTH },
      };
    };
    const plain = (id: string, label: string): FlowNode => ({
      id,
      type: 'plain',
      position: { x: 0, y: 0 },
      data: { label },
      style: { width: STATION_WIDTH, height: PLAIN_H, background: '#FFFFFF' },
    });

    // ---- 布局：主链居左（X_LEFT），每轮迭代检查与工具调用分支左右并排 ----
    const X_LEFT = 180;
    const X_RIGHT = X_LEFT + 470; // 右侧列：工具调用检查
    let cursorY = 28;

    const put = (node: FlowNode, x: number, y: number, height: number) => {
      node.position = { x, y };
      addNode(node);
      cursorY = Math.max(cursorY, y + height + GAP_V);
    };

    const buildItems = paradigmState.on_build_system_prompt;
    put(station('on_build_system_prompt', buildItems), X_LEFT, cursorY, STATION_H(buildItems.length));

    // 用户输入（固定节点）——结束后回线的落点
    const userInputTop = cursorY;
    put(plain('user_input', '用户输入'), X_LEFT, cursorY, PLAIN_H);

    const startItems = paradigmState.on_loop_start;
    put(station('on_loop_start', startItems), X_LEFT, cursorY, STATION_H(startItems.length));

    const epochTop = cursorY;
    const epochItems = paradigmState.on_loop_epoch;
    const epochH = STATION_H(epochItems.length);
    const epochNode = station('on_loop_epoch', epochItems);
    epochNode.position = { x: X_LEFT, y: epochTop };
    addNode(epochNode);

    const toolItems = paradigmState.on_tool_calling;
    const toolNode = station('on_tool_calling', toolItems);
    toolNode.position = { x: X_RIGHT, y: epochTop };
    addNode(toolNode);

    const rowBottom = Math.max(epochTop + epochH, epochTop + STATION_H(toolItems.length));
    const endCheckItems = paradigmState.on_loop_end;
    const endCheckNode = station('on_loop_end', endCheckItems);
    endCheckNode.position = { x: X_LEFT, y: rowBottom + GAP_V };
    addNode(endCheckNode);

    const endY = rowBottom + GAP_V + STATION_H(endCheckItems.length) + GAP_V;
    const endNode = plain('end', '结束');
    endNode.position = { x: X_LEFT, y: endY };
    addNode(endNode);

    // ---- 回环路由点：左侧外绕轨道 ----
    // 轨道1（x = loopRailX1）：循环结束检查(失败) → 每轮循环迭代
    // 轨道2（x = loopRailX2）：结束 → 用户输入（下一轮任务）
    const loopRailX1 = X_LEFT - 140; // 60
    const loopRailX2 = X_LEFT - 70; // 110
    const endCheckTop = endCheckNode.position!.y;

    const pivotD = {
      id: 'loop_pivot_top',
      type: 'dummy',
      position: { x: loopRailX1, y: epochTop + epochH / 2 },
      style: { width: 1, height: 1 },
      className: 'ag-dummy',
    };
    const pivotF = {
      id: 'loop_pivot_bottom',
      type: 'dummy',
      position: { x: loopRailX1, y: endCheckTop + STATION_H(endCheckItems.length) / 2 },
      style: { width: 1, height: 1 },
      className: 'ag-dummy',
    };

    const userMidY = userInputTop + PLAIN_H / 2;
    const endMidY = endY + PLAIN_H / 2;
    const pivotEndTop = {
      id: 'end_loop_top',
      type: 'dummy',
      position: { x: loopRailX2, y: userMidY },
      style: { width: 1, height: 1 },
      className: 'ag-dummy',
    };
    const pivotEndBottom = {
      id: 'end_loop_bottom',
      type: 'dummy',
      position: { x: loopRailX2, y: endMidY },
      style: { width: 1, height: 1 },
      className: 'ag-dummy',
    };

    addNode(pivotD as FlowNode);
    addNode(pivotF as FlowNode);
    addNode(pivotEndTop as FlowNode);
    addNode(pivotEndBottom as FlowNode);

    // ---- 连线（全部横平竖直，使用直角 step 连线） ----
    addEdge('on_build_system_prompt', 's_bot', 'user_input', 't_top');
    addEdge('user_input', 's_bot', 'on_loop_start', 't_top');
    addEdge('on_loop_start', 's_bot', 'on_loop_epoch', 't_top');
    // 分支：有工具调用 → 工具调用检查；无工具调用 → 直达结束检查
    addEdge('on_loop_epoch', 's_right', 'on_tool_calling', 't_left', '有工具调用');
    addEdge('on_loop_epoch', 's_bot', 'on_loop_end', 't_top', '无工具调用');
    // 工具调用检查通过 → 回到「每轮循环迭代时」（进行下一轮迭代；无工具调用时才进入结束检查）
    addEdge('on_tool_calling', 's_bot', 'on_loop_epoch', 't_bot');
    // 环1：结束检查未通过 → 左侧绕回「每轮循环迭代」
    addEdge('on_loop_end', 's_left', 'loop_pivot_bottom', 't_left', undefined, false);
    addEdge('loop_pivot_bottom', 's_top', 'loop_pivot_top', 't_bot', '失败 · 下一轮', false);
    addEdge('loop_pivot_top', 's_right', 'on_loop_epoch', 't_left');
    // 结束检查通过 → 结束
    addEdge('on_loop_end', 's_bot', 'end', 't_top', '成功 · 结束');
    // 环2：结束后回到「用户输入」（新一轮任务循环）
    addEdge('end', 's_left', 'end_loop_bottom', 't_left', undefined, false);
    addEdge('end_loop_bottom', 's_top', 'end_loop_top', 't_bot', undefined, false);
    addEdge('end_loop_top', 's_right', 'user_input', 't_left');

    return { nodes: generatedNodes, edges: generatedEdges };
  }, [paradigmState]);

  return (
    <div className="flex-1 min-h-0 flex gap-10 h-full w-full min-w-0">
      {/* ===== 左侧：Hook 组件视图（文件管理在顶部 Toolbar） ===== */}
      <div
        style={sketchyShape1}
        className="w-[360px] shrink-0 h-full bg-paper border-4 border-ink shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] flex flex-col overflow-hidden relative z-10"
      >
        <div className="px-4 pt-4 pb-3 border-b-4 border-ink bg-cream flex items-end justify-between gap-2">
          <div>
            <h3 className="text-xl font-black text-ink m-0 tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              组件
            </h3>
            <p className="m-0 mt-1 text-[11px] font-bold text-ink/50" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              Hook 动作编排{loading ? '（加载中…）' : ''}
            </p>
          </div>
        </div>

        {/* Hook 列表（可折叠 + action 可展开编辑配置） */}
        <div className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-3">
          {HOOK_META.map((hook) => {
            const open = openHooks.includes(hook.key);
            const actions = paradigmState[hook.key];
            return (
              <div key={hook.key} ref={menuFor === hook.key ? sectionRef : undefined}>
                <div className="relative bg-paper border-2 border-ink overflow-visible">
                  {/* Hook 头部 */}
                  <div
                    onClick={() => toggleHook(hook.key)}
                    className="flex items-center justify-between gap-2 px-3 py-2.5 cursor-pointer select-none bg-cream"
                    style={sketchyShape2}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <ChevronDown
                        size={16}
                        strokeWidth={3}
                        className={`shrink-0 transition-transform ${open ? '' : '-rotate-90'}`}
                      />
                      <span className="w-3 h-3 shrink-0 border-2 border-ink inline-block" style={{ background: hook.color }} />
                      <span className="font-black text-ink text-[15px] truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                        {hook.label}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="text-xs font-bold text-ink/50">{actions.length}</span>
                      <button
                        title={`为「${hook.label}」添加动作`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuFor((cur) => (cur === hook.key ? null : hook.key));
                        }}
                        className="w-7 h-7 flex items-center justify-center bg-cream border-2 border-ink text-ink hover:bg-sand transition-colors"
                        style={sketchyShape2}
                      >
                        <Plus size={15} strokeWidth={3} />
                      </button>
                    </div>
                  </div>

                  {/* 添加动作下拉 */}
                  {menuFor === hook.key && (
                    <div
                      style={sketchyShape1}
                      className="absolute top-full right-2 left-2 z-40 bg-paper border-2 border-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] mt-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {ACTION_TYPES.map((at) => (
                        <button
                          key={at.key}
                          onClick={() => handleAddAction(hook.key, at.key)}
                          className="w-full text-left px-3 py-2 hover:bg-cream flex flex-col gap-0.5 group"
                        >
                          <span className="font-black text-ink text-sm leading-tight" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                            {at.label}
                          </span>
                          <span className="text-xs font-bold text-ink/40 leading-tight">{at.desc}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* action 列表 */}
                  {open && (
                    <ul className="divide-y-2 divide-ink/10">
                      {actions.length === 0 && (
                        <li className="px-3 py-3 text-center text-sm font-bold text-ink/40 border-2 border-dashed border-ink/30 m-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                          暂无动作，点击上方 + 添加
                        </li>
                      )}
                      {actions.map((action) => {
                        const expanded = openActions.has(action.id);
                        return (
                          <li key={action.id}>
                            <div
                              onClick={() => toggleAction(action.id)}
                              className="flex items-center justify-between gap-2 px-3 py-2 cursor-pointer group hover:bg-cream"
                            >
                              <div className="min-w-0 flex items-center gap-1.5">
                                <ChevronDown
                                  size={13}
                                  strokeWidth={3}
                                  className={`shrink-0 text-ink/40 transition-transform ${expanded ? '' : '-rotate-90'}`}
                                />
                                <div className="min-w-0">
                                  <div className="font-black text-ink text-[15px] leading-tight truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                                    {action.label}
                                  </div>
                                  <div className="text-[11px] font-bold text-ink/40 leading-tight truncate">
                                    {action.type}
                                    {Object.keys(action.config).length > 0 && ` · ${Object.keys(action.config).join(', ')}`}
                                  </div>
                                </div>
                              </div>
                              <button
                                title="删除动作"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRemoveAction(hook.key, action.id);
                                }}
                                className="w-7 h-7 shrink-0 flex items-center justify-center text-ink/40 hover:text-paper hover:bg-[#bf616a] border-2 border-transparent hover:border-ink transition-colors"
                                style={sketchyShape2}
                              >
                                <Trash2 size={14} strokeWidth={2.5} />
                              </button>
                            </div>
                            {expanded && (
                              <ConfigEditor
                                action={action}
                                schema={FIELD_SCHEMA[action.type] ?? []}
                                allowTiming={hook.key === 'on_loop_epoch'}
                                allowExpect={hook.key === 'on_loop_end'}
                                onField={(key, val) => commitField(hook.key, action.id, key, val)}
                                onReplace={(cfg) => replaceConfig(hook.key, action.id, cfg)}
                              />
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ===== 右侧：实时流转图 ===== */}
      <div
        style={sketchyShape2}
        className="flex-1 min-w-0 h-full bg-paper border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] relative overflow-hidden flex flex-col rotate-[0.5deg]"
      >
        <div
          className="absolute -top-6 left-20 w-40 h-10 bg-[#EBCB8B]/80 border-4 border-ink -rotate-2 z-50 pointer-events-none"
          style={sketchyShape1}
        ></div>
        <div className="flex-1 min-h-0 w-full relative">
          <style dangerouslySetInnerHTML={{ __html: HIDE_HANDLE_CSS }} />
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            className="bg-cream"
          >
            <Background color="#D47A5A" gap={24} size={1} variant={'dots' as any} />
            <Controls className="!bg-paper !border-2 !border-ink shadow-soft rounded-xl overflow-hidden" />
          </ReactFlow>
        </div>
      </div>

      {/* 新建 Paradigm 弹窗（由顶部 Toolbar 触发） */}
      {creating && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-sm p-6 relative rotate-1">
            <h3 className="text-2xl font-black mb-1 tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              新建 Paradigm
            </h3>
            <p className="font-bold mb-3 text-sm opacity-60" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              将创建 {`~/.purrcat/paradigms/{名称}.yaml`}，初始只有空的五个 Hook
            </p>
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleCreate();
              }}
              style={sketchyShape2}
              className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold mb-4 focus:outline-none"
              placeholder="例如 my_agent_loop"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setCreating(false)}
                style={sketchyShape1}
                className="flex-1 py-2.5 bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all"
              >
                取消
              </button>
              <button
                onClick={() => void handleCreate()}
                disabled={saving}
                style={sketchyShape2}
                className="flex-1 py-2.5 bg-ink text-paper border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] hover:bg-gray-800 transition-all disabled:opacity-40"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export default AgentLoopEditor;
