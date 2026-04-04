'use client'

import React, { useState, useCallback, useEffect } from 'react'
import {
  File,
  Folder,
  ChevronRight,
  ChevronDown,
  Terminal,
  Loader2,
  Eye,
  RefreshCw,
  FolderTree,
  Container
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup
} from "@/components/ui/resizable"
import { useToast } from "@/components/ui/use-toast"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

interface FileItem {
  name: string
  type: 'file' | 'folder'
  children?: FileItem[]
  path: string
}

type DockerStatus = 'checking' | 'running' | 'stopped'

export default function SandboxPage() {
  const { toast } = useToast()
  const [files, setFiles] = useState<FileItem[]>([])
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null)
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['/agent_vm']))
  const [fileContentMap, setFileContentMap] = useState<Record<string, string>>({})
  const [isLoadingTree, setIsLoadingTree] = useState(false)
  const [dockerStatus, setDockerStatus] = useState<DockerStatus>('checking')

  // 检查 Docker 状态
  const checkDockerStatus = useCallback(async () => {
    try {
      // 假设后端提供此接口返回 docker 状态，如 { running: true }
      const res = await fetch('/api/sandbox/status')
      if (res.ok) {
        const data = await res.json()
        setDockerStatus(data.running ? 'running' : 'stopped')
      } else {
        setDockerStatus('stopped')
      }
    } catch (e) {
      // 网络请求失败或接口不存在时视为未运行
      setDockerStatus('stopped')
    }
  }, [])

  // 初始加载及轮询 Docker 状态
  useEffect(() => {
    checkDockerStatus()
    // 每隔 10 秒轮询一次状态
    const interval = setInterval(checkDockerStatus, 10000)
    return () => clearInterval(interval)
  }, [checkDockerStatus])

  const fetchTree = useCallback(async () => {
    setIsLoadingTree(true)
    try {
      const res = await fetch('/api/sandbox/tree')
      if (res.ok) {
        const data = await res.json()
        setFiles(data)
      } else {
        toast({ title: "加载失败", variant: "destructive" })
      }
    } catch (e) {
      toast({ title: "读取工作区失败", variant: "destructive" })
    } finally {
      setIsLoadingTree(false)
    }
  }, [toast])

  const toggleFolder = (path: string) => {
    const next = new Set(expandedFolders)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setExpandedFolders(next)
  }

  const handleSelectFile = async (item: FileItem) => {
    if (item.type === 'folder') {
      toggleFolder(item.path)
      return
    }
    setSelectedFile(item)
    if (fileContentMap[item.path] === undefined) {
      try {
        const res = await fetch(`/api/sandbox/file?path=${encodeURIComponent(item.path)}`)
        if (res.ok) {
          const data = await res.json()
          setFileContentMap(prev => ({ ...prev, [item.path]: data.content }))
        } else {
          toast({ title: "无法读取文件", variant: "destructive" })
        }
      } catch (e) {
        toast({ title: "读取失败", variant: "destructive" })
      }
    }
  }

  const renderTree = (items: FileItem[], depth = 0) => {
    return items.map((item) => {
      const isExpanded = expandedFolders.has(item.path)
      const isSelected = selectedFile?.path === item.path

      return (
        <div key={item.path}>
          <div
            className={cn(
              "flex items-center gap-2 px-2 py-1.5 mx-2 my-0.5 rounded-md cursor-pointer transition-colors text-sm",
              isSelected
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            )}
            style={{ paddingLeft: `${depth * 12 + 8}px` }}
            onClick={() => handleSelectFile(item)}
          >
            {item.type === 'folder' ? (
              <>
                {isExpanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
                <Folder className={cn("size-4 shrink-0", isExpanded ? "fill-primary/20 text-primary" : "fill-muted text-muted-foreground")} />
              </>
            ) : (
              <>
                <div className="size-3.5 shrink-0" />
                <File className={cn("size-4 shrink-0", isSelected ? "text-primary" : "text-muted-foreground/70")} />
              </>
            )}
            <span className="truncate select-none">{item.name}</span>
          </div>
          {item.type === 'folder' && isExpanded && item.children && (
            <div>{renderTree(item.children, depth + 1)}</div>
          )}
        </div>
      )
    })
  }

  return (
    <div className="absolute inset-0 flex flex-col w-full bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">

        {/* 左侧：文件树面板 */}
        <ResizablePanel
          defaultSize={25}
          minSize={20}
          maxSize={35}
          className="border-r border-border/10 bg-muted/10 z-20"
        >
          <div className="h-full flex flex-col">
            {/* 左侧头部 */}
            <div className="h-16 px-6 flex items-center justify-between border-b border-border/10 shrink-0 bg-background/50 backdrop-blur-sm shadow-[0_2px_10px_rgba(0,0,0,0.02)]">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-primary/10 rounded-md">
                    <Terminal className="size-4 text-primary" />
                  </div>
                  <h1 className="font-semibold tracking-tight text-sm">沙盒文件</h1>
                </div>
              </div>

              <Button
                variant="ghost"
                size="icon"
                onClick={fetchTree}
                disabled={isLoadingTree}
                className="h-8 w-8 rounded-full shadow-sm hover:bg-muted/60"
                title="手动刷新工作区"
              >
                <RefreshCw className={cn("size-4", isLoadingTree && "animate-spin")} />
              </Button>
            </div>

            {/* 文件树列表 */}
            <ScrollArea className="flex-1">
              <div className="py-3">
                {isLoadingTree && files.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-muted-foreground opacity-50 animate-pulse">
                    <Loader2 className="size-8 mb-3 animate-spin" />
                    <span className="text-sm">加载工作区中...</span>
                  </div>
                ) : files.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-muted-foreground opacity-50">
                    <FolderTree className="size-10 mb-3" />
                    <span className="text-sm">工作区为空或未加载</span>
                    <span className="text-xs mt-1">请点击右上角刷新按钮</span>
                  </div>
                ) : (
                  renderTree(files)
                )}
              </div>
            </ScrollArea>
          </div>
        </ResizablePanel>

        {/* 调节滑块 */}
        <ResizableHandle className="w-1.5 bg-transparent hover:bg-primary/20 transition-colors cursor-col-resize active:bg-primary/40" />

        {/* 右侧：预览面板 (沉浸式布局) */}
        <ResizablePanel defaultSize={75} minSize={50} className="bg-background relative">
          {/* Docker 状态悬浮指示器 */}
          <div className="absolute bottom-4 right-4 z-20 flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-background/80 backdrop-blur-sm border border-border/50 shadow-sm" title="Docker 沙盒环境状态">
            <Container className={cn(
              "size-4 transition-colors",
              dockerStatus === 'running' && "text-green-500",
              dockerStatus === 'stopped' && "text-red-500",
              dockerStatus === 'checking' && "text-amber-500 animate-pulse"
            )} />
            <span className="text-[10px] font-medium text-muted-foreground select-none">
              {dockerStatus === 'running' ? '运行中' : dockerStatus === 'stopped' ? '未运行' : '检查中'}
            </span>
          </div>

          {selectedFile ? (
            <div className="flex flex-col h-full absolute inset-0">
              {/* 右侧头部 */}
              <div className="h-16 px-6 flex items-center justify-between border-b border-border/10 shrink-0 bg-background/50 backdrop-blur-sm z-10 shadow-[0_2px_10px_rgba(0,0,0,0.02)]">
                <div className="flex items-center gap-3 min-w-0">
                  <File className="size-4.5 text-primary shrink-0" />
                  <span className="text-sm font-medium font-mono text-foreground truncate">
                    {selectedFile.path}
                  </span>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-4">
                  {fileContentMap[selectedFile.path] !== undefined && (
                    <span className="text-[11px] text-muted-foreground/60 font-mono hidden sm:inline-block">UTF-8</span>
                  )}
                  <Badge variant="outline" className="text-xs bg-muted text-muted-foreground border-border/50 font-normal px-2 py-0.5 shadow-sm">
                    <Eye className="size-3 mr-1.5" />
                    只读模式
                  </Badge>
                </div>
              </div>

              {/* 代码内容预览区 */}
              <div className="flex-1 p-0 overflow-hidden relative group bg-background">
                {fileContentMap[selectedFile.path] === undefined ? (
                  <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                    <Loader2 className="size-8 animate-spin opacity-30" />
                  </div>
                ) : (
                  <textarea
                    value={fileContentMap[selectedFile.path] || ''}
                    readOnly
                    spellCheck={false}
                    className="w-full h-full p-6 font-mono text-[13px] bg-transparent border-none outline-none resize-none scrollbar-thin scrollbar-thumb-muted-foreground/20 hover:scrollbar-thumb-muted-foreground/40 leading-relaxed text-foreground/90 whitespace-pre cursor-default focus:ring-0"
                    placeholder="// 该文件为空..."
                  />
                )}
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
              <Terminal className="size-16 mb-4 opacity-20" />
              <div className="text-sm opacity-40">请在左侧选择需要预览的文件</div>
            </div>
          )}
        </ResizablePanel>

      </ResizablePanelGroup>
    </div>
  )
}