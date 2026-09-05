import { useState, useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { useFlowStore } from '../store/flowStore'
import { Trash2, CheckCircle, FileJson, Upload, ArrowLeft, FolderOpen, X, Plus } from 'lucide-react'
import { toast } from 'react-hot-toast'
import type { AgentLoopEditorHandle } from './AgentLoopEditor'

interface GraphFile { name: string; path: string }
interface ParadigmFile { name: string; is_default: boolean }

const sketchyShape1 = { borderRadius: '255px 15px 225px 15px/15px 225px 15px 255px' };
const sketchyShape2 = { borderRadius: '15px 225px 15px 255px/255px 15px 225px 15px' };
const sketchyShape3 = { borderRadius: '225px 15px 255px 15px/15px 255px 15px 225px' };

export type EditorViewMode = 'workflow' | 'agent_loop'

interface ToolbarProps {
  onBack?: () => void
  mode?: EditorViewMode
  onModeChange?: (mode: EditorViewMode) => void
  agentLoop?: {
    ref: RefObject<AgentLoopEditorHandle | null>
    active: string
    dirty: boolean
  }
}

export default function Toolbar({ onBack, mode = 'workflow', onModeChange, agentLoop }: ToolbarProps) {
  const { exportGraph, validateGraph, clearGraph, loadGraph } = useFlowStore()

  // Open 菜单状态
  const [showFileMenu, setShowFileMenu] = useState(false)
  const [graphFiles, setGraphFiles] = useState<GraphFile[]>([])
  const [paradigmFiles, setParadigmFiles] = useState<ParadigmFile[]>([])
  const menuRef = useRef<HTMLDivElement>(null)

  // 部署弹窗状态
  const [isDeployModalOpen, setIsDeployModalOpen] = useState(false)
  const [workflowName, setWorkflowName] = useState('my_awesome_flow')
  const [workflowDescription, setWorkflowDescription] = useState('')

  // 退出弹窗状态
  const [isExitModalOpen, setIsExitModalOpen] = useState(false)

  // 清空画布确认弹窗状态
  const [isClearModalOpen, setIsClearModalOpen] = useState(false)
  // 删除 paradigm 确认（涂鸦风格弹窗）
  const [paradigmToDelete, setParadigmToDelete] = useState<string | null>(null)

  // 点击外部关闭 Open 菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowFileMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 加载已有图谱列表
  const loadGraphList = async () => {
    try {
      const res = await fetch('/api/graphs')
      if (res.ok) {
        const data = await res.json()
        setGraphFiles(data)
      }
    } catch {
      toast.error("获取图谱列表失败")
    }
  }

  // 加载 paradigm 文件列表
  const loadParadigmList = async () => {
    try {
      const res = await fetch('/api/paradigms')
      if (!res.ok) throw new Error("获取失败")
      const data = await res.json()
      setParadigmFiles(data.files ?? [])
    } catch {
      toast.error("获取 paradigm 列表失败")
    }
  }

  const handleToggleMenu = async () => {
    if (!showFileMenu) {
      if (mode === 'agent_loop') await loadParadigmList()
      else await loadGraphList()
    }
    setShowFileMenu(!showFileMenu)
  }

  // 加载选中的图谱
  const handleEditExisting = async (fileName: string) => {
    try {
      const res = await fetch(`/api/graphs/${fileName}`)
      if (res.ok) {
        const data = await res.json()
        loadGraph(data)
        setWorkflowName(fileName.replace(/\.json$/, ''))
        setWorkflowDescription(data.description || '')
        toast.success(`已加载: ${fileName}`)
        setShowFileMenu(false)
      }
    } catch {
      toast.error("加载图谱失败")
    }
  }

  // Agent Loop：通过 ref 调用 AgentLoopEditor 的打开/新建/删除/保存
  const openParadigm = (name: string) => {
    setShowFileMenu(false)
    void agentLoop?.ref.current?.openFile(name)
  }
  const createParadigm = () => {
    setShowFileMenu(false)
    agentLoop?.ref.current?.create()
  }
  const deleteParadigm = async (name: string) => {
    const handle = agentLoop?.ref.current
    if (!handle) return
    await handle.deleteFile(name)
    await loadParadigmList()
    setParadigmToDelete(null)
  }
  const saveParadigm = () => {
    void agentLoop?.ref.current?.save()
  }

  // 校验画布
  const handleValidate = () => {
    const errors = validateGraph()
    if (errors.length > 0) {
      errors.forEach((e) => toast.error(e))
    } else {
      toast.success('校验通过！工作流结构合法。')
    }
  }

  // 🌟 真实执行部署保存逻辑 (增加依赖项扫描与去重)
  const handleRealDeploy = async () => {
    const errors = validateGraph()
    if (errors.length > 0) {
      errors.forEach(e => toast.error(e))
      return
    }

    // 1. 获取基础导出图谱数据
    const graph = exportGraph(workflowName, workflowDescription)
    
    // 2. 扫描图中所有节点，提取技能与MCP依赖并利用 Set 去重
    const skillSet = new Set<string>();
    const mcpSet = new Set<string>();

    if (graph.nodes && Array.isArray(graph.nodes)) {
      graph.nodes.forEach((node: any) => {
        // 提取 skill_info 节点中的 skills
        if (node.type === 'skill_info' && Array.isArray(node.config?.skills_list)) {
          node.config.skills_list.forEach((item: any) => {
            if (item && item.name) skillSet.add(item.name);
          });
        }
        // 提取 mcp_info 节点中的 mcp servers
        if (node.type === 'mcp_info' && Array.isArray(node.config?.mcp_servers)) {
          node.config.mcp_servers.forEach((item: any) => {
            if (item && item.name) mcpSet.add(item.name);
          });
        }
      });
    }

    // 3. 将扫描到的依赖注入到 graph 对象中
    graph.dependencies = {
      skills: Array.from(skillSet),
      mcps: Array.from(mcpSet)
    };

    // 4. 提交带有依赖声明的 JSON 数据到后端
    try {
      const res = await fetch(`/api/graphs/${workflowName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(graph),
      })
      if (res.ok) {
        toast.success(`部署成功: ${workflowName}`)
        setIsDeployModalOpen(false)
      }
    } catch { toast.error("部署失败") }
  }

  return (
    <>
      {/* 顶部导航容器 */}
      <div className="w-full flex items-start justify-between relative z-50 pointer-events-none">
        
        {/* === 左侧区域 === */}
        <div 
          style={sketchyShape3}
          className="pointer-events-auto bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] px-8 py-5 flex items-center gap-8 -rotate-1 relative"
        >
          <div className="absolute top-2 left-1/2 -translate-x-1/2 w-12 h-4 bg-terracotta/30 border-2 border-ink rotate-3" style={sketchyShape1}></div>

          {onBack && (
            <button
              onClick={() => {
                if (useFlowStore.getState().nodes.length > 0) {
                  setIsExitModalOpen(true);
                } else {
                  onBack();
                }
              }}
              style={sketchyShape2}
              className="flex items-center justify-center p-3 bg-cream border-4 border-ink text-ink font-black hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:translate-y-[2px] active:shadow-none rotate-2 hover:-rotate-1"
            >
              <ArrowLeft size={24} strokeWidth={3} />
            </button>
          )}
          {onModeChange ? (
            <div className="flex items-center gap-2">
              {/* 视图切换：Workflow / Agent Loop */}
              <div className="flex items-center p-1 bg-cream border-4 border-ink shadow-[4px_4px_0px_0px_rgba(26,26,26,1)]" style={sketchyShape2}>
                {(['workflow', 'agent_loop'] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => onModeChange(m)}
                    style={sketchyShape1}
                    className={`px-5 py-2 text-lg tracking-widest font-black transition-all ${
                      mode === m ? 'bg-ink text-paper' : 'text-ink hover:bg-sand'
                    }`}
                  >
                    {m === 'workflow' ? 'WORKFLOW' : 'AGENT LOOP'}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-4">
              <h1 className="text-3xl font-black text-ink tracking-widest mt-1" style={{ fontFamily: '"Comic Sans MS", cursive' }}>WORKFLOW</h1>
            </div>
          )}
        </div>

        {/* === 右侧区域 (仅 Workflow 模式下显示) === */}
        {mode === 'workflow' && (
        <div 
          style={sketchyShape1}
          className="pointer-events-auto bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] px-8 py-5 flex items-center gap-6 rotate-1 relative"
        >
          <div className="absolute -top-3 right-6 w-16 h-6 bg-[#EBCB8B]/80 border-2 border-ink -rotate-3" style={sketchyShape2}></div>

          {/* OPEN 按钮与下拉菜单 */}
          <div className="relative" ref={menuRef}>
            <button onClick={handleToggleMenu} style={sketchyShape1} className="flex items-center gap-3 px-6 py-3 bg-cream border-4 border-ink text-ink font-black hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 -rotate-2 hover:rotate-0">
              <FolderOpen size={22} strokeWidth={2.5} />
              <span className="text-lg tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>OPEN</span>
            </button>

            {showFileMenu && (
              <div style={sketchyShape2} className="absolute right-0 top-full mt-6 w-72 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] z-50 overflow-hidden rotate-2">
                <div className="p-4 border-b-4 border-ink bg-terracotta/10 font-black text-ink tracking-widest text-center text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SAVED GRAPHS</div>
                <div className="max-h-72 overflow-y-auto p-3 flex flex-col gap-2">
                  {graphFiles.length === 0 ? (
                    <div className="p-4 text-center font-bold text-ink/50" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Nothing here</div>
                  ) : (
                    graphFiles.map((file, idx) => (
                      <button key={file.name} onClick={() => handleEditExisting(file.name)} style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3} className="w-full flex items-center gap-3 p-4 text-left border-4 border-transparent hover:border-ink hover:bg-cream transition-all group font-bold">
                        <FileJson size={20} strokeWidth={2.5} className="text-terracotta" />
                        <span className="truncate text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{file.name}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 校验按钮 */}
          <button onClick={handleValidate} style={sketchyShape3} className="flex items-center justify-center p-3 bg-cream border-4 border-ink text-ink font-black hover:bg-[#a3be8c] transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 rotate-2" title="Validate">
            <CheckCircle size={24} strokeWidth={2.5} />
          </button>

          {/* 清空按钮 */}
          <button onClick={() => setIsClearModalOpen(true)} style={sketchyShape2} className="flex items-center justify-center p-3 bg-cream border-4 border-ink text-ink font-black hover:bg-[#bf616a] hover:text-paper transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 -rotate-3" title="Clear Canvas">
            <Trash2 size={24} strokeWidth={2.5} />
          </button>

          {/* 部署按钮 (唤起弹窗) */}
          <button onClick={() => setIsDeployModalOpen(true)} style={sketchyShape1} className="flex items-center gap-3 px-8 py-3 bg-ink text-paper border-4 border-ink hover:bg-gray-800 transition-all shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] active:shadow-none active:translate-y-1 rotate-1 ml-4">
            <Upload size={22} strokeWidth={2.5} />
            <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DEPLOY</span>
          </button>
        </div>
        )}

        {/* === 右侧区域（Agent Loop：OPEN / DEPLOY，与 Workflow 排版一致） === */}
        {mode === 'agent_loop' && agentLoop && (
          <div
            style={sketchyShape1}
            className="pointer-events-auto bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] px-8 py-5 flex items-center gap-6 rotate-1 relative"
          >
            <div className="absolute -top-3 right-6 w-16 h-6 bg-[#EBCB8B]/80 border-2 border-ink -rotate-3" style={sketchyShape2}></div>

            {/* 当前文件 + 脏标记 */}
            <div className="hidden 2xl:flex flex-col items-start gap-0.5 pr-4 border-r-4 border-ink">
              <span className="text-[11px] font-black text-ink/40 tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>FILE</span>
              <span className="flex items-center gap-2 text-lg font-black text-ink max-w-[220px] truncate" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                {agentLoop.active ? `${agentLoop.active}.yaml` : '—'}
                {agentLoop.dirty && <span className="inline-block w-2.5 h-2.5 shrink-0 rounded-full bg-[#D47A5A] border-2 border-ink" title="有未保存修改" />}
              </span>
            </div>

            {/* OPEN 按钮与下拉菜单 */}
            <div className="relative" ref={menuRef}>
              <button onClick={handleToggleMenu} style={sketchyShape1} className="flex items-center gap-3 px-6 py-3 bg-cream border-4 border-ink text-ink font-black hover:bg-sand transition-all shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] active:shadow-none active:translate-y-1 -rotate-2 hover:rotate-0">
                <FolderOpen size={22} strokeWidth={2.5} />
                <span className="text-lg tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>OPEN</span>
              </button>

              {showFileMenu && (
                <div style={sketchyShape2} className="absolute right-0 top-full mt-6 w-80 bg-paper border-4 border-ink shadow-[8px_8px_0px_0px_rgba(26,26,26,1)] z-50 overflow-hidden rotate-2">
                  <div className="p-4 border-b-4 border-ink bg-terracotta/10 font-black text-ink tracking-widest text-center text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>PARADIGMS</div>
                  <div className="max-h-80 overflow-y-auto p-3 flex flex-col gap-2">
                    <button onClick={createParadigm} style={sketchyShape3} className="w-full flex items-center gap-3 p-3 text-left border-4 border-ink bg-cream hover:bg-sand transition-all font-black text-ink">
                      <Plus size={18} strokeWidth={3} className="text-terracotta" />
                      <span className="text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>新建 Paradigm…</span>
                    </button>
                    {paradigmFiles.length === 0 ? (
                      <div className="p-4 text-center font-bold text-ink/50" style={{ fontFamily: '"Comic Sans MS", cursive' }}>Nothing here</div>
                    ) : (
                      paradigmFiles.map((f, idx) => (
                        <div key={f.name} className="flex items-stretch gap-1">
                          <button
                            onClick={() => openParadigm(f.name)}
                            style={idx % 2 === 0 ? sketchyShape1 : sketchyShape3}
                            className={`flex-1 min-w-0 flex items-center gap-2 p-3 text-left border-4 transition-all group font-bold ${
                              agentLoop.active === f.name ? 'border-ink bg-cream' : 'border-transparent hover:border-ink hover:bg-cream'
                            }`}
                          >
                            <span className="w-3 h-3 shrink-0 border-2 border-ink inline-block" style={{ background: f.is_default ? '#EBCB8B' : '#BFDCF5' }} />
                            <span className="truncate text-lg" style={{ fontFamily: '"Comic Sans MS", cursive' }}>{f.name}</span>
                            <span className="shrink-0 text-xs font-black text-ink/40">{f.is_default ? '默认' : ''}{agentLoop.active === f.name ? '·当前' : ''}</span>
                          </button>
                          {!f.is_default && (
                            <button
                              title={`删除 ${f.name}`}
                              onClick={() => {
                                setShowFileMenu(false)
                                setParadigmToDelete(f.name)
                              }}
                              style={sketchyShape2}
                              className="shrink-0 flex items-center justify-center px-2 bg-cream border-4 border-ink text-ink/50 hover:text-paper hover:bg-[#bf616a] transition-colors"
                            >
                              <Trash2 size={16} strokeWidth={2.5} />
                            </button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* 部署按钮（保存当前 Paradigm） */}
            <button
              onClick={saveParadigm}
              style={sketchyShape1}
              className="flex items-center gap-3 px-8 py-3 bg-ink text-paper border-4 border-ink hover:bg-gray-800 transition-all shadow-[6px_6px_0px_0px_rgba(212,122,90,1)] active:shadow-none active:translate-y-1 rotate-1 ml-4"
              title={agentLoop.active ? `保存 ${agentLoop.active}.yaml` : '保存当前 Paradigm'}
            >
              <Upload size={22} strokeWidth={2.5} />
              <span className="tracking-widest text-lg font-black" style={{ fontFamily: '"Comic Sans MS", cursive' }}>
                {agentLoop.dirty ? 'DEPLOY*' : 'DEPLOY'}
              </span>
            </button>
          </div>
        )}
      </div>

      {/* === 部署手绘风弹窗 (Modal) === */}
      {isDeployModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape1} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-md p-8 relative rotate-1">
            <button onClick={() => setIsDeployModalOpen(false)} className="absolute top-4 right-4 hover:rotate-90 transition-transform">
              <X size={32} strokeWidth={3} />
            </button>
            <h3 className="text-3xl font-black mb-6 tracking-widest" style={{ fontFamily: '"Comic Sans MS", cursive' }}>SAVE WORKFLOW</h3>
            <p className="font-bold mb-2 opacity-60">Give your cat-powered graph a name:</p>
            <input 
              value={workflowName} onChange={e => setWorkflowName(e.target.value)}
              style={sketchyShape2} className="w-full bg-cream border-4 border-ink p-4 text-xl font-bold mb-4 focus:outline-none"
              placeholder="e.g. data_pipeline"
            />
            <p className="font-bold mb-2 opacity-60">Add a description (optional):</p>
            <textarea 
              value={workflowDescription} onChange={e => setWorkflowDescription(e.target.value)}
              style={sketchyShape1} className="w-full bg-cream border-4 border-ink p-4 text-lg font-bold mb-8 focus:outline-none resize-none h-24"
              placeholder="Describe what this workflow does..."
            />
            <div className="flex gap-4">
              <button onClick={handleRealDeploy} style={sketchyShape1} className="flex-1 py-4 bg-terracotta text-paper border-4 border-ink font-black text-xl shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:translate-y-1 hover:shadow-none transition-all">
                CONFIRM DEPLOY
              </button>
            </div>
          </div>
        </div>
      )}

      {/* === 退出确认弹窗 === */}
      {isExitModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape3} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-sm p-8 relative -rotate-1">
            <h3 className="text-2xl font-black mb-4 tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>WAIT A MINUTE!</h3>
            <p className="font-bold mb-6 opacity-80 text-lg">
              画布上还有未部署的节点。直接返回可能会丢失进度（尽管浏览器缓存通常会保留）。确定要退出编辑器吗？
            </p>
            <div className="flex gap-4">
              <button onClick={() => setIsExitModalOpen(false)} style={sketchyShape1} className="flex-1 py-3 bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand">
                STAY
              </button>
              <button onClick={() => { setIsExitModalOpen(false); onBack?.(); }} style={sketchyShape2} className="flex-1 py-3 bg-[#bf616a] text-paper border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-red-500">
                LEAVE
              </button>
            </div>
          </div>
        </div>
      )}

      {/* === 清空画布确认弹窗 === */}
      {isClearModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape3} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-sm p-8 relative -rotate-1">
            <h3 className="text-2xl font-black mb-4 tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>CLEAR CANVAS?</h3>
            <p className="font-bold mb-6 opacity-80 text-lg">
              确定要清空画布吗？当前画板上未部署的内容将永远丢失！
            </p>
            <div className="flex gap-4">
              <button onClick={() => setIsClearModalOpen(false)} style={sketchyShape1} className="flex-1 py-3 bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all">
                CANCEL
              </button>
              <button onClick={() => { clearGraph(); setIsClearModalOpen(false); }} style={sketchyShape2} className="flex-1 py-3 bg-[#bf616a] text-paper border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-red-500 transition-all">
                CLEAR
              </button>
            </div>
          </div>
        </div>
      )}

      {/* === 删除 Paradigm 确认弹窗（涂鸦风格） === */}
      {paradigmToDelete && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4 pointer-events-auto">
          <div style={sketchyShape3} className="bg-paper border-4 border-ink shadow-[12px_12px_0px_0px_rgba(26,26,26,1)] w-full max-w-sm p-8 relative -rotate-1">
            <h3 className="text-2xl font-black mb-4 tracking-widest text-[#bf616a]" style={{ fontFamily: '"Comic Sans MS", cursive' }}>DELETE PARADIGM?</h3>
            <p className="font-bold mb-6 opacity-80 text-lg">
              确定要删除 paradigm「{paradigmToDelete}」？该操作不可恢复！
            </p>
            <div className="flex gap-4">
              <button onClick={() => setParadigmToDelete(null)} style={sketchyShape1} className="flex-1 py-3 bg-cream text-ink border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-sand transition-all">
                CANCEL
              </button>
              <button
                onClick={() => void deleteParadigm(paradigmToDelete)}
                style={sketchyShape2}
                className="flex-1 py-3 bg-[#bf616a] text-paper border-4 border-ink font-black shadow-[4px_4px_0px_0px_rgba(26,26,26,1)] hover:bg-red-500 transition-all"
              >
                DELETE
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}