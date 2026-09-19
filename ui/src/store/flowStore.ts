import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  Node, Edge, Connection, addEdge, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, getOutgoers,
} from '@xyflow/react'
import { CatalogItem, GraphExport } from '../types'
import { toast } from 'react-hot-toast'

const generateShortId = (prefix: string) => `${prefix}_${Math.random().toString(36).substring(2, 8)}`

interface FlowState {
  nodes: Node[];
  edges: Edge[];
  catalog: CatalogItem[];
  selectedNodeId: string | null;

  fetchCatalog: () => Promise<void>;
  addNode: (type: string, position: { x: number; y: number }) => void;
  removeNode: (nodeId: string) => void;
  removeEdge: (edgeId: string) => void; // 新增：删除连线
  updateNodeData: (nodeId: string, data: Record<string, any>) => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => boolean;
  setSelectedNodeId: (id: string | null) => void;

  validateGraph: () => string[];
  exportGraph: (name: string, description?: string) => GraphExport;
  clearGraph: () => void;
  loadGraph: (graphData: any) => void;
  // 🌟 加载的原 graph 顶层附加键（env / dashboard 等），导出时原样保留
  // dashboard 支持单字符串 URL，或 [{name,url}] 多看板
  graphExtras: { env?: any; dashboard?: string | { name: string; url: string }[] } | null;
}

// 辅助：检查环路
const hasCycle = (node: Node, targetNodeId: string, nodes: Node[], edges: Edge[]): boolean => {
  const outgoers = getOutgoers(node, nodes, edges)
  if (outgoers.some((outgoer) => outgoer.id === targetNodeId)) return true
  return outgoers.some((outgoer) => hasCycle(outgoer, targetNodeId, nodes, edges))
}

// 🌟 坐标推理：无坐标 graph 的拓扑分层自动布局
// 规则：列距/行距均大于卡片尺寸；后继节点的 X 严格大于其全部前继节点（数据从左向右流）
// 分层策略（拉紧布局）：
//   1) 先按最长路径分层（拓扑安全的起点）
//   2) 从右往左迭代上拉：节点优先紧贴其最浅后继的前一层（如 Skill 消息卡贴在消息合并 1 前一层），
//      贴不到时保持原位（受前驱约束）；每次拉动都校验不越过任何前驱/后继，拓扑永远合法
export const inferAutoLayout = (
  nodes: Array<{ id: string }>,
  edges: Array<{ source: string; target: string }>
): Record<string, { x: number; y: number }> => {
  const depth: Record<string, number> = {}
  nodes.forEach(n => { depth[n.id] = 0 })
  // 1) 迭代松弛求最长路径深度（拓扑层）；轮数上限防御异常环
  for (let round = 0; round <= nodes.length; round++) {
    let changed = false
    edges.forEach(e => {
      const d = (depth[e.source] ?? 0) + 1
      if ((depth[e.target] ?? 0) < d) { depth[e.target] = d; changed = true }
    })
    if (!changed) break
  }
  // 2) 拉紧：从深层往浅层迭代，尽量贴住最浅后继的前一层（层号只增，单调收敛）
  const succsOf: Record<string, string[]> = {}
  const predsOf: Record<string, string[]> = {}
  edges.forEach(e => {
    ;(succsOf[e.source] ||= []).push(e.target)
    ;(predsOf[e.target] ||= []).push(e.source)
  })
  for (let round = 0; round <= nodes.length; round++) {
    let changed = false
    const order = [...nodes].sort((a, b) => (depth[b.id] ?? 0) - (depth[a.id] ?? 0))
    order.forEach(n => {
      const succs = succsOf[n.id] || []
      if (succs.length === 0) return
      const minSucc = Math.min(...succs.map(s => depth[s] ?? 0))
      const preds = predsOf[n.id] || []
      const lower = preds.length ? Math.max(...preds.map(p => (depth[p] ?? 0) + 1)) : 0
      const target = Math.max(minSucc - 1, lower)
      // 仅当能严格贴到后继前一层（target < minSucc）且比当前更靠右时才拉动
      if (target > (depth[n.id] ?? 0) && target < minSucc) {
        depth[n.id] = target; changed = true
      }
    })
    if (!changed) break
  }
  const COL = 480, ROW = 480, PAD = 100 // 间距均大于卡片宽高（最大卡约 280 宽 / 450 高）
  const buckets: Record<number, string[]> = {}
  nodes.forEach(n => {
    const d = Math.min(depth[n.id] ?? 0, Math.max(nodes.length - 1, 0))
    ;(buckets[d] ||= []).push(n.id)
  })
  const pos: Record<string, { x: number; y: number }> = {}
  Object.keys(buckets).forEach(d => {
    buckets[+d].forEach((id, i) => { pos[id] = { x: PAD + +d * COL, y: PAD + i * ROW } })
  })
  return pos
}

