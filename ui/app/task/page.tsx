'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import {
  ListTodo,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Trash2,
  StopCircle,
  Terminal,
  Plus,
  Search,
  Check,
  ChevronDown,
  AlertCircle,
  Send,
  RefreshCcw,
  Info,
  Paperclip,
  Wand2,
  Database,
} from 'lucide-react'
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
const LOG_PAGE_SIZE = 200
const TASK_LOG_CACHE = new Map<string, { entries: TaskLogEntry[]; cursor: number }>()

type TaskLogEntry = {
  id: string
  task_id?: string
  timestamp: number
  card_type: string
  content: string
  metadata: Record<string, any>
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
  const [metaOpen, setMetaOpen] = useState(false)

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
            <CardTitle className="flex items-center justify-between text-sm min-w-0">
              <div className="min-w-0 flex-1">
                <span className="truncate block" title={task.name}>{task.name}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Dialog open={metaOpen} onOpenChange={setMetaOpen}>
                  <DialogTrigger asChild>
                    <button
                      type="button"
                      onClick={(e) => e.stopPropagation()}
                      className="rounded-full p-1 hover:bg-muted/40"
                      aria-label="任务信息"
                    >
                      <Info className="size-4" />
                    </button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>任务信息</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">ID</span>
                        <span className="font-medium break-all">{task.id}</span>
                      </div>
                      {task.core && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">核心模型</span>
                          <span className="font-medium break-all">{task.core}</span>
                        </div>
                      )}
                      {task.creat_time && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">创建时间</span>
                          <span className="font-medium">{task.creat_time}</span>
                        </div>
                      )}
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">状态</span>
                        <span className="font-medium">{config.label}</span>
                      </div>
                    </div>
                    <DialogFooter>
                      <Button onClick={() => setMetaOpen(false)}>关闭</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
                <span className={cn('flex items-center gap-1 text-xs px-2 py-1 rounded-full shrink-0', config.bg, config.color)}>
                  <Icon className={cn('size-3', task.status === 'running' && 'animate-spin')} />
                  {config.label}
                </span>
              </div>
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
  const apiFetch = useAppStore((state) => state.apiFetch)
  const [entries, setEntries] = useState<TaskLogEntry[]>([])
  const cursorRef = useRef(0)
  const fetchingRef = useRef(false)
  const [isFetching, setIsFetching] = useState(false)
  const initialFetchRef = useRef(true)
  const [visibleCount, setVisibleCount] = useState(LOG_PAGE_SIZE)
  const injectTask = useAppStore((state) => state.injectTask)
  const [pushContent, setPushContent] = useState('')
  const [isPushing, setIsPushing] = useState(false)

  const handleForcePush = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!pushContent.trim() || isPushing) return
    
    setIsPushing(true)
    try {
      await injectTask(task.id, pushContent)
      setPushContent('')
    } finally {
      setIsPushing(false)
    }
  }

  const normalizeEntry = useCallback(
    (raw: any): TaskLogEntry => {
      const metadata = raw?.metadata && typeof raw.metadata === 'object' ? raw.metadata : {}
      const content =
        typeof raw?.content === 'string'
          ? raw.content
          : raw?.content != null
            ? JSON.stringify(raw.content, null, 2)
            : ''
      return {
        id: String(raw?.id ?? `${task.id}:${Math.random().toString(16).slice(2)}`),
        task_id: raw?.task_id,
        timestamp: typeof raw?.timestamp === 'number' ? raw.timestamp : Date.now() / 1000,
        card_type: String(raw?.card_type ?? 'text'),
        content,
        metadata,
      }
    },
    [task.id],
  )

  const fetchMore = useCallback(async () => {
    if (fetchingRef.current) return
    fetchingRef.current = true
    setIsFetching(true)
    try {
      const query = initialFetchRef.current
        ? `tail=true&limit=${LOG_PAGE_SIZE}`
        : `cursor=${cursorRef.current}&limit=${LOG_PAGE_SIZE}`
      const res = await apiFetch(`/tasks/${task.id}/log?${query}`)
      const data = await res.json()
      const nextEntries = Array.isArray(data?.entries) ? data.entries.map(normalizeEntry) : []
      const nextCursor =
        typeof data?.nextCursor === 'number' ? data.nextCursor : cursorRef.current + nextEntries.length
      cursorRef.current = nextCursor
      setEntries((prev) => {
        const merged = [...prev, ...nextEntries]
        TASK_LOG_CACHE.set(task.id, { entries: merged, cursor: nextCursor })
        return merged
      })
      initialFetchRef.current = false
    } catch {
    } finally {
      setIsFetching(false)
      fetchingRef.current = false
    }
  }, [normalizeEntry, task.id])

  useEffect(() => {
    setVisibleCount(LOG_PAGE_SIZE)
    const cached = TASK_LOG_CACHE.get(task.id)
    if (cached) {
      setEntries(cached.entries)
      cursorRef.current = cached.cursor
      initialFetchRef.current = false
    } else {
      setEntries([])
      cursorRef.current = 0
      initialFetchRef.current = true
    }
    fetchMore()
  }, [fetchMore, task.id])

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const res = await apiFetch('/tasks/dirty')
        const data = await res.json()
        if (Array.isArray(data?.dirty) && data.dirty.includes(task.id)) {
          await fetchMore()
        }
      } catch {
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [fetchMore, task.id])

  const renderEntry = (entry: TaskLogEntry) => {
    const style = entry.metadata?.style
    const surfaceClass = (() => {
      if (style === 'light_gray') return 'bg-muted/50 border'
      if (style === 'gray') return 'bg-muted border'
      if (style === 'dark_white') return 'bg-muted/30 border'
      if (style === 'white') return 'bg-background border'
      return 'bg-background border'
    })()

    if (entry.card_type === 'error') {
      return (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3">
          <div className="text-sm font-medium text-destructive mb-1">错误</div>
          <div className="text-xs whitespace-pre-wrap break-words">{entry.content}</div>
        </div>
      )
    }

    if (entry.card_type === 'system') {
      return (
        <div className={cn('rounded-lg p-3 text-xs text-muted-foreground', surfaceClass)}>
          <div className="font-medium text-foreground mb-1">系统</div>
          <div className="whitespace-pre-wrap break-words">{entry.content}</div>
        </div>
      )
    }

    if (entry.card_type === 'tool_call' || entry.card_type === 'tool_result') {
      return (
        <div className="rounded-lg p-3 text-xs bg-muted/30 border">
          <div className="whitespace-pre-wrap break-words text-muted-foreground">{entry.content}</div>
        </div>
      )
    }

    return (
      <div className={cn('rounded-lg p-3', surfaceClass)}>
        <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">{entry.content}</div>
      </div>
    )
  }

  const visibleEntries = useMemo(() => {
    const start = Math.max(0, entries.length - visibleCount)
    return entries.slice(start)
  }, [entries, visibleCount])

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardHeader className="shrink-0">
        <CardTitle className="flex items-center justify-between">
          <span>{task.name}</span>
          <span
            className={cn(
              'text-xs px-2 py-1 rounded-full',
              statusConfig[task.status].bg,
              statusConfig[task.status].color,
            )}
          >
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
              <h4 className="text-sm font-medium">执行日志</h4>
            </div>
            <ScrollArea className="flex-1 rounded-md border bg-muted/30 min-h-0">
              <div className="p-3 space-y-3">
                {visibleEntries.length ? (
                  <>
                    {entries.length > visibleCount ? (
                      <div className="flex justify-center">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setVisibleCount((v) => v + LOG_PAGE_SIZE)}
                        >
                          显示更早日志（已显示 {visibleEntries.length}/{entries.length}）
                        </Button>
                      </div>
                    ) : null}
                    {visibleEntries.map((entry) => <div key={entry.id}>{renderEntry(entry)}</div>)}
                  </>
                ) : (
                  <div className="text-muted-foreground italic text-xs text-center py-4">暂无日志</div>
                )}
              </div>
            </ScrollArea>
            {isFetching ? (
              <div className="text-[11px] text-muted-foreground mt-1 text-right pr-1">同步中…</div>
            ) : null}
          </div>
        </div>

        <div className="pt-4 border-t space-y-1 text-xs text-muted-foreground shrink-0">
          <div>创建时间: {task.createdAt.toLocaleString('zh-CN')}</div>
          {task.updatedAt && (
            <div>更新时间: {task.updatedAt.toLocaleString('zh-CN')}</div>
          )}
        </div>
      </CardContent>

      {/* Force Push 输入框 */}
      <div className="mt-3 pt-3 border-t shrink-0 px-1">
        <form onSubmit={handleForcePush} className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="size-3 text-amber-500" />
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Force Push 注入</span>
          </div>
          <div className="flex items-stretch gap-2">
            <div className="relative flex-1">
              <Input
                value={pushContent}
                onChange={(e) => setPushContent(e.target.value)}
                placeholder="强行注入任务指令..."
                className="text-xs h-9 bg-muted/20 border-border focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-primary/40 transition-all pr-8 shadow-none outline-none ring-0"
              />
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none opacity-30">
                <Send className="size-3" />
              </div>
            </div>
            <Button 
              type="submit" 
              size="sm" 
              variant="secondary" 
              className="h-9 px-4 border border-border/50 font-medium text-xs shadow-sm active:scale-95 transition-all shrink-0"
              disabled={isPushing || !pushContent.trim()}
            >
              {isPushing ? (
                <RefreshCcw className="size-3.5 animate-spin" />
              ) : (
                '注入'
              )}
            </Button>
          </div>
        </form>
      </div>
    </Card>
  )
}

