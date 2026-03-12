'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAppStore } from '@/lib/store'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { FolderKanban, ListTodo, Cpu, Puzzle, Wand2, Search } from 'lucide-react'

export function StatusCards() {
  const router = useRouter()
  const projects = useAppStore((state) => state.projects)
  const tasks = useAppStore((state) => state.tasks)
  const modelConfig = useAppStore((state) => state.modelConfig)
  const plugins = useAppStore((state) => state.plugins)
  const skills = useAppStore((state) => state.skills)
  const modelCount = modelConfig?.models ? Object.keys(modelConfig.models).length : 0
  const pluginCount = plugins.length
  const skillCount = skills.length

  const runningProjects = projects.filter((p) => p.status === 'running').length
  const runningTasks = tasks.filter((t) => t.status === 'running').length
  const [skillDialogOpen, setSkillDialogOpen] = useState(false)
  const [skillSearch, setSkillSearch] = useState('')

  const filteredSkills = useMemo(() => {
    const keyword = skillSearch.trim().toLowerCase()
    if (!keyword) return skills
    return skills.filter((skill) => {
      const name = (skill.name ?? '').toLowerCase()
      const desc = (skill.description ?? '').toLowerCase()
      const path = (skill.path ?? '').toLowerCase()
      return name.includes(keyword) || desc.includes(keyword) || path.includes(keyword)
    })
  }, [skills, skillSearch])

  return (
    <>
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

      {/* Skill 卡片 */}
      <Card
        className="cursor-pointer hover:bg-accent/50 transition-colors py-4"
        onClick={() => setSkillDialogOpen(true)}
      >
        <CardContent className="p-0 px-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center size-10 rounded-lg bg-purple-500/10 text-purple-500">
              <Wand2 className="size-5" />
            </div>
            <div>
              <div className="text-2xl font-bold">{skillCount}</div>
              <div className="text-xs text-muted-foreground">已配置skill</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Plugin 卡片 */}
      <Card
        className="cursor-pointer hover:bg-accent/50 transition-colors py-4"
        onClick={() => router.push('/plugin')}
      >
        <CardContent className="p-0 px-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center size-10 rounded-lg bg-indigo-500/10 text-indigo-500">
              <Puzzle className="size-5" />
            </div>
            <div>
              <div className="text-2xl font-bold">{pluginCount}</div>
              <div className="text-xs text-muted-foreground">已安装插件</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

      <Dialog open={skillDialogOpen} onOpenChange={setSkillDialogOpen}>
        <DialogContent className="sm:max-w-[720px] max-h-[80vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle>已配置 skill ({skillCount})</DialogTitle>
          </DialogHeader>

          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                value={skillSearch}
                onChange={(e) => setSkillSearch(e.target.value)}
                placeholder="搜索 skill 名称 / 描述 / 路径..."
                className="pl-9"
              />
            </div>
            <div className="text-xs text-muted-foreground tabular-nums shrink-0">
              {filteredSkills.length}/{skillCount}
            </div>
          </div>

          <ScrollArea className="mt-3 h-[60vh] rounded-md border bg-background">
            <div className="p-3 flex flex-col gap-2">
              {filteredSkills.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground text-sm">
                  未找到匹配的 skill
                </div>
              ) : (
                filteredSkills.map((skill) => (
                  <div
                    key={skill.name}
                    className="flex flex-col items-start p-3 rounded-lg border bg-muted/10"
                  >
                    <span className="font-medium text-sm">{skill.name}</span>
                    {skill.description && (
                      <span className="text-xs text-muted-foreground mt-0.5">
                        {skill.description}
                      </span>
                    )}
                    {skill.path && (
                      <span className="text-xs text-muted-foreground mt-1 font-mono break-all">
                        {skill.path}
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  )
}
