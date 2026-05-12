import { memo } from 'react';
import { Handle, Position } from '@xyflow/react'
import { useFlowStore } from '../store/flowStore'

interface TaskInputNodeProps {
  id: string
  data: {
    dynamic_inputs?: Array<{ key: string; desc: string }>
  }
}

const TaskInputNode = memo(function TaskInputNode({ id, data }: TaskInputNodeProps) {
  const updateNodeData = useFlowStore((state) => state.updateNodeData)
  const inputs = data.dynamic_inputs || []

  const addInput = () => {
    const key = prompt("请输入变量名 (如 prompt):")
    const desc = prompt("请输入变量描述:")
    if (key && desc) {
      updateNodeData(id, { dynamic_inputs: [...inputs, { key, desc }] })
    }
  }

  const removeInput = (keyToRemove: string) => {
    updateNodeData(id, { dynamic_inputs: inputs.filter(i => i.key !== keyToRemove) })
  }

  return (
    <div className="bg-ink text-paper rounded-2xl p-5 min-w-[240px] shadow-soft relative">
      <div className="flex items-center gap-2 mb-4 border-b border-white/20 pb-3">
        <span className="text-xl">📥</span>
        <h3 className="font-serif font-bold text-lg">全局输入 (Start)</h3>
      </div>
      
      <div className="space-y-3">
        {inputs.map((input) => (
          <div key={input.key} className="bg-white/10 rounded-lg p-2 text-sm relative">
            <div className="flex items-center justify-between">
              <div className="font-bold text-terracotta">{input.key}</div>
              <button
                onClick={() => removeInput(input.key)}
                className="text-red-400 hover:text-red-300 text-xs font-bold px-2"
              >
                ×
              </button>
            </div>
            <div className="text-paper/70 text-xs mt-1">{input.desc}</div>
            <Handle 
              type="source" 
              position={Position.Right} 
              id={input.key} 
              className="!bg-terracotta !border-ink !w-4 !h-4 right-[-26px]"
            />
          </div>
        ))}
      </div>
      
      <button 
        className="mt-4 w-full py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm font-bold text-terracotta transition-colors border border-white/10"
        onClick={addInput}
      >
        + 添加必填参数
      </button>
    </div>
  );
});

export default TaskInputNode;
