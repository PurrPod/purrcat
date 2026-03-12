'use client'

import { useRouter } from 'next/navigation'
import { useAppStore } from '@/lib/store'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { FolderKanban, ListTodo, Cpu, Settings } from 'lucide-react'

export function StatusCards() {
  const router = useRouter()
  const projects = useAppStore((state) => state.projects)
  const tasks = useAppStore((state) => state.tasks)
  const modelConfig = useAppStore((state) => state.modelConfig)
  const modelCount = modelConfig?.models ? Object.keys(modelConfig.models).length : 0

  const runningProjects = projects.filter((p) => p.status === 'running').length
  const runningTasks = tasks.filter((t) => t.status === 'running').length

  return (
    <div className="flex flex-col gap-3">
      {/* Project 卡片 */}
      <Card
        className="cursor-pointer hover:bg-accent/50 transition-colors py-4"
        onClick={() => router.push('/project')}
      >
        <CardContent className="p-0 px-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center size-10 rounded-lg bg-blue-500/10 text-blue-500">
              <FolderKanban className="size-5" />
            </div>
            <div>
              <div className="text-2xl font-bold">{runningProjects}</div>
              <div className="text-xs text-muted-foreground">运行中项目</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Task 卡片 */}
      <Card
        className="cursor-pointer hover:bg-accent/50 transition-colors py-4"
        onClick={() => router.push('/task')}
      >
        <CardContent className="p-0 px-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center size-10 rounded-lg bg-green-500/10 text-green-500">
              <ListTodo className="size-5" />
            </div>
            <div>
              <div className="text-2xl font-bold">{runningTasks}</div>
              <div className="text-xs text-muted-foreground">运行中任务</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Model 卡片 */}
      <Card 
        className="cursor-pointer hover:bg-accent/50 transition-colors py-4"
        onClick={() => router.push('/setting#config-model_config.json')}
      >
        <CardContent className="p-0 px-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center size-10 rounded-lg bg-amber-500/10 text-amber-500">
              <Cpu className="size-5" />
            </div>
            <div>
              <div className="text-2xl font-bold">{modelCount}</div>
              <div className="text-xs text-muted-foreground">已配置模型</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
