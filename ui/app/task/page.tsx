'use client'

import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
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
import { ListTodo, Clock, CheckCircle, XCircle, Loader2, Trash2, StopCircle, Terminal, Plus, Search, Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Task } from '@/lib/types'
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

  const toggleTool = (groupName: string, toolName: string, groupToolNames: string[]) => {
    let next = selectedTools

    if (next.includes(groupName)) {
      const expanded = new Set(next.filter((t) => t !== groupName))
      for (const n of groupToolNames) expanded.add(n)
      next = Array.from(expanded)
    }

    next = next.includes(toolName) ? next.filter((t) => t !== toolName) : [...next, toolName]
    onSelectionChange(next)
  }

  const setGroupSelection = (groupName: string, toolNames: string[], checked: boolean) => {
    if (checked) {
      const remaining = selectedTools.filter((t) => t !== groupName && !toolNames.includes(t))
      onSelectionChange(Array.from(new Set([...remaining, groupName])))
      return
    }
    onSelectionChange(selectedTools.filter((t) => t !== groupName && !toolNames.includes(t)))
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
                      const groupSelected = selectedTools.includes(group.name)
                      const selectedCount = groupSelected ? toolNames.length : toolNames.filter((n) => selectedTools.includes(n)).length
                      const totalCount = toolNames.length
                      const groupChecked = totalCount === 0 ? false : groupSelected ? true : selectedCount === 0 ? false : selectedCount === totalCount ? true : 'indeterminate'

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
                                const isSelected = groupSelected || selectedTools.includes(tool.name)
                                return (
                                  <button
                                    key={toolIdentifier}
                                    type="button"
                                    onClick={() => toggleTool(group.name, tool.name, toolNames)}
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

function TaskCard({ 
  task, 
  isSelected, 
  onSelect,
  onStop,
  onDelete,
}: { 
  task: Task
  isSelected: boolean
  onSelect: () => void
  onStop: () => void
  onDelete: () => void
}) {
  const config = statusConfig[task.status]
  const Icon = config.icon

  return (
    <ContextMenu>
      <ContextMenuTrigger>
        <Card 
          id={`task-card-${task.id}`}
          className={cn(
            'cursor-pointer transition-all hover:border-primary/50',
            isSelected && 'border-primary ring-1 ring-primary'
          )}
          onClick={onSelect}
        >
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-sm">
              <span className="truncate">{task.name}</span>
              <span className={cn('flex items-center gap-1 text-xs px-2 py-1 rounded-full shrink-0', config.bg, config.color)}>
                <Icon className={cn('size-3', task.status === 'running' && 'animate-spin')} />
                {config.label}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Progress value={task.progress} className="h-1.5" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{task.progress}% 完成</span>
              {task.projectId && <span>项目: {task.projectId}</span>}
            </div>
          </CardContent>
        </Card>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem 
          onClick={(e) => { e.stopPropagation(); onStop(); }}
          disabled={task.status !== 'running' && task.status !== 'pending'}
        >
          <StopCircle className="size-4 mr-2" />
          终止任务
        </ContextMenuItem>
        <ContextMenuItem 
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="text-destructive"
        >
          <Trash2 className="size-4 mr-2" />
          删除并终止任务
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

function TaskDetailView({ task }: { task: Task }) {
  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardHeader className="shrink-0">
        <CardTitle className="flex items-center justify-between">
          <span>{task.name}</span>
          <span className={cn(
            'text-xs px-2 py-1 rounded-full',
            statusConfig[task.status].bg,
            statusConfig[task.status].color
          )}>
            {statusConfig[task.status].label}
          </span>
        </CardTitle>
        {task.description && (
          <p className="text-sm text-muted-foreground">{task.description}</p>
        )}
      </CardHeader>
      <CardContent className="flex-1 flex flex-col space-y-4 min-h-0 overflow-hidden">
        <div className="space-y-2 shrink-0">
          <div className="flex justify-between text-sm">
            <span>任务进度</span>
            <span className="font-medium">{task.progress}%</span>
          </div>
          <Progress value={task.progress} className="h-2" />
        </div>

        {task.projectId && (
          <div className="text-sm shrink-0">
            <span className="text-muted-foreground">所属项目: </span>
            <span className="font-medium">{task.projectId}</span>
          </div>
        )}

        <div className="flex-1 flex flex-col min-h-0 space-y-4">
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex items-center gap-2 mb-2 shrink-0">
              <Terminal className="size-4" />
              <h4 className="text-sm font-medium">对话历史 (Worker)</h4>
            </div>
            <ScrollArea className="flex-1 rounded-md border bg-muted/30 min-h-0">
              <div className="p-3 space-y-3">
                {task.history && task.history.length > 0 ? (
                  task.history.map((msg, index) => (
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

          <div className="h-48 flex flex-col shrink-0">
            <div className="flex items-center gap-2 mb-2 shrink-0">
              <Terminal className="size-4" />
              <h4 className="text-sm font-medium">执行日志</h4>
            </div>
            <ScrollArea className="flex-1 rounded-md border bg-muted/30 min-h-0">
              <div className="p-3 font-mono text-xs space-y-1">
                {task.logs && task.logs.length > 0 ? (
                  task.logs.map((log, index) => (
                    <div key={index} className="text-muted-foreground">
                      {log}
                    </div>
                  ))
                ) : (
                  <div className="text-muted-foreground italic">暂无日志</div>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>

        <div className="pt-4 border-t space-y-1 text-xs text-muted-foreground shrink-0">
          <div>创建时间: {task.createdAt.toLocaleString('zh-CN')}</div>
          {task.updatedAt && (
            <div>更新时间: {task.updatedAt.toLocaleString('zh-CN')}</div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function AddTaskDialog() {
  const addTask = useAppStore((state) => state.addTask)
  const [open, setOpen] = useState(false)
  const fetchModelConfig = useAppStore((state) => state.fetchModelConfig)
  const fetchToolGroups = useAppStore((state) => state.fetchToolGroups)
  const modelConfig = useAppStore((state) => state.modelConfig)
  const [formData, setFormData] = useState({
    title: '',
    desc: '',
    deliverable: '',
    worker: '',
    judger: '',
    available_tools: [] as string[],
    prompt: '',
    judge_mode: false,
    task_histories: ''
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
      worker: modelNames.includes(prev.worker) ? prev.worker : modelNames[0],
      judger: modelNames.includes(prev.judger) ? prev.judger : modelNames[0],
    }))
  }, [open, modelNames])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await addTask(formData)
    setOpen(false)
    setFormData({
      title: '',
      desc: '',
      deliverable: '',
      worker: '',
      judger: '',
      available_tools: [],
      prompt: '',
      judge_mode: false,
      task_histories: ''
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
          <DialogTitle>新建任务 (Simple Task)</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
          <div className="grid gap-6 md:grid-cols-[1fr_340px] py-4 flex-1 min-h-0">
            <div className="min-h-0 pr-4">
              <ScrollArea className="max-h-[62vh]">
                <div className="space-y-4 pr-4">
                <div className="space-y-2">
                  <Label htmlFor="title">任务标题</Label>
                  <Input
                    id="title"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                    placeholder="输入任务标题..."
                    className="shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="deliverable">交付物要求</Label>
                  <Input
                    id="deliverable"
                    value={formData.deliverable}
                    onChange={(e) => setFormData({ ...formData, deliverable: e.target.value })}
                    placeholder="描述最终交付的内容..."
                    className="shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    required
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>执行者 (Worker)</Label>
                    <ModelNameSelect
                      value={formData.worker}
                      onValueChange={(v) => setFormData({ ...formData, worker: v })}
                      placeholder="选择 Worker 模型"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>质检员 (Judger)</Label>
                    <ModelNameSelect
                      value={formData.judger}
                      onValueChange={(v) => setFormData({ ...formData, judger: v })}
                      placeholder="选择 Judger 模型"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="prompt">任务描述</Label>
                  <Textarea
                    id="prompt"
                    value={formData.prompt}
                    onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
                    placeholder="详细描述任务..."
                    spellCheck={false}
                    className="min-h-[180px] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    required
                  />
                </div>
                <div className="flex items-center justify-between space-x-2 pt-2">
                  <Label htmlFor="judge_mode">开启质检模式</Label>
                  <Switch
                    id="judge_mode"
                    checked={formData.judge_mode}
                    onCheckedChange={(checked) => setFormData({ ...formData, judge_mode: checked })}
                  />
                </div>
                </div>
              </ScrollArea>
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

export default function TaskPage() {
  const tasks = useAppStore((state) => state.tasks)
  const removeTask = useAppStore((state) => state.removeTask)
  const stopTask = useAppStore((state) => state.stopTask)
  const [selectedId, setSelectedId] = useState<string | null>(tasks[0]?.id || null)
  const searchParams = useSearchParams()
  
  const selectedTask = tasks.find((t) => t.id === selectedId)
  const runningCount = tasks.filter((t) => t.status === 'running').length

  useEffect(() => {
    const taskId = searchParams.get('taskId')
    if (!taskId) return
    if (!tasks.some((t) => t.id === taskId)) return
    setSelectedId(taskId)
    window.setTimeout(() => {
      document.getElementById(`task-card-${taskId}`)?.scrollIntoView({ block: 'center' })
    }, 0)
  }, [searchParams, tasks])

  return (
    <div className="h-[calc(100vh-4rem)] flex">
      {/* 左侧任务列表 */}
      <div className="w-80 border-r flex flex-col min-h-0 overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ListTodo className="size-5" />
            <h1 className="font-semibold">任务队列</h1>
          </div>
          <AddTaskDialog />
        </div>
        <ScrollArea type="always" className="flex-1 min-h-0">
          <div className="p-4 space-y-8 pr-3">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                isSelected={selectedId === task.id}
                onSelect={() => setSelectedId(task.id)}
                onStop={() => stopTask(task.id)}
                onDelete={() => {
                  removeTask(task.id)
                  if (selectedId === task.id) {
                    setSelectedId(tasks.find((t) => t.id !== task.id)?.id || null)
                  }
                }}
              />
            ))}
            {tasks.length === 0 && (
              <div className="text-center py-8 text-muted-foreground text-sm">
                暂无任务
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* 右侧详情 */}
      <div className="flex-1 p-6 min-h-0 overflow-hidden">
        {selectedTask ? (
          <TaskDetailView task={selectedTask} />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            选择一个任务查看详情
          </div>
        )}
      </div>
    </div>
  )
}
