'use client'

import { useAppStore } from '@/lib/store'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Puzzle, CheckCircle, XCircle, Plus, UploadCloud, Info, Trash2, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useEffect, useRef, useState } from 'react'
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog'
import type { Plugin } from '@/lib/types'


function PluginDetailDialog({ plugin, onUnregister }: { plugin: Plugin; onUnregister: (name: string) => void }) {
  const [open, setOpen] = useState(false)
  const toolGroups = useAppStore((state) => state.toolGroups)
  const fetchToolGroups = useAppStore((state) => state.fetchToolGroups)

  useEffect(() => {
    if (!open) return
    fetchToolGroups()
  }, [open, fetchToolGroups])

  const group = toolGroups.find((g) => g.name === plugin.name)
  const tools = group?.tools ?? []
  const description = group?.description || plugin.description || "这个插件没有提供详细描述。"

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" className="size-6">
          <Info className="size-4 text-muted-foreground" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Puzzle className="size-5 text-primary"/> 
            {plugin.name}
          </DialogTitle>
          <DialogDescription className="pt-2">
            {description}
          </DialogDescription>
        </DialogHeader>
        
        <div className="py-4">
          <h3 className="font-semibold mb-3 text-sm">包含的工具 ({tools.length})</h3>
          <ScrollArea className="h-[200px] rounded-md border p-3 bg-muted/50">
            {tools.length > 0 ? (
              <div className="space-y-2">
                {tools.map((tool) => (
                  <div key={tool.name} className="flex items-start gap-2 text-xs p-2 bg-background rounded">
                    <Wrench className="size-3.5 text-amber-500 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <div className="font-mono font-semibold text-primary leading-tight break-words">
                        {tool.name}
                      </div>
                      <div className="text-muted-foreground whitespace-normal break-words leading-snug mt-0.5">
                        {tool.description || ''}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                {toolGroups.length === 0 ? '工具列表加载中…' : '此插件未定义任何工具。'}
              </div>
            )}
          </ScrollArea>
        </div>

        <DialogFooter className="sm:justify-between flex-col sm:flex-row gap-2">
          <div className="text-xs text-muted-foreground font-mono">
            版本: {plugin.version || 'N/A'}
          </div>
          <Button
            variant="destructive"
            size="icon"
            className="h-8 w-8"
            onClick={() => {
              if (confirm(`确定要注销并删除插件 '${plugin.name}' 吗？此操作不可逆！`)) {
                onUnregister(plugin.name)
                setOpen(false)
              }
            }}
            aria-label={`注销并删除插件 ${plugin.name}`}
          >
            <Trash2 className="size-4" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


export default function PluginPage() {
  const plugins = useAppStore((state) => state.plugins)
  const togglePlugin = useAppStore((state) => state.togglePlugin)
  const fetchPlugins = useAppStore((state) => state.fetchPlugins)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadStatus, setUploadStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  const enabledCount = plugins.filter((p) => p.enabled).length

  const handleAddPluginClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (!files || files.length === 0) {
      return
    }

    setIsUploading(true)
    setUploadStatus(null)

    const formData = new FormData()
    const folderName = files[0].webkitRelativePath.split('/')[0]
    
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i], files[i].webkitRelativePath)
    }

    try {
      const response = await fetch('/api/plugins/upload', {
        method: 'POST',
        body: formData,
      })

      if (response.ok) {
        const result = await response.json()
        setUploadStatus({ message: result.message || `插件 '${folderName}' 上传成功!`, type: 'success' })
        fetchPlugins() // Refresh the plugin list
      } else {
        const errorText = await response.text();
        let errorMessage = errorText;
        try {
          const errorResult = JSON.parse(errorText);
          errorMessage = errorResult.detail || JSON.stringify(errorResult);
        } catch (e) {
          // The error is not a JSON, so we use the raw text.
        }
        throw new Error(errorMessage);
      }
    } catch (error: any) {
      setUploadStatus({ message: error.message, type: 'error' })
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleUnregisterPlugin = async (name: string) => {
    try {
      const response = await fetch(`/api/plugins/${name}`, {
        method: 'DELETE',
      });
      const result = await response.json();
      if (response.ok) {
        setUploadStatus({ message: result.message || `插件 '${name}' 已成功注销。`, type: 'success' });
        fetchPlugins();
      } else {
        throw new Error(result.detail || '注销失败');
      }
    } catch (error: any) {
      setUploadStatus({ message: error.message, type: 'error' });
    }
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className="p-4 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Puzzle className="size-5" />
            <h1 className="font-semibold">插件管理</h1>
          </div>
          <Button size="sm" onClick={handleAddPluginClick} disabled={isUploading}>
            <Plus className="size-4 mr-2" />
            {isUploading ? '上传中...' : '添加插件'}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
          src/plugins/plugin_collection
          <span className="mx-2">|</span>
          共 {plugins.length} 个插件，{enabledCount} 个已启用
        </p>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6">
          {uploadStatus && (
            <Alert variant={uploadStatus.type === 'error' ? 'destructive' : 'default'} className="mb-4">
              <UploadCloud className="h-4 w-4" />
              <AlertTitle>{uploadStatus.type === 'error' ? '上传失败' : '上传成功'}</AlertTitle>
              <AlertDescription>
                {uploadStatus.message}
              </AlertDescription>
            </Alert>
          )}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {plugins.map((plugin) => (
              <Card 
                key={plugin.name}
                className={cn(
                  'transition-all',
                  plugin.enabled ? 'border-primary/50' : 'opacity-70'
                )}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <div className={cn(
                        'size-8 rounded-lg flex items-center justify-center',
                        plugin.enabled ? 'bg-primary/10' : 'bg-muted'
                      )}>
                        <Puzzle className={cn(
                          'size-4',
                          plugin.enabled ? 'text-primary' : 'text-muted-foreground'
                        )} />
                      </div>
                      <div className="flex items-center gap-1">
                        <CardTitle className="text-sm">{plugin.name}</CardTitle>
                        <PluginDetailDialog plugin={plugin} onUnregister={handleUnregisterPlugin} />
                      </div>
                    </div>
                    <Switch
                      checked={plugin.enabled}
                      onCheckedChange={() => togglePlugin(plugin.name)}
                    />
                  </div>
                </CardHeader>
                <CardContent>
                  {plugin.description && (
                    <CardDescription className="text-xs mb-3">
                      {plugin.description}
                    </CardDescription>
                  )}
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground font-mono truncate max-w-[180px]">
                      {plugin.path}
                    </span>
                    <span className={cn(
                      'flex items-center gap-1',
                      plugin.enabled ? 'text-green-500' : 'text-muted-foreground'
                    )}>
                      {plugin.enabled ? (
                        <>
                          <CheckCircle className="size-3" />
                          已启用
                        </>
                      ) : (
                        <>
                          <XCircle className="size-3" />
                          已禁用
                        </>
                      )}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {plugins.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
            <Puzzle className="size-16 mb-4 opacity-20" />
            <p className="text-lg">暂无插件</p>
            <p className="text-sm">现在可以通过上方的“添加插件”按钮来上传你的第一个插件！</p>
          </div>
        )}
      </ScrollArea>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        // @ts-ignore
        webkitdirectory="true"
        directory="true"
      />
    </div>
  )
}