function AddTaskDialog() {
  const addTask = useAppStore((state) => state.addTask)
  const [open, setOpen] = useState(false)
  const fetchModelConfig = useAppStore((state) => state.fetchModelConfig)
  const fetchToolGroups = useAppStore((state) => state.fetchToolGroups)
  const modelConfig = useAppStore((state) => state.modelConfig)
  const skills = useAppStore((state) => state.skills)
  const databases = useAppStore((state) => state.databases)
  const fetchSkills = useAppStore((state) => state.fetchSkills)
  const fetchDatabases = useAppStore((state) => state.fetchDatabases)
  const [skillDialogOpen, setSkillDialogOpen] = useState(false)
  const [dbDialogOpen, setDbDialogOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [formData, setFormData] = useState({
    title: '',
    desc: '',
    deliverable: '',
    core: '',
    prompt: '',
    skills: []
  })

  const modelNames = useMemo(() => {
    const models = (modelConfig?.models ?? {}) as Record<string, any>
    return Object.keys(models)
  }, [modelConfig])

  useEffect(() => {
    if (!open) return
    fetchModelConfig()
    fetchToolGroups()
    fetchSkills()
    fetchDatabases()
  }, [open, fetchModelConfig, fetchToolGroups, fetchSkills, fetchDatabases])

  useEffect(() => {
    if (!open) return
    if (modelNames.length === 0) return
    setFormData((prev) => ({
      ...prev,
      core: modelNames.includes(prev.core) ? prev.core : modelNames[0],
    }))
  }, [open, modelNames])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      // 模拟文件路径（实际应用中会是真实路径）
      const fakePath = `/uploads/${file.name}`
      setFormData((prev) => ({ ...prev, prompt: prev.prompt + (prev.prompt ? '\n' : '') + `[文件: ${fakePath}]` }))
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleSkillSelect = (skillPath: string) => {
    setFormData((prev) => ({ ...prev, prompt: prev.prompt + (prev.prompt ? '\n' : '') + `[Skill: ${skillPath}]` }))
    setSkillDialogOpen(false)
  }

  const handleDatabaseSelect = (dbName: string) => {
    setFormData((prev) => ({ ...prev, prompt: prev.prompt + (prev.prompt ? '\n' : '') + `[数据库: ${dbName}]` }))
    setDbDialogOpen(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await addTask(formData)
      setOpen(false)
      setFormData({
        title: '',
        desc: '',
        deliverable: '',
        core: '',
        prompt: '',
        skills: []
      })
    } catch (error) {
      console.error('Failed to create task:', error)
      alert('创建任务失败，请检查后端服务器是否运行')
    }
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
          <div className="py-4 flex-1 min-h-0">
            <ScrollArea className="max-h-[70vh]">
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
                  <Label>核心模型 (Core)</Label>
                  <ModelNameSelect
                    value={formData.core}
                    onValueChange={(v) => setFormData({ ...formData, core: v })}
                    placeholder="选择核心模型"
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
                <div className="space-y-2">
                  <Label htmlFor="prompt">任务描述</Label>
                  <div className="flex gap-2 mb-2">
                    {/* 上传文件按钮 */}
                    <input
                      ref={fileInputRef}
                      type="file"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Paperclip className="size-4 mr-1" />
                      上传文件
                    </Button>

                    {/* 选择 Skill 按钮 */}
                    <Dialog open={skillDialogOpen} onOpenChange={setSkillDialogOpen}>
                      <DialogTrigger asChild>
                        <Button variant="outline" size="sm">
                          <Wand2 className="size-4 mr-1" />
                          选择 Skill
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>选择 Skill</DialogTitle>
                        </DialogHeader>
                        <ScrollArea className="h-64">
                          <div className="flex flex-col gap-2">
                            {skills.map((skill) => (
                              <button
                                key={skill.name}
                                onClick={() => handleSkillSelect(skill.path)}
                                className="flex flex-col items-start p-3 rounded-lg border hover:bg-accent transition-colors text-left"
                              >
                                <span className="font-medium text-sm">{skill.name}</span>
                                {skill.description && (
                                  <span className="text-xs text-muted-foreground">
                                    {skill.description}
                                  </span>
                                )}
                                <span className="text-xs text-muted-foreground mt-1 font-mono">
                                  {skill.path}
                                </span>
                              </button>
                            ))}
                          </div>
                        </ScrollArea>
                      </DialogContent>
                    </Dialog>

                    {/* 插入数据库按钮 */}
                    <Dialog open={dbDialogOpen} onOpenChange={setDbDialogOpen}>
                      <DialogTrigger asChild>
                        <Button variant="outline" size="sm">
                          <Database className="size-4 mr-1" />
                          插入数据库
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>选择数据库</DialogTitle>
                        </DialogHeader>
                        <ScrollArea className="h-60">
                          <div className="flex flex-col gap-2 p-1">
                            {databases.map((dbName) => (
                              <Button
                                key={dbName}
                                variant="ghost"
                                className="justify-start font-normal"
                                onClick={() => handleDatabaseSelect(dbName)}
                              >
                                <Database className="size-4 mr-2" />
                                {dbName}
                              </Button>
                            ))}
                            {databases.length === 0 && (
                              <div className="text-center py-8 text-muted-foreground text-sm">
                                未发现可用数据库
                              </div>
                            )}
                          </div>
                        </ScrollArea>
                      </DialogContent>
                    </Dialog>
                  </div>
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

              </div>
            </ScrollArea>
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
  
  const selectedTask = tasks.find((t) => t.id === selectedId)
  const runningCount = tasks.filter((t) => t.status === 'running').length

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
