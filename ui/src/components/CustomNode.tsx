import { Handle, Position, useEdges } from '@xyflow/react';
import { useFlowStore } from '../store/flowStore';
import { Trash2 } from 'lucide-react';

export default function CustomNode({ id, data, selected }: any) {
  const removeNode = useFlowStore((state) => state.removeNode);
  const updateNodeData = useFlowStore((state) => state.updateNodeData);
  
  // 获取当前画布上所有的连线，用来判断端口是否被占用
  const edges = useEdges();

  // 辅助函数：判断某个输入端口是否已经连线
  const isInputConnected = (handleName: string) => {
    return edges.some((edge) => edge.target === id && edge.targetHandle === handleName);
  };

  return (
    <div 
      className={`bg-paper border-4 border-ink p-5 min-w-[260px] relative group transition-shadow duration-200 
        ${selected ? 'shadow-[8px_8px_0px_0px_rgba(212,122,90,1)]' : 'shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}
      style={{ borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' }}
    >
      
      <button 
        onClick={(e) => { e.stopPropagation(); removeNode(id); }}
        className="absolute -top-4 -right-4 w-8 h-8 bg-[#bf616a] border-2 border-ink flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] z-50 cursor-pointer"
        style={{ borderRadius: '50% 10% 50% 10%' }}
        title="Delete Node"
      >
        <Trash2 size={16} className="text-paper" />
      </button>

      <div className="flex items-center gap-3 mb-4 border-b-2 border-ink/15 pb-3">
        <div style={{ backgroundColor: data.color || '#D47A5A' }} className="w-5 h-5 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] -rotate-3 shrink-0"></div>
        <div className="font-black text-xl tracking-wider truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{data.name}</div>
      </div>

      <div className="flex flex-col gap-5">
        {/* === 输入端口 + 表单绑定区 === */}
        {data.inputs && data.inputs.length > 0 && (
          <div className="flex flex-col gap-3">
            {data.inputs.map((input: any, idx: number) => {
              const connected = isInputConnected(input.name);
              // 寻找该端口是否对应了 config 里的表单字段
              const configField = data.configSchema?.find((f: any) => f.name === input.name);

              return (
                <div key={`in-${input.name}-${idx}`} className="relative flex flex-col gap-1">
                  <div className="flex items-center">
                    <Handle 
                      type="target" position={Position.Left} id={input.name} 
                      className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-left-[28px] z-10 hover:!bg-terracotta hover:!scale-125 transition-transform" 
                    />
                    <span className="text-xs font-bold uppercase ml-1 opacity-80">
                      {input.name} <span className="text-terracotta opacity-90 ml-1">({input.type})</span>
                    </span>
                  </div>

                  {/* 如果该端口带有 Config，则渲染输入框 */}
                  {configField && (
                    <input
                      type="text"
                      placeholder={connected ? "已由上游连线接管" : `手动输入 ${input.name}...`}
                      value={data[configField.name] || ''}
                      onChange={(e) => updateNodeData(id, { [configField.name]: e.target.value })}
                      disabled={connected} // 核心：连线则禁用
                      className={`ml-2 mt-1 px-2 py-1 border-2 border-ink text-sm font-bold shadow-[2px_2px_0px_0px_rgba(26,26,26,0.3)] transition-all outline-none
                        ${connected ? 'bg-ink/10 cursor-not-allowed opacity-50' : 'bg-cream focus:bg-white focus:shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]'}`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* 输出端口 */}
        {data.outputs && data.outputs.length > 0 && (
          <div className="flex flex-col gap-2 items-end mt-2 pt-2 border-t-2 border-ink/10 border-dashed">
            {data.outputs.map((output: any, idx: number) => (
              <div key={`out-${output.name}-${idx}`} className="relative flex items-center justify-end w-full">
                <span className="text-xs font-bold uppercase mr-1 opacity-80 text-right">
                  {output.name} <span className="text-terracotta opacity-90 ml-1">({output.type})</span>
                </span>
                <Handle 
                  type="source" position={Position.Right} id={output.name} 
                  className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-right-[28px] z-10 hover:!bg-[#a3be8c] hover:!scale-125 transition-transform" 
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}