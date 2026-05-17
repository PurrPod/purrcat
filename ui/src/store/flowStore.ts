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
  exportGraph: (name: string) => GraphExport;
  clearGraph: () => void;
  loadGraph: (graphData: any) => void;
}

// 辅助：检查环路
const hasCycle = (node: Node, targetNodeId: string, nodes: Node[], edges: Edge[]): boolean => {
  const outgoers = getOutgoers(node, nodes, edges)
  if (outgoers.some((outgoer) => outgoer.id === targetNodeId)) return true
  return outgoers.some((outgoer) => hasCycle(outgoer, targetNodeId, nodes, edges))
}

export const useFlowStore = create<FlowState>()(
  persist(
    (set, get) => ({
      nodes: [],
      edges: [],
      catalog: [],
      selectedNodeId: null,

      fetchCatalog: async () => {
        const res = await fetch('http://localhost:8000/api/graphs/nodes')
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
              [f.name]: f.type === 'list' ? (f.default || []) : f.default 
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
                'LLMResponse': 'object'
            };
            return typeMap[t] || t.toLowerCase();
        }

        // 查出原始类型
        const rawSourceType = getPortType(sourceNode, params.sourceHandle || 'default', 'source');
        const rawTargetType = getPortType(targetNode, params.targetHandle || 'default', 'target');
        
        // 归一化对比
        const sType = normalizeType(rawSourceType);
        const tType = normalizeType(rawTargetType);

        // 🌟 4. 智能类型校验
        if (sType !== 'any' && tType !== 'any' && sType !== tType) {
            toast.error(`类型不兼容！无法将 [${rawSourceType}] 连到 [${rawTargetType}] 上`);
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
        // 检查输入输出节点
        if (!nodes.find(n => n.data.nodeType === 'task_input')) errors.push("缺失 [全局输入] 节点")
        if (!nodes.find(n => n.data.nodeType === 'task_output')) errors.push("缺失 [全局输出] 节点")

        // 检查孤立节点（没有连线的节点，除了输入输出外建议校验）
        nodes.forEach(node => {
            const hasConnection = edges.some(e => e.source === node.id || e.target === node.id)
            if (!hasConnection) errors.push(`节点 [${node.data.name}] 尚未连接任何路径`)
        })

        return errors
      },

      exportGraph: (name: string): GraphExport => {
        const { nodes, edges } = get()
        const taskInputNode = nodes.find(n => n.data.nodeType === 'task_input')
        
        const globalSchema: Record<string, any> = {}
        
        // 🌟 核心：兼容对象数组的读取
        if (taskInputNode && Array.isArray(taskInputNode.data.global_vars)) {
          taskInputNode.data.global_vars.forEach((item: any) => {
            // 取名：如果是对象，拿 name 属性；如果是老数据的字符串，直接拿
            const varName = typeof item === 'object' ? (item.name || item.key) : item;
            const varType = typeof item === 'object' ? item.type : 'any';
            
            if (varName) {
              globalSchema[varName] = {
                type: varType,
                required: true,
                description: `动态注入全局参数: ${varName}`
              }
            }
          })
        }

        return {
          version: "2.0",
          name,
          description: "PurrCat Web Export - V2",
          global_schema: globalSchema,
          nodes: nodes.map(n => {
            const { nodeType, name, color, inputs, outputs, configSchema, ...finalConfig } = n.data;

            // 🌟 导出 task_output 节点时，把数组对象清洗为纯字符串数组放入 exposed_keys 中
            if (nodeType === 'task_output' && Array.isArray(finalConfig.target_vars)) {
              finalConfig.exposed_keys = finalConfig.target_vars.map((v:any) => typeof v === 'object' ? (v.name || v.key) : v);
            }

            return {
              id: n.id,
              type: n.data.nodeType,
              name: n.data.name,
              position: [Math.round(n.position.x), Math.round(n.position.y)],
              config: finalConfig 
            }
          }),
          edges: edges.map(e => ({
            source: e.source, 
            target: e.target, 
            sourceHandle: e.sourceHandle || 'default', 
            targetHandle: e.targetHandle || 'default'
          }))
        } as any;
      },

      clearGraph: () => set({ nodes: [], edges: [], selectedNodeId: null }),

      loadGraph: async (graphData: any) => {
        if (get().catalog.length === 0) await get().fetchCatalog();
        const catalog = get().catalog;
        
        const nodes = graphData.nodes || [];
        const edges = graphData.edges || [];
        
        const loadedNodes: Node[] = nodes.map((node: any, index: number) => {
          const definition = catalog.find((item) => item.type === node.type);
          if (!definition) return null;

          let posX = 100 + (index % 3) * 300, posY = 100 + Math.floor(index / 3) * 150;
          if (Array.isArray(node.position)) {
            posX = node.position[0]; posY = node.position[1];
          } else if (node.position?.x !== undefined) {
            posX = node.position.x; posY = node.position.y;
          }

          const sourceData = node.config || node.data || {};
          let dynamicInputs = [];
          if (sourceData.exposed_keys) {
            dynamicInputs = sourceData.exposed_keys.map((k: string) => ({ key: k, desc: 'any' }));
          } else if (node.data?.dynamic_inputs) {
            dynamicInputs = node.data.dynamic_inputs;
          } else if (node.type === 'task_input' && graphData.required_inputs) {
             Object.keys(graphData.required_inputs).forEach(k => dynamicInputs.push({ key: k, desc: graphData.required_inputs[k] }));
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
            if (!['exposed_keys'].includes(key)) defaultData[key] = sourceData[key];
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

        set({ nodes: loadedNodes, edges: loadedEdges, selectedNodeId: null });
      }
    }),
    { name: 'purrcat-flow-cache' } // localStorage 键名
  )
)