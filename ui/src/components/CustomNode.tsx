import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Handle, Position, useEdges, useUpdateNodeInternals } from '@xyflow/react';
import { useFlowStore } from '../store/flowStore';
import { Trash2, Plus, X } from 'lucide-react';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

const DATA_TYPES = ['any', 'string', 'integer', 'boolean', 'list', 'MessageList'];

export default function CustomNode({ id, data, selected }: any) {
  const removeNode = useFlowStore((state) => state.removeNode);
  const removeEdge = useFlowStore((state) => state.removeEdge);
  const updateNodeData = useFlowStore((state) => state.updateNodeData);
  const updateNodeInternals = useUpdateNodeInternals();
  const edges = useEdges();

  // 🌟 状态重构：使用一个对象字典来动态存储弹窗表单数据
  const [listModalField, setListModalField] = useState<any>(null);
  const [listModalData, setListModalData] = useState<Record<string, any>>({});

  const isConnected = (handleId: string, type: 'target' | 'source') => {
    return edges.some((e) => type === 'target' 
      ? e.target === id && e.targetHandle === handleId 
      : e.source === id && e.sourceHandle === handleId);
  };

  const getDynamicHandles = (portDef: any) => {
    if (portDef.port_type !== 'dynamic' || !portDef.dynamic_rules) return [];
    const rules = portDef.dynamic_rules;
    const sourceData = data[rules.watch_config];
    
    if (rules.method === 'regex') {
      const regex = new RegExp(rules.pattern, 'g');
      const matches = [...(sourceData || '').matchAll(regex)];
      return [...new Set(matches.map((m: any) => m[1]))];
    }
    if (rules.method === 'array_map') {
      if (!Array.isArray(sourceData)) return [];
      return sourceData.map((item: any) => typeof item === 'object' ? (item.name || item.key) : item);
    }
    return [];
  };

  React.useEffect(() => {
    updateNodeInternals(id);
  }, [data, id, updateNodeInternals]);

  // 🌟 动态确认添加逻辑
  const handleAddListVar = () => {
    if (!listModalField) return;

    const valName = (listModalData.name || '').trim();
    if (!valName) return; // 防呆：名字不能为空
    
    const currentList = Array.isArray(data[listModalField.name]) ? data[listModalField.name] : [];
    const exists = currentList.some((i: any) => (typeof i === 'object' ? (i.name || i.key) : i) === valName);
    
    if (!exists) {
      // 核心：如果有 schema，保存完整的字典；没有则保留兜底的 name/type
      const newItem = listModalField.item_schema 
        ? { ...listModalData } 
        : { name: valName, type: listModalData.type || 'any' };

      updateNodeData(id, { 
        [listModalField.name]: [...currentList, newItem] 
      });
    }
    
    setListModalField(null);
    setListModalData({});
  };

  const renderConfigField = (field: any) => {
    const value = data[field.name];

    if (field.type === 'list') {
      const listVal = Array.isArray(value) ? value : [];
      const dynamicIn = data.inputs?.find((i:any) => i.port_type === 'dynamic' && i.dynamic_rules?.watch_config === field.name);
      const dynamicOut = data.outputs?.find((o:any) => o.port_type === 'dynamic' && o.dynamic_rules?.watch_config === field.name);

      return (
        <div className="flex flex-col gap-2 mt-1">
          {listVal.map((item: any, idx: number) => {
            const itemName = typeof item === 'object' ? (item.name || item.key) : item;
            const itemType = typeof item === 'object' ? item.type : 'any';
            // 提取 schema 中的新属性用于悬浮提示和红星显示
            const itemRequired = typeof item === 'object' ? item.required : false;
            const itemDesc = typeof item === 'object' ? item.description : '';

            return (
              <div key={idx} className="relative flex items-center justify-between bg-ink/5 px-2 py-1.5 border-2 border-dashed border-ink/30" style={sketchyShape1}>
                {dynamicIn && (
                  <Handle type="target" position={Position.Left} id={itemName} className="!bg-terracotta !w-4 !h-4 !border-2 !border-paper !-left-[18px] z-10 hover:!scale-125 transition-transform" />
                )}
                
                {/* 🌟 节点上显示必填红星，悬浮显示 Description */}
                <span className={`text-sm font-bold text-ink ${dynamicIn ? 'ml-2' : ''} ${dynamicOut ? 'mr-2' : ''}`} title={itemDesc}>
                  {itemName}
                  {itemRequired && <span className="text-[#bf616a] ml-1">*</span>}
                  <span className="opacity-60 text-[10px] ml-1 uppercase">({itemType})</span>
                </span>
                
                <button 
                  onClick={() => {
                    edges
                      .filter((e) => (e.target === id && e.targetHandle === itemName) || (e.source === id && e.sourceHandle === itemName))
                      .forEach((e) => removeEdge(e.id));
                    updateNodeData(id, { [field.name]: listVal.filter((v:any) => (typeof v === 'object' ? v.name : v) !== itemName) });
                  }}
                  className="opacity-40 hover:opacity-100 hover:text-[#bf616a] transition-all ml-auto"
                >
                  <X size={14} strokeWidth={3} />
                </button>

                {dynamicOut && (
                  <Handle type="source" position={Position.Right} id={itemName} className="!bg-[#EBCB8B] !w-4 !h-4 !border-2 !border-paper !-right-[18px] z-10 hover:!scale-125 transition-transform" />
                )}
              </div>
            );
          })}
          
          <button 
            onClick={() => { 
              setListModalField(field); 
              // 🌟 初始化弹窗表单数据
              const initialData: Record<string, any> = {};
              if (field.item_schema) {
                field.item_schema.forEach((sch: any) => {
                  initialData[sch.name] = sch.default !== undefined ? sch.default : (sch.type === 'boolean' ? false : '');
                });
              } else {
                initialData.type = 'any';
              }
              setListModalData(initialData); 
            }}
            className="flex items-center justify-center gap-1 bg-cream border-2 border-ink py-1.5 text-xs font-black hover:bg-[#a3be8c] hover:text-ink transition-all shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-[1px]"
            style={sketchyShape1}
          >
            <Plus size={14} strokeWidth={3} /> ADD {field.label}
          </button>
        </div>
      );
    }

    if (field.type === 'textarea') {
      return <textarea value={value || ''} onChange={(e) => updateNodeData(id, { [field.name]: e.target.value })} className="mt-1 px-3 py-2 border-2 border-ink text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,0.3)] resize-none h-24 outline-none bg-cream focus:bg-white font-mono" />;
    }
    return <input type="text" value={value || ''} onChange={(e) => updateNodeData(id, { [field.name]: e.target.value })} className="mt-1 px-2 py-1 border-2 border-ink text-sm shadow-[2px_2px_0px_0px_rgba(26,26,26,0.3)] outline-none bg-cream focus:bg-white" />;
  };

  return (
    <div 
      className={`bg-paper border-4 border-ink p-5 min-w-[280px] relative group transition-shadow duration-200 
        ${selected ? 'shadow-[8px_8px_0px_0px_rgba(212,122,90,1)]' : 'shadow-[6px_6px_0px_0px_rgba(26,26,26,1)]'}`}
      style={{ borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' }}
    >
      <button onClick={(e) => { e.stopPropagation(); removeNode(id); }} className="absolute -top-4 -right-4 w-8 h-8 bg-[#bf616a] border-2 border-ink flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500 shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] z-50 cursor-pointer" style={{ borderRadius: '50% 10% 50% 10%' }}>
        <Trash2 size={16} className="text-paper" />
      </button>

      <div className="flex items-center gap-3 mb-4 border-b-2 border-ink/15 pb-3">
        <div style={{ backgroundColor: data.color || '#D47A5A' }} className="w-5 h-5 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] -rotate-3 shrink-0"></div>
        <div className="font-black text-xl tracking-wider truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{data.name}</div>
      </div>

      <div className="flex flex-col gap-4">
        {/* 输入引脚 */}
        {data.inputs && data.inputs.length > 0 && (
          <div className="flex flex-col gap-2">
            {data.inputs.map((input: any) => {
              if (input.port_type === 'static' || !input.port_type) {
                return (
                  <div key={`in-${input.name}`} className="relative flex items-center">
                    <Handle type="target" position={Position.Left} id={input.name} className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-left-[28px] z-10 hover:!bg-terracotta hover:!scale-125 transition-transform" />
                    <span className="text-xs font-bold uppercase ml-1 opacity-80">
                      {input.name}
                      {input.type && <span className="text-terracotta opacity-90 ml-1 text-[10px] lowercase">({input.type})</span>}
                    </span>
                  </div>
                );
              }
              if (input.port_type === 'dynamic') {
                const watchedField = data.configSchema?.find((f:any) => f.name === input.dynamic_rules?.watch_config);
                if (watchedField?.type === 'list') return null;

                return getDynamicHandles(input).map((varName: string) => (
                  <div key={`dyn-in-${varName}`} className="relative flex items-center bg-terracotta/10 p-1 border border-dashed border-terracotta/30">
                    <Handle type="target" position={Position.Left} id={varName} className="!bg-terracotta !w-4 !h-4 !border-2 !border-paper !-left-[32px] z-10 hover:!scale-125 transition-transform" />
                    <span className="text-xs font-bold text-terracotta ml-1">{varName}</span>
                  </div>
                ));
              }
              return null;
            })}
          </div>
        )}

        {/* 配置表单 */}
        {data.configSchema?.map((configField: any) => {
           const isHandleConnected = isConnected(configField.name, 'target');
           return (
             <div key={`cfg-${configField.name}`} className="flex flex-col gap-1 mt-1 border-t-2 border-dashed border-ink/10 pt-2">
               <span className="text-xs font-bold uppercase opacity-80 flex justify-between">
                 {configField.label}
                 {isHandleConnected && <span className="text-[10px] text-terracotta">连线已接管</span>}
               </span>
               {!isHandleConnected && renderConfigField(configField)}
             </div>
           );
        })}

        {/* 输出引脚 */}
        {data.outputs && data.outputs.length > 0 && (
          <div className="flex flex-col gap-2 items-end mt-2 pt-2 border-t-2 border-ink/10 border-dashed">
            {data.outputs.map((output: any) => {
              if (output.port_type === 'static' || !output.port_type) {
                return (
                  <div key={`out-${output.name}`} className="relative flex items-center justify-end w-full">
                    <span className="text-xs font-bold uppercase mr-1 opacity-80">
                      {output.name}
                      {output.type && <span className="text-terracotta opacity-90 ml-1 text-[10px] lowercase">({output.type})</span>}
                    </span>
                    <Handle type="source" position={Position.Right} id={output.name} className="!bg-ink !w-4 !h-4 !border-2 !border-paper !-right-[28px] z-10 hover:!bg-[#a3be8c] hover:!scale-125 transition-transform" />
                  </div>
                );
              }
              if (output.port_type === 'dynamic') {
                const watchedField = data.configSchema?.find((f:any) => f.name === output.dynamic_rules?.watch_config);
                if (watchedField?.type === 'list') return null;

                return getDynamicHandles(output).map((branchName: string) => (
                  <div key={`dyn-out-${branchName}`} className="relative flex items-center justify-end w-full bg-[#EBCB8B]/20 p-1 border border-dashed border-[#EBCB8B]/50">
                    <span className="text-xs font-bold text-[#d08770] mr-1">{branchName}</span>
                    <Handle type="source" position={Position.Right} id={branchName} className="!bg-[#EBCB8B] !w-4 !h-4 !border-2 !border-paper !-right-[32px] z-10 hover:!scale-125 transition-transform" />
                  </div>
                ));
              }
              return null;
            })}
          </div>
        )}
      </div>

      {/* 🌟 全新动态表单手绘弹窗 */}
      {listModalField && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto" onClick={(e) => e.stopPropagation()}>
          <div style={sketchyShape3} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-sm p-8 relative -rotate-1">
            <h3 className="text-2xl font-black mb-6 tracking-widest text-[#a3be8c] border-b-4 border-ink/20 pb-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              NEW {listModalField.label?.toUpperCase()}
            </h3>
            
            <div className="flex flex-col gap-4 mb-8 max-h-[60vh] overflow-y-auto pr-2">
              {listModalField.item_schema ? (
                // 🟢 动态 Schema 渲染 (针对 task_input 这样的高级节点)
                listModalField.item_schema.map((sch: any) => (
                  <div key={sch.name}>
                    <p className="font-bold mb-2 opacity-80">{sch.label || sch.name}:</p>
                    
                    {sch.type === 'boolean' ? (
                      <label className="flex items-center gap-3 cursor-pointer bg-cream border-4 border-ink p-3 shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.1)] hover:bg-sand transition-colors" style={sketchyShape2}>
                        <input
                          type="checkbox"
                          checked={!!listModalData[sch.name]}
                          onChange={(e) => setListModalData({ ...listModalData, [sch.name]: e.target.checked })}
                          className="w-5 h-5 accent-terracotta cursor-pointer"
                        />
                        <span className="font-bold">{sch.label}</span>
                      </label>
                    ) : sch.type === 'string' && sch.name === 'type' ? (
                      // Type 特殊处理下拉框
                      <select
                        value={listModalData[sch.name] || 'any'}
                        onChange={(e) => setListModalData({ ...listModalData, [sch.name]: e.target.value })}
                        className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold focus:outline-none focus:bg-white shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.1)]"
                        style={sketchyShape1}
                      >
                        {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    ) : (
                      // 普通文本框
                      <input
                        autoFocus={sch.name === 'name'}
                        value={listModalData[sch.name] || ''}
                        onChange={(e) => setListModalData({ ...listModalData, [sch.name]: e.target.value })}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddListVar()}
                        placeholder={`Enter ${sch.name}...`}
                        className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold focus:outline-none focus:bg-white shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.1)]"
                        style={sketchyShape2}
                      />
                    )}
                  </div>
                ))
              ) : (
                // 🔴 降级渲染 (针对普通的 list，只要求 name 和 type)
                <>
                  <div>
                    <p className="font-bold mb-2 opacity-80">变量名称 (Name):</p>
                    <input 
                      autoFocus
                      value={listModalData.name || ''}
                      onChange={(e) => setListModalData({ ...listModalData, name: e.target.value })}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddListVar()}
                      placeholder="e.g. user_query"
                      className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold focus:outline-none focus:bg-white shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.1)]"
                      style={sketchyShape2}
                    />
                  </div>
                  <div>
                    <p className="font-bold mb-2 opacity-80">数据类型 (Type):</p>
                    <select
                      value={listModalData.type || 'any'}
                      onChange={(e) => setListModalData({ ...listModalData, type: e.target.value })}
                      className="w-full bg-cream border-4 border-ink p-3 text-lg font-bold focus:outline-none focus:bg-white shadow-[inset_2px_2px_0px_0px_rgba(26,26,26,0.1)]"
                      style={sketchyShape1}
                    >
                      {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                </>
              )}
            </div>

            <div className="flex gap-4">
              <button onClick={() => { setListModalField(null); setListModalData({}); }} style={sketchyShape1} className="flex-1 py-3 bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all active:shadow-none active:translate-y-1">
                CANCEL
              </button>
              <button onClick={handleAddListVar} style={sketchyShape2} className="flex-1 py-3 bg-[#a3be8c] text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] transition-all active:shadow-none active:translate-y-1">
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