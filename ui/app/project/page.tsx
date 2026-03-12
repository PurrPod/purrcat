'use client'

import { useEffect, useMemo, useState } from 'react'
import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area'
import { useAppStore } from '@/lib/store'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Progress } from '@/components/ui/progress'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { FolderKanban, Clock, CheckCircle, XCircle, Loader2, Trash2, StopCircle, Plus, Terminal, Search, Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Project } from '@/lib/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'

const statusConfig = {
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: '运行中' },
  pending: { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: '等待中' },
  completed: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-500/10', label: '已完成' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: '失败' },
}

function ToolPickerPanel({
  selectedTools,
  onSelectionChange,
}: {
  selectedTools: string[]
  onSelectionChange: (tools: string[]) => void
}) {
  const toolGroups = useAppStore((state) => state.toolGroups)
  const [searchTerm, setSearchTerm] = useState('')
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})

  const filteredGroups = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase()
    if (!keyword) return toolGroups
    return toolGroups
      .map((group) => ({
        ...group,
        tools: group.tools.filter(
          (tool) =>
            tool.name.toLowerCase().includes(keyword) ||
            group.name.toLowerCase().includes(keyword) ||
            tool.description.toLowerCase().includes(keyword),
        ),
      }))
      .filter((group) => group.tools.length > 0)
  }, [toolGroups, searchTerm])

  useEffect(() => {
    if (toolGroups.length === 0) return
    setOpenGroups((prev) => {
      let changed = false
      const next = { ...prev }
      for (const g of toolGroups) {
        if (next[g.name] === undefined) {
          next[g.name] = true
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [toolGroups])

  useEffect(() => {
    if (!searchTerm.trim()) return
    setOpenGroups((prev) => {
      let changed = false
      const next = { ...prev }
      for (const g of filteredGroups) {
        if (next[g.name] !== true) {
          next[g.name] = true
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [filteredGroups, searchTerm])

  const toggleTool = (toolIdentifier: string) => {
    const next = selectedTools.includes(toolIdentifier)
      ? selectedTools.filter((t) => t !== toolIdentifier)
      : [...selectedTools, toolIdentifier]
    onSelectionChange(next)
  }

  const setGroupSelection = (groupName: string, toolNames: string[], checked: boolean) => {
    const identifiers = toolNames.map((toolName) => `${groupName}/${toolName}`)
    if (checked) {
      const merged = new Set([...selectedTools, ...identifiers])
      onSelectionChange(Array.from(merged))
      return
    }
    onSelectionChange(selectedTools.filter((t) => !identifiers.includes(t)))
  }

  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="flex items-center justify-between">
        <Label>可用工具</Label>
        <span className="text-xs text-muted-foreground">{selectedTools.length} 已选</span>
      </div>

      <div className="mt-2 rounded-md border bg-background overflow-hidden flex flex-col min-h-0 max-h-[62vh]">
        <div className="p-2 border-b">
          <div className="flex items-center gap-2 px-2">
            <Search className="size-4 text-muted-foreground" />
            <Input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="搜索工具 / 插件 / 描述..."
              className="h-8 border-0 px-0 shadow-none focus-visible:ring-0"
            />
          </div>
        </div>

        <ScrollAreaPrimitive.Root className="relative flex-1 overflow-hidden">
          <ScrollAreaPrimitive.Viewport className="size-full rounded-[inherit]">
            <div className="p-2 space-y-3">
              {filteredGroups.length === 0 ? (
                <div className="py-6 text-center text-sm text-muted-foreground">未找到工具。</div>
              ) : (
                filteredGroups.map((group) => (
                  <Collapsible
                    key={group.name}
                    open={openGroups[group.name] ?? true}
                    onOpenChange={(open) => setOpenGroups((prev) => ({ ...prev, [group.name]: open }))}
                    className="rounded-md border border-border/60 bg-background/60"
                  >
                    {(() => {
                      const toolNames = group.tools.map((t) => t.name)
                      const identifiers = toolNames.map((n) => `${group.name}/${n}`)
                      const selectedCount = identifiers.filter((id) => selectedTools.includes(id)).length
                      const totalCount = identifiers.length
                      const groupChecked = totalCount === 0 ? false : selectedCount === 0 ? false : selectedCount === totalCount ? true : 'indeterminate'

                      return (
                        <>
                          <div className="flex items-center justify-between px-2 py-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <Checkbox
                                checked={groupChecked as any}
                                onCheckedChange={(checked) => setGroupSelection(group.name, toolNames, checked === true)}
                              />
                              <div className="min-w-0">
                                <div className="text-xs font-medium truncate">{group.name}</div>
                                <div className="text-[10px] text-muted-foreground">
                                  {selectedCount}/{totalCount}
                                </div>
                              </div>
                            </div>

                            <CollapsibleTrigger asChild>
                              <button
                                type="button"
                                className="rounded-md p-1.5 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                                aria-label={`折叠/展开 ${group.name}`}
                              >
                                <ChevronDown
                                  className={cn(
                                    'size-4 text-muted-foreground transition-transform',
                                    (openGroups[group.name] ?? true) && 'rotate-180',
                                  )}
                                />
                              </button>
                            </CollapsibleTrigger>
                          </div>

                          <CollapsibleContent className="border-t border-border/60">
                            <div className="p-2 space-y-1">
                              {group.tools.map((tool) => {
                                const toolIdentifier = `${group.name}/${tool.name}`
                                const isSelected = selectedTools.includes(toolIdentifier)
                                return (
                                  <button
                                    key={toolIdentifier}
                                    type="button"
                                    onClick={() => toggleTool(toolIdentifier)}
                                    className={cn(
                                      'w-full rounded-md px-2 py-2 text-left hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
                                      isSelected && 'bg-accent',
                                    )}
                                  >
                                    <div className="flex items-start gap-2">
                                      <div
                                        className={cn(
                                          'mt-0.5 flex h-4 w-4 items-center justify-center rounded-sm border border-primary',
                                          isSelected
                                            ? 'bg-primary text-primary-foreground'
                                            : 'opacity-50 [&_svg]:invisible',
                                        )}
                                      >
                                        <Check className="h-4 w-4" />
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <div className="text-sm font-medium leading-tight">{tool.name}</div>
                                        <div className="text-xs text-muted-foreground whitespace-normal break-words leading-snug mt-0.5">
                                          {tool.description || '无描述'}
                                        </div>
                                      </div>
                                    </div>
                                  </button>
                                )
                              })}
                            </div>
                          </CollapsibleContent>
                        </>
                      )
                    })()}
                  </Collapsible>
                ))
              )}
            </div>
          </ScrollAreaPrimitive.Viewport>
          <ScrollAreaPrimitive.ScrollAreaScrollbar
            orientation="vertical"
            forceMount
            className="flex touch-none p-px transition-colors select-none h-full w-2.5 border-l border-l-transparent data-[state=hidden]:opacity-100 data-[state=visible]:opacity-100"
          >
            <ScrollAreaPrimitive.ScrollAreaThumb className="bg-border relative flex-1 rounded-full" />
          </ScrollAreaPrimitive.ScrollAreaScrollbar>
          <ScrollAreaPrimitive.Corner />
        </ScrollAreaPrimitive.Root>
      </div>
    </div>
  )
}

function ModelNameSelect({
  value,
  onValueChange,
  placeholder,
}: {
  value: string
  onValueChange: (value: string) => void
  placeholder: string
}) {
  const modelConfig = useAppStore((state) => state.modelConfig)
  const models = (modelConfig?.models ?? {}) as Record<string, any>
  const modelNames = Object.keys(models)
  const normalizedValue = modelNames.includes(value) ? value : undefined

  return (
    <Select value={normalizedValue} onValueChange={onValueChange}>
      <SelectTrigger className="w-full shadow-none focus-visible:ring-0 focus-visible:ring-offset-0">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {modelNames.length > 0 ? (
          modelNames.map((name) => (
            <SelectItem key={name} value={name}>
              {name}
            </SelectItem>
          ))
        ) : (
          <SelectItem value="__empty__" disabled>
            未加载到 models 列表
          </SelectItem>
        )}
      </SelectContent>
    </Select>
  )
}

function ProjectCard({ 
  project, 
  isSelected, 
  onSelect,
  onStop,
  onDelete,
}: { 
  project: Project
  isSelected: boolean
  onSelect: () => void
  onStop: () => void
  onDelete: () => void
}) {
  const config = statusConfig[project.status]
  const Icon = config.icon

  return (
    <ContextMenu>
      <ContextMenuTrigger>
        <Card 
          className={cn(
            'cursor-pointer transition-all hover:border-primary/50',
            isSelected && 'border-primary ring-1 ring-primary'
          )}
          onClick={onSelect}
        >
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-sm">
              <span className="truncate">{project.name}</span>
              <span className={cn('flex items-center gap-1 text-xs px-2 py-1 rounded-full shrink-0', config.bg, config.color)}>
                <Icon className={cn('size-3', project.status === 'running' && 'animate-spin')} />
                {config.label}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Progress value={project.progress} className="h-1.5" />
            <div className="text-xs text-muted-foreground">
              {project.progress}% 完成
            </div>
          </CardContent>
        </Card>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem 
          onClick={(e) => { e.stopPropagation(); onStop(); }}
          disabled={project.status !== 'running' && project.status !== 'pending'}
        >
          <StopCircle className="size-4 mr-2" />
          终止项目
        </ContextMenuItem>
        <ContextMenuItem 
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="text-destructive"
        >
          <Trash2 className="size-4 mr-2" />
          删除并终止项目
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

function PipelineView({ project }: { project: Project }) {
  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardHeader className="shrink-0">
        <CardTitle className="flex items-center justify-between">
          <span>{project.name}</span>
          <span className={cn(
            'text-xs px-2 py-1 rounded-full',
            statusConfig[project.status].bg,
            statusConfig[project.status].color
          )}>
            {statusConfig[project.status].label}
          </span>
        </CardTitle>
        {project.description && (
          <p className="text-sm text-muted-foreground">{project.description}</p>
        )}
      </CardHeader>
      <CardContent className="flex-1 flex flex-col space-y-4 min-h-0 overflow-hidden">
        <div className="space-y-2 shrink-0">
          <div className="flex justify-between text-sm">
            <span>总体进度</span>
            <span className="font-medium">{project.progress}%</span>
          </div>
          <Progress value={project.progress} className="h-2" />
        </div>

        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex flex-col flex-1 min-h-0 space-y-4">
            <div className="flex-1 flex flex-col min-h-0">
              <h4 className="text-sm font-medium mb-3 shrink-0">Pipeline 步骤</h4>
              <ScrollArea className="flex-1 rounded-md border bg-muted/30">
                <div className="p-3 space-y-3">
                  {project.pipeline.map((step, index) => {
                    const stepConfig = statusConfig[step.status]
                    const StepIcon = stepConfig.icon

                    return (
                      <div key={step.id} className="flex items-start gap-3">
                        <div className={cn(
                          'flex items-center justify-center size-8 rounded-full shrink-0',
                          stepConfig.bg
                        )}>
                          <StepIcon className={cn(
                            'size-4',
                            stepConfig.color,
                            step.status === 'running' && 'animate-spin'
                          )} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">
                              {index + 1}. {step.name}
                            </span>
                            <span className={cn('text-xs', stepConfig.color)}>
                              {step.progress}%
                            </span>
                          </div>
                          <Progress value={step.progress} className="h-1 mt-1" />
                          {step.startedAt && (
                            <div className="text-xs text-muted-foreground mt-1">
                              开始: {step.startedAt.toLocaleTimeString('zh-CN')}
                              {step.completedAt && (
                                <span> | 完成: {step.completedAt.toLocaleTimeString('zh-CN')}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            </div>

            <div className="flex-1 flex flex-col min-h-0">
              <div className="flex items-center gap-2 mb-2 pt-4 border-t shrink-0">
                <Terminal className="size-4" />
                <h4 className="text-sm font-medium">项目对话历史</h4>
              </div>
              <ScrollArea className="flex-1 rounded-md border bg-muted/30">
                <div className="p-3 space-y-3">
                  {project.history && project.history.length > 0 ? (
                    project.history.map((msg, index) => (
                      <div key={index} className={cn(
                        "p-2 rounded-lg text-xs break-words",
                        msg.role === 'user' ? "bg-primary/10 ml-4" : 
                        msg.role === 'system' ? "bg-muted text-muted-foreground italic text-center mx-2" :
                        "bg-accent mr-4"
                      )}>
                        <div className="font-bold mb-1 uppercase text-[10px] opacity-70">
                          {msg.role}
                        </div>
                        <div className="whitespace-pre-wrap">
                          {typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-muted-foreground italic text-xs text-center py-4">暂无对话历史</div>
                  )}
                </div>
              </ScrollArea>
            </div>
          </div>
        </div>

        <div className="pt-4 border-t space-y-1 text-xs text-muted-foreground shrink-0">
          <div>创建时间: {project.createdAt.toLocaleString('zh-CN')}</div>
          {project.updatedAt && (
            <div>更新时间: {project.updatedAt.toLocaleString('zh-CN')}</div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function AddProjectDialog() {
  const addProject = useAppStore((state) => state.addProject)
  const [open, setOpen] = useState(false)
  const fetchModelConfig = useAppStore((state) => state.fetchModelConfig)
  const fetchToolGroups = useAppStore((state) => state.fetchToolGroups)
  const modelConfig = useAppStore((state) => state.modelConfig)
  const [formData, setFormData] = useState({
    name: '',
    prompt: '',
    core: '',
    check_mode: false,
    refine_mode: false,
    judge_mode: false,
    is_agent: false,
    available_tools: [] as string[],
  })

  const modelNames = useMemo(() => {
    const models = (modelConfig?.models ?? {}) as Record<string, any>
    return Object.keys(models)
  }, [modelConfig])

  useEffect(() => {
    if (!open) return
    fetchModelConfig()
    fetchToolGroups()
  }, [open, fetchModelConfig, fetchToolGroups])

  useEffect(() => {
    if (!open) return
    if (modelNames.length === 0) return
    setFormData((prev) => ({
      ...prev,
      core: modelNames.includes(prev.core) ? prev.core : modelNames[0],
    }))
  }, [open, modelNames])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await addProject(formData)
    setOpen(false)
    setFormData({
      name: '',
      prompt: '',
      core: '',
      check_mode: false,
      refine_mode: false,
      judge_mode: false,
      is_agent: false,
      available_tools: [],
    })
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="icon" variant="outline" className="size-8 rounded-full">
          <Plus className="size-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="w-[95vw] sm:max-w-[980px] max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>新建项目</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
          <div className="grid gap-6 md:grid-cols-[1fr_340px] py-4">
            <div className="space-y-4 pr-4">
                <div className="space-y-2">
                  <Label htmlFor="name">项目名称</Label>
                  <Input
                    id="name"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="输入项目名称..."
                    className="shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="prompt">项目需求 (Prompt)</Label>
                  <Textarea
                    id="prompt"
                    value={formData.prompt}
                    onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
                    placeholder="详细描述项目需求..."
                    className="min-h-[180px] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    spellCheck={false}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label>核心模型 (Core)</Label>
                  <ModelNameSelect
                    value={formData.core}
                    onValueChange={(v) => setFormData({ ...formData, core: v })}
                    placeholder="选择 Core 模型"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 pt-2">
                  <div className="flex items-center justify-between space-x-2">
                    <Label htmlFor="check_mode">人工审核 (Check)</Label>
                    <Switch
                      id="check_mode"
                      checked={formData.check_mode}
                      onCheckedChange={(checked) => setFormData({ ...formData, check_mode: checked })}
                    />
                  </div>
                  <div className="flex items-center justify-between space-x-2">
                    <Label htmlFor="refine_mode">需求优化 (Refine)</Label>
                    <Switch
                      id="refine_mode"
                      checked={formData.refine_mode}
                      onCheckedChange={(checked) => setFormData({ ...formData, refine_mode: checked })}
                    />
                  </div>
                  <div className="flex items-center justify-between space-x-2">
                    <Label htmlFor="judge_mode">质检模式 (Judge)</Label>
                    <Switch
                      id="judge_mode"
                      checked={formData.judge_mode}
                      onCheckedChange={(checked) => setFormData({ ...formData, judge_mode: checked })}
                    />
                  </div>
                  <div className="flex items-center justify-between space-x-2">
                    <Label htmlFor="is_agent">Agent 模式</Label>
                    <Switch
                      id="is_agent"
                      checked={formData.is_agent}
                      onCheckedChange={(checked) => setFormData({ ...formData, is_agent: checked })}
                    />
                  </div>
                </div>
            </div>

            <div className="min-h-0">
              <ToolPickerPanel
                selectedTools={formData.available_tools}
                onSelectionChange={(tools) => setFormData({ ...formData, available_tools: tools })}
              />
            </div>
          </div>

          <DialogFooter className="shrink-0 pt-4 border-t">
            <Button type="submit">提交并启动</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function ProjectPage() {
  const projects = useAppStore((state) => state.projects)
  const removeProject = useAppStore((state) => state.removeProject)
  const stopProject = useAppStore((state) => state.stopProject)
  const [selectedId, setSelectedId] = useState<string | null>(projects[0]?.id || null)
  
  const selectedProject = projects.find((p) => p.id === selectedId)
  const runningCount = projects.filter((p) => p.status === 'running').length

  return (
    <div className="h-[calc(100vh-4rem)] flex">
      {/* 左侧项目列表 */}
      <div className="w-80 border-r flex flex-col min-h-0 overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderKanban className="size-5" />
            <h1 className="font-semibold">项目队列</h1>
          </div>
          <AddProjectDialog />
        </div>
        <ScrollArea type="always" className="flex-1 min-h-0">
          <div className="p-4 space-y-8 pr-3">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                isSelected={selectedId === project.id}
                onSelect={() => setSelectedId(project.id)}
                onStop={() => stopProject(project.id)}
                onDelete={() => {
                  removeProject(project.id)
                  if (selectedId === project.id) {
                    setSelectedId(projects.find((p) => p.id !== project.id)?.id || null)
                  }
                }}
              />
            ))}
            {projects.length === 0 && (
              <div className="text-center py-8 text-muted-foreground text-sm">
                暂无项目
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* 右侧详情 */}
      <div className="flex-1 p-6">
        {selectedProject ? (
          <PipelineView project={selectedProject} />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            选择一个项目查看详情
          </div>
        )}
      </div>
    </div>
  )
}
