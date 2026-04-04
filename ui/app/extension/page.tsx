'use client'

import React, { useState, useEffect } from 'react'
import {
  Puzzle,
  Settings2,
  Wrench,
  Cpu,
  Plus,
  Trash2,
  ExternalLink,
  Save,
  BookOpen,
  Server,
  Code,
  Loader2,
  Info
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { useToast } from "@/hooks/use-toast"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"

const API_BASE = 'http://localhost:8001/api'

export default function ExtensionPage() {
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)

  const [llmModels, setLlmModels] = useState<Record<string, any>>({})
  const [specializedModels, setSpecializedModels] = useState<Record<string, any>>({})
  const [mcpServers, setMcpServers] = useState<Record<string, any>>({})
  const [plugins, setPlugins] = useState<any[]>([])
  const [skills, setSkills] = useState<any[]>([])
  const [soulContent, setSoulContent] = useState("")
  const [selectedPlugin, setSelectedPlugin] = useState<any>(null)
  const [isPluginDialogOpen, setIsPluginDialogOpen] = useState(false)

  const [mcpArgsInput, setMcpArgsInput] = useState<Record<string, string>>({})

  const fetchData = async () => {
    setLoading(true)
    try {
      const [configRes, pluginsRes, skillsRes, soulRes] = await Promise.all([
        fetch(`${API_BASE}/config`),
        fetch(`${API_BASE}/plugins`),
        fetch(`${API_BASE}/skills`),
        fetch(`${API_BASE}/files?path=soul`)
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

      const initialArgs: Record<string, string> = {}
      Object.keys(servers).forEach(name => { initialArgs[name] = JSON.stringify(servers[name].args || []) })
      setMcpArgsInput(initialArgs)

      setPlugins(await pluginsRes.json())
      setSkills(await skillsRes.json())

      const soulData = await soulRes.json()
      setSoulContent(soulData.content || "")
    } catch (error) {
      toast({ title: "加载失败", description: "无法连接到后端服务器", variant: "destructive" })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

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
      const finalServers = { ...mcpServers }
      Object.keys(finalServers).forEach(name => {
        try { finalServers[name].args = JSON.parse(mcpArgsInput[name] || "[]") }
        catch { finalServers[name].args = [] }
      })
      await fetch(`${API_BASE}/config/mcp_config.json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mcpServers: finalServers })
      })
      toast({ title: "保存成功", description: "MCP 注册表已更新" })
    } catch (e) { toast({ title: "保存失败", variant: "destructive" }) }
  }

  const handleTogglePlugin = async (name: string) => {
    try {
      const res = await fetch(`${API_BASE}/plugins/${name}/toggle`, { method: 'POST' })
      const data = await res.json()
      setPlugins(plugins.map(p => p.name === name ? { ...p, enabled: data.enabled } : p))
      toast({ title: "插件状态已更新", description: `${name} 当前状态: ${data.enabled ? '启用' : '禁用'}` })
    } catch (e) { toast({ title: "切换失败", variant: "destructive" }) }
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

  const updateLlmModel = (id: string, field: string, value: string) => {
    setLlmModels(prev => ({ ...prev, [id]: { ...prev[id], [field]: value } }))
  }

  const updateSpecModel = (type: string, field: string, value: string) => {
    setSpecializedModels(prev => ({ ...prev, [type]: { ...prev[type], [field]: value } }))
  }

  const updateMcpServer = (name: string, field: string, value: string) => {
    if (field === 'args') setMcpArgsInput(prev => ({ ...prev, [name]: value }))
    else setMcpServers(prev => ({ ...prev, [name]: { ...prev[name], [field]: value } }))
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full absolute inset-0"><Loader2 className="size-8 animate-spin text-muted-foreground" /></div>
  }

  return (
    // 最外层容器：绝对定位于屏幕，不可溢出
    <div className="absolute inset-0 flex flex-col bg-background p-6 overflow-hidden">

      {/* 页面头部 */}
      <div className="flex items-center justify-between shrink-0 mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Extensions & Config</h1>
          <p className="text-muted-foreground text-sm">管理模型密钥、MCP 服务器、本地插件与技能扩展</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>刷新数据</Button>
      </div>

      {/* Tabs 控制区：flex-1 占据剩余所有高度 */}
      <Tabs defaultValue="model" className="flex-1 flex flex-col min-h-0">

        {/* Tab 选项卡（固定高度） */}
        <div className="shrink-0 mb-4">
          <TabsList className="bg-muted/50 p-1 border">
            <TabsTrigger value="model" className="data-[state=active]:bg-background">
              <Settings2 className="size-4 mr-2" /> 模型配置
            </TabsTrigger>
            <TabsTrigger value="mcp" className="data-[state=active]:bg-background">
              <Cpu className="size-4 mr-2" /> MCP 服务器
            </TabsTrigger>
            <TabsTrigger value="local" className="data-[state=active]:bg-background">
              <Puzzle className="size-4 mr-2" /> 本地插件
            </TabsTrigger>
            <TabsTrigger value="skill" className="data-[state=active]:bg-background">
              <Wrench className="size-4 mr-2" /> 技能目录
            </TabsTrigger>
            <TabsTrigger value="soul" className="data-[state=active]:bg-background">
              <BookOpen className="size-4 mr-2" /> SOUL.md
            </TabsTrigger>
          </TabsList>
        </div>

        {/* 关键：内容的展示区被设为 min-h-0 和 flex-1 */}
        <div className="flex-1 min-h-0">

          {/* ====== 模型配置 ====== */}
          <TabsContent value="model" className="m-0 h-full">
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 h-full">
              {/* Card 设置为 flex 纵向布局 */}
              <Card className="flex flex-col h-full border shadow-sm overflow-hidden">
                <CardHeader className="shrink-0 border-b pb-4">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Server className="size-4 text-primary" />
                      LLM 模型配置
                    </CardTitle>
                    <Button size="sm" variant="outline" onClick={() => {
                      const newId = `new_model_${Date.now()}`
                      setLlmModels(prev => ({ ...prev, [newId]: { api_key: "", base_url: "", description: "" } }))
                    }}>
                      <Plus className="size-4 mr-1" /> 添加
                    </Button>
                  </div>
                </CardHeader>
                {/* 独立滚动区域：只有中间列表会滚动 */}
                <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
                  {Object.entries(llmModels).map(([id, config]) => (
                    <div key={id} className="p-4 rounded-lg border bg-muted/10 space-y-3 relative group">
                      <button
                        className="absolute right-3 top-3 text-muted-foreground hover:text-destructive transition-colors"
                        onClick={() => {
                          const newModels = { ...llmModels }; delete newModels[id]; setLlmModels(newModels);
                        }}
                      >
                        <Trash2 className="size-4" />
                      </button>
                      <div className="space-y-1 pr-8">
                        <Label className="text-[10px] uppercase text-muted-foreground">模型标识 (Key)</Label>
                        <Input
                          value={id}
                          onChange={(e) => {
                            const newId = e.target.value;
                            if(newId !== id) {
                              const newModels = { ...llmModels };
                              newModels[newId] = newModels[id];
                              delete newModels[id];
                              setLlmModels(newModels);
                            }
                          }}
                          className="h-8 text-xs font-mono font-bold text-primary"
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                          <Label className="text-[10px] uppercase text-muted-foreground">API Key</Label>
                          <Input type="password" value={config.api_key || ''} onChange={e => updateLlmModel(id, 'api_key', e.target.value)} className="h-8 text-xs font-mono" />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] uppercase text-muted-foreground">Base URL</Label>
                          <Input value={config.base_url || ''} onChange={e => updateLlmModel(id, 'base_url', e.target.value)} className="h-8 text-xs font-mono" />
                        </div>
                      </div>
                      <div className="space-y-1">
                        <Label className="text-[10px] uppercase text-muted-foreground">Description</Label>
                        <Input value={config.description || ''} onChange={e => updateLlmModel(id, 'description', e.target.value)} className="h-8 text-xs" />
                      </div>
                    </div>
                  ))}
                </CardContent>
                {/* 底部固定区：保存按钮 */}
                <CardFooter className="shrink-0 border-t bg-muted/5 p-4">
                  <Button size="sm" className="w-full" onClick={handleSaveModels}><Save className="size-4 mr-2" /> 保存 LLM 配置</Button>
                </CardFooter>
              </Card>

              {/* 专用模型卡片同理 */}
              <Card className="flex flex-col h-full border shadow-sm overflow-hidden">
                <CardHeader className="shrink-0 border-b pb-4">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Code className="size-4 text-purple-500" />
                    专用模型配置 (Specialized)
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
                  {Object.entries(specializedModels).map(([type, config]) => (
                    <div key={type} className="p-4 rounded-lg border bg-muted/10 space-y-3">
                      <Badge variant="outline">{type}</Badge>
                      <div className="space-y-1">
                        <Label className="text-[10px] uppercase text-muted-foreground">Model Name</Label>
                        <Input value={config.name || ''} onChange={e => updateSpecModel(type, 'name', e.target.value)} className="h-8 text-xs font-mono" />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                          <Label className="text-[10px] uppercase text-muted-foreground">API Key</Label>
                          <Input type="password" value={config.api_key || ''} onChange={e => updateSpecModel(type, 'api_key', e.target.value)} className="h-8 text-xs font-mono" />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[10px] uppercase text-muted-foreground">Base URL</Label>
                          <Input value={config.base_url || ''} onChange={e => updateSpecModel(type, 'base_url', e.target.value)} className="h-8 text-xs font-mono" />
                        </div>
                      </div>
                    </div>
                  ))}
                </CardContent>
                <CardFooter className="shrink-0 border-t bg-muted/5 p-4">
                  <Button size="sm" className="w-full" onClick={handleSaveModels}><Save className="size-4 mr-2" /> 保存专用模型</Button>
                </CardFooter>
              </Card>
            </div>
          </TabsContent>

          {/* ====== MCP 服务器 ====== */}
          <TabsContent value="mcp" className="m-0 h-full">
            <Card className="flex flex-col h-full border shadow-sm overflow-hidden">
              <CardHeader className="shrink-0 border-b pb-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Server className="size-4 text-primary" />
                    MCP 服务器注册表
                  </CardTitle>
                  <Button size="sm" variant="outline" onClick={() => {
                    const newName = `new_server_${Date.now()}`
                    setMcpServers(prev => ({ ...prev, [newName]: { command: "npx", args: [] } }))
                    setMcpArgsInput(prev => ({ ...prev, [newName]: "[]" }))
                  }}>
                    <Plus className="size-4 mr-1" /> 添加服务
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
                {Object.entries(mcpServers).map(([name, config]) => (
                  <div key={name} className="p-4 rounded-lg border bg-muted/10 relative group">
                    <button
                      className="absolute right-3 top-3 text-muted-foreground hover:text-destructive transition-colors"
                      onClick={() => {
                        const newServers = { ...mcpServers }; delete newServers[name]; setMcpServers(newServers);
                      }}
                    >
                      <Trash2 className="size-4" />
                    </button>
                    <div className="mb-3 flex items-center gap-2">
                      <div className="size-2 rounded-full bg-green-500" />
                      <Input
                        value={name}
                        onChange={(e) => {
                          const newName = e.target.value;
                          if(newName !== name) {
                            const newServers = { ...mcpServers };
                            newServers[newName] = newServers[name];
                            delete newServers[name];
                            setMcpServers(newServers);
                            setMcpArgsInput(prev => ({ ...prev, [newName]: prev[name] }))
                          }
                        }}
                        className="h-7 w-48 text-sm font-bold border-none bg-transparent px-1 focus-visible:ring-1"
                      />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div className="md:col-span-1 space-y-1">
                        <Label className="text-[10px] uppercase text-muted-foreground">Command</Label>
                        <Input value={config.command || ''} onChange={e => updateMcpServer(name, 'command', e.target.value)} className="h-8 text-xs font-mono" />
                      </div>
                      <div className="md:col-span-3 space-y-1">
                        <Label className="text-[10px] uppercase text-muted-foreground">Args (JSON 数组格式)</Label>
                        <Input
                          value={mcpArgsInput[name] || ''}
                          onChange={e => updateMcpServer(name, 'args', e.target.value)}
                          placeholder='["arg1", "arg2"]'
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
              <CardFooter className="shrink-0 border-t bg-muted/5 p-4 flex justify-end">
                <Button size="sm" onClick={handleSaveMcp}><Save className="size-4 mr-2" /> 保存 MCP 配置</Button>
              </CardFooter>
            </Card>
          </TabsContent>

          {/* ====== 技能目录 ====== */}
          <TabsContent value="skill" className="m-0 h-full">
            <Card className="flex flex-col h-full border shadow-sm overflow-hidden">
              <CardHeader className="shrink-0 border-b pb-4">
                <CardTitle className="text-base flex items-center gap-2">
                  <Wrench className="size-4 text-primary" />
                  已加载技能 (Skills)
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 overflow-y-auto p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {skills.length === 0 && <div className="text-sm text-muted-foreground">暂无技能</div>}
                  {skills.map((skill) => (
                    <div key={skill.name} className="p-4 rounded-lg border bg-muted/10 flex flex-col justify-between">
                      <div>
                        <h4 className="text-sm font-bold flex items-center gap-2 mb-2">
                          {skill.name}
                        </h4>
                      </div>
                      <div className="mt-2 pt-3 border-t flex items-center justify-between">
                        <code className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded truncate">
                          {skill.path}
                        </code>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ====== 本地插件 ====== */}
          <TabsContent value="local" className="m-0 h-full">
            <Card className="flex flex-col h-full border shadow-sm overflow-hidden">
              <CardHeader className="shrink-0 border-b pb-4">
                <CardTitle className="text-base flex items-center gap-2">
                  <Puzzle className="size-4 text-primary" />
                  本地插件 (Local Tools)
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 overflow-y-auto p-4 space-y-3">
                {plugins.length === 0 && <div className="text-sm text-muted-foreground">暂无本地插件</div>}
                {plugins.map((plugin) => (
                  <div key={plugin.name} className="flex items-center justify-between p-3 rounded-lg border bg-muted/10">
                    <div className="flex items-center gap-3">
                      <div className="size-8 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Puzzle className="size-4 text-primary" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold">{plugin.name}</h4>
                          <Badge variant="secondary" className="text-[9px] h-3.5 px-1 py-0">Local</Badge>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <button
                            onClick={() => {
                              setSelectedPlugin(plugin)
                              setIsPluginDialogOpen(true)
                            }}
                            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-primary transition-colors"
                          >
                            <Info className="size-3" />
                            插件详情
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Switch
                        checked={plugin.enabled}
                        onCheckedChange={() => handleTogglePlugin(plugin.name)}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>

              {/* 插件详情弹窗 */}
              <Dialog open={isPluginDialogOpen} onOpenChange={setIsPluginDialogOpen}>
                <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-0 gap-0 overflow-hidden">
                  <DialogHeader className="p-6 border-b shrink-0">
                    <div className="flex items-center gap-3">
                      <div className="size-10 rounded-xl bg-primary/10 flex items-center justify-center">
                        <Puzzle className="size-5 text-primary" />
                      </div>
                      <div>
                        <DialogTitle className="text-xl font-bold">{selectedPlugin?.name}</DialogTitle>
                        <DialogDescription className="text-xs font-mono mt-0.5 opacity-70">
                          {selectedPlugin?.path}
                        </DialogDescription>
                      </div>
                    </div>
                  </DialogHeader>
                  
                  <ScrollArea className="flex-1 overflow-y-auto">
                    <div className="p-6 space-y-6">
                      {/* 介绍部分 */}
                      <section>
                        <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                          <BookOpen className="size-4 text-muted-foreground" />
                          插件介绍
                        </h3>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {selectedPlugin?.config?.description || "暂无描述"}
                        </p>
                      </section>

                      {/* 函数列表 */}
                      <section>
                        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                          <Code className="size-4 text-muted-foreground" />
                          工具函数 ({selectedPlugin?.config?.functions?.length || 0})
                        </h3>
                        <div className="grid gap-3">
                          {selectedPlugin?.config?.functions?.map((fn: any) => (
                            <div key={fn.name} className="p-3 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors">
                              <div className="flex items-center justify-between mb-1.5">
                                <code className="text-xs font-bold text-primary bg-primary/5 px-2 py-0.5 rounded">
                                  {fn.name}
                                </code>
                              </div>
                              <p className="text-xs text-muted-foreground mb-2">
                                {fn.description || "暂无函数描述"}
                              </p>
                              {fn.parameters?.properties && (
                                <div className="mt-2 space-y-1.5">
                                  <div className="text-[10px] font-bold text-muted-foreground/60 uppercase tracking-wider">参数列表</div>
                                  <div className="grid gap-1">
                                    {Object.entries(fn.parameters.properties).map(([pName, pValue]: [string, any]) => (
                                      <div key={pName} className="flex items-baseline gap-2 text-[11px]">
                                        <code className="text-muted-foreground font-semibold shrink-0">{pName}</code>
                                        <span className="text-muted-foreground/40 shrink-0">:</span>
                                        <span className="text-muted-foreground/80">{pValue.description || pValue.type}</span>
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
            </Card>
          </TabsContent>

          {/* ====== SOUL.md ====== */}
          <TabsContent value="soul" className="m-0 h-full">
            <Card className="flex flex-col h-full border shadow-sm overflow-hidden">
              <CardHeader className="shrink-0 border-b pb-4">
                <CardTitle className="text-base flex items-center gap-2">
                  <BookOpen className="size-4 text-primary" />
                  SOUL.md Core Identity
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 p-0 overflow-hidden">
                <Textarea
                  value={soulContent}
                  onChange={(e) => setSoulContent(e.target.value)}
                  className="w-full h-full p-4 font-mono text-sm leading-relaxed resize-none border-none focus-visible:ring-0 rounded-none bg-transparent overflow-y-auto"
                  style={{ fieldSizing: 'fixed' } as any}
                  placeholder="# Your Agent's SOUL..."
                />
              </CardContent>
              <CardFooter className="shrink-0 border-t bg-muted/5 p-4 flex justify-end">
                <Button size="sm" onClick={handleSaveSoul}><Save className="size-4 mr-2" /> 保存 SOUL Identity</Button>
              </CardFooter>
            </Card>
          </TabsContent>

        </div>
      </Tabs>
    </div>
  )
}