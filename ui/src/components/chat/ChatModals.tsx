// src/components/chat/ChatModals.tsx
import React from 'react';
import { Loader2, X, Trash2, Check, ChevronUp, ChevronDown, Plus, Download, Save, AlertCircle, FileJson, FileText, GitFork, Pencil, Clock } from 'lucide-react';
import { sketchyShape1, sketchyShape2, sketchyShape3 } from './ChatShared';

export default function ChatModals(props: any) {
  const {
    isCheckingOut, showBusyModal, setShowBusyModal,
    showModal, setShowModal, newAlias, setNewAlias, confirmNewSession,
    showBranchModal, setShowBranchModal, branchAlias, setBranchAlias, confirmBranchSession,
    sessionToDelete, setSessionToDelete, confirmDeleteSession,
    branchToDelete, setBranchToDelete, currentSessionId, loadSessionHistory, loadBranches, setCurrentBranchId,
    showAddCronModal, setShowAddCronModal, newCron, setNewCron, addCron,
    showInstallSkillModal, setShowInstallSkillModal, skillInstallUrl, setSkillInstallUrl, handleInstallSkill, isInstallingSkill,
    showInstallMcpModal, setShowInstallMcpModal, mcpInstallJson, setMcpInstallJson, handleInstallMcp, isInstallingMcp,
    showInstallSensorModal, setShowInstallSensorModal, sensorInstallJson, setSensorInstallJson, handleInstallSensor, isInstallingSensor,
    showMdModal, setShowMdModal, mdType, mdContent, setMdContent, saveMdContent, isSavingMd,
    showSkillSelectModal, setShowSkillSelectModal, skillData, tempSelectedSkills, setTempSelectedSkills, expandedSkill, setExpandedSkill, setSelectedSkills,
    showMcpSelectModal, setShowMcpSelectModal, mcpData, tempSelectedMcps, setTempSelectedMcps, expandedMcp, setExpandedMcp, setSelectedMcps,
    showRefModal, setShowRefModal, tempRefPath, setTempRefPath, setRefPaths,
    showGraphSelectModal, setShowGraphSelectModal, graphData, tempSelectedGraphs, setTempSelectedGraphs, setSelectedGraphs,
    isConfigOpen, setIsConfigOpen, activeTab, setActiveTab, configData, expandedKey, editJsonStr, setEditJsonStr, toggleKey, handleSaveConfig,
    showSessionModal, setShowSessionModal, isAgentThinking, sessions, handleSelectSession, editingSessionId, editingAlias, setEditingAlias, setEditingSessionId, handleRename
  } = props;

  const CONFIG_TABS = ['model', 'sensor', 'file', 'memory', 'mcp'];

  return (
    <>
      {isCheckingOut && (
        <div className="fixed inset-0 bg-cream/70 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-10 flex flex-col items-center justify-center gap-6 shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] -rotate-1 min-w-[320px]">
            <div className="relative flex items-center justify-center">
              <div className="absolute inset-0 bg-[#EBCB8B] rounded-full blur-xl opacity-60 animate-pulse"></div>
              <div className="bg-ink p-4 border-4 border-paper shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] z-10" style={sketchyShape3}>
                <Loader2 size={64} strokeWidth={2.5} className="animate-spin text-paper" />
              </div>
            </div>
            <div className="text-center mt-2">
              <h3 className="text-3xl font-black tracking-widest text-ink mb-2" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CHECKING OUT...</h3>
              <p className="font-bold opacity-70 text-base text-ink/80 bg-terracotta/10 px-3 py-1 border-2 border-dashed border-ink/20 inline-block" style={sketchyShape1}>
                Waiting for the agent to complete tasks...
              </p>
            </div>
          </div>
        </div>
      )}

      {showBusyModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-2xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>AGENT IS BUSY!</h3>
              <button onClick={() => setShowBusyModal(false)} className="hover:text-terracotta hover:scale-110 transition-all">
                <X size={28} strokeWidth={3}/>
              </button>
            </div>
            <div className="rotate-1">
              <p className="font-bold text-ink/80 text-base leading-relaxed">
                喵~ Agent 正在埋头苦干中！为了保护数据安全，请等待当前任务完成后，再切换会话或拉取新分支哦！
              </p>
            </div>
            <button onClick={() => setShowBusyModal(false)} style={sketchyShape3} className="mt-2 bg-[#EBCB8B] text-ink font-black py-3 border-4 border-ink hover:bg-[#d8b877] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 rotate-1">
              GOT IT
            </button>
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-md w-full">
            <div className="flex justify-between items-center -rotate-1">
              <h3 className="text-3xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW CHAT</h3>
              <button onClick={() => setShowModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="-rotate-1">
              <input autoFocus value={newAlias} onChange={e => setNewAlias(e.target.value)} onKeyDown={e => e.key === 'Enter' && confirmNewSession()} placeholder="Give it a cool name..." className="w-full border-4 border-ink bg-cream p-4 font-bold text-lg focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" style={sketchyShape3} />
            </div>
            <button onClick={confirmNewSession} style={{ ...sketchyShape1, fontFamily: '"Comic Sans MS", cursive' }} className="bg-terracotta text-paper font-black tracking-widest text-xl py-4 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-none transition-all rotate-1">
              CREATE NOW
            </button>
          </div>
        </div>
      )}

      {showBranchModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-md w-full">
            <div className="flex justify-between items-center -rotate-1">
              <h3 className="text-3xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>BRANCH CHAT</h3>
              <button onClick={() => setShowBranchModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="-rotate-1">
              <p className="font-bold opacity-70 mb-2 text-ink">基于当前时间线创造一个平行宇宙：</p>
              <input autoFocus value={branchAlias} onChange={e => setBranchAlias(e.target.value)} onKeyDown={e => e.key === 'Enter' && confirmBranchSession()} placeholder="Give the new branch a name..." className="w-full border-4 border-ink bg-cream p-4 font-bold text-lg focus:outline-none focus:bg-white shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)] placeholder:text-ink/30" style={sketchyShape3} />
            </div>
            <button onClick={confirmBranchSession} style={{ ...sketchyShape1, fontFamily: '"Comic Sans MS", cursive' }} className="bg-[#d08770] text-paper font-black tracking-widest text-xl py-4 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-none transition-all rotate-1">
              FORK TIMELINE
            </button>
          </div>
        </div>
      )}

      {sessionToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DELETE CHAT?</h3>
              <button onClick={() => setSessionToDelete(null)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要删除这个分支会话吗？该分支上的历史记忆将永久丢失！</p>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setSessionToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">CANCEL</button>
              <button onClick={confirmDeleteSession} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">DELETE</button>
            </div>
          </div>
        </div>
      )}

      {branchToDelete && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] -rotate-1 max-w-sm w-full">
            <div className="flex justify-between items-center rotate-1">
              <h3 className="text-2xl font-black tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DESTROY BRANCH?</h3>
              <button onClick={() => setBranchToDelete(null)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <p className="font-bold text-ink/70 rotate-1">确定要彻底销毁支线 [{branchToDelete}] 的全部历史记忆吗？</p>
            <div className="flex gap-4 rotate-1 mt-2">
              <button onClick={() => setBranchToDelete(null)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black py-3 border-4 border-ink hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">CANCEL</button>
              <button onClick={async () => {
                 if (!currentSessionId) return;
                 try {
                     const res = await fetch(`http://localhost:8000/api/sessions/${currentSessionId}/branches/${branchToDelete}`, { method: 'DELETE' });
                     if (res.ok) {
                       setCurrentBranchId('main');
                       loadSessionHistory(currentSessionId, 'main');
                       loadBranches(currentSessionId);
                       setBranchToDelete(null);
                     }
                   } catch {}
              }} style={sketchyShape1} className="flex-1 bg-[#bf616a] text-paper font-black py-3 border-4 border-ink hover:bg-[#a54e56] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1">DESTROY</button>
            </div>
          </div>
        </div>
      )}

      {showAddCronModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-sm w-full">
            <h3 className="text-2xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>NEW ALARM</h3>
            <input placeholder="Alarm Title..." value={newCron.title} onChange={e=>setNewCron({...newCron, title:e.target.value})} className="border-4 border-ink p-3 font-bold bg-cream focus:outline-none" style={sketchyShape3} />
            <input placeholder="Trigger Time (cron expr or HH:MM)" value={newCron.trigger_time} onChange={e=>setNewCron({...newCron, trigger_time:e.target.value})} className="border-4 border-ink p-3 font-bold bg-cream focus:outline-none" style={sketchyShape1} />
            <div className="flex gap-4 mt-2">
              <button onClick={() => setShowAddCronModal(false)} className="flex-1 bg-cream border-4 border-ink font-black py-3 active:translate-y-1 transition-transform shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none" style={sketchyShape2}>CANCEL</button>
              <button onClick={addCron} className="flex-1 bg-[#d08770] text-paper border-4 border-ink font-black py-3 active:translate-y-1 transition-transform shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none" style={sketchyShape1}>SAVE</button>
            </div>
          </div>
        </div>
      )}

      {showInstallSkillModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-terracotta" style={{ fontFamily: '"Comic Sans MS", cursive' }}>INSTALL SKILL</h3>
              <button onClick={() => setShowInstallSkillModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="-rotate-1">
              <p className="font-bold opacity-70 mb-3 text-ink text-sm">输入第三方 Skill 的 Github Tree 链接以自动安装：</p>
              <input value={skillInstallUrl} onChange={e => setSkillInstallUrl(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleInstallSkill()} placeholder="https://github.com/..." className="w-full border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-base focus:outline-none shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3} />
            </div>
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowInstallSkillModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] hover:shadow-none transition-all">CANCEL</button>
              <button onClick={handleInstallSkill} disabled={isInstallingSkill} style={sketchyShape1} className="flex-1 bg-[#a3be8c] text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] hover:translate-y-[1px] flex items-center justify-center gap-2">
                {isInstallingSkill ? <Loader2 size={24} className="animate-spin" strokeWidth={3}/> : <Download size={24} strokeWidth={3}/>} DOWNLOAD
              </button>
            </div>
          </div>
        </div>
      )}

      {showInstallMcpModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-[#88c0d0]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>INSTALL MCP</h3>
              <button onClick={() => setShowInstallMcpModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="-rotate-1 flex flex-col h-full">
              <textarea value={mcpInstallJson} onChange={e => setMcpInstallJson(e.target.value)} placeholder={'{\n  "mcpServers": { ... }\n}'} className="w-full h-64 border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-sm font-mono focus:outline-none resize-none shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3} spellCheck={false} />
            </div>
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowInstallMcpModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] transition-all">CANCEL</button>
              <button onClick={handleInstallMcp} disabled={isInstallingMcp} style={sketchyShape1} className="flex-1 bg-[#88c0d0] text-paper font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#72a6b5] flex items-center justify-center gap-2">
                {isInstallingMcp ? <Loader2 size={24} className="animate-spin" strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>} SAVE & LOAD
              </button>
            </div>
          </div>
        </div>
      )}

      {showInstallSensorModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-[#a3be8c]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>ADD SENSOR</h3>
              <button onClick={() => setShowInstallSensorModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="-rotate-1 flex flex-col h-full">
              <textarea value={sensorInstallJson} onChange={e => setSensorInstallJson(e.target.value)} placeholder={'{\n  "my_custom_sensor": { ... }\n}'} className="w-full h-64 border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-sm font-mono focus:outline-none resize-none shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3} spellCheck={false} />
            </div>
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowInstallSensorModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-[1px] transition-all">CANCEL</button>
              <button onClick={handleInstallSensor} disabled={isInstallingSensor} style={sketchyShape1} className="flex-1 bg-[#a3be8c] text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] flex items-center justify-center gap-2">
                {isInstallingSensor ? <Loader2 size={24} className="animate-spin" strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>} SAVE & LOAD
              </button>
            </div>
          </div>
        </div>
      )}

      {showMdModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[150] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-4xl h-[85vh]">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/20 pb-4 shrink-0">
              <div className="flex items-center gap-3">
                <FileText size={32} className="text-terracotta" strokeWidth={2.5} />
                <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{mdType}.md</h3>
              </div>
              <button onClick={() => setShowMdModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={32} strokeWidth={3}/></button>
            </div>
            <div className="flex-1 -rotate-1 overflow-hidden flex flex-col w-full">
              <textarea value={mdContent} onChange={e => setMdContent(e.target.value)} className="w-full h-full border-4 border-ink bg-[#FDF8F0] p-6 font-mono text-base font-bold focus:outline-none resize-none" style={sketchyShape3} spellCheck={false} />
            </div>
            <div className="shrink-0 flex justify-end gap-4 -rotate-1 pt-2">
              <button onClick={() => setShowMdModal(false)} style={sketchyShape3} className="px-8 bg-cream text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all">CANCEL</button>
              <button onClick={saveMdContent} disabled={isSavingMd} style={sketchyShape1} className="px-10 bg-[#a3be8c] text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#8eb072] flex items-center gap-2">
                {isSavingMd ? <Loader2 className="animate-spin" size={24} strokeWidth={3}/> : <Save size={24} strokeWidth={3}/>} SAVE FILE
              </button>
            </div>
          </div>
        </div>
      )}

      {showSkillSelectModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-md h-[70vh]">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-3 shrink-0">
              <h3 className="text-2xl font-black tracking-widest text-[#d08770]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SELECT SKILLS</h3>
              <button onClick={() => setShowSkillSelectModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="flex-1 overflow-y-auto flex flex-col gap-3 -rotate-1 p-1">
              {skillData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Skills loaded</p> : (
                 skillData.map((skill: any, idx: number) => {
                   const isSelected = tempSelectedSkills.includes(skill.name);
                   return (
                     <div key={skill.name} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${isSelected ? 'shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] border-terracotta bg-terracotta/10' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]'} flex flex-col gap-2 cursor-pointer`} onClick={() => {
                       if (isSelected) setTempSelectedSkills(tempSelectedSkills.filter((s: string) => s !== skill.name));
                       else setTempSelectedSkills([...tempSelectedSkills, skill.name]);
                     }}>
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 border-2 border-ink flex items-center justify-center ${isSelected ? 'bg-terracotta' : 'bg-paper'}`} style={sketchyShape2}>
                            {isSelected && <Check size={16} strokeWidth={4} className="text-paper" />}
                          </div>
                          <span className="font-black text-lg flex-1">{skill.name}</span>
                          <button onClick={(e) => { e.stopPropagation(); setExpandedSkill(expandedSkill === skill.name ? null : skill.name); }}>
                             {expandedSkill === skill.name ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
                          </button>
                        </div>
                        {expandedSkill === skill.name && <div className="text-xs font-bold opacity-80 pl-8 pt-1 border-t-2 border-ink/10 border-dashed mt-1">{skill.description}</div>}
                     </div>
                   );
                 })
              )}
            </div>
            <div className="shrink-0 flex justify-end gap-3 -rotate-1 pt-2 border-t-4 border-ink/10">
              <button onClick={() => { setSelectedSkills(tempSelectedSkills); setShowSkillSelectModal(false); }} style={sketchyShape1} className="px-8 bg-[#EBCB8B] text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]">COMPLETE</button>
            </div>
          </div>
        </div>
      )}

      {showMcpSelectModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-md h-[70vh]">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-3 shrink-0">
              <h3 className="text-2xl font-black tracking-widest text-[#b8956e]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SELECT MCP</h3>
              <button onClick={() => setShowMcpSelectModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="flex-1 overflow-y-auto flex flex-col gap-3 -rotate-1 p-1">
              {Object.keys(mcpData).length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No MCP loaded</p> : (
                 Object.entries(mcpData).map(([server, tools]: any, idx) => {
                   const isSelected = tempSelectedMcps.includes(server);
                   return (
                     <div key={server} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${isSelected ? 'shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] border-terracotta bg-terracotta/10' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]'} flex flex-col gap-2 cursor-pointer`} onClick={() => {
                       if (isSelected) setTempSelectedMcps(tempSelectedMcps.filter((s: string) => s !== server));
                       else setTempSelectedMcps([...tempSelectedMcps, server]);
                     }}>
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 border-2 border-ink flex items-center justify-center ${isSelected ? 'bg-terracotta' : 'bg-paper'}`} style={sketchyShape2}>
                            {isSelected && <Check size={16} strokeWidth={4} className="text-paper" />}
                          </div>
                          <span className="font-black text-lg flex-1 truncate">{server}</span>
                          <button onClick={(e) => { e.stopPropagation(); setExpandedMcp(expandedMcp === server ? null : server); }}>
                             {expandedMcp === server ? <ChevronUp size={20}/> : <ChevronDown size={20}/>}
                          </button>
                        </div>
                        {expandedMcp === server && (
                          <div className="text-xs font-bold opacity-80 pl-8 pt-1 border-t-2 border-ink/10 border-dashed mt-1 flex flex-col gap-1">
                            {tools.map((t: any) => <div key={t.name} className="flex gap-1 items-baseline"><span className="text-terracotta font-black">{t.name}:</span> <span className="opacity-70 truncate">{t.description}</span></div>)}
                          </div>
                        )}
                     </div>
                   );
                 })
              )}
            </div>
            <div className="shrink-0 flex justify-end gap-3 -rotate-1 pt-2 border-t-4 border-ink/10">
              <button onClick={() => { setSelectedMcps(tempSelectedMcps); setShowMcpSelectModal(false); }} style={sketchyShape1} className="px-8 bg-[#EBCB8B] text-ink font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]">COMPLETE</button>
            </div>
          </div>
        </div>
      )}

      {showRefModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-lg w-full">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-2">
              <h3 className="text-3xl font-black tracking-widest text-[#88c0d0]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>REFERENCE FILE</h3>
              <button onClick={() => setShowRefModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="-rotate-1">
              <p className="font-bold opacity-70 mb-3 text-ink text-sm">请输入或粘贴本地文件/文件夹的绝对路径：</p>
              <input autoFocus value={tempRefPath} onChange={e => setTempRefPath(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && tempRefPath.trim()) { setRefPaths([...new Set([...tempRefPath.trim()])]); setTempRefPath(''); setShowRefModal(false); } }} placeholder="/Users/dev/my_project/file.py" className="w-full border-4 border-ink bg-[#FDF8F0] p-4 font-bold text-base focus:outline-none shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.05)]" style={sketchyShape3} />
            </div>
            <div className="flex gap-4 -rotate-1 mt-2">
              <button onClick={() => setShowRefModal(false)} style={sketchyShape3} className="flex-1 bg-cream text-ink font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]">CANCEL</button>
              <button onClick={() => { if (tempRefPath.trim()) { setRefPaths([...new Set([...tempRefPath.trim()])]); setTempRefPath(''); setShowRefModal(false); } }} style={sketchyShape1} className="flex-1 bg-[#88c0d0] text-paper font-black tracking-widest text-lg py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-[#72a6b5] flex items-center justify-center gap-2"><Plus size={24} strokeWidth={3}/> ADD PATH</button>
            </div>
          </div>
        </div>
      )}

      {showGraphSelectModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-6 flex flex-col gap-4 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 w-full max-w-md h-[70vh]">
            <div className="flex justify-between items-center -rotate-1 border-b-4 border-ink/10 pb-3 shrink-0">
              <h3 className="text-2xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SELECT GRAPH</h3>
              <button onClick={() => setShowGraphSelectModal(false)} className="hover:text-terracotta hover:scale-110 transition-all"><X size={28} strokeWidth={3}/></button>
            </div>
            <div className="flex-1 overflow-y-auto flex flex-col gap-3 -rotate-1 p-1">
              {graphData.length === 0 ? <p className="font-bold text-center mt-6 opacity-50 text-sm">No Graphs found</p> : (
                 graphData.map((graph: any, idx: number) => {
                   const graphName = graph.name.replace('.json', '');
                   const isSelected = tempSelectedGraphs.includes(graphName);
                   return (
                     <div key={graphName} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3} className={`border-4 border-ink bg-cream p-3 transition-all ${isSelected ? 'shadow-[4px_4px_0px_0px_rgba(212,122,90,1)] border-terracotta bg-terracotta/10' : 'shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]'} flex flex-col gap-2 cursor-pointer`} onClick={() => {
                       if (isSelected) setTempSelectedGraphs(tempSelectedGraphs.filter((s: string) => s !== graphName));
                       else setTempSelectedGraphs([...tempSelectedGraphs, graphName]);
                     }}>
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 border-2 border-ink flex items-center justify-center ${isSelected ? 'bg-terracotta' : 'bg-paper'}`} style={sketchyShape2}>
                            {isSelected && <Check size={16} strokeWidth={4} className="text-paper" />}
                          </div>
                          <span className="font-black text-lg flex-1 truncate">{graphName}</span>
                        </div>
                     </div>
                   );
                 })
              )}
            </div>
            <div className="shrink-0 flex justify-end gap-3 -rotate-1 pt-2 border-t-4 border-ink/10">
              <button onClick={() => { setSelectedGraphs(tempSelectedGraphs); setShowGraphSelectModal(false); }} style={sketchyShape1} className="px-8 bg-ink text-paper font-black py-3 border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]">COMPLETE</button>
            </div>
          </div>
        </div>
      )}

      {isConfigOpen && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center bg-ink/70 backdrop-blur-sm p-4 md:p-8 pointer-events-auto">
          <div style={sketchyShape2} className="bg-cream border-4 border-ink shadow-[16px_16px_0px_0px_rgba(26,26,26,1)] w-full max-w-5xl h-[80vh] flex flex-row relative">
            <div className="absolute -top-4 left-1/4 w-32 h-10 bg-terracotta/60 border-2 border-ink rotate-2 z-50 pointer-events-none" style={sketchyShape1}></div>
            <button onClick={() => setIsConfigOpen(false)} className="absolute top-4 right-6 hover:rotate-90 hover:text-terracotta transition-all z-10 p-2 bg-paper border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape3}><X size={28} strokeWidth={4} /></button>
            <div className="w-56 shrink-0 border-r-4 border-ink/20 flex flex-col p-6">
              <div className="pb-6 flex items-center gap-4">
                <FileJson size={36} strokeWidth={2.5} className="text-terracotta" />
                <h2 className="text-xl font-black tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CONFIG</h2>
              </div>
              <div className="flex flex-col gap-4">
                {CONFIG_TABS.map((tab, idx) => (
                  <button key={tab} onClick={() => setActiveTab(tab)} style={idx % 3 === 0 ? sketchyShape1 : idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`px-4 py-2.5 font-black text-base border-4 border-ink uppercase tracking-wider transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] ${activeTab === tab ? 'bg-[#EBCB8B] text-ink -translate-x-1' : 'bg-paper text-ink/70 hover:bg-sand'} ${idx % 2 === 0 ? 'rotate-1' : '-rotate-1'}`}>
                    {tab}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-8 flex flex-col gap-6">
              {Object.keys(configData).length === 0 ? <div className="text-center font-bold text-ink/40 mt-10 text-xl">No data found or Loading...</div> : (
                Object.keys(configData).map((key, idx) => {
                  const isExpanded = expandedKey === key;
                  return (
                    <div key={key} className="flex flex-col gap-2">
                      <button onClick={() => toggleKey(key)} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape1} className={`w-full text-left p-4 border-4 border-ink flex justify-between items-center transition-all ${isExpanded ? 'bg-ink text-paper shadow-none' : 'bg-paper text-ink shadow-[6px_6px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}>
                        <div className="flex items-center gap-3"><FileJson size={20} strokeWidth={2.5} className={isExpanded ? 'text-terracotta' : 'text-[#EBCB8B]'} /><span className="text-xl font-black">{key}</span></div>
                        <span className="font-bold opacity-50 text-sm">{isExpanded ? 'CLOSE' : 'EDIT'}</span>
                      </button>
                      {isExpanded && (
                        <div style={sketchyShape3} className="bg-paper border-4 border-ink p-4 flex flex-col gap-4 shadow-[inset_4px_4px_0px_0px_rgba(26,26,26,0.1)]">
                          <div className="flex items-center gap-2 text-ink/60 font-bold text-xs bg-terracotta/10 p-2 border-2 border-ink border-dashed" style={sketchyShape1}><AlertCircle size={14} strokeWidth={3} />注意：请严格遵守 JSON 格式</div>
                          <textarea value={editJsonStr} onChange={(e) => setEditJsonStr(e.target.value)} className="w-full h-48 bg-[#FDF8F0] border-4 border-ink p-4 font-mono text-sm font-bold focus:outline-none resize-y" spellCheck={false} />
                          <div className="flex justify-end">
                            <button onClick={() => handleSaveConfig(key)} style={sketchyShape1} className="px-6 py-2 bg-[#a3be8c] border-4 border-ink text-ink font-black text-lg flex items-center gap-2 shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] rotate-1"><Save size={20} strokeWidth={3} /> SAVE TO DISK</button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {showSessionModal && (
        <div className="fixed inset-0 bg-ink/40 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div style={sketchyShape2} className="bg-paper border-4 border-ink p-8 flex flex-col gap-6 shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] rotate-1 max-w-2xl w-full h-[80vh]">
            <div className="flex justify-between items-center border-b-4 border-ink/20 pb-4 shrink-0">
              <h3 className="text-3xl font-black tracking-widest text-ink" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SWITCH CHAT</h3>
              <div className="flex items-center gap-4">
                 <button onClick={() => {
                   if (isAgentThinking) { setShowBusyModal(true); return; }
                   if (!currentSessionId) { return; }
                   const currentName = sessions.find((s: any) => s.id === currentSessionId)?.alias || 'Current Chat';
                   setBranchAlias(`${currentName} (Branch)`); setShowSessionModal(false); setShowBranchModal(true);
                 }} className="p-2 bg-cream border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape1} title="Branch (Fork) Current Chat"><GitFork size={24} strokeWidth={3}/></button>
                 <button onClick={() => { 
                   if (isAgentThinking) { setShowBusyModal(true); return; }
                   setShowSessionModal(false); setNewAlias('New Chat'); setShowModal(true); 
                 }} className="p-2 bg-terracotta text-paper border-4 border-ink shadow-[2px_2px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape3} title="New Chat"><Plus size={24} strokeWidth={3}/></button>
                 <div className="w-1 h-8 bg-ink/20 mx-1 rounded-full"></div>
                 <button onClick={() => setShowSessionModal(false)} className="p-2 hover:text-terracotta hover:scale-110 transition-all"><X size={32} strokeWidth={3}/></button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto flex flex-col gap-5 p-3">
                {sessions.map((session: any, idx: number) => (
                  <button key={session.id} onClick={() => { if (isAgentThinking && currentSessionId !== session.id) { setShowBusyModal(true); return; } handleSelectSession(session.id); setShowSessionModal(false); }} style={idx % 2 === 0 ? sketchyShape2 : sketchyShape3} className={`text-left p-4 border-4 transition-all flex flex-col gap-2 relative group ${idx % 3 === 0 ? 'rotate-1' : idx % 2 === 0 ? '-rotate-1' : 'rotate-2'} ${currentSessionId === session.id ? 'bg-[#EBCB8B] border-ink text-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] scale-[1.02] z-10' : 'bg-cream border-ink text-ink hover:bg-sand hover:shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:-translate-y-1'}`}>
                    <div className="flex items-start justify-between gap-2">
                      {editingSessionId === session.id ? (
                        <input autoFocus value={editingAlias} onChange={e => setEditingAlias(e.target.value)} onKeyDown={e => { if(e.key === 'Enter') handleRename(session.id); }} onBlur={() => handleRename(session.id)} onClick={e => e.stopPropagation()} className="font-black max-w-[320px] text-xl bg-[#FDF8F0] border-2 border-ink px-1 focus:outline-none" style={{ fontFamily: '"Comic Sans MS", cursive', ...sketchyShape3 }} />
                      ) : (
                        <span className="font-black truncate max-w-[320px] text-xl" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{session.alias}</span>
                      )}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <div onClick={(e) => { e.stopPropagation(); setEditingAlias(session.alias); setEditingSessionId(session.id); }} className="p-1.5 hover:text-ink hover:bg-[#EBCB8B] rounded transition-colors" title="Rename Chat"><Pencil size={18} strokeWidth={2.5} className="opacity-70" /></div>
                        <div onClick={(e) => { e.stopPropagation(); setSessionToDelete(session.id); setShowSessionModal(false); }} className="p-1.5 hover:text-paper hover:bg-[#bf616a] rounded transition-colors" title="Delete Chat"><Trash2 size={20} strokeWidth={2.5} className={currentSessionId === session.id ? 'opacity-100' : 'opacity-40'} /></div>
                      </div>
                    </div>
                    <div className={`flex items-center gap-3 text-sm font-bold opacity-70`}><Clock size={16} strokeWidth={3} /> {session.updated_at}</div>
                  </button>
                ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}