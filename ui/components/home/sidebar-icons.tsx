'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppStore } from '@/lib/store'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { User, BookOpen, Sparkles, Save, Eye, Edit3, Bot } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type FileKey = 'user_profile' | 'me' | 'soul'

const iconButtons = [
  {
    key: 'user_profile' as FileKey,
    icon: User,
    title: 'User Profile',
    description: '用户配置文件',
  },
  {
    key: 'me' as FileKey,
    icon: BookOpen,
    title: 'About Me',
    description: '关于 Agent',
  },
  {
    key: 'soul' as FileKey,
    icon: Sparkles,
    title: 'SOUL',
    description: 'Agent 灵魂配置',
  },
]

export function SidebarIcons() {
  const [activeDialog, setActiveDialog] = useState<FileKey | null>(null)
  const [editContent, setEditContent] = useState('')
  const [viewMode, setViewMode] = useState<'edit' | 'preview'>('preview')
  const [agentDialogOpen, setAgentDialogOpen] = useState(false)
  const [agentModelDraft, setAgentModelDraft] = useState('')
  
  const files = useAppStore((state) => state.files)
  const updateFile = useAppStore((state) => state.updateFile)
  const modelConfig = useAppStore((state) => state.modelConfig)
  const fetchModelConfig = useAppStore((state) => state.fetchModelConfig)
  const updateModelConfig = useAppStore((state) => state.updateModelConfig)

  const modelNames = useMemo(() => {
    const models = (modelConfig?.models ?? {}) as Record<string, any>
    return Object.keys(models)
  }, [modelConfig])

  useEffect(() => {
    if (!agentDialogOpen) return
    fetchModelConfig()
  }, [agentDialogOpen, fetchModelConfig])

  useEffect(() => {
    if (!agentDialogOpen) return
    const configured = (modelConfig as any)?.agent?.model as string | undefined
    if (configured && agentModelDraft !== configured) {
      setAgentModelDraft(configured)
      return
    }
    if (!configured && !agentModelDraft && modelNames.length > 0) {
      setAgentModelDraft(modelNames[0])
    }
  }, [agentDialogOpen, modelConfig, modelNames, agentModelDraft])

  const handleOpen = (key: FileKey) => {
    setEditContent(files[key]?.content || '')
    setActiveDialog(key)
    setViewMode('preview')
  }

  const handleSave = () => {
    if (activeDialog) {
      updateFile(activeDialog, editContent)
    }
    setActiveDialog(null)
  }

  const handleClose = () => {
    setActiveDialog(null)
  }

  const activeFile = activeDialog ? iconButtons.find((b) => b.key === activeDialog) : null

  return (
    <>
      <div className="flex flex-col gap-2">
        {iconButtons.map((item) => (
          <Button
            key={item.key}
            variant="ghost"
            size="icon"
            onClick={() => handleOpen(item.key)}
            className="size-10 rounded-lg hover:bg-accent"
            title={item.description}
          >
            <item.icon className="size-5" />
          </Button>
        ))}

        <div className="h-px bg-border/60 my-1" />

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setAgentDialogOpen(true)}
          className="size-10 rounded-lg hover:bg-accent"
          title="配置主 Agent 模型"
        >
          <Bot className="size-5" />
        </Button>
      </div>

      <Dialog open={activeDialog !== null} onOpenChange={(open) => !open && handleClose()}>
        <DialogContent className="max-w-3xl h-[85vh] flex flex-col overflow-hidden p-0 gap-0">
          <DialogHeader className="flex flex-row items-center justify-between space-y-0 p-4 border-b shrink-0 pr-12">
            <DialogTitle className="flex items-center gap-2 text-base">
              {activeFile && <activeFile.icon className="size-5" />}
              {activeFile?.title}
            </DialogTitle>
            <Tabs
              value={viewMode}
              onValueChange={(v) => setViewMode(v as 'edit' | 'preview')}
              className="mr-2"
            >
              <TabsList className="h-8 p-1">
                <TabsTrigger value="preview" className="h-6 px-3 text-xs gap-1.5">
                  <Eye className="size-3.5" />
                  预览
                </TabsTrigger>
                <TabsTrigger value="edit" className="h-6 px-3 text-xs gap-1.5">
                  <Edit3 className="size-3.5" />
                  编辑
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </DialogHeader>
          
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-4 py-2 bg-muted/30 border-b flex items-center justify-between shrink-0">
              <span className="text-[10px] font-mono text-muted-foreground opacity-70">
                Path: {files[activeDialog || 'user_profile']?.path}
              </span>
              <span className="text-[10px] text-muted-foreground opacity-70">
                Update: {files[activeDialog || 'user_profile']?.lastModified.toLocaleString('zh-CN')}
              </span>
            </div>
            
            <div className="flex-1 min-h-0 p-4">
              <ScrollArea className="h-full pr-4">
                {viewMode === 'edit' ? (
                  <Textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="min-h-[500px] w-full font-mono text-sm resize-none border-none focus-visible:ring-0 p-0 bg-transparent"
                    placeholder="开始编辑 Markdown 内容..."
                  />
                ) : (
                  <div className="prose prose-sm dark:prose-invert max-w-none prose-pre:bg-muted prose-pre:text-muted-foreground">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {editContent || '*内容为空*'}
                    </ReactMarkdown>
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
          
          <DialogFooter className="p-4 border-t shrink-0 bg-muted/10">
            <Button variant="outline" size="sm" onClick={handleClose}>
              取消
            </Button>
            <Button size="sm" onClick={handleSave}>
              <Save className="size-4 mr-2" />
              保存更改
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={agentDialogOpen} onOpenChange={setAgentDialogOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bot className="size-5 text-primary" />
              主 Agent 模型
            </DialogTitle>
          </DialogHeader>

          <div className="py-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">模型名称</span>
              <span className="text-xs text-muted-foreground">{modelNames.length} 个可选</span>
            </div>
            <Select value={agentModelDraft} onValueChange={setAgentModelDraft}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="选择主 Agent 使用的模型" />
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
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAgentDialogOpen(false)}>
              取消
            </Button>
            <Button
              onClick={async () => {
                const currentAgent = ((modelConfig as any)?.agent ?? {}) as Record<string, any>
                await updateModelConfig('agent', { ...currentAgent, model: agentModelDraft })
                setAgentDialogOpen(false)
              }}
              disabled={!agentModelDraft}
            >
              <Save className="size-4 mr-2" />
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
