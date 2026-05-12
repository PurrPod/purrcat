import { memo, useState } from 'react';
import { Handle, Position } from '@xyflow/react'
import { useFlowStore } from '../store/flowStore'

interface TaskOutputNodeProps {
  id: string
  data: {
    dynamic_keys?: string[]
  }
}

const TaskOutputNode = memo(function TaskOutputNode({ id, data }: TaskOutputNodeProps) {
  const updateNodeData = useFlowStore((state) => state.updateNodeData)
  const [inputValue, setInputValue] = useState('')
  const [showInput, setShowInput] = useState(false)

  const dynamicKeys = data.dynamic_keys || []

  const handleAddKey = () => {
    if (inputValue.trim()) {
      const newKeys = [...dynamicKeys, inputValue.trim()]
      updateNodeData(id, { dynamic_keys: newKeys })
      setInputValue('')
      setShowInput(false)
    }
  }

  const handleRemoveKey = (key: string) => {
    const newKeys = dynamicKeys.filter((k) => k !== key)
    updateNodeData(id, { dynamic_keys: newKeys })
  }

  return (
    <div className="bg-[#FFFFFF] border-2 border-[#1A1A1A] rounded-2xl p-4 shadow-sm min-w-[200px]">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 bg-[#6B8E6B] rounded-full flex items-center justify-center">
          <span className="text-white text-sm font-bold">O</span>
        </div>
        <h3 className="font-serif text-lg font-bold text-[#1A1A1A]">全局输出</h3>
      </div>

      <div className="space-y-2">
        {dynamicKeys.map((key) => (
          <div key={key} className="flex items-center justify-between bg-[#FAF8F5] rounded-lg px-3 py-2">
            <span className="text-sm font-sans text-[#1A1A1A]">{key}</span>
            <button
              onClick={() => handleRemoveKey(key)}
              className="text-red-500 hover:text-red-700 text-xs font-bold px-2 py-1"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {showInput ? (
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddKey()}
            placeholder="输入变量名"
            className="flex-1 px-3 py-2 border-2 border-[#1A1A1A] rounded-lg text-sm font-sans focus:outline-none focus:border-[#6B8E6B]"
            autoFocus
          />
          <button
            onClick={handleAddKey}
            className="px-3 py-2 bg-[#1A1A1A] text-white rounded-lg text-sm font-bold hover:bg-[#333]"
          >
            添加
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowInput(true)}
          className="mt-3 w-full py-2 border-2 border-dashed border-[#6B8E6B] rounded-lg text-[#6B8E6B] text-sm font-bold hover:bg-[#FAF8F5] transition-colors"
        >
          + 添加输出声明
        </button>
      )}

      <div className="mt-4 space-y-2">
        {dynamicKeys.map((key) => (
          <div key={key} className="flex items-center justify-start">
            <Handle
              type="target"
              position={Position.Left}
              id={key}
              className="w-3 h-3 bg-[#1A1A1A] border-2 border-white"
            />
            <span className="text-xs font-sans ml-2 bg-[#6B8E6B] text-white px-2 py-1 rounded-full">
              {key}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
});

export default TaskOutputNode;
