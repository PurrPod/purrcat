'use client'

import { useState } from 'react'
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
import { ListTodo, Clock, CheckCircle, XCircle, Loader2, Trash2, StopCircle, Terminal, Plus } from 'lucide-react'
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

const statusConfig = {
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: '运行中' },
  pending: { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: '等待中' },
  completed: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-500/10', label: '已完成' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: '失败' },
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
  const [formData, setFormData] = useState({
    title: '',
    desc: '',
    deliverable: '',
    worker: 'openai:deepseek-chat',
    judger: 'openai:deepseek-chat',
    available_tools: [] as string[],
    prompt: '',
    judge_mode: false,
    task_histories: ''
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await addTask(formData)
    setOpen(false)
    setFormData({
      title: '',
      desc: '',
      deliverable: '',
      worker: 'openai:deepseek-chat',
      judger: 'openai:deepseek-chat',
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
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>新建任务 (Simple Task)</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="title">任务标题</Label>
            <Input 
              id="title" 
              value={formData.title} 
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="输入任务标题..."
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="desc">任务描述</Label>
            <Textarea 
              id="desc" 
              value={formData.desc} 
              onChange={(e) => setFormData({ ...formData, desc: e.target.value })}
              placeholder="详细描述任务..."
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
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="worker">执行者 (Worker)</Label>
              <Input 
                id="worker" 
                value={formData.worker} 
                onChange={(e) => setFormData({ ...formData, worker: e.target.value })}
                placeholder="例如: openai:deepseek-chat"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="judger">质检员 (Judger)</Label>
              <Input 
                id="judger" 
                value={formData.judger} 
                onChange={(e) => setFormData({ ...formData, judger: e.target.value })}
                placeholder="例如: openai:deepseek-chat"
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="tools">可用工具 (逗号分隔)</Label>
            <Input 
              id="tools" 
              value={formData.available_tools.join(', ')} 
              onChange={(e) => setFormData({ ...formData, available_tools: e.target.value.split(',').map(s => s.trim()).filter(s => s) })}
              placeholder="例如: filesystem, web, shell"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="prompt">系统提示词 (System Prompt)</Label>
            <Textarea 
              id="prompt" 
              value={formData.prompt} 
              onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
              placeholder="给任务执行者的系统提示..."
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
          <DialogFooter className="pt-4">
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
      <div className="w-80 border-r flex flex-col">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ListTodo className="size-5" />
            <h1 className="font-semibold">任务队列</h1>
          </div>
          <AddTaskDialog />
        </div>
        <ScrollArea className="flex-1">
          <div className="p-4 space-y-3">
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