export const useFlowStore = create<FlowState>()(
  persist(
    (set, get) => ({
      nodes: [],
      edges: [],
      catalog: [],
      selectedNodeId: null,
      graphExtras: null,

      fetchCatalog: async () => {
        const res = await fetch('/api/graphs/nodes')
        if (res.ok) set({ catalog: await res.json() })
      },

      addNode: (type, position) => {
        const definition = get().catalog.find((item) => item.type === type)
        if (!definition) return
        const newNode: Node = {
          id: generateShortId('nd'),
          type: 'custom', // 🔴 修复：强制交给 React Flow 的 custom 组件渲染
          position,
          data: {
            nodeType: type, // 🌟 真正的业务类型存在这里，供导出时使用
            name: definition.name,
            color: definition.color,
            inputs: definition.inputs,
            outputs: definition.outputs,
            configSchema: definition.config || [],
            // 🌟 初始化 Config 默认值，遇到 list 给个空数组
            ...definition.config?.reduce((acc, f) => ({ 
              ...acc, 
              [f.name]: (f.type as string) === 'list' ? (f.default || []) : f.default 
            }), {}),
          },
        }
        set((state) => ({ nodes: [...state.nodes, newNode] }))
      },

      removeNode: (nodeId) => set((state) => ({
        nodes: state.nodes.filter((n) => n.id !== nodeId),
        edges: state.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      })),

      removeEdge: (edgeId) => set((state) => ({
        edges: state.edges.filter((e) => e.id !== edgeId),
      })),

      updateNodeData: (nodeId, data) => set((state) => ({
        nodes: state.nodes.map((n) => n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n),
      })),

      onNodesChange: (changes) => set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) })),
      onEdgesChange: (changes) => set((state) => ({ edges: applyEdgeChanges(changes, state.edges) })),

      onConnect: (params) => {
        const { nodes, edges } = get()
        const sourceNode = nodes.find(n => n.id === params.source)
        const targetNode = nodes.find(n => n.id === params.target)
        if (!sourceNode || !targetNode) return false

        // 1. 环路校验
        if (hasCycle(targetNode, params.source!, nodes, edges)) {
          toast.error('禁止形成循环连线！');
          return false;
        }

        // 🌟 2. 动态引脚类型推导雷达
        const getPortType = (node: Node, handleId: string, direction: 'source' | 'target') => {
            const ports = direction === 'source' ? (node.data.outputs as any[]) : (node.data.inputs as any[]);
            if (!ports) return 'any';

            // A. 先找有没有固定引脚 (Static Port)
            const staticPort = ports.find(p => p.name === handleId && p.port_type !== 'dynamic');
            if (staticPort) return staticPort.type || 'any';

            // B. 找不到的话，去动态规则里挖 (Dynamic Port)
            const dynamicPortDef = ports.find(p => p.port_type === 'dynamic');
            if (dynamicPortDef) {
               const configFieldName = dynamicPortDef.dynamic_rules?.watch_config;
               if (configFieldName) {
                   const configValue = node.data[configFieldName];
                   if (Array.isArray(configValue)) {
                       // 遍历 list 找到对应的对象，拔出它的 type
                       const item = configValue.find(v => (typeof v === 'object' ? (v.name || v.key) : v) === handleId);
                       if (item && typeof item === 'object' && item.type) {
                           return item.type;
                       }
                   }
               }
            }
            return 'any';
        }

        // 🌟 3. 基础类型归一化字典 (类型向下兼容)
        const normalizeType = (t: string) => {
            if (!t) return 'any';
            // 在这里定义你的类型宽容映射！
            const typeMap: Record<string, string> = {
                'MessageList': 'list',
                'ToolList': 'list',
                'integer': 'number',
                'float': 'number',
                'LLMResponse': 'object',
                'filepath': 'file',
                'File': 'file'
            };
            return typeMap[t] || t.toLowerCase();
        }

        // 端口声明归一化为类型集合：支持 union 数组声明（如 ["string","file"]）
        const toTypeSet = (raw: any): string[] => {
            const list = Array.isArray(raw) ? raw : [raw]
            return list.map((t: any) => normalizeType(String(t)))
        }
        const fmtType = (raw: any) => Array.isArray(raw) ? raw.join(' | ') : String(raw)

        // 查出原始类型（union 端口返回数组）
        const rawSourceType = getPortType(sourceNode, params.sourceHandle || 'default', 'source');
        const rawTargetType = getPortType(targetNode, params.targetHandle || 'default', 'target');

        // 🌟 4. 智能类型校验：any 万能；类型集合兼容即可连线（与引擎 envelope.check 规则一致）
        // 双向软兼容对（子类型）：jsonstring 是 string 的子类型，MessageList 经 normalizeType 已归一为 list
        const SOFT_PAIRS: [string, string][] = [['jsonstring', 'string']];
        const isCompatible = (s: string, t: string) =>
            s === t || SOFT_PAIRS.some(([a, b]) => (s === a && t === b) || (s === b && t === a));
        const sSet = toTypeSet(rawSourceType);
        const tSet = toTypeSet(rawTargetType);
        if (!sSet.includes('any') && !tSet.includes('any') && !sSet.some(s => tSet.some(t => isCompatible(s, t)))) {
            toast.error(`类型不兼容！无法将 [${fmtType(rawSourceType)}] 连到 [${fmtType(rawTargetType)}] 上`);
            return false;
        }

        // 校验通过，建立连线！(自动替换目标引脚上旧的线)
        const newEdge: Edge = { ...params, id: generateShortId('edge'), animated: true }
        set({ edges: addEdge(newEdge, edges.filter(e => !(e.target === params.target && e.targetHandle === params.targetHandle))) })
        return true
      },

      setSelectedNodeId: (id) => set({ selectedNodeId: id }),

      validateGraph: () => {
        const { nodes, edges } = get()
        const errors: string[] = []
        // 全局输入/输出节点是可选的：无外部参数/无对外产出的工作流不需要它们

        // 检查孤立节点（没有连线的节点，除了输入输出外建议校验）
        nodes.forEach(node => {
          const hasConnection = edges.some(e => e.source === node.id || e.target === node.id)
          if (!hasConnection) errors.push(`节点 [${node.data.name}] 尚未连接任何路径`)
        })

        return errors
      },

      exportGraph: (name: string, description?: string): GraphExport => {
        const { nodes, edges } = get()
        const taskInputNode = nodes.find(n => n.data.nodeType === 'task_input')
        
        const globalSchema: Record<string, any> = {}
        
        // 解析全局变量
        if (taskInputNode && Array.isArray(taskInputNode.data.global_vars)) {
          taskInputNode.data.global_vars.forEach((item: any) => {
            const varName = typeof item === 'object' ? (item.name || item.key) : item;
            const varType = typeof item === 'object' ? (item.type || 'any') : 'any';
            if (varName) {
              globalSchema[varName] = {
                type: varType,
                required: typeof item === 'object' && item.required !== undefined ? item.required : true,
                description: typeof item === 'object' && item.description ? item.description : `动态注入全局参数: ${varName}`
              }
            }
          })
        }

        // 🌟 核心修复：部署时建立全局 ID 映射表，彻底杜绝同名节点污染！
        const idMap: Record<string, string> = {};
        nodes.forEach(n => {
          // 为每个节点生成绝对唯一的 8 位哈希 ID，格式如：agent_loop_a1b2c3
          idMap[n.id] = `${n.data.nodeType}_${Math.random().toString(36).substring(2, 8)}`;
        });

        // 🌟 保留原 graph 的顶层附加键（env / dashboard），避免编辑器保存时丢失
        const extras = get().graphExtras;
        return {
          version: "2.0",
          name,
          description: description || "PurrCat Web Export - V2",
          global_schema: globalSchema,
          ...(extras?.env ? { env: extras.env } : {}),
          ...(extras?.dashboard ? { dashboard: extras.dashboard } : {}),
          nodes: nodes.map(n => {
            const { nodeType, ...finalConfig } = n.data;

            if (nodeType === 'task_output' && Array.isArray(finalConfig.target_vars)) {
              finalConfig.exposed_keys = finalConfig.target_vars.map((v:any) => typeof v === 'object' ? (v.name || v.key) : v);
            }

            return {
              id: idMap[n.id], // 🚀 使用安全的 Unique ID 替换旧 ID
              type: n.data.nodeType,
              name: n.data.name,
              position: [Math.round(n.position.x), Math.round(n.position.y)],
              config: finalConfig 
            }
          }),
          edges: edges.map(e => ({
            source: idMap[e.source] || e.source, // 🚀 同步重定向连线的起点
            target: idMap[e.target] || e.target, // 🚀 同步重定向连线的终点
            sourceHandle: e.sourceHandle || 'default', 
            targetHandle: e.targetHandle || 'default'
          }))
        } as any;
      },

      clearGraph: () => set({ nodes: [], edges: [], selectedNodeId: null, graphExtras: null }),

      loadGraph: async (graphData: any) => {
        if (get().catalog.length === 0) await get().fetchCatalog();
        const catalog = get().catalog;
        
        const nodes = graphData.nodes || [];
        const edges = graphData.edges || [];

        // 🌟 无坐标节点的拓扑分层自动布局（后继 X 严格大于全部前继）
        const autoPos = inferAutoLayout(nodes, edges);

        const loadedNodes: Node[] = nodes.map((node: any) => {
          const definition = catalog.find((item) => item.type === node.type);
          if (!definition) return null;

          let posX: number, posY: number;
          if (Array.isArray(node.position)) {
            posX = node.position[0]; posY = node.position[1];
          } else if (node.position?.x !== undefined) {
            posX = node.position.x; posY = node.position.y;
          } else {
            const p = autoPos[node.id] || { x: 100, y: 100 };
            posX = p.x; posY = p.y;
          }

          const sourceData = node.config || node.data || {};
          let dynamicInputs = [];
          if (sourceData.exposed_keys) {
            dynamicInputs = sourceData.exposed_keys.map((k: string) => ({ key: k, desc: 'any' }));
          } else if (node.data?.dynamic_inputs) {
            dynamicInputs = node.data.dynamic_inputs;
          }

          const defaultData: Record<string, any> = {
            nodeType: node.type,
            name: node.name || definition.name,
            color: definition.color,
            inputs: definition.inputs,
            outputs: definition.outputs,
            configSchema: definition.config || [],
            dynamic_inputs: dynamicInputs,
          };

          Object.keys(sourceData).forEach((key) => {
            // 端口/配置 schema 一律以节点定义为准：历史图文件里内嵌的
            // inputs/outputs/configSchema/color 是过时的序列化结果，不得覆盖定义
            if (!['exposed_keys', 'inputs', 'outputs', 'configSchema', 'color'].includes(key)) {
              defaultData[key] = sourceData[key];
            }
          });

          return {
            id: node.id,
            type: 'custom', // 🔴 修复：加载历史图谱时，也统一交给 custom 组件
            position: { x: posX, y: posY },
            data: defaultData,
          };
        }).filter(Boolean) as Node[];

        const loadedEdges: Edge[] = edges.map((edge: any) => ({
          id: `edge-${edge.source}-${edge.target}-${edge.sourceHandle}`,
          source: edge.source, target: edge.target,
          sourceHandle: edge.sourceHandle || 'default', targetHandle: edge.targetHandle || 'default',
          animated: true,
        }));

        set({ nodes: loadedNodes, edges: loadedEdges, selectedNodeId: null, graphExtras: { env: graphData.env, dashboard: graphData.dashboard } });
      }
    }),
    { name: 'purrcat-flow-cache' } // localStorage 键名
  )
)