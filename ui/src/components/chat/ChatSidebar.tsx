// src/components/chat/ChatSidebar.tsx
import { ArrowLeft, Terminal, List, Brain, Server, Zap, AlarmClock, Activity, ChevronDown, ChevronUp, Plus, RefreshCw, Trash2, FileText, GitMerge } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './ChatShared';

export default function ChatSidebar(props: any) {
  const navigate = useNavigate();
  const {
    onBack, setShowSessionModal,
    sidebarMode, setSidebarMode,
    sensorData, toggleSensorStatus, reloadSensors, isReloadingSensors, setShowInstallSensorModal, fetchSensorData,
    mcpData, expandedMcp, setExpandedMcp, refreshMcp, isRefreshingMcp, setShowInstallMcpModal, fetchMcp,
    skillData, expandedSkill, setExpandedSkill, refreshSkill, isRefreshingSkill, setShowInstallSkillModal, fetchSkill,
    cronData, deleteCron, setShowAddCronModal, fetchCron,
    openMdEditor, graphData, fetchGraphData
  } = props;

  return (
    <div className="w-[320px] flex flex-col gap-6 shrink-0 z-20">
      <div className="flex gap-4 items-center">
        <button onClick={onBack} style={sketchyShape2} className="w-16 h-16 bg-cream border-4 border-ink flex items-center justify-center hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:translate-x-[2px] active:shadow-none -rotate-3 hover:rotate-0 group" title="Back">
          <ArrowLeft size={28} strokeWidth={3} className="text-ink group-hover:-translate-x-1 transition-transform" />
        </button>
        <button onClick={() => setShowSessionModal(true)} style={sketchyShape1} className="flex-1 h-16 flex items-center justify-center gap-2 bg-[#EBCB8B] text-ink border-4 border-ink hover:bg-[#d8b877] transition-all active:scale-95 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-2 hover:-rotate-1">
          <List size={22} strokeWidth={3} />
          <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SWITCH</span>
        </button>
      </div>

      <div style={sketchyShape3} className="flex-1 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] p-5 flex flex-col gap-4 overflow-hidden -rotate-1 relative">
        {sidebarMode === 'menu' && (
           <div className="flex-1 flex flex-col gap-5 p-2 mt-2 overflow-y-auto">
               {/* EVOLVE 按钮 */}
               <button onClick={() => navigate('/evolve')} style={sketchyShape2} className="shrink-0 border-4 border-ink bg-[#a3be8c]/40 hover:bg-[#a3be8c] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <Activity size={28} strokeWidth={2.5} className="text-[#729654]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EVOLVE</span>
               </button>

               {/* TASK 按钮 */}
               <button onClick={() => navigate('/task')} style={sketchyShape3} className="shrink-0 border-4 border-ink bg-[#D8E2DC]/50 hover:bg-[#D8E2DC] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <Terminal size={28} strokeWidth={2.5} className="text-[#5e81ac]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>TASK</span>
               </button>

               {/* EDITOR 按钮 */}
               <button onClick={() => navigate('/editor')} style={sketchyShape1} className="shrink-0 border-4 border-ink bg-[#EBCB8B]/50 hover:bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <GitMerge size={28} strokeWidth={2.5} className="text-[#d08770]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>EDITOR</span>
               </button>

               <button onClick={() => navigate('/memory')} style={sketchyShape1} className="shrink-0 border-4 border-ink bg-[#FFB5A7]/40 hover:bg-[#FFB5A7] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <Brain size={28} strokeWidth={2.5} className="text-[#c76c6c]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MEMORY</span>
               </button>
               <button onClick={() => {setSidebarMode('mcp'); fetchMcp();}} style={sketchyShape2} className="shrink-0 border-4 border-ink bg-[#F9E2AF]/50 hover:bg-[#F9E2AF] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <Server size={28} strokeWidth={2.5} className="text-[#b8956e]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP</span>
               </button>
               <button onClick={() => {setSidebarMode('skill'); fetchSkill();}} style={sketchyShape3} className="shrink-0 border-4 border-ink bg-[#FCD5CE]/50 hover:bg-[#FCD5CE] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all -rotate-2 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <Zap size={28} strokeWidth={2.5} className="text-[#d08770]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILL</span>
               </button>
               <button onClick={() => {setSidebarMode('cron'); fetchCron();}} style={sketchyShape1} className="shrink-0 border-4 border-ink bg-[#E8D1C5]/50 hover:bg-[#E8D1C5] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <AlarmClock size={28} strokeWidth={2.5} className="text-[#a07b8a]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CRON</span>
               </button>
               <button onClick={() => openMdEditor('SOUL')} style={sketchyShape2} className="shrink-0 border-4 border-ink bg-[#b48ead]/50 hover:bg-[#b48ead] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-1 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <FileText size={28} strokeWidth={2.5} className="text-[#8f6a88]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SOUL</span>
               </button>
               <button onClick={() => {setSidebarMode('sensor'); fetchSensorData();}} style={sketchyShape3} className="shrink-0 border-4 border-ink bg-[#EBCB8B]/40 hover:bg-[#EBCB8B] shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-3 hover:-translate-y-1 hover:scale-[1.02] transition-all rotate-2 active:shadow-none active:translate-y-1 min-h-[60px]">
                   <Activity size={28} strokeWidth={2.5} className="text-[#b8956e]"/>
                   <span className="font-black text-xl tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSOR</span>
               </button>
           </div>
        )}

        {sidebarMode === 'mcp' && (
           <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
               <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                   <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                   <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>MCP SERVERS</span>
                   <div className="flex items-center gap-2">
                      <button onClick={() => setShowInstallMcpModal(true)} className="p-1 bg-[#88c0d0] text-paper border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-all"><Plus size={18} strokeWidth={3}/></button>
                      <button onClick={refreshMcp} disabled={isRefreshingMcp} title={isRefreshingMcp ? '正在刷新 MCP…' : '刷新 MCP'} className="p-1 bg-[#F9E2AF] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all disabled:opacity-60 disabled:shadow-none disabled:cursor-not-allowed"><RefreshCw size={18} strokeWidth={3} className={isRefreshingMcp ? 'animate-spin' : ''}/></button>
                   </div>
               </div>
               <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                  {Object.keys(mcpData).length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No MCP loaded</p> :
                    Object.entries(mcpData).map(([server, tools]: any, idx) => (
                      <div key={server} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${expandedMcp === server ? 'shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-1' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 cursor-pointer'}`}>
                          <div className="flex justify-between items-center" onClick={() => setExpandedMcp(expandedMcp === server ? null : server)}>
                             <span className="font-black text-lg truncate flex-1">{server}</span>
                             <span className="shrink-0">{expandedMcp === server ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}</span>
                          </div>
                          {expandedMcp === server && (
                              <div className="mt-3 flex flex-col gap-3 border-t-2 border-ink/20 pt-3 border-dashed">
                                 {tools.map((t: any) => (
                                    <div key={t.name} className="text-sm">
                                       <div className="font-bold text-terracotta break-all">{t.name}</div>
                                       <div className="opacity-70 text-xs mt-1 leading-relaxed">{t.description}</div>
                                    </div>
                                 ))}
                              </div>
                          )}
                      </div>
                  ))}
               </div>
           </div>
        )}

        {sidebarMode === 'skill' && (
           <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
               <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                   <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                   <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SKILLS</span>
                   <div className="flex items-center gap-2">
                      <button onClick={() => setShowInstallSkillModal(true)} className="p-1 bg-terracotta text-paper border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-all"><Plus size={18} strokeWidth={3}/></button>
                      <button onClick={refreshSkill} disabled={isRefreshingSkill} title={isRefreshingSkill ? '正在刷新 Skill…' : '刷新 Skill'} className="p-1 bg-[#FCD5CE] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all disabled:opacity-60 disabled:shadow-none disabled:cursor-not-allowed"><RefreshCw size={18} strokeWidth={3} className={isRefreshingSkill ? 'animate-spin' : ''}/></button>
                   </div>
               </div>
               <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                  {skillData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Skills loaded</p> :
                    skillData.map((skill: any, idx: number) => (
                      <div key={skill.name} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape2} className={`border-4 border-ink bg-cream p-3 transition-all ${expandedSkill === skill.name ? 'shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] translate-y-1' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1 cursor-pointer'}`}>
                          <div className="flex justify-between items-center" onClick={() => setExpandedSkill(expandedSkill === skill.name ? null : skill.name)}>
                             <span className="font-black text-lg truncate flex-1">{skill.name}</span>
                             <span className="shrink-0">{expandedSkill === skill.name ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}</span>
                          </div>
                          {expandedSkill === skill.name && <div className="mt-3 flex flex-col gap-2 border-t-2 border-ink/20 pt-2 border-dashed"><div className="opacity-80 text-xs font-bold leading-relaxed">{skill.description}</div></div>}
                      </div>
                  ))}
               </div>
           </div>
        )}

        {sidebarMode === 'cron' && (
           <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
               <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                   <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                   <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>ALARMS</span>
                   <button onClick={fetchCron} className="p-1 bg-[#E8D1C5] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all"><RefreshCw size={18} strokeWidth={3}/></button>
               </div>
               <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                  {cronData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Alarms configured</p> :
                    cronData.map((cron: any, idx: number) => (
                      <div key={cron.id || cron.title} style={idx % 2 === 0 ? sketchyShape3 : sketchyShape1} className={`border-4 border-ink bg-cream p-3 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-1 relative group ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'}`}>
                         <div className="flex justify-between items-center">
                            <span className="font-black text-lg truncate pr-6">{cron.title}</span>
                            <button onClick={()=>deleteCron(cron.id || cron.title)} className="absolute top-2 right-2 p-1 bg-[#bf616a] text-paper border-2 border-ink rounded hover:scale-110 transition-transform opacity-0 group-hover:opacity-100"><Trash2 size={14} strokeWidth={3}/></button>
                         </div>
                         <div className="text-xs font-bold text-ink/70 flex items-center gap-1 mt-1"><AlarmClock size={12}/> Time: {cron.trigger_time}</div>
                      </div>
                  ))}
               </div>
               <button onClick={() => { if (!graphData || graphData.length === 0) fetchGraphData(); setShowAddCronModal(true); }} style={sketchyShape2} className="shrink-0 p-3 bg-[#E8D1C5] text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex items-center justify-center gap-2 mt-2"><Plus size={20} strokeWidth={3}/> ADD ALARM</button>
           </div>
        )}

        {sidebarMode === 'sensor' && (
           <div className="flex-1 flex flex-col h-full overflow-hidden mt-1">
               <div className="flex justify-between items-center mb-4 shrink-0 border-b-4 border-ink/20 pb-3">
                   <button onClick={() => setSidebarMode('menu')} className="p-1 bg-cream border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:-translate-x-1 transition-all"><ArrowLeft size={18} strokeWidth={3}/></button>
                   <span className="font-black tracking-widest text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SENSORS</span>
                   <div className="flex items-center gap-2">
                      <button onClick={() => setShowInstallSensorModal(true)} title="Add Sensor via JSON" className="p-1 bg-[#a3be8c] text-ink border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-all"><Plus size={18} strokeWidth={3}/></button>
                      <button onClick={reloadSensors} disabled={isReloadingSensors} title={isReloadingSensors ? '正在热重启 Sensors…' : '强制热重启'} className="p-1 bg-[#EBCB8B] text-ink border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:rotate-180 transition-all disabled:opacity-60 disabled:shadow-none disabled:cursor-not-allowed"><RefreshCw size={18} strokeWidth={3} className={isReloadingSensors ? 'animate-spin' : ''}/></button>
                   </div>
               </div>
               <div className="flex-1 overflow-y-auto flex flex-col gap-4 p-2 mb-2">
                  {!sensorData || Object.keys(sensorData).length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Sensors found</p> : (
                    Object.entries(sensorData).map(([name, cfg]: [string, any], idx) => (
                      <div key={name} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className="border-4 border-ink bg-cream p-3 transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] flex flex-col gap-2 relative">
                          <div className="flex justify-between items-center pr-2">
                             <span className="font-black text-[17px] truncate max-w-[150px]">{name}</span>
                             <button onClick={() => toggleSensorStatus(name)} className={`relative w-12 h-6 border-2 border-ink flex items-center px-1 transition-colors shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] ${cfg.enabled ? 'bg-[#a3be8c] justify-end' : 'bg-ink/10 justify-start'}`} style={sketchyShape1}> 
                               <div className="w-3.5 h-3.5 bg-ink" style={sketchyShape3}></div> 
                             </button>
                          </div>
                          {cfg.description && <div className="text-xs font-bold opacity-70 leading-relaxed mt-1">{cfg.description}</div>}
                          <div className="flex gap-2 mt-2 border-t-2 border-ink/10 pt-2 border-dashed">
                             {cfg.capabilities?.observe && <div title="Observe" className="w-4 h-4 bg-[#88c0d0] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-transform rotate-3" style={sketchyShape2}></div>}
                             {cfg.capabilities?.express && <div title="Express" className="w-4 h-4 bg-[#EBCB8B] border-2 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)] hover:scale-110 transition-transform -rotate-3" style={sketchyShape1}></div>}
                          </div>
                      </div>
                  )))}
               </div>
           </div>
        )}
      </div>
    </div>
  );
}