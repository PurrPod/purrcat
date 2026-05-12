import { create } from 'zustand'
import { persist } from 'zustand/middleware' // 引入持久化插件
import {
  Node, Edge, Connection, addEdge, applyNodeChanges, applyEdgeChanges,
  NodeChange, EdgeChange, getOutgoers,
} from '@xyflow/react'
import { v4 as uuidv4 } from 'uuid'
import { CatalogItem, GraphExport } from '../types'

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
          id: uuidv4(),
          type: type === 'task_input' ? 'task_input' : type === 'task_output' ? 'task_output' : 'custom',
          position,
          data: {
            nodeType: type,
            name: definition.name,
            color: definition.color,
            inputs: definition.inputs,
            outputs: definition.outputs,
            configSchema: definition.config || [],
            dynamic_inputs: [],
            ...definition.config?.reduce((acc, f) => ({ ...acc, [f.name]: f.default }), {}),
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
        if (hasCycle(targetNode, params.source!, nodes, edges)) return false

        // 2. 类型校验（核心对齐逻辑）
        const sourcePort = [...(sourceNode.data.outputs || [])].find(p => p.name === params.sourceHandle || (params.sourceHandle === 'default' && sourceNode.data.outputs?.length === 1))
        const targetPort = [...(targetNode.data.inputs || [])].find(p => p.name === params.targetHandle || (params.targetHandle === 'default' && targetNode.data.inputs?.length === 1))
        
        // 如果定义了类型且类型不匹配（简单字符串比较），且不是 any 类型
        if (sourcePort && targetPort && sourcePort.type !== 'any' && targetPort.type !== 'any' && sourcePort.type !== targetPort.type) {
            return false 
        }

        const newEdge: Edge = { ...params, id: uuidv4(), animated: true }
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

      exportGraph: (name) => {
        const { nodes, edges } = get()
        return {
          name,
          description: "PurrCat Web Export",
          required_inputs: {}, // 逻辑同前
          nodes: nodes.map(n => ({ id: n.id, type: n.data.nodeType, data: n.data })),
          edges: edges.map(e => ({ source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle }))
        }
      },

      clearGraph: () => set({ nodes: [], edges: [], selectedNodeId: null }),

      loadGraph: (data) => { /* 逻辑同前，通过 fetchCatalog 确保 catalog 存在后再 load */ }
    }),
    { name: 'purrcat-flow-cache' } // localStorage 键名
  )
)