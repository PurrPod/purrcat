import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Handle, Position, useUpdateNodeInternals } from '@xyflow/react';
import { useFlowStore } from '../store/flowStore';
import { Trash2, Plus, X, Variable } from 'lucide-react';
import { toast } from 'react-hot-toast';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

export default function TaskOutputNode({ id, data, selected }: any) {
  const updateNodeData = useFlowStore((state) => state.updateNodeData);
  const removeNode = useFlowStore((state) => state.removeNode);
  const updateNodeInternals = useUpdateNodeInternals();

  const [showModal, setShowModal] = useState(false);
  const [newVar, setNewVar] = useState('');

  // 强制刷新 Handle 位置
  useEffect(() => {
    updateNodeInternals(id);
  }, [data.dynamic_inputs, id, updateNodeInternals]);

  const handleAdd = () => {
    const key = newVar.trim();
    if (!key) return;
    
    const current = data.dynamic_inputs || [];
    if (current.find((item: any) => item.key === key)) {
      toast.error('变量名已存在！');
      return;
    }

    updateNodeData(id, { dynamic_inputs: [...current, { key, desc: 'any' }] });
    setNewVar('');
    setShowModal(false);
  };

  const handleRemoveVar = (keyToRemove: string) => {
    const current = data.dynamic_inputs || [];
    updateNodeData(id, { dynamic_inputs: current.filter((item: any) => item.key !== keyToRemove) });
  };

  return (
    <div 
      className={`bg-paper border-4 border-ink p-5 min-w-[260px] relative group transition-shadow duration-200 
        ${selected ? 'shadow-[8px_8px_0px_0px_rgba(212,122,90,1)]' : 'shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}
      style={sketchyShape3}
    >
      <button 
        onClick={(e) => { e.stopPropagation(); removeNode(id); }}
        className="absolute -top-4 -right-4 w-8 h-8 bg-[#bf616a] border-2 border-ink flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] z-50 cursor-pointer"
        style={{ borderRadius: '50% 10% 50% 10%' }}
        title="Delete Node"
      >
        <Trash2 size={16} className="text-paper" />
      </button>

      <div className="flex items-center gap-3 mb-2 border-b-2 border-ink/15 pb-3">
        <div className="w-5 h-5 bg-[#EBCB8B] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] rotate-6 shrink-0" style={sketchyShape2}></div>
        <div className="font-black text-xl tracking-wider truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          GLOBAL OUTPUT
        </div>
      </div>
      <p className="text-xs font-bold text-ink/60 mb-4 border-b-2 border-dashed border-ink/10 pb-2">定义此工作流最终返回的数据</p>

      {/* 变量列表与输入 Handle */}
      <div className="flex flex-col gap-3">
        {(data.dynamic_inputs || []).map((item: any, idx: number) => (
          <div key={`var-${item.key}-${idx}`} className="relative flex items-center justify-between bg-ink/5 p-2 border-2 border-ink border-dashed" style={sketchyShape1}>
            <Handle 
              type="target" 
              position={Position.Left} 
              id={item.key} 
              className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-left-[32px] z-10 hover:!bg-[#EBCB8B] hover:!scale-125 transition-transform" 
            />
            <div className="flex items-center gap-2">
              <Variable size={16} strokeWidth={2.5} className="text-[#EBCB8B]" />
              <span className="font-bold text-sm">{item.key}</span>
            </div>
            <button onClick={() => handleRemoveVar(item.key)} className="opacity-40 hover:opacity-100 hover:text-[#bf616a] transition-colors p-1">
              <X size={16} strokeWidth={3} />
            </button>
          </div>
        ))}
      </div>

      <button 
        onClick={() => setShowModal(true)}
        className="mt-4 w-full flex items-center justify-center gap-2 bg-cream border-2 border-ink py-2 text-sm font-black hover:bg-[#EBCB8B] hover:text-ink transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-0.5"
        style={sketchyShape2}
      >
        <Plus size={16} strokeWidth={3} /> ADD TARGET
      </button>

      {/* 手绘风添加变量弹窗 */}
      {showModal && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto" onClick={(e) => e.stopPropagation()}>
          <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-sm p-8 relative -rotate-1">
            <h3 className="text-2xl font-black mb-4 tracking-widest text-[#EBCB8B]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW TARGET</h3>
            <p className="font-bold mb-4 opacity-80">输入一个新的输出目标名称：</p>
            <input 
              autoFocus
              value={newVar}
              onChange={(e) => setNewVar(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              placeholder="e.g. final_report"
              className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold mb-6 focus:outline-none focus:bg-white shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.1)]"
              style={sketchyShape3}
            />
            <div className="flex gap-4">
              <button onClick={() => setShowModal(false)} style={sketchyShape2} className="flex-1 py-3 bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:shadow-none active:translate-y-1">
                CANCEL
              </button>
              <button onClick={handleAdd} style={sketchyShape1} className="flex-1 py-3 bg-[#EBCB8B] text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#d8b877] transition-all active:shadow-none active:translate-y-1">
                CONFIRM
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}