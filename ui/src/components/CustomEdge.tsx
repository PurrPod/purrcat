import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
import { X } from 'lucide-react';
import { useFlowStore } from '../store/flowStore';

export default function CustomEdge({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, selected
}: any) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition,
  });
  const removeEdge = useFlowStore((state) => state.removeEdge);

  return (
    <>
      <BaseEdge 
        path={edgePath} 
        markerEnd={markerEnd} 
        style={{ ...style, strokeWidth: selected ? 4 : 2, stroke: selected ? '#D47A5A' : '#1a1a1a' }} 
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          {/* 连线中间的小红叉删除按钮 */}
          <button 
            onClick={() => removeEdge(id)} 
            className="w-6 h-6 bg-paper border-2 border-ink rounded-full flex items-center justify-center text-ink hover:bg-[#bf616a] hover:text-paper shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] transition-colors hover:scale-110 active:scale-95"
            title="删除连线"
          >
            <X size={14} strokeWidth={3} />
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}