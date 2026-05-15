import { useCallback, useRef } from 'react';
import { ReactFlow, Background, Controls, useReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useFlowStore } from '../store/flowStore';
import CustomNode from './CustomNode';
import TaskInputNode from './TaskInputNode';
import TaskOutputNode from './TaskOutputNode';
import CustomEdge from './CustomEdge'; // 引入自定义连线

const nodeTypes = {
  custom: CustomNode,
  task_input: TaskInputNode,
  task_output: TaskOutputNode,
};

// 注册自定义连线
const edgeTypes = {
  custom: CustomEdge,
};

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
        edgeTypes={edgeTypes} // 挂载连线类型
        defaultEdgeOptions={{ type: 'custom' }} // 所有新连线默认走 custom
        fitView
        className="bg-cream"
      >
        <Background color="#D47A5A" gap={20} size={1} variant={'dots' as any} />
        <Controls className="!bg-paper !border-2 !border-ink !shadow-soft rounded-xl overflow-hidden" />
      </ReactFlow>
    </div>
  );
}