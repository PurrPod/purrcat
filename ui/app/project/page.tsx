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
import { FolderKanban, Clock, CheckCircle, XCircle, Loader2, Trash2, StopCircle, Plus, Terminal } from 'lucide-react'
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

const statusConfig = {
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: '运行中' },
  pending: { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: '等待中' },
  completed: { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-500/10', label: '已完成' },
  failed: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: '失败' },
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
  const [formData, setFormData] = useState({
    name: '',
    prompt: '',
    core: 'openai:deepseek-chat',
    check_mode: false,
    refine_mode: false,
    judge_mode: false,
    is_agent: false
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await addProject(formData)
    setOpen(false)
    setFormData({
      name: '',
      prompt: '',
      core: 'openai:deepseek-chat',
      check_mode: false,
      refine_mode: false,
      judge_mode: false,
      is_agent: false
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
          <DialogTitle>新建项目</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">项目名称</Label>
            <Input 
              id="name" 
              value={formData.name} 
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="输入项目名称..."
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
              className="min-h-[100px]"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="core">核心模型 (Core)</Label>
            <Input 
              id="core" 
              value={formData.core} 
              onChange={(e) => setFormData({ ...formData, core: e.target.value })}
              placeholder="例如: openai:deepseek-chat"
              required
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
          <DialogFooter className="pt-4">
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
      <div className="w-80 border-r flex flex-col">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderKanban className="size-5" />
            <h1 className="font-semibold">项目队列</h1>
          </div>
          <AddProjectDialog />
        </div>
        <ScrollArea className="flex-1">
          <div className="p-4 space-y-3">
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
