'use client'

import React, { useState, useEffect, useRef } from 'react'
import {
  Puzzle,
  Settings2,
  Wrench,
  Cpu,
  Plus,
  Trash2,
  Save,
  BookOpen,
  Server,
  Code,
  Loader2,
  Info,
  UploadCloud,
  FileJson
} from 'lucide-react'
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useToast } from "@/hooks/use-toast"
import { cn } from '@/lib/utils'

const API_BASE = 'http://localhost:8001/api'

type TabKey = 'model' | 'mcp' | 'local' | 'skill' | 'soul'

// 辅助组件：处理模型对象Key重命名时输入框脱焦问题
function EditableKeyInput({
  initialKey,
  onRename
}: {
  initialKey: string,
  onRename: (oldKey: string, newKey: string) => void
}) {
  const [val, setVal] = useState(initialKey)

  useEffect(() => { setVal(initialKey) }, [initialKey])

  return (
    <Input
      value={val}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => {
        if (val !== initialKey && val.trim() !== '') {
          onRename(initialKey, val.trim())
        } else {
          setVal(initialKey)
        }
      }}
      className="h-9 text-sm font-mono font-bold text-primary border-primary/20 bg-background"
    />
  )
}

export default function ExtensionPage() {
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<TabKey>('model')

  // States
  const [llmModels, setLlmModels] = useState<Record<string, any>>({})
  const [specializedModels, setSpecializedModels] = useState<Record<string, any>>({})
  const [mcpServers, setMcpServers] = useState<Record<string, any>>({})
  const [plugins, setPlugins] = useState<any[]>([])
  const [skills, setSkills] = useState<any[]>([])
  const [soulContent, setSoulContent] = useState("")
  const [toolsMap, setToolsMap] = useState<Record<string, any[]>>({})

  const [selectedPlugin, setSelectedPlugin] = useState<any>(null)
  const [isPluginDialogOpen, setIsPluginDialogOpen] = useState(false)

  // MCP JSON Import State
  const [isMcpJsonDialogOpen, setIsMcpJsonDialogOpen] = useState(false)
  const [mcpJsonInput, setMcpJsonInput] = useState("")

  // Drag and Drop States
  const [isDragging, setIsDragging] = useState(false)
  const dragCounter = useRef(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [configRes, pluginsRes, skillsRes, soulRes, toolsRes] = await Promise.all([
        fetch(`${API_BASE}/config`),
        fetch(`${API_BASE}/plugins`),
        fetch(`${API_BASE}/skills`),
        fetch(`${API_BASE}/files?path=soul`),
        fetch(`${API_BASE}/tools`)
      ])

      const configData = await configRes.json()
      const modelConfig = configData['model_config.json'] || {}
      setLlmModels(modelConfig.models || {})

      const specKeys = ["image_generator", "image_converter", "video_generator", "audio_generator", "audio_converter", "video_converter"]
      const specModels: Record<string, any> = {}
      specKeys.forEach(k => { if (modelConfig[k]) specModels[k] = modelConfig[k] })
      setSpecializedModels(specModels)

      const mcpConfig = configData['mcp_config.json'] || {}
      const servers = mcpConfig.mcpServers || {}
      setMcpServers(servers)

      setPlugins(await pluginsRes.json())
      setSkills(await skillsRes.json())

      const soulData = await soulRes.json()
      setSoulContent(soulData.content || "")

      const toolsData = await toolsRes.json()
      const tMap: Record<string, any[]> = {}
      toolsData.forEach((p: any) => {
        tMap[p.name] = p.tools
      })
      setToolsMap(tMap)

    } catch (error) {
      toast({ title: "加载失败", description: "无法连接到后端服务器", variant: "destructive" })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  // Action Handlers
  const handleSaveModels = async () => {
    try {
      await fetch(`${API_BASE}/config/model_config.json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ models: llmModels, ...specializedModels })
      })
      toast({ title: "保存成功", description: "模型配置已更新" })
    } catch (e) { toast({ title: "保存失败", variant: "destructive" }) }
  }

  const handleSaveMcp = async () => {
    try {
      // 因为 MCP 取消了单点编辑，直接发送 mcpServers 整体即可
      await fetch(`${API_BASE}/config/mcp_config.json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mcpServers })
      })
      toast({ title: "保存成功", description: "MCP 注册表已更新" })
    } catch (e) { toast({ title: "保存失败", variant: "destructive" }) }
  }

  const handleSaveSoul = async () => {
    try {
      await fetch(`${API_BASE}/files?path=soul`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: soulContent })
      })
      toast({ title: "SOUL.md 已保存", description: "Agent 核心人格已更新" })
    } catch (e) { toast({ title: "保存失败", variant: "destructive" }) }
  }

  const handleCurrentSave = () => {
    if (activeTab === 'model') handleSaveModels()
    else if (activeTab === 'mcp') handleSaveMcp()
    else if (activeTab === 'soul') handleSaveSoul()
    else toast({ title: "无需保存", description: "该页面的修改已实时生效" })
  }

  const handleTogglePlugin = async (name: string) => {
    try {
      const res = await fetch(`${API_BASE}/plugins/${name}/toggle`, { method: 'POST' })
      const data = await res.json()
      setPlugins(plugins.map(p => p.name === name ? { ...p, enabled: data.enabled } : p))
      toast({ title: "插件状态已更新", description: `${name} 当前状态: ${data.enabled ? '启用' : '禁用'}` })
    } catch (e) { toast({ title: "切换失败", variant: "destructive" }) }
  }

  // LLM Rename Logic
  const handleRenameLlmModel = (oldId: string, newId: string) => {
    if (llmModels[newId]) {
      toast({ title: "重命名失败", description: "该模型标识已存在", variant: "destructive" })
      return
    }
    setLlmModels(prev => {
      const next = { ...prev };
      next[newId] = next[oldId];
      delete next[oldId];
      return next;
    })
  }

  const updateLlmModel = (id: string, field: string, value: string) => setLlmModels(prev => ({ ...prev, [id]: { ...prev[id], [field]: value } }))
  const updateSpecModel = (type: string, field: string, value: string) => setSpecializedModels(prev => ({ ...prev, [type]: { ...prev[type], [field]: value } }))

  // --- MCP JSON Import Logic ---
  const handleImportMcpJson = () => {
    try {
      let cleaned = mcpJsonInput.replace(/,\s*([\]}])/g, '$1')
      let parsed = JSON.parse(cleaned)

      if (parsed.mcpServers && typeof parsed.mcpServers === 'object') {
        parsed = parsed.mcpServers
      }

      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error("JSON 格式不是一个有效的对象")
      }

      const newServers = { ...mcpServers }

      Object.entries(parsed).forEach(([key, val]: [string, any]) => {
        newServers[key] = {
          command: val.command || 'npx',
          args: val.args || [],
          env: val.env || {}
        }
      })

      setMcpServers(newServers)
      setIsMcpJsonDialogOpen(false)
      setMcpJsonInput("")
      toast({ title: "解析成功", description: `已成功导入 MCP 列表（点击右下角保存生效）` })
    } catch (error: any) {
      toast({ title: "解析失败", description: error.message || "JSON 格式有误", variant: "destructive" })
    }
  }

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    if (activeTab === 'local' || activeTab === 'skill') {
      dragCounter.current += 1
      if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
        setIsDragging(true)
      }
    }
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    if (activeTab === 'local' || activeTab === 'skill') {
      dragCounter.current -= 1
      if (dragCounter.current === 0) setIsDragging(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    dragCounter.current = 0

    if (activeTab !== 'local' && activeTab !== 'skill') return

    const items = e.dataTransfer.items
    if (!items) return

    const filesToUpload: { file: File, path: string }[] = []

    const traverseFileTree = async (item: any, path: string) => {
      if (item.isFile) {
        const file = await new Promise<File>((resolve) => item.file(resolve))
        filesToUpload.push({ file, path })
      } else if (item.isDirectory) {
        const dirReader = item.createReader()
        const entries = await new Promise<any[]>((resolve) => {
          dirReader.readEntries(resolve)
        })
        for (const entry of entries) {
          await traverseFileTree(entry, path + '/' + entry.name)
        }
      }
    }

    try {
      for (let i = 0; i < items.length; i++) {
        const item = items[i].webkitGetAsEntry()
        if (item) {
          await traverseFileTree(item, item.name)
        }
      }

      if (filesToUpload.length === 0) return

      const formData = new FormData()
      filesToUpload.forEach(({ file, path }) => {
        formData.append('files', file, path)
      })

      const targetEndpoint = activeTab === 'local' ? 'plugins' : 'skills'

      toast({ title: "正在安装...", description: `正在上传 ${filesToUpload.length} 个文件` })

      const res = await fetch(`${API_BASE}/${targetEndpoint}/upload`, {
        method: 'POST',
        body: formData,
      })

      if (res.ok) {
        toast({ title: "安装成功", description: `已成功将文件夹导入 ${targetEndpoint}` })
        fetchData()
      } else {
        throw new Error("后端响应错误")
      }
    } catch (err) {
      toast({ title: "安装失败", description: "上传文件时出错或后端未实现该接口", variant: "destructive" })
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full absolute inset-0 bg-background"><Loader2 className="size-8 animate-spin text-muted-foreground" /></div>
  }

  const tabsConfig = [
    { id: 'model', label: '模型配置', icon: Settings2 },
    { id: 'mcp', label: 'MCP 服务器', icon: Cpu },
    { id: 'local', label: '本地插件', icon: Puzzle },
    { id: 'skill', label: '技能目录', icon: Wrench },
    { id: 'soul', label: 'SOUL.md', icon: BookOpen },
  ] as const

  return (
    <div className="absolute inset-0 flex flex-col w-full bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">

        {/* 左侧：导航栏面板 */}
        <ResizablePanel
          defaultSize={20}
          minSize={15}
          maxSize={30}
          className="border-r border-border/10 bg-muted/10 z-20 flex flex-col"
        >
          <div className="h-20 px-6 flex flex-col justify-center border-b border-border/10 shrink-0 bg-background/50 backdrop-blur-sm shadow-[0_2px_10px_rgba(0,0,0,0.02)]">
            <h1 className="font-bold text-lg tracking-tight">Extensions</h1>
            <p className="text-xs text-muted-foreground">全局扩展与核心配置</p>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-1">
              {tabsConfig.map((tab) => {
                const Icon = tab.icon
                const isActive = activeTab === tab.id
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as TabKey)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-200 font-medium",
                      isActive
                        ? "bg-muted text-foreground shadow-md"
                        : "text-muted-foreground hover:bg-background hover:text-foreground hover:shadow-sm"
                    )}
                  >
                    <Icon className="size-4" />
                    {tab.label}
                  </button>
                )
              })}
            </div>
          </ScrollArea>
        </ResizablePanel>

        <ResizableHandle className="w-1.5 bg-transparent hover:bg-primary/20 transition-colors cursor-col-resize active:bg-primary/40" />

        {/* 右侧：内容面板 */}
        <ResizablePanel
          defaultSize={80}
          minSize={60}
          className="bg-background relative"
        >
          <div className="absolute top-0 left-0 right-0 z-10 bg-gradient-to-b from-background via-background/90 to-transparent pb-16 pointer-events-none" />

          {isDragging && (activeTab === 'local' || activeTab === 'skill') && (
            <div className="absolute inset-0 z-50 bg-background/80 backdrop-blur-md border-2 border-dashed border-primary rounded-[32px] flex flex-col items-center justify-center m-6 pointer-events-none transition-all duration-200">
              <div className="size-24 rounded-full bg-primary/10 flex items-center justify-center mb-6 animate-pulse shadow-[0_0_40px_rgba(var(--primary),0.2)]">
                <UploadCloud className="size-12 text-primary" />
              </div>
              <h2 className="text-3xl font-bold tracking-tight mb-3">松开鼠标，自动安装{activeTab === 'local' ? '插件' : '技能'}</h2>
              <p className="text-muted-foreground text-lg">支持直接拖入文件夹或文件进行文件级注册</p>
            </div>
          )}

          <div
            ref={scrollContainerRef}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            className="absolute inset-0 overflow-y-auto overflow-x-hidden pt-12 pb-8 scroll-smooth scrollbar-thin scrollbar-thumb-muted-foreground/20 hover:scrollbar-thumb-muted-foreground/40 scrollbar-track-transparent"
          >
            <div className="max-w-5xl mx-auto w-full px-6 md:px-12 pb-48 h-full flex flex-col">

              {/* ====== 模型配置 ====== */}
              {activeTab === 'model' && (
                <div className="space-y-8 mt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-semibold flex items-center gap-3"><Server className="text-primary size-6"/> LLM 核心模型配置</h2>
                      <p className="text-sm text-muted-foreground mt-1">管理支持标准格式的语言模型接口与密钥</p>
                    </div>
                    <Button variant="outline" className="rounded-full shadow-sm" onClick={() => {
                      const newId = `new_model_${Date.now()}`
                      setLlmModels(prev => ({ ...prev, [newId]: { api_key: "", base_url: "", description: "" } }))
                    }}>
                      <Plus className="size-4 mr-1" /> 添加模型
                    </Button>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {Object.entries(llmModels).map(([id, config]) => (
                      <div key={id} className="p-5 rounded-[20px] border border-border/40 bg-muted/20 hover:bg-muted/40 transition-colors relative group shadow-sm">
                        <button
                          className="absolute right-4 top-4 text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100"
                          onClick={() => { const newModels = { ...llmModels }; delete newModels[id]; setLlmModels(newModels); }}
                        >
                          <Trash2 className="size-4" />
                        </button>
                        <div className="space-y-4 pr-6">
                          <div className="space-y-1.5">
                            <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">模型标识 (Key)</Label>
                            <EditableKeyInput initialKey={id} onRename={handleRenameLlmModel} />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">API Key</Label>
                              <Input type="password" value={config.api_key || ''} onChange={e => updateLlmModel(id, 'api_key', e.target.value)} className="h-9 font-mono text-xs bg-background" />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">Base URL</Label>
                              <Input value={config.base_url || ''} onChange={e => updateLlmModel(id, 'base_url', e.target.value)} className="h-9 font-mono text-xs bg-background" />
                            </div>
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">Description</Label>
                            <Input value={config.description || ''} onChange={e => updateLlmModel(id, 'description', e.target.value)} className="h-9 text-sm bg-background" />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="pt-8 border-t border-border/40">
                    <h2 className="text-2xl font-semibold flex items-center gap-3 mb-4"><Code className="text-purple-500 size-6"/> 专用模型配置 (Specialized)</h2>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {Object.entries(specializedModels).map(([type, config]) => (
                        <div key={type} className="p-5 rounded-[20px] border border-border/40 bg-purple-500/5 hover:bg-purple-500/10 transition-colors space-y-4 shadow-sm">
                          <Badge variant="outline" className="border-purple-500/30 text-purple-600 bg-purple-500/10">{type}</Badge>
                          <div className="space-y-1.5">
                            <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">Model Name</Label>
                            <Input value={config.name || ''} onChange={e => updateSpecModel(type, 'name', e.target.value)} className="h-9 font-mono text-sm bg-background/50" />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">API Key</Label>
                              <Input type="password" value={config.api_key || ''} onChange={e => updateSpecModel(type, 'api_key', e.target.value)} className="h-9 font-mono text-xs bg-background/50" />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">Base URL</Label>
                              <Input value={config.base_url || ''} onChange={e => updateSpecModel(type, 'base_url', e.target.value)} className="h-9 font-mono text-xs bg-background/50" />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="h-24 w-full shrink-0" />
                </div>
              )}

              {/* ====== MCP 服务器 (严格只读，只允许导入和删除) ====== */}
              {activeTab === 'mcp' && (
                <div className="space-y-6 mt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-semibold flex items-center gap-3"><Cpu className="text-primary size-6"/> MCP 服务器注册表</h2>
                      <p className="text-sm text-muted-foreground mt-1">如需修改，请通过整体导入 JSON 来覆盖。</p>
                    </div>
                    <div className="flex gap-2">
                      <Dialog open={isMcpJsonDialogOpen} onOpenChange={setIsMcpJsonDialogOpen}>
                        <DialogTrigger asChild>
                          <Button variant="default" className="rounded-full shadow-md bg-primary text-primary-foreground hover:bg-primary/90">
                            <FileJson className="size-4 mr-2" /> 导入 MCP
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="sm:max-w-[500px] flex flex-col max-h-[85vh]">
                          <DialogHeader className="shrink-0">
                            <DialogTitle>从 JSON 整体导入 MCP 配置</DialogTitle>
                            <DialogDescription>
                              粘贴标准 mcpServers JSON，此操作会彻底覆盖下方的列表配置。
                            </DialogDescription>
                          </DialogHeader>
                          <div className="mt-4 flex-1 min-h-0 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-muted-foreground/20">
                            <Textarea
                              value={mcpJsonInput}
                              onChange={(e) => setMcpJsonInput(e.target.value)}
                              className="font-mono text-xs min-h-[250px] h-full bg-muted/20 focus-visible:ring-0 focus-visible:border-primary/50 focus-visible:outline-none"
                              placeholder={`{\n  "mcpServers": {\n    "sqlite": {\n      "command": "uvx",\n      "args": ["mcp-server-sqlite"]\n    }\n  }\n}`}
                            />
                          </div>
                          <div className="flex justify-end mt-4 shrink-0 pt-2">
                            <Button onClick={handleImportMcpJson}>解析并导入覆盖</Button>
                          </div>
                        </DialogContent>
                      </Dialog>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    {Object.entries(mcpServers).map(([name, config]) => (
                      <div key={name} className="p-5 rounded-[20px] border border-border/40 bg-muted/20 relative group shadow-sm outline-none">
                        <button
                          className="absolute right-4 top-4 text-muted-foreground hover:text-destructive transition-colors opacity-0 group-hover:opacity-100 z-10"
                          onClick={() => { const newServers = { ...mcpServers }; delete newServers[name]; setMcpServers(newServers); }}
                          title="删除该服务"
                        >
                          <Trash2 className="size-4" />
                        </button>
                        <div className="mb-4 flex items-center gap-2 pr-8">
                          <div className="size-2.5 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)] shrink-0" />
                          <h3 className="text-lg font-bold truncate tracking-tight text-foreground">{name}</h3>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                          <div className="md:col-span-1 space-y-1.5">
                            <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">Command</Label>
                            <div className="h-10 flex items-center px-3 rounded-md border border-border/50 bg-background/50 text-sm font-mono text-muted-foreground overflow-hidden whitespace-nowrap text-ellipsis">
                              {config.command}
                            </div>
                          </div>
                          <div className="md:col-span-3 space-y-1.5">
                            <Label className="text-[11px] uppercase tracking-wider text-muted-foreground font-bold">Args</Label>
                            <div className="h-10 flex items-center px-3 rounded-md border border-border/50 bg-background/50 text-sm font-mono text-muted-foreground overflow-x-auto whitespace-nowrap scrollbar-none">
                              {JSON.stringify(config.args || [])}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                    {Object.keys(mcpServers).length === 0 && (
                      <div className="text-center py-16 text-muted-foreground border border-dashed rounded-[20px] bg-muted/10">
                        暂无 MCP 服务器配置
                      </div>
                    )}
                  </div>
                  <div className="h-24 w-full shrink-0" />
                </div>
              )}

              {/* ====== 本地插件 ====== */}
              {activeTab === 'local' && (
                <div className="space-y-6 mt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-semibold flex items-center gap-3"><Puzzle className="text-primary size-6"/> 本地插件库</h2>
                      <p className="text-sm text-muted-foreground mt-1">支持将插件文件夹拖入此区域直接安装注册</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {plugins.length === 0 && (
                       <div className="col-span-full text-center py-20 text-muted-foreground border-2 border-dashed rounded-[24px] bg-muted/10 flex flex-col items-center justify-center pointer-events-none">
                         <UploadCloud className="size-10 mb-3 opacity-50" />
                         <span className="font-medium">将插件文件夹拖拽至此处安装</span>
                       </div>
                    )}
                    {plugins.map((plugin) => (
                      <div key={plugin.name} className="flex items-center justify-between p-4 rounded-[20px] border border-border/40 bg-background shadow-sm hover:border-primary/30 transition-colors">
                        <div className="flex items-center gap-4 min-w-0">
                          <div className="size-12 rounded-[14px] bg-primary/10 flex items-center justify-center shrink-0">
                            <Puzzle className="size-5 text-primary" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="text-base font-bold truncate">{plugin.name}</h4>
                              <Badge variant="secondary" className="text-[10px] h-4 px-1.5 shrink-0">Local</Badge>
                            </div>
                            <button
                              onClick={() => { setSelectedPlugin(plugin); setIsPluginDialogOpen(true); }}
                              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors bg-muted/40 px-2 py-0.5 rounded-md w-fit"
                            >
                              <Info className="size-3" />
                              查看详情
                            </button>
                          </div>
                        </div>
                        <Switch
                          checked={plugin.enabled}
                          onCheckedChange={() => handleTogglePlugin(plugin.name)}
                          className="data-[state=checked]:bg-primary shrink-0 ml-4"
                        />
                      </div>
                    ))}
                  </div>

                  {/* 插件详情弹窗 */}
                  <Dialog open={isPluginDialogOpen} onOpenChange={setIsPluginDialogOpen}>
                    <DialogContent className="max-w-2xl max-h-[85vh] h-full flex flex-col p-0 gap-0 overflow-hidden rounded-[24px]">
                      <DialogHeader className="p-6 border-b shrink-0 bg-muted/10">
                        <div className="flex items-center gap-4">
                          <div className="size-12 rounded-[16px] bg-primary/10 flex items-center justify-center shrink-0">
                            <Puzzle className="size-6 text-primary" />
                          </div>
                          <DialogTitle className="text-xl font-bold truncate pr-4">{selectedPlugin?.name}</DialogTitle>
                        </div>
                      </DialogHeader>
                      <ScrollArea className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-muted-foreground/20">
                        <div className="p-6 space-y-8">
                          <section>
                            <h3 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                              <BookOpen className="size-4 text-muted-foreground" />
                              插件介绍
                            </h3>
                            <div className="bg-muted/20 p-4 rounded-[16px] text-sm text-muted-foreground leading-relaxed border border-border/40 whitespace-pre-wrap break-words">
                              {/* 准确读取由后端发来的 description */}
                              {selectedPlugin?.description || "暂无描述"}
                            </div>
                          </section>

                          <section>
                            <h3 className="text-sm font-bold text-foreground mb-4 flex items-center gap-2">
                              <Code className="size-4 text-muted-foreground" />
                              工具函数 ({(toolsMap[selectedPlugin?.name] || []).length})
                            </h3>
                            <div className="grid gap-4">
                              {(toolsMap[selectedPlugin?.name] || []).map((fn: any) => (
                                <div key={fn.name} className="p-4 rounded-[16px] border border-border/50 bg-background shadow-sm">
                                  <div className="mb-2">
                                    <code className="text-sm font-bold text-primary bg-primary/10 px-2 py-1 rounded-md break-all">
                                      {fn.name}
                                    </code>
                                  </div>
                                  <p className="text-sm text-muted-foreground mb-4 break-words">
                                    {fn.description || "暂无函数描述"}
                                  </p>
                                  {fn.parameters?.properties && Object.keys(fn.parameters.properties).length > 0 && (
                                    <div className="bg-muted/30 p-3 rounded-xl overflow-x-auto scrollbar-thin">
                                      <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-2">参数列表</div>
                                      <div className="grid gap-1.5 min-w-[300px]">
                                        {Object.entries(fn.parameters.properties).map(([pName, pValue]: [string, any]) => (
                                          <div key={pName} className="flex items-baseline gap-3 text-sm">
                                            <code className="text-foreground font-semibold shrink-0">{pName}</code>
                                            <span className="text-muted-foreground/30 shrink-0 border-b border-dotted flex-1 translate-y-[-4px]"></span>
                                            <span className="text-muted-foreground shrink-0 text-right truncate max-w-[200px]" title={pValue.description || pValue.type}>
                                              {pValue.description || pValue.type}
                                            </span>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </section>
                        </div>
                      </ScrollArea>
                    </DialogContent>
                  </Dialog>
                </div>
              )}

              {/* ====== 技能目录 ====== */}
              {activeTab === 'skill' && (
                <div className="space-y-6 mt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-2xl font-semibold flex items-center gap-3"><Wrench className="text-primary size-6"/> Skills</h2>
                      <p className="text-sm text-muted-foreground mt-1">支持将技能文件夹拖入此区域直接安装注册</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {skills.length === 0 && (
                       <div className="col-span-full text-center py-20 text-muted-foreground border-2 border-dashed rounded-[24px] bg-muted/10 flex flex-col items-center justify-center pointer-events-none">
                         <UploadCloud className="size-10 mb-3 opacity-50" />
                         <span className="font-medium">将技能文件夹拖拽至此处安装</span>
                       </div>
                    )}
                    {skills.map((skill) => (
                      <div key={skill.name} className="p-5 rounded-[20px] border border-border/40 bg-background shadow-sm hover:border-primary/30 transition-colors flex flex-col justify-between group relative">
                        <div className="flex items-start gap-3 mb-4">
                          <div className="size-10 rounded-[12px] bg-primary/10 flex items-center justify-center shrink-0">
                            <Wrench className="size-4 text-primary" />
                          </div>
                          <div className="flex-1 min-w-0 pr-2">
                            <h4 className="text-base font-bold text-foreground group-hover:text-primary transition-colors truncate">
                              {skill.name}
                            </h4>
                          </div>
                          <Dialog>
                            <DialogTrigger asChild>
                              <button className="p-2 text-muted-foreground hover:text-primary transition-colors rounded-full hover:bg-muted/50 shrink-0">
                                <Info className="size-4" />
                              </button>
                            </DialogTrigger>
                            <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden rounded-[24px]">
                              <DialogHeader className="p-6 border-b shrink-0 bg-muted/10">
                                <div className="flex items-center gap-4">
                                  <div className="size-12 rounded-[16px] bg-primary/10 flex items-center justify-center shrink-0">
                                    <Wrench className="size-6 text-primary" />
                                  </div>
                                  <DialogTitle className="text-xl font-bold truncate">{skill.name}</DialogTitle>
                                </div>
                              </DialogHeader>
                              <ScrollArea className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-muted-foreground/20">
                                <div className="p-6 space-y-8">
                                  <section>
                                    <h3 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                                      <BookOpen className="size-4 text-muted-foreground" />
                                      技能目录
                                    </h3>
                                    <div className="bg-muted/20 p-4 rounded-[16px] text-sm text-muted-foreground leading-relaxed border border-border/40 whitespace-pre-wrap break-words">
                                      {skill.description || "暂无描述 (可在技能文件夹下补充 SKILL.md)"}
                                    </div>
                                  </section>
                                </div>
                              </ScrollArea>
                              <div className="p-6 border-t flex justify-end gap-2 shrink-0">
                                <Button variant="destructive" onClick={async () => {
                                  try {
                                    const res = await fetch(`${API_BASE}/skills/${skill.name}`, { method: 'DELETE' })
                                    if (res.ok) {
                                      toast({ title: "移除成功", description: `技能 ${skill.name} 已成功移除` })
                                      fetchData()
                                    } else {
                                      throw new Error("移除失败")
                                    }
                                  } catch (e) {
                                    toast({ title: "移除失败", variant: "destructive" })
                                  }
                                }}>
                                  <Trash2 className="size-4 mr-2" />
                                    删除
                                </Button>
                              </div>
                            </DialogContent>
                          </Dialog>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ====== SOUL.md ====== */}
              {activeTab === 'soul' && (
                <div className="space-y-6 mt-6 flex-1 flex flex-col">
                  <div>
                    <h2 className="text-2xl font-semibold flex items-center gap-3"><BookOpen className="text-primary size-6"/> SOUL.md</h2>
                    <p className="text-sm text-muted-foreground mt-1">定义 Agent 的核心人格与全局基础准则</p>
                  </div>
                  <div className="flex-1 rounded-[24px] border border-border/20 bg-background/80 backdrop-blur-sm shadow-sm p-6 overflow-hidden min-h-[400px]">
                    <Textarea
                      value={soulContent}
                      onChange={(e) => setSoulContent(e.target.value)}
                      className="w-full h-full font-mono text-sm leading-relaxed resize-none border-none focus-visible:ring-0 bg-transparent scrollbar-thin scrollbar-thumb-muted-foreground/20"
                      placeholder="# Your Agent's SOUL..."
                    />
                  </div>
                  <div className="h-24 w-full shrink-0" />
                </div>
              )}

            </div>
          </div>

          {/* 底部悬浮操作栏 */}
          <div className="absolute bottom-0 left-0 right-0 z-20 bg-gradient-to-t from-background via-background/90 to-transparent pt-32 pb-8 px-4 md:px-12 pointer-events-none">
            <div className="max-w-5xl mx-auto w-full pointer-events-auto flex justify-end">
              {(activeTab === 'model' || activeTab === 'mcp' || activeTab === 'soul') && (
                <Button size="lg" variant="secondary" className="bg-background/80 backdrop-blur-md rounded-[24px] shadow-[0_-10px_40px_rgba(0,0,0,0.05)] border border-border/20 p-4 px-8 shadow-sm active:scale-95 transition-all" onClick={handleCurrentSave}>
                  <Save className="size-4 mr-2" />
                  保存更改
                </Button>
              )}
            </div>
          </div>

        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}