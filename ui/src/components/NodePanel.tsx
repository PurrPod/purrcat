import { useEffect } from 'react';
import { useFlowStore } from '../store/flowStore';

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

export default function NodePanel() {
  const catalog = useFlowStore((state) => state.catalog);
  const fetchCatalog = useFlowStore((state) => state.fetchCatalog);

  // 组件挂载时自动拉取后端的可用节点列表
  useEffect(() => {
    fetchCatalog();
  }, []);

  const onDragStart = (event: any, nodeData: any) => {
    event.dataTransfer.setData('application/reactflow', JSON.stringify(nodeData));
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="flex flex-col gap-6 pt-2 pb-8 px-2">
      <div className="text-center mb-4 relative">
        <h2 className="text-3xl font-black text-ink tracking-widest -rotate-2 inline-block relative z-10" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
          TOOLKIT
        </h2>
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-6 bg-[#EBCB8B]/40 -rotate-1 z-0" style={sketchyShape1}></div>
      </div>

      {catalog.length === 0 && (
        <div className="text-center font-bold text-ink/50 mt-10">Loading Nodes...</div>
      )}

      {catalog.map((node, idx) => (
        <div
          key={node.type}
          draggable
          onDragStart={(e) => onDragStart(e, node)}
          style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3}
          className={`p-5 border-4 border-ink bg-paper cursor-grab active:cursor-grabbing hover:-translate-y-2 hover:scale-105 transition-all shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:shadow-[10px_10px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-3 relative group
            ${idx % 3 === 0 ? 'rotate-2' : idx % 2 === 0 ? '-rotate-2' : 'rotate-1'}`}
        >
          <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-4 h-4 bg-ink rounded-full opacity-0 group-hover:opacity-100 transition-opacity"></div>
          
          <div className="flex items-center gap-3">
            <div 
              style={{ ...sketchyShape1, backgroundColor: node.color || '#D47A5A' }} 
              className="w-6 h-6 border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] -rotate-6"
            ></div>
            <div className="font-black text-xl tracking-wide text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
              {node.name}
            </div>
          </div>
          
          <div className="text-sm font-bold text-ink/70 leading-relaxed font-sans border-t-2 border-ink/10 pt-2 border-dashed">
            {node.description || "Drag me to the canvas!"}
          </div>
        </div>
      ))}
    </div>
  );
}