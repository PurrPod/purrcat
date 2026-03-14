'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as ScrollAreaPrimitive from '@radix-ui/react-scroll-area'
import { useRouter } from 'next/navigation'
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
import { FolderKanban, Clock, CheckCircle, XCircle, Loader2, Trash2, StopCircle, Plus, Search, Check, ChevronDown, Info } from 'lucide-react'
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const statusConfig = {
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: '运行中' },
  pending: { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: '等待中' },
  completed: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-500/10', label: '已完成' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: '失败' },
}

const API_BASE = 'http://localhost:8000/api'

type ProjectLogEntry = {
  id: string
  project_id?: string
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
              <div className="flex items-center gap-1 min-w-0">
                <span className="truncate">{project.name}</span>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-6 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Info className="size-4 opacity-70" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent
                    align="start"
                    side="right"
                    className="w-[340px]"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="space-y-2">
                      <div className="text-sm font-medium">项目信息</div>
                      <div className="grid grid-cols-[80px_1fr] gap-x-3 gap-y-1 text-xs">
                        <div className="text-muted-foreground">ID</div>
                        <div className="break-all">{project.id}</div>
                        <div className="text-muted-foreground">创建</div>
                        <div>{project.createdAt?.toLocaleString('zh-CN') ?? '-'}</div>
                        <div className="text-muted-foreground">Core</div>
                        <div className="break-all">{project.core ?? '-'}</div>
                        <div className="text-muted-foreground">工具</div>
                        <div className="break-words">
                          {project.availableTools?.length ? project.availableTools.join(', ') : '-'}
                        </div>
                        <div className="text-muted-foreground">工人</div>
                        <div className="break-words">
                          {project.availableWorkers?.length ? project.availableWorkers.join(', ') : '-'}
                        </div>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
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

function ProjectLogView({ project }: { project: Project }) {
  const router = useRouter()
  const [entries, setEntries] = useState<ProjectLogEntry[]>([])
  const cursorRef = useRef(0)
  const fetchingRef = useRef(false)
  const [isFetching, setIsFetching] = useState(false)
  const [collapsedInputs, setCollapsedInputs] = useState<Record<string, boolean>>({})
  const [inputDrafts, setInputDrafts] = useState<Record<string, string>>({})
  const [actionTaken, setActionTaken] = useState<Record<string, 'Accept' | 'Reject'>>({})

  const normalizeEntry = useCallback((raw: any): ProjectLogEntry => {
    const metadata = raw?.metadata && typeof raw.metadata === 'object' ? raw.metadata : {}
    const content =
      typeof raw?.content === 'string'
        ? raw.content
        : raw?.content != null
          ? JSON.stringify(raw.content, null, 2)
          : ''
    return {
      id: String(raw?.id ?? `${project.id}:${Math.random().toString(16).slice(2)}`),
      project_id: raw?.project_id,
      timestamp: typeof raw?.timestamp === 'number' ? raw.timestamp : Date.now() / 1000,
      card_type: String(raw?.card_type ?? 'text'),
      content,
      metadata,
    }
  }, [project.id])

  const fetchMore = useCallback(async () => {
    if (fetchingRef.current) return
    fetchingRef.current = true
    setIsFetching(true)
    try {
      const res = await fetch(
        `${API_BASE}/projects/${project.id}/log?cursor=${cursorRef.current}&limit=500`,
      )
      const data = await res.json()
      const nextEntries = Array.isArray(data?.entries) ? data.entries.map(normalizeEntry) : []
      setEntries((prev) => [...prev, ...nextEntries])
      if (typeof data?.nextCursor === 'number') {
        cursorRef.current = data.nextCursor
      } else {
        cursorRef.current += nextEntries.length
      }
    } catch {
    } finally {
      setIsFetching(false)
      fetchingRef.current = false
    }
  }, [normalizeEntry, project.id])

  useEffect(() => {
    setEntries([])
    setCollapsedInputs({})
    setInputDrafts({})
    setActionTaken({})
    cursorRef.current = 0
    fetchMore()
  }, [fetchMore, project.id])

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/projects/dirty`)
        const data = await res.json()
        if (Array.isArray(data?.dirty) && data.dirty.includes(project.id)) {
          await fetchMore()
        }
      } catch {
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [fetchMore, project.id])

  const { displayItems, latestTaskById } = useMemo(() => {
    const latestTaskById = new Map<string, ProjectLogEntry>()
    const displayItems: Array<{ kind: 'entry'; entry: ProjectLogEntry } | { kind: 'task'; taskId: string }> = []

    for (const entry of entries) {
      if (entry.card_type !== 'task_status') {
        displayItems.push({ kind: 'entry', entry })
        continue
      }

      const taskId = entry.metadata?.task_id
      if (typeof taskId !== 'string' || !taskId) {
        displayItems.push({ kind: 'entry', entry })
        continue
      }

      if (!latestTaskById.has(taskId)) {
        displayItems.push({ kind: 'task', taskId })
      }
      latestTaskById.set(taskId, entry)
    }

    return { displayItems, latestTaskById }
  }, [entries])

  const submitAnswer = async (answer: string) => {
    await fetch(`${API_BASE}/projects/${project.id}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    })
  }

  const renderEntry = (entry: ProjectLogEntry) => {
    const style = entry.metadata?.style
    const surfaceClass = (() => {
      if (style === 'light_gray') return 'bg-muted/50 border'
      if (style === 'gray') return 'bg-muted border'
      if (style === 'dark_white') return 'bg-muted/30 border'
      if (style === 'white') return 'bg-background border'
      return 'bg-background border'
    })()

    if (entry.card_type === 'stage') {
      return (
        <div className="flex justify-center py-2">
          <div className={cn('px-3 py-1 rounded-full text-xs font-medium', surfaceClass)}>
            {entry.content}
          </div>
        </div>
      )
    }

    if (entry.card_type === 'task_list') {
      const tasks = entry.metadata?.tasks
      const rows =
        tasks && typeof tasks === 'object'
          ? Object.entries(tasks as Record<string, any>)
          : ([] as Array<[string, any]>)

      return (
        <div className={cn('rounded-lg p-3', surfaceClass)}>
          <div className="text-sm font-medium mb-2">{entry.content || '子任务列表'}</div>
          {rows.length > 0 ? (
            <div className="space-y-2">
              {rows.map(([key, t]) => (
                <div key={key} className="rounded-md border bg-background/60 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium text-sm truncate">{t?.title ?? key}</div>
                    <div className="text-[11px] text-muted-foreground shrink-0">
                      {t?.task_id ? `#${String(t.task_id).slice(0, 8)}` : ''}
                    </div>
                  </div>
                  {t?.desc ? (
                    <div className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{t.desc}</div>
                  ) : null}
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <div className="text-muted-foreground">交付物</div>
                    <div className="break-words">{t?.deliverable ?? '-'}</div>
                    <div className="text-muted-foreground">Worker</div>
                    <div className="break-words">{t?.worker ?? '-'}</div>
                    <div className="text-muted-foreground">Tools</div>
                    <div className="break-words">
                      {Array.isArray(t?.available_tools) && t.available_tools.length
                        ? t.available_tools.join(', ')
                        : '-'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground italic">暂无可展示的子任务结构</div>
          )}
        </div>
      )
    }

    if (entry.card_type === 'input') {
      const key = entry.id
      const collapsed = collapsedInputs[key]
      const draft = inputDrafts[key] ?? ''

      if (collapsed) {
        return (
          <div className={cn('rounded-lg p-3 text-xs text-muted-foreground', surfaceClass)}>
            <div className="font-medium text-foreground mb-1">已提交输入</div>
            <div className="line-clamp-3 whitespace-pre-wrap">{draft || entry.content}</div>
          </div>
        )
      }

      return (
        <div className={cn('rounded-lg p-3 space-y-2', surfaceClass)}>
          <div className="text-sm font-medium">{entry.content || '请输入'}</div>
          <Textarea
            value={draft}
            onChange={(e) => setInputDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
            placeholder="在这里输入你的回答..."
            className="min-h-[120px] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          <div className="flex justify-end">
            <Button
              size="sm"
              disabled={!draft.trim()}
              onClick={async () => {
                await submitAnswer(draft.trim())
                setCollapsedInputs((prev) => ({ ...prev, [key]: true }))
              }}
            >
              提交
            </Button>
          </div>
        </div>
      )
    }

    if (entry.card_type === 'text_with_action') {
      const key = entry.id
      const taken = actionTaken[key]
      const actions = Array.isArray(entry.metadata?.actions) ? entry.metadata.actions : ['Accept', 'Reject']

      return (
        <div className={cn('rounded-lg p-3 space-y-3', surfaceClass)}>
          <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">{entry.content}</div>
          <div className="flex gap-2">
            {actions.includes('Accept') ? (
              <Button
                size="sm"
                disabled={!!taken}
                onClick={async () => {
                  setActionTaken((prev) => ({ ...prev, [key]: 'Accept' }))
                  await submitAnswer('y')
                }}
              >
                接受
              </Button>
            ) : null}
            {actions.includes('Reject') ? (
              <Button
                size="sm"
                variant="outline"
                disabled={!!taken}
                onClick={async () => {
                  setActionTaken((prev) => ({ ...prev, [key]: 'Reject' }))
                  await submitAnswer('n')
                }}
              >
                拒绝
              </Button>
            ) : null}
            {taken ? <div className="text-xs text-muted-foreground flex items-center">已选择：{taken}</div> : null}
          </div>
        </div>
      )
    }

    if (entry.card_type === 'markdown') {
      return (
        <div className={cn('rounded-lg p-3', surfaceClass)}>
          {entry.metadata?.title ? <div className="text-sm font-medium mb-2">{entry.metadata.title}</div> : null}
          <div className="prose prose-sm dark:prose-invert max-w-none prose-pre:bg-muted prose-pre:text-muted-foreground prose-pre:overflow-x-auto">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry.content || '*内容为空*'}</ReactMarkdown>
          </div>
        </div>
      )
    }

    if (entry.card_type === 'error') {
      return (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3">
          <div className="text-sm font-medium text-destructive mb-1">错误</div>
          <div className="text-xs whitespace-pre-wrap break-words">{entry.content}</div>
        </div>
      )
    }

    return (
      <div className={cn('rounded-lg p-3', surfaceClass)}>
        <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">{entry.content}</div>
      </div>
    )
  }

  const renderTaskCard = (taskId: string, entry: ProjectLogEntry) => {
    const status = String(entry.metadata?.status ?? 'wait')
    const statusUi = (() => {
      if (status === 'success') return { label: '完成', cls: 'bg-green-500/10 text-green-600 dark:text-green-500' }
      if (status === 'failed') return { label: '失败', cls: 'bg-red-500/10 text-red-600 dark:text-red-500' }
      if (status === 'running') return { label: '执行中', cls: 'bg-blue-500/10 text-blue-600 dark:text-blue-500' }
      return { label: '等待', cls: 'bg-amber-500/10 text-amber-600 dark:text-amber-500' }
    })()

    return (
      <button
        type="button"
        className={cn(
          'w-full text-left rounded-lg border bg-background p-3 hover:bg-muted/40 transition-colors',
        )}
        onClick={() => router.push(`/task?taskId=${encodeURIComponent(taskId)}`)}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium whitespace-pre-wrap break-words">{entry.content}</div>
            <div className="text-[11px] text-muted-foreground mt-1">{taskId}</div>
          </div>
          <div className={cn('text-xs px-2 py-1 rounded-full shrink-0', statusUi.cls)}>{statusUi.label}</div>
        </div>
      </button>
    )
  }

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardHeader className="shrink-0">
        <CardTitle className="flex items-center justify-between gap-3">
          <div className="min-w-0 truncate">{project.name}</div>
          <div className="flex items-center gap-2 shrink-0">
            {isFetching ? <div className="text-xs text-muted-foreground">同步中…</div> : null}
            <span
              className={cn(
                'text-xs px-2 py-1 rounded-full',
                statusConfig[project.status].bg,
                statusConfig[project.status].color,
              )}
            >
              {statusConfig[project.status].label}
            </span>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 overflow-hidden">
        <ScrollArea type="always" className="h-full rounded-md border bg-muted/20">
          <div className="p-4 space-y-3 pr-3">
            {displayItems.length ? (
              displayItems.map((item) => {
                if (item.kind === 'entry') {
                  return <div key={item.entry.id}>{renderEntry(item.entry)}</div>
                }
                const latest = latestTaskById.get(item.taskId)
                if (!latest) return null
                return <div key={`task-${item.taskId}`}>{renderTaskCard(item.taskId, latest)}</div>
              })
            ) : (
              <div className="text-xs text-muted-foreground italic text-center py-10">
                暂无日志
              </div>
            )}
          </div>
        </ScrollArea>
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
      <div className="flex-1 p-6 min-h-0 overflow-hidden">
        {selectedProject ? (
          <ProjectLogView project={selectedProject} />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            选择一个项目查看详情
          </div>
        )}
      </div>
    </div>
  )
}
