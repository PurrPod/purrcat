'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area'
import { useAppStore } from '@/lib/store'
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'

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

  const getExpertTypeName = (expertType?: string) => {
    return expertType || 'BaseTask'
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger>
        <div
            id={`task-card-${task.id}`}
            className={cn(
              'cursor-pointer transition-all duration-200 py-4 px-3 rounded-[12px] overflow-hidden max-w-full',
              isSelected
                ? 'bg-primary/5 shadow-sm'
                : 'hover:bg-accent/50 bg-background/50'
            )}
            onClick={onSelect}
          >
          <div className="flex items-center justify-between text-sm min-w-0 mb-3">
            <div className="min-w-0 flex-1 max-w-[40%]">
              <span className="truncate block font-medium" title={task.name}>{task.name}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Dialog open={metaOpen} onOpenChange={setMetaOpen}>
                <DialogTrigger asChild>
                  <button
                    type="button"
                    onClick={(e) => e.stopPropagation()}
                    className="rounded-full p-1 hover:bg-muted/60 transition-colors"
                    aria-label="任务信息"
                  >
                    <Info className="size-4 text-muted-foreground" />
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
                    {task.expert_type && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">子任务类型</span>
                        <span className="font-medium">{getExpertTypeName(task.expert_type)}</span>
                      </div>
                    )}
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
          </div>
          <div className="space-y-2.5">
            <div className="flex items-center gap-3">
              <Progress value={task.progress} className="h-1.5 flex-1" />
              <span className="text-[11px] text-muted-foreground shrink-0">{task.progress}%</span>
            </div>
            {task.projectId && (
              <div className="text-[11px] text-muted-foreground">
                项目: {task.projectId}
              </div>
            )}
          </div>
        </div>
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

  // Auto-scroll logic similar to home page
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)

  const handleScroll = useCallback(() => {
    if (scrollContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current
      const atBottom = scrollHeight - scrollTop - clientHeight < 100
      setIsAtBottom(atBottom)
    }
  }, [])

  useEffect(() => {
    if (isAtBottom && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [entries, isAtBottom])

  const handleForcePush = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!pushContent.trim() || isPushing) return

    setIsPushing(true)
    setIsAtBottom(true)

    if (scrollContainerRef.current) {
      setTimeout(() => {
        if(scrollContainerRef.current) {
           scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
        }
      }, 50)
    }

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
  }, [normalizeEntry, task.id, apiFetch])

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
  }, [fetchMore, task.id, apiFetch])

  const renderEntry = (entry: TaskLogEntry) => {
    const style = entry.metadata?.style
    const surfaceClass = (() => {
      if (style === 'light_gray') return 'bg-muted/50 border border-border/40'
      if (style === 'gray') return 'bg-muted border border-border/40'
      if (style === 'dark_white') return 'bg-muted/30 border border-border/40'
      if (style === 'white') return 'bg-background border border-border/40 shadow-sm'
      return 'bg-background border border-border/40 shadow-sm'
    })()

    if (entry.card_type === 'error') {
      return (
        <div className="rounded-[16px] border border-destructive/30 bg-destructive/10 p-4">
          <div className="text-sm font-medium text-destructive mb-1 flex items-center gap-2">
            <XCircle className="size-4" /> 错误
          </div>
          <div className="text-sm whitespace-pre-wrap break-words">{entry.content}</div>
        </div>
      )
    }

    if (entry.card_type === 'system') {
      return (
        <div className={cn('rounded-[16px] p-4 text-sm text-muted-foreground', surfaceClass)}>
          <div className="font-medium text-foreground mb-2 flex items-center gap-2">
            <Info className="size-4" /> 系统
          </div>
          <div className="whitespace-pre-wrap break-words">{entry.content}</div>
        </div>
      )
    }

    if (entry.card_type === 'tool_call' || entry.card_type === 'tool_result') {
      return (
        <div className="rounded-[16px] p-4 text-sm bg-muted/20 border border-border/40 font-mono text-muted-foreground">
          <div className="whitespace-pre-wrap break-words">{entry.content}</div>
        </div>
      )
    }

    return (
      <div className={cn('rounded-[16px] p-4', surfaceClass)}>
        <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">{entry.content}</div>
      </div>
    )
  }

  const visibleEntries = useMemo(() => {
    const start = Math.max(0, entries.length - visibleCount)
    return entries.slice(start)
  }, [entries, visibleCount])

  return (
    <div className="relative h-full w-full overflow-hidden bg-background">
      {/* 顶部渐变层 */}
      <div className="absolute top-0 left-0 right-0 z-10 bg-gradient-to-b from-background via-background/90 to-transparent pb-16 pointer-events-none" />

      {/* 滑动内容层 */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-y-auto overflow-x-hidden pt-16 pb-4 md:pt-24 md:pb-8 scroll-smooth scrollbar-thin scrollbar-thumb-muted-foreground/20 hover:scrollbar-thumb-muted-foreground/40 scrollbar-track-transparent"
      >
        <div className="max-w-4xl mx-auto w-full px-4 md:px-8 pb-48 flex flex-col">
          {/* Header 区域 */}
          <div className="mb-8 space-y-6 pt-2">
            <div>
              <h3 className="flex items-center gap-4 text-2xl font-semibold tracking-tight min-w-0">
                <span className="truncate flex-1 min-w-0">{task.name}</span>
                <span
                  className={cn(
                    'text-xs px-3 py-1 rounded-full border border-current/20 shrink-0',
                    statusConfig[task.status].bg,
                    statusConfig[task.status].color,
                  )}
                >
                  {statusConfig[task.status].label}
                </span>
              </h3>
              {task.description && (
                <p className="text-muted-foreground mt-3 leading-relaxed">{task.description}</p>
              )}
              <div className="text-sm text-muted-foreground mt-2">
                创建时间: {task.createdAt.toLocaleString('zh-CN')}
              </div>
            </div>

            <div className="bg-muted/20 p-5 rounded-[20px] border border-border/40">
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground font-medium">任务进度</span>
                  <span className="font-bold">{task.progress}%</span>
                </div>
                <Progress value={task.progress} className="h-2.5 bg-muted/50 w-full" />
              </div>
              {task.projectId && (
                <div className="mt-4 text-sm">
                  <div className="flex justify-between items-center min-w-0">
                    <span className="text-muted-foreground shrink-0">所属项目</span>
                    <span className="font-medium bg-background px-2 py-0.5 rounded-md border shadow-sm truncate max-w-[200px]">{task.projectId}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 日志区域 */}
          <div className="flex items-center justify-between mb-4 mt-6 shrink-0 border-b border-border/40 pb-3">
            <div className="flex items-center gap-2">
              <Terminal className="size-5 text-primary" />
              <h4 className="text-base font-semibold">执行日志</h4>
            </div>
            {isFetching && <div className="text-xs text-muted-foreground animate-pulse">同步中…</div>}
          </div>

          <div className="flex-1 flex flex-col space-y-4">
            {visibleEntries.length ? (
              <>
                {entries.length > visibleCount && (
                  <div className="flex justify-center py-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="rounded-full shadow-sm hover:bg-muted/50"
                      onClick={() => setVisibleCount((v) => v + LOG_PAGE_SIZE)}
                    >
                      加载更早日志 ({visibleEntries.length} / {entries.length})
                    </Button>
                  </div>
                )}
                {visibleEntries.map((entry) => <div key={entry.id}>{renderEntry(entry)}</div>)}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <Database className="size-12 mb-4 opacity-20" />
                <span className="text-sm">尚未生成执行日志</span>
              </div>
            )}

            {/* 底部占位 */}
            <div className="h-8 w-full shrink-0" />
          </div>
        </div>
      </div>

      {/* 底部悬浮输入框（类似主页 Omnibar） */}
      <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-background via-background/90 to-transparent pt-48 pb-8 px-4 md:px-8 pointer-events-none">
        <div className="max-w-4xl mx-auto w-full pointer-events-auto">
          <div className="bg-background/80 backdrop-blur-md rounded-[24px] shadow-[0_-10px_40px_rgba(0,0,0,0.05)] border border-border/20 p-4 dark:shadow-none">
            <form onSubmit={handleForcePush} className="flex items-center gap-2">
              <Input
                value={pushContent}
                onChange={(e) => setPushContent(e.target.value)}
                placeholder="强行注入任务指令..."
                className="h-12 flex-1 rounded-[16px] bg-muted/30 border-transparent focus-visible:bg-muted/50 focus-visible:ring-1 focus-visible:ring-primary/50 transition-all shadow-none pl-4 pr-4"
              />
              <Button
                type="submit"
                className="h-12 w-12 rounded-[16px] shadow-sm active:scale-95 transition-all shrink-0 flex items-center justify-center"
                disabled={isPushing || !pushContent.trim()}
              >
                {isPushing ? (
                  <RefreshCcw className="size-4 animate-spin" />
                ) : (
                  <Send className="size-4" />
                )}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
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
    judger: '',
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
      judger: modelNames.includes(prev.judger) ? prev.judger : modelNames[0],
    }))
  }, [open, modelNames])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const fakePath = `/uploads/${file.name}`
      setFormData((prev) => ({ ...prev, prompt: prev.prompt + (prev.prompt ? '\n' : '') + `[文件: ${fakePath}]` }))
    }
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
      // 在前端组合冗余的拆分字段，形成最终的 prompt 交给后端
      const finalPrompt = `${formData.desc ? `【背景描述】：${formData.desc}\n` : ''}【交付物要求】：${formData.deliverable}\n\n【任务详情】：\n${formData.prompt}`

      await addTask({
        task_name: formData.title,
        prompt: finalPrompt,
        core: formData.core,
        judger: formData.judger // 正确传递 judger 模型名，而不是 judge_mode 布尔值
      })
      setOpen(false)
      setFormData({
        title: '',
        desc: '',
        deliverable: '',
        core: '',
        judger: '',
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
        <Button size="icon" variant="secondary" className="size-8 rounded-full shadow-sm">
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
                  <Label>评审模型 (Judger)</Label>
                  <ModelNameSelect
                    value={formData.judger}
                    onValueChange={(v) => setFormData({ ...formData, judger: v })}
                    placeholder="选择评审模型"
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
                    <input
                      ref={fileInputRef}
                      type="file"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Paperclip className="size-4 mr-1" />
                      上传文件
                    </Button>

                    <Dialog open={skillDialogOpen} onOpenChange={setSkillDialogOpen}>
                      <DialogTrigger asChild>
                        <Button type="button" variant="outline" size="sm">
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
                                type="button"
                                onClick={() => handleSkillSelect(skill.path)}
                                className="flex flex-col items-start p-3 rounded-lg border hover:bg-accent transition-colors text-left"
                              >
                                <span className="font-medium text-sm">{skill.name}</span>
                                {skill.description && (
                                  <span className="text-xs text-muted-foreground mt-0.5">
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

                    <Dialog open={dbDialogOpen} onOpenChange={setDbDialogOpen}>
                      <DialogTrigger asChild>
                        <Button type="button" variant="outline" size="sm">
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
                                type="button"
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

  return (
    <div className="absolute inset-0 flex flex-col w-full bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">
        {/* 左侧：任务列表面板 */}
        <ResizablePanel
          defaultSize={28}
          minSize={20}
          maxSize={35}
          className="border-r border-border/10 bg-muted/10 z-20"
        >
          <div className="h-full flex flex-col">
            <div className="h-16 px-6 flex items-center justify-between border-b border-border/10 shrink-0 bg-background/50 backdrop-blur-sm shadow-[0_2px_10px_rgba(0,0,0,0.02)]">
              <div className="flex items-center gap-2">
                <ListTodo className="size-5 text-primary" />
                <h1 className="font-semibold tracking-tight">任务队列</h1>
              </div>
              <AddTaskDialog />
            </div>
            <ScrollArea className="flex-1 overflow-hidden scrollbar-visible">
              <div className="p-4 space-y-3">
                {tasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    isSelected={selectedId === task.id}
                    onSelect={() => setSelectedId(task.id)}
                    onStop={() => stopTask(task.id)}
                    onDelete={() => {
                      removeTask(task.id).then(() => {
                        if (selectedId === task.id) {
                          setSelectedId(tasks.find((t) => t.id !== task.id)?.id || null)
                        }
                      })
                    }}
                  />
                ))}
                {tasks.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-16 text-muted-foreground opacity-50">
                    <ListTodo className="size-10 mb-3" />
                    <span className="text-sm">暂无任务</span>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </ResizablePanel>

        {/* 调节滑块 */}
        <ResizableHandle className="w-1.5 bg-transparent hover:bg-primary/20 transition-colors cursor-col-resize active:bg-primary/40" />

        {/* 右侧：任务详情视窗 (沉浸式布局) */}
        <ResizablePanel defaultSize={75} minSize={50} className="bg-background relative">
          {selectedTask ? (
            <TaskDetailView task={selectedTask} />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
              <Wand2 className="size-16 mb-6 opacity-20" />
              <div className="text-lg font-medium opacity-60">请在左侧选择一个任务查看详情</div>
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}