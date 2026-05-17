import { useCallback, useRef } from 'react';
import { ReactFlow, Background, Controls, useReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useFlowStore } from '../store/flowStore';
import CustomNode from './CustomNode';     // 🌟 只需要这一个
import CustomEdge from './CustomEdge';

// 🌟 极简！现在整个前端真的只需要注册这一个组件了
const nodeTypes = {
  custom: CustomNode,
};

const edgeTypes = { custom: CustomEdge };

export default function FlowCanvas() {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode } = useFlowStore();
  const { screenToFlowPosition } = useReactFlow();

  const onDragOver = useCallback((event: any) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: any) => {
      event.preventDefault();
      const nodeDataStr = event.dataTransfer.getData('application/reactflow');
      if (!nodeDataStr) return;
      const nodeData = JSON.parse(nodeDataStr);
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      addNode(nodeData.type, position);
    },
    [screenToFlowPosition, addNode]
  );

  return (
    <div className="flex-1 h-full relative" ref={reactFlowWrapper}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={{ type: 'custom' }}
        fitView
        className="bg-cream"
      >
        <Background color="#D47A5A" gap={20} size={1} variant={'dots' as any} />
        <Controls className="!bg-paper !border-2 !border-ink !shadow-soft rounded-xl overflow-hidden" />
      </ReactFlow>
    </div>
  );
}